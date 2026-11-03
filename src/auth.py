from dataclasses import dataclass
from typing import Optional
from fastapi import Header, Query, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings
from src import db

security_scheme = HTTPBearer(auto_error=False)

@dataclass
class UserContext:
    user_id: int
    username: str
    role: str
    key_name: str = "default"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

async def resolve_user(api_key: str) -> Optional[UserContext]:
    """
    Validates the provided API key against Master Key or the database api_keys table.
    """
    if not api_key:
        return None

    # 1. Check Master / Admin API key fallback
    if settings.MASTER_API_KEY and api_key == settings.MASTER_API_KEY:
        return UserContext(
            user_id=3,
            username="admin",
            role="admin",
            key_name="master_admin_key"
        )

    # 2. Check Database API Keys
    try:
        query = """
            SELECT k.name as key_name, k.is_active, u.id as user_id, u.username, u.role
            FROM api_keys k
            JOIN users u ON k.user_id = u.id
            WHERE k.api_key = $1 AND k.is_active = TRUE
            LIMIT 1;
        """
        row = await db.fetch_one(query, api_key)
        if row:
            return UserContext(
                user_id=row["user_id"],
                username=row["username"],
                role=row["role"],
                key_name=row["key_name"]
            )
    except Exception as e:
        # If DB is not reachable or tables not yet seeded, check mock/demo fallback keys
        if api_key == "mcp_alice_sec_101":
            return UserContext(user_id=1, username="alice", role="member", key_name="Alice Demo Key")
        elif api_key == "mcp_bob_sec_202":
            return UserContext(user_id=2, username="bob", role="member", key_name="Bob Demo Key")

    return None

async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key_query: Optional[str] = Query(None, alias="api_key")
) -> UserContext:
    """
    FastAPI dependency to enforce private authentication.
    Accepts:
      - Authorization: Bearer <API_KEY>
      - X-API-Key: <API_KEY>
      - Query param: ?api_key=<API_KEY> (e.g. for SSE streams)
    """
    token = None
    if auth_header and auth_header.credentials:
        token = auth_header.credentials.strip()
    elif x_api_key:
        token = x_api_key.strip()
    elif api_key_query:
        token = api_key_query.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing API key. Pass 'Authorization: Bearer <KEY>' or 'X-API-Key: <KEY>' header."
        )

    user = await resolve_user(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or inactive API key."
        )

    return user
