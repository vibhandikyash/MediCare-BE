"""Patient API routes."""

from fastapi import APIRouter, status
from app.schemas.patients import PatientCreate, PatientResponse
from app.services.patient_service import create_patient

router = APIRouter(tags=["patients"])


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_endpoint(patient: PatientCreate) -> PatientResponse:
    """Create a new patient record."""
    return await create_patient(patient)

