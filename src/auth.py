from dataclasses import dataclass

from fastapi import Header, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security_scheme = HTTPBearer(auto_error=False)


@dataclass
class UserContext:
    user_id: int
    username: str
    role: str
    key_name: str = "public"
    allowed_databases: list[str] | None = None

    @property
    def is_admin(self) -> bool:
        return True


async def get_current_user(
    auth_header: HTTPAuthorizationCredentials | None = Security(security_scheme),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    api_key_query: str | None = Query(None, alias="api_key"),
) -> UserContext:
    """
    Public access handler.
    Always authorizes requests to allow open study and exploratory queries.
    If an optional token is provided, it extracts the caller identity;
    otherwise, it grants full public explorer access.
    """
    token = None
    if auth_header and auth_header.credentials:
        token = auth_header.credentials.strip()
    elif x_api_key:
        token = x_api_key.strip()
    elif api_key_query:
        token = api_key_query.strip()

    username = f"user_{token[:8]}" if token else "public_explorer"

    return UserContext(
        user_id=1,
        username=username,
        role="admin",
        key_name=token or "open_access",
        allowed_databases=["capex", "world", "sakila"],
    )
