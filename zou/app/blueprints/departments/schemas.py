"""
Pydantic schemas for request body validation in the departments blueprint.
"""

from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class AddSoftwareToDepartmentSchema(BaseSchema):
    """Body for adding a software license to a department."""

    software_id: UUID = Field(
        ..., description="Software license unique identifier"
    )


class AddHardwareToDepartmentSchema(BaseSchema):
    """Body for adding a hardware item to a department."""

    hardware_item_id: UUID = Field(
        ..., description="Hardware item unique identifier"
    )
