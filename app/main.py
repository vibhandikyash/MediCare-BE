import logging
from typing import (
    Any,
    Dict,
)
from fastapi import (
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import app.config.cloudinary
from app.api.v1.patients import router as patients_router

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = FastAPI(
    description="Medicare AI Assistant",
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