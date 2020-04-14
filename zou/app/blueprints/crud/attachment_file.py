from zou.app.models.attachment_file import AttachmentFile

from .base import BaseModelResource, BaseModelsResource


class AttachmentFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AttachmentFile)


class AttachmentFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AttachmentFile)
