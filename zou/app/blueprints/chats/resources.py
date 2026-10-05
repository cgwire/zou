from flasgger import swag_from
from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.chats.schemas import ChatMessageSchema
from zou.app.utils import permissions, validation

from zou.app.services import (
    chats_service,
    entities_service,
    persons_service,
    permissions_service,
    user_service,
)
from zou.app.exceptions import WrongParameterException


class ChatResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ChatResource_get.yml")
    def get(self, entity_id):
        """
        Get chat details
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])
        chat = chats_service.get_chat(entity_id)
        chat["messages"] = chats_service.get_chat_messages(entity_id)
        return chat


class ChatMessagesResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ChatMessagesResource_get.yml")
    def get(self, entity_id):
        """
        Get chat messages
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])
        return chats_service.get_chat_messages_for_entity(entity_id)

    @jwt_required()
    @swag_from("openapi/ChatMessagesResource_post.yml")
    def post(self, entity_id):
        """
        Create chat message
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])

        person = persons_service.get_current_user()
        body = validation.validate_request_body(ChatMessageSchema)
        message = body.message
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


class ChatMessageResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ChatMessageResource_get.yml")
    def get(self, entity_id, chat_message_id):
        """
        Get chat message
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])
        chat = chats_service.get_chat(entity_id)
        chat_message = chats_service.get_chat_message(chat_message_id)
        if chat_message["chat_id"] != chat["id"]:
            raise permissions.PermissionDenied()
        return chat_message

    @jwt_required()
    @swag_from("openapi/ChatMessageResource_delete.yml")
    def delete(self, entity_id, chat_message_id):
        """
        Delete chat message
        """
        entity = entities_service.get_entity(entity_id)
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])

        chat = chats_service.get_chat(entity_id)
        chat_message = chats_service.get_chat_message(chat_message_id)
        if chat_message["chat_id"] != chat["id"]:
            raise permissions.PermissionDenied()
        current_user = persons_service.get_current_user()
        if (
            chat_message["person_id"] != current_user["id"]
            and not permissions.has_admin_permissions()
        ):
            raise permissions.PermissionDenied()
        chats_service.delete_chat_message(chat_message_id)

        return "", 204
