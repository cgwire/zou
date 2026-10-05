from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.concepts.resources import (
    ConceptFolderResource,
    ConceptResource,
    AllConceptsResource,
    ConceptsAndTasksResource,
    ConceptPreviewsResource,
    ConceptTaskTypesResource,
    ConceptTasksResource,
    MoveConceptsResource,
    ProjectConceptFoldersResource,
    ProjectConceptsResource,
)

routes = [
    ("/data/concepts", AllConceptsResource),
    ("/data/concepts/with-tasks", ConceptsAndTasksResource),
    ("/data/concepts/<concept_id>", ConceptResource),
    ("/data/concepts/<concept_id>/task-types", ConceptTaskTypesResource),
    ("/data/concepts/<concept_id>/tasks", ConceptTasksResource),
    ("/data/concepts/<concept_id>/preview-files", ConceptPreviewsResource),
    ("/data/projects/<project_id>/concepts", ProjectConceptsResource),
    (
        "/data/projects/<project_id>/concept-folders",
        ProjectConceptFoldersResource,
    ),
    ("/data/concept-folders/<concept_folder_id>", ConceptFolderResource),
    (
        "/actions/projects/<project_id>/move-concepts",
        MoveConceptsResource,
    ),
]


blueprint = Blueprint("concepts", "concepts")
api = configure_api_from_blueprint(blueprint, routes)
