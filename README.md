# Multi-User MySQL MCP Server on Vercel (Free Tier)

A production-ready **Model Context Protocol (MCP)** server built with **Python (FastAPI)**, configured to deploy serverless on **Vercel's Free Hobby Tier**, connected to your online **MySQL database** (`capex`, `world`, `sakila`), with **Private Access Only** and **multi-user role-based permissions**.

---

## 💡 The Core Architecture

### 1. Dual-Transport Architecture for Vercel
Standard MCP servers often use persistent SSE (Server-Sent Events) or local `stdio`. On Vercel Serverless Functions (Hobby tier), functions are ephemeral (15–60s max execution).
This server implements:
- **Stateless HTTP JSON-RPC (`POST /mcp` or `POST /api/mcp`)**: Serverless-native. Executes `initialize`, `tools/list`, `tools/call`, and `resources/read` independently in milliseconds, handling cold starts without dropped sessions.
- **SSE Transport (`GET /sse` & `POST /messages`)**: Standard MCP SSE transport for clients (e.g., Claude Desktop via `mcp-remote`, Cursor) with in-memory session routing and direct HTTP payload fallbacks.

### 2. Multi-User Private Access
- Every request requires private authentication via `Authorization: Bearer <API_KEY>` or `X-API-Key: <API_KEY>`.
- The server validates the key into a `UserContext` with specific database permissions:
  - **Admin** (`mcp_admin_sec_999`): Full query access across all databases (`capex`, `world`, `sakila`).
  - **Alice** (`mcp_alice_sec_101`): Financial analyst scoped to `capex` and `world`.
  - **Bob** (`mcp_bob_sec_202`): General analyst scoped to `world` and `sakila`.

---

## 🗄️ Connected Database Overview

- **Engine**: MySQL 8.0.46
- **Tunnel Host**: `upkbh-106-192-73-56.run.pinggy-free.link`
- **Port**: `34659`
- **User**: `root`
- **Active Databases Verified**:
  - `capex`: Financial ledger (`fact_financial_ledger`: 2.18M+ rows, `dim_asset`: 50,000 rows, `dim_calendar`, `dim_coa`)
  - `world`: International geography (`country`, `city`, `countrylanguage`)
  - `sakila`: Enterprise operations (`customer`, `payment`, `rental`, `film`)

---

## 🚀 Deployment Instructions for Vercel

### Step 1: Push to a GitHub Repository
1. In your terminal:
   ```bash
   git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
   git push -u origin main
   ```
   *(Note: `.env` is automatically ignored by `.gitignore` to keep credentials secure).*

### Step 2: Import into Vercel
1. Go to [https://vercel.com/new](https://vercel.com/new).
2. Import your GitHub repository.
3. Under **Environment Variables**, configure:
   - `DATABASE_URL`: `mysql://root:password@upkbh-106-192-73-56.run.pinggy-free.link:34659/capex`
   - `MASTER_API_KEY`: `mcp_admin_sec_999`
   - `ALICE_API_KEY`: `mcp_alice_sec_101`
   - `BOB_API_KEY`: `mcp_bob_sec_202`
4. Click **Deploy**. Vercel will build and assign you a live HTTPS domain:
   `https://your-mcp-app.vercel.app`

> [!NOTE]
> **About Pinggy Free Links**: Pinggy free tunnels stay active as long as the tunnel command on your host is running. If you ever restart the tunnel and receive a new port/hostname, update `DATABASE_URL` in your `.env` (locally) or in the **Vercel Project Settings > Environment Variables** without needing to touch code!

---

## 🧪 Testing the MCP Server

Run `test_client.py` against your local development server or live Vercel URL:

```bash
# Against local server:
python test_client.py http://127.0.0.1:8000

# Against deployed Vercel URL:
python test_client.py https://your-mcp-app.vercel.app
```

---

## 🔌 Connecting AI Clients (Claude Desktop / Cursor)

### Claude Desktop
In `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "capex-mysql-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://your-mcp-app.vercel.app/sse",
        "--header",
        "Authorization: Bearer mcp_alice_sec_101"
      ]
    }
  }
}
```

### Cursor IDE
In **Settings > Features > MCP Servers > Add New MCP Server**:
- **Name**: `Capex MySQL MCP`
- **Type**: `SSE`
- **URL**: `https://your-mcp-app.vercel.app/sse?api_key=mcp_alice_sec_101`

---

## 🧰 Available MCP Tools

| Tool Name | Description | Example Query |
| :--- | :--- | :--- |
| `list_databases` | Lists accessible databases for the user. | `list_databases()` |
| `list_tables` | Lists tables inside a target database. | `list_tables(database="capex")` |
| `describe_table` | Inspects columns, keys, and data types. | `describe_table(table_name="dim_asset")` |
| `fetch_table_records` | Fetches rows with limit, offset, and order. | `fetch_table_records(table_name="dim_asset", limit=10)` |
| `query_database` | Runs safe read-only SQL `SELECT` queries. | `SELECT Asset_Class, COUNT(*) FROM capex.dim_asset GROUP BY Asset_Class` |
| `get_database_summary` | Returns table row counts and sizes in MB. | `get_database_summary(database="capex")` |
| `get_my_profile` | Returns identity, role, and permissions. | `get_my_profile()` |
