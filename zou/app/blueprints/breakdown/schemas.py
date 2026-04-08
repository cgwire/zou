"""
Pydantic schemas for request body validation in the breakdown blueprint.
"""

from typing import Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class AddAssetInstanceSchema(BaseSchema):
    """Body for adding an asset instance to a shot."""

    asset_instance_id: UUID = Field(
        ..., description="Asset instance unique identifier"
    )


class AddSceneAssetInstanceSchema(BaseSchema):
    """Body for adding an asset instance to a scene."""

    asset_id: UUID = Field(..., description="Asset unique identifier")
    description: Optional[str] = None
