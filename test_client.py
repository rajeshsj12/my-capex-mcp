"""
Test script for Multi-User MCP Server.
Works against local development server (http://127.0.0.1:8000)
or deployed Vercel URL (https://your-app.vercel.app).
"""

import sys
import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"

def make_request(path: str, data: dict = None, headers: dict = None, method: str = "GET"):
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
    print(f"=== Testing MCP Server at {BASE_URL} ===\n")

    # 1. Test Health / Root
    print("[1] Checking Public Root Endpoint...")
    status, res = make_request("/")
    print(f"    Status: {status}")
    print(f"    Response: {json.dumps(res, indent=2)}\n")

    # 2. Test Unauthorized Access (Private access only)
    print("[2] Testing Unauthenticated Access to /mcp (Expect 401)...")
    status, res = make_request("/mcp", data={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, method="POST")
    print(f"    Status: {status} (Expected: 401)")
    print(f"    Response: {res}\n")

    # 3. Test User Alice
    alice_headers = {"Authorization": "Bearer mcp_alice_sec_101"}
    print("[3] Testing User Alice (API Key: mcp_alice_sec_101)...")
    
    # 3a. Initialize
    status, res = make_request("/mcp", data={
        "jsonrpc": "2.0",
        "id": 10,
        "method": "initialize",
        "params": {}
    }, headers=alice_headers, method="POST")
    print(f"    Alice Initialize Result: {res.get('result', {}).get('instructions')}")

    # 3b. List Tools
    status, res = make_request("/mcp", data={
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/list",
        "params": {}
    }, headers=alice_headers, method="POST")
    tools = [t["name"] for t in res.get("result", {}).get("tools", [])]
    print(f"    Available Tools ({len(tools)}): {tools}")

    # 3c. Call get_my_profile
    status, res = make_request("/mcp", data={
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {"name": "get_my_profile", "arguments": {}}
    }, headers=alice_headers, method="POST")
    print(f"    Alice Profile: {res.get('result', {}).get('content', [{}])[0].get('text')}")

    # 3d. Call fetch_user_records
    status, res = make_request("/mcp", data={
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {"name": "fetch_user_records", "arguments": {}}
    }, headers=alice_headers, method="POST")
    print(f"    Alice Records: {res.get('result', {}).get('content', [{}])[0].get('text')}\n")

    # 4. Test User Bob (Tenant Isolation check)
    bob_headers = {"Authorization": "Bearer mcp_bob_sec_202"}
    print("[4] Testing User Bob (API Key: mcp_bob_sec_202)...")
    status, res = make_request("/mcp", data={
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {"name": "fetch_user_records", "arguments": {}}
    }, headers=bob_headers, method="POST")
    print(f"    Bob Records: {res.get('result', {}).get('content', [{}])[0].get('text')}\n")

    print("=== All Test Verifications Completed ===")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1].rstrip("/")
    run_tests()
