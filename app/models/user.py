"""This file contains the user model for the application."""

from typing import Optional
from pydantic import Field, EmailStr
import bcrypt

from app.models.base import BaseModel


class User(BaseModel):
    """User model for storing user accounts.

    Attributes:
        id: MongoDB ObjectId as string
        email: User's email (unique)
        hashed_password: Bcrypt hashed password
        created_at: When the user was created
    """

    id: Optional[str] = Field(default=None, alias="_id")
    email: EmailStr = Field(..., index=True)
    hashed_password: str

    def verify_password(self, password: str) -> bool:
        """Verify if the provided password matches the hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
