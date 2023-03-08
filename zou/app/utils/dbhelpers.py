from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import close_all_sessions


def get_db_uri():
    from zou.app.config import DATABASE

    return URL.create(**DATABASE).render_as_string(hide_password=False)


def reset_all():
    """
    Check that database exist.
    """
    drop_all()
    return create_all()


def create_all():
    """
    Create all database tables.
    """
    from zou.app import db, config

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    if not database_exists(engine.url):
        create_database(engine.url)
    return db.create_all()


def drop_all():
    """
    Drop all database tables.
    """
    from zou.app import db

    db.session.flush()
    close_all_sessions()
    return db.drop_all()
