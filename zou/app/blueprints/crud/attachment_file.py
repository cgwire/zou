from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.attachment_file import AttachmentFile
from zou.app.services import (
    chats_service,
    comments_service,
    permissions_service,
)
from zou.app.utils.openapi import load_specs, swag_from
from zou.app.utils.permissions import PermissionDenied

SPECS = load_specs(__file__, "openapi/attachment_file.yml")


class AttachmentFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AttachmentFile)

    @jwt_required()
    @swag_from(SPECS["AttachmentFilesResource_get"])
    def get(self):
        """
        Get attachment files
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["AttachmentFilesResource_post"])
    def post(self):
        """
        Create attachment file
        """
        return super().post()


class AttachmentFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AttachmentFile)

    @jwt_required()
    @swag_from(SPECS["AttachmentFileResource_get"])
    def get(self, instance_id):
        """
        Get attachment file
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["AttachmentFileResource_put"])
    def put(self, instance_id):
        """
        Update attachment file
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["AttachmentFileResource_delete"])
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
            permissions_service.check_comment_access(
                comment["id"], comment=comment
            )
        elif attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat_by_id(message["chat_id"])
            permissions_service.check_chat_access(chat["object_id"])
        else:
            raise PermissionDenied()
        return True
