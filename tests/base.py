import datetime
import unittest
import orjson as json
import os
import ntpath

from mixer.backend.flask import mixer

from tests.fake_stores import seed_fake_stores

# Seeded before the app is built by tests/conftest.py, and again here for
# an import without it (the plugin suites): the stores taken below must
# never be real clients, since setUp flushes them between tests.
seed_fake_stores()

from zou.app import app, config, db
from zou.app.utils import events, fields, fs
from zou.app.services import (
    tasks_service,
)

from zou.app.stores import (
    auth_tokens_store,
    config_store,
    redis_client,
    redis_lock,
)

from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from flask import current_app

from tests.factories.productions import ProductionFactories
from tests.factories.people import PeopleFactories
from tests.factories.entities import EntityFactories
from tests.factories.tasks import TaskFactories
from tests.factories.files import FileFactories
from tests.factories.schedule import ScheduleFactories
from tests.factories.contexts import ContextFactories

# Absolute, so that the folder created and the folder written to are the
# same one wherever pytest is launched from. One folder per pytest-xdist
# worker (gw0, gw1, ...): the tests sweep it between runs, which would
# take the files of a test running on another worker with it.
TEST_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tmp",
    os.environ.get("PYTEST_XDIST_WORKER", "main"),
)


def indexer_is_up():
    """
    Tell whether an indexer is configured (INDEXER_KEY) and the
    Meilisearch instance answers, so integration tests are skipped
    instead of erroring or hanging when it is absent. In CI (the CI
    variable the runner sets) a configured indexer that does not answer
    is an error instead: pytest exits 0 on a run where every test
    skipped, so the integration pass would go green having tested
    nothing.
    """
    import requests

    from zou.app import config

    if config.INDEXER["key"] is None:
        return False
    url = (
        f"{config.INDEXER['protocol']}://{config.INDEXER['host']}"
        f":{config.INDEXER['port']}/health"
    )
    try:
        up = requests.get(url, timeout=1).status_code == 200
    except requests.RequestException:
        up = False
    if not up and os.environ.get("CI"):
        raise RuntimeError(
            f"INDEXER_KEY is set but Meilisearch does not answer at {url}: "
            "the integration tests would all be skipped"
        )
    return up


# The same fake instances the app was built with, so that setUp can flush
# them.
job_store = redis_client.get_client(config.KV_JOB_DB_INDEX)
lock_store = redis_lock.get_redis_client()


def rebuild_from_compact(entity_fields, task_fields, rows):
    """
    Reverse the compact encoding of a listing by mapping positional values
    back to the field names its header carries, as a client is expected to
    do. Reading the names from the header rather than hardcoding positions
    is the whole contract of the compact form.
    """
    entities = []
    for row in rows:
        entity = dict(zip(entity_fields, row))
        entity["tasks"] = [
            dict(zip(task_fields, task_row)) for task_row in entity["tasks"]
        ]
        entities.append(entity)
    return entities


class ApiTestCase(unittest.TestCase):
    """
    Set of helpers to make test development easier.
    """

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        """
        Configure application before each test.
        """
        app.test_request_context(headers={"mimetype": "application/json"})
        self.flask_app = app
        self.app = app.test_client()
        self.base_headers = {}
        self.post_headers = {"Content-type": "application/json"}
        # No mail during tests, whatever the environment says.
        app.config["MAIL_ENABLED"] = False
        app_context = app.app_context()
        app_context.push()
        self.addCleanup(app_context.pop)
        # The fakeredis stores are module-level: without a flush, revoked
        # tokens and config entries leak from one test to the next.
        self.addCleanup(auth_tokens_store.revoked_tokens_store.flushall)
        self.addCleanup(config_store.config_store.flushall)
        self.addCleanup(job_store.flushall)
        self.addCleanup(lock_store.flushall)
        # The event handlers are module-level too: one a test registers would
        # run in the next tests, or be enqueued on their patched job queue.
        # register() adds to the dict of an event already listed: copy those.
        self.addCleanup(
            setattr,
            events,
            "handlers",
            {name: names.copy() for name, names in events.handlers.items()},
        )

        from zou.app.utils import cache

        cache.clear()

    def tearDown(self):
        pass

    def log_in(self, email):
        tokens = self.post(
            "auth/login", {"email": email, "password": "mypassword"}, 200
        )
        self.auth_headers = {
            "Authorization": f"Bearer {tokens['access_token']}"
        }
        self.base_headers.update(self.auth_headers)
        self.post_headers.update(self.auth_headers)

    def log_in_admin(self):
        self.log_in(self.user["email"])

    def log_in_manager(self):
        self.log_in(self.user_manager["email"])

    def log_in_cg_artist(self):
        self.log_in(self.user_cg_artist["email"])

    def log_in_client(self):
        self.log_in(self.user_client["email"])

    def log_in_vendor(self):
        self.log_in(self.user_vendor["email"])

    def log_in_supervisor(self):
        self.log_in(self.user_supervisor["email"])

    def log_out(self):
        try:
            self.get("auth/logout")
        except AssertionError:
            pass

    def get(self, path, code=200):
        """
        Get data provided at given path. Format depends on the path.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return json.loads(response.data.decode("utf-8"))

    def get_raw(self, path, code=200):
        """
        Get data provided at given path. Format depends on the path. Do not
        parse the json.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return response.data.decode("utf-8")

    def get_ndjson(self, path, code=200):
        """
        Read a streamed listing. The first line is a header describing the
        rows, the ones after it are the rows themselves.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        self.assertEqual(response.mimetype, "application/x-ndjson")
        lines = response.data.decode("utf-8").strip().split("\n")
        return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]

    def get_first(self, path, code=200):
        """
        Get first element of data at given path. It makes the assumption that
        returned data is an array.
        """
        rows = self.get(path, code)
        return rows[0]

    def capture_events(self, event):
        """
        Collect the payloads of given event in a list and return it. Every
        handler registered so far is dropped first, so the list holds that
        one event and nothing else.
        """
        captured = []

        class Handler:
            __name__ = f"{event}_test_handler"

            def handle_event(self, data=None):
                captured.append(data or {})

        events.unregister_all()
        events.register(event, Handler.__name__, Handler())
        return captured

    def get_404(self, path):
        """
        Make sure that given path returns a 404 error for GET requests.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)

    def post(self, path, data, code=201):
        """
        Run a post request at given path while making sure it sends data at
        JSON format.
        """
        clean_data = fields.serialize_value(data)
        response = self.app.post(
            path, data=json.dumps(clean_data), headers=self.post_headers
        )
        if response.status_code == 500:
            print(response.data)
        self.assertEqual(response.status_code, code)
        return json.loads(response.data.decode("utf-8"))

    def put(self, path, data, code=200):
        """
        Run a put request at given path while making sure it sends data at JSON
        format.
        """
        response = self.app.put(
            path, data=json.dumps(data), headers=self.post_headers
        )
        self.assertEqual(response.status_code, code)
        return json.loads(response.data.decode("utf-8"))

    def put_404(self, path, data):
        """
        Make sure that given path returns a 404 error for PUT requests.
        """
        response = self.app.put(
            path, data=json.dumps(data), headers=self.post_headers
        )
        self.assertEqual(response.status_code, 404)

    def delete(self, path, code=204):
        """
        Run a delete request at given path.
        """
        response = self.app.delete(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return response.data

    def delete_404(self, path):
        """
        Make sure that given path returns a 404 error for DELETE requests.
        """
        response = self.app.delete(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)

    def upload_file(self, path, file_path, code=201, extra_fields={}):
        """
        Upload a file at given path. File data are sent in the request body.
        """
        file_content = open(file_path, "rb")
        file_name = ntpath.basename(file_path)
        data = {"file": (file_content, file_name)}
        if len(extra_fields.keys()) > 0:
            data.update(extra_fields)
        response = self.app.post(path, data=data, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return response.json

    def download_file(self, path, target_file_path, code=200):
        """
        Download a file located at given url path and save it at given file
        path.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        file_descriptor = open(target_file_path, "wb")
        file_descriptor.write(response.data)
        return open(target_file_path, "rb").read()


class ApiDBTestCase(
    ProductionFactories,
    PeopleFactories,
    EntityFactories,
    TaskFactories,
    FileFactories,
    ScheduleFactories,
    ContextFactories,
    ApiTestCase,
):
    """
    Set of helpers for Api tests.

    Five things about the fixtures (tests/factories/) are worth knowing
    before writing a test that steps outside the usual one project, one
    asset, one task shape.

    - Every generator repoints the attribute it names, on every call. The
      ones that take a name guard the default call so it returns what is
      already there, but a call with any other argument builds a new row and
      self.<thing> becomes that row:

          shot = self.shot                       # P01
          self.generate_fixture_shot("Z01")      # self.shot is Z01 now

      Which matters twice over, because the later fixtures default to those
      same attributes: after that line a shot task lands on Z01. Keep what
      you need in a local first. generate_fixture_project also assigns
      self.project_id, and several generators read self.project on the way,
      so one that runs after a second production lands in that production,
      or tries to recreate the default one and hits the unique name
      constraint. Build the row by hand when it has to belong somewhere
      precise.
    - The app treats the organisation as a singleton it creates on demand.
      There is deliberately no generator for it: one would add a second row
      the routes never read. Go through organisation_service.get_organisation().
    - Caching is on during tests (conftest sets CACHE_TYPE), so changing a
      model the service also writes leaves the route reading a stale value.
      project.team.append() is the common one: use
      projects_service.add_team_member().

    Two more, about the request rather than the fixtures:

    - Driving a service directly as a given role means opening a request
      context with that person's token, since the permission helpers read
      the token rather than get_current_user. flask.g lives on the
      application context, which setUp pushes once and test_request_context
      reuses, so g.project_role survives from one such block to the next:
      pop it on the way in, the way a real request would start clean.
      Pushing a fresh application context instead looks tidier and is
      wrong, since the session is scoped to it and every row the fixtures
      hold comes back detached.
    - An exception raised in setUp still rolls the transaction back: the
      rollback is a cleanup, which unittest runs after a failed setUp, so
      the test fails instead of blocking the next one. The quiet way to
      break setUp is to give a helper of your own a name this class
      already uses: setUp calls log_in itself, so redefining it with
      another signature raises before a single fixture exists.
    """

    # Schema is created once per session in conftest.py.
    # Data is truncated between classes (much faster than drop+create).

    @classmethod
    def setUpClass(cls):
        super(ApiDBTestCase, cls).setUpClass()
        with app.app_context():
            table_names = ", ".join(
                f'"{t.name}"' for t in db.metadata.tables.values()
            )
            if table_names:
                with db.engine.connect() as conn:
                    conn.execute(db.text(f"TRUNCATE {table_names} CASCADE"))
                    conn.commit()

    def setUp(self, expire_on_commit=True):
        """
        Configure application before each test.
        set up database transaction.
        """
        super().setUp()

        self._db_connection = db.engine.connect()
        self._db_transaction = self._db_connection.begin()
        factory = sessionmaker(
            bind=self._db_connection,
            binds={},
            expire_on_commit=expire_on_commit,
        )
        self._db_session = scoped_session(
            factory, current_app._get_current_object
        )
        db.session = self._db_session
        # unittest skips tearDown when setUp fails, not the cleanups: a
        # transaction left open keeps the fixture rows it wrote, and the
        # next test inserting the same fixtures waits for it forever.
        self.addCleanup(self.release_db_transaction)

        self.generate_fixture_user()
        self.log_in_admin()

    def release_db_transaction(self):
        """
        Rollback transaction to return database to its original state.
        """
        if not self._db_transaction._deactivated_from_connection:
            self._db_transaction.rollback()
        self._db_connection.close()
        self._db_session.remove()

    def generate_data(self, cls, number, **kwargs):
        """
        Generate random data for a given data model.
        """
        mixer.init_app(self.flask_app)
        return mixer.cycle(number).blend(cls, id=fields.gen_uuid, **kwargs)

    # Helpers

    def assign_task(self, task_id, user_id):
        return tasks_service.assign_task(task_id, user_id)

    def assign_task_to_artist(self, task_id):
        if self.user_cg_artist is None:
            self.generate_fixture_user_cg_artist()
        self.assign_task(task_id, self.user_cg_artist["id"])

    def now(self):
        return datetime.datetime.now().replace(microsecond=0).isoformat()

    def upload_csv(self, path, name):
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", f"{name}.csv")
        )
        self.upload_file(path, file_path_fixture)

    def get_fixture_file_path(self, relative_path):
        current_path = os.getcwd()
        file_path_fixture = os.path.join(
            current_path, "tests", "fixtures", relative_path
        )
        return file_path_fixture

    def get_file_path(self, filename):
        return os.path.join(TEST_FOLDER, filename)

    def create_test_folder(self):
        os.makedirs(TEST_FOLDER)

    def delete_test_folder(self):
        fs.rm_rf(TEST_FOLDER)
