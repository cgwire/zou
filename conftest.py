import os

# Must be set before zou.app is imported.
os.environ.setdefault("CACHE_TYPE", "simple")
os.environ.setdefault("BCRYPT_LOG_ROUNDS", "4")
os.environ.setdefault("DB_POOL_PRE_PING", "false")


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
