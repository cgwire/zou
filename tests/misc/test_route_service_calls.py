import ast
import importlib
import pathlib
import unittest

BLUEPRINTS = pathlib.Path(__file__).parents[2] / "zou" / "app" / "blueprints"

# Calls that are already broken. Each one answers 500 the moment its branch
# is reached, and each is a name that does not exist rather than a bug in
# the code around it. They are listed so a new one fails this test instead
# of joining them silently.
KNOWN_BROKEN = {
    (
        "departments/resources.py",
        "departments_service",
        "get_softwares_for_department",
    ),
    ("edits/resources.py", "edits_service", "get_episode"),
    ("edits/resources.py", "tasks_service", "get_edit_tasks_for_episode"),
    ("projects/resources.py", "user_service", "get_project_by_name"),
    ("tasks/resources.py", "persons_service", "get"),
}


def collect_service_calls():
    """
    Every <something>_service.<name>() written in a blueprint, with the file
    it sits in. Only module level attribute calls are considered, which is
    how resources reach the services.
    """
    calls = set()
    for path in sorted(BLUEPRINTS.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            base = function.value
            if not isinstance(base, ast.Name):
                continue
            if not base.id.endswith("_service"):
                continue
            relative = str(path.relative_to(BLUEPRINTS))
            calls.add((relative, base.id, function.attr))
    return calls


class RouteServiceCallsTestCase(unittest.TestCase):
    """
    A resource calling a service function that does not exist raises
    AttributeError at request time, so the route answers 500 for everyone.
    Nothing else catches it: the name is only resolved when the branch runs,
    and the branches this hits are the ones no test walks.
    """

    def test_every_service_call_resolves(self):
        broken = []
        for relative, module_name, attribute in sorted(
            collect_service_calls()
        ):
            try:
                module = importlib.import_module(
                    f"zou.app.services.{module_name}"
                )
            except ImportError:
                # Not a service module of this repo, a plugin may bring its
                # own; nothing to assert about it here.
                continue
            if hasattr(module, attribute):
                continue
            if (relative, module_name, attribute) in KNOWN_BROKEN:
                continue
            broken.append(f"{relative}: {module_name}.{attribute}")

        self.assertEqual(broken, [], "\n".join(broken))

    def test_known_broken_list_stays_accurate(self):
        """
        The allowlist is debt, not decoration: an entry that got fixed has
        to leave it, otherwise the list stops meaning anything.
        """
        calls = collect_service_calls()
        stale = []
        for entry in sorted(KNOWN_BROKEN):
            relative, module_name, attribute = entry
            if entry not in calls:
                stale.append(f"{relative}: {module_name}.{attribute} is gone")
                continue
            module = importlib.import_module(f"zou.app.services.{module_name}")
            if hasattr(module, attribute):
                stale.append(
                    f"{relative}: {module_name}.{attribute} resolves now"
                )
        self.assertEqual(stale, [], "\n".join(stale))
