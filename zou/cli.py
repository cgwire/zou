#!/usr/bin/env python
import os
import sys
import flask_migrate
import click

from sqlalchemy.exc import IntegrityError

from zou.app.utils import dbhelpers, auth, commands
from zou.app.services import persons_service, auth_service
from zou.app.services.exception import (
    IsUserLimitReachedException,
    PersonNotFoundException,
    TwoFactorAuthenticationNotEnabledException,
)
from zou.app import app, config


@click.group()
def cli():
    pass


@cli.command()
def init_db():
    "Creates datababase table (database must be created through PG client)."

    print("Creating database and tables...")
    with app.app_context():
        import zou

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.upgrade(directory=directory)
    print("Database and tables created.")


@cli.command()
@click.option("--message", default="")
def migrate_db(message):
    """
    Generate migration files to describe a new revision of the database schema
    (for development only).
    """
    with app.app_context():
        import zou

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.migrate(directory=directory, message=message)


@cli.command()
@click.option("--revision", default=None)
def downgrade_db(revision):
    """
    Downgrade db to previous revision of the database schema
    (for development only). For revision you can use an hash or a relative migration identifier.
    """
    with app.app_context():
        import zou

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.downgrade(directory=directory, revision=revision)


@cli.command()
def clear_db():
    "Drop all tables from database"

    with app.app_context():
        import zou

        print("Deleting database and tables...")
        dbhelpers.drop_all()
        print("Database and tables deleted.")

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.stamp(directory=directory, revision="base")


@cli.command()
def reset_db():
    "Drop all tables then recreates them."
    with app.app_context():
        import zou

        print("Deleting database and tables...")
        dbhelpers.drop_all()
        print("Database and tables deleted.")

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.stamp(directory=directory, revision="base")

        flask_migrate.upgrade(directory=directory)
        print("Database and tables created.")


@cli.command()
def upgrade_db():
    "Upgrade database schema."
    with app.app_context():
        import zou

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.upgrade(directory=directory)


@cli.command()
@click.option("--revision", default=None)
def stamp_db(revision):
    "Set the database schema revision to current one."
    with app.app_context():
        import zou

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        if revision is None:
            flask_migrate.stamp(directory=directory)
        else:
            flask_migrate.stamp(directory=directory, revision=revision)


@cli.command()
def reset_migrations():
    "Set the database schema revision to first one."
    with app.app_context():
        import zou

        directory = os.path.join(os.path.dirname(zou.__file__), "migrations")
        flask_migrate.stamp(directory=directory, revision="base")


@cli.command()
@click.argument("email")
@click.option("--password", required=True, default=None)
def create_admin(email, password):
    """
    Create an admin user to allow usage of the API when database is empty.
    """
    try:
        person = persons_service.get_person_by_email(email)
        if person["role"] != "admin":
            persons_service.update_person(person["id"], {"role": "admin"})
            print("Existing user's role has been upgraded to 'admin'.")
    except PersonNotFoundException:
        try:
            auth.validate_password(password)
            # Allow "admin@example.com" to be invalid.
            if email != "admin@example.com":
                auth.validate_email(email)
            password = auth.encrypt_password(password)
            persons_service.create_person(
                email, password, "Super", "Admin", role="admin"
            )
            print("Admin successfully created.")
        except auth.PasswordTooShortException:
            print("Password is too short.")
            sys.exit(1)
        except auth.EmailNotValidException:
            print("Email is not valid.")
            sys.exit(1)


@cli.command()
def clean_auth_tokens():
    "Remove revoked and expired tokens."
    commands.clean_auth_tokens()


@cli.command()
def clear_all_auth_tokens():
    "Remove all authentication tokens."
    commands.clear_all_auth_tokens()


@cli.command()
def init_data():
    "Generates minimal data set required to run Kitsu."
    commands.init_data()


@cli.command()
@click.argument("email_or_desktop_login")
def disable_two_factor_authentication(email_or_desktop_login):
    """
    Disable two factor authentication for given user.
    """
    try:
        person_id = persons_service.get_person_by_email_dekstop_login(
            email_or_desktop_login
        )
        auth_service.disable_two_factor_authentication_for_person(person_id)
        print(
            f"Two factor authentication disabled for {email_or_desktop_login}."
        )
    except PersonNotFoundException:
        print(f"Email ({email_or_desktop_login}) not listed in database.")
        sys.exit(1)
    except TwoFactorAuthenticationNotEnabledException:
        print(
            f"Two factor authentication can't be disabled for {email_or_desktop_login} because it's not activated."
        )
        sys.exit(1)


@cli.command()
@click.argument("email")
@click.option("--password", required=True, default=None)
def change_password(email, password):
    """
    Change the password of given user.
    """
    try:
        auth.validate_password(password)
        password = auth.encrypt_password(password)
        persons_service.update_password(email, password)
        print("Password changed for %s" % email)
    except auth.PasswordTooShortException:
        print("The password is too short.")
        sys.exit(1)


@cli.command()
@click.argument("email")
@click.option("--unactive", is_flag=True, default=False)
def set_person_as_active(email, unactive):
    """
    Set a person as active.
    """
    try:
        if persons_service.is_user_limit_reached():
            raise IsUserLimitReachedException
        person = persons_service.get_person_by_email_raw(email)
        person.update({"active": not unactive})
        print(
            f'Person {email} is set as an {"active" if not unactive else "unactive"} user.'
        )
    except IsUserLimitReachedException:
        print(f"User limit reached (limit {config.USER_LIMIT}).")
        sys.exit(1)
    except PersonNotFoundException:
        print(f"Email ({email}) not listed in database.")
        sys.exit(1)


@cli.command()
def sync_with_ldap_server():
    """
    For each user account in your LDAP server, it creates a new user.
    """
    try:
        if persons_service.is_user_limit_reached():
            raise IsUserLimitReachedException
        commands.sync_with_ldap_server()
    except IsUserLimitReachedException:
        print("User limit reached (limit %i)." % config.USER_LIMIT)
        sys.exit(1)


@cli.command()
@click.option("--target", default="http://localhost:5000")
@click.option("--project")
@click.option("--no-projects", is_flag=True)
@click.option("--with-events", is_flag=True)
@click.option("--only-projects", is_flag=True)
def sync_full(
    target,
    project=None,
    with_events=False,
    no_projects=False,
    only_projects=False,
):
    """
    Retrieve all data from target instance. It expects that credentials to
    connect to target instance are given through SYNC_LOGIN and SYNC_PASSWORD
    environment variables.
    """
    print("Start syncing.")
    login = os.getenv("SYNC_LOGIN")
    password = os.getenv("SYNC_PASSWORD")
    commands.import_data_from_another_instance(
        target,
        login,
        password,
        project=project,
        with_events=with_events,
        no_projects=no_projects,
        only_projects=only_projects,
    )
    print("Syncing ended.")


@cli.command()
@click.option("--target", default="http://localhost:5000")
@click.option("--project")
def sync_full_files(target, project=None):
    """
    Retrieve all files from target instance. It expects that credentials to
    connect to target instance are given through SYNC_LOGIN and SYNC_PASSWORD
    environment variables.
    """
    print("Start syncing.")
    login = os.getenv("SYNC_LOGIN")
    password = os.getenv("SYNC_PASSWORD")
    commands.import_files_from_another_instance(
        target, login, password, project=project
    )
    print("Syncing ended.")


@cli.command()
@click.option("--event-target", default="http://localhost:8080")
@click.option("--target", default="http://localhost:8080/api")
@click.option("--logs-directory", default=None)
def sync_changes(event_target, target, logs_directory):
    """
    Run a daemon that import data related to any change happening on target
    instance. It expects that credentials to connect to target instance are
    given through SYNC_LOGIN and SYNC_PASSWORD environment variables.
    """
    login = os.getenv("SYNC_LOGIN")
    password = os.getenv("SYNC_PASSWORD")
    commands.run_sync_change_daemon(
        event_target, target, login, password, logs_directory
    )


@cli.command()
@click.option("--event-target", default="http://localhost:8080")
@click.option("--target", default="http://localhost:8080/api")
@click.option("--logs-directory", default=None)
def sync_file_changes(event_target, target, logs_directory):
    """
    Run a daemon that download files related to any change happening on target
    instance. It expects that credentials to connect to target instance are
    given through SYNC_LOGIN and SYNC_PASSWORD environment variables.
    """
    login = os.getenv("SYNC_LOGIN")
    password = os.getenv("SYNC_PASSWORD")
    commands.run_sync_file_change_daemon(
        event_target, target, login, password, logs_directory
    )


@cli.command()
@click.option("--target", default="http://localhost:8080/api")
@click.option("--minutes", default=0)
@click.option("--page-size", default=300)
def sync_last_events(target, minutes, page_size):
    """
    Retrieve last events that occured on target instance and import data related
    to them. It expects that credentials to connect to target instance are
    given through SYNC_LOGIN and SYNC_PASSWORD environment variables.
    """
    login = os.getenv("SYNC_LOGIN")
    password = os.getenv("SYNC_PASSWORD")
    commands.import_last_changes_from_another_instance(
        target, login, password, minutes=minutes, page_size=page_size
    )


@cli.command()
@click.option("--target", default="http://localhost:8080/api")
@click.option("--minutes", default=20)
@click.option("--page-size", default=50)
def sync_last_files(target, minutes, page_size):
    """
    Retrieve last preview files and thumbnails updloaded on target instance.
    It expects that credentials to connect to target instance are
    given through SYNC_LOGIN and SYNC_PASSWORD environment variables.
    """
    login = os.getenv("SYNC_LOGIN")
    password = os.getenv("SYNC_PASSWORD")
    commands.import_last_file_changes_from_another_instance(
        target, login, password, minutes=minutes, page_size=page_size
    )


@cli.command()
def download_storage_files():
    """
    Download all files from a Swift object storage and store them in a local
    storage.
    """
    commands.download_file_from_storage()


@cli.command()
def dump_database():
    """
    Dump database described in Zou environment variables and save it to
    configured object storage.
    """
    commands.dump_database()


@cli.command()
@click.option("--days", default=None)
def upload_files_to_cloud_storage(days):
    """
    Upload all files related to previews to configured object storage.
    """
    commands.upload_files_to_cloud_storage(days)


@cli.command()
@click.option("--projectid")
def clean_tasks_data(projectid):
    """
    Reset task models data (retake count, wip start date and end date)
    """
    if projectid is not None:
        commands.reset_tasks_data(projectid)


@cli.command()
@click.option("--days", default=90)
def remove_old_data(days):
    """
    Remove old events, notifications and login logs older than 90 days
    (by deafult).
    """
    commands.remove_old_data(days)


@cli.command()
def reset_search_index():
    """
    Reset search index.
    """
    commands.reset_search_index()


@cli.command()
def init_search_index():
    """
    Init search index.
    """
    commands.init_search_index()


@cli.command()
@click.option("--query", default="")
def search_asset(query):
    """ """
    commands.search_asset(query)


if __name__ == "__main__":
    cli()
