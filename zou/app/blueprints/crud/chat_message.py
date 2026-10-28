from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.chat_message import ChatMessage
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/chat_message.yml")


class ChatMessagesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ChatMessage)

    @jwt_required()
    @swag_from(SPECS["ChatMessagesResource_get"])
    def get(self):
        """
        Get chat messages
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["ChatMessagesResource_post"])
    def post(self):
        """
        Create chat message
        """
        return super().post()


class ChatMessageResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ChatMessage)

    @jwt_required()
    @swag_from(SPECS["ChatMessageResource_get"])
    def get(self, instance_id):
        """
        Get chat message
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["ChatMessageResource_put"])
    def put(self, instance_id):
        """
        Update chat message
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["ChatMessageResource_delete"])
    def delete(self, instance_id):
        """
        Delete chat message
        """
        return super().delete(instance_id)
