"""Patient service for business logic operations."""

import logging
from datetime import date, datetime
from fastapi import HTTPException, status
from app.config.mongodb import patients_collection
from app.schemas.patients import PatientCreate, PatientResponse

logger = logging.getLogger(__name__)


def serialize_dates_for_mongodb(data: dict) -> dict:
    """
    Convert datetime.date objects to datetime.datetime for MongoDB compatibility.
    
    MongoDB BSON doesn't support date objects, only datetime objects.
    """
    serialized = {}
    for key, value in data.items():
        if value is None:
            serialized[key] = None
        elif isinstance(value, date) and not isinstance(value, datetime):
            # Convert date to datetime at midnight
            serialized[key] = datetime.combine(value, datetime.min.time())
        else:
            serialized[key] = value
    return serialized


def deserialize_dates_from_mongodb(data: dict) -> dict:
    """
    Convert datetime.datetime objects back to datetime.date for Pydantic compatibility.
    
    When reading from MongoDB, dates are stored as datetime objects.
    """
    deserialized = {}
    date_fields = ["admission_date", "discharge_date"]  # Fields that should be date objects
    
    for key, value in data.items():
        if key in date_fields and isinstance(value, datetime):
            # Convert datetime to date
            deserialized[key] = value.date()
        else:
            deserialized[key] = value
    return deserialized


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
        }
        
        for key, default_value in defaults.items():
            if patient_dict.get(key) is None:
                logger.debug(f"Setting default value for {key}: {default_value}")
                patient_dict[key] = default_value
        
        # Convert date objects to datetime for MongoDB
        logger.debug("Serializing dates for MongoDB")
        patient_dict = serialize_dates_for_mongodb(patient_dict)
        
        # Insert patient into MongoDB
        logger.info("Inserting patient into MongoDB")
        result = await patients_collection.insert_one(patient_dict)
        logger.info(f"Patient inserted with MongoDB ID: {result.inserted_id}")
        
        # Fetch the created patient
        logger.debug("Fetching created patient from MongoDB")
        created_patient = await patients_collection.find_one({"_id": result.inserted_id})
        
        if not created_patient:
            logger.error(f"Failed to retrieve created patient with ID: {result.inserted_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created patient"
            )
        
        # Convert datetime back to date for Pydantic
        logger.debug("Deserializing dates from MongoDB")
        created_patient = deserialize_dates_from_mongodb(created_patient)
        
        # Convert ObjectId to string for response
        created_patient["_id"] = str(created_patient["_id"])
        logger.debug("Converted ObjectId to string")
        
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

