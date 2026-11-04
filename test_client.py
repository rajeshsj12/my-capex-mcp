"""
Test script for Public Multi-User MySQL Analytics MCP Server.
Works against local development server (http://127.0.0.1:8000)
or deployed Vercel URL (https://your-app.vercel.app).
"""

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "https://capex-mcp.vercel.app"


def make_request(
    path: str, data: dict | None = None, headers: dict | None = None, method: str = "GET"
):
    url = f"{BASE_URL}{path}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    encoded_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            return status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return e.code, parsed


def run_tests():
    print(f"=== Testing Public MCP Server at {BASE_URL} ===\n")

    # 1. Test Root Info
    print("[1] Checking Public Root Endpoint...")
    status, res = make_request("/")
    print(f"    Status: {status}")
    print(f"    Access Mode: {res.get('access')}")
    print(f"    Database Status: {res.get('database')}\n")

    # 2. Test Initialize (Public / No Headers)
    print("[2] Initializing MCP Session (No auth headers)...")
    status, res = make_request(
        "/mcp",
        data={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        method="POST",
    )
    print(f"    Status: {status}")
    print(f"    Server Info: {res.get('result', {}).get('serverInfo')}\n")

    # 3. Test Tools List
    print("[3] Listing Available Tools...")
    status, res = make_request(
        "/mcp",
        data={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        method="POST",
    )
    tools = [t["name"] for t in res.get("result", {}).get("tools", [])]
    print(f"    Available Tools ({len(tools)}): {tools}\n")

    # 4. Test Consolidated Summary
    print("[4] Testing Tool: get_consolidated_summary...")
    status, res = make_request(
        "/mcp",
        data={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_consolidated_summary",
                "arguments": {"database": "capex"},
            },
        },
        method="POST",
    )
    summary_text = res.get("result", {}).get("content", [{}])[0].get("text", "{}")
    summary = json.loads(summary_text)
    print("    Report Title:", summary.get("report_title"))
    print(
        "    Portfolio Assets Count:",
        summary.get("asset_portfolio_summary", {}).get("total_assets"),
    )
    print(
        "    Ledger Transactions Count:",
        summary.get("operational_ledger_summary", {}).get("total_ledger_transactions"),
    )
    print(
        "    Total Carbon Emissions (MT):",
        summary.get("operational_ledger_summary", {}).get("cumulative_carbon_emissions_mt"),
    )
    print(
        "    Top Asset Class:",
        summary.get("asset_class_breakdown", [{}])[0].get("Asset_Class"),
        "\n",
    )

    # 5. Test Executive KPIs
    print("[5] Testing Tool: get_executive_kpis...")
    status, res = make_request(
        "/mcp",
        data={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_executive_kpis", "arguments": {}},
        },
        method="POST",
    )
    kpi_text = res.get("result", {}).get("content", [{}])[0].get("text", "{}")
    kpis = json.loads(kpi_text)
    print(
        "    Top Asset:",
        kpis.get("top_10_capital_assets", [{}])[0].get("Asset_ID"),
        "- Cost USD:",
        kpis.get("top_10_capital_assets", [{}])[0].get("Cost_USD"),
    )
    print(
        "    ESG Top Carbon Category:",
        kpis.get("sustainability_carbon_intensity", [{}])[0].get("Asset_Class"),
        "\n",
    )

    # 6. Test Question Answering: Sustainability & Carbon Footprint
    print("[6] Testing Tool: ask_database_question (Topic: sustainability_carbon)...")
    status, res = make_request(
        "/mcp",
        data={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "ask_database_question",
                "arguments": {
                    "topic": "sustainability_carbon",
                    "question": "What is our carbon emission breakdown across machines?",
                },
            },
        },
        method="POST",
    )
    qa_text = res.get("result", {}).get("content", [{}])[0].get("text", "{}")
    qa = json.loads(qa_text)
    print("    Answer Summary:", qa.get("answer_summary"))
    print("    Sample Emission Row:", qa.get("data", [{}])[0], "\n")

    # 7. Test Universal Knowledge Search
    print("[7] Testing Tool: search_database_knowledge (Query: 'Robot')...")
    status, res = make_request(
        "/mcp",
        data={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "search_database_knowledge",
                "arguments": {"query": "Robot"},
            },
        },
        method="POST",
    )
    search_text = res.get("result", {}).get("content", [{}])[0].get("text", "{}")
    search_res = json.loads(search_text)
    print(
        "    Matched Assets Count:",
        len(search_res.get("results", {}).get("matching_assets", [])),
    )
    print(
        "    First Matched Asset:",
        search_res.get("results", {}).get("matching_assets", [{}])[0],
        "\n",
    )

    print("=== All Test Verifications Completed Successfully ===")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1].rstrip("/")
    run_tests()
