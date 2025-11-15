"""Bill schemas for medical bill parsing."""

from typing import List
from pydantic import BaseModel, Field


class BillDetail(BaseModel):
    """Individual bill item detail."""
    
    name: str = Field(..., description="Item/service name (e.g., 'Room Charges', 'Medication', 'Lab Test')")
    cost: str = Field(..., description="Cost of the item (e.g., '5000', '1500.50', '₹2000')")


class BillParsed(BaseModel):
    """Parsed data from medical bill."""
    
    name: str = Field(..., description="Bill name/type (e.g., 'Hospital Bill', 'Pharmacy Bill', 'Lab Charges Bill')")
    details: List[BillDetail] = Field(default_factory=list, description="List of bill items with their costs")
    total: str = Field(..., description="Total bill amount (e.g., '25000', '₹50000', '15000.75')")

