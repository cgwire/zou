"""
Realtime event stream (WebSocket) server.

This process fans out Zou events and hosts the collaborative "preview
rooms". SocketIO message delivery is shared across processes through the
Redis message_queue, BUT the presence state below (rooms_data,
user_rooms, server_stats) lives in this process's memory.

Consequence: run the event stream as a SINGLE process. It uses gevent
(one process, many greenlets) and is meant to be deployed that way; do
NOT put it behind several gunicorn workers or the room playback state
and connection counts diverge per worker. Horizontal scaling would
require moving that presence state into Redis (see ARCH-12 / MEM-8).
"""

from gevent import monkey

monkey.patch_all()

import functools

from flask import jsonify, request
from flask_jwt_extended import (
    get_current_user,
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)
from flask_socketio import (
    ConnectionRefusedError,
    SocketIO,
    disconnect,
    emit,
    join_room,
    leave_room,
)

from zou.app import config, create_app
from zou.app.utils.redis import get_redis_url
from zou.app.utils.socket_auth import (
    auth_error_message,
    load_socket_token,
    socket_token,
)

app = create_app()

from zou.app.services.permissions_service import check_playlist_room_access

server_stats = {"nb_connections": 0}
# The access token of the connections that sent it in the socket.io auth
# payload, by socket id. The other connections use the handshake request.
socket_tokens = {}
rooms_data = {}
user_rooms = {}

COMPARING_FIELDS = {
    "enable",
    "task_type",
    "revision",
    "mode",
    "comparison_preview_index",
}

redis_url = get_redis_url(config.KV_EVENTS_DB_INDEX)
socketio = SocketIO(
    logger=True, cors_allowed_origins=[], cors_credentials=False
)
socketio.init_app(app, message_queue=redis_url, async_mode="gevent")


def _check_room_access(playlist_id):
    """
    Check that the current user may join the review room of the given
    playlist (see check_playlist_room_access). Returns True if access is
    granted, False otherwise.
    """
    try:
        check_playlist_room_access(playlist_id)
        return True
    except Exception:
        return False


def _add_user_to_room_index(user_id, room_id):
    user_rooms.setdefault(user_id, set()).add(room_id)


def _remove_user_from_room_index(user_id, room_id):
    if user_id in user_rooms:
        user_rooms[user_id].discard(room_id)
        if not user_rooms[user_id]:
            del user_rooms[user_id]


def _validate_comparing(data):
    """
    Sanitize the comparing dict to only keep known fields.
    """
    if not isinstance(data, dict):
        return None
    return {k: v for k, v in data.items() if k in COMPARING_FIELDS}


def _get_empty_room(current_frame=0):
    return {
        "playlist_id": None,
        "user_id": None,
        "local_id": None,
        "people": [],
        "is_playing": False,
        "current_entity_id": None,
        "current_entity_index": None,
        "current_preview_file_id": None,
        "current_preview_file_index": None,
        "current_frame": current_frame,
        "is_repeating": None,
        "is_annotations_displayed": False,
        "is_zoom_enabled": False,
        "is_waveform_displayed": False,
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
    room_id = data.get("playlist_id", "0")
    return rooms_data.get(room_id, _get_empty_room()), room_id


def _leave_room(room_id, user_id):
    room = rooms_data.get(room_id, _get_empty_room())
    room["people"] = [p for p in room["people"] if p != user_id]
    _remove_user_from_room_index(user_id, room_id)
    if len(room["people"]) > 0:
        rooms_data[room_id] = room
    elif room_id in rooms_data:
        del rooms_data[room_id]
    _emit_people_updated(room_id, room["people"])
    return room


def _emit_people_updated(room_id, people):
    event_data = {
        "people": people,
        "playlist_id": room_id,
        "id": room_id,
    }
    emit("preview-room:room-people-updated", event_data, room=room_id)
    return event_data


def _update_room_playing_status(data, room):
    room["playlist_id"] = data.get("playlist_id", "")
    room["user_id"] = data.get("user_id", None)
    room["local_id"] = data.get("local_id", None)
    room["is_playing"] = data.get("is_playing", False)
    room["is_repeating"] = data.get("is_repeating", None)
    room["is_laser_mode"] = data.get("is_laser_mode", None)
    room["is_annotations_displayed"] = data.get(
        "is_annotations_displayed", False
    )
    room["is_zoom_enabled"] = data.get("is_zoom_enabled", False)
    room["is_waveform_displayed"] = data.get("is_waveform_displayed", False)
    room["current_entity_id"] = data.get("current_entity_id", None)
    room["current_entity_index"] = data.get("current_entity_index", None)
    room["current_preview_file_id"] = data.get("current_preview_file_id", None)
    room["current_preview_file_index"] = data.get(
        "current_preview_file_index", None
    )
    room["handle_in"] = data.get("handle_in", None)
    room["handle_out"] = data.get("handle_out", None)
    if "current_frame" in data:
        room["current_frame"] = data["current_frame"]
    if "comparing" in data:
        comparing = _validate_comparing(data["comparing"])
        if comparing is not None:
            room["comparing"] = comparing
    if "speed" in data and isinstance(data["speed"], (int, float)):
        room["speed"] = data["speed"]
    return room


@app.route("/", methods=["GET"])
def index():
    return jsonify({"name": f"{config.APP_NAME} Event stream"})


@app.route("/stats", methods=["GET"])
def stats():
    return jsonify(server_stats)


def _set_connection_identity(token):
    socket_tokens[request.sid] = token


def _authenticate():
    """
    Load the JWT of the connection for the current event: the token of the
    auth payload, or the cookie or the header of the handshake request.
    """
    token = socket_tokens.get(request.sid)
    if token is None:
        verify_jwt_in_request()
    else:
        load_socket_token(token)


def _connection_identity():
    return get_jwt_identity()


def authenticated(handler):
    """
    Run given handler only for an authenticated connection, as
    @jwt_required() did for the handshake request only. A connection whose
    token is not valid any more is closed: its reconnection then gets the
    reason in its connect_error.
    """

    @functools.wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            _authenticate()
        except Exception as error:
            message = auth_error_message(error)
            app.logger.info(f"Websocket event refused: {message}")
            disconnect()
            return None
        return handler(*args, **kwargs)

    return wrapper


@socketio.on("connect", namespace="/events")
def connected(auth):
    """
    Accept the handshake request (cookie or header), else the access token
    of the auth payload. A refused connection gets the reason in its
    connect_error. The refusal is the ConnectionRefusedError of
    flask_socketio: Flask-SocketIO hands any other exception, the builtin
    one included, to on_error, and the connection is then accepted.
    """
    try:
        try:
            verify_jwt_in_request()
        except Exception as request_error:
            token = socket_token(auth)
            if token is None:
                raise request_error
            load_socket_token(token)
            _set_connection_identity(token)
    except Exception as error:
        message = auth_error_message(error)
        app.logger.info(f"New websocket client refused: {message}")
        raise ConnectionRefusedError(message)
    server_stats["nb_connections"] += 1
    app.logger.info("New websocket client connected")


@socketio.on("disconnect", namespace="/events")
def disconnected(_):
    try:
        _authenticate()
        user_id = _connection_identity()
        room_ids = list(user_rooms.get(user_id, set()))
        for room_id in room_ids:
            _leave_room(room_id, user_id)
            leave_room(room_id, user_id)
        app.logger.info("Websocket client disconnected")
    except Exception:
        app.logger.info("Websocket client disconnected (no valid token)")
    socket_tokens.pop(request.sid, None)
    server_stats["nb_connections"] -= 1
    if server_stats["nb_connections"] < 0:
        server_stats["nb_connections"] = 0


@socketio.on_error("/events")
def on_error(error):
    server_stats["nb_connections"] -= 1
    if server_stats["nb_connections"] < 0:
        server_stats["nb_connections"] = 0
    app.logger.error(error)


@app.route("/rooms", methods=["GET", "POST"])
@jwt_required()
def rooms():
    return jsonify({"name": f"{config.APP_NAME} Review rooms"})


@socketio.on("preview-room:open-playlist", namespace="/events")
@authenticated
def on_open_playlist(data):
    """
    when a person opens the playlist page he immediately enters the
    websocket room. This way he can see in live which people are in the
    review room. The user still has to explicitly enter the review room
    to actually be in sync with the other users.
    """
    room, room_id = _get_room_from_data(data)
    if not _check_room_access(room_id):
        return
    rooms_data[room_id] = room
    join_room(room_id)
    _emit_people_updated(room_id, room["people"])


@socketio.on("preview-room:close-playlist", namespace="/events")
@authenticated
def on_close_playlist(data):
    """
    when a person closes the playlist page he immediately leaves the
    websocket room.
    """
    room_id = data.get("playlist_id", "0")
    leave_room(room_id)


@socketio.on("preview-room:join", namespace="/events")
@authenticated
def on_join(data):
    """
    When a person joins the review room, we notify all its members that a
    new person is added to the room.
    """
    user_id = _connection_identity()
    room, room_id = _get_room_from_data(data)
    if not _check_room_access(room_id):
        return
    if len(room["people"]) == 0:
        _update_room_playing_status(data, room)
    if user_id not in room["people"]:
        room["people"].append(user_id)
    room["playlist_id"] = room_id
    rooms_data[room_id] = room
    _add_user_to_room_index(user_id, room_id)
    _emit_people_updated(room_id, room["people"])
    emit("preview-room:room-updated", room, room=room_id)


@socketio.on("preview-room:leave", namespace="/events")
@authenticated
def on_leave(data):
    user_id = _connection_identity()
    room_id = data.get("playlist_id", "")
    _leave_room(room_id, user_id)


def _is_preview_user():
    """
    Preview accounts watch a review room, they do not drive it. The HTTP
    read-only rule does not apply here: request.method is the handshake GET.
    """
    return get_current_user().preview_project_id is not None


@socketio.on("preview-room:room-updated", namespace="/events")
@authenticated
def on_room_updated(data, only_newcomer=False):
    if _is_preview_user():
        return
    room, room_id = _get_room_from_data(data)
    rooms_data[room_id] = _update_room_playing_status(data, room)
    event_data = {"only_newcomer": only_newcomer, **rooms_data[room_id]}
    emit("preview-room:room-updated", event_data, room=room_id)


@socketio.on("preview-room:add-annotation", namespace="/events")
@authenticated
def on_add_annotation(data):
    if _is_preview_user():
        return
    room_id = data.get("playlist_id", "")
    emit("preview-room:add-annotation", data, room=room_id)


@socketio.on("preview-room:remove-annotation", namespace="/events")
@authenticated
def on_remove_annotation(data):
    if _is_preview_user():
        return
    room_id = data.get("playlist_id", "")
    emit("preview-room:remove-annotation", data, room=room_id)


@socketio.on("preview-room:update-annotation", namespace="/events")
@authenticated
def on_update_annotation(data):
    if _is_preview_user():
        return
    room_id = data.get("playlist_id", "")
    emit("preview-room:update-annotation", data, room=room_id)


@socketio.on("preview-room:change-version", namespace="/events")
@authenticated
def on_change_version(data):
    if _is_preview_user():
        return
    room_id = data.get("playlist_id", "")
    emit("preview-room:change-version", data, room=room_id)


@socketio.on("preview-room:panzoom-changed", namespace="/events")
@authenticated
def on_panzoom_changed(data):
    if _is_preview_user():
        return
    room_id = data.get("playlist_id", "")
    emit("preview-room:panzoom-changed", data, room=room_id)


@socketio.on("preview-room:comparison-panzoom-changed", namespace="/events")
@authenticated
def on_comparison_panzoom_changed(data):
    if _is_preview_user():
        return
    room_id = data.get("playlist_id", "")
    emit("preview-room:comparison-panzoom-changed", data, room=room_id)


if __name__ == "__main__":
    socketio.run(
        app,
        debug=False,
        host=config.EVENT_STREAM_HOST,
        port=config.EVENT_STREAM_PORT,
    )
