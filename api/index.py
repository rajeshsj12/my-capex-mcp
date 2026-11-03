import uuid
import logging
from typing import Any, Dict, List, Union
from fastapi import FastAPI, Depends, Request, Response, HTTPException, Query, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.auth import UserContext, get_current_user, resolve_user
from src.mcp_handler import (
    process_jsonrpc_request,
    sse_event_stream,
    active_sessions,
    session_users,
    MCP_PROTOCOL_VERSION
)
from src import db

# Configure logging
logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("mcp-server")

app = FastAPI(
    title="Multi-User Postgres MCP Server",
    description="Production-ready Model Context Protocol Server with private multi-tenant database access on Vercel.",
    version="1.0.0"
)

# Enable CORS for browser-based AI agents and web clients
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
        "name": "Multi-User Postgres MCP Server",
        "status": "online",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "endpoints": {
            "stateless_mcp": "POST /mcp",
            "sse_transport": "GET /sse",
            "messages": "POST /messages?sessionId={id}",
            "health": "GET /health"
        },
        "auth": {
            "type": "Bearer Token / X-API-Key / Query Parameter",
            "access": "Private Access Only"
        }
    }

@app.get("/health")
async def health():
    """Health check endpoint for uptime monitoring."""
    db_status = await db.check_connection()
    return {
        "status": "healthy" if db_status.get("connected") else "degraded",
        "database": db_status
    }

# -----------------------------------------------------------------------------
# 1. Stateless HTTP JSON-RPC MCP Endpoint (Ideal for Serverless / Vercel)
# -----------------------------------------------------------------------------
@app.post("/mcp")
@app.post("/api/mcp")
async def handle_stateless_mcp(
    request: Union[Dict[str, Any], List[Dict[str, Any]]],
    user: UserContext = Depends(get_current_user)
):
    """
    Direct JSON-RPC 2.0 endpoint for MCP.
    Stateless, immune to Lambda cold-start session drops, fully isolated per user.
    """
    if isinstance(request, list):
        # Handle batch requests
        results = []
        for req in request:
            res = await process_jsonrpc_request(req, user)
            if res is not None:
                results.append(res)
        return results
    else:
        # Single request
        res = await process_jsonrpc_request(request, user)
        if res is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return res

# -----------------------------------------------------------------------------
# 2. SSE Transport Endpoints (Compatible with standard MCP SSE clients)
# -----------------------------------------------------------------------------
@app.get("/sse")
async def handle_sse(
    request: Request,
    user: UserContext = Depends(get_current_user)
):
    """
    Server-Sent Events connection endpoint.
    Emits an initial 'endpoint' event with the target /messages URL,
    then streams JSON-RPC responses.
    """
    session_id = str(uuid.uuid4())
    logger.info(f"Opening SSE session {session_id} for user '{user.username}' (id: {user.user_id})")

    # Base URL prefix (e.g. https://your-domain.vercel.app)
    base_url = str(request.base_url).rstrip("/")

    return StreamingResponse(
        sse_event_stream(session_id, user, base_url),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/messages")
async def handle_messages(
    request: Request,
    sessionId: Optional[str] = Query(None),
    user: Optional[UserContext] = Depends(get_current_user)
):
    """
    Receives JSON-RPC requests sent to an active SSE session.
    Routes response to the SSE stream and also returns it in HTTP body.
    """
    payload = await request.json()

    # Determine user identity from either the session or direct auth
    active_user = user
    if sessionId and sessionId in session_users:
        active_user = session_users[sessionId]

    if not active_user:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Valid authentication credentials required."
        )

    response_payload = await process_jsonrpc_request(payload, active_user)

    # Deliver to SSE queue if active
    if sessionId and sessionId in active_sessions and response_payload is not None:
        queue = active_sessions[sessionId]
        await queue.put(response_payload)

    # Also return HTTP 200 with payload for serverless resilience
    if response_payload is not None:
        return JSONResponse(content=response_payload)
    return Response(status_code=status.HTTP_202_ACCEPTED)
