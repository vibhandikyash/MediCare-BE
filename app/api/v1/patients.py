"""Patient API routes."""

import logging
import json
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, status, Form, File, UploadFile, HTTPException
from app.schemas.patients import PatientCreate, PatientResponse
from app.services.patient_service import create_patient, get_all_patients
from app.utils.cloudinary_service import upload_pdf_to_cloudinary, upload_multiple_pdfs_to_cloudinary
from app.utils.pdf_service import process_pdf_discharge_summary, process_pdf_report, process_pdf_bill
from app.services.discharge_parser_service import parse_discharge_summary_with_vision
from app.services.report_parser_service import parse_report_with_vision
from app.services.bill_parser_service import parse_bill_with_vision
from app.services.justification_service import generate_insurer_justification_document
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
        parsed_data = None
        
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
                    "diagnosis": parsed_data.diagnosis,
                    "additional_notes": parsed_data.additional_notes,
                    "action_plan": parsed_data.action_plan,
                    "action_plan_pdf_url": parsed_data.action_plan_pdf_url
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
        
        # Process bill details PDFs - parse each bill
        bills_list = []
        if bill_details:
            logger.info(f"=== BILL PROCESSING STARTED ===")
            logger.info(f"Processing {len(bill_details)} bill PDF(s)")
            
            for idx, bill_file in enumerate(bill_details):
                try:
                    logger.info(f"Processing bill {idx + 1}/{len(bill_details)}: {bill_file.filename}")
                    
                    # Validate file type
                    if not bill_file.filename or not bill_file.filename.lower().endswith('.pdf'):
                        logger.warning(f"Skipping non-PDF file: {bill_file.filename}")
                        continue
                    
                    # Step 1: Process PDF: upload PDF, convert to images (for AI processing)
                    logger.info(f"Step 1: Uploading bill PDF and converting to images...")
                    bill_url, image_bytes_list = await process_pdf_bill(
                        bill_file,
                        patient_name
                    )
                    
                    logger.info(f"✓ Bill PDF uploaded to: {bill_url}")
                    logger.info(f"✓ Converted PDF to {len(image_bytes_list)} image(s) for AI processing")
                    
                    # Step 2: Parse bill with AI vision model
                    logger.info(f"Step 2: Parsing bill with AI vision model...")
                    parsed_bill = await parse_bill_with_vision(
                        image_bytes_list=image_bytes_list
                    )
                    
                    logger.info(f"✓ Parsed bill: {parsed_bill.name} with {len(parsed_bill.details)} items, total: {parsed_bill.total}")
                    
                    # Step 3: Structure bill data
                    logger.info(f"Step 3: Structuring bill data...")
                    details_list = []
                    for detail in parsed_bill.details:
                        details_list.append({
                            "name": detail.name,
                            "cost": detail.cost
                        })
                    
                    bill_dict = {
                        "url": bill_url,
                        "name": parsed_bill.name,
                        "details": details_list,
                        "total": parsed_bill.total
                    }
                    bills_list.append(bill_dict)
                    logger.info(f"✓ Successfully structured bill: {parsed_bill.name}")
                    
                except HTTPException:
                    logger.error(f"HTTPException during bill {idx + 1} processing", exc_info=True)
                    # Continue with other bills even if one fails
                    continue
                except Exception as e:
                    logger.error(f"Error processing bill {idx + 1} ({bill_file.filename}): {str(e)}", exc_info=True)
                    # Continue with other bills even if one fails
                    continue
            
            logger.info(f"=== BILL PROCESSING COMPLETED ===")
            logger.info(f"Successfully processed {len(bills_list)} out of {len(bill_details)} bill(s)")
        
        # Process reports PDFs - parse each report
        reports_list = []
        if reports:
            logger.info(f"=== REPORT PROCESSING STARTED ===")
            logger.info(f"Processing {len(reports)} report PDF(s)")
            
            # Get medications and diagnosis for context
            medications_list = medication_details_dict.get("medications", [])
            diagnosis = medication_details_dict.get("diagnosis")
            
            for idx, report_file in enumerate(reports):
                try:
                    logger.info(f"Processing report {idx + 1}/{len(reports)}: {report_file.filename}")
                    
                    # Validate file type
                    if not report_file.filename or not report_file.filename.lower().endswith('.pdf'):
                        logger.warning(f"Skipping non-PDF file: {report_file.filename}")
                        continue
                    
                    # Step 1: Process PDF: upload PDF, convert to images (for AI processing)
                    logger.info(f"Step 1: Uploading report PDF and converting to images...")
                    report_url, image_bytes_list = await process_pdf_report(
                        report_file,
                        patient_name
                    )
                    
                    logger.info(f"✓ Report PDF uploaded to: {report_url}")
                    logger.info(f"✓ Converted PDF to {len(image_bytes_list)} image(s) for AI processing")
                    
                    # Step 2: Parse report with AI vision model
                    logger.info(f"Step 2: Parsing report with AI vision model...")
                    parsed_report = await parse_report_with_vision(
                        image_bytes_list=image_bytes_list,
                        medications=medications_list,
                        diagnosis=diagnosis
                    )
                    
                    logger.info(f"✓ Parsed report: {parsed_report.name} with {len(parsed_report.biomarkers)} biomarkers")
                    
                    # Step 3: Structure report data
                    logger.info(f"Step 3: Structuring report data...")
                    biomarkers_list = []
                    for biomarker in parsed_report.biomarkers:
                        biomarkers_list.append({
                            "name": biomarker.name,
                            "range": biomarker.range,
                            "value": biomarker.value
                        })
                    
                    report_dict = {
                        "url": report_url,
                        "name": parsed_report.name,
                        "reason": parsed_report.reason,
                        "biomarkers": biomarkers_list
                    }
                    reports_list.append(report_dict)
                    logger.info(f"✓ Successfully structured report: {parsed_report.name}")
                    
                except HTTPException:
                    logger.error(f"HTTPException during report {idx + 1} processing", exc_info=True)
                    # Continue with other reports even if one fails
                    continue
                except Exception as e:
                    logger.error(f"Error processing report {idx + 1} ({report_file.filename}): {str(e)}", exc_info=True)
                    # Continue with other reports even if one fails
                    continue
            
            logger.info(f"=== REPORT PROCESSING COMPLETED ===")
            logger.info(f"Successfully processed {len(reports_list)} out of {len(reports)} report(s)")
        
        # Upload medical certificate PDF if provided
        medical_certificate_url = ""
        if doctor_medical_certificate:
            logger.info(f"Uploading medical certificate PDF: {doctor_medical_certificate.filename}")
            medical_certificate_url = await upload_pdf_to_cloudinary(
                doctor_medical_certificate,
                folder=f"medicare/patients/{patient_name.replace(' ', '_')}/certificates"
            )
            logger.info(f"Medical certificate uploaded successfully: {medical_certificate_url}")
        
        # Extract appointment followups from parsed discharge summary if available
        appointment_followups = []
        if parsed_data:
            appointment_followups = parsed_data.appointment_followup
            logger.info(f"Extracted {len(appointment_followups)} appointment followups from discharge summary")
        
        # Generate insurer justification document
        justification_pdf_url = None
        try:
            logger.info("=== GENERATING INSURER JUSTIFICATION DOCUMENT ===")
            discharge_date_str = discharge_date.strftime("%Y-%m-%d") if discharge_date else None
            admission_date_str = admission_date.strftime("%Y-%m-%d")
            
            justification_pdf_url = await generate_insurer_justification_document(
                patient_name=patient_name,
                medical_condition=medical_condition,
                admission_date=admission_date_str,
                discharge_date=discharge_date_str,
                age=age,
                gender=gender,
                assigned_doctor=assigned_doctor,
                medication_details=medication_details_dict,
                bill_details=bills_list,
                reports=reports_list,
                doctor_notes=doctor_notes,
            )
            
            if justification_pdf_url:
                logger.info(f"✓ Insurer justification document generated: {justification_pdf_url}")
            else:
                logger.warning("⚠ Insurer justification document generation returned None (continuing anyway)")
        except Exception as e:
            logger.error(f"Error generating insurer justification document: {str(e)}", exc_info=True)
            logger.warning("⚠ Continuing with patient creation despite justification document generation failure")
            # Don't fail the whole process if justification generation fails
            justification_pdf_url = None
        
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
            bill_details=bills_list,
            reports=reports_list,
            doctor_notes=doctor_notes,
            doctor_medical_certificate=medical_certificate_url,
            appointment_followup=appointment_followups,
            telegram_chat_id=telegram_chat_id,
            insurer_justification_pdf_url=justification_pdf_url,
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
