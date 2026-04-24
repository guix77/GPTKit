import logging
import logging.handlers
import os

from fastapi import Depends, FastAPI
from fastapi.openapi.utils import get_openapi

from app.auth import verify_token
from app.routers import domain

# Configure logging to server.log
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "..", "server.log")

# Create file handler
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)

app = FastAPI(
    title="GPTKit",
    description="Backend for Custom GPT Actions",
    version="1.0.0"
)

def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Bearer token authentication. Set GPTKIT_BEARER_TOKEN environment variable."
        }
    }
    # Apply security to all endpoints
    for path in openapi_schema["paths"].values():
        for method in path.values():
            if isinstance(method, dict) and "security" not in method:
                method["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

app.include_router(domain.router)

@app.get("/", dependencies=[Depends(verify_token)])
async def root() -> dict[str, str]:
    return {"message": "GPTKit is running"}
