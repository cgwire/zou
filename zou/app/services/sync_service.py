import datetime
import logging
import os
import sys

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
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.search_filter import SearchFilter
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.models.time_spent import TimeSpent

from zou.app.services import deletion_service, tasks_service
from zou.app.stores import file_store
from flask_fs.backends.local import LocalBackend
from zou.app.utils import events
from zou.app import app

logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


preview_folder = app.config["PREVIEW_FOLDER"]
local_picture = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "pictures")}
)
local_movie = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "movies")}
)
local_file = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "files")}
)


event_name_model_map = {
    "attachment-file": AttachmentFile,
    "asset": Entity,
    "asset-type": EntityType,
    "build-job": BuildJob,
    "custom-action": CustomAction,
    "comment": Comment,
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
    "preview-file": PreviewFile,
    "project": Project,
    "project-status": ProjectStatus,
    "sequence": Entity,
    "shot": Entity,
    "schedule-item": ScheduleItem,
    "subscription": Subscription,
    "search-filter": SearchFilter,
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
    "preview-file": "preview-files",
    "project": "projects",
    "project-status": "project-status",
    "sequence": "sequences",
    "shot": "shots",
    "schedule-item": "schedule-items",
    "search-filter": "search-filters",
    "subscription": "subscriptions",
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
    "person",
    "organisation",
    "project-status",
    "department",
    "task-type",
    "task-status",
    "custom-action",
    "asset-type",
    "project",
]

thumbnail_events = [
    "organisation",
    "person",
    "project",
]

file_events = [
    "preview-file:add-file",
    "organisation:set-thumbnail",
    "person:set-thumbnail",
    "project:set-thumbnail",
]

special_events = [
    "preview-file:set-main",
    "shot:casting-update",
    "task:unassign",
    "task:assign",
]


def init(target, login, password):
    """
    Set parameters for the client that will retrieve data from the target.
    """
    gazu.set_host(target)
    gazu.log_in(login, password)


def init_events_listener(target, event_target, login, password, logs_dir=None):
    """
    Set parameters for the client that will listen to events from the target.
    """
    gazu.set_event_host(event_target)
    gazu.set_host(target)
    gazu.log_in(login, password)
    if logs_dir is not None:
        set_logger(logs_dir)

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
    Retrieve and import all cross-projects data from target instance.
    """
    for event in main_events:
        path = event_name_model_path_map[event]
        model = event_name_model_map[event]
        sync_entries(path, model, project=project)


def run_project_data_sync(project=None):
    """
    Retrieve and import all data related to projects from target instance.
    """
    if project:
        projects = [gazu.project.get_project_by_name(project)]
    else:
        projects = gazu.project.all_open_projects()
    for project in projects:
        logger.info("Syncing %s..." % project["name"])
        for event in project_events:
            print("Syncing %ss..." % event)
            path = event_name_model_path_map[event]
            model = event_name_model_map[event]
            sync_project_entries(project, path, model)
        sync_entity_thumbnails(project, "assets")
        sync_entity_thumbnails(project, "shots")
        logger.info("Sync of %s complete." % project["name"])


def run_other_sync(project=None, with_events=False):
    """
    Retrieve and import all search filters and events from target instance.
    """
    sync_entries("search-filters", SearchFilter, project=project)
    sync_entries("day-offs", SearchFilter, project=project)
    if with_events:
        sync_entries("events", ApiEvent, project=project)


def run_last_events_sync(minutes=0, page_size=300):
    """
    Retrieve last events from target instance and import related data and
    action.
    """
    path = "events/last?page_size=%s" % page_size
    if minutes > 0:
        now = datetime.datetime.now()
        min_before = now - datetime.timedelta(minutes=minutes)
        after = min_before.strftime("%Y-%m-%dT%H:%M:%S")
        path += "&before=%s" % now.strftime("%Y-%m-%dT%H:%M:%S")
        path += "&after=%s" % after
    events = gazu.client.fetch_all(path)
    events.reverse()
    for event in events:
        event_name = event["name"].split(":")[0]
        if event_name in event_name_model_map:
            try:
                sync_event(event)
            except Exception:
                pass


def run_last_events_files(minutes=0, page_size=50):
    """
    Retrieve last events from target instance and import related data and
    action.
    """
    path = "events/last?only_files=true&page_size=%s" % page_size
    if minutes > 0:
        now = datetime.datetime.now()
        min_before = now - datetime.timedelta(minutes=minutes)
        after = min_before.strftime("%Y-%m-%dT%H:%M:%S")
        path += "&before=%s" % now.strftime("%Y-%m-%dT%H:%M:%S")
        path += "&after=%s" % after
    events = gazu.client.fetch_all(path)
    events.reverse()
    for event in events:
        event_name = event["name"].split(":")[0]
        if event_name == "preview-file":
            preview_file = PreviewFile.get(event["data"]["preview_file_id"])
            if preview_file is not None:
                download_preview_from_another_instance(preview_file)
        else:
            download_thumbnail_from_another_instance(
                event_name, event["data"]["%s_id" % event_name]
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
    instance_id = event["data"]["%s_id" % event_name.replace("-", "_")]

    if action in ["update", "new"]:
        instance = gazu.client.fetch_one(path, instance_id)
        model.create_from_import(instance)
    elif action in ["delete"]:
        model.delete_from_import(instance_id)


def sync_entries(model_name, model, project=None):
    """
    Retrieve cross-projects data from target instance.
    """
    instances = []

    if model_name in ["organisations", "persons"]:
        path = model_name + "?relations=true"
        if model_name == "persons":
            path += "&with_pass_hash=true"
        instances = gazu.client.fetch_all(path)
        model.create_from_import_list(instances)
    elif project:
        project = gazu.project.get_project_by_name(project)
        if model_name == "projects":
            instances = [gazu.client.fetch_one(model_name, project.get("id"))]
        elif model_name in "search-filters":
            instances = gazu.client.fetch_all(
                model_name, params=dict(project_id=project.get("id"))
            )
        else:
            instances = gazu.client.fetch_all(model_name)
        model.create_from_import_list(instances)
    else:
        page = 1
        init = True
        results = {"nb_pages": 2}
        while init or results["nb_pages"] >= page:
            results = gazu.client.fetch_all(
                "%s?relations=true&page=%d" % (model_name, page)
            )
            instances += results["data"]
            page += 1
            init = False
            model.create_from_import_list(results["data"])

    logger.info("%s %s synced." % (len(instances), model_name))


def sync_project_entries(project, model_name, model):
    """
    Retrieve all project data from target instance.
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
        path = "projects/%s/%s" % (project["id"], model_name)
        results = gazu.client.fetch_all(path)
        instances += results
        try:
            model.create_from_import_list(instances)
        except sqlalchemy.exc.IntegrityError:
            logger.error("An error occured", exc_info=1)

    elif model_name == "news":
        while init or result_length > 0:
            path = "projects/%s/%s?page=%d" % (project["id"], model_name, page)
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
            path = "projects/%s/%s?page=%d" % (project["id"], model_name, page)
            if model_name == "playlists":
                path = "projects/%s/playlists/all?page=%d" % (
                    project["id"],
                    page,
                )
            results = gazu.client.fetch_all(path)
            instances += results["data"]
            try:
                model.create_from_import_list(results["data"])
            except sqlalchemy.exc.IntegrityError:
                logger.error("An error occured", exc_info=1)
            page += 1
            init = False
    logger.info("    %s %s synced." % (len(instances), model_name))


def sync_entity_thumbnails(project, model_name):
    """
    Once every preview files and entities has been imported, this function
    allows you to import project entities again to set thumbnails id (link to
    a preview file) for all entities.
    """
    results = gazu.client.fetch_all(
        "projects/%s/%s" % (project["id"], model_name)
    )
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
    logger.info("    %s %s thumbnails synced." % (total, model_name))


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
    Add listeners to forward all non CRUD events to local event broadcaster.
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
        "%s:new" % event_name,
        create_entry(model_name, event_name, model, "new"),
    )
    gazu.events.add_listener(
        event_client,
        "%s:update" % event_name,
        create_entry(model_name, event_name, model, "update"),
    )
    gazu.events.add_listener(
        event_client,
        "%s:delete" % event_name,
        delete_entry(model_name, event_name, model),
    )


def create_entry(model_name, event_name, model, event_type):
    """
    Generate a function that creates a model each time a related creation event
    is retrieved. If it's an update event, it updates the model related to the
    event. Data are retrived through the HTTP client.
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
                logger.info("Creation: %s %s" % (event_name, model_id))
            else:
                logger.info("Update: %s %s" % (event_name, model_id))
        except gazu.exception.RouteNotFoundException as e:
            logger.error("Route not found: %s" % e)
            logger.error("Fail %s created/updated %s" % (event_name, model_id))

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
        logger.info("Deletion: %s %s" % (model_name, model_id))

    return delete


def forward_event(event_name):
    """
    Generate a function that takes data in argument and that forwards it as
    given event name to the local event brodcaster.
    It's useful to generate callbacks for event listener.
    """

    def forward(data):
        if not data.get("sync", False):
            data["sync"] = True
            logger.info("Forward event: %s" % event_name)
            project_id = data.get("project_id", None)
            events.emit(event_name, data, persist=False, project_id=project_id)

    return forward


def forward_base_event(event_name, event_type, data):
    """
    Forward given event to current instance event queue.
    """
    full_event_name = "%s:%s" % (event_name, event_type)
    data["sync"] = True
    logger.info("Forward event: %s" % full_event_name)
    project_id = data.get("project_id", None)
    events.emit(full_event_name, data, project_id=project_id)


def add_file_listeners(event_client):
    """
    Add new preview event listener.
    """
    gazu.events.add_listener(
        event_client, "preview-file:add-file", retrieve_file
    )
    for model_name in thumbnail_events:
        gazu.events.add_listener(
            event_client,
            "%s:set-thumbnail" % model_name,
            get_retrieve_thumbnail(model_name),
        )


def retrieve_file(data):
    if data.get("sync", False):
        return
    try:
        preview_file_id = data["preview_file_id"]
        preview_file = PreviewFile.get(preview_file_id)
        download_preview_from_another_instance(preview_file)
        forward_event({"name": "preview-file:add-file", "data": data})
        logger.info(
            "Preview file and related downloaded: %s" % preview_file_id
        )
    except gazu.exception.RouteNotFoundException as e:
        logger.error("Route not found: %s" % e)
        logger.error("Fail to dowonload preview file: %s" % (preview_file_id))


def get_retrieve_thumbnail(model_name):
    def retrieve_thumbnail(data):
        if data.get("sync", False):
            return
        try:
            instance_id = data["preview_file_id"]
            download_thumbnail_from_another_instance(model_name, instance_id)
            forward_event(
                {"name": "%s:set-thumbnail" % model_name, "data": data}
            )
            logger.info(
                "Thumbnail downloaded: %s %s" % (model_name, instance_id)
            )
        except gazu.exception.RouteNotFoundException as e:
            logger.error("Route not found: %s" % e)
            logger.error(
                "Fail to dowonload thunbnail: %s %s"
                % (model_name, instance_id)
            )

    return retrieve_thumbnail


def download_entity_thumbnails_from_storage():
    """
    Download all thumbnail files for non preview entries from object storage
    and store them locally.
    """
    for project in Project.query.all():
        download_entity_thumbnail(project)
    for organisation in Organisation.query.all():
        download_entity_thumbnail(organisation)
    for person in Person.query.all():
        download_entity_thumbnail(person)


def download_preview_files_from_storage():
    """
    Download all thumbnail and original files for preview entries from object
    storage and store them locally.
    """
    for preview_file in PreviewFile.query.all():
        download_preview(preview_file)


def download_entity_thumbnail(entity):
    """
    Download thumbnail file for given entity from object storage and store it
    locally.
    """
    local = LocalBackend(
        "local", {"root": os.path.join(preview_folder, "pictures")}
    )

    file_path = local.path("thumbnails-" + str(entity.id))
    dirname = os.path.dirname(file_path)
    if entity.has_avatar:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(file_path, "wb") as tmp_file:
            for chunk in file_store.open_picture("thumbnails", str(entity.id)):
                tmp_file.write(chunk)


def download_file(file_path, prefix, dl_func, preview_file_id):
    """
    Download preview file for given preview from object storage and store it
    locally.
    """
    dirname = os.path.dirname(file_path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    try:
        with open(file_path, "wb") as tmp_file:
            for chunk in dl_func(prefix, preview_file_id):
                tmp_file.write(chunk)
        print("%s downloaded" % file_path)
    except:
        pass


def download_preview(preview_file):
    """
    Download all files link to preview file entry: orginal file and variants.
    """
    print(
        "download preview %s (%s)" % (preview_file.id, preview_file.extension)
    )
    is_movie = preview_file.extension == "mp4"
    is_picture = preview_file.extension == "png"
    is_file = not is_movie and not is_picture

    preview_file_id = str(preview_file.id)
    file_key = "previews-%s" % preview_file_id
    if is_file:
        file_path = local_file.path(file_key)
        dl_func = file_store.open_picture
    elif is_movie:
        file_path = local_movie.path(file_key)
        dl_func = file_store.open_movie
    else:
        file_path = local_picture.path(file_key)
        dl_func = file_store.open_file

    if is_movie or is_picture:
        for prefix in ["thumbnails", "thumbnails-square", "original"]:
            pic_dl_func = file_store.open_picture
            pic_file_path = local_picture.path(
                "%s-%s" % (prefix, str(preview_file.id))
            )
            download_file(pic_file_path, prefix, pic_dl_func, preview_file_id)

    download_file(file_path, "previews", dl_func, preview_file_id)


def download_files_from_another_instance(project=None):
    """
    Download all files from target instance.
    """
    download_thumbnails_from_another_instance("person")
    download_thumbnails_from_another_instance("organisation")
    download_thumbnails_from_another_instance("project", project=project)
    download_preview_files_from_another_instance(project=project)
    download_attachment_files_from_another_instance(project=project)


def download_thumbnails_from_another_instance(model_name, project=None):
    """
    Download all thumbnails from target instance for given model.
    """
    model = event_name_model_map[model_name]

    if project is None:
        instances = model.query.all()
    else:
        project = gazu.project.get_project_by_name(project)
        instances = model.query.filter_by(id=project.get("id"))

    for instance in instances:
        if instance.has_avatar:
            download_thumbnail_from_another_instance(model_name, instance.id)


def download_thumbnail_from_another_instance(model_name, model_id):
    """
    Download into the local storage the thumbnail for a given model instance.
    """
    from zou.app import app

    with app.app_context():
        file_path = "/tmp/thumbnails-%s.png" % str(model_id)
        path = "/pictures/thumbnails/%ss/%s.png" % (model_name, model_id)
        try:
            gazu.client.download(path, file_path)
            file_store.add_picture("thumbnails", model_id, file_path)
            os.remove(file_path)
            print("%s downloaded" % file_path)
        except Exception as e:
            print(e)
            print("%s download failed" % file_path)
        return path


def download_preview_files_from_another_instance(project=None):
    """
    Download all preview files and related (thumbnails and low def included).
    """
    if project:
        project_dict = gazu.project.get_project_by_name(project)
        preview_files = (
            PreviewFile.query.join(Task)
            .filter(Task.project_id == project_dict["id"])
            .all()
        )
    else:
        preview_files = PreviewFile.query.all()

    for preview_file in preview_files:
        download_preview_from_another_instance(preview_file)


def download_preview_from_another_instance(preview_file):
    """
    Download all files link to preview file entry: orginal file and variants.
    """

    from zou.app import app

    print(
        "download preview %s (%s)" % (preview_file.id, preview_file.extension)
    )
    is_movie = preview_file.extension == "mp4"
    is_picture = preview_file.extension == "png"
    is_file = not is_movie and not is_picture

    preview_file_id = str(preview_file.id)
    with app.app_context():
        if is_movie or is_picture:
            for prefix in [
                "thumbnails",
                "thumbnails-square",
                "original",
                "previews",
            ]:
                if not file_store.exists_picture(prefix, preview_file_id):
                    download_file_from_another_instance(
                        file_store.add_picture,
                        prefix,
                        preview_file_id,
                        "png",
                    )

        if is_movie:
            for prefix in ["low", "previews"]:
                if not file_store.exists_movie(prefix, preview_file_id):
                    download_file_from_another_instance(
                        file_store.add_movie,
                        prefix,
                        preview_file_id,
                        preview_file.extension,
                    )

        elif is_file:
            if not file_store.exists_file("previews", preview_file_id):
                download_file_from_another_instance(
                    file_store.add_file,
                    "previews",
                    preview_file_id,
                    preview_file.extension,
                )


def download_file_from_another_instance(
    save_func, prefix, preview_file_id, extension
):
    """
    Download preview file for given preview from object storage and store it
    locally.
    """
    if prefix == "previews" and extension == "mp4":
        path = "/movies/originals/preview-files/%s.mp4" % preview_file_id
    elif prefix == "low":
        path = "/movies/low/preview-files/%s.mp4" % preview_file_id
    else:
        path_prefix = prefix
        if prefix == "original":
            path_prefix = prefix + "s"
        path = "/pictures/%s/preview-files/%s.%s" % (
            path_prefix,
            preview_file_id,
            extension,
        )
    try:
        file_path = "/tmp/%s.%s" % (preview_file_id, extension)
        response = gazu.client.download(path, file_path)
        if response.status_code == 404:
            print("not found", preview_file_id)
        if response.status_code == 500:
            print("error while downloading", preview_file_id)
        else:
            save_func(prefix, preview_file_id, file_path)
        os.remove(file_path)
        print("%s (%s) downloaded" % (file_path, prefix))
    except Exception as e:
        print(e)
        print("%s download failed" % file_path)


def download_attachment_files_from_another_instance(project=None):
    from zou.app import app

    if project:
        project_dict = gazu.project.get_project_by_name(project)
        attachment_files = (
            AttachmentFile.query.join(Comment)
            .join(Task, Comment.object_id == Task.id)
            .filter(Task.project_id == project_dict["id"])
            .all()
        )
    else:
        attachment_files = AttachmentFile.query.all()
    for attachment_file in attachment_files:
        with app.app_context():
            download_attachment_file_from_another_instance(
                attachment_file.present()
            )


def download_attachment_file_from_another_instance(attachment_file):
    attachment_file_id = attachment_file["id"]
    extension = attachment_file["extension"]
    path = "/data/attachment-files/%s/file/%s" % (
        attachment_file_id,
        attachment_file["name"],
    )
    try:
        file_path = "/tmp/%s.%s" % (attachment_file_id, extension)
        gazu.client.download(path, file_path)
        file_store.add_file("attachments", attachment_file_id, file_path)
        os.remove(file_path)
        print("%s (%s) downloaded" % (file_path, "attachment"))
    except Exception as e:
        print(e)
        print("%s download failed" % file_path)
