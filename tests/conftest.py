import os
import tempfile

import flask_bcrypt
import pytest
from sqlalchemy_utils import create_database, database_exists

from tests.fake_stores import seed_fake_stores

# Must be set before zou.app is imported.
os.environ.setdefault("CACHE_TYPE", "simple")
os.environ.setdefault("BCRYPT_LOG_ROUNDS", "4")
os.environ.setdefault("DB_POOL_PRE_PING", "false")

# Under pytest-xdist each worker (gw0, gw1, ...) is a process of its own
# building its own app: give it its own database, so the rows one worker
# writes and the truncations it runs between classes stay invisible to
# the others. A serial run keeps the plain name.
_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER")
if _XDIST_WORKER:
    _database = os.environ.get("DB_DATABASE", "zoudb")
    os.environ["DB_DATABASE"] = f"{_database}_{_XDIST_WORKER}"

# Force isolated preview and temp stores before any zou module reads the
# config. Without this, running the tests from a working checkout resolves
# PREVIEW_FOLDER to ./previews, a live development store, which route
# tests then write into and which teardowns may remove entirely. TMP_DIR
# would be the one folder every worker shares, and three tests assert on
# its exact content.
os.environ["PREVIEW_FOLDER"] = tempfile.mkdtemp(prefix="zou-test-previews-")
os.environ["TMP_DIR"] = tempfile.mkdtemp(prefix="zou-test-tmp-")

# flask_bcrypt module-level functions create a Bcrypt() instance without
# the app, so BCRYPT_LOG_ROUNDS is ignored and rounds default to 12.
# Wrap them to force 4 rounds in tests.
_TEST_ROUNDS = 4
_orig_generate = flask_bcrypt.generate_password_hash


def _fast_generate(password, rounds=None):
    return _orig_generate(password, rounds=rounds or _TEST_ROUNDS)


flask_bcrypt.generate_password_hash = _fast_generate


@pytest.fixture(autouse=True)
def _skip_bcrypt_check(request, monkeypatch):
    """
    Bypass bcrypt verification during login, since paying ~100 ms per
    login would dominate the suite. A test that asserts on the
    verification itself opts out with the real_bcrypt marker, set at
    module level: pytestmark = pytest.mark.real_bcrypt.
    """
    if request.node.get_closest_marker("real_bcrypt") is None:
        monkeypatch.setattr(
            "flask_bcrypt.check_password_hash",
            lambda *args, **kwargs: True,
        )


def _is_xdist_controller(config):
    """
    True in the process that only dispatches the tests to pytest-xdist
    workers. It runs no test, so it builds no app and touches no
    database: each worker runs these hooks for itself.
    """
    dispatching = bool(getattr(config.option, "numprocesses", None))
    return dispatching and not hasattr(config, "workerinput")


def pytest_configure(config):
    """
    Build the application explicitly and create the database schema once
    for the entire test session. Importing zou.app no longer builds the
    app as a side effect: the suite owns the moment (and the config
    environment) the app is wired with.
    """
    if _is_xdist_controller(config):
        return

    from zou.app import create_app
    from zou.app.utils import dbhelpers

    seed_fake_stores()
    app = create_app()

    # Register the admin blueprint so it can be tested.
    from zou.app.blueprints.admin import blueprint as admin_blueprint

    if "admin" not in app.blueprints:
        app.register_blueprint(admin_blueprint)

    with app.app_context():
        from zou.app import db

        # A worker database is created on first use: nothing prepares it
        # when a developer starts a parallel run.
        if not database_exists(db.engine.url):
            create_database(db.engine.url)
        dbhelpers.drop_all()
        db.engine.dispose()
        dbhelpers.create_all()
        db.engine.dispose()


def pytest_unconfigure(config):
    """
    Drop the database schema at the end of the test session, and the
    database itself for a pytest-xdist worker: created on first use, it
    would otherwise outlive the run, one per core, on a developer's
    server. The temp folders of the process go with them.
    """
    import shutil

    for folder in (os.environ["PREVIEW_FOLDER"], os.environ["TMP_DIR"]):
        shutil.rmtree(folder, ignore_errors=True)
    if _is_xdist_controller(config):
        return

    from sqlalchemy.orm import close_all_sessions
    from sqlalchemy_utils import drop_database

    from zou.app import app, db
    from zou.app.utils import dbhelpers

    with app.app_context():
        if _XDIST_WORKER:
            close_all_sessions()
            db.engine.dispose()
            drop_database(db.engine.url)
        else:
            dbhelpers.drop_all()
