"""Smoke tests for the face encoding helpers.

These tests are skipped automatically if face_recognition / dlib aren't installed,
so the test suite still passes on a fresh checkout before `pip install`.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

face_rec_available = importlib.util.find_spec("face_recognition") is not None
pytestmark = pytest.mark.skipif(not face_rec_available, reason="face_recognition not installed")


def test_encoding_blob_roundtrip():
    import numpy as np

    from core.face import blob_to_encoding, encoding_to_blob

    enc = np.random.rand(128).astype(np.float64)
    blob = encoding_to_blob(enc)
    restored = blob_to_encoding(blob)
    assert restored.shape == (128,)
    assert np.allclose(enc, restored)


def test_match_face_self_match():
    import numpy as np

    from core.face import match_face

    enc = np.random.rand(128).astype(np.float64)
    known = [(1, enc), (2, np.random.rand(128).astype(np.float64))]
    assert match_face(enc, known, tolerance=0.5) == 1


def test_match_face_no_match_when_far():
    import numpy as np

    from core.face import match_face

    a = np.zeros(128)
    b = np.ones(128) * 5.0
    assert match_face(a, [(7, b)], tolerance=0.5) is None
