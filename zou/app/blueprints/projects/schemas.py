"""
Pydantic schemas for request body validation in the projects blueprint.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class ProjectTeamSchema(BaseSchema):
    """Body for adding a person to a project team."""

    person_id: str = Field(..., min_length=1)


class ProjectAssetTypeSchema(BaseSchema):
    """Body for adding an asset type to a project."""

    asset_type_id: str = Field(..., min_length=1)


class ProjectTaskTypeSchema(BaseSchema):
    """Body for adding a task type to a project."""

    task_type_id: str = Field(..., min_length=1)
    priority: Optional[int] = None


class ProjectTaskStatusSchema(BaseSchema):
    """Body for adding a task status to a project."""

    task_status_id: str = Field(..., min_length=1)


class ProjectStatusAutomationSchema(BaseSchema):
    """Body for adding a status automation to a project."""

    status_automation_id: str = Field(..., min_length=1)


class ProjectPreviewBackgroundSchema(BaseSchema):
    """Body for adding a preview background file to a project."""

    preview_background_file_id: str = Field(..., min_length=1)


class MetadataDescriptorSchema(BaseSchema):
    """Body for creating a metadata descriptor."""

    entity_type: str = "Asset"
    name: str = Field(..., min_length=1)
    data_type: str = Field("string", min_length=1)
    for_client: Optional[bool] = False
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class MetadataDescriptorUpdateSchema(BaseSchema):
    """Body for updating a metadata descriptor."""

    name: Optional[str] = None
    for_client: Optional[bool] = False
    data_type: str = Field("string", min_length=1)
    choices: List[str] = Field(default=[])
    departments: List[str] = Field(default=[])


class MetadataDescriptorOrderSchema(BaseSchema):
    """Body for reordering metadata descriptors."""

    entity_type: str = Field(..., min_length=1)
    descriptor_ids: List[str] = Field(..., min_length=1)


class BudgetSchema(BaseSchema):
    """Body for creating a budget."""

    name: str = Field(..., min_length=1)
    currency: Optional[str] = "USD"


class BudgetUpdateSchema(BaseSchema):
    """Body for updating a budget."""

    name: Optional[str] = None
    currency: Optional[str] = None


class BudgetEntrySchema(BaseSchema):
    """Body for creating a budget entry."""

    department_id: str = Field(..., min_length=1)
    person_id: Optional[str] = None
    start_date: Optional[str] = None
    months_duration: Optional[int] = None
    daily_salary: Optional[float] = None
    position: Optional[str] = None
    seniority: Optional[str] = None


class BudgetEntryUpdateSchema(BaseSchema):
    """Body for updating a budget entry."""

    department_id: Optional[str] = None
    person_id: Optional[str] = None
    start_date: Optional[str] = None
    months_duration: Optional[int] = None
    daily_salary: Optional[float] = None
    position: Optional[str] = None
    seniority: Optional[str] = None
    exceptions: Optional[dict] = Field(default={})


class ScheduleVersionCopySchema(BaseSchema):
    """Body for copying task links from another schedule version."""

    production_schedule_version_id: str = Field(..., min_length=1)
