"""
Pydantic schemas for request body validation in the search blueprint.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class SearchSchema(BaseSchema):
    """Body for searching entities across the project."""

    query: str = Field(..., description="Search query string")
    project_id: Optional[UUID] = None
    limit: int = Field(3, ge=1)
    offset: int = Field(0, ge=0)
    index_names: List[str] = Field(
        default=["assets", "shots", "persons"],
        description="List of index names to search",
    )
