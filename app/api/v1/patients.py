"""Patient API routes."""

import logging
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, status, Form, File, UploadFile, HTTPException
from app.schemas.patients import PatientCreate, PatientResponse
from app.services.patient_service import create_patient
from app.utils.cloudinary_service import upload_pdf_to_cloudinary, upload_multiple_pdfs_to_cloudinary
from pydantic import EmailStr

logger = logging.getLogger(__name__)
router = APIRouter(tags=["patients"])


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_endpoint(
    patient_name: str = Form(..., min_length=1, max_length=200),
    patient_contact: str = Form(..., min_length=10, max_length=10),
    patient_email: EmailStr = Form(...),
    emergency_name: str = Form(..., min_length=1, max_length=200),
    emergency_email: EmailStr = Form(...),
    emergency_contact: str = Form(..., min_length=10, max_length=10),
    patient_discharge_summary_pdf: UploadFile = File(...),
    admission_date: date = Form(...),
    discharge_date: Optional[date] = Form(None),
    medical_condition: str = Form(..., min_length=1, max_length=500),
    assigned_doctor: str = Form(..., min_length=1, max_length=200),
    age: int = Form(..., ge=0, le=130),
    gender: str = Form(..., min_length=1, max_length=50),
    bill_details: Optional[List[UploadFile]] = File(None),
    reports: Optional[List[UploadFile]] = File(None),
    doctor_notes: str = Form(default=""),
    doctor_medical_certificate: Optional[UploadFile] = File(None),
) -> PatientResponse:
    """
    Create a new patient record with PDF file uploads to Cloudinary.
    
    All PDF files will be uploaded to Cloudinary and their URLs will be stored.
    """
    try:
        logger.info(f"Creating patient: {patient_name}")
        logger.debug(f"Patient details - email: {patient_email}, contact: {patient_contact}, age: {age}, gender: {gender}")
        
        # Validate contact numbers
        logger.debug("Validating contact numbers")
        if not patient_contact.isdigit():
            logger.warning(f"Invalid patient_contact format: {patient_contact}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_contact must contain only digits"
            )
        if not emergency_contact.isdigit():
            logger.warning(f"Invalid emergency_contact format: {emergency_contact}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="emergency_contact must contain only digits"
            )
        
        # Upload discharge summary PDF
        logger.info(f"Uploading discharge summary PDF: {patient_discharge_summary_pdf.filename}")
        discharge_summary_url = await upload_pdf_to_cloudinary(
            patient_discharge_summary_pdf,
            folder=f"medicare/patients/{patient_name.replace(' ', '_')}/discharge_summary"
        )
        logger.info(f"Discharge summary uploaded successfully: {discharge_summary_url}")
        
        # Upload bill details PDFs
        bill_urls = []
        if bill_details:
            logger.info(f"Uploading {len(bill_details)} bill detail PDF(s)")
            bill_urls = await upload_multiple_pdfs_to_cloudinary(
                bill_details,
                folder=f"medicare/patients/{patient_name.replace(' ', '_')}/bills"
            )
            logger.info(f"Bill details uploaded successfully: {len(bill_urls)} file(s)")
        
        # Upload reports PDFs
        report_urls = []
        if reports:
            logger.info(f"Uploading {len(reports)} report PDF(s)")
            report_urls = await upload_multiple_pdfs_to_cloudinary(
                reports,
                folder=f"medicare/patients/{patient_name.replace(' ', '_')}/reports"
            )
            logger.info(f"Reports uploaded successfully: {len(report_urls)} file(s)")
        
        # Upload medical certificate PDF if provided
        medical_certificate_url = ""
        if doctor_medical_certificate:
            logger.info(f"Uploading medical certificate PDF: {doctor_medical_certificate.filename}")
            medical_certificate_url = await upload_pdf_to_cloudinary(
                doctor_medical_certificate,
                folder=f"medicare/patients/{patient_name.replace(' ', '_')}/certificates"
            )
            logger.info(f"Medical certificate uploaded successfully: {medical_certificate_url}")
        
        # Create patient data
        logger.debug("Creating PatientCreate object")
        patient_data = PatientCreate(
            patient_name=patient_name,
            patient_contact=patient_contact,
            patient_email=patient_email,
            emergency_name=emergency_name,
            emergency_email=emergency_email,
            emergency_contact=emergency_contact,
            patient_discharge_summary_pdf=discharge_summary_url,
            admission_date=admission_date,
            discharge_date=discharge_date,
            medical_condition=medical_condition,
            assigned_doctor=assigned_doctor,
            age=age,
            gender=gender,
            bill_details=bill_urls,
            reports=report_urls,
            doctor_notes=doctor_notes,
            doctor_medical_certificate=medical_certificate_url,
        )
        
        logger.info("Calling create_patient service")
        result = await create_patient(patient_data)
        logger.info(f"Patient created successfully with ID: {result.id}")
        return result
        
    except HTTPException:
        logger.error("HTTPException raised in create_patient_endpoint", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_patient_endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
