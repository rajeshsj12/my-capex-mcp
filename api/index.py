from __future__ import annotations

import json
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

# Enable CORS for all clients (Claude Desktop, Cursor, Web Agents, OpenAI, Copilot)
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
    logging.getLogger("mcp-server").error(
        f"Global unhandled error on {request.url.path}: {err_trace}"
    )
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


async def _extract_json_body(request: Request) -> Any:
    """Safely extract JSON body if present, or return None."""
    try:
        body_bytes = await request.body()
        if not body_bytes or not body_bytes.strip():
            return None
        return json.loads(body_bytes)
    except Exception:
        return None


@app.api_route("/", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/index", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/index.py", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def root(request: Request, user: UserContext = Depends(get_current_user)):
    """
    Root endpoint supporting GET, POST, HEAD, and OPTIONS.
    Handles discovery metadata, connector validation, and direct JSON-RPC MCP calls.
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Allow": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Startup initialization failed",
                "traceback": _startup_error,
            },
        )

    # Check if client sent an MCP JSON-RPC call directly to root /
    if request.method == "POST":
        body = await _extract_json_body(request)
        if isinstance(body, dict) and "jsonrpc" in body:
            res = await process_jsonrpc_request(body, user)
            if res is None:
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            return res
        elif (
            isinstance(body, list)
            and len(body) > 0
            and isinstance(body[0], dict)
            and "jsonrpc" in body[0]
        ):
            results = []
            for req in body:
                r = await process_jsonrpc_request(req, user)
                if r is not None:
                    results.append(r)
            return results

    # Return metadata for GET, HEAD, or non-JSON-RPC POST
    try:
        db_status = await db.check_connection()
    except Exception as e:
        db_status = {"connected": False, "error": str(e)}

    return {
        "name": "Enterprise MySQL Analytics MCP Server",
        "public_url": get_public_url(),
        "status": "online",
        "access": "Public (No authentication required)",
        "auth": "none",
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


@app.api_route("/health", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/health", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def health(request: Request):
    """Health check endpoint for uptime monitoring."""
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Allow": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

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


@app.api_route("/mcp", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/mcp", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def handle_stateless_mcp(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    """
    Stateless HTTP JSON-RPC 2.0 MCP endpoint.
    Accepts POST for JSON-RPC 2.0 requests.
    Accepts GET, HEAD, and OPTIONS for connector status checks and capability discovery (prevents 405 errors).
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Allow": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={"error": "Startup error", "traceback": _startup_error},
        )

    if request.method == "POST":
        body = await _extract_json_body(request)
        if isinstance(body, list):
            results = []
            for req in body:
                res = await process_jsonrpc_request(req, user)
                if res is not None:
                    results.append(res)
            return results
        elif isinstance(body, dict) and "jsonrpc" in body:
            res = await process_jsonrpc_request(body, user)
            if res is None:
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            return res

    # GET, HEAD, or non-JSON-RPC POST: Return MCP endpoint discovery info
    return {
        "name": "Enterprise MySQL Analytics MCP Server",
        "status": "online",
        "endpoint": "/mcp",
        "transport": "HTTP POST (JSON-RPC 2.0)",
        "access": "Public (No authentication required)",
        "auth": "none",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "methods": ["GET", "POST", "HEAD", "OPTIONS"],
    }


@app.api_route("/sse", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/sse", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def handle_sse(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    """
    Server-Sent Events connection endpoint.
    Also handles HTTP JSON-RPC POST requests for streamable HTTP transports like mcp-remote.
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Allow": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={"error": "Startup error", "traceback": _startup_error},
        )

    # Support Streamable HTTP / JSON-RPC fallback
    if request.method == "POST":
        body = await _extract_json_body(request)
        if isinstance(body, dict) and "jsonrpc" in body:
            res = await process_jsonrpc_request(body, user)
            if res is None:
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            return res
        elif isinstance(body, list) and len(body) > 0:
            results = []
            for req in body:
                r = await process_jsonrpc_request(req, user)
                if r is not None:
                    results.append(r)
            return results

    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
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


@app.api_route("/messages", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/api/messages", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def handle_messages(
    request: Request,
    sessionId: str | None = None,
    user: UserContext | None = Depends(get_current_user),
):
    """
    Receives JSON-RPC requests sent to an SSE session.
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Allow": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    if _startup_error is not None:
        return JSONResponse(
            status_code=500,
            content={"error": "Startup error", "traceback": _startup_error},
        )

    if request.method != "POST":
        return {
            "status": "online",
            "endpoint": "/messages",
            "transport": "HTTP POST",
            "access": "Public (No authentication required)",
            "auth": "none",
        }

    payload = await _extract_json_body(request) or {}

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


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"],
)
async def catch_all_fallback(
    request: Request, user: UserContext = Depends(get_current_user)
):
    """
    Fallback route to ensure no method or path returns 405 or 404 when probed by automated connectors.
    """
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Allow": "*",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            },
        )

    if request.method == "POST":
        body = await _extract_json_body(request)
        if isinstance(body, dict) and "jsonrpc" in body:
            res = await process_jsonrpc_request(body, user)
            if res is None:
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            return res
        elif isinstance(body, list) and len(body) > 0:
            results = []
            for req in body:
                r = await process_jsonrpc_request(req, user)
                if r is not None:
                    results.append(r)
            return results

    return JSONResponse(
        status_code=200,
        content={
            "name": "Enterprise MySQL Analytics MCP Server",
            "status": "online",
            "path": str(request.url.path),
            "method": request.method,
            "access": "Public (No authentication required)",
            "auth": "none",
            "endpoints": {
                "root": "/",
                "stateless_mcp": "/mcp",
                "sse_transport": "/sse",
                "health": "/health",
            },
        },
    )
