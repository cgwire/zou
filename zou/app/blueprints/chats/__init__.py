from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.chats.resources import (
    ChatResource,
    ChatMessagesResource,
    ChatMessageResource,
)


routes = [
    ("/data/entities/<entity_id>/chat", ChatResource),
    ("/data/entities/<entity_id>/chat/messages", ChatMessagesResource),
    (
        "/data/entities/<entity_id>/chat/messages/<chat_message_id>",
        ChatMessageResource,
    ),
]

blueprint = Blueprint("chats", "chats")
api = configure_api_from_blueprint(blueprint, routes)
