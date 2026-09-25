import os
import pathlib
import subprocess
import sys
import unittest

from concurrent.futures import ThreadPoolExecutor

SERVICES = pathlib.Path(__file__).parents[2] / "zou" / "app" / "services"

# Imports written inside a function body. Each one is a service reaching up
# into a service that imports it back; the list can only shrink.
KNOWN_DEFERRED_IMPORTS = {
    ("deletion_service", "remove_task", "tasks_service"),
    ("deletion_service", "remove_preview_file", "tasks_service"),
    ("deletion_service", "remove_attachment_file", "comments_service"),
    ("deletion_service", "remove_entities", "assets_service"),
    ("deletion_service", "remove_entities", "concepts_service"),
    ("deletion_service", "remove_entities", "edits_service"),
    ("deletion_service", "remove_entities", "entities_service"),
    ("deletion_service", "remove_entities", "shots_service"),
    ("deletion_service", "remove_project", "playlists_service"),
    ("deletion_service", "remove_episode", "shots_service"),
    ("deletion_service", "remove_episode", "assets_service"),
    ("deletion_service", "remove_episode", "tasks_service"),
}


def deferred_imports():
    import ast

    found = set()
    for path in sorted(SERVICES.glob("*_service.py")):
        tree = ast.parse(path.read_text())
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ""
                if not module.startswith("zou.app.services"):
                    continue
                for alias in node.names:
                    target = (
                        alias.name
                        if module == "zou.app.services"
                        else module.split(".")[-1]
                    )
                    found.add((path.stem, function.name, target))
    return found


class ServiceImportsTestCase(unittest.TestCase):
    def test_every_service_imports_on_its_own(self):
        """
        The application imports the services in one order, which hides an
        import cycle that only bites from another entry point (a CLI
        command, a job worker, a plugin). Each module is imported first in
        a fresh interpreter.
        """
        env = {**os.environ, "DEBUG": "1", "MAIL_ENABLED": "False"}

        def import_alone(path):
            result = subprocess.run(
                [sys.executable, "-c", f"import zou.app.services.{path.stem}"],
                capture_output=True,
                text=True,
                env=env,
            )
            return path.stem, result.returncode, result.stderr.strip()[-600:]

        services = sorted(SERVICES.glob("*_service.py"))
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
            for name, returncode, stderr in pool.map(import_alone, services):
                with self.subTest(service=name):
                    self.assertEqual(returncode, 0, stderr)

    def test_no_new_deferred_service_import(self):
        found = deferred_imports()
        self.assertEqual(
            found - KNOWN_DEFERRED_IMPORTS,
            set(),
            "A new import inside a function: either import it at module "
            "level, or move the dependency down a layer.",
        )
        for entry in KNOWN_DEFERRED_IMPORTS - found:
            self.fail(f"{entry} was fixed: drop it from the known list")
