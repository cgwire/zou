"""
Pydantic schemas for request body validation in the files blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class WorkingFilePathSchema(BaseSchema):
    """Body for generating a working file path."""

    name: str = "main"
    mode: str = "working"
    software_id: Optional[str] = None
    comment: str = ""
    revision: int = 0
    sep: str = "/"


class OutputFilePathSchema(BaseSchema):
    """Body for generating an output file path."""

    name: str = "main"
    mode: str = "output"
    output_type_id: str = Field(..., min_length=1)
    task_type_id: str = Field(..., min_length=1)
    revision: int = 0
    extension: str = ""
    representation: str = ""
    separator: str = "/"


class NewWorkingFileSchema(BaseSchema):
    """Body for creating a new working file revision."""

    name: str = Field(..., min_length=1, description="The file name")
    description: str = ""
    mode: str = "working"
    comment: str = ""
    person_id: Optional[str] = None
    software_id: Optional[str] = None
    revision: int = 0
    sep: str = "/"


class WorkingFileCommentSchema(BaseSchema):
    """Body for updating a working file comment."""

    comment: str = Field(
        ..., min_length=1, description="Comment field expected."
    )


class NewOutputFileSchema(BaseSchema):
    """Body for creating a new entity output file."""

    name: str = "main"
    mode: str = "output"
    output_type_id: str = Field(..., min_length=1)
    task_type_id: str = Field(..., min_length=1)
    person_id: Optional[str] = None
    working_file_id: Optional[str] = None
    comment: str = Field("", description="Comment for the output file")
    revision: int = 0
    extension: str = ""
    representation: str = ""
    nb_elements: int = 1
    sep: str = "/"
    file_status_id: Optional[str] = None


class NextRevisionSchema(BaseSchema):
    """Body for getting next output file revision number."""

    name: str = "main"
    output_type_id: str = Field(..., min_length=1)
    task_type_id: str = Field(..., min_length=1)


class SetTreeSchema(BaseSchema):
    """Body for setting a project file tree."""

    tree_name: str = Field(
        ...,
        min_length=1,
        description="The name of the tree to set is required.",
    )


class GuessFilePathSchema(BaseSchema):
    """Body for guessing file tree template from path."""

    project_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    sep: str = "/"
