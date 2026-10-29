import ast
import pathlib
import unittest

EVENT_STREAM = pathlib.Path(__file__).parents[2] / "zou" / "event_stream.py"


def module():
    """
    The suite cannot import the event stream (gevent patch, own app, Redis
    queue): it is read as source, as in test_event_stream_rooms.
    """
    return ast.parse(EVENT_STREAM.read_text())


def function_node(name):
    for node in module().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"zou/event_stream.py has no {name}")


def socket_handlers():
    """
    The handlers of the namespace, except connect: they run after the
    connection, thus they read the identity that the connection kept.
    """
    handlers = {}
    for node in module().body:
        if not isinstance(node, ast.FunctionDef) or node.name == "connected":
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "on"
            ):
                handlers[node.name] = node
    return handlers


def called_names(node):
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            function = child.func
            if isinstance(function, ast.Attribute):
                names.add(function.attr)
            elif isinstance(function, ast.Name):
                names.add(function.id)
    return names


def raised_names(node):
    """
    The names raised as such: ConnectionRefusedError for
    `raise ConnectionRefusedError(message)`, but nothing for
    `raise builtins.ConnectionRefusedError(message)`.
    """
    return {
        child.exc.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Raise)
        and isinstance(child.exc, ast.Call)
        and isinstance(child.exc.func, ast.Name)
    }


def imported_from(name):
    """
    The module given name is imported from, None for a builtin.
    """
    for node in module().body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return node.module
    return None


def decorator_names(node):
    names = set()
    for decorator in node.decorator_list:
        target = (
            decorator.func if isinstance(decorator, ast.Call) else decorator
        )
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


class EventStreamAuthTestCase(unittest.TestCase):
    """
    A client without a cookie or a header (a browser WebSocket, the Kitsu
    File Manager) sends its token in the socket.io auth payload.
    """

    def test_connect_reads_the_auth_payload(self):
        node = function_node("connected")
        self.assertEqual([arg.arg for arg in node.args.args], ["auth"])
        self.assertIn("socket_token", called_names(node))
        self.assertIn("load_socket_token", called_names(node))

    def test_connect_keeps_the_identity_of_the_connection(self):
        node = function_node("connected")
        self.assertIn("_set_connection_identity", called_names(node))

    def test_a_refused_connection_tells_why(self):
        node = function_node("connected")
        self.assertIn("auth_error_message", called_names(node))
        self.assertIn("ConnectionRefusedError", called_names(node))

    def test_a_refused_connection_raises_the_socketio_error(self):
        """
        flask-socketio hands any other exception of the connect handler, the
        builtin ConnectionRefusedError included, to the on_error handler of
        the namespace, and the connection is then accepted.
        """
        node = function_node("connected")
        self.assertIn("ConnectionRefusedError", raised_names(node))
        self.assertIn(
            imported_from("ConnectionRefusedError"),
            ["flask_socketio", "socketio.exceptions"],
        )

    def test_the_handlers_use_the_identity_of_the_connection(self):
        handlers = socket_handlers()
        self.assertIn("on_join", handlers)
        self.assertIn("disconnected", handlers)
        for name, node in handlers.items():
            self.assertNotIn("jwt_required", decorator_names(node), name)
            self.assertNotIn("get_jwt_identity", called_names(node), name)
            self.assertNotIn("verify_jwt_in_request", called_names(node), name)

    def test_the_room_handlers_need_a_connection_identity(self):
        for name, node in socket_handlers().items():
            if name != "disconnected":
                self.assertIn("authenticated", decorator_names(node), name)
