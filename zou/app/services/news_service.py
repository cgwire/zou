import dataclasses
import math
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import aliased

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.news import News
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import (
    entities_service,
    persons_service,
    tasks_service,
)
from zou.app.utils import cache, events, fields


@dataclasses.dataclass
class NewsFilters:
    """
    Criteria that the news list and the news stats share. project_ids is
    a scoping allowlist. It is different from the project_id that the
    caller asked for. If project_ids is empty and the current user is not
    an admin, the query uses the projects of the current user.
    """

    project_id: Optional[str] = None
    project_ids: Optional[list] = None
    current_user: Optional[Any] = None
    task_status_id: Optional[str] = None
    task_type_id: Optional[str] = None
    author_id: Optional[str] = None
    episode_id: Optional[str] = None
    only_preview: bool = False
    before: Optional[Any] = None
    after: Optional[Any] = None


def _apply_news_filters(query, filters):
    """
    Apply the filters that the news list and the news stats share.

    project_ids is a scoping allowlist. It is different from the
    project_id that the caller asked for. If project_ids is empty and the
    current user is not an admin, the query uses the projects of the
    current user.
    """
    if filters.project_id is not None:
        query = query.filter(Task.project_id == filters.project_id)

    if filters.project_ids and len(filters.project_ids) > 0:
        query = query.filter(Project.id.in_(filters.project_ids))
    elif (
        filters.current_user is not None
        and filters.current_user.role.code != "admin"
    ):
        query = query.filter(Project.team.contains(filters.current_user))

    if filters.episode_id is not None:
        Sequence = aliased(Entity, name="sequence")
        query = query.join(Sequence, Entity.parent_id == Sequence.id).filter(
            Sequence.parent_id == filters.episode_id
        )

    if filters.task_status_id is not None:
        query = query.filter(Comment.task_status_id == filters.task_status_id)

    if filters.task_type_id is not None:
        query = query.filter(Task.task_type_id == filters.task_type_id)

    if filters.author_id is not None:
        query = query.filter(News.author_id == filters.author_id)

    if filters.only_preview:
        query = query.filter(News.preview_file_id != None)

    if filters.after is not None:
        query = query.filter(
            News.created_at > func.cast(filters.after, News.created_at.type)
        )

    if filters.before is not None:
        query = query.filter(
            News.created_at < func.cast(filters.before, News.created_at.type)
        )

    return query


def _get_news_total(query, limit):
    """
    Return the number of news that match the given query, and the page
    count.
    """
    # count() puts the full select with its 5 joins in a subquery. A count
    # of the news column over the same joins gives the same total and does
    # not materialize the select. Remove order_by: aggregates forbid it.
    total = query.order_by(None).with_entities(func.count(News.id)).scalar()
    nb_pages = int(math.ceil(total / float(limit)))
    return total, nb_pages


def create_news(
    comment_id=None,
    author_id=None,
    task_id=None,
    preview_file_id=None,
    change=False,
    created_at=None,
):
    """
    Create a news for the given person and comment.
    """
    news = News.create(
        change=change,
        author_id=author_id,
        comment_id=comment_id,
        preview_file_id=preview_file_id,
        task_id=task_id,
        created_at=created_at,
    )
    return news.serialize()


def create_news_for_task_and_comment(
    task, comment, change=False, created_at=None
):
    """
    Create a news for the given task and comment. The news records the
    comment and the change on the task. Then emit a news:new event.
    """
    task = tasks_service.get_task(task["id"])
    news = create_news(
        comment_id=comment["id"],
        preview_file_id=comment["preview_file_id"],
        author_id=comment["person_id"],
        task_id=comment["object_id"],
        change=change,
        created_at=created_at,
    )
    events.emit(
        "news:new",
        {
            "news_id": news["id"],
            "task_status_id": comment["task_status_id"],
            "task_type_id": task["task_type_id"],
        },
        project_id=task["project_id"],
    )
    return news


def delete_news_for_comment(comment_id):
    """
    Delete all news of the given comment. This is necessary before you
    can delete the comment.
    """
    news_list = News.get_all_by(comment_id=comment_id)
    if len(news_list) > 0:
        task = tasks_service.get_task(news_list[0].task_id)
        delete_news(news_list, task["project_id"])
    return fields.serialize_list(news_list)


def delete_news(news_list, project_id=None):
    """
    Delete the given news rows. Remove them from the get_news cache and
    announce each removal. If there is no project, the function cannot
    address the cache entry and sends the event without a project scope.
    """
    for news in news_list:
        news_id = str(news.id)
        news.delete()
        if project_id is not None:
            cache.cache.delete_memoized(get_news, str(project_id), news_id)
        events.emit("news:delete", {"news_id": news_id}, project_id=project_id)


def clear_news_cache(news_list, project_id):
    """
    Remove the given news from the get_news cache. Call it after a write
    that changes the output of the single-news route. On the events after
    such a write, the feeds load the news again through this route.
    """
    for news in news_list:
        cache.cache.delete_memoized(get_news, str(project_id), str(news.id))


def clear_comment_news_cache(comment_id, project_id):
    """
    Remove the news of the given comment from the get_news cache.
    """
    clear_news_cache(News.get_all_by(comment_id=comment_id), project_id)


def get_last_news_for_project(
    filters=None, news_id=None, entity_id=None, page=1, limit=50
):
    """
    Return a page of the last news that match the given filters (50 news
    per page by default). The page is a dict with data, total, nb_pages,
    limit, offset and page. Add related data to each news so that clients
    can show it.
    """
    filters = filters or NewsFilters()
    offset = (page - 1) * limit

    # A news gets the created_at of its comment, to the nearest second, so
    # many news have the same value. The id keeps the same order on every
    # page.
    query = (
        News.query.order_by(News.created_at.desc(), News.id.desc())
        .join(Task, News.task_id == Task.id)
        .join(Project)
        .join(Entity, Task.entity_id == Entity.id)
        .outerjoin(Comment, News.comment_id == Comment.id)
        .outerjoin(PreviewFile, News.preview_file_id == PreviewFile.id)
    )

    if news_id is not None:
        query = query.filter(News.id == news_id)

    if entity_id is not None:
        query = query.filter(Entity.id == entity_id)

    query = _apply_news_filters(query, filters)

    total, nb_pages = _get_news_total(query, limit)

    query = query.add_columns(
        Project.id,
        Project.name,
        Task.task_type_id,
        Comment.id,
        Comment.task_status_id,
        Task.entity_id,
        PreviewFile.extension,
        PreviewFile.annotations,
        PreviewFile.revision,
        Entity.preview_file_id,
    )

    query = query.limit(limit)
    query = query.offset(offset)
    news_list = query.all()
    result = []

    entity_ids = list(
        set(
            task_entity_id
            for (_, _, _, _, _, _, task_entity_id, _, _, _, _) in news_list
        )
    )
    entity_names_map = entities_service.get_full_entity_names(entity_ids)

    for (
        news,
        project_id,
        project_name,
        task_type_id,
        comment_id,
        task_status_id,
        task_entity_id,
        preview_file_extension,
        preview_file_annotations,
        preview_file_revision,
        entity_preview_file_id,
    ) in news_list:
        entity_name_data = entity_names_map.get(str(task_entity_id))
        if entity_name_data:
            full_entity_name, episode_id, _ = entity_name_data
        else:
            full_entity_name, episode_id = "", None

        result.append(
            fields.serialize_dict(
                {
                    "id": news.id,
                    "type": "News",
                    "author_id": news.author_id,
                    "comment_id": news.comment_id,
                    "task_id": news.task_id,
                    "task_type_id": task_type_id,
                    "task_status_id": task_status_id,
                    "task_entity_id": task_entity_id,
                    "preview_file_id": news.preview_file_id,
                    "preview_file_extension": preview_file_extension,
                    "preview_file_revision": preview_file_revision,
                    "project_id": project_id,
                    "project_name": project_name,
                    "created_at": news.created_at,
                    "change": news.change,
                    "full_entity_name": full_entity_name,
                    "episode_id": episode_id,
                    "entity_preview_file_id": entity_preview_file_id,
                }
            )
        )

    # Embed the author so that clients can show guest authors directly.
    author_ids = list(
        {news["author_id"] for news in result if news.get("author_id")}
    )
    author_map = persons_service.get_short_persons_map(author_ids)
    for news in result:
        news["person"] = author_map.get(news["author_id"])

    # The feed also plays the preview files of a news that it loads alone.
    if filters.only_preview or news_id is not None:
        task_ids = [
            news["task_id"] for news in result if news["task_id"] is not None
        ]
        revisions = [news["preview_file_revision"] for news in result]
        preview_files = (
            PreviewFile.query.filter(PreviewFile.task_id.in_(task_ids))
            .filter(PreviewFile.revision.in_(revisions))
            .order_by(
                PreviewFile.task_id, PreviewFile.revision, PreviewFile.position
            )
        )
        preview_files_map = {}
        for preview_file in preview_files:
            key = f"{preview_file.task_id!s}-{preview_file.revision}"
            preview_files_map.setdefault(key, []).append(
                preview_file.present_minimal()
            )

        for entry in result:
            key = f"{entry['task_id']}-{entry['preview_file_revision']}"
            entry["preview_files"] = preview_files_map.get(key, [])

    return {
        "data": result,
        "total": total,
        "nb_pages": nb_pages,
        "limit": limit,
        "offset": offset,
        "page": page,
    }


def get_news_stats_for_project(filters=None):
    """
    Return the number of news for each task status for the given project
    and filters. Count only the news that record a status change.
    { "task-status-1": 24, "task-status-2": 58 }
    """
    query = (
        News.query.join(Task, News.task_id == Task.id)
        .join(Project)
        .join(Comment)
        .join(Entity, Task.entity_id == Entity.id)
        .outerjoin(PreviewFile, News.preview_file_id == PreviewFile.id)
        .with_entities(Comment.task_status_id, func.count(Entity.id))
        .group_by(
            Comment.task_status_id,
        )
        .filter(News.change == True)
    )

    query = _apply_news_filters(query, filters or NewsFilters())

    stats = {}
    for task_status_id, count in query.all():
        if task_status_id is not None:
            stats[str(task_status_id)] = count
    return stats


@cache.memoize_function(120)
def get_news(project_id, news_id):
    """
    Return one news, in the same shape as the news list.
    """
    return get_last_news_for_project(
        NewsFilters(project_id=project_id), news_id=news_id
    )


def get_news_for_entity(entity_id):
    """
    Return the last 2000 news of the given entity, in the same page format
    as get_last_news_for_project.
    """
    return get_last_news_for_project(entity_id=entity_id, limit=2000)
