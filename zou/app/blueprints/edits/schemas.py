"""
Pydantic schemas for request body validation in the edits blueprint.
"""

from typing import Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class NewEditSchema(BaseSchema):
    """Body for creating a new edit."""

    name: str = Field(..., min_length=1, description="The edit name")
    description: Optional[str] = ""
    data: Optional[dict] = None
    episode_id: Optional[UUID] = None
