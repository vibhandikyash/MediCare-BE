"""Patient service for business logic operations."""

from fastapi import HTTPException, status
from app.config.mongodb import patients_collection
from app.schemas.patients import PatientCreate, PatientResponse

async def create_patient(patient: PatientCreate) -> PatientResponse:
    """Create a new patient record in the database."""
    try:
        # Convert Pydantic model to dict
        patient_dict = patient.model_dump()
        
        # Set default values for optional fields if not provided
        defaults = {
            "bill_details": [],
            "reports": [],
            "doctor_notes": "",
            "doctor_medical_certificate": "",
        }
        
        for key, default_value in defaults.items():
            if patient_dict.get(key) is None:
                patient_dict[key] = default_value
        
        # Insert patient into MongoDB
        result = await patients_collection.insert_one(patient_dict)
        
        # Fetch the created patient
        created_patient = await patients_collection.find_one({"_id": result.inserted_id})
        
        if not created_patient:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created patient"
            )
        
        # Convert ObjectId to string for response
        created_patient["_id"] = str(created_patient["_id"])
        
        return PatientResponse(**created_patient)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create patient: {str(e)}"
        )

