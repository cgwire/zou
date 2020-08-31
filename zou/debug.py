from flask_socketio import SocketIO
from zou.app import app

socketio = SocketIO(app)

if __name__ == "__main__":
    socketio.run(app, debug=True)
