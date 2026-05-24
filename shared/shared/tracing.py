"""Tracing primitives for MCP tool calls.

Emits one JSON line per tool call to stderr (consumable by Vercel runtime
logs, Cloud Logging, BigQuery sinks, etc.). stderr — not stdout — because in
stdio transport mode stdout carries the JSON-RPC protocol; writing traces there
would corrupt the message stream.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

_PAYLOAD_BYTES_CAP = 20 * 1024

_RESERVED_EXTRA_KEYS = frozenset(
    {
        "trace_id", "session_id", "request_id", "mcp_server", "tool_name", "category",
        "status", "error", "input", "output", "input_bytes", "output_bytes", "truncated",
        "duration_ms", "work_ms", "upstream_ms_total", "upstream_breakdown",
        "upstream_call_count", "retry_count", "retry_reasons", "total_retry_delay_ms",
        "user_email", "user_name", "user_id", "mcp_client",
    }
)

_identity_extras: dict[str, Callable[[Any], dict[str, Any]]] = {}


def register_identity_extras(mcp_server: str, extractor: Callable[[Any], dict[str, Any]]) -> None:
    _identity_extras[mcp_server] = extractor


@dataclass
class TraceContext:
    trace_id: str
    mcp_server: str
    tool_name: str
    category: str
    started_at: float
    upstream_breakdown: dict[str, int] = field(default_factory=dict)
    upstream_call_count: int = 0
    retry_count: int = 0
    retry_reasons: list[str] = field(default_factory=list)
    total_retry_delay_ms: int = 0


_current_trace: ContextVar[TraceContext | None] = ContextVar("_current_trace", default=None)


def record_retry(reason: str, delay_ms: int) -> None:
    trace = _current_trace.get()
    if trace is None:
        return
    trace.retry_count += 1
    trace.retry_reasons.append(reason)
    trace.total_retry_delay_ms += delay_ms


def record_upstream(name: str, duration_ms: int) -> None:
    trace = _current_trace.get()
    if trace is None:
        return
    trace.upstream_breakdown[name] = trace.upstream_breakdown.get(name, 0) + duration_ms
    trace.upstream_call_count += 1


def _truncate_payload(payload: Any) -> tuple[str, int, bool]:
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = json.dumps(repr(payload), ensure_ascii=False)
    size = len(serialized.encode("utf-8"))
    if size > _PAYLOAD_BYTES_CAP:
        return serialized[:_PAYLOAD_BYTES_CAP] + "…[truncated]", size, True
    return serialized, size, False


def _extract_identity(ctx: Any, mcp_server: str) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "user_email": None, "user_name": None, "user_id": None, "mcp_client": None,
    }
    with contextlib.suppress(Exception):
        token = getattr(ctx, "access_token", None) or getattr(ctx, "token", None)
        claims = getattr(token, "claims", None) if token else None
        if claims:
            identity["user_email"] = claims.get("email")
            identity["user_name"] = claims.get("name")
            identity["user_id"] = claims.get("sub")
    extras_fn = _identity_extras.get(mcp_server)
    if extras_fn is not None:
        with contextlib.suppress(Exception):
            for key, value in (extras_fn(ctx) or {}).items():
                if key not in _RESERVED_EXTRA_KEYS:
                    identity[key] = value
    return identity


def _emit_event(
    trace: TraceContext,
    *,
    status: str,
    error: str | None,
    input_payload: Any,
    output_payload: Any,
    identity: dict[str, Any],
) -> None:
    duration_ms = int((time.monotonic() - trace.started_at) * 1000)
    upstream_ms_total = sum(trace.upstream_breakdown.values())
    work_ms = max(0, duration_ms - upstream_ms_total)

    in_str, in_bytes, in_trunc = _truncate_payload(input_payload)
    out_str, out_bytes, out_trunc = _truncate_payload(output_payload)

    event = {
        "event_type": "mcp_tool_call",
        "trace_id": trace.trace_id,
        "mcp_server": trace.mcp_server,
        "tool_name": trace.tool_name,
        "category": trace.category,
        "status": status,
        "error": error,
        "duration_ms": duration_ms,
        "work_ms": work_ms,
        "upstream_ms_total": upstream_ms_total,
        "upstream_breakdown": trace.upstream_breakdown,
        "upstream_call_count": trace.upstream_call_count,
        "retry_count": trace.retry_count,
        "retry_reasons": trace.retry_reasons,
        "total_retry_delay_ms": trace.total_retry_delay_ms,
        "input": in_str,
        "input_bytes": in_bytes,
        "output": out_str,
        "output_bytes": out_bytes,
        "truncated": in_trunc or out_trunc,
        **identity,
    }
    sys.stderr.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    sys.stderr.flush()


def traced_tool(*, mcp_server: str, category: str, exclude: tuple[str, ...] = ()):
    """Wrap an async tool to emit a tool-call trace event.

    Order matters: ``@mcp.tool(...)`` MUST sit above ``@traced_tool(...)``.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = kwargs.get("ctx")
            input_payload = {k: v for k, v in kwargs.items() if k not in {"ctx", *exclude}}
            trace = TraceContext(
                trace_id=str(uuid.uuid4()),
                mcp_server=mcp_server,
                tool_name=func.__name__,
                category=category,
                started_at=time.monotonic(),
            )
            token = _current_trace.set(trace)
            status, error, output = "ok", None, None
            try:
                output = await func(*args, **kwargs)
                return output
            except BaseException as exc:  # noqa: BLE001
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                _emit_event(
                    trace,
                    status=status,
                    error=error,
                    input_payload=input_payload,
                    output_payload=output,
                    identity=_extract_identity(ctx, mcp_server),
                )
                _current_trace.reset(token)

        return wrapper

    return decorator
