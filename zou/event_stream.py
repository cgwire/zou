from gevent import monkey

monkey.patch_all()

from flask import Flask, jsonify
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
    JWTManager,
)
from flask_socketio import SocketIO, disconnect, join_room, emit
from flask_sqlalchemy import SQLAlchemy
from zou.app import config
from zou.app.stores import auth_tokens_store
from zou.app.utils.monitoring import init_monitoring
from zou.app.utils.flask import ORJSONProvider
from zou.app.services import persons_service

server_stats = {"nb_connections": 0}
rooms_data = {}

# Review room helpers


def _get_empty_room(current_frame=0):
    return {
        "people": [],
        "is_playing": False,
        "current_entity_index": None,
        "current_preview_file_id": None,
        "current_frame": current_frame,
        "is_repeating": None,
        "is_laser_mode": None,
        "handle_in": None,
        "handle_out": None,
        "speed": None,
        "comparing": {
            "enable": False,
            "task_type": None,
            "revision": None,
            "mode": "sidebyside",
            "comparison_preview_index": 0,
        },
    }


def _get_room_from_data(data):
    room_id = data["playlist_id"]
    return rooms_data.get(room_id, _get_empty_room()), room_id


def _leave_room(room_id, user_id):
    room = rooms_data.get(room_id, _get_empty_room())
    room["people"] = list(set(room["people"]) - {user_id})
    if len(room["people"]) > 0:
        rooms_data[room_id] = room
    else:
        del rooms_data[room_id]
    emit("preview-room:room-people-updated", room, room=room_id)


def _update_room_playing_status(data, room):
    room["is_playing"] = data.get("is_playing", False)
    room["is_repeating"] = data.get("is_repeating", False)
    room["is_laser_mode"] = data.get("is_laser_mode", False)
    room["current_entity_index"] = data["current_entity_index"]
    room["handle_in"] = data.get("handle_in", None)
    room["handle_out"] = data.get("handle_out", None)
    if "current_preview_file_id" in data:
        room["current_preview_file_id"] = data["current_preview_file_id"]
    if "current_frame" in data:
        room["current_frame"] = data["current_frame"]
    if "comparing" in data:
        room["comparing"] = data["comparing"]
    if "speed" in data:
        room["speed"] = data["speed"]
    return room


# Database helpers


def get_redis_url():
    redis_host = config.KEY_VALUE_STORE["host"]
    redis_port = config.KEY_VALUE_STORE["port"]
    db_index = config.KV_EVENTS_DB_INDEX
    return "redis://%s:%s/%s" % (redis_host, redis_port, db_index)


# Routes


def set_info_routes(socketio, app):
    @app.route("/", methods=["GET"])
    def index():
        return jsonify({"name": "%s Event stream" % config.APP_NAME})

    @app.route("/stats", methods=["GET"])
    def stats():
        return jsonify(server_stats)


def set_application_routes(socketio, app):
    @socketio.on("connect", namespace="/events")
    def connected():
        try:
            verify_jwt_in_request()
            server_stats["nb_connections"] += 1
            app.logger.info("New websocket client connected")
        except Exception:
            app.logger.info("New websocket client failed to connect")
            disconnect()
            return False

    @socketio.on("disconnect", namespace="/events")
    def disconnected():
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            # needed to be able to clear empty rooms
            tmp_rooms_data = dict(rooms_data)
            for room_id in tmp_rooms_data:
                _leave_room(room_id, user_id)
            server_stats["nb_connections"] -= 1
            app.logger.info("Websocket client disconnected")
        except Exception:
            pass

    @socketio.on_error("/events")
    def on_error(error):
        server_stats["nb_connections"] -= 1
        if server_stats["nb_connections"] < 0:
            server_stats["nb_connections"] = 0
        app.logger.error(error)


def set_playlist_room_routes(socketio, app):
    @app.route("/rooms", methods=["GET", "POST"])
    @jwt_required()
    def rooms():
        return jsonify({"name": "%s Review rooms" % config.APP_NAME})

    @socketio.on("preview-room:open-playlist", namespace="/events")
    @jwt_required()
    def on_open_playlist(data):
        """
        when a person opens the playlist page he immediately enters the
        websocket room. This way he can see in live which people are in the
        review room. The user still has to explicitly enter the review room
        to actually be in sync with the other users
        """
        room, room_id = _get_room_from_data(data)
        rooms_data[room_id] = room
        join_room(room_id)
        emit("preview-room:room-people-updated", room, room=room_id)

    @socketio.on("preview-room:join", namespace="/events")
    @jwt_required()
    def on_join(data):
        """
        When a person joins the review room, we notify all its members that a
        new person is added to the room.
        """
        user_id = get_jwt_identity()
        room, room_id = _get_room_from_data(data)
        if len(room["people"]) == 0:
            _update_room_playing_status(data, room)
        room["people"] = list(set(room["people"] + [user_id]))
        rooms_data[room_id] = room
        emit("preview-room:room-people-updated", room, room=room_id)

    @socketio.on("preview-room:leave", namespace="/events")
    @jwt_required()
    def on_leave(data):
        user_id = get_jwt_identity()
        room_id = data["playlist_id"]
        _leave_room(room_id, user_id)

    @socketio.on("preview-room:update-playing-status", namespace="/events")
    @jwt_required()
    def on_playing_status_updated(data, only_newcomer=False):
        room, room_id = _get_room_from_data(data)
        rooms_data[room_id] = _update_room_playing_status(data, room)
        event_data = {"only_newcomer": only_newcomer, **rooms_data[room_id]}
        emit("preview-room:room-updated", event_data, room=room_id)

    @socketio.on("preview-room:add-annotation", namespace="/events")
    @jwt_required()
    def on_add_annotation(data):
        room_id = data["playlist_id"]
        emit("preview-room:add-annotation", data, room=room_id)

    @socketio.on("preview-room:remove-annotation", namespace="/events")
    @jwt_required()
    def on_remove_annotation(data):
        room_id = data["playlist_id"]
        emit("preview-room:remove-annotation", data, room=room_id)

    @socketio.on("preview-room:update-annotation", namespace="/events")
    @jwt_required()
    def on_update_annotation(data):
        room_id = data["playlist_id"]
        emit("preview-room:update-annotation", data, room=room_id)

    @socketio.on("preview-room:change-version", namespace="/events")
    @jwt_required()
    def on_change_version(data):
        room_id = data["playlist_id"]
        emit("preview-room:change-version", data, room=room_id)

    return app


def create_app():
    redis_url = get_redis_url()
    socketio = SocketIO(
        logger=True, cors_allowed_origins=[], cors_credentials=False
    )
    app = Flask(__name__)
    app.json = ORJSONProvider(app)
    app.config.from_object(config)
    init_monitoring(app)
    db = SQLAlchemy(app)
    app.extensions["sqlalchemy"].db = db
    set_info_routes(socketio, app)
    set_application_routes(socketio, app)
    set_playlist_room_routes(socketio, app)
    socketio.init_app(app, message_queue=redis_url, async_mode="gevent")
    return (app, socketio)


def set_auth(app):
    jwt = JWTManager(app)  # JWT auth tokens

    @jwt.token_in_blocklist_loader
    def check_if_token_is_revoked(_, payload):
        identity_type = payload.get("identity_type")
        if identity_type == "person":
            return auth_tokens_store.is_revoked(payload["jti"])
        elif identity_type in ["bot", "person_api"]:
            return persons_service.is_jti_revoked(payload["jti"])
        else:
            return True


(app, socketio) = create_app()
set_auth(app)


if __name__ == "__main__":
    socketio.run(
        app,
        debug=False,
        host=config.EVENT_STREAM_HOST,
        port=config.EVENT_STREAM_PORT,
    )
