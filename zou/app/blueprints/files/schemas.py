"""
Pydantic schemas for request body validation in the files blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class WorkingFilePathSchema(BaseSchema):
    """
    Body to generate a working file path.
    """

    name: str = "main"
    mode: str = "working"
    software_id: Optional[str] = None
    comment: str = ""
    revision: int = 0
    sep: str = "/"


class OutputFilePathSchema(BaseSchema):
    """
    Body to generate an output file path.
    """

    name: str = "main"
    mode: str = "output"
    output_type_id: str = Field(..., min_length=1)
    task_type_id: str = Field(..., min_length=1)
    revision: int = 0
    extension: str = ""
    representation: str = ""
    separator: str = "/"


class NewWorkingFileSchema(BaseSchema):
    """
    Body to create a new revision of a working file.
    """

    name: str = Field(..., min_length=1, description="The file name")
    description: str = ""
    mode: str = "working"
    comment: str = ""
    person_id: Optional[str] = None
    software_id: Optional[str] = None
    revision: int = 0
    sep: str = "/"


class WorkingFileCommentSchema(BaseSchema):
    """
    Body to update the comment of a working file.
    """

    comment: str = Field(
        ..., min_length=1, description="Comment field expected."
    )


class NewOutputFileSchema(BaseSchema):
    """
    Body to create a new output file for an entity or an asset instance.
    """

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
    """
    Body to get the next revision number of an output file.
    """

    name: str = "main"
    output_type_id: str = Field(..., min_length=1)
    task_type_id: str = Field(..., min_length=1)


class GuessFilePathSchema(BaseSchema):
    """
    Body to guess the file tree template from a path.
    """

    project_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    sep: str = "/"
