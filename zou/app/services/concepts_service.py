from sqlalchemy import cast, Text
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import selectinload

from zou.app.utils import (
    cache,
    events,
    fields,
    query as query_utils,
)

from zou.app import db
from zou.app.models.entity import (
    Entity,
    EntityLink,
    EntityVersion,
    EntityConceptLink,
)
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task

from zou.app.services import (
    base_service,
    deletion_service,
    entities_service,
    notifications_service,
    user_service,
)
from zou.app.exceptions import (
    ConceptFolderNotFoundException,
    ConceptNotFoundException,
    WrongIdFormatException,
    WrongParameterException,
    EntityNotFoundException,
)

CONCEPTS_AND_TASKS_TASK_FIELDS = [
    "id",
    "duration",
    "due_date",
    "end_date",
    "entity_id",
    "estimation",
    "last_comment_date",
    "nb_assets_ready",
    "priority",
    "real_start_date",
    "retake_count",
    "start_date",
    "task_status_id",
    "task_type_id",
    "data",
]


def clear_concept_cache(concept_id):
    """
    Drop every memoized serialization of given concept.
    """
    cache.cache.delete_memoized(get_concept, concept_id)
    cache.cache.delete_memoized(get_concept, concept_id, True)
    cache.cache.delete_memoized(get_full_concept, concept_id)
    entities_service.clear_entity_cache(concept_id)


@cache.memoize_function(1200)
def get_concept_type():
    """
    Return the Concept entity type.
    """
    return entities_service.get_temporal_entity_type_by_name("Concept")


def get_concept_raw(concept_id):
    """
    Return given concept as an active record.
    """
    return base_service.get_typed_instance(
        Entity, concept_id, get_concept_type()["id"], ConceptNotFoundException
    )


@cache.memoize_function(120)
def get_concept(concept_id, relations=False):
    """
    Return given concept as a dictionary.
    """
    return get_concept_raw(concept_id).serialize(
        obj_type="Concept", relations=relations
    )


@cache.memoize_function_single_flight(120)
def get_full_concept(concept_id):
    """
    Return given concept as a dictionary with extra data like project.
    """
    concepts = get_concepts_and_tasks({"id": concept_id})
    if len(concepts) == 0:
        raise ConceptNotFoundException
    concept = concepts[0]
    concept.update(get_concept(concept_id, relations=True))
    return concept


def remove_concept(concept_id, force=False):
    """
    Remove given concept from database. If it has tasks linked to it, it marks
    the concept as canceled. Deletion can be forced.
    """
    concept = get_concept_raw(concept_id)
    is_tasks_related = Task.query.filter_by(entity_id=concept_id).count() > 0

    if is_tasks_related and not force:
        concept.update({"canceled": True})
        clear_concept_cache(concept_id)
        events.emit(
            "concept:update",
            {"concept_id": concept_id},
            project_id=str(concept.project_id),
        )
    else:
        deletion_service.remove_tasks_for_entity(concept_id)

        EntityVersion.delete_all_by(entity_id=concept_id)
        Subscription.delete_all_by(entity_id=concept_id)
        EntityLink.delete_all_by(entity_in_id=concept_id)
        EntityLink.delete_all_by(entity_out_id=concept_id)
        EntityConceptLink.delete_all_by(entity_in_id=concept_id)
        EntityConceptLink.delete_all_by(entity_out_id=concept_id)

        concept.delete()
        events.emit(
            "concept:delete",
            {"concept_id": concept_id},
            project_id=str(concept.project_id),
        )
        clear_concept_cache(concept_id)

    return concept.serialize(obj_type="Concept")


def get_concepts(criterions=None):
    """
    Get all concepts for given criterions.
    """
    if criterions is None:
        criterions = {}
    concept_type = get_concept_type()
    criterions["entity_type_id"] = concept_type["id"]
    is_only_assignation = "assigned_to" in criterions
    if is_only_assignation:
        del criterions["assigned_to"]

    query = Entity.query.options(selectinload(Entity.entity_concept_links))
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    query = (
        query.join(Project, Project.id == Entity.project_id)
        .add_columns(Project.name)
        .order_by(Entity.name)
    )

    if is_only_assignation:
        query = query.outerjoin(Task, Task.entity_id == Entity.id)
        query = query.filter(user_service.build_assignee_filter())

    try:
        data = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException

    concepts = []
    for concept_model, project_name in data:
        concept = concept_model.serialize(obj_type="Concept")
        concept["project_name"] = project_name
        concepts.append(concept)

    return concepts


def get_concepts_and_tasks(criterions=None):
    """
    Get all concepts for given criterions with related tasks for each
    concept, as a list of dicts. Flat narrow queries through
    entities_service.fetch_entity_task_map instead of a row-multiplying
    join; response shape unchanged.
    """
    if criterions is None:
        criterions = {}
    concept_type = get_concept_type()
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), concept_type["id"]
    )

    assigned_to = "assigned_to" in criterions
    if assigned_to:
        del criterions["assigned_to"]

    def apply_filters(query):
        query = query.filter(Entity.entity_type_id == concept_type["id"])
        if "id" in criterions:
            query = query.filter(Entity.id == criterions["id"])
        if "project_id" in criterions:
            query = query.filter(Entity.project_id == criterions["project_id"])
        if assigned_to:
            has_assigned_task = (
                db.session.query(Task.id)
                .filter(Task.entity_id == Entity.id)
                .filter(user_service.build_assignee_filter())
                .exists()
            )
            query = query.filter(has_assigned_task)
        return query

    # The variants of an uploaded picture are built by a background job:
    # the status tells a concept whose picture is not stored yet.
    concept_rows = (
        apply_filters(
            Entity.query.join(
                Project, Project.id == Entity.project_id
            ).outerjoin(PreviewFile, PreviewFile.id == Entity.preview_file_id)
        )
        .with_entities(
            cast(Entity.id, Text).label("id"),
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.canceled,
            cast(Entity.entity_type_id, Text).label("entity_type_id"),
            cast(Entity.parent_id, Text).label("parent_id"),
            cast(Entity.preview_file_id, Text).label("preview_file_id"),
            PreviewFile.status.label("preview_file_status"),
            cast(Entity.source_id, Text).label("source_id"),
            Entity.nb_frames,
            Entity.nb_entities_out,
            Entity.is_casting_standby,
            cast(Entity.created_by, Text).label("created_by"),
            Entity.created_at,
            Entity.updated_at,
            cast(Entity.project_id, Text).label("project_id"),
            Project.name.label("project_name"),
        )
        .all()
    )

    tasks_by_entity, build_task = entities_service.fetch_entity_task_map(
        apply_filters,
        subscription_map,
        CONCEPTS_AND_TASKS_TASK_FIELDS,
        assigned_to=assigned_to,
    )

    concept_links = apply_filters(
        db.session.query(EntityConceptLink).join(
            Entity, EntityConceptLink.entity_in_id == Entity.id
        )
    ).with_entities(
        cast(EntityConceptLink.entity_in_id, Text),
        cast(EntityConceptLink.entity_out_id, Text),
    )
    links_by_concept = {}
    for entity_in_id, entity_out_id in concept_links.all():
        links_by_concept.setdefault(entity_in_id, []).append(entity_out_id)

    concepts = []
    for row in concept_rows:
        data = fields.serialize_value(row.data or {})
        concepts.append(
            {
                "canceled": row.canceled,
                "data": data,
                "description": row.description,
                "entity_type_id": row.entity_type_id,
                "fps": data.get("fps", None),
                "frame_in": data.get("frame_in", None),
                "frame_out": data.get("frame_out", None),
                "id": row.id,
                "name": row.name,
                "nb_frames": row.nb_frames,
                "parent_id": row.parent_id,
                "preview_file_id": row.preview_file_id,
                "preview_file_status": fields.serialize_value(
                    row.preview_file_status
                ),
                "project_id": row.project_id,
                "project_name": row.project_name,
                "source_id": row.source_id,
                "nb_entities_out": row.nb_entities_out,
                "is_casting_standby": row.is_casting_standby,
                "tasks": [
                    build_task(task_row)
                    for task_row in tasks_by_entity.get(row.id, ())
                ],
                "entity_concept_links": links_by_concept.get(row.id, []),
                "type": "Concept",
                "updated_at": fields.serialize_datetime(row.updated_at),
                "created_at": fields.serialize_datetime(row.created_at),
                "created_by": row.created_by,
            }
        )
    return concepts


def get_concepts_for_project(project_id, only_assigned=False):
    """
    Retrieve all concepts related to given project.
    """
    return entities_service.get_entities_for_project(
        project_id,
        get_concept_type()["id"],
        "Concept",
        only_assigned=only_assigned,
    )


def create_concept(
    project_id,
    name,
    data=None,
    description=None,
    entity_concept_links=None,
    created_by=None,
    parent_id=None,
):
    """
    Create concept for given project, in given concept folder when one is
    named.
    """
    if data is None:
        data = {}
    if entity_concept_links is None:
        entity_concept_links = []
    concept_type = get_concept_type()
    if parent_id is not None:
        get_project_concept_folder_raw(project_id, parent_id)

    concept = Entity.get_by(
        entity_type_id=concept_type["id"],
        project_id=project_id,
        name=name,
    )

    if concept is None:
        try:
            entity_concept_links = [
                entity_concept_link
                for entity_concept_link_id in entity_concept_links
                if (entity_concept_link := Entity.get(entity_concept_link_id))
                is not None
            ]
        except StatementError:
            raise EntityNotFoundException()
        concept = Entity.create(
            entity_type_id=concept_type["id"],
            project_id=project_id,
            name=name,
            data=data,
            description=description,
            entity_concept_links=entity_concept_links,
            created_by=created_by,
            parent_id=parent_id,
        )

        events.emit(
            "concept:new",
            {
                "concept_id": concept.id,
            },
            project_id=project_id,
        )

    return concept.serialize(obj_type="Concept")


def is_concept(entity):
    """
    Returns True if given entity has 'Concept' as entity type
    """
    concept_type = get_concept_type()
    return str(entity["entity_type_id"]) == concept_type["id"]


@cache.memoize_function(1200)
def get_concept_folder_type():
    """
    Return the ConceptFolder entity type.
    """
    return entities_service.get_temporal_entity_type_by_name("ConceptFolder")


def is_concept_folder(entity):
    """
    Returns True if given entity has 'ConceptFolder' as entity type
    """
    concept_folder_type = get_concept_folder_type()
    return str(entity["entity_type_id"]) == concept_folder_type["id"]


def get_concept_folder_raw(concept_folder_id):
    """
    Return given concept folder as an active record.
    """
    return base_service.get_typed_instance(
        Entity,
        concept_folder_id,
        get_concept_folder_type()["id"],
        ConceptFolderNotFoundException,
    )


def get_project_concept_folder_raw(project_id, concept_folder_id):
    """
    Return given concept folder as an active record, as long as it belongs
    to given project.
    """
    concept_folder = get_concept_folder_raw(concept_folder_id)
    if str(concept_folder.project_id) != str(project_id):
        raise ConceptFolderNotFoundException()
    return concept_folder


def get_concept_folder(concept_folder_id):
    """
    Return given concept folder as a dictionary.
    """
    return get_concept_folder_raw(concept_folder_id).serialize(
        obj_type="ConceptFolder"
    )


def get_concept_folders_for_project(project_id):
    """
    Retrieve all concept folders of given project, sorted by name.
    """
    return entities_service.get_entities_for_project(
        project_id, get_concept_folder_type()["id"], "ConceptFolder"
    )


def find_concept_folder_raw(project_id, name):
    """
    Return the concept folder of given project carrying given name as an
    active record, or None.
    """
    return Entity.get_by(
        entity_type_id=get_concept_folder_type()["id"],
        project_id=project_id,
        name=name,
    )


def create_concept_folder(project_id, name, created_by=None):
    """
    Create a concept folder for given project. A folder already carrying
    this name is returned as is.
    """
    concept_folder = find_concept_folder_raw(project_id, name)
    if concept_folder is None:
        concept_folder = Entity.create(
            entity_type_id=get_concept_folder_type()["id"],
            project_id=project_id,
            name=name,
            created_by=created_by,
        )
        events.emit(
            "concept-folder:new",
            {"concept_folder_id": str(concept_folder.id)},
            project_id=str(project_id),
        )
    return concept_folder.serialize(obj_type="ConceptFolder")


def update_concept_folder(concept_folder_id, name):
    """
    Rename given concept folder. Two folders of a project cannot share a
    name.
    """
    concept_folder = get_concept_folder_raw(concept_folder_id)
    namesake = find_concept_folder_raw(concept_folder.project_id, name)
    if namesake is not None and namesake.id != concept_folder.id:
        raise WrongParameterException(
            "A concept folder with this name already exists."
        )
    concept_folder.update({"name": name})
    entities_service.clear_entity_cache(concept_folder_id)
    events.emit(
        "concept-folder:update",
        {"concept_folder_id": str(concept_folder.id)},
        project_id=str(concept_folder.project_id),
    )
    return concept_folder.serialize(obj_type="ConceptFolder")


def remove_concept_folder(concept_folder_id):
    """
    Remove given concept folder from database. Its concepts are kept: they
    go back to the root of the project.
    """
    concept_folder = get_concept_folder_raw(concept_folder_id)
    project_id = str(concept_folder.project_id)
    concept_ids = [
        str(concept.id)
        for concept in Entity.get_all_by(parent_id=concept_folder.id)
    ]
    move_concepts(project_id, concept_ids, None)
    result = concept_folder.serialize(obj_type="ConceptFolder")
    concept_folder.delete()
    entities_service.clear_entity_cache(concept_folder_id)
    events.emit(
        "concept-folder:delete",
        {"concept_folder_id": str(concept_folder_id)},
        project_id=project_id,
    )
    return result


def move_concepts(project_id, concept_ids, concept_folder_id=None):
    """
    Move given concepts to given concept folder, or back to the root of the
    project when no folder is named. Ids that are not concepts of the
    project are skipped. Returns the ids of the concepts that were moved.
    """
    if concept_folder_id is not None:
        get_project_concept_folder_raw(project_id, concept_folder_id)
    if len(concept_ids) == 0:
        return []
    try:
        concepts = (
            Entity.query.filter(Entity.id.in_(concept_ids))
            .filter(Entity.project_id == project_id)
            .filter(Entity.entity_type_id == get_concept_type()["id"])
            .all()
        )
    except StatementError:
        raise WrongIdFormatException()

    for concept in concepts:
        concept.update_no_commit({"parent_id": concept_folder_id})
    Entity.commit()

    moved_ids = [str(concept.id) for concept in concepts]
    for concept_id in moved_ids:
        clear_concept_cache(concept_id)
        events.emit(
            "concept:update",
            {"concept_id": concept_id},
            project_id=str(project_id),
        )
    return moved_ids
