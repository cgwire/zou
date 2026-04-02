"""
Pydantic schemas for request body validation in the tasks blueprint.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class CommentPreviewSchema(BaseSchema):
    """Body for adding a preview to a comment."""

    revision: int = Field(0, ge=0)


class ToReviewSchema(BaseSchema):
    """Body for setting a task to review."""

    person_id: Optional[str] = None
    comment: Optional[str] = ""
    name: Optional[str] = "main"
    revision: int = Field(1, ge=0)
    change_status: Optional[bool] = True


class UnassignTasksSchema(BaseSchema):
    """Body for clearing task assignations."""

    task_ids: List[str] = Field(
        ..., min_length=1, description="Tasks list required."
    )
    person_id: Optional[str] = None


class AssignTasksSchema(BaseSchema):
    """Body for assigning tasks to a person."""

    task_ids: List[str] = Field(
        ..., min_length=1, description="Tasks list required."
    )


class AssignPersonSchema(BaseSchema):
    """Body for assigning a single task to a person."""

    person_id: str = Field(
        ..., min_length=1, description="Assignee ID required."
    )


class TimeSpentSchema(BaseSchema):
    """Body for creating/updating time spent on a task."""

    duration: int = Field(..., gt=0, description="Duration in minutes")
