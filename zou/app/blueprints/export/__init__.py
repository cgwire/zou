"""
This module is named source instead of import because import is a Python
keyword.
"""
from zou.app.utils.api import create_blueprint_for_api

from .csv.assets import AssetsCsvExport
from .csv.casting import CastingCsvExport
from .csv.projects import ProjectsCsvExport
from .csv.shots import ShotsCsvExport
from .csv.persons import PersonsCsvExport
from .csv.playlists import PlaylistCsvExport
from .csv.task_types import TaskTypesCsvExport
from .csv.tasks import TasksCsvExport
from .csv.time_spents import TimeSpentsCsvExport
from .csv.edits import EditsCsvExport

routes = [
    ("/export/csv/projects/<uuid:project_id>/assets.csv", AssetsCsvExport),
    ("/export/csv/projects/<uuid:project_id>/shots.csv", ShotsCsvExport),
    ("/export/csv/projects/<uuid:project_id>/casting.csv", CastingCsvExport),
    ("/export/csv/projects/<uuid:project_id>/edits.csv", EditsCsvExport),
    ("/export/csv/playlists/<uuid:playlist_id>", PlaylistCsvExport),
    ("/export/csv/persons.csv", PersonsCsvExport),
    ("/export/csv/projects.csv", ProjectsCsvExport),
    ("/export/csv/tasks.csv", TasksCsvExport),
    ("/export/csv/time-spents.csv", TimeSpentsCsvExport),
    ("/export/csv/task-types.csv", TaskTypesCsvExport),
]

blueprint = create_blueprint_for_api("export", routes)
