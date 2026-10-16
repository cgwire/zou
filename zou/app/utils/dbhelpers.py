from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import close_all_sessions
from sqlalchemy_utils import create_database, database_exists


def create_all():
    """
    Create all database tables.
    """
    from zou.app import config, db

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    if not database_exists(engine.url):
        create_database(engine.url)
    return db.create_all()


def drop_all():
    """
    Drop all database tables. Uses CASCADE to handle foreign keys from
    plugin tables that may not be tracked in db.metadata.
    """
    from zou.app import db

    db.session.flush()
    close_all_sessions()
    with db.engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()


def is_init():
    """
    Check if database is initialized.
    """
    from zou.app import db
    from zou.app.models.project_status import ProjectStatus

    return (
        inspect(db.engine).has_table("person")
        and db.session.query(ProjectStatus).count() == 2
    )
