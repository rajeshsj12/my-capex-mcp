import re
from typing import Any, Dict, List
from src.auth import UserContext
from src import db

# Standard Model Context Protocol (MCP) Tools Schema
AVAILABLE_TOOLS = [
    {
        "name": "get_my_profile",
        "description": "Get current authenticated user identity, assigned role, and accessible database scopes.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_databases",
        "description": "List all online MySQL databases accessible to the current user (e.g. capex, world, sakila).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_tables",
        "description": "List all tables within a specified database (defaults to 'capex').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name (e.g. 'capex', 'world', 'sakila'). Defaults to 'capex'."
                }
            },
            "required": []
        }
    },
    {
        "name": "describe_table",
        "description": "Inspect column names, data types, keys, and nullability for a specific table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table (e.g. 'dim_asset', 'fact_financial_ledger', 'dim_coa')"
                },
                "database": {
                    "type": "string",
                    "description": "Database containing the table. Defaults to 'capex'."
                }
            },
            "required": ["table_name"]
        }
    },
    {
        "name": "fetch_table_records",
        "description": "Fetch records from a database table with filtering, ordering, and pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to query (e.g. 'dim_asset', 'dim_coa', 'country')"
                },
                "database": {
                    "type": "string",
                    "description": "Target database. Defaults to 'capex'."
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default: 20, max: 200)"
                },
                "offset": {
                    "type": "integer",
                    "description": "Rows to skip for pagination (default: 0)"
                },
                "order_by": {
                    "type": "string",
                    "description": "Column name to order results by (optional)"
                }
            },
            "required": ["table_name"]
        }
    },
    {
        "name": "query_database",
        "description": "Execute a safe read-only SQL SELECT query against the online MySQL database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL SELECT query to execute (e.g. 'SELECT Asset_Class, COUNT(*), SUM(Cost) FROM capex.dim_asset GROUP BY Asset_Class;')"
                },
                "database": {
                    "type": "string",
                    "description": "Optional default database context to use (e.g. 'capex')"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "get_database_summary",
        "description": "Get a high-level summary of table row counts and schema statistics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database to summarize. Defaults to 'capex'."
                }
            },
            "required": []
        }
    }
]

def _check_db_access(user: UserContext, target_db: str):
    """Enforces multi-user access control per database."""
    if user.is_admin:
        return
    if user.allowed_databases and target_db.lower() not in [d.lower() for d in user.allowed_databases]:
        raise PermissionError(
            f"Access Denied: User '{user.username}' is not permitted to access database '{target_db}'. "
            f"Allowed databases: {user.allowed_databases}"
        )

async def execute_tool(name: str, arguments: Dict[str, Any], user: UserContext) -> Dict[str, Any]:
    """
    Executes an MCP tool with tenant isolation and security checks.
    """
    if name == "get_my_profile":
        return {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "key_name": user.key_name,
            "allowed_databases": user.allowed_databases or ["*"],
            "access_level": "Full Admin Access" if user.is_admin else "Scoped Analyst Access"
        }

    elif name == "list_databases":
        rows = await db.fetch_all("SHOW DATABASES;")
        all_dbs = [r[list(r.keys())[0]] for r in rows if r[list(r.keys())[0]] not in ("information_schema", "performance_schema", "sys", "mysql")]
        if user.is_admin:
            accessible = all_dbs
        else:
            accessible = [d for d in all_dbs if d.lower() in [x.lower() for x in (user.allowed_databases or [])]]
        return {
            "accessible_databases": accessible,
            "user": user.username
        }

    elif name == "list_tables":
        target_db = arguments.get("database", "capex").strip()
        _check_db_access(user, target_db)
        # Use backticks to prevent injection
        safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
        rows = await db.fetch_all(f"SHOW TABLES FROM `{safe_db}`;")
        tables = [list(r.values())[0] for r in rows]
        return {
            "database": safe_db,
            "table_count": len(tables),
            "tables": tables
        }

    elif name == "describe_table":
        table = arguments["table_name"].strip()
        target_db = arguments.get("database", "capex").strip()
        _check_db_access(user, target_db)
        safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
        safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table)

        columns = await db.fetch_all(f"DESCRIBE `{safe_db}`.`{safe_table}`;")
        return {
            "database": safe_db,
            "table": safe_table,
            "column_count": len(columns),
            "columns": columns
        }

    elif name == "fetch_table_records":
        table = arguments["table_name"].strip()
        target_db = arguments.get("database", "capex").strip()
        _check_db_access(user, target_db)

        limit = min(max(int(arguments.get("limit", 20)), 1), 200)
        offset = max(int(arguments.get("offset", 0)), 0)
        order_by = arguments.get("order_by")

        safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
        safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table)

        query = f"SELECT * FROM `{safe_db}`.`{safe_table}`"
        if order_by:
            safe_order = re.sub(r"[^a-zA-Z0-9_]", "", order_by)
            query += f" ORDER BY `{safe_order}`"
        query += f" LIMIT {limit} OFFSET {offset};"

        records = await db.fetch_all(query)
        return {
            "database": safe_db,
            "table": safe_table,
            "returned_rows": len(records),
            "offset": offset,
            "limit": limit,
            "records": records
        }

    elif name == "query_database":
        raw_sql = arguments.get("sql", "").strip()
        target_db = arguments.get("database")
        
        # Enforce Read-Only SELECT queries
        clean_sql = raw_sql.strip()
        if not clean_sql.lower().startswith("select") and not clean_sql.lower().startswith("show") and not clean_sql.lower().startswith("explain"):
            raise ValueError("Security Policy: Only SELECT, SHOW, and EXPLAIN queries are permitted.")

        forbidden = ["insert", "update", "delete", "drop", "truncate", "alter", "create", "grant", "revoke", "lock", "flush"]
        # Match standalone forbidden SQL keywords
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", clean_sql, re.IGNORECASE):
                raise ValueError(f"Security Policy: Query contains forbidden statement '{kw.upper()}'.")

        # Check database scope permissions for analysts
        if not user.is_admin and user.allowed_databases:
            for match in re.finditer(r"`?([a-zA-Z0-9_]+)`?\.", clean_sql):
                db_prefix = match.group(1).lower()
                if db_prefix not in [d.lower() for d in user.allowed_databases]:
                    raise PermissionError(f"Access Denied: You do not have permission to query database '{db_prefix}'.")

        if target_db:
            _check_db_access(user, target_db)
            safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
            await db.execute(f"USE `{safe_db}`;")

        # Automatically append limit if missing to protect server memory
        if "limit" not in clean_sql.lower() and clean_sql.lower().startswith("select"):
            clean_sql = clean_sql.rstrip(";") + " LIMIT 100;"

        rows = await db.fetch_all(clean_sql)
        return {
            "query": clean_sql,
            "rows_returned": len(rows),
            "data": rows
        }

    elif name == "get_database_summary":
        target_db = arguments.get("database", "capex").strip()
        _check_db_access(user, target_db)
        safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)

        summary_sql = f"""
            SELECT 
                table_name AS `Table`, 
                table_rows AS `Approx_Rows`,
                ROUND((data_length + index_length) / 1024 / 1024, 2) AS `Size_MB`
            FROM information_schema.tables 
            WHERE table_schema = '{safe_db}'
            ORDER BY table_rows DESC;
        """
        tables_info = await db.fetch_all(summary_sql)
        return {
            "database": safe_db,
            "tables": tables_info
        }

    else:
        raise ValueError(f"Unknown MCP tool: {name}")
