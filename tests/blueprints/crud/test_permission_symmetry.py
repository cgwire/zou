import ast
import pathlib
import unittest

CRUD_PATH = (
    pathlib.Path(__file__).parents[2] / "zou" / "app" / "blueprints" / "crud"
)

# Names whose presence in a resource means it narrows what the caller reads,
# either by refusing access or by dropping fields from the payload.
RESTRICTORS = [
    "check_project_access",
    "check_entity_access",
    "block_access_to_vendor",
    "has_client_permissions",
    "serialize_safe",
    "present_minimal",
    "ignored_attrs",
]

# Hooks through which a collection resource can narrow the same way without
# naming a restrictor itself.
COMPENSATIONS = [
    "add_project_permission_filter",
    "all_entries",
    "serialize_list",
    "serialize_instance",
]


def names_used(node):
    """
    Return the called functions and keyword argument names appearing under
    the given node, which is enough to spot a restrictor whether it is
    called (check_project_access()) or passed (ignored_attrs=).
    """
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            function = child.func
            if isinstance(function, ast.Attribute):
                names.add(function.attr)
            elif isinstance(function, ast.Name):
                names.add(function.id)
            for keyword in child.keywords:
                if keyword.arg is not None:
                    names.add(keyword.arg)
    return names


def collect_resources():
    """
    Map (module, model) to the collection and single resources it declares,
    each with its method names and the names those methods use.
    """
    resources = {}
    for path in sorted(CRUD_PATH.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "BaseModelsResource" in bases:
                kind = "collection"
            elif "BaseModelResource" in bases:
                kind = "single"
            else:
                continue
            model = None
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and len(child.args) == 2
                    and isinstance(child.args[1], ast.Name)
                ):
                    model = child.args[1].id
            methods = {
                method.name: names_used(method)
                for method in node.body
                if isinstance(method, ast.FunctionDef)
            }
            resources.setdefault((path.name, model), {})[kind] = (
                node.name,
                methods,
            )
    return resources


class CrudPermissionSymmetryTestCase(unittest.TestCase):
    """
    A model exposed under /data has two CRUD resources, one for the
    collection and one for a single instance, and their read permissions are
    written independently. Every leak of that shape found so far came from a
    collection that opened read without repeating what its single sibling
    restricts: /data/playlists listed the playlists of every project while
    /data/playlists/<id> called check_project_access, and
    /data/organisations returned the chat tokens that
    /data/organisations/<id> masked. Read the two side by side and require
    the collection to narrow whenever the single resource does.
    """

    def test_open_collections_narrow_like_their_single_sibling(self):
        offenders = []
        for (module, model), sides in sorted(collect_resources().items()):
            if "collection" not in sides or "single" not in sides:
                continue
            collection_name, collection_methods = sides["collection"]
            _, single_methods = sides["single"]

            # A collection left on the admin-only default is stricter than
            # anything its sibling can require, so it is never at fault.
            read_check = collection_methods.get("check_read_permissions")
            if read_check is None or "check_admin_permissions" in read_check:
                continue

            if any(hook in collection_methods for hook in COMPENSATIONS):
                continue

            single_names = set().union(*single_methods.values())
            collection_names = set().union(*collection_methods.values())
            missing = [
                restrictor
                for restrictor in RESTRICTORS
                if restrictor in single_names
                and restrictor not in collection_names
            ]
            if missing:
                offenders.append(
                    f"{module}: {collection_name} opens read but does not "
                    f"apply {', '.join(missing)} the way its single "
                    f"resource does, and overrides none of "
                    f"{', '.join(COMPENSATIONS)}"
                )

        self.assertEqual(offenders, [], "\n" + "\n".join(offenders))
