import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, Optional
from src.auth import UserContext
from src.tools import AVAILABLE_TOOLS, execute_tool
from src import db

logger = logging.getLogger("mcp-server")

MCP_PROTOCOL_VERSION = "2024-11-05"

# Active SSE sessions (Session ID -> asyncio.Queue)
active_sessions: Dict[str, asyncio.Queue] = {}
session_users: Dict[str, UserContext] = {}

async def process_jsonrpc_request(request: Dict[str, Any], user: UserContext) -> Optional[Dict[str, Any]]:
    """
    Core MCP JSON-RPC 2.0 message processor.
    Handles 'initialize', 'tools/list', 'tools/call', 'resources/list', 'resources/read', 'ping'.
    """
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {}) or {}

    # Notifications don't have an ID and expect no response
    if not req_id and method and method.startswith("notifications/"):
        logger.info(f"Received notification: {method}")
        return None

    def make_response(result: Any = None, error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            resp["error"] = error
        else:
            resp["result"] = result if result is not None else {}
        return resp

    try:
        if method == "initialize":
            return make_response({
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "serverInfo": {
                    "name": "multi-user-postgres-mcp",
                    "version": "1.0.0"
                },
                "instructions": (
                    f"Connected as {user.username} (Role: {user.role}). "
                    "You have private access to query and manage your isolated database records."
                )
            })

        elif method == "ping":
            return make_response({})

        elif method == "tools/list":
            return make_response({"tools": AVAILABLE_TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {}) or {}
            
            if not tool_name:
                return make_response(error={"code": -32602, "message": "Missing 'name' in tools/call parameters"})

            try:
                result_data = await execute_tool(tool_name, arguments, user)
                return make_response({
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result_data, indent=2)
                        }
                    ],
                    "isError": False
                })
            except Exception as tool_err:
                logger.error(f"Error executing tool {tool_name}: {tool_err}")
                return make_response({
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: {str(tool_err)}"
                        }
                    ],
                    "isError": True
                })

        elif method == "resources/list":
            return make_response({
                "resources": [
                    {
                        "uri": f"postgres://user/{user.user_id}/records",
                        "name": f"{user.username}'s Database Records",
                        "description": "Live private records for the authenticated user",
                        "mimeType": "application/json"
                    }
                ]
            })

        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri == f"postgres://user/{user.user_id}/records":
                records = await db.fetch_all(
                    "SELECT id, category, title, content, metadata, created_at FROM user_records WHERE user_id = $1 LIMIT 50",
                    user.user_id
                )
                return make_response({
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(records, indent=2)
                        }
                    ]
                })
            else:
                return make_response(error={"code": -32602, "message": f"Resource not found or unauthorized: {uri}"})

        else:
            return make_response(error={"code": -32601, "message": f"Method not found: {method}"})

    except Exception as e:
        logger.error(f"Internal error processing method {method}: {e}")
        return make_response(error={"code": -32603, "message": f"Internal server error: {str(e)}"})

async def sse_event_stream(session_id: str, user: UserContext, request_url_prefix: str) -> AsyncGenerator[str, None]:
    """
    SSE generator yielding the standard MCP endpoint event followed by messages & keep-alives.
    """
    queue: asyncio.Queue = asyncio.Queue()
    active_sessions[session_id] = queue
    session_users[session_id] = user

    try:
        # Step 1: Send endpoint event telling the client where to POST messages
        # Include session_id in the target URI
        endpoint_url = f"{request_url_prefix}/messages?sessionId={session_id}"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"

        # Step 2: Stream loop
        while True:
            try:
                # Wait for queued messages or send a keepalive ping every 10 seconds
                msg = await asyncio.wait_for(queue.get(), timeout=10.0)
                yield f"event: message\ndata: {json.dumps(msg)}\n\n"
            except asyncio.TimeoutError:
                # Keep-alive comment to keep connection alive in serverless/proxies
                yield ": keep-alive\n\n"
    except asyncio.CancelledError:
        logger.info(f"SSE client {session_id} disconnected.")
    finally:
        active_sessions.pop(session_id, None)
        session_users.pop(session_id, None)
