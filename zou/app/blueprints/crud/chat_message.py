from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.chat_message import ChatMessage

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class ChatMessagesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ChatMessage)

    @jwt_required()
    @swag_from("openapi/ChatMessagesResource_get.yml")
    def get(self):
        """
        Get chat messages
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/ChatMessagesResource_post.yml")
    def post(self):
        """
        Create chat message
        """
        return super().post()


class ChatMessageResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ChatMessage)

    @jwt_required()
    @swag_from("openapi/ChatMessageResource_get.yml")
    def get(self, instance_id):
        """
        Get chat message
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/ChatMessageResource_put.yml")
    def put(self, instance_id):
        """
        Update chat message
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/ChatMessageResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete chat message
        """
        return super().delete(instance_id)
