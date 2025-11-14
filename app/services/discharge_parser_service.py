"""Service for parsing discharge summaries using AI/LLM."""

import logging
import json
import os
import base64
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

load_dotenv()
logger = logging.getLogger(__name__)


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
        timing = ["10:00AM"]  # Default time
    
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
                reminder = Reminder(
                    day=current_day_enum,
                    datte=current_date,
                    time=time_str,
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
    "patient_name": "string or null",
    "discharge_date": "YYYY-MM-DD or null",
    "diagnosis": "string or null",
    "additional_notes": "string or null"
}}

Do not include any explanations, markdown formatting, or additional text. Return ONLY the JSON object.
"""

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
        
        # Parse JSON response
        try:
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            parsed_json = json.loads(response_text)
            logger.info("Successfully parsed AI response to JSON")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {str(e)}")
            logger.error(f"Response text: {response_text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI returned invalid JSON: {str(e)}"
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
                
                # Parse timing - accept time strings directly
                timing = []
                timing_data = med_data.get("timing", [])
                
                if timing_data:
                    # If AI provided timing, use it (should be time strings like "10:00AM")
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
                    
                    # Check if it's "twice daily" or similar patterns
                    
                
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
            
            # Create final parsed result
            result = DischargeSummaryParsed(
                medications=medications,
                patient_name=parsed_json.get("patient_name"),
                discharge_date=discharge_date,
                diagnosis=parsed_json.get("diagnosis"),
                additional_notes=parsed_json.get("additional_notes"),
            )
            
            logger.info(f"Successfully parsed discharge summary with {len(result.medications)} medications")
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
