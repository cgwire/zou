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
from zou.app.models.project import Project
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task

from zou.app.services import (
    deletion_service,
    entities_service,
    notifications_service,
    user_service,
)
from zou.app.services.exception import (
    ConceptNotFoundException,
    WrongIdFormatException,
    EntityNotFoundException,
)


def clear_concept_cache(concept_id):
    cache.cache.delete_memoized(get_concept, concept_id)
    cache.cache.delete_memoized(get_concept, concept_id, True)
    cache.cache.delete_memoized(get_full_concept, concept_id)


@cache.memoize_function(1200)
def get_concept_type():
    return entities_service.get_temporal_entity_type_by_name("Concept")


def get_concept_raw(concept_id):
    """
    Return given concept as an active record.
    """
    concept_type = get_concept_type()
    try:
        concept = Entity.get_by(
            entity_type_id=concept_type["id"], id=concept_id
        )
    except StatementError:
        raise ConceptNotFoundException

    if concept is None:
        raise ConceptNotFoundException

    return concept


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
    if len(concepts) > 0:
        concept = concepts[0]
        concept.update(get_concept(concept_id, relations=True))
        return concept
    else:
        raise ConceptNotFoundException


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
        from zou.app.services import tasks_service

        tasks = Task.query.filter_by(entity_id=concept_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))

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

    deleted_concept = concept.serialize(obj_type="Concept")
    return deleted_concept


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
]


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

    concept_rows = (
        apply_filters(
            Entity.query.join(Project, Project.id == Entity.project_id)
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
    data={},
    description=None,
    entity_concept_links=[],
    created_by=None,
):
    """
    Create concept for given project.
    """
    concept_type = get_concept_type()

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
