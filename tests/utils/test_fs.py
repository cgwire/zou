import tempfile
import unittest
from unittest import mock

import pytest
from flask_fs.errors import FileNotFound

from zou.app.utils import fs


class FakeConfig:
    FS_BACKEND = "s3"

    def __init__(self, tmp_dir):
        self.TMP_DIR = tmp_dir


class GetFilePathAndFileTestCase(unittest.TestCase):
    def test_missing_remote_file_raises_file_not_found(self):
        # A remote download that "succeeds" but yields an empty file must be
        # reported as absent (FileNotFound -> 404), not an unhandled 500.
        def open_file(prefix, instance_id):
            yield from ()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch("zou.app.utils.fs.time.sleep"):
                with pytest.raises(FileNotFound):
                    fs.get_file_path_and_file(
                        FakeConfig(tmp_dir),
                        get_local_path=lambda prefix, instance_id: "",
                        open_file=open_file,
                        prefix="previews",
                        instance_id="does-not-exist",
                        extension="png",
                    )
