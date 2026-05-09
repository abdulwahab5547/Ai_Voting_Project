"""Face encoding + matching using the face_recognition library."""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Optional

import face_recognition
import numpy as np
from PIL import Image

from config import Config


class FaceError(Exception):
    """Raised when face encoding fails (no face / multiple faces)."""


def decode_data_url(data_url: str) -> bytes:
    """Strip a `data:image/png;base64,...` prefix and return raw image bytes."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url)


def load_image(image_bytes: bytes) -> np.ndarray:
    """Convert raw image bytes into an RGB numpy array."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def encode_face(image_bytes: bytes) -> np.ndarray:
    """Return a 128-d encoding for the single face in the image.

    Raises FaceError if zero or more than one face is detected.
    """
    rgb = load_image(image_bytes)
    locations = face_recognition.face_locations(rgb, model="hog")
    if len(locations) == 0:
        raise FaceError("No face detected. Please look directly at the camera.")
    if len(locations) > 1:
        raise FaceError("Multiple faces detected. Only one person at a time.")
    encodings = face_recognition.face_encodings(rgb, known_face_locations=locations)
    return encodings[0]


def encoding_to_blob(enc: np.ndarray) -> bytes:
    return enc.astype(np.float64).tobytes()


def blob_to_encoding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float64)


def match_face(
    candidate: np.ndarray,
    known: list[tuple[int, np.ndarray]],
    tolerance: Optional[float] = None,
) -> Optional[int]:
    """Return the voter_id of the best match, or None.

    `known` is a list of (voter_id, encoding) tuples loaded from the DB.
    """
    if not known:
        return None
    tol = Config.FACE_TOLERANCE if tolerance is None else tolerance
    encodings = np.stack([e for _, e in known])
    distances = np.linalg.norm(encodings - candidate, axis=1)
    best_idx = int(np.argmin(distances))
    if distances[best_idx] <= tol:
        return known[best_idx][0]
    return None
