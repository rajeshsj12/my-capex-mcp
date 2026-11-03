from dataclasses import dataclass
from typing import Optional
from fastapi import Header, Query, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings

security_scheme = HTTPBearer(auto_error=False)

@dataclass
class UserContext:
    user_id: int
    username: str
    role: str
    key_name: str = "default"
    allowed_databases: Optional[list] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

async def resolve_user(api_key: str) -> Optional[UserContext]:
    """
    Validates the provided API key against configured multi-user credentials.
    """
    if not api_key:
        return None

    # 1. Master / Admin Key
    if settings.MASTER_API_KEY and api_key == settings.MASTER_API_KEY:
        return UserContext(
            user_id=1,
            username="admin",
            role="admin",
            key_name="master_admin_key",
            allowed_databases=["capex", "world", "sakila"]
        )

    # 2. Alice Key (Financial / Capex Analyst)
    if settings.ALICE_API_KEY and api_key == settings.ALICE_API_KEY:
        return UserContext(
            user_id=2,
            username="alice",
            role="analyst",
            key_name="Alice Capex Analyst Key",
            allowed_databases=["capex", "world"]
        )

    # 3. Bob Key (General / World Analyst)
    if settings.BOB_API_KEY and api_key == settings.BOB_API_KEY:
        return UserContext(
            user_id=3,
            username="bob",
            role="analyst",
            key_name="Bob World Analyst Key",
            allowed_databases=["world", "sakila"]
        )

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
            detail="Unauthorized: Missing API key. Provide 'Authorization: Bearer <KEY>' or 'X-API-Key: <KEY>' header."
        )

    user = await resolve_user(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or inactive API key."
        )

    return user
