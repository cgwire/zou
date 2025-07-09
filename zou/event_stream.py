from gevent import monkey

monkey.patch_all()

from flask import jsonify
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)
from flask_socketio import SocketIO, disconnect, join_room, leave_room, emit

from zou.app import config, app
from zou.app.utils.redis import get_redis_url

server_stats = {"nb_connections": 0}
rooms_data = {}

redis_url = get_redis_url(config.KV_EVENTS_DB_INDEX)
socketio = SocketIO(
    logger=True, cors_allowed_origins=[], cors_credentials=False
)
socketio.init_app(app, message_queue=redis_url, async_mode="gevent")


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
    room["people"] = list(set(room["people"]) - {user_id})
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
    room["user_id"] = data.get("user_id", False)
    room["local_id"] = data.get("local_id", False)
    room["is_playing"] = data.get("is_playing", False)
    room["is_repeating"] = data.get("is_repeating", False)
    room["is_laser_mode"] = data.get("is_laser_mode", False)
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
        room["comparing"] = data["comparing"]
    if "speed" in data:
        room["speed"] = data["speed"]
    return room


@app.route("/", methods=["GET"])
def index():
    return jsonify({"name": "%s Event stream" % config.APP_NAME})


@app.route("/stats", methods=["GET"])
def stats():
    return jsonify(server_stats)


@socketio.on("connect", namespace="/events")
def connected(_):
    try:
        verify_jwt_in_request()
        server_stats["nb_connections"] += 1
        app.logger.info("New websocket client connected")
    except Exception:
        app.logger.info("New websocket client failed to connect")
        disconnect()
        return False


@socketio.on("disconnect", namespace="/events")
def disconnected(_):
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        # Needed to be able to clear empty rooms
        tmp_rooms_data = dict(rooms_data)
        for room_id in tmp_rooms_data:
            _leave_room(room_id, user_id)
            leave_room(room_id, user_id)
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
    to actually be in sync with the other users.
    """
    room, room_id = _get_room_from_data(data)
    rooms_data[room_id] = room
    # Connect to the socketio room but dont add the user to the data of
    # the room.
    join_room(room_id)
    _emit_people_updated(room_id, room["people"])


@socketio.on("preview-room:close-playlist", namespace="/events")
@jwt_required()
def on_close_playlist(data):
    """
    when a person closes the playlist page he immediately leaves the
    websocket room.
    """
    room, room_id = _get_room_from_data(data)
    # Leave only the socketio room but dont remove the user from the data of
    # the room. This operation must be done via a leave event.
    leave_room(room_id)


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
    room["playlist_id"] = room_id
    rooms_data[room_id] = room
    _emit_people_updated(room_id, room["people"])
    emit("preview-room:room-updated", room, room=room_id)


@socketio.on("preview-room:leave", namespace="/events")
@jwt_required()
def on_leave(data):
    user_id = get_jwt_identity()
    room_id = data.get("playlist_id", "")
    _leave_room(room_id, user_id)


@socketio.on("preview-room:room-updated", namespace="/events")
@jwt_required()
def on_room_updated(data, only_newcomer=False):
    room, room_id = _get_room_from_data(data)
    rooms_data[room_id] = _update_room_playing_status(data, room)
    event_data = {"only_newcomer": only_newcomer, **rooms_data[room_id]}
    emit("preview-room:room-updated", event_data, room=room_id)


@socketio.on("preview-room:add-annotation", namespace="/events")
@jwt_required()
def on_add_annotation(data):
    room_id = data.get("playlist_id", "")
    emit("preview-room:add-annotation", data, room=room_id)


@socketio.on("preview-room:remove-annotation", namespace="/events")
@jwt_required()
def on_remove_annotation(data):
    room_id = data.get("playlist_id", "")
    emit("preview-room:remove-annotation", data, room=room_id)


@socketio.on("preview-room:update-annotation", namespace="/events")
@jwt_required()
def on_update_annotation(data):
    room_id = data.get("playlist_id", "")
    emit("preview-room:update-annotation", data, room=room_id)


@socketio.on("preview-room:change-version", namespace="/events")
@jwt_required()
def on_change_version(data):
    room_id = data.get("playlist_id", "")
    emit("preview-room:change-version", data, room=room_id)


@socketio.on("preview-room:panzoom-changed", namespace="/events")
@jwt_required()
def on_change_version(data):
    room_id = data.get("playlist_id", "")
    emit("preview-room:panzoom-changed", data, room=room_id)


@socketio.on("preview-room:comparison-panzoom-changed", namespace="/events")
@jwt_required()
def on_change_version(data):
    room_id = data.get("playlist_id", "")
    emit("preview-room:comparison-panzoom-changed", data, room=room_id)


if __name__ == "__main__":
    socketio.run(
        app,
        debug=False,
        host=config.EVENT_STREAM_HOST,
        port=config.EVENT_STREAM_PORT,
    )
