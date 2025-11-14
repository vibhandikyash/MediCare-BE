"""Patient service for business logic operations."""

import logging
from datetime import date, datetime
from fastapi import HTTPException, status
from app.config.supabase import get_supabase_client
from app.schemas.patients import PatientCreate, PatientResponse

logger = logging.getLogger(__name__)

def serialize_dates_for_mongodb(data: dict) -> dict:
    """Convert date objects to ISO format strings for database storage."""
    for key, value in data.items():
        if isinstance(value, (date, datetime)):
            data[key] = value.isoformat()
        elif isinstance(value, list):
            data[key] = [
                item.isoformat() if isinstance(item, (date, datetime)) else item
                for item in value
            ]
    return data

async def create_patient(patient: PatientCreate) -> PatientResponse:
    """Create a new patient record in the database."""
    try:
        logger.info(f"Starting patient creation for: {patient.patient_name}")
        
        # Convert Pydantic model to dict
        logger.debug("Converting Pydantic model to dict")
        patient_dict = patient.model_dump()
        logger.debug(f"Patient dict keys: {list(patient_dict.keys())}")
        
        # Set default values for optional fields if not provided
        defaults = {
            "bill_details": [],
            "reports": [],
            "doctor_notes": "",
            "doctor_medical_certificate": "",
            "messages": [],
            "conversation_summary": "",
            "appointment_followup": "",
            "telegram_chat_id": None,
        }
        
        for key, default_value in defaults.items():
            if patient_dict.get(key) is None:
                logger.debug(f"Setting default value for {key}: {default_value}")
                patient_dict[key] = default_value
        
        # Convert date objects to datetime for MongoDB
        logger.debug("Serializing dates for MongoDB")
        patient_dict = serialize_dates_for_mongodb(patient_dict)
        
        # Insert patient into Supabase
        logger.info("Inserting patient into Supabase")
        supabase = get_supabase_client()
        result = supabase.table("patients").insert(patient_dict).execute()
        
        if not result.data or len(result.data) == 0:
            logger.error("Failed to create patient in Supabase")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create patient"
            )
        
        created_patient = result.data[0]
        logger.info(f"Patient inserted with ID: {created_patient.get('id')}")
        
        # Map 'id' to '_id' for PatientResponse compatibility
        created_patient["_id"] = created_patient.get("id")
        
        logger.info("Creating PatientResponse object")
        response = PatientResponse(**created_patient)
        logger.info(f"Patient created successfully: {response.id}")
        return response
        
    except HTTPException:
        logger.error("HTTPException in create_patient", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_patient: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create patient: {str(e)}"
        )

