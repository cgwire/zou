import ast
import os
import pathlib
import subprocess
import sys
import unittest

from concurrent.futures import ThreadPoolExecutor

SERVICES = pathlib.Path(__file__).parents[2] / "zou" / "app" / "services"


def deferred_imports():

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


def import_graph():
    """
    Map each service to the services it imports, wherever the import is.
    """
    graph = {}
    for path in sorted(SERVICES.glob("*_service.py")):
        targets = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "zou.app.services":
                    targets |= {alias.name for alias in node.names}
                elif node.module.startswith("zou.app.services."):
                    targets.add(node.module.split(".")[-1])
        graph[path.stem] = targets - {path.stem}
    return graph


def find_cycle(graph):
    """
    Return one import cycle as a list of services, or None.
    """
    state = {}

    def visit(service, path):
        state[service] = "open"
        for target in sorted(graph.get(service, ())):
            if state.get(target) == "open":
                return path[path.index(target) :] + [target]
            if target not in state:
                cycle = visit(target, path + [target])
                if cycle:
                    return cycle
        state[service] = "done"
        return None

    for service in sorted(graph):
        if service not in state:
            cycle = visit(service, [service])
            if cycle:
                return cycle
    return None


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

    def test_no_deferred_service_import(self):
        self.assertEqual(
            deferred_imports(),
            set(),
            "An import inside a function hides a cycle: import it at module "
            "level and move the dependency down a layer if that loops.",
        )

    def test_no_import_cycle_between_services(self):
        """
        The services form layers: a service only imports the ones below
        it. A cycle makes the placement of every function in it arbitrary,
        so the first one that comes back fails here with its path.
        """
        cycle = find_cycle(import_graph())
        self.assertIsNone(
            cycle,
            f"Import cycle: {' -> '.join(cycle or [])}. Move the function "
            "that closes it to the lower service.",
        )
