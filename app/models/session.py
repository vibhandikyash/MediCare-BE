"""This file contains the session model for the application."""

from typing import Optional
from pydantic import Field

from app.models.base import BaseModel


class Session(BaseModel):
    """Session model for storing chat sessions.

    Attributes:
        id: MongoDB ObjectId as string
        user_id: Reference to the user's ObjectId
        name: Name of the session (defaults to empty string)
        created_at: When the session was created
    """

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    name: str = Field(default="")
