"""
Pydantic schemas for request body validation in the user blueprint.
"""

from typing import Annotated, List, Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema

# The column lengths of search_filter and search_filter_group: Postgres
# refuses a longer value with an internal error.
FilterName = Annotated[str, Field(min_length=1, max_length=200)]
FilterQuery = Annotated[str, Field(min_length=1, max_length=500)]
FilterType = Annotated[str, Field(max_length=80)]
FilterColor = Annotated[str, Field(max_length=8)]


class SubscribeTasksSchema(BaseSchema):
    """
    Body for subscribing to or unsubscribing from several tasks at once.
    """

    task_ids: List[str] = Field(..., min_length=1)


class CreateSearchFilterSchema(BaseSchema):
    """
    Body for creating a search filter.
    """

    name: FilterName
    query: FilterQuery
    list_type: FilterType = "todo"
    project_id: Optional[str] = None
    entity_type: Optional[FilterType] = None
    is_shared: Optional[bool] = False
    search_filter_group_id: Optional[str] = None
    department_id: Optional[str] = None


class UpdateSearchFilterSchema(BaseSchema):
    """
    Body for updating a search filter.
    """

    name: Optional[FilterName] = None
    search_query: Optional[FilterQuery] = None
    search_filter_group_id: Optional[str] = None
    is_shared: Optional[bool] = None
    department_id: Optional[str] = None


class CreateSearchFilterGroupSchema(BaseSchema):
    """
    Body for creating a search filter group.
    """

    name: FilterName
    color: Optional[FilterColor] = ""
    list_type: FilterType = "todo"
    project_id: Optional[str] = None
    is_shared: Optional[bool] = False
    entity_type: Optional[FilterType] = None
    department_id: Optional[str] = None


class UpdateSearchFilterGroupSchema(BaseSchema):
    """
    Body for updating a search filter group.
    """

    name: Optional[FilterName] = None
    color: Optional[FilterColor] = None
    is_shared: Optional[bool] = None
    department_id: Optional[str] = None


class NotificationUpdateSchema(BaseSchema):
    """
    Body for updating a notification.
    """

    read: Optional[bool] = None
