-- ====================================================================
-- Multi-User MCP Server Database Schema (PostgreSQL)
-- Works with free Neon (neon.tech), Supabase (supabase.com), or any Postgres
-- ====================================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role VARCHAR(20) DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. API Keys for Private Access Authentication
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    api_key VARCHAR(128) UNIQUE NOT NULL,
    name VARCHAR(50) DEFAULT 'default',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Multi-Tenant User Records (Private Data isolated per user)
CREATE TABLE IF NOT EXISTS user_records (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL DEFAULT 'general',
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_api_keys_lookup ON api_keys(api_key) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_user_records_user_id ON user_records(user_id);
CREATE INDEX IF NOT EXISTS idx_user_records_category ON user_records(user_id, category);

-- ====================================================================
-- Sample Seed Data (for verification and quick testing)
-- ====================================================================

-- Seed Users
INSERT INTO users (id, username, email, role) VALUES
    (1, 'alice', 'alice@company.internal', 'member'),
    (2, 'bob', 'bob@company.internal', 'member'),
    (3, 'admin', 'admin@company.internal', 'admin')
ON CONFLICT (id) DO NOTHING;

-- Seed API Keys
INSERT INTO api_keys (user_id, api_key, name) VALUES
    (1, 'mcp_alice_sec_101', 'Alice Personal Key'),
    (2, 'mcp_bob_sec_202', 'Bob Personal Key'),
    (3, 'mcp_admin_sec_999', 'Admin Master Key')
ON CONFLICT (api_key) DO NOTHING;

-- Seed User-Isolated Data
INSERT INTO user_records (user_id, category, title, content, metadata) VALUES
    (1, 'project', 'Project Alpha Specs', 'Confidential blueprint for Alpha mobile platform release.', '{"priority": "high", "sprint": 4}'),
    (1, 'finance', 'Alice Q3 Travel Expense Report', 'Receipts for developer summit in San Francisco: $1,420 total.', '{"status": "approved", "budget_code": "ENG-2026"}'),
    (2, 'sales', 'Enterprise Client Pipeline', 'Acme Corp negotiation: $85,000 ARR contract pending final legal approval.', '{"stage": "closing", "probability": 0.9}'),
    (2, 'notes', 'Bob Architecture Research', 'Benchmarked pgvector vs Pinecone for semantic product catalog search.', '{"tags": ["db", "ai", "vector"]}')
ON CONFLICT DO NOTHING;
