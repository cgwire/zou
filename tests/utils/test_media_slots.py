import threading
import unittest

from flask import Flask

from zou.app.utils import media_slots


def build_app(limit, wait_timeout=1):
    """
    A bare app with one media route that blocks until told to finish,
    and one API route that answers right away.
    """
    app = Flask(__name__)
    app.started = threading.Event()
    app.finish = threading.Event()

    @app.route("/pictures/thumbnails/preview-files/<instance_id>.png")
    def thumbnail(instance_id):
        app.started.set()
        app.finish.wait(5)
        return "png"

    @app.route("/pictures/preview-files/<instance_id>", methods=["POST"])
    def upload(instance_id):
        return "uploaded"

    @app.route("/movies/low/preview-files/<instance_id>.mp4")
    def movie(instance_id):
        raise RuntimeError("storage down")

    @app.route("/data/projects")
    def projects():
        return "[]"

    media_slots.init_media_slots(app, limit, wait_timeout)
    return app


def hold_the_slot(app):
    """
    Start a media request in a thread and return once it holds the slot.
    """
    thread = threading.Thread(
        target=app.test_client().get,
        args=["/pictures/thumbnails/preview-files/a.png"],
    )
    thread.start()
    app.started.wait(5)
    return thread


class MediaSlotsTestCase(unittest.TestCase):
    def test_is_media_request(self):
        app = Flask(__name__)
        cases = [
            ("GET", "/pictures/thumbnails/preview-files/a.png", True),
            ("HEAD", "/movies/low/preview-files/a.mp4", True),
            ("POST", "/pictures/preview-files/a", False),
            ("GET", "/data/projects", False),
            ("GET", "/picturesque", False),
        ]
        for method, path, expected in cases:
            with app.test_request_context(path, method=method):
                self.assertEqual(media_slots.is_media_request(), expected)

    def test_disabled_registers_nothing(self):
        app = build_app(0)
        self.assertEqual(app.before_request_funcs, {})
        self.assertEqual(app.teardown_request_funcs, {})

    def test_full_slots_do_not_block_the_api(self):
        app = build_app(1, wait_timeout=5)
        thread = hold_the_slot(app)
        try:
            response = app.test_client().get("/data/projects")
            self.assertEqual(response.status_code, 200)
            response = app.test_client().post("/pictures/preview-files/b")
            self.assertEqual(response.status_code, 200)
        finally:
            app.finish.set()
            thread.join(5)

    def test_media_request_waits_for_a_slot(self):
        app = build_app(1, wait_timeout=5)
        thread = hold_the_slot(app)
        threading.Timer(0.2, app.finish.set).start()
        response = app.test_client().get(
            "/pictures/thumbnails/preview-files/b.png"
        )
        thread.join(5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"png")

    def test_media_request_gives_up_after_the_wait_timeout(self):
        app = build_app(1, wait_timeout=0.05)
        thread = hold_the_slot(app)
        try:
            response = app.test_client().get(
                "/pictures/thumbnails/preview-files/b.png"
            )
        finally:
            app.finish.set()
            thread.join(5)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.headers["Retry-After"],
            str(media_slots.RETRY_AFTER),
        )
        self.assertTrue(response.cache_control.no_store)
        self.assertTrue(response.json["error"])

    def test_slot_is_released_after_each_request(self):
        app = build_app(1, wait_timeout=0.05)
        app.finish.set()
        client = app.test_client()
        for _ in range(3):
            response = client.get("/pictures/thumbnails/preview-files/a.png")
            self.assertEqual(response.status_code, 200)

    def test_slot_is_released_when_the_view_fails(self):
        app = build_app(1, wait_timeout=0.05)
        app.finish.set()
        client = app.test_client()
        for _ in range(2):
            response = client.get("/movies/low/preview-files/a.mp4")
            self.assertEqual(response.status_code, 500)
        response = client.get("/pictures/thumbnails/preview-files/a.png")
        self.assertEqual(response.status_code, 200)

    def test_zero_wait_timeout_waits_forever(self):
        app = build_app(1, wait_timeout=0)
        thread = hold_the_slot(app)
        threading.Timer(0.2, app.finish.set).start()
        response = app.test_client().get(
            "/pictures/thumbnails/preview-files/b.png"
        )
        thread.join(5)
        self.assertEqual(response.status_code, 200)
