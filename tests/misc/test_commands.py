import datetime
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from click.testing import CliRunner

from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.services import preview_files_service
from zou.app.stores import auth_tokens_store, file_store
from zou.app.utils import commands
from zou.app.models.entity_type import EntityType
from zou.app.models.task_type import TaskType
from zou.cli import cli


def totimestamp(dt, epoch=datetime.datetime(1970, 1, 1)):
    td = dt - epoch
    return (td.microseconds + (td.seconds + td.days * 86400) * 10**6) / 10**6


class CommandsTestCase(ApiDBTestCase):
    def setUp(self):
        super(CommandsTestCase, self).setUp()
        self.store = auth_tokens_store
        self.store.clear()

    def test_clean_auth_tokens_revoked(self):
        self.store.add("testkey", "false")
        self.store.add("testkey2", "false")
        self.assertEqual(len(self.store.keys()), 2)
        self.store.add("testkey2", "true")
        commands.clean_auth_tokens()
        self.assertEqual(len(self.store.keys()), 1)
        self.assertEqual(self.store.keys()[0], "testkey")

    def test_init_data(self):
        commands.init_data()
        task_types = TaskType.get_all()
        entity_types = EntityType.get_all()
        self.assertEqual(len(task_types), 13)
        self.assertEqual(len(entity_types), 8)

    def test_init_data_creates_concept_task_type(self):
        commands.init_data()
        concept_task_types = TaskType.get_all_by(for_entity="Concept")
        self.assertEqual(len(concept_task_types), 1)
        self.assertEqual(concept_task_types[0].name, "Concept")


class DisableTwoFactorAuthenticationCommandTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person_id = str(self.person.id)
        self.person_email = self.person.email
        self.person_desktop_login = self.person.desktop_login
        self.runner = CliRunner()

    def enable_totp(self):
        self.person.update(
            {"totp_enabled": True, "totp_secret": "JBSWY3DPEHPK3PXP"}
        )

    def test_disable_by_email(self):
        self.enable_totp()
        result = self.runner.invoke(
            cli,
            ["disable-two-factor-authentication", self.person_email],
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Two factor authentication disabled", result.output)
        person = Person.get(self.person_id)
        self.assertFalse(person.totp_enabled)
        self.assertIsNone(person.totp_secret)

    def test_disable_by_desktop_login(self):
        self.enable_totp()
        result = self.runner.invoke(
            cli,
            [
                "disable-two-factor-authentication",
                self.person_desktop_login,
            ],
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Two factor authentication disabled", result.output)
        person = Person.get(self.person_id)
        self.assertFalse(person.totp_enabled)
        self.assertIsNone(person.totp_secret)

    def test_disable_person_not_found(self):
        result = self.runner.invoke(
            cli,
            [
                "disable-two-factor-authentication",
                "nonexistent@example.com",
            ],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("not listed in database", result.output)

    def test_disable_two_factor_not_enabled(self):
        result = self.runner.invoke(
            cli,
            ["disable-two-factor-authentication", self.person_email],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("can't be disabled", result.output)


class RenormalizeMoviePreviewFilesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file(status="broken")
        self.preview_file_id = str(self.preview_file.id)

    def _run_renormalize(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            commands.renormalize_movie_preview_files(
                preview_file_id=self.preview_file_id,
                all_broken=True,
            )
        return buf.getvalue()

    def test_skips_when_source_missing_in_storage(self):
        with patch.object(
            file_store, "exists_movie", return_value=False
        ), patch.object(
            preview_files_service, "prepare_and_store_movie"
        ) as mock_prepare:
            output = self._run_renormalize()

        self.assertIn("Source movie missing in storage", output)
        mock_prepare.assert_not_called()

    def test_skips_when_local_copy_missing(self):
        missing_path = "/tmp/zou-test-source-does-not-exist.mp4"
        with patch.object(
            file_store, "exists_movie", return_value=True
        ), patch.object(
            file_store,
            "get_local_movie_path",
            return_value=missing_path,
        ), patch(
            "zou.app.utils.commands.shutil.copyfile"
        ), patch(
            "zou.app.utils.commands.config.FS_BACKEND", "local"
        ), patch(
            "zou.app.utils.commands.config.ENABLE_JOB_QUEUE", False
        ), patch.object(
            preview_files_service, "prepare_and_store_movie"
        ) as mock_prepare:
            output = self._run_renormalize()

        self.assertIn("Local copy of source movie is missing or", output)
        mock_prepare.assert_not_called()
