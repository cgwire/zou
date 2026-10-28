import math

from flask_jwt_extended import jwt_required
from slugify import slugify

from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.services import (
    assets_service,
    edits_service,
    organisation_service,
    permissions_service,
    shots_service,
    task_types_service,
    tasks_service,
)
from zou.app.utils import date_helpers
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


def snap_to_whole(value):
    """
    Return the whole number a float result lands a hair off, the value
    otherwise: 2.05 hours make 122.99999999999999 minutes, and 22.8 hours
    at 7.6 hours a day make 3.0000000000000004 days.
    """
    whole = round(value)
    return whole if abs(value - whole) < 1e-6 else value


def parse_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(value)
    return number


DATE_FORMAT = (date_helpers.get_date_from_string, "YYYY-MM-DD")
NUMBER_FORMAT = (parse_number, "a number with a dot, such as 1.5")
WHOLE_NUMBER_FORMAT = (int, "a whole number")


class TaskTypeEstimationsCsvImportResource(BaseCsvProjectImportResource):

    def check_permissions(self, project_id, task_type, episode_id=None):
        return permissions_service.check_supervisor_project_task_type_access(
            project_id, task_type["id"]
        )

    # The task type is read before the base class checks the session.
    @jwt_required()
    @swag_from(SPECS["TaskTypeEstimationsCsvImportResource_post"])
    def post(self, project_id, task_type_id, episode_id=None):
        """
        Import task type estimations csv
        """
        task_type = task_types_service.get_task_type(task_type_id)
        return super().post(project_id, task_type, episode_id)

    def prepare_import(self, project_id, task_type, episode_id=None):
        self.organisation = organisation_service.get_organisation()
        self.for_entity = task_type["for_entity"]
        self.own_episode_id = None
        self.candidates = {}
        self.tasks_map = {}
        self.entity_label = f"{self.for_entity.lower()}s"
        self.no_episode_label = (
            "main pack" if self.for_entity == "Asset" else "no episode"
        )
        episodes = shots_service.get_episodes({"project_id": project_id})
        self.episode_names = {
            episode["id"]: episode["name"] for episode in episodes
        }
        self.descriptor_fields = {
            name: descriptor
            for name, descriptor in self.get_descriptor_field_map(
                project_id, "Task"
            ).items()
            if descriptor["task_type_id"] == task_type["id"]
        }

        if self.for_entity == "Asset":
            self.add_asset_candidates(project_id, episode_id)
        elif self.for_entity == "Shot":
            self.add_shot_candidates(project_id, episode_id)
        elif self.for_entity == "Episode":
            # The route episode is ignored: older Kitsu versions post the
            # import of an episode task type under the current episode.
            for episode in episodes:
                self.add_candidate(episode, "", episode["id"])
        elif self.for_entity in ["Sequence", "Edit"]:
            self.add_episode_child_candidates(project_id, episode_id)

        for task in tasks_service.get_tasks_for_project_and_task_type(
            project_id, task_type["id"]
        ):
            self.tasks_map[task["entity_id"]] = task

    def add_asset_candidates(self, project_id, episode_id):
        asset_type_names = {
            asset_type["id"]: asset_type["name"]
            for asset_type in assets_service.get_asset_types_for_project(
                project_id
            )
        }
        criterions = {"project_id": project_id}
        if episode_id not in [None, "main", "all"]:
            # The assets of the episode and the ones cast into it, as the
            # task type page of the episode lists them. get_assets compares
            # the id uncast: a malformed one would fail as a 500.
            self.check_id_parameter(episode_id)
            criterions["episode_id"] = episode_id
            self.own_episode_id = episode_id
        assets = assets_service.get_assets(criterions)
        if episode_id == "main":
            # A None criterion would compile to "= NULL" and match nothing.
            assets = [asset for asset in assets if asset["source_id"] is None]
        for asset in assets:
            self.add_candidate(
                asset,
                asset_type_names[asset["entity_type_id"]],
                asset["source_id"],
            )

    def add_shot_candidates(self, project_id, episode_id):
        criterions = {"project_id": project_id}
        if episode_id is not None and episode_id not in ["main", "all"]:
            criterions["parent_id"] = episode_id
        sequences = shots_service.get_sequences(criterions)
        if episode_id == "main":
            # A None criterion would compile to "= NULL" and match nothing.
            sequences = [
                sequence
                for sequence in sequences
                if sequence["parent_id"] is None
            ]
        sequences = {sequence["id"]: sequence for sequence in sequences}
        for shot in shots_service.get_shots({"project_id": project_id}):
            sequence = sequences.get(shot["parent_id"])
            if sequence is not None:
                self.add_candidate(
                    shot, sequence["name"], sequence["parent_id"]
                )

    def add_episode_child_candidates(self, project_id, episode_id):
        """
        Register the sequences or the edits, under the name of their
        episode as parent, an empty one when they have none.
        """
        criterions = {"project_id": project_id}
        if episode_id not in [None, "main", "all"]:
            criterions["parent_id"] = episode_id
        if self.for_entity == "Sequence":
            entities = shots_service.get_sequences(criterions)
        else:
            entities = edits_service.get_edits(criterions)
        if episode_id == "main":
            # A None criterion would compile to "= NULL" and match nothing.
            entities = [
                entity for entity in entities if entity["parent_id"] is None
            ]
        for entity in entities:
            self.add_candidate(
                entity,
                self.episode_names.get(entity["parent_id"], ""),
                entity["parent_id"],
            )

    def add_candidate(self, entity, parent_name, episode_id):
        """
        Register an entity a row can name, under the slug of its name. The
        episode id (the source of an asset) is kept to tell candidates
        apart.
        """
        self.candidates.setdefault(slugify(entity["name"]), []).append(
            {
                "id": entity["id"],
                "name": entity["name"],
                "parent_name": parent_name,
                "parent_key": slugify(parent_name),
                "episode_id": episode_id,
                # Kitsu hides both from the task type page and its export.
                "canceled": bool(entity.get("canceled"))
                or entity.get("status") == "canceled",
            }
        )

    def find_entity(self, parent, name):
        """
        Return the candidate a row names, None when there is none. Parent
        and name are compared apart, each through its slug, so that case,
        spaces and accents do not matter. When several candidates share the
        slugs, the ones named exactly like the row win, then the ones not
        canceled, then, in an episode, its own assets over the ones cast
        into it. More than one left refuses the row.
        """
        if name == "":
            return None
        parent_ignored = self.is_parent_ignored(parent)
        parent_key = slugify(parent)
        candidates = [
            candidate
            for candidate in self.candidates.get(slugify(name), [])
            if parent_ignored or candidate["parent_key"] == parent_key
        ]
        if len(candidates) > 1:
            candidates = [
                candidate
                for candidate in candidates
                if self.is_exact_match(candidate, parent, name)
            ] or candidates
        if len(candidates) > 1:
            candidates = [
                candidate
                for candidate in candidates
                if not candidate["canceled"]
            ] or candidates
        if len(candidates) > 1 and self.own_episode_id is not None:
            # The import matched the assets of the episode only before
            # matching the cast ones: their rows must keep importing.
            candidates = [
                candidate
                for candidate in candidates
                if candidate["episode_id"] == self.own_episode_id
            ] or candidates
        if len(candidates) > 1:
            raise RowException(
                f"{self.describe_row(parent, name)} matches "
                f"{len(candidates)} {self.entity_label}"
                f"{self.describe_episodes(candidates)}"
            )
        return candidates[0] if candidates else None

    def describe_row(self, parent, name):
        if self.is_parent_ignored(parent):
            return f"Entity '{name}'"
        return f"Entity '{name}' with parent '{parent}'"

    def describe_episodes(self, candidates):
        if not self.episode_names or self.for_entity == "Episode":
            return ""
        labels = sorted(
            {
                self.episode_names.get(
                    candidate["episode_id"], self.no_episode_label
                )
                for candidate in candidates
            }
        )
        if len(labels) == 1:
            return f", all in {labels[0]}"
        return f", in episodes {', '.join(labels[:-1])} and {labels[-1]}"

    def is_parent_ignored(self, parent):
        """
        Episode rows have no parent, and a sequence or an edit row with
        an empty Parent names any episode in scope.
        """
        return self.for_entity == "Episode" or (
            self.for_entity in ["Sequence", "Edit"] and parent == ""
        )

    def is_exact_match(self, candidate, parent, name):
        return candidate["name"].strip() == name and (
            self.is_parent_ignored(parent)
            or candidate["parent_name"].strip() == parent
        )

    def import_row(self, row, project_id, task_type, episode_id=None):
        # A column missing from the file raises the KeyError the base class
        # names. Only asset and shot rows need a parent.
        if self.for_entity in ["Asset", "Shot"]:
            parent = (row["Parent"] or "").strip()
        else:
            parent = (row.get("Parent") or "").strip()
        name = (row["Entity"] or "").strip()
        entity = self.find_entity(parent, name)
        if entity is None:
            raise RowException(f"{self.describe_row(parent, name)} not found")

        new_data = {}
        estimation = self.read_cell(row, "Estimation", NUMBER_FORMAT)
        if estimation is not None:
            new_data["estimation"] = self.get_estimation_minutes(estimation)

        nb_drawings = self.read_cell(row, "Drawings", WHOLE_NUMBER_FORMAT)
        if nb_drawings is not None:
            new_data["nb_drawings"] = nb_drawings

        start_date = self.read_cell(row, "Start date", DATE_FORMAT)
        if start_date is not None:
            new_data["start_date"] = start_date

        due_date = self.read_cell(row, "Due date", DATE_FORMAT)
        if due_date is not None:
            new_data["due_date"] = due_date
        elif new_data.get("start_date") and new_data.get("estimation"):
            new_data["due_date"] = date_helpers.add_business_days_to_date(
                new_data["start_date"],
                self.get_estimation_days(estimation) - 1,
            )

        difficulty = self.read_cell(row, "Difficulty", WHOLE_NUMBER_FORMAT)
        if difficulty is not None:
            new_data["difficulty"] = difficulty

        task = self.tasks_map.get(entity["id"])
        if task is None:
            raise RowException(
                f"{self.describe_row(parent, name)} "
                f"has no '{task_type['name']}' task"
            )

        # Merge descriptor cells into the task's own metadata instead of
        # replacing it, so columns absent from the CSV are preserved.
        if any(field in row for field in self.descriptor_fields):
            new_data["data"] = self.get_descriptor_values(row, task["data"])

        tasks_service.update_task(task["id"], new_data)

    def read_cell(self, row, column, value_format):
        """
        Return the parsed value of a cell, None when it is empty. A value
        that does not parse is refused with the name of its column and the
        form expected.
        """
        value = (row.get(column) or "").strip()
        if value == "":
            return None
        parse, expected = value_format
        try:
            return parse(value)
        except ValueError:
            raise RowException(
                f"Invalid value in column '{column}': '{value}' "
                f"(expected {expected})"
            )

    def get_estimation_minutes(self, estimation):
        """
        Return in minutes an estimation given in the unit Kitsu shows and
        exports estimations in: hours when the organisation displays
        durations in hours, days otherwise.
        """
        if self.organisation["format_duration_in_hours"]:
            # Unrounded, as Kitsu stores the hours typed in its lists:
            # whole minutes would bring 0.66 hours back as 0.67.
            return snap_to_whole(estimation * 60)
        return round(estimation * self.organisation["hours_by_day"] * 60)

    def get_estimation_days(self, estimation):
        """
        Return in days an estimation given in the unit Kitsu shows and
        exports estimations in.
        """
        if self.organisation["format_duration_in_hours"]:
            return snap_to_whole(
                estimation / self.organisation["hours_by_day"]
            )
        return estimation


class TaskTypeEstimationsEpisodeCsvImportResource(
    TaskTypeEstimationsCsvImportResource
):
    @swag_from(SPECS["TaskTypeEstimationsEpisodeCsvImportResource_post"])
    def post(self, project_id, task_type_id, episode_id):
        """
        Import episode task type estimations csv
        """
        return super().post(project_id, task_type_id, episode_id)
