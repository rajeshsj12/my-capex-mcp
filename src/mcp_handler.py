import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.auth import UserContext
from src.tools import AVAILABLE_TOOLS, execute_tool

logger = logging.getLogger("mcp-server")

MCP_PROTOCOL_VERSION = "2024-11-05"

active_sessions: dict[str, asyncio.Queue] = {}
session_users: dict[str, UserContext] = {}

SERVER_INSTRUCTIONS = """You are connected to an enterprise analytics Model Context Protocol (MCP) server.
Databases available:
1. `capex`: Financial ledger (2.18M+ transactions), capital asset management (50,000 assets), Chart of Accounts (COA), and fiscal calendar.
   - Join fact_financial_ledger to dim_asset using Asset_Key.
   - Join fact_financial_ledger to dim_coa using Account_Code = AccountCode.
   - Join fact_financial_ledger to dim_calendar using Date_Key.
   - Key metrics: Cost (USD), IoT_Hours (machine run hours), Carbon_Emissions_MT (sustainability metric), Useful_Life_Yrs.
2. `world`: Global geography with countries, cities, and spoken languages.
3. `sakila`: Commercial business operations (rentals, films, payments, customers).

You have rich analytical tools available:
- `get_consolidated_summary`: High-level asset valuation, ledger totals, and category breakdowns.
- `get_executive_kpis`: Sustainability ESG metrics (carbon intensity), top 10 assets, and depreciation.
- `ask_database_question`: Immediate answers to specific domain questions.
- `search_database_knowledge`: Universal search across all entities.
- `query_database`: Custom read-only SQL queries (SELECT, SHOW, DESCRIBE, WITH CTEs).
- `get_data_dictionary`: Detailed schema reference with keys and column definitions.
Use these tools to answer any business, technical, operational, or exploratory question raised by the user!"""


async def process_jsonrpc_request(
    request: dict[str, Any], user: UserContext
) -> dict[str, Any] | None:
    """
    Core MCP JSON-RPC 2.0 message processor.
    Handles 'initialize', 'tools/list', 'tools/call', 'resources/list', 'resources/read', 'ping'.
    """
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {}) or {}

    if not req_id and method and method.startswith("notifications/"):
        logger.info(f"Notification received: {method}")
        return None

    def make_response(result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
        resp: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            resp["error"] = error
        else:
            resp["result"] = result if result is not None else {}
        return resp

    try:
        if method == "initialize":
            return make_response(
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {
                        "name": "enterprise-capex-mysql-mcp",
                        "version": "2.0.0",
                    },
                    "instructions": SERVER_INSTRUCTIONS,
                }
            )

        elif method == "ping":
            return make_response({})

        elif method == "tools/list":
            return make_response({"tools": AVAILABLE_TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {}) or {}

            if not tool_name:
                return make_response(
                    error={
                        "code": -32602,
                        "message": "Missing 'name' in tools/call parameters",
                    }
                )

            try:
                result_data = await execute_tool(tool_name, arguments, user)
                return make_response(
                    {
                        "content": [{"type": "text", "text": json.dumps(result_data, indent=2)}],
                        "isError": False,
                    }
                )
            except Exception as tool_err:
                logger.error(f"Error executing tool {tool_name}: {tool_err}")
                return make_response(
                    {
                        "content": [{"type": "text", "text": f"Error: {tool_err!s}"}],
                        "isError": True,
                    }
                )

        elif method == "resources/list":
            return make_response(
                {
                    "resources": [
                        {
                            "uri": "capex://data_dictionary",
                            "name": "CapEx Database Schema & Relationships Dictionary",
                            "description": "Complete reference of tables, primary/foreign keys, and metric definitions",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "capex://consolidated_summary",
                            "name": "Consolidated Executive Summary",
                            "description": "Portfolio valuation, total ledger transactions, carbon emissions, and financing sources",
                            "mimeType": "application/json",
                        },
                    ]
                }
            )

        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri == "capex://data_dictionary":
                data = await execute_tool("get_data_dictionary", {"database": "capex"}, user)
                return make_response(
                    {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(data, indent=2),
                            }
                        ]
                    }
                )
            elif uri == "capex://consolidated_summary":
                data = await execute_tool("get_consolidated_summary", {"database": "capex"}, user)
                return make_response(
                    {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(data, indent=2),
                            }
                        ]
                    }
                )
            else:
                return make_response(
                    error={"code": -32602, "message": f"Resource not found: {uri}"}
                )

        else:
            return make_response(error={"code": -32601, "message": f"Method not found: {method}"})

    except Exception as e:
        logger.error(f"Internal error processing method {method}: {e}")
        return make_response(error={"code": -32603, "message": f"Internal server error: {e!s}"})


async def sse_event_stream(
    session_id: str, user: UserContext, request_url_prefix: str
) -> AsyncGenerator[str, None]:
    """
    SSE generator yielding standard MCP endpoint event followed by messages & keep-alives.
    """
    queue: asyncio.Queue = asyncio.Queue()
    active_sessions[session_id] = queue
    session_users[session_id] = user

    try:
        endpoint_url = f"{request_url_prefix}/messages?sessionId={session_id}"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"

        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=10.0)
                yield f"event: message\ndata: {json.dumps(msg)}\n\n"
            except TimeoutError:
                yield ": keep-alive\n\n"
    except asyncio.CancelledError:
        logger.info(f"SSE client {session_id} disconnected.")
    finally:
        active_sessions.pop(session_id, None)
        session_users.pop(session_id, None)
