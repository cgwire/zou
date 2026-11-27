"""
Pydantic schemas that validate the request bodies of the project templates
blueprint.
"""

from typing import List, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class AddTaskTypeSchema(BaseSchema):
    """
    Body to attach a task type to a project template.
    """

    task_type_id: str = Field(..., min_length=1, description="Task type UUID")
    priority: Optional[int] = None
    hd_bitrate_compression: Optional[int] = Field(None, ge=1)
    ld_bitrate_compression: Optional[int] = Field(None, ge=1)
    is_client_visible: Optional[bool] = None

    def bitrates(self):
        """
        Return the bitrates to write on the link. If the body does not give
        them, return None: a call that sets only the priority keeps the current
        bitrates.
        """
        keys = ("hd_bitrate_compression", "ld_bitrate_compression")
        if not self.model_fields_set.intersection(keys):
            return None
        return {key: getattr(self, key) for key in keys}


class AddTaskStatusSchema(BaseSchema):
    """
    Body to attach a task status to a project template.
    """

    task_status_id: str = Field(
        ..., min_length=1, description="Task status UUID"
    )
    priority: Optional[int] = None
    roles_for_board: List[str] = Field(default_factory=list)
    is_client_allowed: Optional[bool] = None


class AssetTypeWorkflowSchema(BaseSchema):
    """
    Body to set the workflow of an asset type on a template. An empty list
    restores the studio workflow.
    """

    task_type_ids: List[str]


class AddAssetTypeSchema(BaseSchema):
    """
    Body to attach an asset type to a project template.
    """

    asset_type_id: str = Field(
        ..., min_length=1, description="Asset type UUID"
    )


class AddStatusAutomationSchema(BaseSchema):
    """
    Body to attach a status automation to a project template.
    """

    status_automation_id: str = Field(
        ..., min_length=1, description="Status automation UUID"
    )


class AddBackgroundSchema(BaseSchema):
    """
    Body to attach a preview background to a project template.
    """

    preview_background_file_id: str = Field(
        ..., min_length=1, description="Preview background file UUID"
    )


class ReorderTaskTypesSchema(BaseSchema):
    """
    Body of the route that reorders the task types: the IDs in their new order.
    """

    task_type_ids: List[str]


class ReorderTaskStatusesSchema(BaseSchema):
    """
    Body of the route that reorders the task statuses: the IDs in their new
    order.
    """

    task_status_ids: List[str]


class SetMetadataDescriptorsSchema(BaseSchema):
    """
    Body to replace the snapshot of the metadata descriptors on a template.
    """

    metadata_descriptors: Optional[list] = None


class SetDefaultBackgroundSchema(BaseSchema):
    """
    Body to set the default preview background of a template.
    """

    default_preview_background_file_id: Optional[str] = None


class CreateTemplateFromProjectSchema(BaseSchema):
    """
    Body to create a template from an existing project.
    """

    name: str = Field(..., min_length=1, description="Template name")
    description: Optional[str] = None
