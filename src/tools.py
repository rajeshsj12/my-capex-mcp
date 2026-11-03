import re
from typing import Any

from src import db
from src.auth import UserContext

# Complete Model Context Protocol (MCP) Tools Catalog
AVAILABLE_TOOLS = [
    {
        "name": "get_consolidated_summary",
        "description": (
            "Get an executive consolidated summary of the entire database. "
            "Includes total asset valuation, capitalized vs non-capitalized assets, "
            "total ledger transaction counts (over 2.1M rows), cumulative IoT run hours, "
            "carbon emissions (MT), asset class breakdowns, and financing sources."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database to summarize (defaults to 'capex').",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_executive_kpis",
        "description": (
            "Calculates executive KPIs across CapEx investments, ESG sustainability "
            "(carbon emissions by asset class and carbon intensity), operational machine "
            "running hours, depreciation estimates, and the top 10 most expensive capital assets."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ask_database_question",
        "description": (
            "Specialized assistant to answer specific analytical questions about the data. "
            "Choose a topic category ('financial_performance', 'asset_portfolio', "
            "'sustainability_carbon', 'iot_operations', 'global_geography', 'commercial_sakila') "
            "or ask any specific question."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": [
                        "financial_performance",
                        "asset_portfolio",
                        "sustainability_carbon",
                        "iot_operations",
                        "global_geography",
                        "commercial_sakila",
                    ],
                    "description": "The category of analysis to generate answers for.",
                },
                "question": {
                    "type": "string",
                    "description": "Specific question you want answered (e.g. 'What is our total carbon footprint in MT?', 'Top 5 countries by population?')",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "search_database_knowledge",
        "description": (
            "Universal search across tables (assets, chart of accounts, countries, films) "
            "for any keyword, asset ID, country name, account code, or asset class."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword or code (e.g. 'Robot', 'Equity', 'AST-000001', 'Cash', 'Brazil')",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_data_dictionary",
        "description": (
            "Returns a complete data dictionary and entity-relationship guide for capex, world, "
            "and sakila. Explains primary/foreign keys (e.g. Asset_Key, Account_Code, Date_Key), "
            "dimensions, fact metrics, and how to write precise SQL joins."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name (defaults to 'capex').",
                }
            },
            "required": [],
        },
    },
    {
        "name": "query_database",
        "description": (
            "Execute any custom read-only SQL query against the MySQL database. "
            "Supports SELECT, SHOW, DESCRIBE, EXPLAIN, CTEs, and JOINs between fact and dimension tables."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query to execute (e.g. 'SELECT Asset_Class, COUNT(*), SUM(Cost) FROM capex.dim_asset GROUP BY Asset_Class;')",
                },
                "database": {
                    "type": "string",
                    "description": "Optional default database context (e.g. 'capex', 'world', 'sakila').",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "fetch_table_records",
        "description": "Fetch rows from any table with pagination, ordering, and optional WHERE filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Table name (e.g. 'dim_asset', 'dim_coa', 'country', 'city')",
                },
                "database": {
                    "type": "string",
                    "description": "Target database (defaults to 'capex').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default: 20, max: 200).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset (default: 0).",
                },
                "order_by": {
                    "type": "string",
                    "description": "Column name to order results by (optional).",
                },
                "where_clause": {
                    "type": "string",
                    "description": "Optional SQL condition without WHERE (e.g. 'Cost > 50000' or 'Is_Capitalized = 1').",
                },
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "list_databases",
        "description": "List all accessible databases on the MySQL server.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_tables",
        "description": "List all tables within a specified database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name (defaults to 'capex').",
                }
            },
            "required": [],
        },
    },
]


async def execute_tool(name: str, arguments: dict[str, Any], user: UserContext) -> dict[str, Any]:
    """
    Executes an analytical MCP tool and returns consolidated results.
    """
    if name == "get_consolidated_summary":
        target_db = arguments.get("database", "capex").strip().lower()

        if target_db == "capex":
            # 1. Total Assets & CapEx Valuation
            asset_stats_sql = """
                SELECT 
                    COUNT(*) AS total_assets,
                    SUM(Cost) AS total_asset_valuation_usd,
                    AVG(Cost) AS avg_asset_cost_usd,
                    SUM(CASE WHEN Is_Capitalized = 1 THEN 1 ELSE 0 END) AS capitalized_assets_count,
                    SUM(CASE WHEN Is_Capitalized = 0 THEN 1 ELSE 0 END) AS uncapitalized_assets_count,
                    SUM(CASE WHEN Is_Disposed = 1 THEN 1 ELSE 0 END) AS disposed_assets_count
                FROM capex.dim_asset;
            """
            asset_stats = await db.fetch_one(asset_stats_sql)

            # 2. Financial Ledger Metrics (Over 2.18M rows)
            ledger_stats_sql = """
                SELECT 
                    COUNT(*) AS total_ledger_transactions,
                    ROUND(SUM(Amount), 2) AS net_ledger_balance,
                    ROUND(SUM(IoT_Hours), 2) AS cumulative_iot_hours,
                    ROUND(SUM(Carbon_Emissions_MT), 3) AS cumulative_carbon_emissions_mt
                FROM capex.fact_financial_ledger;
            """
            ledger_stats = await db.fetch_one(ledger_stats_sql)

            # 3. Asset Class Distribution
            class_stats_sql = """
                SELECT 
                    Asset_Class,
                    COUNT(*) AS asset_count,
                    ROUND(SUM(Cost), 2) AS total_cost_usd,
                    ROUND(AVG(Cost), 2) AS avg_cost_usd,
                    ROUND(SUM(Planned_Run_Hours), 0) AS total_planned_hours
                FROM capex.dim_asset
                GROUP BY Asset_Class
                ORDER BY total_cost_usd DESC;
            """
            class_stats = await db.fetch_all(class_stats_sql)

            # 4. Financing Sources
            financing_sql = """
                SELECT 
                    Financing_Source,
                    COUNT(*) AS asset_count,
                    ROUND(SUM(Cost), 2) AS total_financing_usd,
                    ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM capex.dim_asset)), 2) AS percentage_of_assets
                FROM capex.dim_asset
                GROUP BY Financing_Source
                ORDER BY total_financing_usd DESC;
            """
            financing_stats = await db.fetch_all(financing_sql)

            # 5. Chart of Accounts (COA) Summary
            coa_sql = """
                SELECT 
                    AccountType,
                    COUNT(*) AS account_count,
                    GROUP_CONCAT(DISTINCT AccountSubType SEPARATOR ', ') AS sub_types
                FROM capex.dim_coa
                GROUP BY AccountType;
            """
            coa_stats = await db.fetch_all(coa_sql)

            return {
                "report_title": "Enterprise Consolidated Capital & Financial Summary",
                "database": "capex",
                "asset_portfolio_summary": asset_stats,
                "operational_ledger_summary": ledger_stats,
                "asset_class_breakdown": class_stats,
                "financing_sources_breakdown": financing_stats,
                "chart_of_accounts_distribution": coa_stats,
            }

        else:
            tables = await db.fetch_all(f"SHOW TABLES FROM `{target_db}`;")
            return {
                "database": target_db,
                "tables_count": len(tables),
                "tables": [next(iter(t.values())) for t in tables],
            }

    elif name == "get_executive_kpis":
        # 1. Top 10 Capital Investments
        top_assets_sql = """
            SELECT 
                Asset_ID,
                Asset_Class,
                Cost AS Cost_USD,
                Useful_Life_Yrs,
                Financing_Source,
                Purchase_Date
            FROM capex.dim_asset
            ORDER BY Cost DESC
            LIMIT 10;
        """
        top_assets = await db.fetch_all(top_assets_sql)

        # 2. Sustainability & ESG Metrics
        esg_sql = """
            SELECT 
                a.Asset_Class,
                ROUND(SUM(l.Carbon_Emissions_MT), 2) AS Total_Carbon_MT,
                ROUND(SUM(l.IoT_Hours), 2) AS Total_IoT_Hours,
                ROUND(SUM(l.Carbon_Emissions_MT) / NULLIF(SUM(l.IoT_Hours), 0), 4) AS Carbon_Intensity_per_Hour
            FROM capex.fact_financial_ledger l
            JOIN capex.dim_asset a ON l.Asset_Key = a.Asset_Key
            GROUP BY a.Asset_Class
            ORDER BY Total_Carbon_MT DESC;
        """
        esg_metrics = await db.fetch_all(esg_sql)

        # 3. Depreciation and Asset Longevity
        depr_sql = """
            SELECT 
                Asset_Class,
                ROUND(AVG(Useful_Life_Yrs), 1) AS Avg_Useful_Life_Yrs,
                ROUND(AVG(Tax_Depr_Rate) * 100, 2) AS Avg_Tax_Depr_Rate_Pct,
                ROUND(SUM(Cost * Tax_Depr_Rate), 2) AS Estimated_Annual_Tax_Depreciation
            FROM capex.dim_asset
            GROUP BY Asset_Class
            ORDER BY Estimated_Annual_Tax_Depreciation DESC;
        """
        depr_metrics = await db.fetch_all(depr_sql)

        return {
            "title": "Executive Financial, Operational & ESG Dashboard",
            "top_10_capital_assets": top_assets,
            "sustainability_carbon_intensity": esg_metrics,
            "depreciation_and_asset_lifecycle": depr_metrics,
        }

    elif name == "ask_database_question":
        topic = arguments.get("topic")
        question = arguments.get("question", "")

        if topic == "financial_performance":
            data = await db.fetch_all("""
                SELECT 
                    c.AccountType,
                    COUNT(l.Ledger_ID) AS Transaction_Count,
                    ROUND(SUM(l.Amount), 2) AS Total_Amount_USD
                FROM capex.fact_financial_ledger l
                JOIN capex.dim_coa c ON l.Account_Code = c.AccountCode
                GROUP BY c.AccountType
                ORDER BY Total_Amount_USD DESC;
            """)
            answer = "Financial ledger transactions categorized by Chart of Accounts type (Asset, Liability, Equity, Revenue, Expense)."

        elif topic == "sustainability_carbon":
            data = await db.fetch_all("""
                SELECT 
                    a.Asset_Class,
                    ROUND(SUM(l.Carbon_Emissions_MT), 2) AS Carbon_Footprint_MT,
                    ROUND(AVG(l.Carbon_Emissions_MT), 4) AS Avg_Emissions_per_Txn
                FROM capex.fact_financial_ledger l
                JOIN capex.dim_asset a ON l.Asset_Key = a.Asset_Key
                GROUP BY a.Asset_Class
                ORDER BY Carbon_Footprint_MT DESC;
            """)
            answer = "Carbon emissions aggregated across machine asset classes."

        elif topic == "iot_operations":
            data = await db.fetch_all("""
                SELECT 
                    a.Asset_Class,
                    ROUND(SUM(l.IoT_Hours), 2) AS Actual_IoT_Hours,
                    ROUND(SUM(a.Planned_Run_Hours), 2) AS Total_Planned_Hours
                FROM capex.fact_financial_ledger l
                JOIN capex.dim_asset a ON l.Asset_Key = a.Asset_Key
                GROUP BY a.Asset_Class
                ORDER BY Actual_IoT_Hours DESC;
            """)
            answer = (
                "Machine operational IoT running hours compared with initial planned run hours."
            )

        elif topic == "asset_portfolio":
            data = await db.fetch_all("""
                SELECT 
                    Asset_Class,
                    Financing_Source,
                    COUNT(*) AS Asset_Count,
                    ROUND(SUM(Cost), 2) AS Total_Cost
                FROM capex.dim_asset
                GROUP BY Asset_Class, Financing_Source
                ORDER BY Total_Cost DESC
                LIMIT 15;
            """)
            answer = "Asset portfolio cross-tabulation by Asset Class and Financing Source."

        elif topic == "global_geography":
            data = await db.fetch_all("""
                SELECT 
                    Continent,
                    COUNT(Code) AS Country_Count,
                    SUM(Population) AS Total_Population,
                    ROUND(AVG(LifeExpectancy), 1) AS Avg_Life_Expectancy,
                    ROUND(SUM(GNP), 2) AS Total_GNP
                FROM world.country
                GROUP BY Continent
                ORDER BY Total_Population DESC;
            """)
            answer = "Global population, economic output (GNP), and life expectancy by continent."

        elif topic == "commercial_sakila":
            data = await db.fetch_all("""
                SELECT 
                    c.name AS Category,
                    COUNT(r.rental_id) AS Total_Rentals,
                    ROUND(SUM(p.amount), 2) AS Total_Revenue
                FROM sakila.rental r
                JOIN sakila.payment p ON r.rental_id = p.rental_id
                JOIN sakila.inventory i ON r.inventory_id = i.inventory_id
                JOIN sakila.film_category fc ON i.film_id = fc.film_id
                JOIN sakila.category c ON fc.category_id = c.category_id
                GROUP BY c.name
                ORDER BY Total_Revenue DESC;
            """)
            answer = "Commercial entertainment rental revenues categorized by film genre."

        else:
            data = []
            answer = "Please select a valid topic or query the database directly."

        return {
            "topic": topic,
            "question_raised": question or f"Analysis for {topic}",
            "answer_summary": answer,
            "data": data,
        }

    elif name == "search_database_knowledge":
        query = arguments.get("query", "").strip()
        search_pattern = f"%{query}%"

        results = {}

        # 1. Search Assets
        assets = await db.fetch_all(
            """
            SELECT Asset_ID, Asset_Class, Cost, Purchase_Date, Financing_Source
            FROM capex.dim_asset
            WHERE Asset_ID LIKE %s OR Asset_Class LIKE %s OR Financing_Source LIKE %s
            LIMIT 5;
        """,
            (search_pattern, search_pattern, search_pattern),
        )
        if assets:
            results["matching_assets"] = assets

        # 2. Search Chart of Accounts
        coa = await db.fetch_all(
            """
            SELECT AccountCode, AccountName, AccountType, AccountSubType
            FROM capex.dim_coa
            WHERE AccountName LIKE %s OR AccountType LIKE %s OR AccountSubType LIKE %s
            LIMIT 5;
        """,
            (search_pattern, search_pattern, search_pattern),
        )
        if coa:
            results["matching_accounts"] = coa

        # 3. Search World Countries
        countries = await db.fetch_all(
            """
            SELECT Code, Name, Continent, Region, Population, HeadOfState
            FROM world.country
            WHERE Name LIKE %s OR Continent LIKE %s OR Code LIKE %s
            LIMIT 5;
        """,
            (search_pattern, search_pattern, search_pattern),
        )
        if countries:
            results["matching_countries"] = countries

        return {
            "query": query,
            "total_categories_matched": len(results),
            "results": results,
        }

    elif name == "get_data_dictionary":
        target_db = arguments.get("database", "capex").strip().lower()

        if target_db == "capex":
            return {
                "database": "capex",
                "description": "Enterprise Capital Expenditure (CapEx), Asset Management, and Financial Ledger Warehouse.",
                "relationships": [
                    "fact_financial_ledger.Asset_Key -> dim_asset.Asset_Key",
                    "fact_financial_ledger.Account_Code -> dim_coa.AccountCode",
                    "fact_financial_ledger.Date_Key -> dim_calendar.Date_Key",
                ],
                "tables": {
                    "dim_asset": {
                        "purpose": "Stores capital asset master records (50,000 rows).",
                        "primary_key": "Asset_Key",
                        "key_columns": {
                            "Asset_Key": "Unique integer identifier",
                            "Asset_ID": "Business code (e.g. AST-000001)",
                            "Asset_Class": "Category (6-Axis Robot, AGV Fleet, CNC Machining, etc.)",
                            "Cost": "Purchase / construction cost in USD",
                            "Salvage_Value": "Expected value at end of useful life",
                            "Useful_Life_Yrs": "Depreciation duration in years",
                            "Is_Capitalized": "1 if capitalized on balance sheet, 0 if expensed",
                            "Purchase_Date": "Acquisition date",
                            "Planned_Run_Hours": "Estimated machine hours over lifetime",
                            "Tax_Depr_Rate": "Tax depreciation percentage",
                            "Financing_Source": "Equity Issuance, Debt, Capital Lease, etc.",
                        },
                    },
                    "fact_financial_ledger": {
                        "purpose": "Double-entry operational and financial ledger transactions (2,189,640 rows).",
                        "primary_key": "Ledger_ID",
                        "key_columns": {
                            "Ledger_ID": "Unique transaction row ID",
                            "Transaction_ID": "Group transaction identifier (e.g. TXN-ACQ-000001)",
                            "Date_Key": "Foreign key to dim_calendar (YYYYMMDD)",
                            "Asset_Key": "Foreign key to dim_asset",
                            "Account_Code": "Foreign key to dim_coa.AccountCode",
                            "Amount": "Financial debit/credit value in USD",
                            "IoT_Hours": "Actual operating machine run hours recorded by IoT sensors",
                            "Carbon_Emissions_MT": "Estimated greenhouse gas emissions in metric tons",
                        },
                    },
                    "dim_coa": {
                        "purpose": "Chart of Accounts defining ledger classification.",
                        "primary_key": "AccountCode",
                        "columns": [
                            "AccountCode",
                            "AccountName",
                            "AccountType",
                            "AccountSubType",
                            "NormalBalance",
                        ],
                    },
                    "dim_calendar": {
                        "purpose": "Fiscal calendar dimensions for time-series aggregation.",
                        "primary_key": "Date_Key",
                        "columns": [
                            "Date",
                            "Date_Key",
                            "Fiscal_Year",
                            "Fiscal_Month",
                            "Scenario",
                        ],
                    },
                },
            }

        elif target_db == "world":
            return {
                "database": "world",
                "tables": {
                    "country": "Country demographics, continents, population, GNP, and government.",
                    "city": "Global cities with district and population.",
                    "countrylanguage": "Spoken languages per country with percentage.",
                },
            }
        else:
            return {
                "database": target_db,
                "message": "Standard schema catalog available via list_tables.",
            }

    elif name == "query_database":
        raw_sql = arguments.get("sql", "").strip()
        target_db = arguments.get("database")

        clean_sql = raw_sql.strip()
        if not clean_sql.lower().startswith(("select", "show", "describe", "explain", "with")):
            raise ValueError(
                "Security Policy: Only read-only queries (SELECT, SHOW, DESCRIBE, EXPLAIN, WITH) are permitted."
            )

        forbidden = [
            "insert",
            "update",
            "delete",
            "drop",
            "truncate",
            "alter",
            "create",
            "grant",
            "revoke",
            "lock",
            "flush",
        ]
        for kw in forbidden:
            if re.search(rf"\b{kw}\b", clean_sql, re.IGNORECASE):
                raise ValueError(
                    f"Security Policy: Query contains forbidden statement '{kw.upper()}'."
                )

        if target_db:
            safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
            await db.execute(f"USE `{safe_db}`;")

        # Automatically add limit if omitted to protect client memory
        if "limit" not in clean_sql.lower() and clean_sql.lower().startswith("select"):
            clean_sql = clean_sql.rstrip(";") + " LIMIT 100;"

        rows = await db.fetch_all(clean_sql)
        return {"query": clean_sql, "rows_returned": len(rows), "data": rows}

    elif name == "fetch_table_records":
        table = arguments["table_name"].strip()
        target_db = arguments.get("database", "capex").strip()
        limit = min(max(int(arguments.get("limit", 20)), 1), 200)
        offset = max(int(arguments.get("offset", 0)), 0)
        order_by = arguments.get("order_by")
        where_clause = arguments.get("where_clause")

        safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
        safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table)

        query = f"SELECT * FROM `{safe_db}`.`{safe_table}`"
        if where_clause:
            # Basic validation to prevent harmful statements
            if any(
                k in where_clause.lower() for k in ["drop", ";", "truncate", "update", "delete"]
            ):
                raise ValueError("Invalid where clause.")
            query += f" WHERE {where_clause}"

        if order_by:
            safe_order = re.sub(r"[^a-zA-Z0-9_ ]", "", order_by)
            query += f" ORDER BY {safe_order}"

        query += f" LIMIT {limit} OFFSET {offset};"

        records = await db.fetch_all(query)
        return {
            "database": safe_db,
            "table": safe_table,
            "returned_rows": len(records),
            "offset": offset,
            "limit": limit,
            "records": records,
        }

    elif name == "list_databases":
        rows = await db.fetch_all("SHOW DATABASES;")
        all_dbs = [
            r[next(iter(r.keys()))]
            for r in rows
            if r[next(iter(r.keys()))]
            not in ("information_schema", "performance_schema", "sys", "mysql")
        ]
        return {"databases": all_dbs}

    elif name == "list_tables":
        target_db = arguments.get("database", "capex").strip()
        safe_db = re.sub(r"[^a-zA-Z0-9_]", "", target_db)
        rows = await db.fetch_all(f"SHOW TABLES FROM `{safe_db}`;")
        tables = [next(iter(r.values())) for r in rows]
        return {"database": safe_db, "table_count": len(tables), "tables": tables}

    else:
        raise ValueError(f"Unknown MCP tool: {name}")
