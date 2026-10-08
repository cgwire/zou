"""
Pull-based synchronization from another Kitsu instance through gazu.

The service logs in to a remote instance and mirrors its data locally,
model by model, following the API event log to fetch only what changed
since the last run (see _fetch_events / cursor_event_id). It is meant
for one-way replication (a studio mirror, a backup instance); it never
pushes local changes back. File synchronization (previews, thumbnails)
downloads to a temporary path first and cleans it up on failure so a
partial download never lands in the store.
"""

import datetime
import logging
import os
import sys
import time
import requests

import gazu
import sqlalchemy


from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.build_job import BuildJob
from zou.app.models.custom_action import CustomAction
from zou.app.models.comment import Comment
from zou.app.models.day_off import DayOff
from zou.app.models.department import Department
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType
from zou.app.models.event import ApiEvent
from zou.app.models.organisation import Organisation
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.milestone import Milestone
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.models.time_spent import TimeSpent
from zou.app.models.studio import Studio
from zou.app.models.status_automation import StatusAutomation

from zou.app.services import (
    deletion_service,
    tasks_service,
)
from zou.app.utils import events, date_helpers

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOGLEVEL", "INFO").upper())
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


event_name_model_map = {
    "attachment-file": AttachmentFile,
    "asset": Entity,
    "asset-type": EntityType,
    "build-job": BuildJob,
    "custom-action": CustomAction,
    "comment": Comment,
    "concept": Entity,
    "department": Department,
    "day-off": DayOff,
    "entity": Entity,
    "entity-link": EntityLink,
    "entity-type": EntityType,
    "episode": Entity,
    "event": ApiEvent,
    "organisation": Organisation,
    "metadata-descriptor": MetadataDescriptor,
    "milestone": Milestone,
    "news": News,
    "notification": Notification,
    "person": Person,
    "playlist": Playlist,
    "preview-background-file": PreviewBackgroundFile,
    "preview-file": PreviewFile,
    "project": Project,
    "project-status": ProjectStatus,
    "sequence": Entity,
    "shot": Entity,
    "schedule-item": ScheduleItem,
    "subscription": Subscription,
    "search-filter": SearchFilter,
    "search-filter-group": SearchFilterGroup,
    "status-automation": StatusAutomation,
    "studio": Studio,
    "task": Task,
    "task-status": TaskStatus,
    "task-type": TaskType,
    "time-spent": TimeSpent,
}

event_name_model_path_map = {
    "attachment-file": "attachment-files",
    "asset": "assets",
    "asset-type": "entity-types",
    "build-job": "build-jobs",
    "comment": "comments",
    "concept": "concepts",
    "custom-action": "custom-actions",
    "day-off": "day-offs",
    "department": "departments",
    "entity": "entities",
    "entity-link": "entity-links",
    "entity-type": "entity-types",
    "episode": "episodes",
    "event": "events",
    "metadata-descriptor": "metadata-descriptors",
    "milestone": "milestones",
    "news": "news",
    "notification": "notifications",
    "organisation": "organisations",
    "person": "persons",
    "playlist": "playlists",
    "preview-background-file": "preview-background-files",
    "preview-file": "preview-files",
    "project": "projects",
    "project-status": "project-status",
    "sequence": "sequences",
    "shot": "shots",
    "schedule-item": "schedule-items",
    "search-filter": "search-filters",
    "search-filter-group": "search-filter-groups",
    "subscription": "subscriptions",
    "status-automation": "status-automations",
    "studio": "studios",
    "task": "tasks",
    "task-status": "task-status",
    "task-type": "task-types",
    "time-spent": "time-spents",
}

project_events = [
    "episode",
    "sequence",
    "asset",
    "shot",
    "task",
    "preview-file",
    "time-spent",
    "playlist",
    "build-job",
    "comment",
    "concept",
    "attachment-file",
    "metadata-descriptor",
    "schedule-item",
    "subscription",
    "notification",
    "entity-link",
    "news",
    "milestone",
]

main_events = [
    "studio",
    "department",
    "task-type",
    "task-status",
    "status-automation",
    "custom-action",
    "organisation",
    "project-status",
    "asset-type",
    "person",
    "project",
]


special_events = [
    "preview-file:set-main",
    "shot:casting-update",
    "task:unassign",
    "task:assign",
]


def check_sync_account():
    """
    Warn when the sync account is not an admin on the source instance. The log
    routes are scoped to the caller's productions, so a non-admin account
    never sees the events carrying no project at all, nor the productions it
    is not a member of. Never raises: syncing a single production with a
    manager account stays legitimate.
    """
    try:
        user = gazu.client.get_current_user()
    except Exception:
        logger.warning(
            "Could not read the role of the sync account on the source "
            "instance."
        )
        return False

    if user.get("role") != "admin":
        logger.warning(
            f"The sync account ({user.get('email')}) is not an admin on the "
            "source instance: the event log is scoped to its productions. "
            "Events carrying no project (organisation and person thumbnails, "
            "settings) and events of productions it does not belong to will "
            "be missing from the sync."
        )
        return False
    return True


def init(source, login, password, multithreaded=False, number_workers=30):
    """
    Set parameters for the client that will retrieve data from the source.
    """
    if multithreaded:
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=number_workers,
            pool_maxsize=number_workers * 2,
            max_retries=3,
        )
        gazu.raw.default_client.session.mount(
            source,
            adapter,
        )

    gazu.set_host(source)
    gazu.log_in(login, password)
    check_sync_account()


def init_events_listener(source, event_source, login, password, logs_dir=None):
    """
    Set parameters for the client that will listen to events from the source.
    """
    gazu.set_event_host(event_source)
    gazu.set_host(source)
    gazu.log_in(login, password)
    if logs_dir is not None:
        set_logger(logs_dir)
    check_sync_account()

    return gazu.events.init()


def set_logger(logs_dir):
    """
    Configure so that it logs results to a file stored in a given folder.
    """
    file_name = os.path.join(logs_dir, "zou_sync_changes.log")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        file_name, when="D"
    )

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def run_listeners(event_client):
    """
    Run event listener which will run all previously associated callbacks to
    """
    try:
        gazu.events.run_client(event_client)
    except KeyboardInterrupt:
        raise
    except Exception:
        logger.error("An error occured.", exc_info=1)
        run_listeners(event_client)


def run_main_data_sync(project=None):
    """
    Retrieve and import all cross-projects data from source instance.
    """
    for event in main_events:
        path = event_name_model_path_map[event]
        model = event_name_model_map[event]
        sync_entries(path, model, project=project)


def run_project_data_sync(project=None):
    """
    Retrieve and import all data related to projects from source instance.
    """
    if project:
        projects = [gazu.project.get_project_by_name(project)]
    else:
        projects = gazu.project.all_open_projects()
    for project in projects:
        logger.info(f"Syncing {project['name']}...")
        for event in project_events:
            logger.info(f"Syncing {event}s...")
            path = event_name_model_path_map[event]
            model = event_name_model_map[event]
            sync_project_entries(project, path, model)
        sync_entity_thumbnails(project, "assets")
        sync_entity_thumbnails(project, "shots")
        sync_entity_thumbnails(project, "concepts")
        logger.info(f"Sync of {project['name']} complete.")


def run_other_sync(project=None, with_events=False):
    """
    Retrieve and import all search filters and events from source instance.
    """
    sync_entries("search-filter-groups", SearchFilterGroup, project=project)
    sync_entries("search-filters", SearchFilter, project=project)
    # Day-offs are not scoped per project on the source side; only pull them
    # for full-instance syncs, otherwise a single-project sync would import
    # day-offs from every other project on the source.
    if project is None:
        sync_entries("day-offs", DayOff, project=project)
    if with_events:
        sync_entries("events", ApiEvent, project=project)


def push_project_data(
    target,
    login,
    password,
    project_name,
    batch_size=200,
    throttle=0.0,
    silent=True,
):
    """
    Push a single project's data to a target zou instance via the
    /import/kitsu/* routes. Reference data (persons, departments, task
    types/statuses, asset types, studios) is assumed to already exist on
    the target with matching UUIDs — the routes will fail on foreign-key
    violation if it doesn't.

    ``throttle`` is a pause (in seconds) between every batch POST. Useful
    to spare the target instance under load — set to 0.5 or 1.0 if the
    default rate causes timeouts or saturates request workers.

    ``silent`` (default True) appends ``?silent=true`` to every POST so
    the target skips per-row ``events.emit`` — no api_event rows written
    and no Redis broadcast per imported entry. Bulk migration is not
    something connected UIs need a live event storm for.
    """
    gazu.set_host(target)
    gazu.log_in(login, password)

    project = Project.get_by(name=project_name)
    if project is None:
        raise Exception(f"Project '{project_name}' not found locally.")
    project_id = str(project.id)
    logger.info(f"Pushing {project.name} ({project_id}) to {target}...")

    _push_batch(
        "/import/kitsu/projects",
        [project.serialize(relations=True)],
        batch_size,
        silent=silent,
    )

    _push_query(
        "/import/kitsu/metadata-descriptors",
        MetadataDescriptor.query.filter_by(project_id=project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
        relations=True,
    )
    _push_query(
        "/import/kitsu/milestones",
        Milestone.query.filter_by(project_id=project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )

    # Entities in hierarchy order so FKs (parent_id) resolve as we go.
    for entity_type_name in (
        "Episode",
        "Sequence",
        "Asset",
        "Shot",
        "ConceptFolder",
        "Concept",
    ):
        entity_type = EntityType.get_by(name=entity_type_name)
        if entity_type is None:
            continue
        _push_query(
            "/import/kitsu/entities",
            Entity.query.filter_by(
                project_id=project_id, entity_type_id=entity_type.id
            ),
            batch_size=batch_size,
            throttle=throttle,
            silent=silent,
            label=f"/import/kitsu/entities ({entity_type_name})",
        )

    _push_query(
        "/import/kitsu/schedule-items",
        ScheduleItem.query.filter_by(project_id=project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )
    _push_query(
        "/import/kitsu/entity-links",
        EntityLink.query.join(
            Entity, EntityLink.entity_in_id == Entity.id
        ).filter(Entity.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )

    _push_query(
        "/import/kitsu/tasks",
        Task.query.filter_by(project_id=project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )
    _push_query(
        "/import/kitsu/subscriptions",
        Subscription.query.join(Task).filter(Task.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )
    _push_query(
        "/import/kitsu/notifications",
        Notification.query.join(Task).filter(Task.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )
    _push_query(
        "/import/kitsu/time-spents",
        TimeSpent.query.join(Task).filter(Task.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )

    _push_query(
        "/import/kitsu/comments",
        Comment.query.join(Task, Comment.object_id == Task.id).filter(
            Task.project_id == project_id
        ),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
        relations=True,
    )
    _push_query(
        "/import/kitsu/preview-files",
        PreviewFile.query.join(Task).filter(Task.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
        # source_file_id -> OutputFile.id, and OutputFile is out of scope
        # for sync-push (see the verify "NOT SYNCED" rows). Strip it so the
        # FK doesn't blow up the whole batch on the target side.
        strip_fields=["source_file_id"],
    )

    _push_query(
        "/import/kitsu/attachment-files",
        AttachmentFile.query.join(Comment)
        .join(Task, Comment.object_id == Task.id)
        .filter(Task.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )
    _push_query(
        "/import/kitsu/news",
        News.query.join(Task).filter(Task.project_id == project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )

    _push_query(
        "/import/kitsu/playlists",
        Playlist.query.filter_by(project_id=project_id),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
        relations=True,
    )
    _push_query(
        "/import/kitsu/build-jobs",
        BuildJob.query.join(Playlist).filter(
            Playlist.project_id == project_id
        ),
        batch_size=batch_size,
        throttle=throttle,
        silent=silent,
    )

    logger.info(f"Push of {project.name} complete.")


def _push_query(
    path,
    query,
    batch_size=200,
    relations=False,
    label=None,
    strip_fields=None,
    throttle=0.0,
    silent=True,
):
    """
    Page through a query (offset+limit) and POST one batch at a time.
    Avoids loading the whole table into memory before the first POST,
    which matters on high-volume tables (comments, preview-files)
    especially with ``relations=True`` triggering joined lookups per row.

    offset+limit is used rather than ``yield_per`` because several models
    define eager loaders on their collections (joinedload/subqueryload),
    which yield_per refuses to combine with.
    """
    display = label or path
    post_path = f"{path}?silent=true" if silent else path
    total_expected = query.count()
    if total_expected == 0:
        logger.info(f"  {display}: nothing to push")
        return

    logger.info(f"  {display}: pushing {total_expected} rows...")

    offset = 0
    total = 0
    failed = 0

    while True:
        instances = query.offset(offset).limit(batch_size).all()
        if not instances:
            break
        items = []
        for instance in instances:
            item = instance.serialize(relations=relations)
            if strip_fields:
                for field in strip_fields:
                    item.pop(field, None)
            items.append(item)
        try:
            gazu.client.post(post_path, items)
        except Exception:
            logger.error(
                f"  {display}: batch at offset {offset} failed", exc_info=1
            )
            failed += len(items)
        total += len(items)
        percent = 100.0 * total / total_expected
        suffix = f" [{failed} failed]" if failed else ""
        logger.info(
            f"  {display}: {total}/{total_expected} ({percent:.1f}%){suffix}"
        )
        offset += batch_size
        if throttle > 0 and total < total_expected:
            time.sleep(throttle)

    if failed:
        logger.warning(
            f"  {display}: pushed {total - failed}/{total} rows "
            f"({failed} failed)"
        )
    else:
        logger.info(f"  {display}: pushed {total} rows")


def _push_batch(path, payload, batch_size=200, label=None, silent=True):
    """
    One-shot POST helper for the small pre-built lists (e.g. the
    project itself). For query-driven pushes, use _push_query.
    """
    display = label or path
    post_path = f"{path}?silent=true" if silent else path
    total = len(payload)
    failed = 0
    for offset in range(0, total, batch_size):
        chunk = payload[offset : offset + batch_size]
        try:
            gazu.client.post(post_path, chunk)
        except Exception:
            logger.error(f"  {display}: batch {offset} failed", exc_info=1)
            failed += len(chunk)
    if failed:
        logger.warning(
            f"  {display}: pushed {total - failed}/{total} rows "
            f"({failed} failed)"
        )
    else:
        logger.info(f"  {display}: pushed {total} rows")


def _add_time_window(path, minutes):
    """
    Append before/after query parameters covering the last given minutes.
    """
    now = date_helpers.get_utc_now_datetime()
    min_before = now - datetime.timedelta(minutes=minutes)
    after = min_before.strftime("%Y-%m-%dT%H:%M:%S")
    path += f'&before={now.strftime("%Y-%m-%dT%H:%M:%S")}'
    path += f"&after={after}"
    return path


def _fetch_events(path, limit, paginate):
    """
    Fetch events from the source instance, newest first. When paginate is
    set, follow the cursor until the whole time window is covered, so a
    burst bigger than the page size does not silently drop events.
    """
    events = []
    cursor = None
    while True:
        page_path = path
        if cursor is not None:
            page_path += f"&cursor_event_id={cursor}"
        page = gazu.client.fetch_all(page_path)
        events += page
        if not paginate or len(page) < limit:
            break
        cursor = page[-1]["id"]
    return events


def run_last_events_sync(minutes=0, limit=300):
    """
    Retrieve last events from source instance and import related data and
    action.
    """
    path = f"events/last?limit={limit}"
    if minutes > 0:
        path = _add_time_window(path, minutes)
    events = _fetch_events(path, limit, paginate=minutes > 0)
    events.reverse()
    for event in events:
        event_name = event["name"].split(":")[0]
        if event_name in event_name_model_map:
            try:
                sync_event(event)
            except Exception:
                logger.exception(
                    f"Failed to sync event {event['id']} ({event['name']})"
                )


def sync_event(event):
    """
    From information given by an event, retrieve related data and apply it.
    """
    event_name = event["name"]
    [event_name, action] = event_name.split(":")

    model = event_name_model_map[event_name]
    path = event_name_model_path_map[event_name]

    if event_name == "metadata-descriptor":  # Backward compatibility
        if "metadata_descriptor_id" not in event["data"]:
            event_name = "descriptor"
    instance_id = event["data"][f"{event_name.replace('-', '_')}_id"]

    if action in ["update", "new"]:
        instance = gazu.client.fetch_one(path, instance_id)
        model.create_from_import(instance)
    elif action in ["delete"]:
        model.delete_from_import(instance_id)


def sync_entries(model_name, model, project=None):
    """
    Retrieve cross-projects data from source instance.
    """
    instances = []

    page = 1
    init = True
    results = {"nb_pages": 2}
    params = {
        "relations": "true",
    }
    if model_name == "persons":
        params["with_pass_hash"] = "true"
    if project is not None and model_name in [
        "projects",
        "search-filters",
        "search-filter-groups",
    ]:
        # Added to the parameters, never substituted for them: the team and
        # the task types of a production are only serialized when the
        # relations are asked for.
        project = gazu.project.get_project_by_name(project)
        if model_name == "projects":
            params["id"] = project["id"]
        else:
            params["project_id"] = project["id"]
    while init or results["nb_pages"] >= page:
        params["page"] = page
        results = gazu.client.fetch_all(model_name, params=params)
        if model_name == "task-status" and results["data"]:
            results["data"] = [
                r for r in results["data"] if not r["for_concept"]
            ]
        instances += results["data"]
        page += 1
        init = False
        model.create_from_import_list(results["data"])

    logger.info(f"{len(instances)} {model_name} synced.")


def sync_project_entries(project, model_name, model):
    """
    Retrieve all project data from source instance.
    """
    instances = []
    page = 1
    init = True
    results = {"nb_pages": 2}
    result_length = 1
    if model_name not in [
        "tasks",
        "comments",
        "news",
        "notifications",
        "playlists",
        "preview-files",
    ]:  # not much data we retrieve all in a single request.
        path = f"projects/{project['id']}/{model_name}"
        results = gazu.client.fetch_all(path)
        instances += results
        try:
            model.create_from_import_list(instances)
        except sqlalchemy.exc.IntegrityError:
            logger.error("An error occured", exc_info=1)

    elif model_name == "news":
        while init or result_length > 0:
            path = f'projects/{project["id"]}/{model_name}?page={page}'
            results = gazu.client.fetch_all(path)["data"]
            instances += results
            try:
                model.create_from_import_list(results)
            except sqlalchemy.exc.IntegrityError:
                logger.error("An error occured", exc_info=1)
            result_length = len(results)
            page += 1
            init = False

    else:  # Lot of data, we retrieve all through paginated requests.
        while init or results["nb_pages"] >= page:
            path = f'projects/{project["id"]}/{model_name}?page={page}'
            if model_name == "playlists":
                path = f'projects/{project["id"]}/playlists/all?page={page}'
            results = gazu.client.fetch_all(path)
            instances += results["data"]
            try:
                model.create_from_import_list(results["data"])
            except sqlalchemy.exc.IntegrityError:
                logger.error("An error occured", exc_info=1)
            page += 1
            init = False
    logger.info(f"    {len(instances)} {model_name} synced.")


def sync_entity_thumbnails(project, model_name):
    """
    Once every preview files and entities has been imported, this function
    allows you to import project entities again to set thumbnails id (link to
    a preview file) for all entities.
    """
    results = gazu.client.fetch_all(f"projects/{project['id']}/{model_name}")
    total = 0
    for result in results:
        if result.get("preview_file_id") is not None:
            entity = Entity.get(result["id"])
            try:
                entity.update(
                    {
                        "preview_file_id": result["preview_file_id"],
                        "updated_at": result["updated_at"],
                    }
                )
                total += 1
            except sqlalchemy.exc.IntegrityError:
                logger.error("An error occured", exc_info=1)
    logger.info(f"    {total} {model_name} thumbnails synced.")


def add_main_sync_listeners(event_client):
    """
    Add listeners to manage CRUD events related to general data.
    """
    for event in main_events:
        path = event_name_model_path_map[event]
        model = event_name_model_map[event]
        add_sync_listeners(event_client, path, event, model)


def add_project_sync_listeners(event_client):
    """
    Add listeners to manage CRUD events related to open projects data.
    """
    for event in project_events:
        path = event_name_model_path_map[event]
        model = event_name_model_map[event]
        add_sync_listeners(event_client, path, event, model)


def add_special_sync_listeners(event_client):
    """
    Add listeners to forward all non CRUD events to local event broadcaster.
    """
    for event in special_events:
        gazu.events.add_listener(event_client, event, forward_event(event))


def add_sync_listeners(event_client, model_name, event_name, model):
    """
    Add Create, Update and Delete event listeners for givent model name to given
    event client.
    """
    gazu.events.add_listener(
        event_client,
        f"{event_name}:new",
        create_entry(model_name, event_name, model, "new"),
    )
    gazu.events.add_listener(
        event_client,
        f"{event_name}:update",
        create_entry(model_name, event_name, model, "update"),
    )
    gazu.events.add_listener(
        event_client,
        f"{event_name}:delete",
        delete_entry(model_name, event_name, model),
    )


def create_entry(model_name, event_name, model, event_type):
    """
    Generate a function that creates a model each time a related creation event
    is retrieved. If it's an update event, it updates the model related to the
    event. Data are retrived through the HTTP client.
    It's useful to generate callbacks for event listener.
    """

    def create(data):
        if data.get("sync", False):
            return
        model_id_field_name = event_name.replace("-", "_") + "_id"
        model_id = data[model_id_field_name]
        try:
            instance = gazu.client.fetch_one(model_name, model_id)
            model.create_from_import(instance)
            forward_base_event(event_name, event_type, data)
            if event_type == "new":
                logger.info(f"Creation: {event_name} {model_id}")
            else:
                logger.info(f"Update: {event_name} {model_id}")
        except gazu.exception.RouteNotFoundException as e:
            logger.error(f"Route not found: {e}")
            logger.error(f"Fail {event_name} created/updated {model_id}")

    return create


def delete_entry(model_name, event_name, model):
    """
    Generate a function that delete a model each time a related deletion event
    is retrieved.
    It's useful to generate callbacks for event listener.
    """

    def delete(data):
        if data.get("sync", False):
            return
        model_id = data[event_name.replace("-", "_") + "_id"]
        if event_name == "comment":
            comment = deletion_service.remove_comment(model_id)
            tasks_service.reset_task_data(comment["object_id"])
        else:
            model.delete_all_by(id=model_id)
        forward_base_event(event_name, "delete", data)
        logger.info(f"Deletion: {model_name} {model_id}")

    return delete


def forward_local_event(event_name, data):
    """
    Forward an event of the source instance to the local broadcaster. What
    this instance emitted itself comes back flagged and is dropped here,
    otherwise the two instances would keep answering each other.
    """
    if data.get("sync", False):
        return
    data["sync"] = True
    logger.info(f"Forward event: {event_name}")
    project_id = data.get("project_id", None)
    events.emit(event_name, data, persist=False, project_id=project_id)


def forward_event(event_name):
    """
    Generate a function that takes data in argument and that forwards it as
    given event name to the local event brodcaster.
    It's useful to generate callbacks for event listener. Call
    forward_local_event directly when the name is already known: this one
    only binds it, it forwards nothing by itself.
    """
    return lambda data: forward_local_event(event_name, data)


def forward_base_event(event_name, event_type, data):
    """
    Forward given event to current instance event queue.
    """
    full_event_name = f"{event_name}:{event_type}"
    data["sync"] = True
    logger.info(f"Forward event: {full_event_name}")
    project_id = data.get("project_id", None)
    events.emit(full_event_name, data, project_id=project_id)
