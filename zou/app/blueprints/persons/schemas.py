"""
Pydantic schemas for request/response validation in the persons blueprint.

Use these schemas to ensure incoming JSON bodies match the expected format
and to return clear validation errors (e.g. 400 with field-level messages).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _parse_datetime(v):
    """Parse date string (YYYY-MM-DD or ISO datetime) to datetime."""
    if v is None or isinstance(v, datetime):
        return v
    from zou.app.utils import date_helpers
    try:
        return date_helpers.get_datetime_from_string(v)
    except Exception:
        try:
            return date_helpers.get_date_from_string(v)
        except Exception:
            raise ValueError(
                "Wrong date format. Expected: 2020-01-05T13:23:10 or 2020-01-05"
            )


class DesktopLoginCreateSchema(BaseModel):
    """Body for creating a desktop login log. Date is optional (default: now)."""
    date: Optional[datetime] = None

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v):
        return _parse_datetime(v) if v else v


class AddToDepartmentSchema(BaseModel):
    """Body for adding a person to a department."""
    department_id: UUID = Field(..., description="Department unique identifier")

    @field_validator("department_id", mode="before")
    @classmethod
    def ensure_uuid(cls, v):
        if isinstance(v, str):
            from zou.app.utils.fields import is_valid_id
            if not is_valid_id(v):
                raise ValueError("department_id must be a valid UUID")
            return v
        return v


class ChangePasswordSchema(BaseModel):
    """Body for changing a person's password (admin)."""
    password: str = Field(..., min_length=1, description="New password")
    password_2: str = Field(..., min_length=1, description="Password confirmation")

    @field_validator("password_2")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and info.data["password"] != v:
            raise ValueError("Confirmation password doesn't match.")
        return v
