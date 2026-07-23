"""
Pydantic schemas for request body validation in the projects blueprint.
"""

from typing import List, Literal, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema

# Mirrors ROLE_TYPES minus admin: admin stays a global-only role.
ProjectRole = Literal["user", "supervisor", "manager", "client", "vendor"]


class ProjectTeamSchema(BaseSchema):
    """
    Body for adding a person to a project team.
    """

    person_id: str = Field(..., min_length=1)
    role: Optional[ProjectRole] = None


class ProjectTeamRoleSchema(BaseSchema):
    """
    Body for setting the role of a team member on this project only. A null
    role restores inheritance of the person's global role.
    """

    role: Optional[ProjectRole] = None


class ProjectAssetTypeSchema(BaseSchema):
    """
    Body for adding an asset type to a project.
    """

    asset_type_id: str = Field(..., min_length=1)


class ProjectTaskTypeSchema(BaseSchema):
    """
    Body for adding a task type to a project.
    """

    task_type_id: str = Field(..., min_length=1)
    priority: Optional[int] = None


class ProjectTaskStatusSchema(BaseSchema):
    """
    Body for adding a task status to a project.
    """

    task_status_id: str = Field(..., min_length=1)


class ProjectSettingsBatchSchema(BaseSchema):
    """
    Body for adding several task types, task statuses and asset types to a
    project in a single request.
    """

    task_types: List[ProjectTaskTypeSchema] = Field(default=[])
    task_status_ids: List[str] = Field(default=[])
    asset_type_ids: List[str] = Field(default=[])
    # When set, task_types is the full wanted set: existing task type links
    # absent from it are removed (used by the import-from-production flow).
    replace_task_types: bool = False


class ProjectStatusAutomationSchema(BaseSchema):
    """
    Body for adding a status automation to a project.
    """

    status_automation_id: str = Field(..., min_length=1)


class ProjectPreviewBackgroundSchema(BaseSchema):
    """
    Body for adding a preview background file to a project.
    """

    preview_background_file_id: str = Field(..., min_length=1)


class MetadataDescriptorSchema(BaseSchema):
    """
    Body for creating a metadata descriptor.
    """

    entity_type: str = "Asset"
    task_type_id: Optional[str] = None
    name: str = Field(..., min_length=1)
    data_type: str = Field("string", min_length=1)
    for_client: Optional[bool] = False
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class MetadataDescriptorUpdateSchema(BaseSchema):
    """
    Body for updating a metadata descriptor.
    """

    name: Optional[str] = None
    for_client: Optional[bool] = False
    data_type: str = Field("string", min_length=1)
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class MetadataDescriptorOrderSchema(BaseSchema):
    """
    Body for reordering metadata descriptors.
    """

    entity_type: str = Field(..., min_length=1)
    descriptor_ids: List[str] = Field(..., min_length=1)


class AllProjectsMetadataDescriptorUpdateSchema(BaseSchema):
    """
    Body for updating a metadata descriptor across all accessible projects.
    """

    entity_type: str = Field(..., min_length=1)
    name: Optional[str] = None
    for_client: Optional[bool] = False
    data_type: str = Field("string", min_length=1)
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class AllProjectsMetadataDescriptorOrderSchema(BaseSchema):
    """
    Body for reordering metadata descriptors across all accessible projects.
    The order is given as a list of field names shared by the projects.
    """

    entity_type: str = Field(..., min_length=1)
    field_order: List[str] = Field(..., min_length=1)


class BudgetSchema(BaseSchema):
    """
    Body for creating a budget.
    """

    name: str = Field(..., min_length=1)
    currency: Optional[str] = "USD"


class BudgetUpdateSchema(BaseSchema):
    """
    Body for updating a budget.
    """

    name: Optional[str] = None
    currency: Optional[str] = None


class BudgetEntrySchema(BaseSchema):
    """
    Body for creating a budget entry.
    """

    department_id: str = Field(..., min_length=1)
    person_id: Optional[str] = None
    start_date: Optional[str] = None
    months_duration: Optional[int] = None
    daily_salary: Optional[float] = None
    position: Optional[str] = None
    seniority: Optional[str] = None


class BudgetEntryUpdateSchema(BaseSchema):
    """
    Body for updating a budget entry.
    """

    department_id: Optional[str] = None
    person_id: Optional[str] = None
    start_date: Optional[str] = None
    months_duration: Optional[int] = None
    daily_salary: Optional[float] = None
    position: Optional[str] = None
    seniority: Optional[str] = None
    exceptions: Optional[dict] = Field(default={})


class ScheduleVersionCopySchema(BaseSchema):
    """
    Body for copying task links from another schedule version.
    """

    production_schedule_version_id: str = Field(..., min_length=1)
