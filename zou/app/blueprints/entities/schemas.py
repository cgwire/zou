from typing import List

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class CreateEntityTasksSchema(BaseSchema):
    task_type_ids: List[str] = Field(default_factory=list)
