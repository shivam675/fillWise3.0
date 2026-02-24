"""
RewriteOrchestrator: schedules and executes section rewrites.

Processes sections in topological (sequence) order, streams tokens
over WebSocket, and stores results to the database.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models.document import Section
from app.db.models.job import JobStatus, RewriteJob, RewriteStatus, SectionRewrite
from app.db.models.ruleset import Ruleset
from app.schemas.job import JobProgressUpdate
from app.services.llm.client import OllamaClient
from app.services.llm.prompt_engine import PromptEngine
from app.services.risk.analyzer import RiskAnalyzer

if TYPE_CHECKING:
    pass

_log = structlog.get_logger(__name__)


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
        self._llm = OllamaClient()
        self._prompt_engine = PromptEngine()
        self._risk_analyzer = RiskAnalyzer()

    async def run(self, job_id: str) -> AsyncIterator[JobProgressUpdate]:
        """
        Execute all pending section rewrites for the job.

        Yields JobProgressUpdate events that should be forwarded to the
        connected WebSocket client.
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

        job.status = JobStatus.RUNNING
        # total_sections is already set by _schedule_rewrites; don't double it
        await self._db.flush()

        log.info("job_started", pending_rewrites=len(pending))

        total = job.total_sections or 0

        for rewrite in pending:
            async for update in self._process_rewrite(rewrite, ruleset, total, job.completed_sections or 0):
                yield update

            job.completed_sections = (job.completed_sections or 0) + 1
            await self._db.flush()

        # Determine final status
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

        await self._db.flush()
        log.info("job_finished", status=job.status)

    async def _process_rewrite(
        self, rewrite: SectionRewrite, ruleset: Ruleset,
        total_sections: int = 0, completed_sections: int = 0,
    ) -> AsyncIterator[JobProgressUpdate]:
        """Process a single SectionRewrite, yield token updates."""
        section = await self._db.get(Section, rewrite.section_id)
        if section is None:
            rewrite.status = RewriteStatus.SKIPPED
            await self._db.flush()
            return

        log = _log.bind(rewrite_id=rewrite.id, section_id=rewrite.section_id)
        rewrite.status = RewriteStatus.RUNNING
        await self._db.flush()

        yield JobProgressUpdate(
            job_id=rewrite.job_id,
            section_id=rewrite.section_id,
            status=RewriteStatus.RUNNING,
            completed_sections=completed_sections,
            total_sections=total_sections,
        )

        try:
            # Compile prompt
            compiled = self._prompt_engine.compile(
                rules_json=ruleset.rules_json,
                section_type=section.section_type,
                original_text=section.original_text,
                section_heading=section.heading,
                jurisdiction=ruleset.jurisdiction,
            )

            rewrite.prompt_hash = compiled.prompt_hash
            rewrite.prompt_text = (
                json.dumps(compiled.to_dict())[:65000]  # guard against DB overflow
            )
            rewrite.model_name = self._settings.ollama_model
            await self._db.flush()

            # Stream LLM response with timeout
            start_ms = int(time.monotonic() * 1000)
            token_buffer: list[str] = []
            token_count = 0
            
            # 5 minute timeout for LLM response
            REWRITE_TIMEOUT = 300  # seconds

            try:
                async with asyncio.timeout(REWRITE_TIMEOUT):
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
                        )
            except asyncio.TimeoutError:
                log.warning("rewrite_timeout", timeout_seconds=REWRITE_TIMEOUT)
                raise Exception(f"LLM response timed out after {REWRITE_TIMEOUT} seconds")

            raw_response = "".join(token_buffer)
            clean_text, _audit_meta = self._prompt_engine.extract_audit_json(raw_response)

            end_ms = int(time.monotonic() * 1000)

            rewrite.rewritten_text = clean_text
            rewrite.tokens_completion = token_count
            rewrite.duration_ms = end_ms - start_ms
            rewrite.status = RewriteStatus.COMPLETED
            await self._db.flush()

            # Risk analysis
            await self._risk_analyzer.analyze(
                db=self._db,
                rewrite=rewrite,
                original_text=section.original_text,
                rewritten_text=clean_text,
            )

            log.info(
                "rewrite_complete",
                tokens=token_count,
                duration_ms=rewrite.duration_ms,
            )

            yield JobProgressUpdate(
                job_id=rewrite.job_id,
                section_id=rewrite.section_id,
                status=RewriteStatus.COMPLETED,
                completed_sections=completed_sections + 1,
                total_sections=total_sections,
            )

        except Exception as exc:
            log.error("rewrite_failed", error=str(exc))
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
            )

    async def _fail_job(self, job: RewriteJob, message: str) -> None:
        job.status = JobStatus.FAILED
        job.error_message = message
        await self._db.flush()
