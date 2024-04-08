from zou.app.models.chat_message import ChatMessage

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class ChatMessagesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ChatMessage)


class ChatMessageResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ChatMessage)
