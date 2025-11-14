"""This file contains the thread model for the application."""

from datetime import UTC, datetime
from typing import Optional
from pydantic import Field

from app.models.base import BaseModel


class Thread(BaseModel):
    """Thread model for storing conversation threads.

    Attributes:
        id: MongoDB ObjectId as string
        created_at: When the thread was created
    """

    id: Optional[str] = Field(default=None, alias="_id")
