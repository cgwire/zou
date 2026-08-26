"""
Pydantic schemas for request body validation in the breakdown blueprint.
"""

from typing import Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class AddAssetInstanceSchema(BaseSchema):
    """
    Body for adding an asset instance to a shot.
    """

    asset_instance_id: UUID = Field(
        ..., description="Asset instance unique identifier"
    )


class AddSceneAssetInstanceSchema(BaseSchema):
    """
    Body for adding an asset instance to a scene.
    """

    asset_id: UUID = Field(..., description="Asset unique identifier")
    description: Optional[str] = None


class CastAssetSchema(BaseSchema):
    """
    Body for casting one asset in several entities at once.
    """

    entity_ids: list[UUID] = Field(
        ..., min_length=1, description="Entities to cast the asset in"
    )
    nb_occurences: Optional[int] = Field(
        default=None,
        ge=0,
        description="Number of occurences, 0 removes the asset from the "
        "casting, omit to keep the current one",
    )
    label: Optional[str] = Field(
        default=None, description="Casting label, omit to keep the current one"
    )
