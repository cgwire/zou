import os

import flask_bcrypt
import pytest

# Must be set before zou.app is imported.
os.environ.setdefault("CACHE_TYPE", "simple")
os.environ.setdefault("BCRYPT_LOG_ROUNDS", "4")
os.environ.setdefault("DB_POOL_PRE_PING", "false")

_REAL_BCRYPT_FILES = {"test_auth_route.py", "test_auth_service.py"}

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
    """Bypass bcrypt verification during login for non-auth tests."""
    if request.fspath.basename not in _REAL_BCRYPT_FILES:
        monkeypatch.setattr(
            "flask_bcrypt.check_password_hash",
            lambda *args, **kwargs: True,
        )


def pytest_configure(config):
    """Create database schema once for the entire test session."""
    from zou.app import app
    from zou.app.utils import dbhelpers

    with app.app_context():
        dbhelpers.drop_all()
        dbhelpers.create_all()


def pytest_unconfigure(config):
    """Drop database schema at the end of the test session."""
    from zou.app import app
    from zou.app.utils import dbhelpers

    with app.app_context():
        dbhelpers.drop_all()
