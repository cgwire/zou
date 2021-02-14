"""
This module is named source instead of import because import is a Python
keyword.
"""
from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from .csv.assets import AssetsCsvExport
from .csv.casting import CastingCsvExport
from .csv.projects import ProjectsCsvExport
from .csv.shots import ShotsCsvExport
from .csv.persons import PersonsCsvExport
from .csv.playlists import PlaylistCsvExport
from .csv.task_types import TaskTypesCsvExport
from .csv.tasks import TasksCsvExport
from .csv.time_spents import TimeSpentsCsvExport

routes = [
    ("/export/csv/projects/<project_id>/assets.csv", AssetsCsvExport),
    ("/export/csv/projects/<project_id>/shots.csv", ShotsCsvExport),
    ("/export/csv/projects/<project_id>/casting.csv", CastingCsvExport),
    ("/export/csv/playlists/<playlist_id>", PlaylistCsvExport),
    ("/export/csv/persons.csv", PersonsCsvExport),
    ("/export/csv/projects.csv", ProjectsCsvExport),
    ("/export/csv/tasks.csv", TasksCsvExport),
    ("/export/csv/time-spents.csv", TimeSpentsCsvExport),
    ("/export/csv/task-types.csv", TaskTypesCsvExport),
]

blueprint = Blueprint("export", "export")
api = configure_api_from_blueprint(blueprint, routes)
