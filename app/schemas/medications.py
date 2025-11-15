"""Medication schemas for discharge summary parsing."""

from __future__ import annotations
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from app.schemas.patients import Followup


class TimingEnum(str, Enum):
    """Medication timing options."""
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class DayEnum(str, Enum):
    """Days of the week."""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class FrequencyEnum(str, Enum):
    """Medication frequency options."""
    DAILY = "daily"
    ALTERNATE_DAYS = "alternate_days"
    TWICE_A_WEEK = "twice_a_week"
    WEEKLY = "weekly"
    AS_NEEDED = "as_needed"
    CUSTOM = "custom"


class MedicationStatus(str, Enum):
    """Medication status."""
    ACTIVE = "active"
    STOPPED = "stopped"
    COMPLETED = "completed"


class Reminder(BaseModel):
    """Reminder for medication intake."""
    
    day: DayEnum = Field(..., description="Day of the week")
    datte: date = Field(..., description="Actual date for this reminder")
    time: str = Field(..., description="Time to take medication (e.g., '10:00AM', '6:00PM')")
    isreminded: bool = Field(default=False, description="Whether reminder has been sent")
    isresponded: bool = Field(default=False, description="Whether patient has responded to reminder")


class MedicationDetail(BaseModel):
    """Detailed medication information extracted from discharge summary."""
    
    name: str = Field(..., description="Medication name")
    dosage: str = Field(..., description="Medication dosage (e.g., 500mg, 10ml)")
    start_date: Optional[date] = Field(None, description="Medication start date")
    end_date: Optional[date] = Field(None, description="Medication end date")
    timing: List[str] = Field(default_factory=list, description="Specific times to take medication (e.g., '10:00AM', '6:00PM')")
    days: List[DayEnum] = Field(default_factory=list, description="Specific days of the week (if applicable)")
    frequency: FrequencyEnum = Field(FrequencyEnum.DAILY, description="Frequency of medication")
    status: MedicationStatus = Field(MedicationStatus.ACTIVE, description="Current status of medication")
    reminders: List[Reminder] = Field(default_factory=list, description="List of reminders for this medication")
    
class DischargeSummaryParsed(BaseModel):
    """Parsed data from discharge summary."""
    
    medications: List[MedicationDetail] = Field(default_factory=list, description="List of medications")
    patient_name: Optional[str] = Field(None, description="Patient name from discharge summary")
    discharge_date: Optional[date] = Field(None, description="Discharge date from summary")
    diagnosis: Optional[str] = Field(None, description="Diagnosis from discharge summary")
    additional_notes: Optional[str] = Field(None, description="Any additional relevant notes")
    appointment_followup: List[Followup] = Field(default_factory=list, description="List of appointment followups")


class DischargeSummaryUploadResponse(BaseModel):
    """Response after uploading and parsing discharge summary."""
    
    pdf_url: str = Field(..., description="Cloudinary URL of the uploaded PDF")
    image_urls: List[str] = Field(default_factory=list, description="URLs of converted PDF pages as images")
    parsed_data: DischargeSummaryParsed = Field(..., description="Parsed medication and patient data")
    raw_text: Optional[str] = Field(None, description="Extracted text from the document")

