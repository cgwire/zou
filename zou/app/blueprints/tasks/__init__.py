from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    TaskFullResource,
    TaskForEntityResource,
    DeleteTasksResource,
    DeleteAllTasksForTaskTypeResource,
    TaskAssignResource,
    TasksAssignResource,
    ClearAssignationResource,
    PersonRelatedTasksResource,
    PersonTasksResource,
    PersonDoneTasksResource,
    ToReviewResource,
    TaskCommentsResource,
    TaskCommentResource,
    TaskPreviewsResource,
    AddPreviewResource,
    AddExtraPreviewResource,
    ProjectCommentsResource,
    ProjectNotificationsResource,
    ProjectPreviewFilesResource,
    ProjectSubscriptionsResource,
    ProjectTasksResource,
    CreateShotTasksResource,
    CreateAssetTasksResource,
    CreateEditTasksResource,
    GetTimeSpentResource,
    SetTimeSpentResource,
    AddTimeSpentResource,
)


routes = [
    ("/data/tasks/<task_id>/comments", TaskCommentsResource),
    ("/data/tasks/<task_id>/comments/<comment_id>", TaskCommentResource),
    ("/data/tasks/<task_id>/previews", TaskPreviewsResource),
    ("/data/tasks/<task_id>/full", TaskFullResource),
    ("/data/persons/<person_id>/tasks", PersonTasksResource),
    (
        "/data/persons/<person_id>/related-tasks/<task_type_id>",
        PersonRelatedTasksResource,
    ),
    ("/data/persons/<person_id>/done-tasks", PersonDoneTasksResource),
    (
        "/data/entities/<entity_id>/task-types/<task_type_id>/tasks",
        TaskForEntityResource,
    ),
    ("/data/projects/<project_id>/comments", ProjectCommentsResource),
    (
        "/data/projects/<project_id>/notifications",
        ProjectNotificationsResource,
    ),
    ("/data/projects/<project_id>/preview-files", ProjectPreviewFilesResource),
    (
        "/data/projects/<project_id>/subscriptions",
        ProjectSubscriptionsResource,
    ),
    ("/data/projects/<project_id>/tasks", ProjectTasksResource),
    (
        "/actions/projects/<project_id>/task-types/<task_type_id>/delete-tasks",
        DeleteAllTasksForTaskTypeResource,
    ),
    (
        "/actions/projects/<project_id>/delete-tasks",
        DeleteTasksResource,
    ),
    ("/actions/tasks/<task_id>/assign", TaskAssignResource),
    ("/actions/tasks/clear-assignation", ClearAssignationResource),
    ("/actions/persons/<person_id>/assign", TasksAssignResource),
    ("/actions/tasks/<task_id>/time-spents/<date>", GetTimeSpentResource),
    (
        "/actions/tasks/<task_id>/time-spents/<date>/persons/<person_id>",
        SetTimeSpentResource,
    ),
    (
        "/actions/tasks/<task_id>/time-spents/<date>/persons/<person_id>/add",
        AddTimeSpentResource,
    ),
    (
        "/actions/tasks/<task_id>/comments/<comment_id>/add-preview",
        AddPreviewResource,
    ),
    (
        "/actions/tasks/<task_id>/comments/<comment_id>/preview-files/"
        "<preview_file_id>",
        AddExtraPreviewResource,
    ),
    ("/actions/tasks/<task_id>/to-review", ToReviewResource),
    (
        "/actions/projects/<project_id>/task-types/<task_type_id>/shots/create-tasks",
        CreateShotTasksResource,
    ),
    (
        "/actions/projects/<project_id>/task-types/<task_type_id>/assets/create-tasks",
        CreateAssetTasksResource,
    ),
    (
        "/actions/projects/<project_id>/task-types/<task_type_id>/edits/create-tasks",
        CreateEditTasksResource,
    ),
]

blueprint = Blueprint("tasks", "tasks")
api = configure_api_from_blueprint(blueprint, routes)
