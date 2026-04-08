"""
Pydantic schemas for request/response validation in the persons blueprint.

Use these schemas to ensure incoming JSON bodies match the expected format
and to return clear validation errors (e.g. 400 with field-level messages).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from zou.app.utils import date_helpers
from zou.app.utils.validation import BaseSchema


def _parse_datetime(v):
    """Parse date string (YYYY-MM-DD or ISO datetime) to datetime."""
    if v is None or isinstance(v, datetime):
        return v
    try:
        return date_helpers.get_datetime_from_string(v)
    except Exception:
        try:
            return date_helpers.get_date_from_string(v)
        except Exception:
            raise ValueError(
                "Wrong date format. Expected: 2020-01-05T13:23:10 or 2020-01-05"
            )


class DesktopLoginCreateSchema(BaseSchema):
    """Body for creating a desktop login log. Date is optional (default: now)."""

    date: Optional[datetime] = None

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v):
        return _parse_datetime(v) if v else v


class AddToDepartmentSchema(BaseSchema):
    """Body for adding a person to a department."""

    department_id: UUID = Field(
        ..., description="Department unique identifier"
    )


class ChangePasswordSchema(BaseSchema):
    """Body for changing a person's password (admin)."""

    password: str = Field(..., min_length=1, description="New password")
    password_2: str = Field(
        ..., min_length=1, description="Password confirmation"
    )

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_2:
            raise ValueError("Confirmation password doesn't match.")
        return self
