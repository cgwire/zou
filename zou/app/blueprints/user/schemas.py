"""
Pydantic schemas for request body validation in the user blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class CreateSearchFilterSchema(BaseSchema):
    """Body for creating a search filter."""

    name: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    list_type: str = Field("todo")
    project_id: Optional[str] = None
    entity_type: Optional[str] = None
    is_shared: Optional[bool] = False
    search_filter_group_id: Optional[str] = None
    department_id: Optional[str] = None


class UpdateSearchFilterSchema(BaseSchema):
    """Body for updating a search filter."""

    name: Optional[str] = None
    search_query: Optional[str] = None
    search_filter_group_id: Optional[str] = None
    is_shared: Optional[bool] = None
    project_id: Optional[str] = None
    department_id: Optional[str] = None


class CreateSearchFilterGroupSchema(BaseSchema):
    """Body for creating a search filter group."""

    name: str = Field(..., min_length=1)
    color: str = Field(..., min_length=1)
    list_type: str = Field("todo")
    project_id: Optional[str] = None
    is_shared: Optional[bool] = False
    entity_type: Optional[str] = None
    department_id: Optional[str] = None


class UpdateSearchFilterGroupSchema(BaseSchema):
    """Body for updating a search filter group."""

    name: Optional[str] = None
    color: Optional[str] = None
    is_shared: Optional[bool] = None
    project_id: Optional[str] = None
    department_id: Optional[str] = None


class NotificationUpdateSchema(BaseSchema):
    """Body for updating a notification."""

    read: Optional[bool] = None
