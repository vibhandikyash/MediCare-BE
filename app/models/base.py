"""Base models and common imports for all models."""

from datetime import datetime, UTC
from typing import Optional, Dict, Any
from pydantic import BaseModel as PydanticBaseModel, Field


class BaseModel(PydanticBaseModel):
    """Base model with common fields for MongoDB documents."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Config:
        """Pydantic config."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        populate_by_name = True

    def to_mongo(self) -> Dict[str, Any]:
        """Convert model to MongoDB document."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return data

    @classmethod
    def from_mongo(cls, data: Dict[str, Any]):
        """Create model instance from MongoDB document."""
        if not data:
            return None
        return cls(**data)
