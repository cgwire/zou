from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from zou.app import config
from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry
from zou.app.models.build_job import BuildJob
from zou.app.models.comment import Comment
from zou.app.models.desktop_login_log import DesktopLoginLog
from zou.app.models.entity import (
    Entity,
    EntityConceptLink,
    EntityLink,
    EntityVersion,
)
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.milestone import Milestone
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.models.working_file import WorkingFile
from zou.app.utils import events
from zou.app.services import (
    playlist_builds_service,
    playlists_service,
    base_service,
    breakdown_service,
    deletion_service,
    entity_types_service,
    index_service,
    search_filters_service,
    shots_service,
    entities_service,
    assets_service,
    concepts_service,
    edits_service,
)
from zou.app.exceptions import (
    EntityNotFoundException,
    ModelWithRelationsDeletionException,
    PersonInProtectedAccounts,
    ProjectNotFoundException,
)


def remove_playlist_dependents(playlist_dict):
    """
    Delete what hangs off given playlist: its notifications, its build jobs
    (with their movie files) and its share links. The one cascade both the
    service and the CRUD route run, so a dependent added here is gone from
    both.
    """
    playlist_id = playlist_dict["id"]
    notifications = Notification.query.filter_by(playlist_id=playlist_id).all()
    for notification in notifications:
        notification.delete()
    jobs = BuildJob.query.filter_by(playlist_id=playlist_id).all()
    for job in jobs:
        playlist_builds_service.remove_build_job_impl(
            playlist_dict, job.serialize()
        )
    share_links = PlaylistShareLink.query.filter_by(
        playlist_id=playlist_id
    ).all()
    for share_link in share_links:
        share_link.delete()


def remove_playlist(playlist_id):
    """
    Remove given playlist from database (and delete related build jobs).
    """
    playlist = playlists_service.get_playlist_raw(playlist_id)
    playlist_dict = playlist.serialize()
    remove_playlist_dependents(playlist_dict)
    playlist.delete()
    events.emit(
        "playlist:delete",
        {"playlist_id": playlist_dict["id"]},
        project_id=playlist_dict["project_id"],
    )
    return playlist_dict


def remove_entities(project_id, entity_ids, force=False):
    """
    Delete a list of a project's entities, dispatching each to the right
    removal by its type (asset, shot, edit, concept). Without force, entities
    with tasks are canceled on first deletion, then removed for real when
    already canceled; concepts are always removed. With force, every entity is
    removed for real along with its tasks. Absent entities and entities that
    do not belong to the project or are not one of those types are skipped.
    Returns the ids of the entities that were removed.
    """

    shot_type_id = entity_types_service.get_shot_type()["id"]
    edit_type_id = entity_types_service.get_edit_type()["id"]
    concept_type_id = entity_types_service.get_concept_type()["id"]

    to_remove = []
    for entity_id in entity_ids:
        try:
            entity = entities_service.get_entity(entity_id)
        except EntityNotFoundException:
            # Already gone (e.g. deleted by someone else): the deletion is
            # idempotent, skip it like remove_tasks ignores unknown ids.
            continue
        if entity["project_id"] != project_id:
            continue
        entity_type_id = entity["entity_type_id"]
        entity_force = force or entity["canceled"]
        if entity_type_id == shot_type_id:
            remove = remove_shot
        elif entity_type_id == edit_type_id:
            remove = remove_edit
        elif entity_type_id == concept_type_id:
            remove = remove_concept
            entity_force = True
        elif entity_types_service.is_asset_dict(entity):
            remove = remove_asset
        else:
            continue
        to_remove.append((entity_id, remove, entity_force))

    for entity_id, remove, entity_force in to_remove:
        remove(entity_id, force=entity_force)
    return [entity_id for entity_id, _, _ in to_remove]


def remove_episode(episode_id, force=False):
    """
    Remove an episode and all related sequences and shots.
    """

    episode = shots_service.get_episode_raw(episode_id)
    if force:
        for sequence in Entity.get_all_by(parent_id=episode_id):
            remove_sequence(sequence.id, force=True)
        for asset in Entity.get_all_by(source_id=episode_id):
            remove_asset(asset.id, force=True)
        deletion_service.remove_tasks_for_entity(episode_id)
        Playlist.delete_all_by(episode_id=episode_id)
        ScheduleItem.delete_all_by(object_id=episode_id)
        EntityVersion.delete_all_by(entity_id=episode_id)
        Subscription.delete_all_by(entity_id=episode_id)
        EntityLink.delete_all_by(entity_in_id=episode_id)
        EntityLink.delete_all_by(entity_out_id=episode_id)
        EntityConceptLink.delete_all_by(entity_in_id=episode_id)
        EntityConceptLink.delete_all_by(entity_out_id=episode_id)
        deletion_service.remove_output_files_for_entity(episode_id)
    try:
        episode.delete()
        events.emit(
            "episode:delete",
            {"episode_id": episode_id},
            project_id=str(episode.project_id),
        )
    except IntegrityError:
        raise ModelWithRelationsDeletionException(
            "Some data are still linked to this episode."
        )
    shots_service.clear_episode_cache(episode_id)
    return episode.serialize(obj_type="Episode")


def remove_project(project_id):
    """
    Remove a project and everything it owns: previews, tasks, budgets, entity
    links, playlists, entities, metadata, schedule and news.
    """

    preview_files = (
        PreviewFile.query.join(Task)
        .filter(Task.project_id == project_id)
        .all()
    )
    for preview_file in preview_files:
        deletion_service.remove_preview_file(preview_file, force=True)

    for task_id in deletion_service.get_task_ids(project_id=project_id):
        deletion_service.remove_task(task_id, force=True)

    budgets = Budget.get_all_by(project_id=project_id)
    for budget in budgets:
        BudgetEntry.delete_all_by(budget_id=budget.id)
        budget.delete()

    EntityLink.query.filter(
        EntityLink.entity_in_id == Entity.id,
        Entity.project_id == project_id,
    ).delete()
    EntityConceptLink.query.filter(
        EntityConceptLink.entity_in_id == Entity.id,
        Entity.project_id == project_id,
    ).delete()
    EntityConceptLink.query.filter(
        EntityConceptLink.entity_out_id == Entity.id,
        Entity.project_id == project_id,
    ).delete()
    EntityVersion.query.filter(
        EntityVersion.entity_id == Entity.id, Entity.project_id == project_id
    ).delete()
    playlists = Playlist.query.filter_by(project_id=project_id)
    for playlist in playlists:
        remove_playlist(playlist.id)

    ApiEvent.delete_all_by(project_id=project_id)
    deletion_service.remove_output_files_for_project(project_id)
    Entity.delete_all_by(project_id=project_id)

    descriptors = MetadataDescriptor.query.filter_by(project_id=project_id)
    for descriptor in descriptors:
        descriptor.departments = []
        descriptor.save()
    MetadataDescriptor.delete_all_by(project_id=project_id)
    Milestone.delete_all_by(project_id=project_id)
    ScheduleItem.delete_all_by(project_id=project_id)
    deletion_service.remove_production_schedule_versions_for_project(
        project_id
    )
    search_filters_service.remove_search_filters(project_id=project_id)
    News.query.filter(
        News.task_id == Task.id, Task.project_id == project_id
    ).delete()
    project = base_service.get_instance(
        Project, project_id, ProjectNotFoundException
    )
    project.delete()
    events.emit("project:delete", {"project_id": project.id})
    return project_id


def remove_person(person_id, force=True):
    """
    Remove a person. With force, everything they own is deleted or detached
    first: comments, notifications, logs, subscriptions, time spents, team
    memberships and task assignations.
    """
    person = Person.get(person_id)
    if person.email in config.PROTECTED_ACCOUNTS:
        raise PersonInProtectedAccounts(
            "Can't delete this person it's a protected account."
        )
    if force:
        for comment in Comment.get_all_by(person_id=person_id):
            deletion_service.remove_comment(comment.id)
        comments = Comment.query.filter(
            Comment.acknowledgements.contains(person)
        )
        for comment in comments:
            comment.acknowledgements = [
                member
                for member in comment.acknowledgements
                if str(member.id) != person_id
            ]
            comment.save()
        ApiEvent.delete_all_by(user_id=person_id)
        Notification.delete_all_by(person_id=person_id)
        Notification.delete_all_by(author_id=person_id)
        search_filters_service.remove_search_filters(person_id=person_id)
        DesktopLoginLog.delete_all_by(person_id=person_id)
        LoginLog.delete_all_by(person_id=person_id)
        Subscription.delete_all_by(person_id=person_id)
        TimeSpent.delete_all_by(person_id=person_id)
        for project in Project.query.filter(Project.team.contains(person)):
            project.team = [
                member
                for member in project.team
                if str(member.id) != person_id
            ]
            project.save()
        for task in Task.query.options(selectinload(Task.assignees)).filter(
            Task.assignees.contains(person)
        ):
            task.assignees = [
                assignee
                for assignee in task.assignees
                if str(assignee.id) != person_id
            ]
            task.save()
        for task in Task.get_all_by(assigner_id=person_id):
            task.update({"assigner_id": None})
        for output_file in OutputFile.get_all_by(person_id=person_id):
            output_file.update({"person_id": None})
        for working_file in WorkingFile.get_all_by(person_id=person_id):
            working_file.update({"person_id": None})
        for preview_file in PreviewFile.get_all_by(person_id=person_id):
            preview_file.update({"person_id": None})
    try:
        person.delete()
        events.emit("person:delete", {"person_id": person.id})
    except IntegrityError:
        raise ModelWithRelationsDeletionException(
            "Some data are still linked to given person."
        )

    return person.serialize_safe()


def remove_asset(asset_id, force=False):
    """
    Remove given asset. With tasks attached and without force, the asset
    is only marked canceled; force deletes it and everything tied to it.
    """
    asset = assets_service.get_asset_raw(asset_id)
    is_tasks_related = Task.query.filter_by(entity_id=asset_id).count() > 0

    if is_tasks_related and not force:
        asset.update({"canceled": True})
        assets_service.clear_asset_cache(str(asset_id))
        events.emit(
            "asset:update",
            {"asset_id": asset_id},
            project_id=str(asset.project_id),
        )
        breakdown_service.refresh_casting_stats(
            asset.serialize(obj_type="Asset")
        )
    else:
        # Before deleting EntityLinks, collect affected shot IDs so we can
        # refresh their casting stats after deletion
        cast_in = breakdown_service.get_cast_in(asset_id)
        affected_shot_ids = {
            entity["shot_id"] for entity in cast_in if "shot_id" in entity
        }

        deletion_service.remove_tasks_for_entity(asset_id)
        index_service.remove_asset_index(str(asset_id))
        events.emit(
            "asset:delete",
            {"asset_id": asset_id},
            project_id=str(asset.project_id),
        )
        EntityVersion.delete_all_by(entity_id=asset_id)
        Subscription.delete_all_by(entity_id=asset_id)
        EntityLink.delete_all_by(entity_in_id=asset_id)
        EntityLink.delete_all_by(entity_out_id=asset_id)
        EntityConceptLink.delete_all_by(entity_in_id=asset_id)
        EntityConceptLink.delete_all_by(entity_out_id=asset_id)
        deletion_service.remove_output_files_for_entity(asset_id)
        for child in Entity.get_all_by(parent_id=asset_id):
            child.update({"parent_id": None})
        asset.delete()
        assets_service.clear_asset_cache(str(asset_id))

        if affected_shot_ids:
            for shot_id in affected_shot_ids:
                shot = shots_service.get_shot(shot_id)
                breakdown_service.refresh_shot_casting_stats(shot)
    deleted_asset = asset.serialize(obj_type="Asset")
    return deleted_asset


def cancel_asset(asset_id, force=True):
    """
    Set cancel flag on asset to true. Send an event to event queue.
    """
    asset = assets_service.get_asset_raw(asset_id)

    asset.update({"canceled": True})
    asset_dict = asset.serialize(obj_type="Asset")
    # Same write as the canceling branch of remove_asset, so the same
    # invalidation: without it the asset reads back as live for the whole
    # memoization window.
    assets_service.clear_asset_cache(str(asset_id))
    events.emit(
        "asset:delete",
        {"asset_id": asset_id},
        project_id=str(asset.project_id),
    )
    return asset_dict


def remove_shot(shot_id, force=False):
    """
    Remove given shot from database. If it has tasks linked to it, it marks
    the shot as canceled. Deletion can be forced.
    """
    shot = shots_service.get_shot_raw(shot_id)
    is_tasks_related = Task.query.filter_by(entity_id=shot_id).count() > 0

    if is_tasks_related and not force:
        shot.update({"canceled": True})
        shots_service.clear_shot_cache(shot_id)
        events.emit(
            "shot:update",
            {"shot_id": shot_id},
            project_id=str(shot.project_id),
        )
    else:
        deletion_service.remove_tasks_for_entity(shot_id)

        EntityVersion.delete_all_by(entity_id=shot_id)
        Subscription.delete_all_by(entity_id=shot_id)
        EntityLink.delete_all_by(entity_in_id=shot_id)
        EntityLink.delete_all_by(entity_out_id=shot_id)
        EntityConceptLink.delete_all_by(entity_in_id=shot_id)
        EntityConceptLink.delete_all_by(entity_out_id=shot_id)
        deletion_service.remove_output_files_for_entity(shot_id)

        shot.delete()
        events.emit(
            "shot:delete",
            {"shot_id": shot_id},
            project_id=str(shot.project_id),
        )
        index_service.remove_shot_index(shot_id)
        shots_service.clear_shot_cache(shot_id)

    deleted_shot = shot.serialize(obj_type="Shot")
    return deleted_shot


def remove_scene(scene_id):
    """
    Remove given scene from database. If it has tasks linked to it, it marks
    the scene as canceled.
    """
    scene = shots_service.get_scene_raw(scene_id)
    try:
        scene.delete()
    except IntegrityError:
        scene.update({"canceled": True})
    deleted_scene = scene.serialize(obj_type="Scene")
    events.emit(
        "scene:delete",
        {"scene_id": scene_id},
        project_id=str(scene.project_id),
    )
    return deleted_scene


def remove_sequence(sequence_id, force=False):
    """
    Remove a sequence and all related shots.
    """
    sequence = shots_service.get_sequence_raw(sequence_id)
    if force:
        # Scenes hang from a sequence too, and remove_shot would raise on
        # one halfway through, after taking part of the sequence away.
        for shot in Entity.get_all_by(
            parent_id=sequence_id,
            entity_type_id=entity_types_service.get_shot_type()["id"],
        ):
            remove_shot(shot.id, force=True)
        for scene in Entity.get_all_by(
            parent_id=sequence_id,
            entity_type_id=entity_types_service.get_scene_type()["id"],
        ):
            remove_scene(scene.id)
        Subscription.delete_all_by(entity_id=sequence_id)
        ScheduleItem.delete_all_by(object_id=sequence_id)

        deletion_service.remove_tasks_for_entity(sequence_id)
        Subscription.delete_all_by(entity_id=sequence_id)
        deletion_service.remove_output_files_for_entity(sequence_id)
    try:
        sequence.delete()
        events.emit(
            "sequence:delete",
            {"sequence_id": sequence_id},
            project_id=str(sequence.project_id),
        )
    except IntegrityError:
        raise ModelWithRelationsDeletionException(
            "Some data are still linked to this sequence."
        )
    shots_service.clear_sequence_cache(sequence_id)
    return sequence.serialize(obj_type="Sequence")


def remove_edit(edit_id, force=False):
    """
    Remove given edit from database. If it has tasks linked to it, it marks
    the edit as canceled. Deletion can be forced.
    """
    edit = edits_service.get_edit_raw(edit_id)
    is_tasks_related = Task.query.filter_by(entity_id=edit_id).count() > 0

    if is_tasks_related and not force:
        edit.update({"canceled": True})
        edits_service.clear_edit_cache(edit_id)
        events.emit(
            "edit:update",
            {"edit_id": edit_id},
            project_id=str(edit.project_id),
        )
    else:
        deletion_service.remove_tasks_for_entity(edit_id)

        EntityVersion.delete_all_by(entity_id=edit_id)
        Subscription.delete_all_by(entity_id=edit_id)
        ScheduleItem.delete_all_by(object_id=edit_id)
        EntityLink.delete_all_by(entity_in_id=edit_id)
        EntityLink.delete_all_by(entity_out_id=edit_id)
        EntityConceptLink.delete_all_by(entity_in_id=edit_id)
        EntityConceptLink.delete_all_by(entity_out_id=edit_id)

        edit.delete()
        edits_service.clear_edit_cache(edit_id)
        events.emit(
            "edit:delete",
            {"edit_id": edit_id},
            project_id=str(edit.project_id),
        )

    return edit.serialize(obj_type="Edit")


def remove_concept(concept_id, force=False):
    """
    Remove given concept from database. If it has tasks linked to it, it marks
    the concept as canceled. Deletion can be forced.
    """
    concept = concepts_service.get_concept_raw(concept_id)
    is_tasks_related = Task.query.filter_by(entity_id=concept_id).count() > 0

    if is_tasks_related and not force:
        concept.update({"canceled": True})
        concepts_service.clear_concept_cache(concept_id)
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
        concepts_service.clear_concept_cache(concept_id)

    return concept.serialize(obj_type="Concept")
