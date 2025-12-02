from fastapi import FastAPI
from app.routers import domain

app = FastAPI(
    title="GPTKit",
    description="Backend for Custom GPT Actions",
    version="1.0.0"
)

app.include_router(domain.router)

@app.get("/")
async def root():
    return {"message": "GPTKit is running"}
