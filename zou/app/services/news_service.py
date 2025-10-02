import math

from sqlalchemy import func
from sqlalchemy.orm import aliased

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.news import News
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task

from zou.app.utils import cache, events, fields
from zou.app.services import names_service, tasks_service


def create_news(
    comment_id=None,
    author_id=None,
    task_id=None,
    preview_file_id=None,
    change=False,
    created_at=None,
):
    """
    Create a new news for given person and comment.
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
    For given task and comment, create a news matching comment and change
    that occured on the task.
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
    Delete all news related to comment. It's mandatory to be able to delete the
    comment afterwards.
    """
    news_list = News.get_all_by(comment_id=comment_id)
    if len(news_list) > 0:
        task = tasks_service.get_task(news_list[0].task_id)
        for news in news_list:
            news.delete()
            events.emit(
                "news:delete",
                {"news_id": news.id},
                project_id=task["project_id"],
            )
    return fields.serialize_list(news_list)


def get_last_news_for_project(
    project_ids=[],
    project_id=None,
    news_id=None,
    entity_id=None,
    only_preview=False,
    task_type_id=None,
    task_status_id=None,
    author_id=None,
    page=1,
    limit=50,
    before=None,
    after=None,
    episode_id=None,
    current_user=None,
):
    """
    Return last 50 news for given project. Add related information to make it
    displayable.
    """
    offset = (page - 1) * limit

    query = (
        News.query.order_by(News.created_at.desc())
        .join(Task, News.task_id == Task.id)
        .join(Project)
        .join(Entity, Task.entity_id == Entity.id)
        .outerjoin(Comment, News.comment_id == Comment.id)
        .outerjoin(PreviewFile, News.preview_file_id == PreviewFile.id)
    )

    if news_id is not None:
        query = query.filter(News.id == news_id)

    if project_id is not None:
        query = query.filter(Task.project_id == project_id)

    if len(project_ids) > 0:
        query = query.filter(Project.id.in_(project_ids))
    elif current_user is not None:
        if current_user.role.code != "admin":
            query = query.filter(Project.team.contains(current_user))

    if entity_id is not None:
        query = query.filter(Entity.id == entity_id)

    if episode_id is not None:
        Sequence = aliased(Entity, name="sequence")
        query = query.join(Sequence, Entity.parent_id == Sequence.id).filter(
            Sequence.parent_id == episode_id
        )

    if task_status_id is not None:
        query = query.filter(Comment.task_status_id == task_status_id)

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if author_id is not None:
        query = query.filter(News.author_id == author_id)

    if only_preview:
        query = query.filter(News.preview_file_id != None)

    if after is not None:
        query = query.filter(
            News.created_at > func.cast(after, News.created_at.type)
        )

    if before is not None:
        query = query.filter(
            News.created_at < func.cast(before, News.created_at.type)
        )

    (total, nb_pages) = _get_news_total(query, limit)

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
        full_entity_name, episode_id, _ = names_service.get_full_entity_name(
            task_entity_id
        )

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

    if only_preview:
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
            key = f"{str(preview_file.task_id)}-{preview_file.revision}"
            if not key in preview_files_map:
                preview_files_map[key] = []
            preview_files_map[key].append(preview_file.present_minimal())

        for entry in result:
            key = f"{entry['task_id']}-{entry['preview_file_revision']}"
            entry["preview_files"] = preview_files_map[key]

    return {
        "data": result,
        "total": total,
        "nb_pages": nb_pages,
        "limit": limit,
        "offset": offset,
        "page": page,
    }


def _get_news_total(query, limit):
    total = query.count()
    nb_pages = int(math.ceil(total / float(limit)))
    return total, nb_pages


def get_news_stats_for_project(
    project_ids=[],
    project_id=None,
    only_preview=False,
    task_type_id=None,
    task_status_id=None,
    episode_id=None,
    author_id=None,
    before=None,
    after=None,
    current_user=None,
):
    """
    Return the number of news by task status for given project and filters.
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

    if project_id is not None:
        query = query.filter(Task.project_id == project_id)

    if len(project_ids) > 0:
        query = query.filter(Project.id.in_(project_ids))
    elif current_user is not None:
        if current_user.role.code != "admin":
            query = query.filter(Project.team.contains(current_user))

    if task_status_id is not None:
        query = query.filter(Comment.task_status_id == task_status_id)

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if author_id is not None:
        query = query.filter(News.author_id == author_id)

    if episode_id is not None:
        Sequence = aliased(Entity, name="sequence")
        query = query.join(Sequence, Entity.parent_id == Sequence.id).filter(
            Sequence.parent_id == episode_id
        )

    if only_preview:
        query = query.filter(News.preview_file_id != None)

    if after is not None:
        query = query.filter(
            News.created_at > func.cast(after, News.created_at.type)
        )

    if before is not None:
        query = query.filter(
            News.created_at < func.cast(before, News.created_at.type)
        )
    stats = {}
    for task_status_id, count in query.all():
        if task_status_id is not None:
            stats[str(task_status_id)] = count
    return stats


@cache.memoize_function(120)
def get_news(project_id, news_id):
    return get_last_news_for_project(project_id=project_id, news_id=news_id)


def get_news_for_entity(entity_id):
    """
    Get all news related to a given entity.
    """
    return get_last_news_for_project(entity_id=entity_id, limit=2000)
