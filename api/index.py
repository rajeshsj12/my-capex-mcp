import logging
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

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


@app.get("/")
async def root():
    """Server info and diagnostic status."""
    db_status = await db.check_connection()
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
async def health():
    """Health check endpoint for uptime monitoring."""
    db_status = await db.check_connection()
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
async def handle_sse(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    """
    Server-Sent Events connection endpoint.
    Publicly accessible.
    """
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
async def handle_messages(
    request: Request,
    sessionId: str | None = None,
    user: UserContext | None = Depends(get_current_user),
):
    """
    Receives JSON-RPC requests sent to an SSE session.
    """
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
