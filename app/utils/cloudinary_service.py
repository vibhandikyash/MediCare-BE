"""Cloudinary service for uploading files."""

import logging
import os
import cloudinary.uploader
from fastapi import UploadFile, HTTPException, status
from typing import Optional
import app.config.cloudinary  # Ensure Cloudinary is configured

logger = logging.getLogger(__name__)


async def upload_pdf_to_cloudinary(
    file: UploadFile,
    folder: Optional[str] = "medicare/patients",
    resource_type: str = "raw"
) -> str:
    """
    Upload a PDF file to Cloudinary and return the secure URL.
    
    Args:
        file: FastAPI UploadFile object
        folder: Cloudinary folder path for organization
        resource_type: Type of resource (raw for PDFs)
    
    Returns:
        str: Secure URL of the uploaded file
    
    Raises:
        HTTPException: If upload fails
    """
    try:
        logger.info(f"Starting Cloudinary upload for file: {file.filename}, folder: {folder}")
        
        # Validate file type
        if not file.filename or not file.filename.endswith('.pdf'):
            logger.warning(f"Invalid file type: {file.filename}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are allowed"
            )
        
        # Read file content
        logger.debug(f"Reading file content: {file.filename}")
        file_content = await file.read()
        file_size = len(file_content)
        logger.debug(f"File size: {file_size} bytes")
        
        # Upload to Cloudinary
        logger.info(f"Uploading to Cloudinary: {file.filename}")
        upload_result = cloudinary.uploader.upload(
            file_content,
            folder=folder,
            resource_type=resource_type,
            format="pdf",
            type="upload",  # Explicitly set upload type
            invalidate=True,  # Invalidate CDN cache
            use_filename=True,  # Use original filename
            unique_filename=True,  # Add unique suffix to avoid conflicts
        )
        
        # Log full upload result for debugging
        logger.debug(f"Upload result: {upload_result}")
        
        # Return secure URL - for raw files, use secure_url or url
        secure_url = upload_result.get("secure_url") or upload_result.get("url")
        if not secure_url:
            # Fallback: construct URL manually if not in response
            public_id = upload_result.get("public_id", "")
            cloud_name = upload_result.get("cloud_name") or os.getenv("CLOUDINARY_CLOUD_NAME")
            secure_url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/{public_id}.pdf"
        
        logger.info(f"File uploaded successfully: {secure_url}")
        logger.info(f"Public ID: {upload_result.get('public_id')}")
        logger.info(f"Resource type: {upload_result.get('resource_type')}")
        return secure_url
        
    except HTTPException:
        logger.error("HTTPException in upload_pdf_to_cloudinary", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error uploading file to Cloudinary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file to Cloudinary: {str(e)}"
        )


async def upload_multiple_pdfs_to_cloudinary(
    files: list[UploadFile],
    folder: Optional[str] = "medicare/patients",
    resource_type: str = "raw"
) -> list[str]:
    """
    Upload multiple PDF files to Cloudinary and return their secure URLs.
    
    Args:
        files: List of FastAPI UploadFile objects
        folder: Cloudinary folder path for organization
        resource_type: Type of resource (raw for PDFs)
    
    Returns:
        list[str]: List of secure URLs of the uploaded files
    
    Raises:
        HTTPException: If any upload fails
    """
    logger.info(f"Uploading {len(files)} files to Cloudinary")
    urls = []
    for idx, file in enumerate(files, 1):
        logger.debug(f"Uploading file {idx}/{len(files)}: {file.filename if file.filename else 'unnamed'}")
        url = await upload_pdf_to_cloudinary(file, folder, resource_type)
        urls.append(url)
    logger.info(f"Successfully uploaded {len(urls)} files")
    return urls

