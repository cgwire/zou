"""
Pydantic schemas for request body validation in the chats blueprint.
"""

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class ChatMessageSchema(BaseSchema):
    """
    Body for posting a message in an entity chat.
    """

    message: str = Field(..., description="Message text content")
