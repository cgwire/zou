import logging
from operator import itemgetter

from sqlalchemy import or_
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import defer, joinedload

from zou.app.exceptions import (
    PlaylistLockTimeoutException,
    PlaylistNotFoundException,
)
from zou.app.models.playlist import Playlist
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    assets_service,
    base_service,
    edits_service,
    entities_service,
    entity_types_service,
    projects_service,
    shots_service,
    tasks_service,
)
from zou.app.stores.redis_lock import with_playlist_lock
from zou.app.utils import events, fields, query as query_utils

logger = logging.getLogger(__name__)

# Page size for the playlist list endpoints.
PLAYLISTS_PAGE_SIZE = 20

# Allowlist of the accepted Playlist.for_entity values. For historical
# reasons, the column is a permissive String(10). The consumers (gazu
# Literal, kitsu UI branches, docs) only use the values of this set.
# Validate at the CRUD boundary, so that no other value goes into storage.
VALID_FOR_ENTITY_VALUES = ("shot", "asset", "sequence", "edit", "episode")

# The preview_file_id of the first entry for the list rows (PostgreSQL
# jsonb path). With defer(Playlist.shots), it prevents the load of the
# full `shots` column.
_FIRST_SHOT_PREVIEW_FILE_ID_SQL = Playlist.shots[0][
    "preview_file_id"
].astext.label("first_preview_file_id")

# Sentinel: build_playlist_dict() must read the shots on the model
# (tests / legacy).
_FIRST_PREVIEW_FILE_ID_FROM_QUERY_UNSET = object()

# Scalar attributes for the playlist list dict. They prevent the
# serialization of the shots JSON, which is heavy.
_PLAYLIST_LIST_ATTRS = (
    "id",
    "name",
    "project_id",
    "episode_id",
    "task_type_id",
    "for_client",
    "for_entity",
    "is_for_all",
    "created_at",
    "updated_at",
    "created_by",
)


def _apply_playlist_pagination(query, page, sort_by, model=Playlist):
    """
    Apply the sort to the query, normalize the page, and apply the limit
    and the offset to the query.
    """
    query = query_utils.apply_sort_by(model, query, sort_by)
    if page < 1:
        page = 1
    offset = (page - 1) * PLAYLISTS_PAGE_SIZE
    return query.limit(PLAYLISTS_PAGE_SIZE).offset(offset)


def all_playlists_for_project(
    project_id,
    for_client=False,
    page=1,
    sort_by="updated_at",
    task_type_id=None,
):
    """
    Return one page of the playlists of the given project, as the light
    dicts of build_playlist_dict.
    """
    result = []
    query = Playlist.query.filter(Playlist.project_id == project_id)
    if for_client:
        query = query.filter(Playlist.for_client)

    if task_type_id is not None and len(task_type_id) > 0:
        query = query.filter(Playlist.task_type_id == task_type_id)

    query = _apply_playlist_pagination(query, page, sort_by)
    query = query.options(defer(Playlist.shots)).add_columns(
        _FIRST_SHOT_PREVIEW_FILE_ID_SQL
    )
    for playlist, first_preview_file_id in query.all():
        result.append(
            build_playlist_dict(
                playlist, first_preview_file_id=first_preview_file_id
            )
        )
    return result


def all_playlists_for_episode(
    project_id,
    episode_id,
    for_client=False,
    page=1,
    sort_by="updated_at",
    task_type_id=None,
    for_entity=None,
):
    """
    Return one page of the playlists of the given episode, as the light
    dicts of build_playlist_dict. The "main" pseudo-episode lists the
    playlists without an episode that are not for all episodes. The "all"
    pseudo-episode lists the playlists of the full production, for all the
    entity types. If `for_entity` is given, it limits them to one type
    (Kitsu shows them as All assets and All shots).
    """
    result = []
    query = Playlist.query
    if for_client:
        query = query.filter(Playlist.for_client)

    if for_entity:
        query = query.filter(Playlist.for_entity == for_entity)

    if task_type_id is not None and len(task_type_id) > 0:
        query = query.filter(Playlist.task_type_id == task_type_id)

    if episode_id == "main":
        query = (
            query.filter(Playlist.episode_id == None)
            .filter(Playlist.project_id == project_id)
            .filter(
                or_(
                    Playlist.is_for_all.is_(None),
                    Playlist.is_for_all == False,
                )
            )
        )
    elif episode_id == "all":
        query = (
            query.filter(Playlist.episode_id == None)
            .filter(Playlist.project_id == project_id)
            .filter(Playlist.is_for_all == True)
        )
    else:
        query = query.filter(Playlist.episode_id == episode_id).filter(
            Playlist.project_id == project_id
        )

    query = _apply_playlist_pagination(query, page, sort_by)
    query = query.options(defer(Playlist.shots)).add_columns(
        _FIRST_SHOT_PREVIEW_FILE_ID_SQL
    )
    for playlist, first_preview_file_id in query.all():
        result.append(
            build_playlist_dict(
                playlist, first_preview_file_id=first_preview_file_id
            )
        )
    return result


def build_playlist_dict(
    playlist, first_preview_file_id=_FIRST_PREVIEW_FILE_ID_FROM_QUERY_UNSET
):
    """
    Build a dict with a simple version of the playlist. It has only the
    data that the list of playlists shows. The function does not change the
    playlist model. It uses only scalar attributes, so it does not
    serialize the shots JSON column, which can be large.
    """
    out = {"type": "Playlist"}
    for attr in _PLAYLIST_LIST_ATTRS:
        if hasattr(playlist, attr):
            out[attr] = fields.serialize_value(getattr(playlist, attr))
    if playlist.for_entity is None:
        out["for_entity"] = "shot"
    if first_preview_file_id is not _FIRST_PREVIEW_FILE_ID_FROM_QUERY_UNSET:
        if first_preview_file_id:
            out["first_preview_file_id"] = fields.serialize_value(
                first_preview_file_id
            )
    else:
        first_shot_preview_file_id = get_first_shot_preview_file_id(playlist)
        if first_shot_preview_file_id is not None:
            out["first_preview_file_id"] = first_shot_preview_file_id
    return out


def get_first_shot_preview_file_id(playlist):
    """
    Return the preview_file_id of the first shot, or None.
    """
    if not playlist.shots or not isinstance(playlist.shots, list):
        return None
    first = playlist.shots[0]
    return first.get("preview_file_id") if isinstance(first, dict) else None


def get_playlist_with_preview_file_revisions(
    playlist_id, with_annotations=True
):
    """
    Return the given playlist. The shot list has, for each shot, all the
    available previews.

    If with_annotations is False, the response does not include the
    annotation blobs. They are the heaviest part of a playlist, and the web
    client loads them when it needs them. Callers that cannot load them
    later (for example the shared guest player) keep the default. They get
    the annotations in the response.
    """
    # Load build_jobs eagerly to prevent N+1 queries when the function
    # builds the build_jobs list.
    playlist = (
        Playlist.query.options(joinedload(Playlist.build_jobs))
        .filter(Playlist.id == playlist_id)
        .first()
    )
    if playlist is None:
        raise PlaylistNotFoundException()
    playlist_dict = playlist.serialize()
    playlist_dict = _add_build_job_infos_to_playlist_dict(
        playlist, playlist_dict
    )

    if playlist_dict["shots"] is None:
        playlist_dict["shots"] = []
    playlist_dict, preview_file_map = set_preview_files_for_entities(
        playlist_dict, with_annotations=with_annotations
    )

    for shot in playlist_dict["shots"]:
        try:
            preview_file = preview_file_map.get(shot["preview_file_id"], None)
            if preview_file is not None:
                shot["preview_file_id"] = preview_file["id"]
                shot["preview_file_original_name"] = preview_file[
                    "original_name"
                ]
                shot["preview_file_extension"] = preview_file["extension"]
                shot["preview_file_revision"] = preview_file["revision"]
                shot["preview_file_width"] = preview_file["width"]
                shot["preview_file_height"] = preview_file["height"]
                shot["preview_file_duration"] = preview_file["duration"]
                shot["preview_file_status"] = preview_file["status"]
                shot["preview_file_task_id"] = preview_file["task_id"]
                shot["preview_file_previews"] = preview_file.get(
                    "previews", []
                )
                if with_annotations:
                    shot["preview_file_annotations"] = preview_file.get(
                        "annotations"
                    )
            else:
                del shot["preview_file_id"]
        except Exception as e:
            logger.warning(
                "Failed to enrich shot with preview file: shot_id=%s, error=%s",
                shot.get("id"),
                e,
            )
    return playlist_dict


def _add_build_job_infos_to_playlist_dict(playlist, playlist_dict):
    """
    Add the build jobs of the playlist to a playlist dict, newest first.
    Because of this, the client knows if a movie is available or if its
    build is not complete.
    """
    playlist_dict["build_jobs"] = []
    for build_job in reversed(playlist.build_jobs):
        playlist_dict["build_jobs"].append(build_job.present())
    return playlist_dict


def set_preview_files_for_entities(playlist_dict, with_annotations=True):
    """
    Get all the preview files of the entities of the given playlist. Add to
    each entity a dict with task type IDs as keys and preview lists as
    values. If the entity has no preview, the list is empty. Return the
    playlist dict and a map of the preview files by ID.

    The annotation blobs are included only if with_annotations is True. The
    web client does not include them, to keep the payload small. It loads
    them when it needs them.
    """
    entity_ids = []
    for entity in playlist_dict["shots"]:
        entity_id = (
            entity.get("id")
            or entity.get("shot_id")
            or entity.get("entity_id")
        )
        if entity_id:
            entity_ids.append(entity_id)
            entity.setdefault("id", entity_id)
    previews = {}
    preview_file_map = {}

    # Select scalar columns, not full PreviewFile ORM objects. A playlist can
    # have thousands of revisions, and the creation of so many ORM instances
    # took most of the query time. Also skip the heavy JSONB blobs `data`
    # (never used) and `annotations` (only if the caller asks for them). This
    # is the same as in get_entity_previews_by_task_type().
    preview_columns = [
        PreviewFile.id,
        PreviewFile.revision,
        PreviewFile.original_name,
        PreviewFile.extension,
        PreviewFile.width,
        PreviewFile.height,
        PreviewFile.duration,
        PreviewFile.status,
        PreviewFile.created_at,
        PreviewFile.task_id,
        Task.task_type_id,
        Task.entity_id,
    ]
    if with_annotations:
        preview_columns.append(PreviewFile.annotations)

    preview_rows = (
        PreviewFile.query.with_entities(*preview_columns)
        .join(Task)
        .join(TaskType)
        .filter(Task.entity_id.in_(entity_ids))
        .order_by(TaskType.priority.desc())
        .order_by(TaskType.name)
        .order_by(PreviewFile.revision.desc())
        .order_by(PreviewFile.position)
        .order_by(PreviewFile.created_at)
        .all()
    )

    for row in preview_rows:
        entity_id = str(row.entity_id)
        task_type_id = str(row.task_type_id)
        if entity_id not in previews:
            previews[entity_id] = {}

        if task_type_id not in previews[entity_id]:
            previews[entity_id][task_type_id] = []

        preview_file_id = str(row.id)

        light_preview_file = {
            "id": preview_file_id,
            "revision": row.revision,
            "original_name": row.original_name,
            "extension": row.extension,
            "width": row.width,
            "height": row.height,
            "duration": float(row.duration or 0),
            "status": fields.serialize_value(row.status),
            "created_at": fields.serialize_value(row.created_at),
            "task_id": str(row.task_id),
        }  # Do not add more fields: the responses must stay small
        if with_annotations:
            light_preview_file["annotations"] = row.annotations
        previews[entity_id][task_type_id].append(light_preview_file)
        preview_file_map[preview_file_id] = light_preview_file

    for entity_id in previews.keys():
        for task_type_id in previews[entity_id].keys():
            previews[entity_id][task_type_id] = mix_preview_file_revisions(
                previews[entity_id][task_type_id]
            )

    for entity in playlist_dict["shots"]:
        entity_id = entity.get("id")
        if entity_id and str(entity_id) in previews:
            entity["preview_files"] = previews[str(entity_id)]
        else:
            entity["preview_files"] = []

    # playlist_dict is already JSON-safe here:
    # - the top-level fields and shots came through playlist.serialize().
    # - build_jobs came through BuildJob.present().
    # - the function builds each preview file dict with serialized values.
    # A second serialize_value() pass on the full (large) structure only
    # walks and copies it again, for no result.
    return (playlist_dict, preview_file_map)


def get_entity_previews_by_task_type(entity_id):
    """
    Return all the preview files of the given entity, as a dict. The keys
    are task type IDs. The values are preview lists grouped by revision.
    """
    previews = {}
    query = (
        Task.query.filter_by(entity_id=entity_id)
        .add_columns(
            PreviewFile.id,
            PreviewFile.revision,
            PreviewFile.position,
            PreviewFile.original_name,
            PreviewFile.extension,
            PreviewFile.width,
            PreviewFile.height,
            PreviewFile.duration,
            PreviewFile.status,
            PreviewFile.annotations,
            PreviewFile.created_at,
            PreviewFile.task_id,
            PreviewFile.data,
        )
        .join(PreviewFile, Task.id == PreviewFile.task_id)
        .join(TaskType)
        .order_by(TaskType.priority.desc())
        .order_by(TaskType.name)
        .order_by(PreviewFile.revision.desc())
        .order_by(PreviewFile.created_at)
    )

    task_previews = {}
    for (
        task,
        preview_file_id,
        preview_file_revision,
        preview_file_position,
        preview_file_original_name,
        preview_file_extension,
        preview_file_width,
        preview_file_height,
        preview_file_duration,
        preview_file_status,
        preview_file_annotations,
        preview_file_created_at,
        preview_file_task_id,
        preview_file_data,
    ) in query.all():
        task_id = str(task.id)
        if task_id not in task_previews:
            task_previews[task_id] = []
        data = preview_file_data or {}
        task_previews[task_id].append(
            fields.serialize_dict(
                {
                    "id": preview_file_id,
                    "revision": preview_file_revision,
                    "position": preview_file_position,
                    "original_name": preview_file_original_name,
                    "extension": preview_file_extension,
                    "width": preview_file_width,
                    "height": preview_file_height,
                    "duration": float(preview_file_duration or 0),
                    "status": preview_file_status,
                    "annotations": preview_file_annotations,
                    "created_at": preview_file_created_at,
                    "task_id": task_id,
                    "task_type_id": str(task.task_type_id),
                    "original_width": data.get("original_width"),
                    "original_height": data.get("original_height"),
                    "original_duration": data.get("original_duration"),
                    "original_file_size": data.get("original_file_size"),
                }
            )
        )

    for task_id in task_previews.keys():
        preview_files = task_previews[task_id]
        task_type_id = task_previews[task_id][0]["task_type_id"]

        if len(preview_files) > 0:
            preview_files = mix_preview_file_revisions(preview_files)
            previews[task_type_id] = [
                {
                    "id": preview_file["id"],
                    "revision": preview_file["revision"],
                    "original_name": preview_file["original_name"],
                    "extension": preview_file["extension"],
                    "width": preview_file["width"],
                    "height": preview_file["height"],
                    "duration": preview_file["duration"],
                    "status": preview_file["status"],
                    "annotations": preview_file["annotations"],
                    "previews": preview_file["previews"],
                    "created_at": preview_file["created_at"],
                    "task_id": preview_file["task_id"],
                    "original_width": preview_file.get("original_width"),
                    "original_height": preview_file.get("original_height"),
                    "original_duration": preview_file.get("original_duration"),
                    "original_file_size": preview_file.get(
                        "original_file_size"
                    ),
                }
                for preview_file in preview_files
            ]  # Do not add more fields: the responses must stay small
    return previews


def mix_preview_file_revisions(preview_files):
    """
    Group the preview files that have the same revision in one preview
    file. This preview file contains the other preview files.
    """
    revision_map = {}
    result = []
    for preview_file in preview_files:
        revision = preview_file["revision"]
        if revision not in revision_map:
            preview_file["previews"] = []
            revision_map[revision] = preview_file
            result.append(preview_file)
        else:
            parent_preview_file = revision_map[revision]
            parent_preview_file["previews"].append(preview_file)
    return result


def get_playlist_raw(playlist_id):
    """
    Return the given playlist as an active record.
    """
    return base_service.get_instance(
        Playlist, playlist_id, PlaylistNotFoundException
    )


def get_playlist(playlist_id):
    """
    Return the given playlist as a dict.
    """
    return get_playlist_raw(playlist_id).serialize()


def get_project_playlist(project_id, playlist_id):
    """
    Return the id, the project and the client flag of the given playlist,
    if it belongs to the given project. A read check needs only these
    values. The caller loads the shots after this call. The client gives
    the ID together with a project that it can access. If the playlist is
    in another project, or if the ID is not valid, the playlist is not
    found.
    """
    try:
        playlist = (
            Playlist.query.with_entities(Playlist.for_client)
            .filter(
                Playlist.id == playlist_id, Playlist.project_id == project_id
            )
            .first()
        )
    except StatementError:
        raise PlaylistNotFoundException()
    if playlist is None:
        raise PlaylistNotFoundException()
    return {
        "id": str(playlist_id),
        "project_id": str(project_id),
        "for_client": playlist.for_client,
    }


def add_entity_to_playlist(playlist_id, entity_id, preview_file_id=None):
    """
    Append one entity to the list of playlist shots. The rules are the same
    as in add_entities_to_playlist, which this function calls. A playlist
    entry is the couple (entity, preview). Because of this, you can add the
    same entity again with a different preview. If a call gives no
    preview, the entry gets the latest preview.
    """
    return add_entities_to_playlist(
        playlist_id,
        [{"entity_id": entity_id, "preview_file_id": preview_file_id}],
    )


def get_latest_preview_file_ids_for_entities(entity_ids, task_type_id=None):
    """
    Return a map of entity ID to the ID of its latest preview file. The
    latest preview file has the highest revision. If two have the same
    revision, created_at decides. If task_type_id is set, use only the
    preview files uploaded for this task type.
    """
    if not entity_ids:
        return {}
    query = (
        PreviewFile.query.join(Task, PreviewFile.task_id == Task.id)
        .filter(Task.entity_id.in_(entity_ids))
        .with_entities(PreviewFile.id, Task.entity_id)
        .order_by(
            Task.entity_id,
            PreviewFile.revision.desc(),
            PreviewFile.created_at.desc(),
        )
    )
    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)
    latest = {}
    for preview_file_id, entity_id in query.all():
        entity_id_str = str(entity_id)
        if entity_id_str not in latest:
            latest[entity_id_str] = str(preview_file_id)
    return latest


def add_entities_to_playlist(playlist_id, entities):
    """
    Append many (entity, preview) couples to the list of playlist shots, in
    one atomic database write. A playlist entry is the couple (entity_id,
    preview_file_id). The same entity can occur many times with different
    previews, so the function skips only exact duplicate couples.

    If a couple has no preview_file_id, use the latest preview of the
    entity. This is the highest revision. If the playlist has a task type,
    use only the previews of this task type. Emit a playlist:add_entity
    event for each added couple. If the function cannot get the playlist
    lock, raise PlaylistLockTimeoutException.
    """
    couples = [
        (
            str(entity["entity_id"]),
            (
                str(entity["preview_file_id"])
                if entity.get("preview_file_id") is not None
                else None
            ),
        )
        for entity in entities
    ]
    with with_playlist_lock(
        playlist_id, timeout=30, wait_timeout=35
    ) as acquired:
        if not acquired:
            raise PlaylistLockTimeoutException(
                "Could not acquire the lock of this playlist"
            )
        playlist = get_playlist_raw(playlist_id)
        task_type_id = (
            str(playlist.task_type_id)
            if playlist.task_type_id is not None
            else None
        )
        entity_ids_to_resolve = [
            entity_id
            for entity_id, preview_file_id in couples
            if preview_file_id is None
        ]
        resolved_preview_ids = (
            get_latest_preview_file_ids_for_entities(
                entity_ids_to_resolve, task_type_id
            )
            if entity_ids_to_resolve
            else {}
        )
        shots = list(playlist.shots or [])
        present_couples = {
            (shot.get("entity_id"), shot.get("preview_file_id"))
            for shot in shots
        }
        added_shots = []
        for entity_id, preview_file_id in couples:
            if preview_file_id is None:
                preview_file_id = resolved_preview_ids.get(entity_id)
            couple = (entity_id, preview_file_id)
            if couple not in present_couples:
                shot = {"entity_id": entity_id}
                if preview_file_id is not None:
                    shot["preview_file_id"] = preview_file_id
                shots.append(shot)
                present_couples.add(couple)
                added_shots.append(shot)
        if added_shots:
            playlist.update({"shots": shots})
        playlist_dict = playlist.serialize()

    for shot in added_shots:
        events.emit(
            "playlist:add_entity",
            {
                "playlist_id": playlist_dict["id"],
                "entity_id": shot["entity_id"],
                "preview_file_id": shot.get("preview_file_id"),
            },
            project_id=playlist_dict["project_id"],
        )
    return playlist_dict


def playlist_previews(shots, only_movies=False):
    """
    Return the preview ID and extension for all the given shots. Use one
    batch query, not N queries (this prevents N+1 queries).
    """
    preview_file_ids = []
    for entity in shots:
        if not isinstance(entity, dict):
            continue
        pf_id = entity.get("preview_file_id")
        if pf_id is not None and len(str(pf_id).strip()) > 0:
            preview_file_ids.append(str(pf_id))
    if not preview_file_ids:
        return []

    preview_rows = (
        PreviewFile.query.with_entities(PreviewFile.id, PreviewFile.extension)
        .filter(PreviewFile.id.in_(preview_file_ids))
        .all()
    )
    id_to_preview = {
        str(pf_id): {"id": str(pf_id), "extension": ext}
        for pf_id, ext in preview_rows
    }

    # Keep the order of the shots and apply the only_movies filter.
    result = []
    for entity in shots:
        if not isinstance(entity, dict):
            continue
        pf_id = entity.get("preview_file_id")
        if not pf_id:
            continue
        preview = id_to_preview.get(str(pf_id))
        if preview is None:
            continue
        if only_movies and preview["extension"] != "mp4":
            continue
        result.append(preview)
    return result


def get_playlists_for_project(project_id, page=0):
    """
    Return the playlists of the given project with their relations. The
    pagination is the same as in query_utils.get_paginated_results.
    """
    query = Playlist.query.filter(Playlist.project_id == project_id)
    return query_utils.get_paginated_results(query, page, relations=True)


def generate_temp_playlist(task_ids, sort=True):
    """
    Make the data structure of a playlist for the given list of tasks. It
    does not save anything. It makes a temporary playlist that shows a
    quick preview of many shots.
    """
    if len(task_ids) == 0:
        return []

    task_id = task_ids[0]
    task = tasks_service.get_task(task_id)
    for_entity = entities_service.get_for_entity_from_task(task)
    task_type_links = projects_service.get_task_type_links(
        task["project_id"], for_entity
    )
    entities = []

    for task_id in task_ids:
        entity = generate_playlisted_entity_from_task(task_id, task_type_links)
        entities.append(entity)
    if not sort:
        return entities
    # Each entry has the full key set (empty if it does not apply).
    # Because of this, one composite key sorts shots by sequence, edits by
    # episode and assets by type. A check of one key at a time selected
    # episode_name for shots, and the sequence order was lost.
    return sorted(
        entities,
        key=itemgetter(
            "episode_name", "sequence_name", "asset_type_name", "name"
        ),
    )


def get_playlist_task_id_for_entity(entity_id):
    """
    Return the task that makes the playlist entry for the given entity:
    the task with the most recent review among the tasks that have a
    preview. If no task of the entity has a preview, return None.
    """
    task = (
        Task.query.filter(Task.entity_id == entity_id)
        .filter(Task.last_preview_file_id.isnot(None))
        .order_by(Task.last_comment_date.desc())
        .first()
    )
    return str(task.id) if task is not None else None


def generate_playlisted_entity_from_task(task_id, task_type_links):
    """
    Make the data structure of a playlist shot for the given task. It does
    not save anything.
    """
    task = tasks_service.get_task(task_id)
    entity = entities_service.get_entity(task["entity_id"])
    if entity_types_service.is_shot(entity):
        playlisted_entity = get_base_shot_for_playlist(entity, task_id)
    elif entity_types_service.is_sequence(entity):
        playlisted_entity = get_base_sequence_for_playlist(entity, task_id)
    elif entity_types_service.is_episode(entity):
        playlisted_entity = get_base_episode_for_playlist(entity, task_id)
    elif entity_types_service.is_edit(entity):
        playlisted_entity = get_base_edit_for_playlist(entity, task_id)
    else:
        playlisted_entity = get_base_asset_for_playlist(entity, task_id)

    task_type_id = task["task_type_id"]
    preview_files = get_entity_previews_by_task_type(entity["id"])

    preview_file = None
    if task_type_id in preview_files and len(preview_files[task_type_id]) > 0:
        preview_file = preview_files[task_type_id][0]

    if preview_file is None and len(preview_files.keys()) > 0:
        available_task_types = [
            link["task_type_id"]
            for link in task_type_links
            if link["task_type_id"] in preview_files
        ]
        if len(available_task_types) > 0:
            task_type_id = available_task_types[0]
            preview_file = preview_files[task_type_id][0]

    if preview_file is not None:
        playlisted_entity.update(
            {
                "preview_file_id": preview_file["id"],
                "preview_file_original_name": preview_file["original_name"],
                "preview_file_extension": preview_file["extension"],
                "preview_file_width": preview_file["width"],
                "preview_file_height": preview_file["height"],
                "preview_file_duration": preview_file["duration"],
                "preview_file_revision": preview_file["revision"],
                "preview_file_status": preview_file["status"],
                "preview_file_annotations": preview_file["annotations"] or [],
                "preview_file_previews": preview_file["previews"],
            }
        )
    playlisted_entity["preview_files"] = preview_files
    return playlisted_entity


def _build_playlisted_entity(entity, task_id, parent_name="", **extra):
    """
    Build a playlist entry with the full key set, for all kinds of entity.
    Because of this, a consumer can read episode_id or sequence_name on all
    entries. It does not have to know which builder made the entry. The
    keys that do not apply stay empty, and the clients read them as
    absent.
    """
    entry = {
        "id": entity["id"],
        "name": entity["name"],
        "preview_file_task_id": task_id,
        "parent_name": parent_name,
        "episode_id": "",
        "episode_name": "",
        "sequence_id": "",
        "sequence_name": "",
        "asset_type_id": "",
        "asset_type_name": "",
    }
    entry.update(extra)
    return entry


def get_base_episode_for_playlist(entity, task_id):
    """
    Build the playlist entry of an episode. An episode has no parent to
    show.
    """
    episode = shots_service.get_episode(entity["id"])
    return _build_playlisted_entity(episode, task_id)


def get_base_sequence_for_playlist(entity, task_id):
    """
    Build the playlist entry of a sequence, with its episode as the parent.
    """
    sequence = shots_service.get_sequence(entity["id"])
    episode = None
    try:
        episode = shots_service.get_episode(sequence["parent_id"])
    except Exception as e:
        logger.debug(
            "No episode for sequence parent_id=%s: %s",
            sequence.get("parent_id"),
            e,
        )
    if episode is None:
        return _build_playlisted_entity(sequence, task_id)
    return _build_playlisted_entity(
        sequence,
        task_id,
        parent_name=episode["name"],
        episode_id=episode["id"],
        episode_name=episode["name"],
    )


def get_base_shot_for_playlist(entity, task_id):
    """
    Build the playlist entry of a shot, with its sequence as the parent.
    """
    shot = shots_service.get_shot(entity["id"])
    sequence = shots_service.get_sequence(shot["parent_id"])
    return _build_playlisted_entity(
        shot,
        task_id,
        parent_name=sequence["name"],
        sequence_id=sequence["id"],
        sequence_name=sequence["name"],
    )


def get_base_edit_for_playlist(entity, task_id):
    """
    Build the playlist entry of an edit, with its episode as the parent.
    """
    edit = edits_service.get_edit(entity["id"])
    episode = None
    try:
        episode = shots_service.get_episode(edit["parent_id"])
    except Exception as e:
        logger.debug(
            f"No episode for edit parent_id={edit.get('parent_id')}: {e}"
        )
    if episode is None:
        return _build_playlisted_entity(edit, task_id)
    return _build_playlisted_entity(
        edit,
        task_id,
        parent_name=episode["name"],
        episode_id=episode["id"],
        episode_name=episode["name"],
    )


def get_base_asset_for_playlist(entity, task_id):
    """
    Build the playlist entry of an asset, with its type as the parent.
    """
    asset = assets_service.get_asset(entity["id"])
    asset_type = entity_types_service.get_asset_type(asset["entity_type_id"])
    return _build_playlisted_entity(
        asset,
        task_id,
        parent_name=asset_type["name"],
        asset_type_id=asset_type["id"],
        asset_type_name=asset_type["name"],
    )
