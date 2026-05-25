"""FastAPI app exposed on Vercel.

Routes:
- GET  /api/health         → liveness probe (public)
- POST /api/chat           → run an organizer pass / arbitrary prompt (API_SECRET)
- POST /api/agent          → streaming chat (API_SECRET)
- GET  /api/cron/organize  → cron-protected proactive pass (CRON_SECRET)

Auth: routes that trigger agent runs (vault mutations + model spend) require a
bearer token. ``/api/chat`` and ``/api/agent`` use ``API_SECRET``; the Vercel
cron route uses ``CRON_SECRET``. If a secret is unset the matching route stays
open for local dev — set it before deploying publicly.
"""

from __future__ import annotations

import hmac
import os

from agents.chat import astream_chat
from agents.organizer import run_organizer_pass
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="vault-mcp api", version="0.1.0")


def _require_secret(authorization: str | None, env_var: str) -> None:
    """401 unless ``authorization`` is ``Bearer <env_var>`` (constant-time).

    No-op when the env var is unset, so local dev works without ceremony.
    """
    secret = os.environ.get(env_var, "")
    if not secret:
        return
    if not (authorization and hmac.compare_digest(authorization, f"Bearer {secret}")):
        raise HTTPException(status_code=401, detail="unauthorized")


def require_api_secret(authorization: str | None = Header(default=None)) -> None:
    _require_secret(authorization, "API_SECRET")


class ChatRequest(BaseModel):
    prompt: str | None = None
    dry_run: bool = False


class Turn(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    messages: list[Turn]


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", dependencies=[Depends(require_api_secret)])
async def chat(req: ChatRequest) -> dict:
    try:
        result = await run_organizer_pass(req.prompt, dry_run=req.dry_run)
    except Exception as exc:  # noqa: BLE001 — surface as JSON, never a 500 HTML page
        return {"response": None, "error": f"{type(exc).__name__}: {exc}"}
    final = result["messages"][-1] if result.get("messages") else result
    return {"response": getattr(final, "content", str(final))}


@app.post("/api/agent", dependencies=[Depends(require_api_secret)])
async def agent_stream(req: AgentRequest) -> StreamingResponse:
    messages = [{"role": t.role, "content": t.content} for t in req.messages]

    async def gen():
        async for token in astream_chat(messages):
            yield token

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@app.get("/api/cron/organize")
async def cron_organize(authorization: str | None = Header(default=None)) -> dict:
    _require_secret(authorization, "CRON_SECRET")
    try:
        result = await run_organizer_pass(None)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    final = result["messages"][-1] if result.get("messages") else result
    summary = getattr(final, "content", str(final))[:2000]
    return {"status": "ran", "summary": summary}
