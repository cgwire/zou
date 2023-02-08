# coding: utf-8

import os
import json
import datetime


from ldap3 import Server, Connection, ALL, NTLM, SIMPLE
from zou.app.utils import thumbnail as thumbnail_utils
from zou.app.stores import auth_tokens_store, file_store
from zou.app.services import (
    assets_service,
    backup_service,
    deletion_service,
    edits_service,
    index_service,
    persons_service,
    projects_service,
    shots_service,
    sync_service,
    tasks_service,
)
from zou.app.models.person import Person
from sqlalchemy.sql.expression import not_
from zou.app.index_schema import init_indexes

from zou.app.services.exception import (
    PersonNotFoundException,
    IsUserLimitReachedException,
)

from zou.app import app


def clean_auth_tokens():
    """
    Remove all revoked tokens (most of the time outdated) from the key value
    store.
    """
    for key in auth_tokens_store.keys():
        value = json.loads(auth_tokens_store.get(key))

        if type(value) is bool:
            auth_tokens_store.delete(key)

        else:
            is_revoked = value["revoked"] == True
            expiration = datetime.datetime.fromtimestamp(value["token"]["exp"])
            is_expired = expiration < datetime.datetime.now()

            if is_revoked or is_expired:
                auth_tokens_store.delete(key)


def clear_all_auth_tokens():
    """
    Remove all authentication tokens from the key value store.
    """
    for key in auth_tokens_store.keys():
        auth_tokens_store.delete(key)


def init_data():
    """
    Put the minimum required data into the database to start with it.
    """
    projects_service.get_open_status()
    projects_service.get_closed_status()
    print("Project status initialized.")

    assets_service.get_or_create_asset_type("Character")
    assets_service.get_or_create_asset_type("Prop")
    assets_service.get_or_create_asset_type("Environment")
    assets_service.get_or_create_asset_type("FX")
    print("Asset types initialized.")

    shots_service.get_episode_type()
    shots_service.get_sequence_type()
    shots_service.get_shot_type()
    print("Shot types initialized.")

    edits_service.get_edit_type()
    print("Edit type initialized.")

    modeling = tasks_service.get_or_create_department("Modeling", "#78909C")
    animation = tasks_service.get_or_create_department("Animation", "#009688")
    fx = tasks_service.get_or_create_department("FX", "#26C6DA")
    compositing = tasks_service.get_or_create_department(
        "Compositing", "#F06292"
    )
    concept = tasks_service.get_or_create_department("Concept", "#8D6E63")
    layout = tasks_service.get_or_create_department("Layout", "#7CB342")

    tasks_service.get_or_create_task_type(concept, "Concept", "#8D6E63", 1)
    tasks_service.get_or_create_task_type(modeling, "Modeling", "#78909C", 2)
    tasks_service.get_or_create_task_type(modeling, "Shading", "#64B5F6", 3)
    tasks_service.get_or_create_task_type(animation, "Rigging", "#9CCC65", 4)

    tasks_service.get_or_create_task_type(
        concept,
        "Storyboard",
        "#43A047",
        priority=1,
        for_entity="Shot",
    )
    tasks_service.get_or_create_task_type(
        layout,
        "Layout",
        "#7CB342",
        priority=2,
        for_entity="Shot",
    )
    tasks_service.get_or_create_task_type(
        animation,
        "Animation",
        "#009688",
        priority=3,
        for_entity="Shot",
    )
    tasks_service.get_or_create_task_type(
        compositing,
        "Lighting",
        "#F9A825",
        priority=4,
        for_entity="Shot",
    )
    tasks_service.get_or_create_task_type(
        fx, "FX", "#26C6DA", priority=5, for_entity="Shot"
    )
    tasks_service.get_or_create_task_type(
        compositing,
        "Rendering",
        "#F06292",
        priority=6,
        for_entity="Shot",
    )
    tasks_service.get_or_create_task_type(
        compositing,
        "Compositing",
        "#ff5252",
        priority=7,
        for_entity="Shot",
    )
    tasks_service.get_or_create_task_type(
        compositing,
        "Edit",
        "#9b298c",
        priority=8,
        for_entity="Edit",
    )
    print("Task types initialized.")

    tasks_service.get_default_status()
    tasks_service.get_or_create_status("Work In Progress", "wip", "#3273dc")
    tasks_service.get_or_create_status(
        "Waiting For Approval", "wfa", "#ab26ff", is_feedback_request=True
    )
    tasks_service.get_or_create_status(
        "Retake", "retake", "#ff3860", is_retake=True
    )
    tasks_service.get_or_create_status("Done", "done", "#22d160", is_done=True)
    tasks_service.get_or_create_status("Ready To Start", "ready", "#fbc02d")

    print("Task status initialized.")


def sync_with_ldap_server():
    """
    Connect to a LDAP server, then creates all related accounts.
    """
    LDAP_HOST = app.config["LDAP_HOST"]
    LDAP_PORT = app.config["LDAP_PORT"]
    LDAP_PASSWORD = os.getenv("LDAP_PASSWORD", "password")
    LDAP_BASE_DN = app.config["LDAP_BASE_DN"]
    LDAP_DOMAIN = app.config["LDAP_DOMAIN"]
    LDAP_USER = os.getenv("LDAP_USER", "")
    LDAP_GROUP = app.config["LDAP_GROUP"]
    LDAP_SSL = app.config["LDAP_SSL"]
    EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "studio.local")
    LDAP_EXCLUDED_ACCOUNTS = os.getenv("LDAP_EXCLUDED_ACCOUNTS", "")
    LDAP_IS_AD = app.config["LDAP_IS_AD"]
    LDAP_IS_AD_SIMPLE = app.config["LDAP_IS_AD_SIMPLE"]

    def clean_value(value):
        cleaned_value = str(value)
        if cleaned_value == "[]":
            cleaned_value = ""
        return cleaned_value

    def search_ldap_users(conn, excluded_accounts):
        is_ad = LDAP_IS_AD or LDAP_IS_AD_SIMPLE
        attributes = ["givenName", "sn", "mail", "cn"]
        if is_ad:
            attributes += [
                "sAMAccountName",
                "thumbnailPhoto",
                "userAccountControl",
            ]
        else:
            attributes += ["uid", "jpegPhoto"]
        query = "(objectClass=person)"
        if is_ad:
            query = "(&(objectClass=person)(!(objectClass=computer)))"
        if len(LDAP_GROUP) > 0 and is_ad:
            query = "(&(objectClass=person)(memberOf=%s))" % LDAP_GROUP
        conn.search(LDAP_BASE_DN, query, attributes=attributes)
        return [
            {
                "first_name": clean_value(entry.givenName or entry.cn),
                "last_name": clean_value(entry.sn),
                "email": clean_value(entry.mail),
                "desktop_login": clean_value(
                    entry.sAMAccountName if is_ad else entry.uid
                ),
                "thumbnail": (
                    entry.thumbnailPhoto if is_ad else entry.jpegPhoto
                ).raw_values,
                "active": (bool(entry.userAccountControl.value & 2) is False)
                if is_ad
                else True,
            }
            for entry in conn.entries
            if clean_value(entry.sAMAccountName if is_ad else entry.uid)
            not in excluded_accounts
        ]

    def get_ldap_users():
        excluded_accounts = LDAP_EXCLUDED_ACCOUNTS.split(",")
        ldap_server = "%s:%s" % (LDAP_HOST, LDAP_PORT)
        SSL = LDAP_SSL
        if LDAP_IS_AD_SIMPLE:
            user = LDAP_USER
            authentication = SIMPLE
        elif LDAP_IS_AD:
            user = "%s\%s" % (LDAP_DOMAIN, LDAP_USER)
            authentication = NTLM
        else:
            user = "uid=%s,%s" % (LDAP_USER, LDAP_BASE_DN)
            authentication = SIMPLE

        server = Server(ldap_server, get_info=ALL, use_ssl=SSL)
        conn = Connection(
            server,
            user=user,
            password=LDAP_PASSWORD,
            authentication=authentication,
            raise_exceptions=True,
            auto_bind=True,
        )

        return search_ldap_users(conn, excluded_accounts)

    def update_person_list_with_ldap_users(users):
        persons_updated = []
        for user in users:
            if persons_service.is_user_limit_reached():
                raise IsUserLimitReachedException
            first_name = user["first_name"]
            last_name = user["last_name"]
            desktop_login = user["desktop_login"]
            email = user["email"]
            active = user.get("active", True)
            if "thumbnail" in user and len(user["thumbnail"]) > 0:
                thumbnail = user["thumbnail"][0]
            else:
                thumbnail = ""

            person = None
            try:
                person = persons_service.get_person_by_desktop_login(
                    desktop_login
                )
            except PersonNotFoundException:
                try:
                    person = persons_service.get_person_by_email(email)
                except PersonNotFoundException:
                    pass

            if len(email) == 0 or email == "[]" or type(email) != str:
                email = "%s@%s" % (desktop_login, EMAIL_DOMAIN)

            if person is None and active is True:
                try:
                    person = persons_service.create_person(
                        email,
                        "default".encode("utf-8"),
                        first_name,
                        last_name,
                        desktop_login=desktop_login,
                        is_generated_from_ldap=True,
                    )
                    print("User %s created." % desktop_login)
                    persons_updated.append(person["id"])
                except:
                    print(
                        "User %s creation failed (email duplicated?)."
                        % (desktop_login)
                    )

            elif person is not None:
                try:
                    person = persons_service.update_person(
                        person["id"],
                        {
                            "email": email,
                            "first_name": first_name,
                            "last_name": last_name,
                            "active": active,
                            "is_generated_from_ldap": True,
                            "desktop_login": desktop_login,
                        },
                    )
                    print("User %s updated." % desktop_login)
                    persons_updated.append(person["id"])
                except:
                    print(
                        "User %s update failed (email duplicated?)."
                        % (desktop_login)
                    )

            if person is not None and len(thumbnail) > 0:
                save_thumbnail(person, thumbnail)

        for person in (
            Person.query.filter_by(is_generated_from_ldap=True, active=True)
            .filter(not_(Person.id.in_(persons_updated)))
            .all()
        ):
            persons_service.update_person(person.id, {"active": False})
            print(
                "User %s disabled (not found in LDAP)." % person.desktop_login
            )

    def save_thumbnail(person, thumbnail):
        from zou.app import app

        with app.app_context():
            thumbnail_path = "/tmp/ldap_th.jpg"
            with open(thumbnail_path, "wb") as th_file:
                th_file.write(thumbnail)
            thumbnail_png_path = thumbnail_utils.convert_jpg_to_png(
                thumbnail_path
            )
            thumbnail_utils.turn_into_thumbnail(
                thumbnail_png_path, size=thumbnail_utils.BIG_SQUARE_SIZE
            )
            file_store.add_picture(
                "thumbnails", person["id"], thumbnail_png_path
            )
            os.remove(thumbnail_png_path)
            persons_service.update_person(person["id"], {"has_avatar": True})

    ldap_users = get_ldap_users()
    update_person_list_with_ldap_users(ldap_users)


def import_data_from_another_instance(
    target,
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
    sync_service.init(target, login, password)
    if not only_projects:
        sync_service.run_main_data_sync(project=project)
    if not no_projects:
        sync_service.run_project_data_sync(project=project)
        sync_service.run_other_sync(project=project)


def run_sync_change_daemon(event_target, target, login, password, logs_dir):
    """
    Listen to event websocket. Each time a change occurs, it retrieves the
    related data and save it in the current instance.
    """
    event_client = sync_service.init_events_listener(
        target, event_target, login, password, logs_dir
    )
    sync_service.add_main_sync_listeners(event_client)
    sync_service.add_project_sync_listeners(event_client)
    sync_service.add_special_sync_listeners(event_client)
    print("Start listening.")
    sync_service.run_listeners(event_client)


def run_sync_file_change_daemon(
    event_target, target, login, password, logs_dir
):
    """
    Listen to event websocket. Each time a change occurs, it retrieves the
    related file and save it in the current instance storage.
    """
    event_client = sync_service.init_events_listener(
        target, event_target, login, password, logs_dir
    )
    sync_service.add_file_listeners(event_client)
    print("Start listening.")
    sync_service.run_listeners(event_client)


def import_last_changes_from_another_instance(
    target, login, password, minutes=0, page_size=300
):
    """
    Retrieve and save all the data related to most recent events from another
    API instance. It doesn't change the IDs.
    """
    sync_service.init(target, login, password)
    print("Last events syncing started.")
    sync_service.run_last_events_sync(minutes=minutes, page_size=300)
    print("Last events syncing ended.")


def import_last_file_changes_from_another_instance(
    target, login, password, minutes=20, page_size=50, force=False
):
    """
    Retrieve and save all the data related most to recent file events
    from another API instance (new previews and thumbnails).
    It doesn't change the IDs.
    """
    sync_service.init(target, login, password)
    print("Last files syncing started.")
    sync_service.run_last_events_files(minutes=minutes, page_size=50)
    print("Last files syncing ended.")


def import_files_from_another_instance(target, login, password, project=None):
    """
    Retrieve and save all the data related most recent events from another API
    instance. It doesn't change the IDs.
    """
    sync_service.init(target, login, password)
    sync_service.download_files_from_another_instance(project=project)


def download_file_from_storage():
    sync_service.download_entity_thumbnails_from_storage()
    sync_service.download_preview_files_from_storage()


def dump_database():
    filename = backup_service.generate_db_backup(
        app.config["DATABASE"]["host"],
        app.config["DATABASE"]["port"],
        app.config["DATABASE"]["username"],
        app.config["DATABASE"]["password"],
        app.config["DATABASE"]["database"],
    )
    backup_service.store_db_backup(filename)


def upload_files_to_cloud_storage(days):
    backup_service.upload_entity_thumbnails_to_storage(days)
    backup_service.upload_preview_files_to_storage(days)


def reset_tasks_data(project_id):
    deletion_service.reset_tasks_data(project_id)


def remove_old_data(days_old=90):
    print("Start removing non critical data older than %s." % days_old)
    print("Removing old events...")
    deletion_service.remove_old_events(days_old)
    print("Removing old login logs...")
    deletion_service.remove_old_login_logs(days_old)
    print("Removing old notitfications...")
    deletion_service.remove_old_notifications(days_old)
    print("Old data removed.")


def reset_search_index():
    print("Resetting search index.")
    index_service.reset_index()
    print("Search index resetted.")


def init_search_index():
    print("Initialising search index.")
    init_indexes()
    print("Search index initialised.")


def search_asset(query):
    assets = index_service.search_assets(query)
    if len(assets) == 0:
        print("No asset found")
    for asset in assets:
        print(asset["name"], asset["id"])
    return assets
