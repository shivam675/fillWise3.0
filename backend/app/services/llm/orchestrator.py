"""
RewriteOrchestrator: schedules and executes section rewrites.

Processes sections in topological (sequence) order, streams tokens
over WebSocket, and stores results to the database.

Each section is committed atomically with the job progress counter so
that a WebSocket disconnect never loses completed work.  Failed
sections are retried up to ``settings.rewrite_max_attempts`` times
with exponential back-off before being marked FAILED.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models.document import Section
from app.db.models.job import JobStatus, RewriteJob, RewriteStatus, SectionRewrite
from app.db.models.ruleset import Ruleset
from app.schemas.job import JobProgressUpdate
from app.services.llm.client import get_ollama_client
from app.services.llm.prompt_engine import PromptEngine
from app.services.risk.analyzer import RiskAnalyzer

_log = structlog.get_logger(__name__)


# ── In-process cancellation flags ──────────────────────────────────── #

_cancellation_flags: dict[str, bool] = {}


def request_cancellation(job_id: str) -> None:
    """Signal a running job to stop after its current section finishes."""
    _cancellation_flags[job_id] = True


def _clear_cancellation(job_id: str) -> None:
    """Remove the cancellation flag for a completed/cancelled job."""
    _cancellation_flags.pop(job_id, None)


class RewriteOrchestrator:
    """
    Orchestrates the full rewrite pipeline for a single RewriteJob.

    Usage:
        orch = RewriteOrchestrator(db)
        async for update in orch.run(job_id):
            await websocket.send_json(update.model_dump())
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._settings = get_settings()
        self._llm = get_ollama_client()
        self._prompt_engine = PromptEngine()
        self._risk_analyzer = RiskAnalyzer()

    async def run(self, job_id: str) -> AsyncIterator[JobProgressUpdate]:
        """
        Execute all pending section rewrites for the job.

        Yields JobProgressUpdate events to be forwarded over WebSocket.

        Each successfully processed section is committed along with the
        updated job.completed_sections counter so disconnects never lose
        completed work.
        """
        log = _log.bind(job_id=job_id)

        job = await self._db.get(RewriteJob, job_id)
        if job is None or job.status not in (JobStatus.PENDING, JobStatus.PAUSED):
            return

        ruleset = await self._db.get(Ruleset, job.ruleset_id)
        if ruleset is None:
            await self._fail_job(job, "Ruleset not found")
            return

        # Fetch all pending rewrites in sequence order
        result = await self._db.execute(
            select(SectionRewrite)
            .join(Section, Section.id == SectionRewrite.section_id)
            .where(
                SectionRewrite.job_id == job_id,
                SectionRewrite.status == RewriteStatus.PENDING,
            )
            .order_by(Section.sequence_no)
        )
        pending: list[SectionRewrite] = list(result.scalars().all())

        # Mark RUNNING and commit immediately so the UI reflects the state
        job.status = JobStatus.RUNNING
        await self._db.commit()

        log.info("job_started", pending_rewrites=len(pending))

        total = job.total_sections or 0

        for rewrite in pending:
            # ── Check for cancellation between sections ─────────────── #
            if _cancellation_flags.get(job_id, False):
                _clear_cancellation(job_id)
                job.status = JobStatus.CANCELLED
                job.error_message = "Job was stopped by user."
                await self._db.commit()
                log.info("job_cancelled_by_user")
                return

            async for update in self._process_rewrite(
                rewrite, ruleset, total, job.completed_sections or 0
            ):
                yield update

            # Atomically commit section outcome + updated job counter
            if rewrite.status in (RewriteStatus.COMPLETED, RewriteStatus.SKIPPED):
                job.completed_sections = (job.completed_sections or 0) + 1
            await self._db.commit()

        # Determine and persist final job status
        failure_result = await self._db.execute(
            select(SectionRewrite).where(
                SectionRewrite.job_id == job_id,
                SectionRewrite.status == RewriteStatus.FAILED,
            )
        )
        failures = list(failure_result.scalars().all())

        if failures:
            job.status = JobStatus.FAILED
            job.error_message = f"{len(failures)} section(s) failed to rewrite."
        else:
            job.status = JobStatus.COMPLETED

        await self._db.commit()
        _clear_cancellation(job_id)
        log.info("job_finished", status=job.status)

    async def _process_rewrite(
        self,
        rewrite: SectionRewrite,
        ruleset: Ruleset,
        total_sections: int = 0,
        completed_sections: int = 0,
    ) -> AsyncIterator[JobProgressUpdate]:
        """
        Process a single SectionRewrite with per-attempt retry logic.

        Retries up to ``settings.rewrite_max_attempts`` times on failure,
        using exponential back-off between attempts.  The caller is
        responsible for committing after this generator is exhausted.
        """
        section = await self._db.get(Section, rewrite.section_id)
        if section is None:
            rewrite.status = RewriteStatus.SKIPPED
            await self._db.flush()
            return

        log = _log.bind(rewrite_id=rewrite.id, section_id=rewrite.section_id)
        max_attempts = self._settings.rewrite_max_attempts
        timeout_seconds = self._settings.ollama_timeout_seconds

        for attempt in range(1, max_attempts + 1):
            rewrite.attempt_number = attempt
            rewrite.status = RewriteStatus.RUNNING
            rewrite.error_message = None
            await self._db.flush()

            yield JobProgressUpdate(
                job_id=rewrite.job_id,
                section_id=rewrite.section_id,
                status=RewriteStatus.RUNNING,
                completed_sections=completed_sections,
                total_sections=total_sections,
                attempt=attempt,
            )

            try:
                # ── Compile prompt ──────────────────────────────────────────────── #
                compiled = self._prompt_engine.compile(
                    rules_json=ruleset.rules_json,
                    section_type=section.section_type,
                    original_text=section.original_text,
                    section_heading=section.heading,
                    jurisdiction=ruleset.jurisdiction,
                )

                rewrite.prompt_hash = compiled.prompt_hash
                rewrite.prompt_text = json.dumps(compiled.to_dict())[:65000]
                rewrite.model_name = self._settings.ollama_model
                await self._db.flush()

                # ── Stream LLM response ───────────────────────────────────────────── #
                start_ms = int(time.monotonic() * 1000)
                token_buffer: list[str] = []
                token_count = 0

                try:
                    async with asyncio.timeout(timeout_seconds):
                        async for token in self._llm.stream_completion(
                            compiled.system_prompt, compiled.user_prompt
                        ):
                            token_buffer.append(token)
                            token_count += 1
                            yield JobProgressUpdate(
                                job_id=rewrite.job_id,
                                section_id=rewrite.section_id,
                                status=RewriteStatus.RUNNING,
                                token=token,
                                completed_sections=completed_sections,
                                total_sections=total_sections,
                                attempt=attempt,
                            )
                except asyncio.TimeoutError:
                    raise Exception(
                        f"LLM response timed out after {timeout_seconds}s"
                    )

                # ── Extract clean text ───────────────────────────────────────────── #
                raw_response = "".join(token_buffer)
                clean_text, _audit_meta = self._prompt_engine.extract_audit_json(raw_response)

                end_ms = int(time.monotonic() * 1000)

                rewrite.rewritten_text = clean_text
                rewrite.tokens_completion = token_count
                rewrite.duration_ms = end_ms - start_ms
                rewrite.status = RewriteStatus.COMPLETED
                await self._db.flush()

                # ── Risk analysis ─────────────────────────────────────────────────── #
                await self._risk_analyzer.analyze(
                    db=self._db,
                    rewrite=rewrite,
                    original_text=section.original_text,
                    rewritten_text=clean_text,
                )

                log.info(
                    "rewrite_complete",
                    attempt=attempt,
                    tokens=token_count,
                    duration_ms=rewrite.duration_ms,
                )

                yield JobProgressUpdate(
                    job_id=rewrite.job_id,
                    section_id=rewrite.section_id,
                    status=RewriteStatus.COMPLETED,
                    completed_sections=completed_sections + 1,
                    total_sections=total_sections,
                    attempt=attempt,
                )
                return  # Success — exit the retry loop

            except Exception as exc:
                log.warning(
                    "rewrite_attempt_failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(exc),
                )
                if attempt < max_attempts:
                    rewrite.status = RewriteStatus.PENDING
                    rewrite.error_message = (
                        f"Attempt {attempt} failed, retrying: {str(exc)[:500]}"
                    )
                    await self._db.flush()
                    # Exponential back-off: 2s, 4s, 8s …
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue

                # All attempts exhausted — mark permanently FAILED
                log.error("rewrite_failed_all_attempts", error=str(exc))
                rewrite.status = RewriteStatus.FAILED
                rewrite.error_message = str(exc)[:1000]
                await self._db.flush()

                yield JobProgressUpdate(
                    job_id=rewrite.job_id,
                    section_id=rewrite.section_id,
                    status=RewriteStatus.FAILED,
                    error=str(exc),
                    completed_sections=completed_sections,
                    total_sections=total_sections,
                    attempt=attempt,
                )

    async def _fail_job(self, job: RewriteJob, message: str) -> None:
        job.status = JobStatus.FAILED
        job.error_message = message
        await self._db.commit()
