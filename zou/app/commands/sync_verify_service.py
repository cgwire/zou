"""
Compare object counts between a source Kitsu instance and the local one
to verify a project synchronization.
"""

import gazu


from zou.app.models.asset_instance import AssetInstance
from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry
from zou.app.models.build_job import BuildJob
from zou.app.models.chat import Chat
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.milestone import Milestone
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.playlist import Playlist
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.preview_file import PreviewFile
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
)
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.models.working_file import WorkingFile

from zou.app.commands.sync_service import logger


def _project_sync_specs(pid):
    """
    (label, source counter, target counter, synced_by_sync_full) for every
    project-scoped model. synced=False rows flag tables present in the
    schema that sync_full doesn't migrate today, surfaced so the operator
    knows to handle them out-of-band.
    """
    return [
        (
            "Episode",
            _src_count(f"projects/{pid}/episodes"),
            _tgt_entity_type(pid, "Episode"),
            True,
        ),
        (
            "Sequence",
            _src_count(f"projects/{pid}/sequences"),
            _tgt_entity_type(pid, "Sequence"),
            True,
        ),
        ("Asset", _src_count(f"projects/{pid}/assets"), _tgt_asset(pid), True),
        (
            "Shot",
            _src_count(f"projects/{pid}/shots"),
            _tgt_entity_type(pid, "Shot"),
            True,
        ),
        (
            "Concept",
            _src_count(f"projects/{pid}/concepts"),
            _tgt_entity_type(pid, "Concept"),
            True,
        ),
        (
            "EntityLink",
            _src_count(f"projects/{pid}/entity-links"),
            _tgt_entity_link(pid),
            True,
        ),
        (
            "Task",
            _src_count(f"projects/{pid}/tasks"),
            _tgt(Task, project_id=pid),
            True,
        ),
        (
            "Comment",
            _src_count(f"projects/{pid}/comments"),
            _tgt_comment(pid),
            True,
        ),
        (
            "TimeSpent",
            _src_count(f"projects/{pid}/time-spents"),
            _tgt_time_spent(pid),
            True,
        ),
        (
            "PreviewFile",
            _src_count(f"projects/{pid}/preview-files"),
            _tgt_preview_file(pid),
            True,
        ),
        (
            "Playlist",
            _src_count(f"projects/{pid}/playlists/all"),
            _tgt(Playlist, project_id=pid),
            True,
        ),
        (
            "BuildJob",
            _src_count(f"projects/{pid}/build-jobs"),
            _tgt_build_job(pid),
            True,
        ),
        (
            "AttachmentFile",
            _src_count(f"projects/{pid}/attachment-files"),
            _tgt_attachment_file(pid),
            True,
        ),
        (
            "MetadataDescriptor",
            _src_count(f"projects/{pid}/metadata-descriptors"),
            _tgt(MetadataDescriptor, project_id=pid),
            True,
        ),
        (
            "ScheduleItem",
            _src_count(f"projects/{pid}/schedule-items"),
            _tgt(ScheduleItem, project_id=pid),
            True,
        ),
        (
            "Subscription",
            _src_count(f"projects/{pid}/subscriptions"),
            _tgt_subscription(pid),
            True,
        ),
        (
            "Notification",
            _src_count(f"projects/{pid}/notifications"),
            _tgt_notification(pid),
            True,
        ),
        ("News", _src_count(f"projects/{pid}/news"), _tgt_news(pid), True),
        (
            "Milestone",
            _src_count(f"projects/{pid}/milestones"),
            _tgt(Milestone, project_id=pid),
            True,
        ),
        (
            "SearchFilter",
            _src_count_params("search-filters", {"project_id": pid}),
            _tgt(SearchFilter, project_id=pid),
            True,
        ),
        (
            "SearchFilterGroup",
            _src_count_params("search-filter-groups", {"project_id": pid}),
            _tgt(SearchFilterGroup, project_id=pid),
            True,
        ),
        # Below: tables sync_full does not migrate today.
        (
            "Budget",
            _src_count(f"projects/{pid}/budgets"),
            _tgt(Budget, project_id=pid),
            False,
        ),
        ("BudgetEntry", None, _tgt_budget_entry(pid), False),
        (
            "OutputFile",
            _src_count(f"projects/{pid}/output-files"),
            _tgt_output_file(pid),
            False,
        ),
        ("WorkingFile", None, _tgt_working_file(pid), False),
        ("AssetInstance", None, _tgt_asset_instance(pid), False),
        ("Chat", None, _tgt_chat(pid), False),
        (
            "ProductionSchedule",
            None,
            _tgt(ProductionScheduleVersion, project_id=pid),
            False,
        ),
        ("PlaylistShareLink", None, _tgt_share_link(pid), False),
    ]


def verify_project_sync(project_name, direction="pull"):
    """
    Compare row counts for every project-scoped model between the local
    instance and a remote one (configured via ``init(...)``).

    ``direction="pull"`` (default): the remote is the source of a sync-full;
    column ``Source``=remote, ``Target``=local. Used to detect batches
    dropped silently by ``sync_entries`` and tables not yet wired into
    ``project_events``.

    ``direction="push"``: the remote is the target of a sync-push;
    column ``Source``=local, ``Target``=remote. Used to detect rows that
    didn't reach the target after a sync-push.

    Pure read-only.
    """
    remote_role = "source" if direction == "pull" else "target"

    try:
        remote_project = gazu.project.get_project_by_name(project_name)
    except Exception as exception:
        # gazu answers None for a production it does not know, so anything
        # raised here is the connection itself. The clause used to name
        # gazu.exception.ProjectNotFoundException, which does not exist:
        # evaluating it turned every failure into an AttributeError raised
        # while handling the first one.
        print(f"Could not reach the {remote_role} instance: {exception}")
        return

    if remote_project is None:
        print(f"Project '{project_name}' not found on {remote_role}.")
        return

    pid = remote_project["id"]
    local_project = Project.get(pid)
    if local_project is None:
        if direction == "pull":
            print(
                f"Project '{project_name}' ({pid}) is not present locally."
                f" Run `zou sync-full --only-projects --project "
                f"'{project_name}'` first."
            )
        else:
            print(
                f"Project '{project_name}' ({pid}) is not present locally."
                " Nothing to push-verify against."
            )
        return

    specs = _project_sync_specs(pid)

    print(f"\nVerifying project '{project_name}' ({pid}):\n")
    header = (
        f"{'Model':22s}  {'Source':>8s}  {'Target':>8s}  "
        f"{'Delta':>8s}  Status"
    )
    print(header)
    print("-" * (len(header) + 4))

    diffs = 0
    missing_with_data = 0
    for label, remote_fn, local_fn, synced in specs:
        remote = _safe(remote_fn)
        local = _safe(local_fn)
        if direction == "push":
            src, tgt = local, remote
        else:
            src, tgt = remote, local

        src_str = f"{src:>8d}" if isinstance(src, int) else "     N/A"
        tgt_str = f"{tgt:>8d}" if isinstance(tgt, int) else "     N/A"

        if isinstance(src, int) and isinstance(tgt, int):
            delta = tgt - src
            delta_str = f"{delta:+d}"
            if synced:
                status = "OK" if delta == 0 else "DIFF"
                if delta != 0:
                    diffs += 1
            else:
                status = "NOT SYNCED"
                if src > 0:
                    missing_with_data += 1
        else:
            delta_str = "    -"
            status = "ok" if synced else "NOT SYNCED"

        print(f"{label:22s}  {src_str}  {tgt_str}  {delta_str:>8s}  {status}")

    print()
    if diffs:
        if direction == "pull":
            print(
                f"{diffs} synced model(s) show a row-count delta — likely due "
                "to IntegrityError batches caught silently by sync_entries. "
                "Re-run with LOGLEVEL=DEBUG and grep for 'An error occured'."
            )
        else:
            print(
                f"{diffs} synced model(s) show a row-count delta — some "
                "rows did not reach the target. Inspect the sync-push logs "
                "for failed batches."
            )
    if missing_with_data:
        held_on = "source" if direction == "pull" else "the local instance"
        print(
            f"{missing_with_data} non-synced model(s) hold data on "
            f"{held_on} — they are out of scope for sync. Plan a manual "
            "transfer."
        )
    if not diffs and not missing_with_data:
        print("All comparable models match and no unsynced tables hold data.")


def _safe(fn):
    """
    Run a counting callable, turning any failure into None so one
    unreachable route does not abort the whole verification table.
    """
    if fn is None:
        return None
    try:
        return fn()
    except Exception as e:
        logger.warning("Verify count failed: %s", e)
        return None


def _src_count(path):
    """
    Return a callable counting rows on the source instance for a path.

    Handles list-returning routes (e.g. /projects/X/assets) and paginated
    routes (which return {"data": ..., "total": N, "nb_pages": M}).

    """

    def fetch():
        response = gazu.client.fetch_all(path)
        if isinstance(response, list):
            return len(response)
        if isinstance(response, dict):
            if "total" in response:
                return response["total"]
            count = len(response.get("data", []))
            nb_pages = response.get("nb_pages", 1)
            for page in range(2, nb_pages + 1):
                sep = "&" if "?" in path else "?"
                more = gazu.client.fetch_all(f"{path}{sep}page={page}")
                if isinstance(more, dict):
                    count += len(more.get("data", []))
            return count
        return None

    return fetch


def _src_count_params(path, params):
    """
    Same as _src_count for a route taking query parameters. Only reads the
    first page: the routes it serves return a total.
    """

    def fetch():
        response = gazu.client.fetch_all(path, params=params)
        if isinstance(response, list):
            return len(response)
        if isinstance(response, dict):
            return response.get("total", len(response.get("data", [])))
        return None

    return fetch


def _tgt(model, **filters):
    """
    Build a counter of the local rows of given model matching filters.
    """
    return lambda: model.query.filter_by(**filters).count()


def _tgt_via(model, parent, foreign_key, project_id):
    """
    Build a counter of the rows of given model whose parent belongs to the
    project. Mirrors the join the matching source route does.
    """
    return lambda: (
        model.query.join(parent, parent.id == foreign_key)
        .filter(parent.project_id == project_id)
        .count()
    )


def _tgt_entity_type(project_id, type_name):
    """
    Build a counter of the project entities of given type name. A type
    absent from this instance counts as zero rather than failing.
    """

    def count():
        et = EntityType.get_by(name=type_name)
        if et is None:
            return 0
        return Entity.query.filter_by(
            project_id=project_id, entity_type_id=et.id
        ).count()

    return count


def _tgt_asset(project_id):
    """
    Assets are entities whose type is not one of the structural types.
    """
    structural = [
        "Episode",
        "Sequence",
        "Shot",
        "Concept",
        "ConceptFolder",
        "Edit",
        "Scene",
    ]

    def count():
        structural_ids = [
            et.id
            for et in EntityType.query.filter(
                EntityType.name.in_(structural)
            ).all()
        ]
        q = Entity.query.filter_by(project_id=project_id)
        if structural_ids:
            q = q.filter(~Entity.entity_type_id.in_(structural_ids))
        return q.count()

    return count


def _tgt_entity_link(project_id):
    """
    Entity links whose source entity lives in the project.
    """

    return _tgt_via(EntityLink, Entity, EntityLink.entity_in_id, project_id)


def _tgt_comment(project_id):
    """
    Comments attached to tasks of the project (matches the source route).
    """

    return _tgt_via(Comment, Task, Comment.object_id, project_id)


def _tgt_time_spent(project_id):
    """
    Time spents on tasks of the project.
    """
    return _tgt_via(TimeSpent, Task, TimeSpent.task_id, project_id)


def _tgt_preview_file(project_id):
    """
    Preview files attached to tasks of the project.
    """
    return _tgt_via(PreviewFile, Task, PreviewFile.task_id, project_id)


def _tgt_build_job(project_id):
    """
    Build jobs of the project playlists.
    """
    return _tgt_via(BuildJob, Playlist, BuildJob.playlist_id, project_id)


def _tgt_attachment_file(project_id):
    """
    Attachment files of the comments of the project tasks.
    """

    def count():
        return (
            AttachmentFile.query.join(
                Comment, Comment.id == AttachmentFile.comment_id
            )
            .join(Task, Task.id == Comment.object_id)
            .filter(Task.project_id == project_id)
            .count()
        )

    return count


def _tgt_subscription(project_id):
    """
    Subscriptions on tasks of the project.
    """
    return _tgt_via(Subscription, Task, Subscription.task_id, project_id)


def _tgt_notification(project_id):
    """
    Notifications attached to tasks of the project.
    """

    return _tgt_via(Notification, Task, Notification.task_id, project_id)


def _tgt_news(project_id):
    """
    News tied to tasks of the project.
    """

    return _tgt_via(News, Task, News.task_id, project_id)


def _tgt_output_file(project_id):
    """
    Output files of the project entities.
    """
    return _tgt_via(OutputFile, Entity, OutputFile.entity_id, project_id)


def _tgt_working_file(project_id):
    """
    Working files of the project tasks.
    """
    return _tgt_via(WorkingFile, Task, WorkingFile.task_id, project_id)


def _tgt_asset_instance(project_id):
    """
    Asset instances of the project assets.
    """
    return _tgt_via(AssetInstance, Entity, AssetInstance.asset_id, project_id)


def _tgt_chat(project_id):
    """
    Chats attached to entities of the project.
    """

    return _tgt_via(Chat, Entity, Chat.object_id, project_id)


def _tgt_budget_entry(project_id):
    """
    Budget entries of the project budgets.
    """
    return _tgt_via(BudgetEntry, Budget, BudgetEntry.budget_id, project_id)


def _tgt_share_link(project_id):
    """
    Share links of the project playlists.
    """
    return _tgt_via(
        PlaylistShareLink, Playlist, PlaylistShareLink.playlist_id, project_id
    )
