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
        Get chat details.
        ---
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: integer
            required: true
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Chat information
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
        Get chat messages for an entity.
        ---
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: integer
            required: true
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Chat messages
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        return chats_service.get_chat_messages_for_entity(entity_id)

    @jwt_required()
    def post(self, entity_id):
        """
        Create a new chat message.
        ---
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: integer
            required: true
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: message
            description: Message to send
            type: string
            required: true
            x-example: Hello, world!
          - in: formData
            name: files
            description: Files to attach
            type: file
            required: false
        responses:
            201:
                description: Chat message created
            400:
                description: Not participant of the chat
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
            raise WrongParameterException("You are not a participant of this chat")

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
        Get chat message.
        ---
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: integer
            required: true
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: chat_message_id
            description: ID of the chat message
            type: integer
            required: true
            x-example: 1
        responses:
            200:
                description: Chat message
        """
        entity = entities_service.get_entity(entity_id)
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])
        return chats_service.get_chat_message(chat_message_id)

    @jwt_required()
    def delete(self, entity_id, chat_message_id):
        """
        Delete chat message.
        ---
        tags:
          - Chat
        parameters:
          - in: path
            name: entity_id
            description: ID of the entity related to the chat
            type: integer
            required: true
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: chat_message_id
            description: ID of the chat message
            type: integer
            required: true
            x-example: 1
        responses:
            204:
                description: Empty response
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
