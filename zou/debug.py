import logging
from flask_socketio import SocketIO
from zou.app import app

FORMAT = "%(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
socketio = SocketIO(app)

if __name__ == "__main__":
    socketio.run(app, debug=True)
