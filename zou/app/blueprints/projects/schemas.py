"""
Pydantic schemas that validate the request bodies of the projects blueprint.
"""

from typing import List, Literal, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema

# Same as ROLE_TYPES without admin: admin is only a global role.
ProjectRole = Literal["user", "supervisor", "manager", "client", "vendor"]


class ProjectTeamSchema(BaseSchema):
    """
    Body to add a person to a project team.
    """

    person_id: str = Field(..., min_length=1)
    role: Optional[ProjectRole] = None


class ProjectTeamRoleSchema(BaseSchema):
    """
    Body to set the role of a team member on this project only. A null role
    restores the inheritance of the global role of the person.
    """

    role: Optional[ProjectRole] = None


class ProjectAssetTypeSchema(BaseSchema):
    """
    Body to add an asset type to a project.
    """

    asset_type_id: str = Field(..., min_length=1)


class ProjectAssetTypeWorkflowSchema(BaseSchema):
    """
    Body to set the workflow of an asset type on a project. An empty list
    restores the studio workflow.
    """

    task_type_ids: List[str]


class ProjectTaskTypeSoftwareSchema(BaseSchema):
    """
    Body to link a software to a task type of a project.
    """

    software_id: str = Field(..., min_length=1)


class ProjectTaskTypeSchema(BaseSchema):
    """
    Body to add a task type to a project.
    """

    task_type_id: str = Field(..., min_length=1)
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


class ProjectTaskStatusSchema(BaseSchema):
    """
    Body to add a task status to a project.
    """

    task_status_id: str = Field(..., min_length=1)


class ProjectTaskStatusClientAllowedSchema(BaseSchema):
    """
    Body to override whether the clients of a project may set a task status.
    The field is required. A null value restores the studio value.
    """

    is_client_allowed: Optional[bool] = Field(...)


class ProjectSettingsBatchSchema(BaseSchema):
    """
    Body to add several task types, task statuses and asset types to a project
    in one request.
    """

    task_types: List[ProjectTaskTypeSchema] = Field(default=[])
    task_status_ids: List[str] = Field(default=[])
    asset_type_ids: List[str] = Field(default=[])
    # If set, task_types is the full set of task types to keep. The existing
    # task type links that are not in it go away. The import from a production
    # uses this.
    replace_task_types: bool = False


class ProjectStatusAutomationSchema(BaseSchema):
    """
    Body to add a status automation to a project.
    """

    status_automation_id: str = Field(..., min_length=1)


class ProjectPreviewBackgroundSchema(BaseSchema):
    """
    Body to add a preview background file to a project.
    """

    preview_background_file_id: str = Field(..., min_length=1)


class MetadataDescriptorSchema(BaseSchema):
    """
    Body to create a metadata descriptor.
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
    Body to update a metadata descriptor.
    """

    name: Optional[str] = None
    for_client: Optional[bool] = False
    data_type: str = Field("string", min_length=1)
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class MetadataDescriptorOrderSchema(BaseSchema):
    """
    Body to reorder the metadata descriptors.
    """

    entity_type: str = Field(..., min_length=1)
    descriptor_ids: List[str] = Field(..., min_length=1)


class AllProjectsMetadataDescriptorUpdateSchema(BaseSchema):
    """
    Body to update a metadata descriptor in all the accessible projects.
    """

    entity_type: str = Field(..., min_length=1)
    name: Optional[str] = None
    for_client: Optional[bool] = False
    data_type: str = Field("string", min_length=1)
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class AllProjectsMetadataDescriptorOrderSchema(BaseSchema):
    """
    Body to reorder the metadata descriptors in all the accessible projects.
    The order is a list of the field names that the projects share.
    """

    entity_type: str = Field(..., min_length=1)
    field_order: List[str] = Field(..., min_length=1)


class BudgetSchema(BaseSchema):
    """
    Body to create a budget.
    """

    name: str = Field(..., min_length=1)
    currency: Optional[str] = "USD"


class BudgetUpdateSchema(BaseSchema):
    """
    Body to update a budget.
    """

    name: Optional[str] = None
    currency: Optional[str] = None


class BudgetEntrySchema(BaseSchema):
    """
    Body to create a budget entry.
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
    Body to update a budget entry.
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
    Body to copy the task links from another schedule version.
    """

    production_schedule_version_id: str = Field(..., min_length=1)


class PreviewAccountOpenSchema(BaseSchema):
    """
    Body to open or close the access window of a preview account.
    """

    is_open: bool
