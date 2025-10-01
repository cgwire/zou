# coding: utf-8

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
from zou.app.stores import auth_tokens_store, file_store, queue_store
from zou.app.services import (
    assets_service,
    backup_service,
    breakdown_service,
    deletion_service,
    edits_service,
    index_service,
    persons_service,
    preview_files_service,
    projects_service,
    shots_service,
    sync_service,
    tasks_service,
)
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.plugin import Plugin
from sqlalchemy.sql.expression import not_

from zou.app.services.exception import (
    PersonNotFoundException,
    IsUserLimitReachedException,
)

from zou.app import config

from zou.app import app


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


def init_data():
    """
    Put the minimum required data into the database to start with it.
    """
    with app.app_context():
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

        modeling = tasks_service.get_or_create_department(
            "Modeling", "#78909C"
        )
        animation = tasks_service.get_or_create_department(
            "Animation", "#009688"
        )
        fx = tasks_service.get_or_create_department("FX", "#26C6DA")
        compositing = tasks_service.get_or_create_department(
            "Compositing", "#F06292"
        )
        concept = tasks_service.get_or_create_department("Concept", "#8D6E63")
        layout = tasks_service.get_or_create_department("Layout", "#7CB342")

        tasks_service.get_or_create_task_type(concept, "Concept", "#8D6E63", 1)
        tasks_service.get_or_create_task_type(
            modeling, "Modeling", "#78909C", 2
        )
        tasks_service.get_or_create_task_type(
            modeling, "Shading", "#64B5F6", 3
        )
        tasks_service.get_or_create_task_type(
            animation, "Rigging", "#9CCC65", 4
        )

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

        tasks_service.get_or_create_task_type(
            concept, "Concept", "#8D6E63", 1, for_entity="Concept"
        )

        print("Task types initialized.")

        tasks_service.get_default_status()
        tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )
        tasks_service.get_or_create_status(
            "Waiting For Approval", "wfa", "#ab26ff", is_feedback_request=True
        )
        tasks_service.get_or_create_status(
            "Retake", "retake", "#ff3860", is_retake=True
        )
        tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.get_or_create_status(
            "Ready To Start", "ready", "#fbc02d"
        )

        tasks_service.get_or_create_status(
            "Neutral",
            "neutral",
            "#CCCCCC",
            is_default=True,
            for_concept=True,
            is_artist_allowed=True,
            is_client_allowed=True,
        )

        tasks_service.get_or_create_status(
            "Approved",
            "approved",
            "#66BB6A",
            for_concept=True,
            is_artist_allowed=True,
            is_client_allowed=True,
        )

        tasks_service.get_or_create_status(
            "Rejected",
            "rejected",
            "#E81123",
            for_concept=True,
            is_artist_allowed=True,
            is_client_allowed=True,
        )

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
            if LDAP_IS_AD_SIMPLE:
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
        if len(LDAP_GROUP) > 0:
            if is_ad:
                query = f"(&(objectClass=person)(memberOf={LDAP_GROUP}))"
            else:
                conn.search(
                    LDAP_BASE_DN,
                    f"(&(objectClass=groupofUniqueNames)(cn={LDAP_GROUP}))",
                    attributes=["uniqueMember"],
                )
                group_members = conn.entries[0].uniqueMember.values
        conn.search(LDAP_BASE_DN, query, attributes=attributes)
        ldap_users = []
        for entry in conn.entries:
            if LDAP_IS_AD_SIMPLE:
                desktop_login = entry.cn
            elif LDAP_IS_AD:
                desktop_login = entry.sAMAccountName
            else:
                desktop_login = entry.uid
            desktop_login = clean_value(desktop_login)

            if desktop_login not in excluded_accounts and (
                group_members is None or entry.entry_dn in group_members
            ):
                if is_ad:
                    ldap_uid = clean_value(entry.objectGUID)
                elif entry.uniqueIdentifier:
                    ldap_uid = clean_value(entry.uniqueIdentifier)
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
                    emails = ["%s@%s" % (desktop_login, EMAIL_DOMAIN)]
                else:

                    def sort_mails(email):
                        if email == desktop_login:
                            return -2
                        elif EMAIL_DOMAIN in email:
                            return -1
                        else:
                            return 0

                    emails = sorted(emails, key=sort_mails)

                if is_ad:
                    active = bool(entry.userAccountControl.value & 2) is False
                elif entry.organizationalStatus:
                    active = (
                        entry.organizationalStatus.value.lower() == "active"
                    )
                else:
                    active = False

                ldap_users.append(
                    {
                        "first_name": clean_value(entry.givenName or entry.cn),
                        "last_name": clean_value(entry.sn),
                        "email": emails[0].lower(),
                        "emails": emails,
                        "desktop_login": desktop_login,
                        "thumbnail": thumbnail,
                        "active": active,
                        "ldap_uid": ldap_uid,
                    }
                )
        return ldap_users

    def get_ldap_users():
        excluded_accounts = LDAP_EXCLUDED_ACCOUNTS.split(",")
        ldap_server = f"{LDAP_HOST}:{LDAP_PORT}"
        SSL = LDAP_SSL
        if LDAP_IS_AD_SIMPLE:
            user = LDAP_USER
            authentication = SIMPLE
        elif LDAP_IS_AD:
            user = f"{LDAP_DOMAIN}\\{LDAP_USER}"
            authentication = NTLM
        else:
            user = f"uid={LDAP_USER},{LDAP_BASE_DN}"
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
        persons_to_update = []
        persons_to_create = []
        for user in sorted(users, key=lambda k: k["active"]):
            person = None
            try:
                person = persons_service.get_person_by_ldap_uid(
                    user["ldap_uid"]
                )
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
            .filter(
                not_(Person.id.in_([p[0]["id"] for p in persons_to_update]))
            )
            .all()
        ):
            persons_service.update_person(
                person.id, {"active": False}, bypass_protected_accounts=True
            )
            print(
                "User %s disabled (not found in LDAP)." % person.desktop_login
            )

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
                    f"User {user['desktop_login']} update failed (limit reached, limit {config.USER_LIMIT})."
                )
            except BaseException:
                print(
                    f"User {user['desktop_login']} update failed (email duplicated?)."
                )

            if user["thumbnail"] is not None:
                save_thumbnail(person, user["thumbnail"])

        person = None
        for user in persons_to_create:
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
                        f"User {user['desktop_login']} creation failed (limit reached, limit {config.USER_LIMIT})."
                    )
                except BaseException:
                    print(
                        f"User {user['desktop_login']} creation failed (email duplicated?)."
                    )

            if person is not None and user["thumbnail"] is not None:
                save_thumbnail(person, user["thumbnail"])

    def save_thumbnail(person, thumbnail):
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

    ldap_users = get_ldap_users()
    update_person_list_with_ldap_users(ldap_users)


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
        sync_service.add_file_listeners(event_client)
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
        sync_service.run_last_events_sync(minutes=minutes, limit=300)
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
        sync_service.run_last_events_files(minutes=minutes, limit=50)
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
):
    """
    Retrieve and save all the data related most recent events from another API
    instance. It doesn't change the IDs.
    """
    with app.app_context():
        sync_service.init(
            source, login, password, multithreaded, number_workers
        )
        return sync_service.download_files_from_another_instance(
            project=project,
            multithreaded=multithreaded,
            number_workers=number_workers,
            number_attemps=number_attemps,
            force_resync=force_resync,
        )


def download_file_from_storage():
    with app.app_context():
        sync_service.download_entity_thumbnails_from_storage()
        sync_service.download_preview_files_from_storage()


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
        print("Start removing non critical data older than %s." % days_old)
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
    episodes=[],
    only_shots=False,
    only_assets=False,
    force_regenerate_tiles=False,
    with_tiles=False,
    with_metadata=False,
    with_thumbnails=False,
):
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
        )


def reset_movie_files_metadata():
    with app.app_context():
        preview_files_service.reset_movie_files_metadata()


def reset_picture_files_metadata():
    with app.app_context():
        preview_files_service.reset_picture_files_metadata()


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


def renormalize_movie_preview_files(
    preview_file_id=None,
    project_id=None,
    all_broken=None,
    all_processing=None,
    days=None,
    hours=None,
    minutes=None,
):
    with app.app_context():
        if preview_file_id is None and not all_broken and not all_processing:
            print(
                "You must specify at least one flag from --all-broken or --all-processing."
            )
            sys.exit(1)

        query = PreviewFile.query.filter(
            PreviewFile.extension == "mp4"
        ).order_by(PreviewFile.created_at.asc())

        if any((minutes, hours, days)):
            since_date = datetime.datetime.now() - datetime.timedelta(
                days=days or 0,
                hours=hours or 0,
                minutes=minutes or 0,
            )
            query = query.filter(PreviewFile.created_at >= since_date)

        if preview_file_id is not None:
            query = query.filter(PreviewFile.id == preview_file_id)

        if project_id is not None:
            query = query.join(Task).filter(
                PreviewFile.project_id == project_id
            )

        if all_broken and all_processing:
            query = query.filter(
                PreviewFile.status.in_(("broken", "processing"))
            )
        elif all_broken:
            query = query.filter(PreviewFile.status == "broken")
        elif all_processing:
            query = query.filter(PreviewFile.status == "processing")

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
                    try:
                        if config.FS_BACKEND == "local":
                            shutil.copyfile(
                                file_store.get_local_movie_path(
                                    "source", preview_file_id
                                ),
                                uploaded_movie_path,
                            )
                        else:
                            sync_service.download_file(
                                uploaded_movie_path,
                                "source",
                                file_store.open_movie,
                                str(preview_file_id),
                            )
                    except:
                        pass
                    if config.ENABLE_JOB_QUEUE:
                        queue_store.job_queue.enqueue(
                            preview_files_service.prepare_and_store_movie,
                            args=(
                                preview_file_id,
                                uploaded_movie_path,
                                True,
                                False,
                            ),
                            job_timeout=int(config.JOB_QUEUE_TIMEOUT),
                        )
                    else:
                        preview_files_service.prepare_and_store_movie(
                            preview_file_id,
                            uploaded_movie_path,
                            normalize=True,
                            add_source_to_file_store=False,
                        )
                except Exception as e:
                    print(
                        f"Renormalization of preview file {preview_file_id} failed: {e}"
                    )
                    continue


def list_plugins(output_format, verbose, filter_field, filter_value):
    with app.app_context():
        query = Plugin.query

        # Apply filter if needed
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
                plugin_data["Revision"] = plugin.revision or "-"
                plugin_data["Installation Date"] = plugin.created_at
                plugin_data["Last Update"] = plugin.updated_at
            plugin_list.append(plugin_data)

        if output_format == "table":
            headers = plugin_list[0].keys()
            rows = [p.values() for p in plugin_list]
            click.echo(tabulate(rows, headers, tablefmt="fancy_grid"))
        elif output_format == "json":
            click.echo(json.dumps(plugin_list, indent=2, ensure_ascii=False))
