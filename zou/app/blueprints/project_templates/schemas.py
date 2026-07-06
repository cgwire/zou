"""
Pydantic schemas for request body validation in the project templates
blueprint.
"""

from typing import List, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class AddTaskTypeSchema(BaseSchema):
    """
    Body for attaching a task type to a project template.
    """

    task_type_id: str = Field(..., min_length=1, description="Task type UUID")
    priority: Optional[int] = None


class AddTaskStatusSchema(BaseSchema):
    """
    Body for attaching a task status to a project template.
    """

    task_status_id: str = Field(
        ..., min_length=1, description="Task status UUID"
    )
    priority: Optional[int] = None
    roles_for_board: List[str] = Field(default_factory=list)


class AddAssetTypeSchema(BaseSchema):
    """
    Body for attaching an asset type to a project template.
    """

    asset_type_id: str = Field(
        ..., min_length=1, description="Asset type UUID"
    )


class AddStatusAutomationSchema(BaseSchema):
    """
    Body for attaching a status automation to a project template.
    """

    status_automation_id: str = Field(
        ..., min_length=1, description="Status automation UUID"
    )


class AddBackgroundSchema(BaseSchema):
    """
    Body for attaching a preview background to a project template.
    """

    preview_background_file_id: str = Field(
        ..., min_length=1, description="Preview background file UUID"
    )


class SetMetadataDescriptorsSchema(BaseSchema):
    """
    Body for replacing the metadata descriptors snapshot on a template.
    """

    metadata_descriptors: Optional[list] = None


class SetDefaultBackgroundSchema(BaseSchema):
    """
    Body for setting the default preview background of a template.
    """

    default_preview_background_file_id: Optional[str] = None


class CreateTemplateFromProjectSchema(BaseSchema):
    """
    Body for creating a template from an existing project.
    """

    name: str = Field(..., min_length=1, description="Template name")
    description: Optional[str] = None
