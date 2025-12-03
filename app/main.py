from fastapi import FastAPI
from app.routers import domain
import logging
import logging.handlers
import os

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

app.include_router(domain.router)

@app.get("/")
async def root():
    return {"message": "GPTKit is running"}
