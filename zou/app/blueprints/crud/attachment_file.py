from zou.app.models.attachment_file import AttachmentFile

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import chats_service, tasks_service, user_service

from zou.app.utils.permissions import PermissionDenied


class AttachmentFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AttachmentFile)


class AttachmentFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AttachmentFile)

    def check_read_permissions(self, instance):
        attachment_file = instance
        if attachment_file["comment_id"] is not None:
            comment = tasks_service.get_comment(attachment_file["comment_id"])
            task = tasks_service.get_task(comment["object_id"])
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
        elif attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat(message["chat_id"])
            print(chat)
            user_service.check_entity_access(chat["object_id"])
        else:
            raise PermissionDenied()
        return True
