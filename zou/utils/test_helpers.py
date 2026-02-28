import sys
from pathlib import Path

# The tests package lives at the zou repository root, not inside the zou
# package.  Add the repo root to sys.path so "tests.base" is importable
# regardless of the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.base import ApiTestCase, ApiDBTestCase  # noqa: E402

__all__ = ["ApiTestCase", "ApiDBTestCase"]
