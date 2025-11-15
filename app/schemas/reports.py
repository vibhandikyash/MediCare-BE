"""Report schemas for medical report parsing."""

from typing import List, Optional
from pydantic import BaseModel, Field


class Biomarker(BaseModel):
    """Biomarker information from medical report."""
    
    name: str = Field(..., description="Biomarker name (e.g., 'Hemoglobin', 'Glucose', 'Cholesterol')")
    range: str = Field(..., description="Normal range for the biomarker (e.g., '12-16 g/dL', '70-100 mg/dL')")
    value: str = Field(..., description="Actual measured value (e.g., '14.5 g/dL', '95 mg/dL')")

class ReportParsed(BaseModel):
    """Parsed data from medical report."""
    
    name: str = Field(..., description="Report name (e.g., 'Complete Blood Count', 'Lipid Profile', 'Liver Function Test')")
    reason: str = Field(..., description="Reason for this test based on medications and diagnosis")
    biomarkers: List[Biomarker] = Field(default_factory=list, description="List of biomarkers with their values and ranges")

