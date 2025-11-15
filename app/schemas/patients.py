"""Patient schemas for request/response validation."""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, EmailStr
from enum import Enum

class FollowupStatus(str, Enum):
    """Followup status for appointments."""
    CONFIRMED = "confirmed"
    NOT_CONFIRMED = "not_confirmed"

class Followup(BaseModel):
    """Followup tracking for appointments."""
    
    followup_date: date = Field(..., description="Followup date in ISO format")
    isreminder1sent: bool = Field(default=False, description="Whether first reminder has been sent")
    isreminder2sent: bool = Field(default=False, description="Whether second reminder has been sent")
    status: FollowupStatus = Field(default=FollowupStatus.NOT_CONFIRMED, description="Followup status: confirmed or not_confirmed")

class PatientBase(BaseModel):
    """Base patient schema with common fields."""

    patient_name: str = Field(..., min_length=1, max_length=200, description="Patient's full name")
    patient_contact: str = Field(..., min_length=10, max_length=10, description="10-digit patient contact number")
    patient_email: EmailStr = Field(..., description="Patient's email")
    emergency_name: str = Field(..., min_length=1, max_length=200, description="Emergency contact name")
    emergency_email: EmailStr = Field(..., description="Emergency contact email")
    emergency_contact: str = Field(..., min_length=10, max_length=10, description="10-digit emergency contact number")
    medication_details: Dict[str, Any] = Field(..., description="Medication details as JSONB")
    admission_date: date = Field(..., description="Date of patient admission")
    discharge_date: Optional[date] = Field(None, description="Date of patient discharge")
    medical_condition: str = Field(..., min_length=1, max_length=500, description="Patient's medical condition summary")
    assigned_doctor: str = Field(..., min_length=1, max_length=200, description="Doctor assigned to the patient")
    age: int = Field(..., ge=0, le=130, description="Patient age in years")
    gender: str = Field(..., min_length=1, max_length=50, description="Patient gender")
    bill_details: List[Any] = Field(default_factory=list, description="Array of bill details as JSONB")
    reports: List[Any] = Field(default_factory=list, description="Array of reports as JSONB")
    doctor_notes: str = Field(default="", description="Doctor's notes as String")
    doctor_medical_certificate: str = Field(default="", description="Doctor's medical certificate file path or URL")
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="Array of conversation messages as JSONB")
    conversation_summary: str = Field(default="", description="Summary of the conversation")
    appointment_followup: List[Followup] = Field(default_factory=list, description="List of appointment followups")
    telegram_chat_id: Optional[float] = Field(None, description="Telegram chat ID")
    
    @field_validator("patient_contact", "emergency_contact")
    @classmethod
    def validate_numeric_string(cls, v: str, info) -> str:
        """Validate that the string contains only digits."""
        if not v.isdigit():
            raise ValueError(f"{info.field_name} must contain only digits")
        return v


class PatientCreate(PatientBase):
    """Schema for creating a new patient."""


class PatientUpdate(BaseModel):
    """Schema for updating a patient."""

    patient_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Patient's full name")
    patient_contact: Optional[str] = Field(None, min_length=10, max_length=10, description="10-digit patient contact number")
    patient_email: Optional[EmailStr] = Field(None, description="Patient's email")
    emergency_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Emergency contact name")
    emergency_email: Optional[EmailStr] = Field(None, description="Emergency contact email")
    emergency_contact: Optional[str] = Field(None, min_length=10, max_length=10, description="10-digit emergency contact number")
    medication_details: Optional[Dict[str, Any]] = Field(None, description="Medication details as JSONB")
    admission_date: Optional[date] = Field(None, description="Date of patient admission")
    discharge_date: Optional[date] = Field(None, description="Date of patient discharge")
    medical_condition: Optional[str] = Field(None, min_length=1, max_length=500, description="Patient's medical condition summary")
    assigned_doctor: Optional[str] = Field(None, min_length=1, max_length=200, description="Doctor assigned to the patient")
    age: Optional[int] = Field(None, ge=0, le=130, description="Patient age in years")
    gender: Optional[str] = Field(None, min_length=1, max_length=50, description="Patient gender")
    bill_details: Optional[List[Any]] = Field(None, description="Array of bill details as JSONB")
    reports: Optional[List[Any]] = Field(None, description="Array of reports as JSONB")
    doctor_notes: str = Field(default="", description="Doctor's notes as String")
    doctor_medical_certificate: Optional[str] = Field(None, description="Doctor's medical certificate file path or URL")
    messages: Optional[List[Dict[str, Any]]] = Field(None, description="Array of conversation messages as JSONB")
    conversation_summary: Optional[str] = Field(None, description="Summary of the conversation")
    appointment_followup: Optional[List[Followup]] = Field(None, description="List of appointment followups")
    telegram_chat_id: Optional[float] = Field(None, description="Telegram chat ID")

    @field_validator("patient_contact", "emergency_contact")
    @classmethod
    def validate_contact_numbers(cls, v: Optional[str], info) -> Optional[str]:
        """Validate contact numbers if provided."""
        if v is not None and not v.isdigit():
            raise ValueError(f"{info.field_name} must contain only digits")
        return v


class PatientResponse(PatientBase):
    """Schema for patient response."""

    id: str = Field(..., alias="_id", description="Supabase UUID")
    created_at: Optional[datetime] = Field(None, description="Timestamp when patient was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when patient was last updated")

    class Config:
        """Pydantic config."""
        populate_by_name = True
        json_encoders = {
            str: str
        }
