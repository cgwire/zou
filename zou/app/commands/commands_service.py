"""
Operations run from the command line (zou <command>): LDAP sync, instance
sync, dumps, preview renormalization, plugin management. The CLI in
zou/cli.py parses the arguments and calls here; the functions carry the
application logic and print their progress.
"""

import os
import datetime
import tempfile
import sys
import shutil
import click
import orjson as json

from tabulate import tabulate
from ldap3 import Server, Connection, ALL, NTLM, SIMPLE
from zou.app.utils import thumbnail as thumbnail_utils, auth
from zou.app.utils.progress import NullProgress
from zou.app.stores import auth_tokens_store, file_store
from zou.app.commands import (
    backup_service,
    sync_files_service,
    sync_service,
    sync_verify_service,
)
from zou.app.services import (
    breakdown_service,
    deletion_service,
    index_service,
    persons_service,
    preview_file_states_service,
    preview_files_service,
    projects_service,
    tasks_service,
    departments_service,
    entity_types_service,
    organisation_service,
    task_types_service,
)
from zou.app.models.entity import Entity
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.models.plugin import Plugin
from sqlalchemy.sql.expression import not_

from zou.app.exceptions import (
    PersonNotFoundException,
    IsUserLimitReachedException,
)

from zou.app import config

from zou.app import app

# Departments (name, color) and task types (department, name, color,
# priority, for_entity) that init-data creates, per studio domain. The
# "default" entry is the 3d pipeline.
DOMAIN_TASK_TYPES = {
    "2d": {
        "departments": [
            ("Concept", "#8D6E63"),
            ("Layout", "#7CB342"),
            ("Animation", "#009688"),
            ("Compositing", "#F06292"),
        ],
        "task_types": [
            ("Concept", "Concept", "#8D6E63", 1, "Asset"),
            ("Concept", "Storyboard", "#43A047", 1, "Shot"),
            ("Layout", "Layout", "#7CB342", 2, "Shot"),
            ("Animation", "Animation", "#009688", 3, "Shot"),
            ("Animation", "Clean-up", "#4DB6AC", 4, "Shot"),
            ("Compositing", "Color", "#F9A825", 5, "Shot"),
            ("Compositing", "Compositing", "#ff5252", 6, "Shot"),
            ("Compositing", "Edit", "#9b298c", 7, "Edit"),
            ("Concept", "Concept", "#8D6E63", 1, "Concept"),
        ],
    },
    "vfx": {
        "departments": [
            ("Modeling", "#78909C"),
            ("Animation", "#009688"),
            ("FX", "#26C6DA"),
            ("Compositing", "#F06292"),
            ("Concept", "#8D6E63"),
            ("Layout", "#7CB342"),
            ("Matchmove", "#5C6BC0"),
            ("DMP", "#8D6E63"),
        ],
        "task_types": [
            ("Concept", "Concept", "#8D6E63", 1, "Asset"),
            ("Modeling", "Modeling", "#78909C", 2, "Asset"),
            ("Modeling", "Shading", "#64B5F6", 3, "Asset"),
            ("Animation", "Rigging", "#9CCC65", 4, "Asset"),
            ("Matchmove", "Matchmove", "#5C6BC0", 1, "Shot"),
            ("Matchmove", "Rotomation", "#7986CB", 2, "Shot"),
            ("Concept", "Storyboard", "#43A047", 1, "Shot"),
            ("Layout", "Layout", "#7CB342", 2, "Shot"),
            ("Animation", "Animation", "#009688", 3, "Shot"),
            ("Compositing", "Lighting", "#F9A825", 4, "Shot"),
            ("FX", "FX", "#26C6DA", 5, "Shot"),
            ("Compositing", "Rendering", "#F06292", 6, "Shot"),
            ("Compositing", "Compositing", "#ff5252", 7, "Shot"),
            ("DMP", "DMP", "#A1887F", 8, "Shot"),
            ("Compositing", "Edit", "#9b298c", 9, "Edit"),
            ("Concept", "Concept", "#8D6E63", 1, "Concept"),
        ],
    },
    "games": {
        "departments": [
            ("Game Design", "#7B1FA2"),
            ("Level Design", "#00897B"),
            ("Character Art", "#78909C"),
            ("Environment Art", "#43A047"),
            ("Animation", "#009688"),
            ("VFX", "#26C6DA"),
            ("QA", "#E53935"),
        ],
        "task_types": [
            ("Game Design", "Game Design", "#7B1FA2", 1, "Asset"),
            ("Level Design", "Level Design", "#00897B", 2, "Asset"),
            ("Character Art", "Character Art", "#78909C", 3, "Asset"),
            ("Environment Art", "Environment Art", "#43A047", 4, "Asset"),
            ("Animation", "Animation", "#009688", 5, "Asset"),
            ("VFX", "VFX", "#26C6DA", 6, "Asset"),
            ("Character Art", "Concept", "#8D6E63", 1, "Concept"),
            ("QA", "QA", "#E53935", 1, "Shot"),
        ],
    },
    "default": {
        "departments": [
            ("Modeling", "#78909C"),
            ("Animation", "#009688"),
            ("FX", "#26C6DA"),
            ("Compositing", "#F06292"),
            ("Concept", "#8D6E63"),
            ("Layout", "#7CB342"),
        ],
        "task_types": [
            ("Concept", "Concept", "#8D6E63", 1, "Asset"),
            ("Modeling", "Modeling", "#78909C", 2, "Asset"),
            ("Modeling", "Shading", "#64B5F6", 3, "Asset"),
            ("Animation", "Rigging", "#9CCC65", 4, "Asset"),
            ("Concept", "Storyboard", "#43A047", 1, "Shot"),
            ("Layout", "Layout", "#7CB342", 2, "Shot"),
            ("Animation", "Animation", "#009688", 3, "Shot"),
            ("Compositing", "Lighting", "#F9A825", 4, "Shot"),
            ("FX", "FX", "#26C6DA", 5, "Shot"),
            ("Compositing", "Rendering", "#F06292", 6, "Shot"),
            ("Compositing", "Compositing", "#ff5252", 7, "Shot"),
            ("Compositing", "Edit", "#9b298c", 8, "Edit"),
            ("Concept", "Concept", "#8D6E63", 1, "Concept"),
        ],
    },
}


def clean_auth_tokens():
    """
    Remove all revoked tokens from the key value
    store.
    """
    for key in auth_tokens_store.keys():
        if auth_tokens_store.is_revoked(key):
            auth_tokens_store.delete(key)


def clear_all_auth_tokens():
    """
    Remove all authentication tokens from the key value store.
    """
    for key in auth_tokens_store.keys():
        auth_tokens_store.delete(key)


def _init_asset_types_for_domain(domain):
    """
    Initialize asset types according to domain (2d, 3d, vfx, games).
    """
    if domain == "2d":
        for name in ("Character", "Prop", "Background", "FX"):
            entity_types_service.get_or_create_asset_type(name)
    elif domain == "vfx":
        for name in ("Character", "Prop", "Environment", "FX", "Vehicle"):
            entity_types_service.get_or_create_asset_type(name)
    elif domain == "games":
        for name in ("Character", "Prop", "Environment", "FX", "UI"):
            entity_types_service.get_or_create_asset_type(name)
    else:
        # 3d (default)
        for name in ("Character", "Prop", "Environment", "FX"):
            entity_types_service.get_or_create_asset_type(name)


def _init_task_types_for_domain(domain):
    """
    Initialize departments and task types according to domain.
    """
    setup = DOMAIN_TASK_TYPES.get(domain, DOMAIN_TASK_TYPES["default"])
    departments = {}
    for name, color in setup["departments"]:
        departments[name] = departments_service.get_or_create_department(
            name, color
        )
    for department, name, color, priority, for_entity in setup["task_types"]:
        task_types_service.get_or_create_task_type(
            departments[department],
            name,
            color,
            priority=priority,
            for_entity=for_entity,
        )


def init_data(domain="3d"):
    """
    Put the minimum required data into the database to start with it.

    domain: "2d" (2D production), "3d" (3D animation), "vfx", or "games"
    """
    with app.app_context():
        projects_service.get_open_status()
        projects_service.get_closed_status()
        print("Project status initialized.")

        _init_asset_types_for_domain(domain)
        print(f"Asset types initialized (domain: {domain}).")

        entity_types_service.get_episode_type()
        entity_types_service.get_sequence_type()
        entity_types_service.get_shot_type()
        print("Shot types initialized.")

        entity_types_service.get_edit_type()
        print("Edit type initialized.")

        _init_task_types_for_domain(domain)
        print("Task types initialized.")

        task_types_service.get_default_task_status()
        task_types_service.get_or_create_task_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )
        task_types_service.get_or_create_task_status(
            "Waiting For Approval", "wfa", "#ab26ff", is_feedback_request=True
        )
        task_types_service.get_or_create_task_status(
            "Retake", "retake", "#ff3860", is_retake=True
        )
        task_types_service.get_or_create_task_status(
            "Done", "done", "#22d160", is_done=True
        )
        task_types_service.get_or_create_task_status(
            "Ready To Start", "ready", "#fbc02d"
        )

        task_types_service.get_or_create_task_status(
            "Neutral",
            "neutral",
            "#CCCCCC",
            is_default=True,
            for_concept=True,
            is_artist_allowed=True,
            is_client_allowed=True,
        )

        task_types_service.get_or_create_task_status(
            "Approved",
            "approved",
            "#66BB6A",
            for_concept=True,
            is_artist_allowed=True,
            is_client_allowed=True,
        )

        task_types_service.get_or_create_task_status(
            "Rejected",
            "rejected",
            "#E81123",
            for_concept=True,
            is_artist_allowed=True,
            is_client_allowed=True,
        )

        print("Task status initialized.")


def _ldap_settings():
    """
    The directory connection settings, from the configuration and the
    environment.
    """
    return {
        "LDAP_HOST": app.config["LDAP_HOST"],
        "LDAP_PORT": app.config["LDAP_PORT"],
        "LDAP_PASSWORD": os.getenv("LDAP_PASSWORD", "password"),
        "LDAP_BASE_DN": app.config["LDAP_BASE_DN"],
        "LDAP_DOMAIN": app.config["LDAP_DOMAIN"],
        "LDAP_USER": os.getenv("LDAP_USER", ""),
        "LDAP_GROUP": app.config["LDAP_GROUP"],
        "LDAP_SSL": app.config["LDAP_SSL"],
        "EMAIL_DOMAIN": os.getenv("EMAIL_DOMAIN", "studio.local"),
        "LDAP_EXCLUDED_ACCOUNTS": os.getenv("LDAP_EXCLUDED_ACCOUNTS", ""),
        "LDAP_IS_AD": app.config["LDAP_IS_AD"],
        "LDAP_IS_AD_SIMPLE": app.config["LDAP_IS_AD_SIMPLE"],
    }


def _ldap_clean_value(value):
    cleaned_value = str(value)
    if cleaned_value == "[]":
        cleaned_value = ""
    return cleaned_value


def _ldap_search_users(settings, conn, excluded_accounts):
    """
    Read the user entries of the directory (or of the configured group) and
    return them as dicts the person sync understands.
    """
    is_ad = settings["LDAP_IS_AD"] or settings["LDAP_IS_AD_SIMPLE"]
    attributes = ["givenName", "sn", "mail", "cn"]
    if is_ad:
        if settings["LDAP_IS_AD_SIMPLE"]:
            attributes += ["cn"]
        else:
            attributes += ["sAMAccountName"]
        attributes += [
            "thumbnailPhoto",
            "userAccountControl",
            "objectGUID",
        ]
    else:
        attributes += [
            "uid",
            "jpegPhoto",
            "uniqueIdentifier",
            "organizationalStatus",
        ]
    query = "(objectClass=person)"
    if is_ad:
        query = "(&(objectClass=person)(!(objectClass=computer)))"
    group_members = None
    if len(settings["LDAP_GROUP"]) > 0:
        if is_ad:
            query = (
                f"(&(objectClass=person)(memberOf={settings['LDAP_GROUP']}))"
            )
        else:
            conn.search(
                settings["LDAP_BASE_DN"],
                f"(&(objectClass=groupofUniqueNames)(cn={settings['LDAP_GROUP']}))",
                attributes=["uniqueMember"],
            )
            group_members = conn.entries[0].uniqueMember.values
    conn.search(settings["LDAP_BASE_DN"], query, attributes=attributes)
    ldap_users = []
    for entry in conn.entries:
        if settings["LDAP_IS_AD_SIMPLE"]:
            desktop_login = entry.cn
        elif settings["LDAP_IS_AD"]:
            desktop_login = entry.sAMAccountName
        else:
            desktop_login = entry.uid
        desktop_login = _ldap_clean_value(desktop_login)

        if desktop_login not in excluded_accounts and (
            group_members is None or entry.entry_dn in group_members
        ):
            if is_ad:
                ldap_uid = _ldap_clean_value(entry.objectGUID)
            elif entry.uniqueIdentifier:
                ldap_uid = _ldap_clean_value(entry.uniqueIdentifier)
            else:
                ldap_uid = None
            thumbnails = (
                entry.thumbnailPhoto if is_ad else entry.jpegPhoto
            ).raw_values
            if len(thumbnails) > 0 and len(thumbnails[0]) > 0:
                thumbnail = thumbnails[0]
            else:
                thumbnail = None

            emails = entry.mail.values
            if len(emails) == 0:
                emails = [f"{desktop_login}@{settings['EMAIL_DOMAIN']}"]
            else:

                def sort_mails(email):
                    if email == desktop_login:
                        return -2
                    elif settings["EMAIL_DOMAIN"] in email:
                        return -1
                    else:
                        return 0

                emails = sorted(emails, key=sort_mails)

            if is_ad:
                active = bool(entry.userAccountControl.value & 2) is False
            elif entry.organizationalStatus:
                active = entry.organizationalStatus.value.lower() == "active"
            else:
                active = False

            ldap_users.append(
                {
                    "first_name": _ldap_clean_value(
                        entry.givenName or entry.cn
                    ),
                    "last_name": _ldap_clean_value(entry.sn),
                    "email": emails[0].lower(),
                    "emails": emails,
                    "desktop_login": desktop_login,
                    "thumbnail": thumbnail,
                    "active": active,
                    "ldap_uid": ldap_uid,
                }
            )
    return ldap_users


def _ldap_fetch_users(settings):
    """
    Bind to the directory with the configured account and list its users.
    """
    excluded_accounts = settings["LDAP_EXCLUDED_ACCOUNTS"].split(",")
    ldap_server = f"{settings['LDAP_HOST']}:{settings['LDAP_PORT']}"
    SSL = settings["LDAP_SSL"]
    if settings["LDAP_IS_AD_SIMPLE"]:
        user = settings["LDAP_USER"]
        authentication = SIMPLE
    elif settings["LDAP_IS_AD"]:
        user = f"{settings['LDAP_DOMAIN']}\\{settings['LDAP_USER']}"
        authentication = NTLM
    elif "=" in settings["LDAP_USER"]:
        # settings["LDAP_USER"] is already a full bind DN, use it as is. OpenLDAP
        # admin accounts often live outside the users base DN
        # (e.g. cn=admin,dc=studio,dc=local).
        user = settings["LDAP_USER"]
        authentication = SIMPLE
    else:
        user = f"uid={settings['LDAP_USER']},{settings['LDAP_BASE_DN']}"
        authentication = SIMPLE

    server = Server(ldap_server, get_info=ALL, use_ssl=SSL)
    conn = Connection(
        server,
        user=user,
        password=settings["LDAP_PASSWORD"],
        authentication=authentication,
        raise_exceptions=True,
        auto_bind=True,
    )

    return _ldap_search_users(settings, conn, excluded_accounts)


def _ldap_update_persons(users):
    """
    Align the persons with the directory users: disable the ones that are
    gone, update the ones found, create the missing active ones.
    """
    persons_to_update = []
    persons_to_create = []
    for user in sorted(users, key=lambda k: k["active"]):
        person = None
        try:
            person = persons_service.get_person_by_ldap_uid(user["ldap_uid"])
        except PersonNotFoundException:
            try:
                person = persons_service.get_person_by_desktop_login(
                    user["desktop_login"]
                )
            except PersonNotFoundException:
                for mail in user["emails"]:
                    try:
                        person = persons_service.get_person_by_email(mail)
                        break
                    except PersonNotFoundException:
                        pass

        if person is None:
            persons_to_create.append(user)
        else:
            persons_to_update.append((person, user))

    for person in (
        Person.query.filter_by(is_generated_from_ldap=True, active=True)
        .filter(not_(Person.id.in_([p[0]["id"] for p in persons_to_update])))
        .all()
    ):
        persons_service.update_person(
            person.id, {"active": False}, bypass_protected_accounts=True
        )
        print(f"User {person.desktop_login} disabled (not found in LDAP).")

    for person, user in persons_to_update:
        try:
            if (
                not person["active"]
                and user["active"]
                and persons_service.is_user_limit_reached()
            ):
                raise IsUserLimitReachedException

            if any(
                user[key] != person[key]
                for key in [
                    key
                    for key in user.keys()
                    if key not in ["thumbnail", "emails"]
                ]
            ):
                persons_service.update_person(
                    person["id"],
                    {
                        "email": user["email"],
                        "first_name": user["first_name"],
                        "last_name": user["last_name"],
                        "active": user["active"],
                        "is_generated_from_ldap": True,
                        "desktop_login": user["desktop_login"],
                        "ldap_uid": user["ldap_uid"],
                    },
                    bypass_protected_accounts=True,
                )
                print(f"User {user['desktop_login']} updated.")
        except IsUserLimitReachedException:
            print(
                f"User {user['desktop_login']} update failed (limit reached, limit {organisation_service.get_user_limit()})."
            )
        except Exception:
            print(
                f"User {user['desktop_login']} update failed (email duplicated?)."
            )

        if user["thumbnail"] is not None:
            _ldap_save_thumbnail(person, user["thumbnail"])

    for user in persons_to_create:
        # Reset per user: an inactive or failed entry must not inherit
        # the previous person and receive its thumbnail.
        person = None
        if user["active"]:
            try:
                if persons_service.is_user_limit_reached():
                    raise IsUserLimitReachedException
                person = persons_service.create_person(
                    user["email"],
                    "default".encode("utf-8"),
                    user["first_name"],
                    user["last_name"],
                    desktop_login=user["desktop_login"],
                    is_generated_from_ldap=True,
                    ldap_uid=user["ldap_uid"],
                )
                print(f"User {user['desktop_login']} created.")
            except IsUserLimitReachedException:
                print(
                    f"User {user['desktop_login']} creation failed (limit reached, limit {organisation_service.get_user_limit()})."
                )
            except Exception:
                print(
                    f"User {user['desktop_login']} creation failed (email duplicated?)."
                )

        if person is not None and user["thumbnail"] is not None:
            _ldap_save_thumbnail(person, user["thumbnail"])


def _ldap_save_thumbnail(person, thumbnail):
    """
    Store the directory photo as the avatar of given person.
    """
    thumbnail_path = "/tmp/ldap_th.jpg"
    with open(thumbnail_path, "wb") as th_file:
        th_file.write(thumbnail)
    thumbnail_png_path = thumbnail_utils.convert_jpg_to_png(thumbnail_path)
    thumbnail_utils.turn_into_thumbnail(
        thumbnail_png_path, size=thumbnail_utils.BIG_SQUARE_SIZE
    )
    file_store.add_picture("thumbnails", person["id"], thumbnail_png_path)
    os.remove(thumbnail_png_path)
    persons_service.update_person(
        person["id"], {"has_avatar": True}, bypass_protected_accounts=True
    )


def sync_with_ldap_server():
    """
    Connect to a LDAP server, then creates all related accounts.
    """
    settings = _ldap_settings()
    _ldap_update_persons(_ldap_fetch_users(settings))


def import_data_from_another_instance(
    source,
    login,
    password,
    project=None,
    with_events=False,
    no_projects=False,
    only_projects=False,
):
    """
    Retrieve and save all the data from another API instance. It doesn't
    change the IDs.
    """
    with app.app_context():
        sync_service.init(source, login, password)
        if not only_projects:
            sync_service.run_main_data_sync(project=project)
        if not no_projects:
            sync_service.run_project_data_sync(project=project)
            sync_service.run_other_sync(
                project=project, with_events=with_events
            )


def verify_project_against_source(source, login, password, project_name):
    """
    Connect to the source instance and compare row counts for every
    project-scoped model. Prints a side-by-side report and a non-zero
    exit code is not used — the report is informational.
    """
    with app.app_context():
        sync_service.init(source, login, password)
        sync_verify_service.verify_project_sync(project_name, direction="pull")


def verify_project_against_target(target, login, password, project_name):
    """
    Mirror of :func:`verify_project_against_source` for the sync-push
    direction. Connect to the target instance we pushed to and compare
    its row counts against the local ones.
    """
    with app.app_context():
        sync_service.init(target, login, password)
        sync_verify_service.verify_project_sync(project_name, direction="push")


def push_project_to_target(
    target,
    login,
    password,
    project_name,
    batch_size=200,
    throttle=0.0,
    silent=True,
):
    """
    Push the project named ``project_name`` from the local instance to
    ``target`` via /import/kitsu/* routes.
    """
    with app.app_context():
        sync_service.push_project_data(
            target,
            login,
            password,
            project_name,
            batch_size=batch_size,
            throttle=throttle,
            silent=silent,
        )


def run_sync_change_daemon(event_source, source, login, password, logs_dir):
    """
    Listen to event websocket. Each time a change occurs, it retrieves the
    related data and save it in the current instance.
    """
    with app.app_context():
        event_client = sync_service.init_events_listener(
            source, event_source, login, password, logs_dir
        )
        sync_service.add_main_sync_listeners(event_client)
        sync_service.add_project_sync_listeners(event_client)
        sync_service.add_special_sync_listeners(event_client)
        print("Start listening.")
        sync_service.run_listeners(event_client)


def run_sync_file_change_daemon(
    event_source, source, login, password, logs_dir
):
    """
    Listen to event websocket. Each time a change occurs, it retrieves the
    related file and save it in the current instance storage.
    """
    with app.app_context():
        event_client = sync_service.init_events_listener(
            source, event_source, login, password, logs_dir
        )
        sync_files_service.add_file_listeners(event_client)
        print("Start listening.")
        sync_service.run_listeners(event_client)


def import_last_changes_from_another_instance(
    source, login, password, minutes=0, limit=300
):
    """
    Retrieve and save all the data related to most recent events from another
    API instance. It doesn't change the IDs.
    """
    with app.app_context():
        sync_service.init(source, login, password)
        print("Last events syncing started.")
        sync_service.run_last_events_sync(minutes=minutes, limit=limit)
        print("Last events syncing ended.")


def import_last_file_changes_from_another_instance(
    source, login, password, minutes=20, limit=50, force=False
):
    """
    Retrieve and save all the data related most to recent file events
    from another API instance (new previews and thumbnails).
    It doesn't change the IDs.
    """
    with app.app_context():
        sync_service.init(source, login, password)
        print("Last files syncing started.")
        sync_files_service.run_last_events_files(minutes=minutes, limit=limit)
        print("Last files syncing ended.")


def import_files_from_another_instance(
    source,
    login,
    password,
    project=None,
    multithreaded=False,
    number_workers=30,
    number_attemps=3,
    force_resync=False,
    include_broken=True,
    include_missing=True,
):
    """
    Retrieve and save all the data related most recent events from another API
    instance. It doesn't change the IDs.
    """
    with app.app_context():
        sync_service.init(
            source, login, password, multithreaded, number_workers
        )
        return sync_files_service.download_files_from_another_instance(
            project=project,
            multithreaded=multithreaded,
            number_workers=number_workers,
            number_attemps=number_attemps,
            force_resync=force_resync,
            include_broken=include_broken,
            include_missing=include_missing,
        )


def download_file_from_storage():
    with app.app_context():
        sync_files_service.download_entity_thumbnails_from_storage()
        sync_files_service.download_preview_files_from_storage()


def dump_database(store=False):
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    filename = f"zou-db-backup-{now}.sql.gz"
    if store:
        filename = os.path.join(tempfile.gettempdir(), filename)

    filename = backup_service.generate_db_backup(
        app.config["DATABASE"]["host"],
        app.config["DATABASE"]["port"],
        app.config["DATABASE"]["username"],
        app.config["DATABASE"]["password"],
        app.config["DATABASE"]["database"],
        filename,
    )

    if store:
        backup_service.store_db_backup(os.path.basename(filename), filename)
        os.remove(filename)
        print(
            f"Postgres dump added to store (dbbackup/{os.path.basename(filename)})."
        )
    else:
        print(f"Postgres dump created ({os.path.realpath(filename)}).")


def upload_files_to_cloud_storage(days):
    with app.app_context():
        backup_service.upload_entity_thumbnails_to_storage(days)
        backup_service.upload_preview_files_to_storage(days)


def reset_tasks_data(project_id):
    with app.app_context():
        tasks_service.reset_tasks_data(project_id)


def remove_old_data(days_old=90):
    with app.app_context():
        print(f"Start removing non critical data older than {days_old}.")
        print("Removing old events...")
        deletion_service.remove_old_events(days_old)
        print("Removing old login logs...")
        deletion_service.remove_old_login_logs(days_old)
        print("Removing old notitfications...")
        deletion_service.remove_old_notifications(days_old)
        print("Old data removed.")


def reset_search_index():
    with app.app_context():
        print("Resetting search index.")
        index_service.reset_index()
        print("Search index reset.")


def search_asset(query):
    with app.app_context():
        assets = index_service.search_assets(query)
        if len(assets) == 0:
            print("No asset found")
        for asset in assets:
            print(asset["name"], asset["id"])
        return assets


def generate_preview_extra(
    project=None,
    entity_id=None,
    episodes=None,
    only_shots=False,
    only_assets=False,
    force_regenerate_tiles=False,
    with_tiles=False,
    with_metadata=False,
    with_thumbnails=False,
    progress=False,
):
    if episodes is None:
        episodes = []
    with app.app_context():
        preview_files_service.generate_preview_extra(
            project=project,
            entity_id=entity_id,
            episodes=episodes,
            only_shots=only_shots,
            only_assets=only_assets,
            force_regenerate_tiles=force_regenerate_tiles,
            with_thumbnails=with_thumbnails,
            with_metadata=with_metadata,
            with_tiles=with_tiles,
            progress=get_progress("Generating preview extras", progress),
        )


class ClickProgress:
    """
    Draws a progress bar for a long running command. Outside an
    interactive terminal click hides the bar, so a cron or a redirected
    run stays readable.
    """

    def __init__(self, label):
        self.label = label
        self.bar = None

    def start(self, total):
        self.bar = click.progressbar(length=total, label=self.label)
        self.bar.__enter__()

    def advance(self):
        if self.bar is not None:
            self.bar.update(1)

    def stop(self):
        if self.bar is not None:
            self.bar.__exit__(None, None, None)
            self.bar = None


def get_progress(label, enabled):
    """
    The reporter a command hands its service: a bar when asked for one,
    the silent reporter otherwise.
    """
    return ClickProgress(label) if enabled else NullProgress()


def queue_missing_tiles(
    project=None,
    entity_id=None,
    episodes=None,
    only_shots=False,
    only_assets=False,
    limit=None,
    force=False,
    progress=False,
):
    with app.app_context():
        summary = preview_files_service.queue_missing_tiles(
            project=project,
            entity_id=entity_id,
            episodes=episodes,
            only_shots=only_shots,
            only_assets=only_assets,
            limit=limit,
            force=force,
            progress=get_progress("Queueing tiles", progress),
        )
    print(
        f"{summary['checked']} movies checked: "
        f"{summary['queued']} queued, "
        f"{summary['stored']} already there, "
        f"{summary['recently_attempted']} skipped "
        "(attempt within the hour), "
        f"{summary['storage_errors']} storage errors"
    )


def reset_movie_files_metadata():
    with app.app_context():
        preview_files_service.reset_movie_files_metadata()


def reset_picture_files_metadata():
    with app.app_context():
        preview_files_service.reset_picture_files_metadata()


def probe_preview_files(
    project_id=None,
    only_unknown=False,
    limit=None,
    dry_run=False,
    progress=False,
):
    with app.app_context():
        summary = preview_file_states_service.probe_preview_files(
            project_id=project_id,
            only_unknown=only_unknown,
            limit=limit,
            dry_run=dry_run,
            progress=get_progress("Probing previews", progress),
        )
    # Movies without a tile sheet first: the file a hover rebuilds.
    keys = sorted(summary, key=lambda key: (key != "pictures/tiles", key))
    for key in keys:
        if summary[key] > 0:
            print(f"{key}: {summary[key]} missing")


def reset_breakdown_data():
    with app.app_context():
        print("Resetting breakdown data for all open projects.")
        breakdown_service.refresh_all_shot_casting_stats()
        print("Resetting done.")


def create_bot(
    email,
    name,
    expiration_date,
    role,
):
    with app.app_context():
        # Allow "admin@example.com" to be invalid.
        if email != "admin@example.com":
            auth.validate_email(email)
        bot = persons_service.create_person(
            email=email,
            password=None,
            first_name=name,
            last_name="",
            expiration_date=expiration_date,
            role=role,
            is_bot=True,
        )
        print(bot["access_token"])


class _SourceMovieMissing(RuntimeError):
    """
    Raised when the source movie binary is gone from storage during a
    renormalize pass. Used to distinguish 'broken' from 'missing' status.
    """


def renormalize_movie_preview_files(
    preview_file_id=None,
    project_id=None,
    all_broken=None,
    all_processing=None,
    all_missing=None,
    days=None,
    hours=None,
    minutes=None,
):
    with app.app_context():
        if isinstance(preview_file_id, str):
            preview_file_id = [preview_file_id]

        if (
            not preview_file_id
            and not all_broken
            and not all_processing
            and not all_missing
        ):
            print(
                "You must specify at least one flag from --preview-file-id, "
                "--all-broken, --all-missing or --all-processing."
            )
            sys.exit(1)

        query = PreviewFile.query.order_by(PreviewFile.created_at.asc())

        if not preview_file_id:
            query = query.filter(PreviewFile.extension == "mp4")

        if any((minutes, hours, days)):
            since_date = datetime.datetime.now() - datetime.timedelta(
                days=days or 0,
                hours=hours or 0,
                minutes=minutes or 0,
            )
            query = query.filter(PreviewFile.created_at >= since_date)

        if preview_file_id:
            query = query.filter(PreviewFile.id.in_(preview_file_id))

        if project_id is not None:
            query = query.join(Task).filter(Task.project_id == project_id)

        selected_statuses = []
        if all_broken:
            selected_statuses.append("broken")
        if all_missing:
            selected_statuses.append("missing")
        if all_processing:
            selected_statuses.append("processing")
        if selected_statuses:
            query = query.filter(PreviewFile.status.in_(selected_statuses))

        preview_files = query.all()
        len_preview_files = len(preview_files)
        if len_preview_files == 0:
            print("No preview files found.")
            sys.exit(1)
        else:
            for i, preview_file in enumerate(preview_files):
                try:
                    preview_file_id = str(preview_file.id)
                    print(
                        f"Renormalizing preview file {preview_file_id} ({i+1}/{len_preview_files})."
                    )
                    extension = preview_file.extension
                    uploaded_movie_path = os.path.join(
                        config.TMP_DIR,
                        f"{preview_file_id}.{extension}.tmp",
                    )
                    if not file_store.exists_movie("source", preview_file_id):
                        raise _SourceMovieMissing(
                            f"Source movie missing in storage for preview "
                            f"{preview_file_id}; skipping renormalization."
                        )
                    if config.FS_BACKEND == "local":
                        shutil.copyfile(
                            file_store.get_local_movie_path(
                                "source", preview_file_id
                            ),
                            uploaded_movie_path,
                        )
                    else:
                        sync_files_service.download_file(
                            uploaded_movie_path,
                            "source",
                            file_store.open_movie,
                            str(preview_file_id),
                        )
                    if (
                        not os.path.exists(uploaded_movie_path)
                        or os.path.getsize(uploaded_movie_path) == 0
                    ):
                        raise RuntimeError(
                            f"Local copy of source movie is missing or "
                            f"empty at {uploaded_movie_path}; skipping "
                            f"renormalization of {preview_file_id}."
                        )
                    preview_files_service.dispatch_movie_processing(
                        preview_file_id,
                        uploaded_movie_path,
                        normalize=True,
                        add_source_to_file_store=False,
                    )
                except _SourceMovieMissing as e:
                    print(
                        f"Renormalization of preview file {preview_file_id} failed: {e}"
                    )
                    try:
                        preview_files_service.set_preview_file_as_missing(
                            preview_file_id
                        )
                    except Exception as mark_err:
                        print(
                            f"Could not mark {preview_file_id} as missing: {mark_err}"
                        )
                    continue
                except Exception as e:
                    print(
                        f"Renormalization of preview file {preview_file_id} failed: {e}"
                    )
                    try:
                        preview_files_service.set_preview_file_as_broken(
                            preview_file_id
                        )
                    except Exception as mark_err:
                        print(
                            f"Could not mark {preview_file_id} as broken: {mark_err}"
                        )
                    continue


def normalize_annotation_times(project_id=None, dry_run=False):
    """
    Merge preview file annotation entries that land on the same frame and
    snap their times onto the frame grid used by the Kitsu player. Older
    Kitsu versions stored unrounded times, leaving duplicated entries whose
    drawings the player cannot display.
    """
    with app.app_context():
        query = PreviewFile.query.filter(
            PreviewFile.annotations.isnot(None)
        ).order_by(PreviewFile.created_at.asc())
        if project_id is not None:
            query = query.join(Task).filter(Task.project_id == project_id)
        changed_count = 0
        scanned_count = 0
        for preview_file in query:
            if not preview_file.annotations:
                continue
            scanned_count += 1
            preview_file_id = str(preview_file.id)
            try:
                if dry_run:
                    task = Task.get(preview_file.task_id)
                    project = Project.get(task.project_id).serialize()
                    entity = Entity.get(task.entity_id)
                    fps = float(
                        preview_files_service.get_preview_file_fps(
                            project,
                            entity.serialize() if entity is not None else None,
                        )
                    )
                    _, changed = (
                        preview_files_service.normalize_annotation_times(
                            preview_file.annotations, fps
                        )
                    )
                else:
                    changed = preview_files_service.normalize_preview_file_annotation_times(
                        preview_file
                    )
                if changed:
                    changed_count += 1
                    print(
                        f"Preview file {preview_file_id} "
                        f"{'needs normalization' if dry_run else 'normalized'}."
                    )
            except Exception as e:
                print(
                    f"Normalization of preview file {preview_file_id} "
                    f"failed: {e}"
                )
        print(
            f"{changed_count}/{scanned_count} annotated preview files "
            f"{'need normalization' if dry_run else 'normalized'}."
        )


def list_plugins(output_format, verbose, filter_field, filter_value):
    with app.app_context():
        query = Plugin.query

        if filter_field and filter_value:
            if filter_field == "maintainer":
                query = query.filter(
                    Plugin.maintainer_name.ilike(f"%{filter_value}%")
                )
            else:
                model_field = getattr(Plugin, filter_field)
                query = query.filter(model_field.ilike(f"%{filter_value}%"))

        plugins = query.order_by(Plugin.name).all()

        if not plugins:
            click.echo("No plugins found matching the criteria.")
            return

        plugin_list = []
        for plugin in plugins:
            maintainer = (
                f"{plugin.maintainer_name} <{plugin.maintainer_email}>"
                if plugin.maintainer_email
                else plugin.maintainer_name
            )
            plugin_data = {
                "Plugin ID": plugin.plugin_id,
                "Name": plugin.name,
                "Version": plugin.version,
                "Maintainer": maintainer,
                "License": plugin.license,
            }
            if verbose:
                plugin_data["Description"] = plugin.description or "-"
                plugin_data["Website"] = plugin.website or "-"
                plugin_data["Icon"] = plugin.icon or "-"
                plugin_data["Revision"] = plugin.revision or "-"
                plugin_data["Installation Date"] = plugin.created_at
                plugin_data["Last Update"] = plugin.updated_at
            plugin_list.append(plugin_data)

        if output_format == "table":
            headers = plugin_list[0].keys()
            rows = [p.values() for p in plugin_list]
            click.echo(tabulate(rows, headers, tablefmt="fancy_grid"))
        elif output_format == "json":
            click.echo(
                json.dumps(plugin_list, option=json.OPT_INDENT_2).decode(
                    "utf-8"
                )
            )
