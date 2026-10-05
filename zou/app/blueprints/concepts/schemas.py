"""
Pydantic schemas for request body validation in the concepts blueprint.
"""

from typing import Annotated, List, Optional

from pydantic import AfterValidator, Field

from zou.app.utils import fields
from zou.app.utils.validation import BaseSchema


def _check_id(value):
    if not fields.is_valid_id(value):
        raise ValueError("must be a valid UUID")
    return value


IdStr = Annotated[str, AfterValidator(_check_id)]


class NewConceptSchema(BaseSchema):
    """
    Body for creating a new concept.
    """

    name: str = Field(..., min_length=1, description="The concept name")
    data: Optional[dict] = None
    description: Optional[str] = None
    entity_concept_links: List[dict] = Field(default=[])
    parent_id: Optional[IdStr] = Field(
        default=None, description="The concept folder to create it in"
    )


class ConceptFolderSchema(BaseSchema):
    """
    Body for creating or renaming a concept folder.
    """

    name: str = Field(
        ..., min_length=1, max_length=160, description="The folder name"
    )


class MoveConceptsSchema(BaseSchema):
    """
    Body for moving concepts to a concept folder, or back to the root of the
    project when no folder is named.
    """

    concept_ids: List[IdStr] = Field(..., description="The concepts to move")
    concept_folder_id: Optional[IdStr] = Field(
        default=None, description="The folder to move them to"
    )
