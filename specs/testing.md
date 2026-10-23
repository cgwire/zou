# Testing

## Setup

```bash
# Activate virtualenv
source ~/.virtualenvs/zou/bin/activate

# Run tests (requires PostgreSQL on localhost:5432)
DB_DATABASE=zoudb-test py.test tests/path/to/test_file.py -v
```

## Test base class

All tests inherit from `ApiDBTestCase` (`tests/base.py`), which provides:

- **Schema management**: `conftest.py` creates tables once per session; `setUpClass` truncates between test classes
- **Transaction isolation**: Each test runs in a transaction that is rolled back in a cleanup registered by `setUp`, which unittest also runs when `setUp` fails
- **Admin login**: `setUp` creates an admin user and logs in automatically
- **HTTP helpers**: `get()`, `post()`, `put()`, `delete()` send requests and assert status codes
- **404 helpers**: `get_404()`, `put_404()`, `delete_404()` assert 404 responses
- **`get_first(path)`**: GET list and return first element
- **Fixture generators**: `generate_fixture_project()`, `generate_fixture_asset()`, `generate_fixture_task()`, etc.
- **`generate_data(Model, N, **kwargs)`**: Uses mixer to create N random instances
- **`generate_base_context()`**: Creates project status, project, asset type, department, task type, task status

## Test organization

```
tests/
├── base.py              # ApiDBTestCase and all fixture generators
├── conftest.py          # Schema creation/teardown, bcrypt bypass (pytest hooks)
├── blueprints/<name>/   # Route tests, one directory per blueprint (crud, auth, shots...)
├── services/            # Service function tests
├── utils/               # Utility function tests
├── stores/              # Redis and file store tests
├── cli/                 # CLI command tests
├── remote/              # Nomad runner tests
├── misc/                # Static guards (service calls, imports, permission symmetry)
└── fixtures/            # CSV, EDL, Shotgun, picture and video fixtures
```

## What conftest.py does for you

- **Isolated preview store**: `PREVIEW_FOLDER` is forced to a temporary
  directory before the app loads, so route tests never write into a
  development store.
- **Fast passwords**: bcrypt runs with 4 rounds and password verification
  is bypassed during login. A test that asserts on the verification itself
  opts out with `pytestmark = pytest.mark.real_bcrypt`.
- **Integration marker**: tests needing a running Meilisearch are marked
  `integration` and skipped when the indexer is not reachable.
- **No SQLite fallback**: the suite needs a PostgreSQL instance; the CI
  starts one per job.

## CRUD model test pattern

Five tests per model: GET list, GET single (+404), POST, PUT (+404), DELETE (+404).

```python
from tests.base import ApiDBTestCase
from zou.app.models.department import Department
from zou.app.utils import fields

class DepartmentTestCase(ApiDBTestCase):
    def setUp(self):
        super(DepartmentTestCase, self).setUp()
        self.generate_data(Department, 3)

    def test_get_departments(self):
        departments = self.get("data/departments")
        self.assertEqual(len(departments), 3)

    def test_get_department(self):
        department = self.get_first("data/departments")
        department_again = self.get("data/departments/%s" % department["id"])
        self.assertEqual(department, department_again)
        self.get_404("data/departments/%s" % fields.gen_uuid())

    def test_create_department(self):
        data = {"name": "open", "color": "#000000"}
        self.department = self.post("data/departments", data)
        self.assertIsNotNone(self.department["id"])
        departments = self.get("data/departments")
        self.assertEqual(len(departments), 4)

    def test_update_department(self):
        department = self.get_first("data/departments")
        data = {"color": "#FFFFFF"}
        self.put("data/departments/%s" % department["id"], data)
        department_again = self.get("data/departments/%s" % department["id"])
        self.assertEqual(data["color"], department_again["color"])
        self.put_404("data/departments/%s" % fields.gen_uuid(), data)

    def test_delete_department(self):
        departments = self.get("data/departments")
        self.assertEqual(len(departments), 3)
        department = departments[0]
        self.delete("data/departments/%s" % department["id"])
        departments = self.get("data/departments")
        self.assertEqual(len(departments), 2)
        self.delete_404("data/departments/%s" % fields.gen_uuid())
```

## Models with FK dependencies

For models with required foreign keys, generate fixtures before data:

```python
def setUp(self):
    super().setUp()
    self.generate_base_context()         # project, task_type, etc.
    self.generate_data(
        Milestone, 3,
        project_id=self.project.id,      # pass FK values explicitly
        task_type_id=self.task_type.id,
    )
```

For models where mixer can't generate valid data (e.g., check constraints), create instances manually via `Model.create()` or `self.post()`.

## Service test pattern

```python
from tests.base import ApiDBTestCase
from zou.app.services import my_service
from zou.app.exceptions import MyNotFoundException

class MyServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        # ... setup required data

    def test_get_something(self):
        result = my_service.get_something(self.project.id)
        self.assertEqual(len(result), expected)

    def test_get_something_not_found(self):
        self.assertRaises(
            MyNotFoundException,
            my_service.get_something,
            "nonexistent-id",
        )
```
