from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.chat import Chat
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/chat.yml")


class ChatsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Chat)

    @jwt_required()
    @swag_from(SPECS["ChatsResource_get"])
    def get(self):
        """
        Get chats
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["ChatsResource_post"])
    def post(self):
        """
        Create chat
        """
        return super().post()


class ChatResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Chat)

    @jwt_required()
    @swag_from(SPECS["ChatResource_get"])
    def get(self, instance_id):
        """
        Get chat
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["ChatResource_put"])
    def put(self, instance_id):
        """
        Update chat
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["ChatResource_delete"])
    def delete(self, instance_id):
        """
        Delete chat
        """
        return super().delete(instance_id)
