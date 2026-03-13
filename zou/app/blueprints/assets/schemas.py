"""
Pydantic schemas for request body validation in the assets blueprint.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class NewAssetSchema(BaseSchema):
    """Body for creating a new asset."""

    name: str = Field(
        ..., min_length=1, description="The asset name is required."
    )
    description: Optional[str] = ""
    data: Optional[dict] = Field(default={})
    is_shared: Optional[bool] = False
    episode_id: Optional[UUID] = None


class AssetInstanceSchema(BaseSchema):
    """Body for creating an asset instance on an asset."""

    asset_to_instantiate_id: UUID = Field(
        ..., description="Asset to instantiate unique identifier"
    )
    description: Optional[str] = None


class SetSharedAssetsSchema(BaseSchema):
    """Body for setting shared status on assets."""

    is_shared: Optional[bool] = True
    asset_ids: Optional[List[UUID]] = None
