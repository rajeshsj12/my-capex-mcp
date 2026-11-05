from __future__ import annotations

import logging
import os
import sys
import traceback
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# TOP-LEVEL FastAPI instance (Required by Vercel static analyzer at column 0)
app = FastAPI(
    title="Enterprise MySQL Analytics MCP Server",
    description="Open public Model Context Protocol Server with comprehensive business intelligence and Q&A tools.",
    version="2.0.0",
)

# Enable CORS for all clients (Claude Desktop, Cursor, Web Agents)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Capture any unhandled server error and return detailed JSON diagnostics
    instead of an opaque Vercel 500 FUNCTION_INVOCATION_FAILED.
    """
    err_trace = traceback.format_exc()
    logging.getLogger("mcp-server").error(f"Global unhandled error on {request.url.path}: {err_trace}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc),
            "path": str(request.url.path),
            "traceback": err_trace,
        },
    )


# Ensure both project root and 'api' directory are in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
for p in [CURRENT_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

_startup_error: str | None = None

try:
    from src import db
    from src.auth import UserContext, get_current_user
    from src.config import get_public_url, settings
    from src.mcp_handler import (
        MCP_PROTOCOL_VERSION,
        active_sessions,
        process_jsonrpc_request,
        session_users,
        sse_event_stream,
    )

    logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
    logger = logging.getLogger("mcp-server")
except Exception:
    _startup_error = traceback.format_exc()
    logger = logging.getLogger("mcp-server")
    logger.error(f"Startup import error: {_startup_error}")


@app.get("/")
@app.get("/api")
@app.get("/api/")
@app.get("/api/index")
@app.get("/api/index.py")
async def root():
    """Server info and diagnostic status."""
    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Startup initialization failed",
                "traceback": _startup_error,
            },
        )

    try:
        db_status = await db.check_connection()
    except Exception as e:
        db_status = {"connected": False, "error": str(e)}

    return {
        "name": "Enterprise MySQL Analytics MCP Server",
        "public_url": get_public_url(),
        "status": "online",
        "access": "Public (No authentication required)",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "endpoints": {
            "stateless_mcp": "POST /mcp",
            "sse_transport": "GET /sse",
            "messages": "POST /messages?sessionId={id}",
            "health": "GET /health",
        },
        "available_topics": [
            "financial_performance",
            "asset_portfolio",
            "sustainability_carbon",
            "iot_operations",
            "global_geography",
            "commercial_sakila",
        ],
    }


@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check endpoint for uptime monitoring."""
    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={
                "status": "degraded",
                "error": "Startup error",
                "traceback": _startup_error,
            },
        )
    try:
        db_status = await db.check_connection()
    except Exception as e:
        db_status = {"connected": False, "error": str(e)}

    return {
        "status": "healthy" if db_status.get("connected") else "degraded",
        "database": db_status,
    }


# -----------------------------------------------------------------------------
# 1. Stateless HTTP JSON-RPC MCP Endpoint (Vercel Serverless Ready)
# -----------------------------------------------------------------------------
@app.post("/mcp")
@app.post("/api/mcp")
async def handle_stateless_mcp(
    request: dict[str, Any] | list[dict[str, Any]],
    user: UserContext = Depends(get_current_user),
):
    """
    Direct JSON-RPC 2.0 endpoint for MCP.
    Publicly accessible, stateless, zero session drop risk on Vercel.
    """
    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={"error": "Startup error", "traceback": _startup_error},
        )

    if isinstance(request, list):
        results = []
        for req in request:
            res = await process_jsonrpc_request(req, user)
            if res is not None:
                results.append(res)
        return results
    else:
        res = await process_jsonrpc_request(request, user)
        if res is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return res


# -----------------------------------------------------------------------------
# 2. SSE Transport Endpoints (Claude Desktop / Cursor)
# -----------------------------------------------------------------------------
@app.get("/sse")
@app.get("/api/sse")
async def handle_sse(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    """
    Server-Sent Events connection endpoint.
    Publicly accessible.
    """
    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={"error": "Startup error", "traceback": _startup_error},
        )

    session_id = str(uuid.uuid4())
    logger.info(f"Opening public SSE session {session_id} for {user.username}")

    base_url = str(request.base_url).rstrip("/")

    return StreamingResponse(
        sse_event_stream(session_id, user, base_url),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/messages")
@app.post("/api/messages")
async def handle_messages(
    request: Request,
    sessionId: str | None = None,
    user: UserContext | None = Depends(get_current_user),
):
    """
    Receives JSON-RPC requests sent to an SSE session.
    """
    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={"error": "Startup error", "traceback": _startup_error},
        )

    payload = await request.json()

    active_user = user
    if sessionId and sessionId in session_users:
        active_user = session_users[sessionId]

    if not active_user:
        active_user = UserContext(user_id=1, username="public_user", role="admin")

    response_payload = await process_jsonrpc_request(payload, active_user)

    if sessionId and sessionId in active_sessions and response_payload is not None:
        queue = active_sessions[sessionId]
        await queue.put(response_payload)

    if response_payload is not None:
        return JSONResponse(content=response_payload)
    return Response(status_code=status.HTTP_202_ACCEPTED)
