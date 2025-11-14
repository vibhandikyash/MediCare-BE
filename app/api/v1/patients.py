"""Patient API routes."""

import logging
import json
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, status, Form, File, UploadFile, HTTPException
from app.schemas.patients import PatientCreate, PatientResponse
from app.services.patient_service import create_patient, get_all_patients
from app.utils.cloudinary_service import upload_pdf_to_cloudinary, upload_multiple_pdfs_to_cloudinary
from app.utils.pdf_service import process_pdf_discharge_summary
from app.services.discharge_parser_service import parse_discharge_summary_with_vision
from pydantic import EmailStr

logger = logging.getLogger(__name__)
router = APIRouter(tags=["patients"])


@router.get("", response_model=List[PatientResponse], status_code=status.HTTP_200_OK)
async def get_all_patients_endpoint() -> List[PatientResponse]:
    """
    Get all patient records with their Cloudinary URLs.
    
    Returns all patient data including:
    - bill_details: List of Cloudinary URLs for bill PDFs
    - reports: List of Cloudinary URLs for report PDFs
    - doctor_medical_certificate: Cloudinary URL for medical certificate
    - medication_details: Contains discharge_summary_url if available
    
    All Cloudinary URLs are already stored in the database and are directly accessible.
    """
    try:
        logger.info("Fetching all patients")
        patients = await get_all_patients()
        logger.info(f"Successfully retrieved {len(patients)} patients")
        logger.debug(f"Patients: {patients}")
        return patients
        
    except HTTPException:
        logger.error("HTTPException raised in get_all_patients_endpoint", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_all_patients_endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_endpoint(
    patient_name: str = Form(..., min_length=1, max_length=200),
    patient_contact: str = Form(..., min_length=10, max_length=10),
    patient_email: EmailStr = Form(...),
    emergency_name: str = Form(..., min_length=1, max_length=200),
    emergency_email: EmailStr = Form(...),
    emergency_contact: str = Form(..., min_length=10, max_length=10),
    medication_details: Optional[str] = Form(None),
    admission_date: date = Form(...),
    discharge_date: Optional[date] = Form(None),
    medical_condition: str = Form(..., min_length=1, max_length=500),
    assigned_doctor: str = Form(..., min_length=1, max_length=200),
    age: int = Form(..., ge=0, le=130),
    gender: str = Form(..., min_length=1, max_length=50),
    bill_details: Optional[List[UploadFile]] = File(None),
    reports: Optional[List[UploadFile]] = File(None),
    doctor_notes: str = Form(...),
    doctor_medical_certificate: Optional[UploadFile] = File(None),
    discharge_summary_pdf: Optional[UploadFile] = File(None),
    telegram_chat_id: Optional[float] = Form(None),
) -> PatientResponse:
    """
    Create a new patient record with PDF file uploads to Cloudinary.
    
    If discharge_summary_pdf is provided, it will be automatically parsed to extract
    medication details. The extracted medications will be stored in medication_details.
    
    All PDF files will be uploaded to Cloudinary and their URLs will be stored.
    medication_details and doctor_notes should be JSON strings (optional if discharge_summary_pdf is provided).
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
        
        # Process discharge summary PDF if provided
        medication_details_dict = {}
        
        if discharge_summary_pdf:
            try:
                logger.info(f"=== DISCHARGE SUMMARY PROCESSING STARTED ===")
                logger.info(f"Processing discharge summary PDF: {discharge_summary_pdf.filename}")
                
                # Validate file type
                if not discharge_summary_pdf.filename or not discharge_summary_pdf.filename.lower().endswith('.pdf'):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Discharge summary must be a PDF file"
                    )
                
                # Step 1: Process PDF: upload PDF, convert to images (for AI processing)
                logger.info("Step 1: Uploading PDF and converting to images...")
                discharge_summary_url, image_bytes_list = await process_pdf_discharge_summary(
                    discharge_summary_pdf,
                    patient_name
                )
                
                logger.info(f"✓ PDF uploaded to: {discharge_summary_url}")
                logger.info(f"✓ Converted PDF to {len(image_bytes_list)} image(s) for AI processing")
                
                # Step 2: Parse discharge summary with AI vision model
                logger.info("Step 2: Parsing discharge summary with AI vision model...")
                parsed_data = await parse_discharge_summary_with_vision(
                    image_bytes_list=image_bytes_list
                )
                
                logger.info(f"✓ Parsed {len(parsed_data.medications)} medications from discharge summary")
                
                # Step 3: Convert parsed medications to dict format
                logger.info("Step 3: Structuring medication data...")
                medications_list = []
                for med in parsed_data.medications:
                    reminders_list = []
                    for reminder in med.reminders:
                        reminders_list.append({
                            "day": reminder.day.value,
                            "date": reminder.datte.isoformat(),
                            "time": reminder.time,
                            "isreminded": reminder.isreminded,
                            "isresponded": reminder.isresponded,
                        })
                    
                    med_dict = {
                        "name": med.name,
                        "dosage": med.dosage,
                        "start_date": med.start_date.isoformat() if med.start_date else None,
                        "end_date": med.end_date.isoformat() if med.end_date else None,
                        "timing": med.timing,
                        "days": [d.value for d in med.days],
                        "frequency": med.frequency.value,
                        "status": med.status.value,
                        "reminders": reminders_list,
                    }
                    medications_list.append(med_dict)
                    logger.debug(f"  - Medication: {med.name} ({med.dosage}) with {len(reminders_list)} reminders")
                
                # Structure medication_details
                medication_details_dict = {
                    "medications": medications_list,
                    "source": "discharge_summary",
                    "parsed_at": datetime.now().isoformat(),
                    "discharge_summary_url": discharge_summary_url,
                    "patient_name_from_summary": parsed_data.patient_name,
                    "discharge_date_from_summary": parsed_data.discharge_date.isoformat() if parsed_data.discharge_date else None,
                    "diagnosis": parsed_data.diagnosis,
                    "additional_notes": parsed_data.additional_notes
                }
                
                logger.info(f"✓ Successfully structured medication details: {len(medications_list)} medications")
                logger.info(f"=== DISCHARGE SUMMARY PROCESSING COMPLETED ===")
                
            except HTTPException:
                logger.error("HTTPException during discharge summary processing", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Error processing discharge summary: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to process discharge summary: {str(e)}"
                )
        
        # If no discharge summary, parse medication_details JSON if provided
        elif medication_details:
            logger.info("Parsing medication_details from JSON string")
            try:
                medication_details_dict = json.loads(medication_details)
                logger.info(f"Parsed medication_details JSON with {len(medication_details_dict.get('medications', []))} medications")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid medication_details JSON: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"medication_details must be valid JSON: {str(e)}"
                )
        else:
            # No medication details provided at all
            logger.info("No medication details provided - using empty dict")
            medication_details_dict = {}
        
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
        logger.info("Creating PatientCreate object with medication_details")
        logger.debug(f"medication_details contains {len(medication_details_dict.get('medications', []))} medications")
        
        patient_data = PatientCreate(
            patient_name=patient_name,
            patient_contact=patient_contact,
            patient_email=patient_email,
            emergency_name=emergency_name,
            emergency_email=emergency_email,
            emergency_contact=emergency_contact,
            medication_details=medication_details_dict,
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
            telegram_chat_id=telegram_chat_id,
        )
        
        logger.info("Calling create_patient service to save to database")
        result = await create_patient(patient_data)
        logger.info(f"✓ Patient created successfully with ID: {result.id}")
        logger.info(f"✓ Medication details saved: {len(medication_details_dict.get('medications', []))} medications")
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
