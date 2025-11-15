"""Service for generating insurer justification documents using AI/LLM."""

import logging
import json
import os
import re
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status
import httpx
from dotenv import load_dotenv
from app.utils.pdf_service import convert_markdown_to_pdf

load_dotenv()
logger = logging.getLogger(__name__)


def parse_currency_to_float(value: Any) -> float:
    """
    Robustly parse currency values to float.
    
    Handles various formats:
    - '$2,180' -> 2180.0
    - '$1,234.56' -> 1234.56
    - '2,180' -> 2180.0
    - '1234.56' -> 1234.56
    - 1234.56 -> 1234.56
    - '-$500' -> -500.0
    
    Args:
        value: Currency value (str, int, or float)
        
    Returns:
        float: Parsed numeric value, or 0.0 if parsing fails
    """
    if value is None:
        return 0.0
    
    # If already a number, return it
    if isinstance(value, (int, float)):
        return float(value)
    
    # If not a string, try to convert
    if not isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    # Clean the string: remove whitespace, dollar signs, and other currency symbols
    cleaned = value.strip()
    
    # Remove currency symbols ($, €, £, etc.)
    cleaned = re.sub(r'[$€£¥₹]', '', cleaned)
    
    # Remove commas (thousands separators)
    cleaned = cleaned.replace(',', '')
    
    # Try to parse as float
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        logger.warning(f"Could not parse currency value: {value}, defaulting to 0.0")
        return 0.0


def get_justification_document_prompt(
    patient_name: str,
    medical_condition: str,
    admission_date: str,
    discharge_date: Optional[str],
    age: int,
    gender: str,
    assigned_doctor: str,
    medication_details: Dict[str, Any],
    bill_details: List[Dict[str, Any]],
    reports: List[Dict[str, Any]],
    doctor_notes: str,
) -> str:
    """Generate the justification document prompt with patient context."""
    
    # Format medication details
    medications_text = ""
    if medication_details and medication_details.get("medications"):
        medications_list = []
        for med in medication_details.get("medications", []):
            med_text = f"- {med.get('name', 'Unknown')} ({med.get('dosage', 'N/A')})"
            if med.get('frequency'):
                med_text += f" - Frequency: {med.get('frequency')}"
            medications_list.append(med_text)
        medications_text = "\n".join(medications_list) if medications_list else "None specified"
    else:
        medications_text = "None specified"
    
    # Format bill details
    bills_text = ""
    if bill_details:
        bills_list = []
        total_cost = 0
        for bill in bill_details:
            bill_name = bill.get("name", "Unknown Bill")
            bill_total = bill.get("total", 0)
            # Use robust currency parser to handle formats like '$2,180'
            total_cost += parse_currency_to_float(bill_total)
            details = bill.get("details", [])
            details_text = "\n    ".join([f"- {d.get('name', 'N/A')}: ${d.get('cost', '0')}" for d in details])
            bills_list.append(f"  **{bill_name}**\n    Total: ${bill_total}\n    Items:\n    {details_text}")
        bills_text = "\n\n".join(bills_list) if bills_list else "No bills provided"
        bills_text += f"\n\n**Total Medical Costs: ${total_cost:.2f}**"
    else:
        bills_text = "No bills provided"
    
    # Format reports
    reports_text = ""
    if reports:
        reports_list = []
        for report in reports:
            report_name = report.get("name", "Unknown Report")
            reason = report.get("reason", "Not specified")
            biomarkers = report.get("biomarkers", [])
            biomarkers_text = "\n    ".join([
                f"- {b.get('name', 'N/A')}: {b.get('value', 'N/A')} (Range: {b.get('range', 'N/A')})"
                for b in biomarkers
            ])
            reports_list.append(f"  **{report_name}**\n    Reason: {reason}\n    Results:\n    {biomarkers_text}")
        reports_text = "\n\n".join(reports_list) if reports_list else "No reports provided"
    else:
        reports_text = "No reports provided"
    
    discharge_date_text = discharge_date if discharge_date else "Not yet discharged"
    
    return f"""
You are a medical documentation specialist tasked with creating a comprehensive justification document for insurance claims.

Your task is to create a clear, professional, and detailed justification document that explains why all medical treatments, procedures, medications, and services were medically necessary for the patient.

**PATIENT INFORMATION:**
- Name: {patient_name}
- Age: {age}
- Gender: {gender}
- Medical Condition: {medical_condition}
- Assigned Doctor: {assigned_doctor}
- Admission Date: {admission_date}
- Discharge Date: {discharge_date_text}

**MEDICATIONS PRESCRIBED:**
{medications_text}

**MEDICAL BILLS AND COSTS:**
{bills_text}

**MEDICAL REPORTS AND TEST RESULTS:**
{reports_text}

**DOCTOR'S NOTES:**
{doctor_notes if doctor_notes else "No additional notes provided"}

**YOUR TASK:**
Create a comprehensive justification document in markdown format that:

1. **Executive Summary**: Brief overview of the patient's condition and treatment necessity
2. **Medical Condition Details**: Explain the patient's medical condition in clear terms
3. **Treatment Justification**: For each major treatment/procedure/service:
   - Explain what was done
   - Why it was medically necessary
   - How it relates to the patient's condition
   - Clinical rationale
4. **Medication Justification**: For each medication or medication category:
   - Explain why it was prescribed
   - How it addresses the medical condition
   - Medical necessity
5. **Diagnostic Tests Justification**: For each test/report:
   - Explain why the test was necessary
   - How results informed treatment decisions
   - Clinical significance
6. **Cost Justification**: Explain why the costs were reasonable and necessary:
   - Break down major cost items
   - Explain medical necessity for each
   - Reference standard medical practices
7. **Conclusion**: Summary reinforcing medical necessity

**IMPORTANT REQUIREMENTS:**
- Use clear, professional language that insurance reviewers can understand
- Avoid overly technical jargon, but include necessary medical terms with brief explanations
- Be specific and detailed - vague justifications lead to claim denials
- Reference the patient's specific condition, age, and circumstances
- Connect each treatment/service to the medical condition
- Use markdown formatting:
  - Use # for main title: "# Insurance Claim Justification Document"
  - Use ## for major sections
  - Use ### for subsections
  - Use **bold** for emphasis
  - Use bullet points (-) and numbered lists (1., 2., 3.) where appropriate
  - Use paragraphs for detailed explanations
- Make the document comprehensive but concise
- Focus on medical necessity and clinical rationale
- Do NOT make up information - only use what is provided

**OUTPUT FORMAT:**
Return ONLY the markdown document. Do not include any explanations, code blocks, or additional text outside the markdown content.
Start directly with the title: "# Insurance Claim Justification Document"
"""


async def generate_insurer_justification_document(
    patient_name: str,
    medical_condition: str,
    admission_date: str,
    discharge_date: Optional[str],
    age: int,
    gender: str,
    assigned_doctor: str,
    medication_details: Dict[str, Any],
    bill_details: List[Dict[str, Any]],
    reports: List[Dict[str, Any]],
    doctor_notes: str,
    model: str = "anthropic/claude-3.5-sonnet",
) -> Optional[str]:
    """
    Generate an insurer justification document using a separate LLM.
    
    Args:
        patient_name: Patient's name
        medical_condition: Patient's medical condition
        admission_date: Admission date (string format)
        discharge_date: Discharge date (string format or None)
        age: Patient age
        gender: Patient gender
        assigned_doctor: Assigned doctor name
        medication_details: Medication details dictionary
        bill_details: List of bill details
        reports: List of report details
        doctor_notes: Doctor's notes
        model: LLM model to use (default: claude-3.5-sonnet for better reasoning)
    
    Returns:
        str: Cloudinary URL of the generated PDF, or None if generation fails
    """
    try:
        logger.info(f"Generating insurer justification document for patient: {patient_name}")
        
        # Get API key from environment
        api_key = os.getenv("OPEN_ROUTER_API_KEY")
        if not api_key:
            load_dotenv(override=True)
            api_key = os.getenv("OPEN_ROUTER_API_KEY")
        
        if not api_key:
            logger.error("OPEN_ROUTER_API_KEY environment variable is not set")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPEN_ROUTER_API_KEY environment variable is not set. Please check your .env file."
            )
        
        api_key = api_key.strip()
        
        # Generate prompt
        prompt = get_justification_document_prompt(
            patient_name=patient_name,
            medical_condition=medical_condition,
            admission_date=admission_date,
            discharge_date=discharge_date,
            age=age,
            gender=gender,
            assigned_doctor=assigned_doctor,
            medication_details=medication_details,
            bill_details=bill_details,
            reports=reports,
            doctor_notes=doctor_notes,
        )
        
        # Prepare request payload
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a medical documentation specialist who creates clear, comprehensive justification documents for insurance claims. Your documents help reduce claim denials by providing detailed medical necessity explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # Lower temperature for more consistent, factual output
        }
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.getenv("SITE_URL", "https://medicare-app.com"),
            "X-Title": os.getenv("SITE_NAME", "MediCare Justification Document Generator"),
            "Content-Type": "application/json"
        }
        
        logger.info(f"Using OpenRouter API with model: {model}")
        logger.info("Sending request to generate justification document")
        
        # Make async HTTP request to OpenRouter
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:  # Longer timeout for complex documents
                response = await client.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                response_data = response.json()
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("error", {}).get("message", str(e))
            except:
                error_detail = str(e)
            logger.error(f"OpenRouter API HTTP error: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"OpenRouter API error: {error_detail}"
            )
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter API HTTP error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to connect to OpenRouter API: {str(e)}"
            )
        
        # Extract response text
        try:
            response_text = response_data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            logger.error(f"Invalid response format from OpenRouter: {response_data}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response format from OpenRouter API"
            )
        
        logger.info(f"LLM response received: {len(response_text)} characters")
        logger.debug(f"Response preview: {response_text[:200]}...")
        
        # Clean up markdown if it's wrapped in code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("markdown"):
                response_text = response_text[7:]
            response_text = response_text.strip()
        
        # Generate PDF from markdown
        logger.info("Converting markdown to PDF...")
        try:
            pdf_url = await convert_markdown_to_pdf(response_text, patient_name, "justifications")
            if pdf_url:
                logger.info(f"Insurer justification PDF generated and uploaded: {pdf_url}")
                return pdf_url
            else:
                logger.warning("PDF generation returned None")
                return None
        except Exception as e:
            logger.error(f"Failed to generate PDF from markdown: {str(e)}", exc_info=True)
            # Don't fail the whole process if PDF generation fails
            return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating insurer justification document: {str(e)}", exc_info=True)
        # Don't fail patient creation if justification generation fails
        logger.warning("Continuing with patient creation despite justification document generation failure")
        return None

