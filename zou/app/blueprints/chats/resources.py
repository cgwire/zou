from flask import request
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.utils import permissions

from zou.app.services import (
    chats_service,
    entities_service,
    persons_service,
    user_service,
)
from zou.app.services.exception import WrongParameterException


class ChatResource(Resource):

    @jwt_required()
    def get(self, entity_id):
        """
        Get chat details
        ---
        description: Retrieve chat information and messages for a specific entity.
          Returns chat metadata including participants and all associated messages.
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Chat information successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Chat unique identifier
                    entity_id:
                      type: string
                      format: uuid
                      description: Entity ID this chat is associated with
                    participants:
                      type: array
                      items:
                        type: string
                        format: uuid
                      description: List of participant user IDs
                    messages:
                      type: array
                      items:
                        type: object
                      description: Array of chat messages
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        chat = chats_service.get_chat(entity_id)
        chat["messages"] = chats_service.get_chat_messages(entity_id)
        return chat


class ChatMessagesResource(Resource):

    @jwt_required()
    def get(self, entity_id):
        """
        Get chat messages
        ---
        description: Retrieve all chat messages for a specific entity.
          Returns a list of messages with sender information and timestamps.
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Chat messages successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Message unique identifier
                      message:
                        type: string
                        description: Message content
                      person_id:
                        type: string
                        format: uuid
                        description: ID of the message sender
                      created_at:
                        type: string
                        format: date-time
                        description: Message creation timestamp
                      attachments:
                        type: array
                        items:
                          type: object
                        description: Array of file attachments
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        return chats_service.get_chat_messages_for_entity(entity_id)

    @jwt_required()
    def post(self, entity_id):
        """
        Create chat message
        ---
        description: Create a new chat message for a specific entity.
          Supports both JSON and form data with optional file attachments.
          Only chat participants can send messages.
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    description: Message content to send
                    example: Hello, world!
                required:
                  - message
            multipart/form-data:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    description: Message content to send
                    example: Hello, world!
                  files:
                    type: array
                    items:
                      type: string
                      format: binary
                    description: Files to attach to the message
                required:
                  - message
        responses:
          201:
            description: Chat message successfully created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Created message unique identifier
                    message:
                      type: string
                      description: Message content
                    person_id:
                      type: string
                      format: uuid
                      description: ID of the message sender
                    created_at:
                      type: string
                      format: date-time
                      description: Message creation timestamp
                    attachments:
                      type: array
                      items:
                        type: object
                      description: Array of attached files
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])

        person = persons_service.get_current_user()
        if request.is_json:
            location = ["values", "json"]
        else:
            location = ["values", "form"]
        parser = reqparse.RequestParser()
        parser.add_argument(
            "message", type=str, required=True, location=location
        )
        args = parser.parse_args()
        message = args["message"]
        files = request.files

        chat = chats_service.get_chat(entity_id)
        if person["id"] not in chat["participants"]:
            raise WrongParameterException(
                "You are not a participant of this chat"
            )

        return (
            chats_service.create_chat_message(
                chat["id"], person["id"], message, files=files
            ),
            201,
        )


class ChatMessageResource(Resource):

    @jwt_required()
    def get(self, entity_id, chat_message_id):
        """
        Get chat message
        ---
        description: Retrieve a specific chat message by its ID.
          Returns detailed message information including content and metadata.
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: chat_message_id
            description: ID of the chat message
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Chat message successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Message unique identifier
                    message:
                      type: string
                      description: Message content
                    person_id:
                      type: string
                      format: uuid
                      description: ID of the message sender
                    created_at:
                      type: string
                      format: date-time
                      description: Message creation timestamp
                    updated_at:
                      type: string
                      format: date-time
                      description: Message last update timestamp
                    attachments:
                      type: array
                      items:
                        type: object
                      description: Array of file attachments
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        return chats_service.get_chat_message(chat_message_id)

    @jwt_required()
    def delete(self, entity_id, chat_message_id):
        """
        Delete chat message
        ---
        description: Delete a specific chat message. Only the message author
          or administrators can delete messages.
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: chat_message_id
            description: ID of the chat message to delete
            type: string
            format: uuid
            required: true
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          204:
            description: Chat message successfully deleted
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])

        chat_message = chats_service.get_chat_message(chat_message_id)
        current_user = persons_service.get_current_user()
        if (
            chat_message["person_id"] != current_user["id"]
            or not permissions.has_admin_permissions
        ):
            raise permissions.PermissionDenied
        chats_service.delete_chat_message(chat_message_id)

        return "", 204
