from flask import Flask, jsonify
from flask_jwt_extended import verify_jwt_in_request, JWTManager, current_user
from flask_socketio import SocketIO, disconnect, send, join_room, emit
from zou.app import config
from zou.app.stores import auth_tokens_store

rooms_data = {}


def _get_empty_room():
    # TODO (?) :
    # - handle updating the playlist order, adding/removing items
    # - sync playing speed
    # - sync number of frames per image
    # - sync annotations
    #   (maybe already done, see event preview-file:annotation-update)
    return {
        "people": [],
        "is_playing": False,
        "current_entity_index": None,
        "current_frame_number": 0,
        "is_repeating": None,
        "comparing": {
            "enable": False,
            "task_type": None,
            "revision": None,
            "mode": "sidebyside",
            "comparison_preview_index": 0
        }
    }


def create_app():
    socketio = SocketIO(logger=True)

    app = Flask(__name__)
    app.config.from_object(config)

    @app.route("/", methods=["GET", "POST"])
    def index():
        return jsonify({"name": "%s Review rooms" % config.APP_NAME})

    @socketio.on("connect", namespace="/events")
    def connected():
        app.logger.error("New websocket client connected")
        # try:
        #     verify_jwt_in_request()
        #     app.logger.info("New websocket client connected")
        # except Exception:
        #     app.logger.info("New websocket client failed to connect")
        #     disconnect()
        #     return False

    @socketio.on("disconnect", namespace="/events")
    def disconnected():
        app.logger.info("Websocket client disconnected")

    @socketio.on_error("/events")
    def on_error(error):
        app.logger.error(error)

    @socketio.on("preview-room:open-playlist", namespace="/events")
    def on_open_playlist(data):
        """
        when a person opens the playlist page he immediately enters the
        websocket room. This way he can see in live which people are in the
        review room. The user still has to explicitly enter the review room
        to actually be in sync with the other users
        """
        room_id = data["playlist_id"]
        room = rooms_data.get(room_id, _get_empty_room())
        rooms_data[room_id] = room
        join_room(room_id)
        emit("preview-room:room-people-updated", room, room=room_id)

    def _update_room_playing_status(data, room):
        room["is_playing"] = data.get("is_playing", False)
        room["is_repeating"] = data.get("is_repeating", False)
        room["current_entity_index"] = data["current_entity_index"]
        if "current_frame_number" in data:
            room["current_frame_number"] = data["current_frame_number"]
        if "comparing" in data:
            room["comparing"] = data["comparing"]

        return room

    @socketio.on("preview-room:sync-newcomer", namespace="/events")
    def on_sync_newcomer(data):
        """
        once a new person joins the room, all the people in the room are alerted
        (see `on_join` and the emitted preview-room:room-people-updated)
        we then listen for their replies, telling the newcomer where they are
        in the playlist
        """
        on_playing_status_updated(data, only_newcomer=True)

    @socketio.on("preview-room:join", namespace="/events")
    def on_join(data):
        """
        When a person joins the review room, we notify all its members that a
        new person is added to the room.
        All the members will then send back the current status of the playlist,
        so that the newcomer will be in sync
        """
        user_id = data["user_id"]
        room_id = data["playlist_id"]
        room = rooms_data.get(room_id, _get_empty_room())
        room["people"] = list(set(room["people"] + [user_id]))
        rooms_data[room_id] = room
        emit("preview-room:room-people-updated", room, room=room_id)

    @socketio.on("preview-room:leave", namespace="/events")
    def on_leave(data):
        user_id = data["user_id"]
        room_id = data["playlist_id"]
        room = rooms_data.get(room_id, _get_empty_room())
        room["people"] = list(set(room["people"]) - {user_id})
        rooms_data[room_id] = room
        emit("preview-room:room-people-updated", room, room=room_id)

    @socketio.on("preview-room:update-playing-status", namespace="/events")
    def on_playing_status_updated(data, only_newcomer=False):
        room_id = data["playlist_id"]
        room = rooms_data.get(room_id, _get_empty_room())
        rooms_data[room_id] = _update_room_playing_status(data, room)

        event_data = {"only_newcomer": only_newcomer, **rooms_data[room_id]}
        emit("preview-room:room-updated", event_data, room=room_id)

    socketio.init_app(app, async_mode="gevent")
    return app, socketio


(app, socketio) = create_app()
jwt = JWTManager(app)  # JWT auth tokens


@jwt.token_in_blacklist_loader
def check_if_token_is_revoked(decrypted_token):
    return auth_tokens_store.is_revoked(decrypted_token)


if __name__ == "__main__":
    socketio.run(
        app,
        debug=False,
        host=config.EVENT_STREAM_HOST,
        port=config.EVENT_STREAM_PORT,
    )
