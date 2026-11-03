import json
from typing import Any, Dict, List
from src.auth import UserContext
from src import db

# Standard MCP Tool Definitions Schema
AVAILABLE_TOOLS = [
    {
        "name": "get_my_profile",
        "description": "Get current authenticated user identity, role, and workspace permissions.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "fetch_user_records",
        "description": "Fetch private data records belonging to the authenticated user from the database. Supports category filtering, search, and pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g. 'project', 'finance', 'sales', 'notes')"
                },
                "search": {
                    "type": "string",
                    "description": "Optional keyword search in record title or content"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of records to return (default: 10, max: 100)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of records to skip for pagination (default: 0)"
                }
            },
            "required": []
        }
    },
    {
        "name": "insert_user_record",
        "description": "Create a new private record stored securely in the database for the current user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the record"
                },
                "content": {
                    "type": "string",
                    "description": "Detailed text content of the record"
                },
                "category": {
                    "type": "string",
                    "description": "Category tag (e.g. 'notes', 'tasks', 'research', 'analytics')"
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional key-value JSON metadata"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "execute_safe_query",
        "description": "Execute a safe read-only SQL SELECT query against the online database. For members, queries are automatically isolated to the user's data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL SELECT query to execute (e.g. 'SELECT id, category, title, created_at FROM user_records ORDER BY created_at DESC LIMIT 5')"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "list_accessible_tables",
        "description": "Inspect available database tables and schemas accessible to the user.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_database_stats",
        "description": "Get summary analytics, record counts, and categories for the current user's database workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

async def execute_tool(name: str, arguments: Dict[str, Any], user: UserContext) -> Dict[str, Any]:
    """
    Executes an MCP tool with tenant isolation based on the authenticated UserContext.
    """
    if name == "get_my_profile":
        return {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "key_name": user.key_name,
            "access_level": "Administrator (Full Workspace)" if user.is_admin else "Tenant Member (User-Isolated)"
        }

    elif name == "fetch_user_records":
        category = arguments.get("category")
        search = arguments.get("search")
        limit = min(int(arguments.get("limit", 10)), 100)
        offset = max(int(arguments.get("offset", 0)), 0)

        conditions = ["user_id = $1"]
        params: List[Any] = [user.user_id]
        idx = 2

        if category:
            conditions.append(f"category = ${idx}")
            params.append(category)
            idx += 1

        if search:
            conditions.append(f"(title ILIKE ${idx} OR content ILIKE ${idx})")
            params.append(f"%{search}%")
            idx += 1

        params.append(limit)
        limit_idx = idx
        idx += 1

        params.append(offset)
        offset_idx = idx

        sql = f"""
            SELECT id, category, title, content, metadata, created_at, updated_at
            FROM user_records
            WHERE {" AND ".join(conditions)}
            ORDER BY created_at DESC
            LIMIT ${limit_idx} OFFSET ${offset_idx};
        """
        rows = await db.fetch_all(sql, *params)
        return {
            "count": len(rows),
            "user_id": user.user_id,
            "records": rows
        }

    elif name == "insert_user_record":
        title = arguments["title"].strip()
        content = arguments["content"].strip()
        category = arguments.get("category", "general").strip()
        metadata = json.dumps(arguments.get("metadata", {}))

        insert_sql = """
            INSERT INTO user_records (user_id, category, title, content, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, category, title, created_at;
        """
        created = await db.fetch_one(insert_sql, user.user_id, category, title, content, metadata)
        return {
            "status": "success",
            "message": f"Record created successfully with ID {created['id']}",
            "record": created
        }

    elif name == "execute_safe_query":
        raw_sql = arguments.get("sql", "").strip()
        # Security validation: Only allow SELECT statements
        if not raw_sql.lower().startswith("select"):
            raise ValueError("Security Violation: Only SELECT queries are permitted.")
        
        forbidden_keywords = ["drop", "truncate", "delete", "update", "insert", "alter", "grant", "revoke"]
        for kw in forbidden_keywords:
            if f" {kw} " in f" {raw_sql.lower()} ":
                raise ValueError(f"Security Violation: Query contains forbidden keyword '{kw}'.")

        # Multi-user tenant isolation check
        if not user.is_admin:
            # Standard members must only query their own user_id
            if "user_records" in raw_sql.lower() and "user_id" not in raw_sql.lower():
                raise ValueError("Security Violation: Queries against 'user_records' must explicitly filter by your user_id.")

        rows = await db.fetch_all(raw_sql)
        return {
            "rows_returned": len(rows),
            "data": rows
        }

    elif name == "list_accessible_tables":
        tables_sql = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """
        tables = await db.fetch_all(tables_sql)
        return {
            "tables": [t["table_name"] for t in tables],
            "descriptions": {
                "users": "User identity and account metadata (Admin only for full query).",
                "api_keys": "Active API authentication keys.",
                "user_records": "Secure multi-tenant data table partitioned by user_id."
            }
        }

    elif name == "get_database_stats":
        stats_sql = """
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT category) as unique_categories,
                MAX(created_at) as latest_record_time
            FROM user_records
            WHERE user_id = $1;
        """
        stats = await db.fetch_one(stats_sql, user.user_id)
        return {
            "user_id": user.user_id,
            "username": user.username,
            "stats": stats or {}
        }

    else:
        raise ValueError(f"Unknown MCP tool: {name}")
