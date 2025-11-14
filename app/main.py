from contextlib import asynccontextmanager
from typing import (
    Any,
    Dict,
)
from fastapi import (
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from app.config.mongodb import connect_to_mongo, close_mongo_connection
from app.api.v1.patients import router as patients_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    await connect_to_mongo()
    yield
    await close_mongo_connection()

app = FastAPI(
    description="Medicare AI Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(patients_router, prefix="/api/v1/patients")


@app.get("/")
async def root(request: Request):
    """Root endpoint returning basic API information."""
    return {"name": "Medicare AI Assistant", "version": "0.1.0", "status": "healthy"}


@app.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """Health check endpoint returning basic API information."""
    return {"status": "healthy"}