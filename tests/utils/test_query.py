import unittest

from zou.app.utils.query import check_criterion_id_format
from zou.app.services.exception import WrongParameterException


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
