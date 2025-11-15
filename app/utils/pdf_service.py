"""PDF processing service for converting PDFs to images for AI processing."""

import io
import logging
from typing import List, Tuple
from fastapi import UploadFile, HTTPException, status
import fitz

logger = logging.getLogger(__name__)

async def convert_pdf_bytes_to_images(pdf_bytes: bytes) -> List[bytes]:
    """
    Convert PDF bytes to a list of images (one per page) using PyMuPDF.
    
    Args:
        pdf_bytes: PDF file content as bytes
    
    Returns:
        List[bytes]: List of image bytes in PNG format (one per page)
    """
    try:
        # Open PDF document from bytes
        logger.info("Opening PDF with PyMuPDF")
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        image_bytes_list = []
        
        # Process each page
        logger.info(f"Processing {len(pdf_document)} page(s)")
        for page_num in range(len(pdf_document)):
            logger.debug(f"Processing page {page_num + 1}/{len(pdf_document)}")
            page = pdf_document[page_num]
            
            zoom = 2.5  # 2.0 = 144 DPI, 2.5 = 180 DPI, 3.0 = 216 DPI
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert pixmap to PNG bytes
            img_bytes = pix.tobytes("png")
            image_bytes_list.append(img_bytes)
        
        # Close the PDF document
        pdf_document.close()
        
        logger.info(f"Successfully converted PDF to {len(image_bytes_list)} image(s)")
        
        return image_bytes_list
        
    except Exception as e:
        logger.error(f"Error converting PDF bytes to images: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to convert PDF to images: {str(e)}"
        )


async def convert_pdf_to_images(pdf_file: UploadFile) -> List[bytes]:
    """
    Convert a PDF file to a list of images (one per page) using PyMuPDF.
    
    This function converts a PDF file to a list of images (one per page) using PyMuPDF.
    The images are returned as bytes in PNG format.
    """
    try:
        # Read PDF bytes
        logger.info(f"Reading PDF file: {pdf_file.filename}")
        pdf_bytes = await pdf_file.read()
        
        # Reset file pointer for potential reuse
        await pdf_file.seek(0)
        
        return await convert_pdf_bytes_to_images(pdf_bytes)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error converting PDF to images: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to convert PDF to images: {str(e)}"
        )


async def process_pdf_discharge_summary(pdf_file: UploadFile, patient_name: str) -> Tuple[str, List[bytes]]:
    """
    Complete workflow: Read PDF bytes, upload to Cloudinary, convert to images (for AI processing only).
    """
    try:
        import cloudinary.uploader
        
        # Read PDF bytes first (before any operations consume the stream)
        logger.info(f"Processing discharge summary PDF for patient: {patient_name}")
        logger.info(f"Reading PDF file: {pdf_file.filename}")
        pdf_bytes = await pdf_file.read()
        logger.info(f"PDF file read: {len(pdf_bytes)} bytes")
        
        # Reset file pointer for potential reuse
        await pdf_file.seek(0)
        
        # Upload PDF bytes to Cloudinary
        folder_name = patient_name.replace(' ', '_')
        folder = f"medicare/patients/{folder_name}/discharge_summaries"
        
        logger.info(f"Uploading PDF to Cloudinary folder: {folder}")
        upload_result = cloudinary.uploader.upload(
            pdf_bytes,
            folder=folder,
            resource_type="raw",
            format="pdf",
            type="upload",  # Explicitly set upload type
            invalidate=True,  # Invalidate CDN cache
            use_filename=True,  # Use original filename
            unique_filename=True,  # Add unique suffix to avoid conflicts
        )
        
        # Log full upload result for debugging
        logger.debug(f"Upload result: {upload_result}")
        
        # Get secure URL - for raw files, use secure_url or url
        pdf_url = upload_result.get("secure_url") or upload_result.get("url")
        if not pdf_url:
            # Fallback: construct URL manually if not in response
            import os
            public_id = upload_result.get("public_id", "")
            cloud_name = upload_result.get("cloud_name") or os.getenv("CLOUDINARY_CLOUD_NAME")
            pdf_url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}.pdf"
        
        logger.info(f"PDF uploaded: {pdf_url}")
        logger.info(f"Public ID: {upload_result.get('public_id')}")
        logger.info(f"Resource type: {upload_result.get('resource_type')}")
        
        # Convert PDF bytes to images (using the bytes we already read)
        logger.info("Converting PDF to images...")
        image_bytes_list = await convert_pdf_bytes_to_images(pdf_bytes)
        
        logger.info(f"Discharge summary processing complete: PDF uploaded, {len(image_bytes_list)} image(s) ready for AI processing")
        return pdf_url, image_bytes_list
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF discharge summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process discharge summary: {str(e)}"
        )


async def process_pdf_report(pdf_file: UploadFile, patient_name: str) -> Tuple[str, List[bytes]]:
    """
    Complete workflow: Read PDF bytes, upload to Cloudinary, convert to images (for AI processing only).
    Similar to process_pdf_discharge_summary but for medical reports.
    """
    try:
        import cloudinary.uploader
        
        # Read PDF bytes first (before any operations consume the stream)
        logger.info(f"Processing report PDF for patient: {patient_name}")
        logger.info(f"Reading PDF file: {pdf_file.filename}")
        pdf_bytes = await pdf_file.read()
        logger.info(f"PDF file read: {len(pdf_bytes)} bytes")
        
        # Reset file pointer for potential reuse
        await pdf_file.seek(0)
        
        # Upload PDF bytes to Cloudinary
        folder_name = patient_name.replace(' ', '_')
        folder = f"medicare/patients/{folder_name}/reports"
        
        logger.info(f"Uploading PDF to Cloudinary folder: {folder}")
        upload_result = cloudinary.uploader.upload(
            pdf_bytes,
            folder=folder,
            resource_type="raw",
            format="pdf",
            type="upload",  # Explicitly set upload type
            invalidate=True,  # Invalidate CDN cache
            use_filename=True,  # Use original filename
            unique_filename=True,  # Add unique suffix to avoid conflicts
        )
        
        # Log full upload result for debugging
        logger.debug(f"Upload result: {upload_result}")
        
        # Get secure URL - for raw files, use secure_url or url
        pdf_url = upload_result.get("secure_url") or upload_result.get("url")
        if not pdf_url:
            # Fallback: construct URL manually if not in response
            import os
            public_id = upload_result.get("public_id", "")
            cloud_name = upload_result.get("cloud_name") or os.getenv("CLOUDINARY_CLOUD_NAME")
            pdf_url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}.pdf"
        
        logger.info(f"PDF uploaded: {pdf_url}")
        logger.info(f"Public ID: {upload_result.get('public_id')}")
        logger.info(f"Resource type: {upload_result.get('resource_type')}")
        
        # Convert PDF bytes to images (using the bytes we already read)
        logger.info("Converting PDF to images...")
        image_bytes_list = await convert_pdf_bytes_to_images(pdf_bytes)
        
        logger.info(f"Report processing complete: PDF uploaded, {len(image_bytes_list)} image(s) ready for AI processing")
        return pdf_url, image_bytes_list
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF report: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process report: {str(e)}"
        )


async def process_pdf_bill(pdf_file: UploadFile, patient_name: str) -> Tuple[str, List[bytes]]:
    """
    Complete workflow: Read PDF bytes, upload to Cloudinary, convert to images (for AI processing only).
    Similar to process_pdf_report but for medical bills.
    """
    try:
        import cloudinary.uploader
        
        # Read PDF bytes first (before any operations consume the stream)
        logger.info(f"Processing bill PDF for patient: {patient_name}")
        logger.info(f"Reading PDF file: {pdf_file.filename}")
        pdf_bytes = await pdf_file.read()
        logger.info(f"PDF file read: {len(pdf_bytes)} bytes")
        
        # Reset file pointer for potential reuse
        await pdf_file.seek(0)
        
        # Upload PDF bytes to Cloudinary
        folder_name = patient_name.replace(' ', '_')
        folder = f"medicare/patients/{folder_name}/bills"
        
        logger.info(f"Uploading PDF to Cloudinary folder: {folder}")
        upload_result = cloudinary.uploader.upload(
            pdf_bytes,
            folder=folder,
            resource_type="raw",
            format="pdf",
            type="upload",  # Explicitly set upload type
            invalidate=True,  # Invalidate CDN cache
            use_filename=True,  # Use original filename
            unique_filename=True,  # Add unique suffix to avoid conflicts
        )
        
        # Log full upload result for debugging
        logger.debug(f"Upload result: {upload_result}")
        
        # Get secure URL - for raw files, use secure_url or url
        pdf_url = upload_result.get("secure_url") or upload_result.get("url")
        if not pdf_url:
            # Fallback: construct URL manually if not in response
            import os
            public_id = upload_result.get("public_id", "")
            cloud_name = upload_result.get("cloud_name") or os.getenv("CLOUDINARY_CLOUD_NAME")
            pdf_url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}.pdf"
        
        logger.info(f"PDF uploaded: {pdf_url}")
        logger.info(f"Public ID: {upload_result.get('public_id')}")
        logger.info(f"Resource type: {upload_result.get('resource_type')}")
        
        # Convert PDF bytes to images (using the bytes we already read)
        logger.info("Converting PDF to images...")
        image_bytes_list = await convert_pdf_bytes_to_images(pdf_bytes)
        
        logger.info(f"Bill processing complete: PDF uploaded, {len(image_bytes_list)} image(s) ready for AI processing")
        return pdf_url, image_bytes_list
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF bill: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process bill: {str(e)}"
        )