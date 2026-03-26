import copy
import os
import unittest
from unittest.mock import patch, MagicMock

import requests
from click.testing import CliRunner

# Ensure ADMIN_TOKEN is set before zou.cli is imported so the command
# is registered.
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")

from zou.cli import cli  # noqa: E402

TEST_TOKEN = "test-admin-token"

# Env vars as seen by the CLI process during tests.
CLI_ENV = {
    "ADMIN_TOKEN": TEST_TOKEN,
    "USER_LIMIT": "100",
    "DEFAULT_TIMEZONE": "Europe/Paris",
    "DEFAULT_LOCALE": "en_US",
    "JOB_QUEUE_NOMAD_HOST": "zou-nomad-01.zou",
    "JOB_QUEUE_NOMAD_NORMALIZE_JOB": "",
    "JOB_QUEUE_NOMAD_PLAYLIST_JOB": "zou-playlist",
}

# API response when everything is in sync with CLI_ENV.
API_RESPONSE_SYNCED = {
    "user_limit": {"env": 100, "redis": "100"},
    "default_timezone": {"env": "Europe/Paris", "redis": "Europe/Paris"},
    "default_locale": {"env": "en_US", "redis": "en_US"},
    "nomad_host": {"env": "zou-nomad-01.zou", "redis": "zou-nomad-01.zou"},
    "nomad_normalize_job": {"env": "", "redis": ""},
    "nomad_playlist_job": {"env": "zou-playlist", "redis": "zou-playlist"},
    "active_users": 42,
}

# API response where redis has a stale value for user_limit.
API_RESPONSE_DESYNC = {
    "user_limit": {"env": 200, "redis": "200"},
    "default_timezone": {"env": "Europe/Paris", "redis": "Europe/Paris"},
    "default_locale": {"env": "en_US", "redis": "en_US"},
    "nomad_host": {"env": "zou-nomad-01.zou", "redis": "zou-nomad-01.zou"},
    "nomad_normalize_job": {"env": "", "redis": ""},
    "nomad_playlist_job": {"env": "zou-playlist", "redis": "zou-playlist"},
    "active_users": 10,
}


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = copy.deepcopy(json_data)
    resp.text = str(json_data)
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


class GetCurrentConfigCommandTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_exit_0_when_synced(self, mock_get):
        mock_get.return_value = _mock_response(API_RESPONSE_SYNCED)

        result = self.runner.invoke(cli, ["get-current-config"], color=True)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Config check", result.output)
        self.assertIn("user_limit", result.output)
        self.assertIn("Active users: 42", result.output)
        self.assertNotIn("✗", result.output)

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_exit_1_when_desync(self, mock_get):
        """env-cli has USER_LIMIT=100 but redis has 200 → mismatch."""
        mock_get.return_value = _mock_response(API_RESPONSE_DESYNC)

        result = self.runner.invoke(cli, ["get-current-config"], color=True)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("✗", result.output)
        self.assertIn("out of sync", result.output)

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_shows_three_columns(self, mock_get):
        mock_get.return_value = _mock_response(API_RESPONSE_SYNCED)

        result = self.runner.invoke(cli, ["get-current-config"], color=True)
        self.assertIn("Env (CLI)", result.output)
        self.assertIn("Redis", result.output)
        self.assertIn("Env (API)", result.output)

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_null_redis_shows_empty_symbol(self, mock_get):
        data = copy.deepcopy(API_RESPONSE_SYNCED)
        data["nomad_normalize_job"]["redis"] = None
        mock_get.return_value = _mock_response(data)

        result = self.runner.invoke(cli, ["get-current-config"], color=True)
        self.assertIn("∅", result.output)
        # env-cli is "" but redis is "∅" → mismatch
        self.assertNotEqual(result.exit_code, 0)

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_connection_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError()

        result = self.runner.invoke(cli, ["get-current-config"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Cannot connect", result.output)

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = _mock_response({}, status_code=403)

        result = self.runner.invoke(cli, ["get-current-config"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error 403", result.output)

    @patch.dict(os.environ, CLI_ENV, clear=False)
    @patch("requests.get")
    def test_custom_host_option(self, mock_get):
        mock_get.return_value = _mock_response(API_RESPONSE_SYNCED)

        result = self.runner.invoke(
            cli,
            ["get-current-config", "--host", "http://myhost:8080"],
        )
        self.assertEqual(result.exit_code, 0)
        mock_get.assert_called_once_with(
            "http://myhost:8080/admin/config/check",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
