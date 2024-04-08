from zou.app.models.chat import Chat

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class ChatsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Chat)


class ChatResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Chat)
