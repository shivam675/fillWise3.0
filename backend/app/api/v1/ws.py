"""
WebSocket endpoint for streaming rewrite job progress.

Clients connect to /ws/jobs/{job_id} with a valid JWT in the query
string (?token=...) since browser WebSocket APIs cannot send headers.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import verify_ws_ticket
from app.db.session import get_session_factory
from app.services.llm.orchestrator import RewriteOrchestrator

_log = structlog.get_logger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/jobs/{job_id}")
async def job_stream(
    websocket: WebSocket,
    job_id: str,
    ticket: str = Query(..., description="Short-lived WS auth ticket"),
) -> None:
    """
    Stream rewrite job progress updates to connected clients.

    Protocol:
      - Client connects with ?token=<access_token>
      - Server sends JobProgressUpdate JSON objects
      - When job completes, server sends {"done": true} and closes
      - Server closes with code 4001 on auth failure
    """
    # Authenticate before accepting
    try:
        payload = verify_ws_ticket(ticket)
        user_id: str = payload["sub"]  # type: ignore[assignment]
    except (JWTError, KeyError):
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await websocket.accept()
    _log.info("ws_client_connected", job_id=job_id, user_id=user_id)

    factory = get_session_factory()
    try:
        async with factory() as db:
            orch = RewriteOrchestrator(db)
            async for update in orch.run(job_id):
                try:
                    await websocket.send_json(update.model_dump())
                except WebSocketDisconnect:
                    _log.info("ws_client_disconnected_during_job", job_id=job_id)
                    return

            # Ensure final job status is persisted
            await db.commit()
            await websocket.send_json({"done": True, "job_id": job_id})

    except WebSocketDisconnect:
        _log.info("ws_client_disconnected", job_id=job_id)
    except Exception as exc:
        _log.error("ws_job_error", job_id=job_id, error=str(exc))
        try:
            await websocket.send_json({"error": str(exc), "done": True})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
