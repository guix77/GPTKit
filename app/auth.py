from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

# HTTPBearer scheme for extracting Bearer token
security = HTTPBearer(auto_error=False)

def get_bearer_token() -> Optional[str]:
    """Get the expected Bearer token from environment variable."""
    # Allow disabling auth in local/dev mode
    if os.getenv("GPTKIT_DISABLE_AUTH", "").lower() in ("1", "true", "yes"):
        logger.warning("Authentication is DISABLED (GPTKIT_DISABLE_AUTH is set). Not recommended for production!")
        return None
    
    token = os.getenv("GPTKIT_BEARER_TOKEN")
    if not token:
        raise ValueError(
            "GPTKIT_BEARER_TOKEN environment variable must be set. "
            "Authentication is required for all endpoints. "
            "Set GPTKIT_DISABLE_AUTH=1 to disable auth in development."
        )
    return token

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[str]:
    """
    Verify the Bearer token from the Authorization header.
    
    Raises HTTPException if token is invalid or missing (unless auth is disabled).
    Returns the token if valid, or None if authentication is disabled.
    """
    expected_token = get_bearer_token()
    
    # If auth is disabled, allow access
    if expected_token is None:
        return None
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if credentials.credentials != expected_token:
        logger.warning(f"Invalid token attempt from client")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return credentials.credentials

