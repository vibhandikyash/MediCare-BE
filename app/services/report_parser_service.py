"""Service for parsing medical reports using AI/LLM."""

import logging
import json
import os
import base64
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
import httpx
from dotenv import load_dotenv
from app.schemas.reports import ReportParsed, Biomarker

load_dotenv()
logger = logging.getLogger(__name__)


def get_report_parsing_prompt(medications: List[Dict[str, Any]], diagnosis: Optional[str] = None) -> str:
    """Generate the parsing prompt with medications and diagnosis context."""
    
    # Build context from medications - only extract relevant medication names
    medication_names = []
    if medications:
        for med in medications:
            if isinstance(med, dict) and med.get("name"):
                medication_names.append(med["name"])
    
    medications_context = ", ".join(medication_names) if medication_names else "None"
    diagnosis_context = diagnosis if diagnosis else "Not specified"
    
    return f"""
You are a medical report parser specialized in extracting structured information from medical test reports.

CONTEXT INFORMATION:
- Patient's current medications: {medications_context}
- Patient's diagnosis: {diagnosis_context}

Your task is to parse the provided medical report and extract:
1. **Report name**: The type of test/report (e.g., "Complete Blood Count", "Lipid Profile", "Liver Function Test", "Blood Glucose Test", "HbA1c Test")
2. **Biomarkers**: All biomarkers/test parameters found in the report with their:
   - **name**: Full biomarker name (e.g., "Hemoglobin", "Total Cholesterol", "Glucose", "ALT")
   - **range**: Normal/reference range (e.g., "12-16 g/dL", "70-100 mg/dL", "<200 mg/dL")
   - **value**: Actual measured value from the report (e.g., "14.5 g/dL", "95 mg/dL", "180 mg/dL")
3. **Reason**: A concise reason for this test based on the patient's medications and diagnosis. 
   - Only mention relevant medications that relate to this specific test
   - Only mention relevant diagnosis that relates to this specific test
   - Keep it brief and specific (1-2 sentences maximum)
   - If no clear connection, state "Routine monitoring" or "Diagnostic test"

IMPORTANT RULES:
- Extract ALL biomarkers from the report, not just abnormal ones
- For each biomarker, ensure you capture the exact value and range as shown in the report
- The reason should be specific to this test type and relevant to the patient's medications/diagnosis
- Do NOT include all medications - only those relevant to this specific test
- Do NOT include the full diagnosis if not relevant - only mention what's necessary

IMPORTANT: Return ONLY a valid JSON object with this exact structure:
{{
    "name": "string (report/test name)",
    "reason": "string (brief reason based on relevant medications/diagnosis)",
    "biomarkers": [
        {{
            "name": "string (biomarker name)",
            "range": "string (normal range)",
            "value": "string (measured value)"
        }}
    ]
}}

Do not include any explanations, markdown formatting, or additional text. Return ONLY the JSON object.
"""

async def parse_report_with_vision(image_bytes_list: list[bytes], medications: List[Dict[str, Any]] = None, diagnosis: Optional[str] = None, model: str = "google/gemini-2.5-pro") -> ReportParsed:
    try:
        logger.info(f"Initializing vision model for parsing {len(image_bytes_list)} report images")
        
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
        
        # Strip whitespace from API key
        api_key = api_key.strip()
        
        # Prepare medications list (handle None case)
        meds_list = medications if medications else []
        
        # Prepare message content with images
        prompt = get_report_parsing_prompt(medications=meds_list, diagnosis=diagnosis)
        content = [
            {
                "type": "text",
                "text": prompt + "\n\nAnalyze the following medical report images:"
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
                    "content": "You are a medical report parser."
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
            "HTTP-Referer": os.getenv("SITE_URL", "https://medicare-app.com"),
            "X-Title": os.getenv("SITE_NAME", "MediCare Report Parser"),
            "Content-Type": "application/json"
        }
        
        logger.info(f"Using OpenRouter API with model: {model}")
        logger.info("Sending report images to vision model for parsing")
        
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
            biomarkers = []
            for biomarker_data in parsed_json.get("biomarkers", []):
                biomarker = Biomarker(
                    name=biomarker_data.get("name") or "Unknown",
                    range=biomarker_data.get("range") or "Not specified",
                    value=biomarker_data.get("value") or "Not specified"
                )
                biomarkers.append(biomarker)
            
            # Create final parsed result
            result = ReportParsed(
                name=parsed_json.get("name") or "Medical Report",
                reason=parsed_json.get("reason") or "Routine monitoring",
                biomarkers=biomarkers
            )
            
            logger.info(f"Successfully parsed report: {result.name} with {len(result.biomarkers)} biomarkers")
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
        logger.error(f"Error parsing report with vision: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse report with vision: {str(e)}"
        )

