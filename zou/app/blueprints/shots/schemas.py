"""
Pydantic schemas that validate the request bodies of the shots blueprint.
"""

from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from zou.app.utils.validation import BaseSchema


class NewShotSchema(BaseSchema):
    """
    Body to create a new shot.
    """

    name: str = Field(..., min_length=1, description="Shot name")
    sequence_id: Optional[UUID] = None
    data: Optional[dict] = None
    nb_frames: Optional[int] = None
    description: Optional[str] = None


class NewSequenceSchema(BaseSchema):
    """
    Body to create a new sequence.
    """

    name: str = Field(..., min_length=1, description="Sequence name")
    episode_id: Optional[UUID] = None
    description: Optional[str] = ""
    data: Optional[dict] = Field(default={})


class NewEpisodeSchema(BaseSchema):
    """
    Body to create a new episode.
    """

    name: str = Field(..., min_length=1, description="Episode name")
    status: Optional[str] = "running"
    description: Optional[str] = ""
    data: Optional[dict] = Field(default={})


class NewSceneSchema(BaseSchema):
    """
    Body to create a new scene.
    """

    name: str = Field(..., min_length=1, description="Scene name")
    sequence_id: Optional[UUID] = None


class UpdateShotSchema(BaseSchema):
    """
    Body of the route that updates a shot. The schema checks the typed columns,
    and the other columns of the entity pass through. The route removes the
    read-only fields and the relation fields.
    """

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    nb_frames: Optional[int] = None
    data: Optional[dict] = None
    parent_id: Optional[UUID] = None
    canceled: Optional[bool] = None


class AddShotToSceneSchema(BaseSchema):
    """
    Body to add a shot to a scene.
    """

    shot_id: UUID = Field(..., description="Shot unique identifier")
