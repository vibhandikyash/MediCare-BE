"""Service for parsing medical bills using AI/LLM."""

import logging
import json
import os
import base64
from typing import List
from fastapi import HTTPException, status
import httpx
from dotenv import load_dotenv
from app.schemas.bills import BillParsed, BillDetail

load_dotenv()
logger = logging.getLogger(__name__)


def get_bill_parsing_prompt() -> str:
    """Generate the parsing prompt for bill extraction."""
    
    return """
You are a medical bill parser specialized in extracting structured information from medical bills and invoices.

Your task is to parse the provided medical bill and extract:
1. **Bill name**: The type of bill (e.g., "Hospital Bill", "Pharmacy Bill", "Lab Charges Bill", "Consultation Bill", "Surgery Bill")
2. **Details**: All bill items/services with their costs. For each item extract:
   - **name**: Item/service name (e.g., "Room Charges", "Medication - Aspirin", "Blood Test", "Doctor Consultation")
   - **cost**: Cost of the item (preserve the format from the bill, e.g., "5000", "1500.50", "₹2000", "$100")
3. **Total**: The total bill amount (preserve the format from the bill, e.g., "25000", "₹50000", "$1500.75")

IMPORTANT RULES:
- Extract ALL bill items from the document, not just major ones
- For each item, capture the exact name as shown in the bill
- Preserve the cost format exactly as shown (including currency symbols, decimals, etc.)
- The total should match the final total shown on the bill
- If the bill has subtotals or tax breakdowns, include them as separate items if they are listed
- Group related items if they are listed together (e.g., "Medication - Aspirin 500mg" not just "Aspirin")

IMPORTANT: Return ONLY a valid JSON object with this exact structure:
{{
    "name": "string (bill name/type)",
    "details": [
        {{
            "name": "string (item/service name)",
            "cost": "string (cost amount)"
        }}
    ],
    "total": "string (total bill amount)"
}}

Do not include any explanations, markdown formatting, or additional text. Return ONLY the JSON object.
"""

async def parse_bill_with_vision(
    image_bytes_list: list[bytes],
    model: str = "google/gemini-2.5-pro"
) -> BillParsed:
    """
    Parse medical bill using vision model (image-based parsing only).
    
    Args:
        image_bytes_list: List of image bytes from PDF pages
        model: AI model to use for parsing
    
    Returns:
        BillParsed object with extracted bill information
    """
    try:
        logger.info(f"Initializing vision model for parsing {len(image_bytes_list)} bill images")
        
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
        
        # Prepare message content with images
        prompt = get_bill_parsing_prompt()
        content = [
            {
                "type": "text",
                "text": prompt + "\n\nAnalyze the following medical bill images:"
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
                    "content": "You are a medical bill parser."
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
            "X-Title": os.getenv("SITE_NAME", "MediCare Bill Parser"),
            "Content-Type": "application/json"
        }
        
        logger.info(f"Using OpenRouter API with model: {model}")
        logger.info("Sending bill images to vision model for parsing")
        
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
            details = []
            for detail_data in parsed_json.get("details", []):
                bill_detail = BillDetail(
                    name=detail_data.get("name") or "Unknown",
                    cost=detail_data.get("cost") or "0"
                )
                details.append(bill_detail)
            
            # Create final parsed result
            result = BillParsed(
                name=parsed_json.get("name") or "Medical Bill",
                details=details,
                total=parsed_json.get("total") or "0"
            )
            
            logger.info(f"Successfully parsed bill: {result.name} with {len(result.details)} items, total: {result.total}")
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
        logger.error(f"Error parsing bill with vision: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse bill with vision: {str(e)}"
        )

