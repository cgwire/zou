from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.chat import Chat

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class ChatsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Chat)

    @jwt_required()
    @swag_from("openapi/ChatsResource_get.yml")
    def get(self):
        """
        Get chats
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/ChatsResource_post.yml")
    def post(self):
        """
        Create chat
        """
        return super().post()


class ChatResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Chat)

    @jwt_required()
    @swag_from("openapi/ChatResource_get.yml")
    def get(self, instance_id):
        """
        Get chat
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/ChatResource_put.yml")
    def put(self, instance_id):
        """
        Update chat
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/ChatResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete chat
        """
        return super().delete(instance_id)
