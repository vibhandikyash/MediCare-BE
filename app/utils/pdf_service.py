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
            format="pdf"
        )
        pdf_url = upload_result.get("secure_url", upload_result.get("url"))
        logger.info(f"PDF uploaded: {pdf_url}")
        
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
