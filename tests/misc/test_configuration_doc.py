import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).parents[2]
CONFIG = ROOT / "zou" / "app" / "config.py"
DOC = ROOT / "specs" / "configuration.md"

# Read by the LDAP sync command rather than by config.py, documented in
# its prose.
NOT_IN_CONFIG = {"LDAP_PASSWORD", "LDAP_USER"}


def variables_read_by_config():
    source = CONFIG.read_text()
    return set(
        re.findall(
            r"(?:os\.getenv|envtobool|env_with_semicolon_to_list"
            r'|os\.environ\.get)\(\s*"([A-Z0-9_]+)"',
            source,
        )
    )


def variables_in_the_tables():
    return set(re.findall(r"^\| `([A-Z0-9_]+)` \|", DOC.read_text(), re.M))


class ConfigurationDocTestCase(unittest.TestCase):
    def test_every_variable_read_is_documented(self):
        missing = variables_read_by_config() - variables_in_the_tables()
        self.assertEqual(
            sorted(missing),
            [],
            "Add a row for these variables to specs/configuration.md.",
        )

    def test_every_documented_variable_is_read(self):
        stale = (
            variables_in_the_tables()
            - variables_read_by_config()
            - NOT_IN_CONFIG
        )
        self.assertEqual(
            sorted(stale),
            [],
            "These rows of specs/configuration.md name variables config.py "
            "no longer reads.",
        )
