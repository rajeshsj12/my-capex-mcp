# Multi-User Python MCP Server on Vercel (Free Tier)

A production-ready **Model Context Protocol (MCP)** server built with **Python (FastAPI)**, deployed serverless on **Vercel's Free Hobby Tier**, connected to a free **PostgreSQL online database** (Neon or Supabase), with **Private Access Only** and **multi-user tenant isolation**.

---

## 💡 The Core Idea & Architecture

### 1. The Challenge of MCP on Serverless Platforms
Standard MCP servers often use persistent SSE (Server-Sent Events) or local `stdio`. However, Vercel Serverless Functions are ephemeral (with 15–60s execution limits on the free tier) and distribute traffic across multiple stateless instances. If instance A opens an SSE connection and instance B receives a tool call, in-memory state is lost.

### 2. The Solution: Dual-Transport Architecture
This MCP server solves this problem by providing two parallel transport modes:
- **Stateless HTTP JSON-RPC (`POST /mcp` or `POST /api/mcp`)**: Serverless-native. Each request (`initialize`, `tools/list`, `tools/call`) executes independently in milliseconds, returns immediate results, and never drops connections.
- **SSE Transport (`GET /sse` & `POST /messages`)**: Standard MCP SSE transport for clients (e.g. Claude Desktop via `mcp-remote`, Cursor, etc.) with in-memory session dispatch and direct HTTP response fallbacks.

### 3. Multi-User Private Access (Row-Level Security)
- Every request requires private authentication via `Authorization: Bearer <API_KEY>` or `X-API-Key: <API_KEY>`.
- The server resolves the key against the database `api_keys` table to an isolated `UserContext(user_id, username, role)`.
- **Database queries automatically filter by `user_id`**, ensuring User Alice can never see or modify User Bob's records.

```
                      ┌──────────────────────────────────────────────┐
                      │             Claude Desktop / Cursor          │
                      │         (Sends API Key in Auth Header)       │
                      └──────────────────────┬───────────────────────┘
                                             │ HTTPS
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │          Vercel Serverless (FastAPI)         │
                      │ 1. Validate API Key -> UserContext           │
                      │ 2. Route JSON-RPC 2.0 (MCP Protocol)         │
                      │ 3. Enforce Tenant Scoping (user_id = $1)     │
                      └──────────────────────┬───────────────────────┘
                                             │ SSL (Pooled Connection)
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │     Free Online Database (Neon / Supabase)    │
                      │  - users & api_keys                          │
                      │  - user_records (multi-tenant data)          │
                      └──────────────────────────────────────────────┘
```

---

## 🛠 Project Structure

```text
├── api/
│   └── index.py         # Vercel Serverless entrypoint (FastAPI app)
├── src/
│   ├── __init__.py
│   ├── config.py        # Settings and environment variables
│   ├── auth.py          # Private multi-user authentication & resolution
│   ├── db.py            # Serverless-optimized asyncpg database pool
│   ├── tools.py         # MCP Tool schemas and execution logic
│   └── mcp_handler.py   # MCP JSON-RPC 2.0 protocol engine & SSE streams
├── schema.sql           # Database schema with sample multi-user data
├── vercel.json          # Vercel deployment configuration
├── requirements.txt     # Python dependencies
├── test_client.py       # Multi-user test script
├── .env.example         # Environment template
└── README.md
```

---

## 🚀 Step 1: Set Up Free Online Database (Neon / Supabase)

You can get a free, managed PostgreSQL database in under 2 minutes:

### Option A: Neon (Recommended - Best for Serverless)
1. Go to [https://neon.tech](https://neon.tech) and create a free account (no credit card required).
2. Create a new project (e.g., `mcp-db`).
3. In the Neon Console, go to **SQL Editor**, paste the contents of `schema.sql`, and click **Run**.
4. In the Neon Dashboard, copy your connection string (select **Pooled connection**):
   ```
   postgresql://[user]:[password]@[ep-name]-pooler.[region].neon.tech/neondb?sslmode=require
   ```

### Option B: Supabase
1. Go to [https://supabase.com](https://supabase.com) and create a free project.
2. Go to **SQL Editor**, paste the contents of `schema.sql`, and click **Run**.
3. Under **Project Settings > Database**, copy your connection string (select **Transaction Pooler**, port `6543`).

---

## ⚡ Step 2: Deploy to Vercel for Free

### Method A: Deploy via GitHub (Easiest)
1. Initialize git and commit your files:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for Multi-User MCP Server"
   ```
2. Push this repository to your GitHub account (make the repo **Private** for extra security).
3. Log in to [https://vercel.com](https://vercel.com).
4. Click **"Add New..." > "Project"**, and import your GitHub repository.
5. In the **Environment Variables** section, add:
   - `DATABASE_URL`: Your pooled PostgreSQL connection string from Step 1.
   - `MASTER_API_KEY`: A secure master secret (e.g. `mcp_admin_sec_999`).
6. Click **Deploy**. Vercel will build and assign you a live HTTPS domain:
   `https://your-project-name.vercel.app`

### Method B: Deploy via Vercel CLI
If you have Node.js installed:
```bash
npx vercel
```
Follow the interactive prompts, link to your Vercel account, and set the environment variables in the Vercel Dashboard.

---

## 🧪 Step 3: Verify & Test Multi-User Isolation

Run `test_client.py` against your deployed Vercel domain:

```bash
python test_client.py https://your-project-name.vercel.app
```

The script will verify:
1. Public health check (`GET /`).
2. Unauthenticated request to `/mcp` is rejected with `HTTP 401 Unauthorized`.
3. User Alice (`mcp_alice_sec_101`) initializes and queries only Alice's records.
4. User Bob (`mcp_bob_sec_202`) queries only Bob's records, proving strict data isolation.

---

## 🔌 Step 4: Connect AI Clients (Claude Desktop / Cursor)

### Connecting to Claude Desktop (Private Remote MCP)
In Claude Desktop's config file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the server using `mcp-remote` with private authentication headers:

```json
{
  "mcpServers": {
    "private-db-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://your-project-name.vercel.app/sse",
        "--header",
        "Authorization: Bearer mcp_alice_sec_101"
      ]
    }
  }
}
```

### Connecting in Cursor
In Cursor Settings > Features > MCP Servers > Add New MCP Server:
- **Name**: `Private DB MCP`
- **Type**: `SSE`
- **URL**: `https://your-project-name.vercel.app/sse?api_key=mcp_alice_sec_101`

---

## 🧰 Available MCP Tools

| Tool Name | Description | Tenant Scoped? |
| :--- | :--- | :--- |
| `get_my_profile` | Returns identity, role, and permissions of the caller. | Yes |
| `fetch_user_records` | Fetches private database records with search & pagination. | Yes (`user_id = $1`) |
| `insert_user_record` | Creates a new private record belonging to the user. | Yes (auto-assigned) |
| `execute_safe_query` | Read-only SQL `SELECT` with strict tenant checks. | Yes |
| `list_accessible_tables` | Lists accessible tables and descriptions. | Schema level |
| `get_database_stats` | Aggregated record counts & categories for the user. | Yes |

---

## 🔒 Security Best Practices
1. **Never commit `.env`**: `.gitignore` is pre-configured to exclude secrets.
2. **Revocation**: To revoke a user's access, set `is_active = FALSE` in the `api_keys` table.
3. **Connection Pooling**: Always use the Neon or Supabase **pooled connection string** to prevent hitting connection limits on serverless cold starts.
