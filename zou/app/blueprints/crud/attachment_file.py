from zou.app.models.attachment_file import AttachmentFile

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import tasks_service, user_service


class AttachmentFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AttachmentFile)


class AttachmentFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AttachmentFile)

    def check_read_permissions(self, instance):
        attachment_file = instance
        comment = tasks_service.get_comment(attachment_file["comment_id"])
        task = tasks_service.get_task(comment["object_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return True
