import unittest

import orjson as json

from tests.base import ApiDBTestCase
from zou.app.exceptions import WrongParameterException
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.utils import query
from zou.app.utils.query import check_criterion_id_format


class GetQueryCriterionsTestCase(unittest.TestCase):
    def test_get_query_criterions(self):
        request = type("test", (object,), {})()
        request.args = {"page": "1", "name": "Test", "project_id": "1234"}
        criterions = query.get_query_criterions_from_request(request)
        self.assertDictEqual(
            criterions, {"name": "Test", "project_id": "1234"}
        )


class CheckCriterionIdFormatTestCase(unittest.TestCase):
    valid_id = "a24a6ea4-ce75-4665-a070-57453082c25e"

    def test_valid_ids_pass(self):
        criterions = {
            "id": self.valid_id,
            "project_id": self.valid_id,
            "episode_id": self.valid_id,
        }
        self.assertIsNone(check_criterion_id_format(criterions))

    def test_missing_ids_pass(self):
        self.assertIsNone(check_criterion_id_format({"name": "foo"}))

    def test_invalid_id_raises(self):
        for field in ("id", "project_id", "episode_id"):
            with self.assertRaises(WrongParameterException):
                check_criterion_id_format({field: "not-a-uuid"})

    def test_trailing_characters_raise(self):
        for field in ("id", "project_id", "episode_id"):
            with self.assertRaises(WrongParameterException):
                check_criterion_id_format({field: f"{self.valid_id}\n"})

    def test_episode_id_sentinels_pass(self):
        for sentinel in ("all", "main"):
            self.assertIsNone(
                check_criterion_id_format({"episode_id": sentinel})
            )

    def test_sentinels_not_allowed_for_other_fields(self):
        for field in ("id", "project_id"):
            with self.assertRaises(WrongParameterException):
                check_criterion_id_format({field: "all"})

    def test_only_listed_fields_are_checked(self):
        self.assertIsNone(
            check_criterion_id_format(
                {"episode_id": "not-a-uuid"}, ["id", "project_id"]
            )
        )


class ApplyCriterionsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_project_closed()
        self.generate_fixture_project_standard()

    def get_project_ids(self, criterions):
        db_query = query.apply_criterions_to_db_query(
            Project, Project.query, criterions
        )
        return {str(project.id) for project in db_query.all()}

    def test_json_list_value_filters_with_in(self):
        ids = [str(self.project.id), str(self.project_standard.id)]
        self.assertEqual(
            self.get_project_ids({"id": json.dumps(ids).decode()}), set(ids)
        )

    def test_many_to_many_key_filters_on_the_linked_id(self):
        person = self.generate_fixture_person()
        self.project.team.append(person)
        self.project.save()
        self.assertEqual(
            self.get_project_ids({"team": str(person.id)}),
            {str(self.project.id)},
        )

    def test_column_without_python_type_is_cast(self):
        person = self.generate_fixture_person()
        person.update({"locale": "fr_FR"})
        db_query = query.apply_criterions_to_db_query(
            Person, Person.query, {"locale": "fr_FR"}
        )
        self.assertEqual([entry.id for entry in db_query.all()], [person.id])

    def test_page_after_the_last_one_keeps_the_real_total(self):
        result = query.get_paginated_results(Project.query, page=5, limit=1)
        self.assertEqual(result["data"], [])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["nb_pages"], 3)

    def test_sort_by_a_column_other_than_a_date_is_ascending(self):
        db_query = query.apply_sort_by(Project, Project.query, "name")
        self.assertEqual(
            [project.name for project in db_query.all()],
            ["Big Buck Bunny", "Cosmos Landromat", "Old Project"],
        )
