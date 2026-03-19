"""
Pydantic schemas for request body validation in the concepts blueprint.
"""

from typing import List, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class NewConceptSchema(BaseSchema):
    """Body for creating a new concept."""

    name: str = Field(..., min_length=1, description="The concept name")
    data: Optional[dict] = None
    description: Optional[str] = None
    entity_concept_links: List[dict] = Field(default=[])
