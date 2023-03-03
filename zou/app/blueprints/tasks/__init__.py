from zou.app.utils.api import create_blueprint_for_api

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
    CreateEntityTasksResource,
    GetTimeSpentDateResource,
    GetTimeSpentResource,
    SetTimeSpentResource,
    AddTimeSpentResource,
    SetTaskMainPreviewResource,
)


routes = [
    ("/data/tasks/<uuid:task_id>/comments", TaskCommentsResource),
    (
        "/data/tasks/<uuid:task_id>/comments/<uuid:comment_id>",
        TaskCommentResource,
    ),
    ("/data/tasks/<uuid:task_id>/previews", TaskPreviewsResource),
    ("/data/tasks/<uuid:task_id>/full", TaskFullResource),
    ("/data/persons/<uuid:person_id>/tasks", PersonTasksResource),
    (
        "/data/persons/<uuid:person_id>/related-tasks/<uuid:task_type_id>",
        PersonRelatedTasksResource,
    ),
    ("/data/persons/<uuid:person_id>/done-tasks", PersonDoneTasksResource),
    (
        "/data/entities/<uuid:entity_id>/task-types/<uuid:task_type_id>/tasks",
        TaskForEntityResource,
    ),
    ("/data/projects/<uuid:project_id>/comments", ProjectCommentsResource),
    (
        "/data/projects/<uuid:project_id>/notifications",
        ProjectNotificationsResource,
    ),
    (
        "/data/projects/<uuid:project_id>/preview-files",
        ProjectPreviewFilesResource,
    ),
    (
        "/data/projects/<uuid:project_id>/subscriptions",
        ProjectSubscriptionsResource,
    ),
    ("/data/projects/<uuid:project_id>/tasks", ProjectTasksResource),
    (
        "/actions/projects/<uuid:project_id>/task-types/<uuid:task_type_id>/delete-tasks",
        DeleteAllTasksForTaskTypeResource,
    ),
    (
        "/actions/projects/<uuid:project_id>/delete-tasks",
        DeleteTasksResource,
    ),
    ("/actions/tasks/<uuid:task_id>/assign", TaskAssignResource),
    ("/actions/tasks/clear-assignation", ClearAssignationResource),
    ("/actions/persons/<uuid:person_id>/assign", TasksAssignResource),
    (
        "/actions/tasks/<uuid:task_id>/time-spents/<string:date>",
        GetTimeSpentDateResource,
    ),
    ("/actions/tasks/<uuid:task_id>/time-spents", GetTimeSpentResource),
    (
        "/actions/tasks/<uuid:task_id>/time-spents/<string:date>/persons/<uuid:person_id>",
        SetTimeSpentResource,
    ),
    (
        "/actions/tasks/<uuid:task_id>/time-spents/<string:date>/persons/<uuid:person_id>/add",
        AddTimeSpentResource,
    ),
    (
        "/actions/tasks/<uuid:task_id>/comments/<uuid:comment_id>/add-preview",
        AddPreviewResource,
    ),
    (
        "/actions/tasks/<uuid:task_id>/comments/<uuid:comment_id>/preview-files/"
        "<preview_file_id>",
        AddExtraPreviewResource,
    ),
    ("/actions/tasks/<uuid:task_id>/to-review", ToReviewResource),
    (
        "/actions/projects/<uuid:project_id>/task-types/<uuid:task_type_id>/shots/create-tasks",
        CreateShotTasksResource,
    ),
    (
        "/actions/projects/<uuid:project_id>/task-types/<uuid:task_type_id>/assets/create-tasks",
        CreateAssetTasksResource,
    ),
    (
        "/actions/projects/<uuid:project_id>/task-types/<uuid:task_type_id>/edits/create-tasks",
        CreateEditTasksResource,
    ),
    (
        "/actions/projects/<uuid:project_id>/task-types/<uuid:task_type_id>/create-tasks/<string:entity_type>/",
        CreateEntityTasksResource,
    ),
    (
        "/actions/tasks/<uuid:task_id>/set-main-preview",
        SetTaskMainPreviewResource,
    ),
]

blueprint = create_blueprint_for_api("tasks", routes)
