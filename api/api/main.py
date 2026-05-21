"""FastAPI app exposed on Vercel.

Routes:
- GET  /api/health         → liveness probe
- POST /api/chat           → run an organizer pass / arbitrary prompt
- GET  /api/cron/organize  → cron-protected proactive pass (Vercel Cron hits this)
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from agents.organizer import run_organizer_pass

app = FastAPI(title="vault-mcp api", version="0.1.0")


class ChatRequest(BaseModel):
    prompt: str | None = None


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    result = await run_organizer_pass(req.prompt)
    final = result["messages"][-1] if result.get("messages") else result
    return {"response": getattr(final, "content", str(final))}


@app.get("/api/cron/organize")
async def cron_organize(authorization: str | None = Header(default=None)) -> dict:
    secret = os.environ.get("CRON_SECRET", "")
    expected = f"Bearer {secret}" if secret else None
    if expected and authorization != expected:
        raise HTTPException(status_code=401, detail="invalid cron secret")
    result = await run_organizer_pass(None)
    final = result["messages"][-1] if result.get("messages") else result
    summary = getattr(final, "content", str(final))[:2000]
    return {"status": "ran", "summary": summary}
