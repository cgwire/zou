import os
import tempfile
import unittest

from zou.remote import playlist as remote_playlist


class FakeStorage:
    """
    A storage holding movies under the given keys only, like an instance
    that skipped the high def normalization.
    """

    def __init__(self, keys):
        self.keys = keys
        self.reads = []

    def read_chunks(self, filename):
        self.reads.append(filename)
        if filename not in self.keys:
            raise FileNotFoundError(filename)
        yield b"movie-bytes"


class FetchInputsTestCase(unittest.TestCase):
    def test_a_movie_stored_as_low_def_only_is_fetched(self):
        storage = FakeStorage({"lowdef-abc"})
        with tempfile.TemporaryDirectory() as outdir:
            inputs = remote_playlist._fetch_inputs(storage, outdir, ["abc"])
            path, filename = inputs[0]
            self.assertEqual(filename, "cache-lowdef-abc.mp4")
            with open(path, "rb") as fetched:
                self.assertEqual(fetched.read(), b"movie-bytes")
            # The failed attempt on the high def key left no empty file.
            self.assertEqual(os.listdir(outdir), [filename])
        self.assertEqual(storage.reads, ["previews-abc", "lowdef-abc"])

    def test_a_movie_stored_nowhere_fails_the_fetch(self):
        storage = FakeStorage(set())
        with tempfile.TemporaryDirectory() as outdir:
            with self.assertRaises(FileNotFoundError):
                remote_playlist._fetch_inputs(storage, outdir, ["abc"])
            self.assertEqual(os.listdir(outdir), [])
