from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import close_all_sessions
from sqlalchemy_utils import create_database, database_exists


def create_all():
    """
    Create the database if it does not exist, then create all the tables
    of db.metadata.
    """
    from zou.app import config, db

    engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
    if not database_exists(engine.url):
        create_database(engine.url)
    return db.create_all()


def drop_all():
    """
    Drop the public schema with all its contents, then create it again
    empty. CASCADE also removes the plugin tables that db.metadata does not
    track.
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
    Tell whether the person table exists and the database stores at least
    one project status.
    """
    from zou.app import db
    from zou.app.models.project_status import ProjectStatus

    return (
        inspect(db.engine).has_table("person")
        and db.session.query(ProjectStatus).count() > 0
    )


def ping():
    """
    Run a query that reads nothing, to check that the database answers.
    """
    from zou.app import db

    db.session.execute(text("SELECT 1"))
