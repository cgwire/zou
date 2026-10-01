import ast
import pathlib
import unittest

EVENT_STREAM = pathlib.Path(__file__).parents[2] / "zou" / "event_stream.py"

# What a handler must not do before it checked the access to the room.
ROOM_WRITES = {"join_room", "emit", "_emit_people_updated"}


def function_node(function_name):
    """
    Return the module level function of given name of the event stream.
    The suite cannot import that module: on import it patches the process
    for gevent, builds an application of its own, and binds a Redis queue.
    So it is read as source.
    """
    tree = ast.parse(EVENT_STREAM.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"zou/event_stream.py has no {function_name}")


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


def returns_when_refused(statement):
    """
    Tell whether given statement is `if not _check_room_access(...):`
    followed by a return.
    """
    return (
        isinstance(statement, ast.If)
        and isinstance(statement.test, ast.UnaryOp)
        and isinstance(statement.test.op, ast.Not)
        and "_check_room_access" in called_names(statement.test)
        and any(isinstance(child, ast.Return) for child in statement.body)
    )


class EventStreamRoomAccessTestCase(unittest.TestCase):
    """
    A review room shows the shot and the preview on screen and the
    annotations drawn during the review. Opening or joining one runs the
    room check of the permissions service, which its own tests cover.
    """

    def test_the_room_access_runs_the_playlist_room_check(self):
        self.assertIn(
            "check_playlist_room_access",
            called_names(function_node("_check_room_access")),
        )

    def test_opening_and_joining_a_room_stop_when_refused(self):
        for handler in ("on_open_playlist", "on_join"):
            with self.subTest(handler=handler):
                checked = False
                for statement in function_node(handler).body:
                    if returns_when_refused(statement):
                        checked = True
                        break
                    self.assertFalse(called_names(statement) & ROOM_WRITES)
                self.assertTrue(checked)
