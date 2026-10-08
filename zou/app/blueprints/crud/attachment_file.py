from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.attachment_file import AttachmentFile

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import (
    chats_service,
    permissions_service,
    comments_service,
)

from zou.app.utils.permissions import PermissionDenied


class AttachmentFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AttachmentFile)

    @jwt_required()
    @swag_from("openapi/AttachmentFilesResource_get.yml")
    def get(self):
        """
        Get attachment files
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/AttachmentFilesResource_post.yml")
    def post(self):
        """
        Create attachment file
        """
        return super().post()


class AttachmentFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AttachmentFile)

    @jwt_required()
    @swag_from("openapi/AttachmentFileResource_get.yml")
    def get(self, instance_id):
        """
        Get attachment file
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/AttachmentFileResource_put.yml")
    def put(self, instance_id):
        """
        Update attachment file
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/AttachmentFileResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete attachment file
        """
        return super().delete(instance_id)

    def check_read_permissions(self, instance):
        attachment_file = instance
        if attachment_file["comment_id"] is not None:
            comment = comments_service.get_comment(
                attachment_file["comment_id"]
            )
            permissions_service.check_task_access(comment["object_id"])
        elif attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat(message["chat_id"])
            permissions_service.check_entity_access(chat["object_id"])
        else:
            raise PermissionDenied()
        return True
