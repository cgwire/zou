"""
Pydantic schemas that validate the request bodies of the tasks blueprint.
"""

from typing import List, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class CommentPreviewSchema(BaseSchema):
    """
    Body to add a preview to a comment.
    """

    revision: Optional[int] = Field(None, ge=0)


class UnassignTasksSchema(BaseSchema):
    """
    Body to clear the assignations of tasks.
    """

    task_ids: List[str] = Field(
        ..., min_length=1, description="Tasks list required."
    )
    person_id: Optional[str] = None


class SetTasksPrioritySchema(BaseSchema):
    """
    Body to set the priority of several tasks.
    """

    task_ids: List[str] = Field(
        ..., min_length=1, description="Tasks list required."
    )
    priority: int = Field(..., ge=0, description="Priority to set.")


class SetTasksMainPreviewSchema(BaseSchema):
    """
    Body to set the main preview of the entities of several tasks.
    """

    task_ids: List[str] = Field(
        ..., min_length=1, description="Tasks list required."
    )


class AssignTasksSchema(BaseSchema):
    """
    Body to assign tasks to a person.
    """

    task_ids: List[str] = Field(
        ..., min_length=1, description="Tasks list required."
    )


class AssignPersonSchema(BaseSchema):
    """
    Body to assign one task to a person.
    """

    person_id: str = Field(
        ..., min_length=1, description="Assignee ID required."
    )


class TimeSpentSchema(BaseSchema):
    """
    Body to create or update the time spent on a task.
    """

    duration: float = Field(..., gt=0, description="Duration in minutes")
