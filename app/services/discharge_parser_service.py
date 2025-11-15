"""Service for parsing discharge summaries using AI/LLM."""

import logging
import json
import os
import base64
import re
from typing import Optional
from datetime import datetime, date, timedelta
from fastapi import HTTPException, status
import httpx
from dotenv import load_dotenv
from app.schemas.medications import (
    DischargeSummaryParsed,
    MedicationDetail,
    DayEnum,
    FrequencyEnum,
    MedicationStatus,
    Reminder,
)
from app.schemas.patients import Followup, FollowupStatus
from app.utils.pdf_service import generate_action_plan_pdf

load_dotenv()
logger = logging.getLogger(__name__)


def convert_time_to_iso(time_str: str, date_obj: date) -> str:
    """
    Convert time string from formats like '10:00AM', '6:00PM' to ISO 8601 format 'YYYY-MM-DDTHH:mm:ssZ'.
    
    Args:
        time_str: Time string in formats like '10:00AM', '6:00PM', '10:00', etc.
        date_obj: Date object to combine with time
    
    Returns:
        ISO 8601 format datetime string (YYYY-MM-DDTHH:mm:ssZ) in 24-hour format
    """
    try:
        # Remove whitespace and convert to uppercase
        time_str = time_str.strip().upper()
        
        # Check if it's already in 24-hour format (contains no AM/PM)
        if 'AM' not in time_str and 'PM' not in time_str:
            # If it's already in HH:MM format, add seconds
            if ':' in time_str:
                parts = time_str.split(':')
                if len(parts) == 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    second = 0
                elif len(parts) == 3:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    second = int(parts[2])
                else:
                    hour = int(parts[0])
                    minute = 0
                    second = 0
            else:
                hour = int(time_str)
                minute = 0
                second = 0
        else:
            # Parse AM/PM format
            is_pm = 'PM' in time_str
            time_str = time_str.replace('AM', '').replace('PM', '').strip()
            
            # Split hours and minutes
            if ':' in time_str:
                parts = time_str.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
            else:
                # Just hour, no minutes
                hour = int(time_str)
                minute = 0
                second = 0
            
            # Convert to 24-hour format
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
        
        # Combine date and time into ISO 8601 format
        datetime_obj = datetime.combine(date_obj, datetime.min.time().replace(hour=hour, minute=minute, second=second))
        return datetime_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to convert time '{time_str}' to ISO format: {str(e)}")
        # Return default time with the provided date
        default_time = datetime.combine(date_obj, datetime.min.time().replace(hour=10, minute=0, second=0))
        return default_time.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_reminders(
    days: list[DayEnum],
    timing: list[str],
    frequency: FrequencyEnum,
    start_date: Optional[date],
    end_date: Optional[date],
    ) -> list[Reminder]:
    """
    Generate reminders for a medication based on days, timing, frequency, and date range.
    
    Args:
        days: List of days of the week
        timing: List of times (e.g., ["10:00AM", "6:00PM"])
        frequency: Frequency of medication
        start_date: Start date for medication (defaults to tomorrow if not provided)
        end_date: End date for medication (defaults to 30 days fromDefault start if not provided)
    
    Returns:
        List of Reminder objects with calculated dates
    """
    # Don't create reminders for "as_needed" medications
    if frequency == FrequencyEnum.AS_NEEDED:
        return []
    
    reminders = []
    
    # Determine start and end dates
    today = datetime.now().date()
    if start_date is None:
        start_date = today + timedelta(days=1)  #  to tomorrow
    
    if end_date is None:
        end_date = start_date + timedelta(days=30)  # Default to 30 days from start
    
    # Ensure we have at least one time
    if not timing:
        # Default time will be converted to ISO 8601 format when creating reminders
        timing = ["10:00AM"]  # Default time (will be converted to ISO 8601 format with date)
    
    # Determine which days to use
    days_to_use = []
    if days:
        # Use specified days
        days_to_use = days
    elif frequency == FrequencyEnum.DAILY:
        # Daily means all days
        days_to_use = list(DayEnum)
    elif frequency == FrequencyEnum.TWICE_A_WEEK:
        # Twice a week - use start_date day and 3 days later
        start_day_index = start_date.weekday()  # 0=Monday, 6=Sunday
        days_to_use = [
            DayEnum(list(DayEnum)[start_day_index]),
            DayEnum(list(DayEnum)[(start_day_index + 3) % 7])
        ]
    elif frequency == FrequencyEnum.WEEKLY:
        # Weekly - use start_date day
        start_day_index = start_date.weekday()
        days_to_use = [DayEnum(list(DayEnum)[start_day_index])]
    elif frequency == FrequencyEnum.ALTERNATE_DAYS:
        # Alternate days - use all days but skip one
        days_to_use = [DayEnum.MONDAY, DayEnum.WEDNESDAY, DayEnum.FRIDAY, DayEnum.SUNDAY]
    else:
        # For custom, use all days if no specific days provided
        days_to_use = list(DayEnum)
    
    # Generate reminders for each day and time combination
    current_date = start_date
    
    # Generate reminders for the date range
    while current_date <= end_date:
        current_day_index = current_date.weekday()  # 0=Monday, 6=Sunday
        current_day_enum = DayEnum(list(DayEnum)[current_day_index])
        
        # Check if this day is in our days_to_use list
        if current_day_enum in days_to_use:
            # Create a reminder for each time on this day
            for time_str in timing:
                # Convert time to ISO 8601 format (YYYY-MM-DDTHH:mm:ssZ)
                time_iso = convert_time_to_iso(time_str, current_date)
                reminder = Reminder(
                    day=current_day_enum,
                    datte=current_date,
                    time=time_iso,
                    isreminded=False,
                    isresponded=False,
                )
                reminders.append(reminder)
        
        # Move to next day
        current_date += timedelta(days=1)
    
    return reminders


def get_discharge_summary_parsing_prompt() -> str:
    """Generate the parsing prompt with current date context."""
    today = datetime.now()
    today_name = today.strftime("%A").lower()
    tomorrow = today + timedelta(days=1)
    tomorrow_name = tomorrow.strftime("%A").lower()
    tomorrow_date = tomorrow.strftime("%Y-%m-%d")
    
    return f"""
You are a medical document parser specialized in extracting medication information from discharge summaries.

Your task is to parse the provided discharge summary and extract ALL medication information in a structured format.

IMPORTANT CONTEXT:
- Today is {today_name.capitalize()}
- Starting from tomorrow ({tomorrow_name.capitalize()}, {tomorrow_date}), the patient's medications should begin
- When determining start dates or scheduling medications, use {tomorrow_name.capitalize()} ({tomorrow_date}) as the starting point unless the document specifies otherwise

Only Focus on discharge medications suggested by the doctor.
CRITICAL RULES:
- ONLY include medications that are PRESCRIBED or RECOMMENDED to be TAKEN
- DO NOT include medications that are explicitly told to be STOPPED, AVOIDED, or DISCONTINUED should not be included in the result.

For each medication, extract:
1. **name**: Full medication name
2. **dosage**: Dosage amount and unit (e.g., "500mg", "10ml", "2 tablets")
3. **start_date**: When to start the medication (format: YYYY-MM-DD, or null if not specified)
4. **end_date**: When to stop the medication (format: YYYY-MM-DD, or null if not specified)
5. **timing**: Array of specific times when medication should be taken (e.g., "10:00AM", "6:00PM", "8:00AM"). 
   - If "twice daily" or "two times a day" is mentioned, use ["10:00AM", "6:00PM"]
   - If "daily" or no specific time is mentioned, use ["10:00AM"] as default
   - If specific times are mentioned in the document, extract those exact times
   - Note: Times will be automatically converted to ISO format (HH:MM:SS) in 24-hour format
6. **days**: Array of specific days if applicable. Options: "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
   - For "daily" frequency: consider all days of the week starting from today 
   - For "twice_a_week" or "weekly": consider days of the week starting from today according to the frequency
7. **frequency**: How often to take. Options: "daily", "alternate_days", "twice_a_week", "weekly", "as_needed", "custom"
8. **status**: Current status. Options: "active", "stopped", "completed"

Also extract:
- **patient_name**: Patient's full name
- **discharge_date**: Date of discharge (format: YYYY-MM-DD)
- **diagnosis**: Primary diagnosis or condition
- **additional_notes**: Any other relevant information, including warnings about medications to avoid

**action_plan**: The action plan text. Note that don't make up any instructions. Only use the information that is provided in the document.
            CRITICAL REQUIREMENTS:
            1. Create a well-structured markdown document (NOT HTML)
            2. Include a prominent title "Post-Discharge Action Plan" as a level 1 heading (# Post-Discharge Action Plan)
            3. Expand and detail the action plan with:
            - Clear step-by-step instructions for what the patient should do next
            - Specific actions they need to take (e.g., "Take medication X at 10 AM daily")
            - Timeline or schedule information (e.g., "For the next 7 days", "Starting tomorrow")
            - Important warnings or precautions
            - When to seek medical attention or emergency care
            - Follow-up actions and reminders
            - Any lifestyle modifications or restrictions
            4. Format the content using proper markdown syntax:
            - Use ## for major sections (e.g., "## Immediate Actions", "## Daily Care Instructions", "## Warning Signs", "## Follow-up Appointments")
            - Use ### for subsections
            - Use numbered lists (1., 2., 3.) for step-by-step instructions
            - Use bullet points (- or *) for general information or reminders
            - Use regular paragraphs for descriptive text (separated by blank lines)
            - Use **bold** or *italic* for emphasis on critical information
            - Use --- for horizontal rules to separate major sections if needed
            5. Structure the document with clear sections:
            - Immediate Actions (what to do right away)
            - Daily Care Instructions (ongoing care)
            - Medication Schedule (if applicable)
            - Activity Guidelines (what they can/cannot do)
            - Warning Signs (when to seek help)
            - Follow-up Information
            6. Use clean, readable markdown formatting that is easy to convert to PDF
            7. Preserve ALL important information from the original text and expand on it with actionable details
            8. Add specific, actionable next steps even if not explicitly mentioned in the original text (infer from context)
            9. DO NOT use HTML tags - use ONLY markdown syntax

- **appointment_followup**: Array of appointment followup dates. Extract any mentioned follow-up appointments, check-ups, or review dates.
  For each followup appointment, extract:
  - **reason**: Reason for the followup appointment
  - **notes**: Any other relevant information about the followup appointment
  - **followup_date**: Date of the followup appointment (format: YYYY-MM-DD)
  - **isreminder1sent**: Always set to false (default)
  - **isreminder2sent**: Always set to false (default)
  - **status**: Always set to "not_confirmed" (default)

IMPORTANT: Return ONLY a valid JSON object with this exact structure:
{{
    "medications": [
        {{
            "name": "string",
            "dosage": "string",
            "start_date": "YYYY-MM-DD or null",
            "end_date": "YYYY-MM-DD or null",
            "timing": ["10:00AM", "6:00PM"],
            "days": [],
            "frequency": "daily",
            "status": "active",
        }}
    ],
    "diagnosis": "string or null",
    "additional_notes": "string or null",
    "action_plan": "string or null",
    "appointment_followup": [
        {{
            "reason": "string",
            "notes": "string",
            "followup_date": "YYYY-MM-DD",
            "isreminder1sent": false,
            "isreminder2sent": false,
            "status": "not_confirmed"
        }}
    ]
    
}}

Do not include any explanations, markdown formatting, or additional text. Return ONLY the JSON object.
"""


def robust_json_parse(text: str) -> dict:
    """
    Robustly parse JSON from LLM response, handling various edge cases.
    
    Args:
        text: Raw text response from LLM that may contain JSON
        
    Returns:
        Parsed JSON dictionary
        
    Raises:
        HTTPException: If JSON cannot be parsed after all attempts
    """
    original_text = text
    
    # Strategy 1: Remove markdown code blocks (multiple patterns)
    # Handle ```json ... ```, ``` ... ```, ```JSON ... ```
    text = re.sub(r'^```(?:json|JSON)?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()
    
    # Strategy 2: Extract JSON object from text (find first { ... })
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        text = json_match.group(0)
    
    # Strategy 3: Remove common JSON-invalid characters
    # Remove trailing commas before closing braces/brackets
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    
    # Strategy 4: Remove single-line comments (// ...)
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    
    # Strategy 5: Remove multi-line comments (/* ... */)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    
    # Strategy 6: Fix common escape issues
    # Ensure proper escaping of quotes within strings
    # This is tricky, so we'll try parsing first
    
    # Try parsing with cleaned text
    attempts = [
        ("Cleaned text", text),
        ("Original text", original_text),
        ("Text with trailing comma fix", re.sub(r',(\s*[}\]])', r'\1', original_text)),
    ]
    
    for attempt_name, attempt_text in attempts:
        try:
            # Try direct JSON parsing
            parsed = json.loads(attempt_text)
            logger.info(f"Successfully parsed JSON using: {attempt_name}")
            return parsed
        except json.JSONDecodeError as e:
            logger.debug(f"JSON parse attempt '{attempt_name}' failed: {str(e)}")
            continue
    
    # Strategy 7: Try to fix common issues and parse again
    try:
        # Use the cleaned text from earlier
        attempt_text = text
        
        # Remove any text before first {
        first_brace = attempt_text.find('{')
        if first_brace > 0:
            attempt_text = attempt_text[first_brace:]
        
        # Remove any text after last }
        last_brace = attempt_text.rfind('}')
        if last_brace > 0 and last_brace < len(attempt_text) - 1:
            attempt_text = attempt_text[:last_brace + 1]
        
        # Fix trailing commas
        attempt_text = re.sub(r',(\s*[}\]])', r'\1', attempt_text)
        
        parsed = json.loads(attempt_text)
        logger.info("Successfully parsed JSON after aggressive cleaning")
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Strategy 8: Try using json5-like fixes (if available) or manual fixes
    # This is more aggressive and should only be used as last resort
    try:
        # Use the cleaned text from earlier
        attempt_text = text
        
        # Remove any text before first {
        first_brace = attempt_text.find('{')
        if first_brace > 0:
            attempt_text = attempt_text[first_brace:]
        
        # Remove any text after last }
        last_brace = attempt_text.rfind('}')
        if last_brace > 0 and last_brace < len(attempt_text) - 1:
            attempt_text = attempt_text[:last_brace + 1]
        
        # Fix single quotes to double quotes (but preserve escaped quotes)
        # Only replace single quotes that appear to be string delimiters
        attempt_text = re.sub(r"'([^']*)'", r'"\1"', attempt_text)
        
        # Fix trailing commas again
        attempt_text = re.sub(r',(\s*[}\]])', r'\1', attempt_text)
        
        parsed = json.loads(attempt_text)
        logger.info("Successfully parsed JSON after quote fixes")
        return parsed
    except json.JSONDecodeError:
        pass
    
    # If all strategies fail, log the error and raise exception
    logger.error(f"Failed to parse JSON after all attempts")
    logger.error(f"Original text length: {len(original_text)}")
    logger.error(f"Original text preview (first 500 chars): {original_text[:500]}")
    logger.error(f"Cleaned text preview (first 500 chars): {text[:500]}")
    
    # Try to provide helpful error message
    try:
        # One last attempt: try to find and show the JSON error location
        json.loads(text)
    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing failed: {str(e)}"
        if hasattr(e, 'pos') and e.pos:
            start = max(0, e.pos - 50)
            end = min(len(text), e.pos + 50)
            error_msg += f"\nError near position {e.pos}: ...{text[start:end]}..."
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI returned invalid JSON that could not be parsed. {error_msg}"
        )
    
    # Fallback (shouldn't reach here)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="AI returned invalid JSON that could not be parsed after multiple attempts"
    )


async def parse_discharge_summary_with_vision(image_bytes_list: list[bytes], model: str = "google/gemini-2.5-pro") -> DischargeSummaryParsed:
    """
    Parse discharge summary using vision model (image-based parsing only).
    """
    try:
        logger.info(f"Initializing vision model for parsing {len(image_bytes_list)} images")
        
        # Get API key from environment
        api_key = os.getenv("OPEN_ROUTER_API_KEY")
        if not api_key:
            # Try reloading .env file
            load_dotenv(override=True)
            api_key = os.getenv("OPEN_ROUTER_API_KEY")
        
        if not api_key:
            logger.error("OPEN_ROUTER_API_KEY environment variable is not set")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPEN_ROUTER_API_KEY environment variable is not set. Please check your .env file."
            )
        
        # Strip whitespace from API key
        api_key = api_key.strip()
        # Prepare message content with images
        prompt = get_discharge_summary_parsing_prompt()
        content = [
            {
                "type": "text",
                "text": prompt + "\n\nAnalyze the following discharge summary images:"
            }
        ]
        
        # Add all images as base64 encoded data URLs
        for img_bytes in image_bytes_list:
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            data_url = f"data:image/png;base64,{base64_image}"
            content.append({
                "type": "image_url",
                "image_url": {"url": data_url}
            })
        
        # Prepare request payload
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a medical document parser."
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.getenv("SITE_URL", "https://medicare-app.com"),  # Optional
            "X-Title": os.getenv("SITE_NAME", "MediCare Discharge Summary Parser"),  # Optional
            "Content-Type": "application/json"
        }
        
        logger.info(f"Using OpenRouter API with model: {model}")
        logger.info("Sending images to vision model for parsing")
        
        # Make async HTTP request to OpenRouter
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
        
        logger.info(f"Vision model response received: {len(response_text)} characters")
        logger.debug(f"Response preview: {response_text[:200]}...")
        
        # Parse JSON response using robust parser
        try:
            parsed_json = robust_json_parse(response_text)
            logger.info("Successfully parsed AI response to JSON")
        except HTTPException:
            # Re-raise HTTP exceptions from robust_json_parse
            raise
        except Exception as e:
            logger.error(f"Unexpected error during JSON parsing: {str(e)}")
            logger.error(f"Response text: {response_text[:500]}...")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse AI response: {str(e)}"
            )
        
        # Convert JSON to Pydantic model
        try:
            medications = []
            for med_data in parsed_json.get("medications", []):
                start_date = None
                if med_data.get("start_date"):
                    try:
                        start_date = datetime.strptime(med_data["start_date"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass
                
                end_date = None
                if med_data.get("end_date"):
                    try:
                        end_date = datetime.strptime(med_data["end_date"], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass
                
                # Parse frequency first (needed for timing defaults)
                frequency = FrequencyEnum.DAILY
                if med_data.get("frequency"):
                    try:
                        frequency = FrequencyEnum(med_data["frequency"].lower())
                    except ValueError:
                        pass
                
                # Parse timing - accept time strings directly (keep as time strings, not full ISO datetime)
                timing = []
                timing_data = med_data.get("timing", [])
                
                if timing_data:
                    # If AI provided timing, keep as time strings (e.g., "10:00AM", "6:00PM")
                    # These will be converted to full ISO 8601 format when creating reminders
                    for t in timing_data:
                        if t and isinstance(t, str):
                            timing.append(t.strip())
                
                # If no timing provided, apply defaults based on frequency or instructions
                if not timing:
                    # Check frequency field
                    frequency_str = med_data.get("frequency", "").lower() if isinstance(med_data.get("frequency"), str) else ""
                    
                    # Check medication name and dosage for "twice daily" indicators
                    name_str = (med_data.get("name") or "").lower()
                    dosage_str = (med_data.get("dosage") or "").lower()
                    combined_text = f"{name_str} {dosage_str} {frequency_str}".lower()
                    
                
                days = []
                for d in med_data.get("days", []):
                    try:
                        days.append(DayEnum(d.lower()))
                    except ValueError:
                        pass
                
                status_val = MedicationStatus.ACTIVE
                if med_data.get("status"):
                    try:
                        status_val = MedicationStatus(med_data["status"].lower())
                    except ValueError:
                        pass
                
                # Generate reminders for this medication
                reminders = generate_reminders(
                    days=days,
                    timing=timing,
                    frequency=frequency,
                    start_date=start_date,
                    end_date=end_date,
                )
                
                medication = MedicationDetail(
                    name=med_data.get("name") or "Unknown",
                    dosage=med_data.get("dosage") or "Not specified",
                    start_date=start_date,
                    end_date=end_date,
                    timing=timing,
                    days=days,
                    frequency=frequency,
                    status=status_val,
                    reminders=reminders,
                )
                medications.append(medication)
            
            # Process discharge date
            discharge_date = None
            if parsed_json.get("discharge_date"):
                try:
                    discharge_date = datetime.strptime(parsed_json["discharge_date"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    logger.warning(f"Invalid discharge_date format: {parsed_json.get('discharge_date')}")
            
            # Process appointment followups
            appointment_followups = []
            followup_data_list = parsed_json.get("appointment_followup", [])
            for followup_data in followup_data_list:
                try:
                    followup_date = None
                    if followup_data.get("followup_date"):
                        try:
                            followup_date = datetime.strptime(followup_data["followup_date"], "%Y-%m-%d").date()
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid followup_date format: {followup_data.get('followup_date')}")
                            continue
                    
                    if followup_date is None:
                        continue
                    
                    # Parse status
                    status_val = FollowupStatus.NOT_CONFIRMED
                    if followup_data.get("status"):
                        try:
                            status_val = FollowupStatus(followup_data["status"].lower())
                        except ValueError:
                            pass
                    
                    followup = Followup(
                        followup_date=followup_date,
                        reason=followup_data.get("reason"),
                        notes=followup_data.get("notes"),
                        isreminder1sent=followup_data.get("isreminder1sent", False),
                        isreminder2sent=followup_data.get("isreminder2sent", False),
                        status=status_val,
                    )
                    appointment_followups.append(followup)
                except Exception as e:
                    logger.warning(f"Error parsing followup: {str(e)}")
                    continue
            
            # Generate action plan PDF if action_plan exists
            action_plan_pdf_url = None
            action_plan_text = parsed_json.get("action_plan")
            if action_plan_text:
                try:
                    patient_name_for_pdf = parsed_json.get("patient_name") or "Unknown_Patient"
                    logger.info("Generating action plan PDF...")
                    action_plan_pdf_url = await generate_action_plan_pdf(action_plan_text, patient_name_for_pdf)
                    if action_plan_pdf_url:
                        logger.info(f"Action plan PDF generated and uploaded: {action_plan_pdf_url}")
                except Exception as e:
                    logger.warning(f"Failed to generate action plan PDF: {str(e)}")
                    # Continue without PDF URL if generation fails
            
            # Create final parsed result
            result = DischargeSummaryParsed(
                medications=medications,
                patient_name=parsed_json.get("patient_name"),
                discharge_date=discharge_date,
                diagnosis=parsed_json.get("diagnosis"),
                additional_notes=parsed_json.get("additional_notes"),
                action_plan=action_plan_text,
                action_plan_pdf_url=action_plan_pdf_url,
                appointment_followup=appointment_followups,
            )
            
            logger.info(f"Successfully parsed discharge summary with {len(result.medications)} medications and {len(result.appointment_followup)} appointment followups")
            return result
            
        except Exception as e:
            logger.error(f"Error converting parsed data to Pydantic model: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to structure parsed data: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing discharge summary with vision: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse discharge summary with vision: {str(e)}"
        )
