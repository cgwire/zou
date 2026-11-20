from typing import Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class NewUntrackedSchema(BaseSchema):
    """
    Body for creating an untracked item.
    """

    name: str = Field(
        ..., min_length=1, max_length=160, description="The item name"
    )
    description: str = ""
    parent_id: Optional[UUID] = Field(
        default=None,
        description="Episode, sequence or shot the item is linked to",
    )
    create_task: bool = Field(
        default=False,
        description="Create the task of the item along, with the task type "
        "of its department",
    )
    department_id: Optional[UUID] = Field(
        default=None,
        description="Department the task is planned for, none by default",
    )
    color: Optional[str] = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Colour of the row of the item in the schedule",
    )


class UpdateUntrackedSchema(BaseSchema):
    """
    Body for renaming an untracked item or changing its link. A null
    parent_id removes the link, a missing one keeps it.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
