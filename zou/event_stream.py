from flask import Flask, jsonify
from flask_jwt_extended import verify_jwt_in_request, JWTManager
from flask_socketio import SocketIO, disconnect
from zou.app import config
from zou.app.stores import auth_tokens_store

from gevent import monkey

monkey.patch_all()


def get_redis_url():
    redis_host = config.KEY_VALUE_STORE["host"]
    redis_port = config.KEY_VALUE_STORE["port"]
    return "redis://%s:%s/2" % (redis_host, redis_port)


def create_app(redis_url):
    socketio = SocketIO(logger=True)

    app = Flask(__name__)
    app.config.from_object(config)

    @app.route("/")
    def index():
        return jsonify({"name": "%s Event stream" % config.APP_NAME})

    @socketio.on("connect", namespace="/events")
    def connected():
        try:
            verify_jwt_in_request()
            app.logger.info("New websocket client connected")
        except Exception:
            app.logger.info("New websocket client failed to connect")
            disconnect()
            return False

    @socketio.on("disconnect", namespace="/events")
    def disconnected():
        app.logger.info("Websocket client disconnected")

    @socketio.on_error("/events")
    def on_error(error):
        app.logger.error(error)

    socketio.init_app(app, message_queue=redis_url, async_mode="gevent")
    return (app, socketio)


redis_url = get_redis_url()
(app, socketio) = create_app(redis_url)
jwt = JWTManager(app)  # JWT auth tokens


@jwt.token_in_blacklist_loader
def check_if_token_is_revoked(decrypted_token):
    return auth_tokens_store.is_revoked(decrypted_token)


if __name__ == "main":
    socketio.run(
        app,
        debug=False,
        host=config["EVENT_STREAM_HOST"],
        port=config["EVENT_STREAM_PORT"],
    )
