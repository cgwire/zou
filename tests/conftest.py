import os
import tempfile

# Force an isolated preview store before any zou module reads the config.
# Without this, running the tests from a working checkout resolves
# PREVIEW_FOLDER to ./previews — a live development store — which route
# tests then write into and which teardowns may remove entirely.
os.environ["PREVIEW_FOLDER"] = tempfile.mkdtemp(prefix="zou-test-previews-")
