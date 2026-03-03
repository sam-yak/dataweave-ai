"""
DataWeave AI — Main application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from api.schema_routes import schema_builder_router

app = FastAPI(
    title="DataWeave AI",
    description="Multi-agent AI data onboarding platform",
    version="1.0.0",
)

# CORS — allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://dataweaveai.co",
        "https://www.dataweaveai.co",
        "https://dataweave-ai-gold.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(schema_builder_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "name": "DataWeave AI",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }
