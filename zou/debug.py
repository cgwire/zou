from gevent import monkey

monkey.patch_all()

from zou.app import app, config
from flask_socketio import SocketIO
import logging


FORMAT = "%(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
socketio = SocketIO(app, cors_allowed_origins=[], cors_credentials=False)

if __name__ == "__main__":
    print(
        "The Kitsu API server is listening on port %s..." % config.DEBUG_PORT
    )
    socketio.run(app, port=config.DEBUG_PORT, debug=True)
