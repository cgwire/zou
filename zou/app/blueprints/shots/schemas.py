"""
Pydantic schemas for request body validation in the shots blueprint.
"""

from typing import Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class NewShotSchema(BaseSchema):
    """Body for creating a new shot."""

    name: str = Field(..., min_length=1, description="Shot name")
    sequence_id: Optional[UUID] = None
    data: Optional[dict] = None
    nb_frames: Optional[int] = None
    description: Optional[str] = None


class NewSequenceSchema(BaseSchema):
    """Body for creating a new sequence."""

    name: str = Field(..., min_length=1, description="Sequence name")
    episode_id: Optional[UUID] = None
    description: Optional[str] = ""
    data: Optional[dict] = Field(default={})


class NewEpisodeSchema(BaseSchema):
    """Body for creating a new episode."""

    name: str = Field(..., min_length=1, description="Episode name")
    status: Optional[str] = "running"
    description: Optional[str] = ""
    data: Optional[dict] = Field(default={})


class NewSceneSchema(BaseSchema):
    """Body for creating a new scene."""

    name: str = Field(..., min_length=1, description="Scene name")
    sequence_id: Optional[UUID] = None


class AddShotToSceneSchema(BaseSchema):
    """Body for adding a shot to a scene."""

    shot_id: UUID = Field(..., description="Shot unique identifier")
