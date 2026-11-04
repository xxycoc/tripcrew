"""Validate receipt images before booking; save only alongside a new expense."""

from io import BytesIO
import os
from pathlib import Path

import av


MAX_BYTES = 10 * 1024 * 1024
FORMATS = {".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
           ".png": (b"\x89PNG\r\n\x1a\n",), ".gif": (b"GIF87a", b"GIF89a"),
           ".bmp": (b"BM",), ".tif": (b"II*\x00", b"MM\x00*"),
           ".tiff": (b"II*\x00", b"MM\x00*"), ".webp": (b"RIFF",)}


def load(filename):
    path = Path(filename)
    extension = path.suffix.lower()
    if extension not in FORMATS:
        raise ValueError("Receipt must be a JPEG, PNG, WebP, GIF, BMP or TIFF image.")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ValueError("Cannot read receipt image; check the local file path and permissions.") from exc
    if len(data) > MAX_BYTES:
        raise ValueError("Receipt image must be at most 10 MiB.")
    if not data.startswith(FORMATS[extension]) or (extension == ".webp" and data[8:12] != b"WEBP"):
        raise ValueError("Receipt contents do not match its image extension.")
    try:
        with av.open(BytesIO(data)) as image:
            next(image.decode(video=0))
    except (av.FFmpegError, StopIteration, ValueError, IndexError) as exc:
        raise ValueError("Receipt is not a readable image.") from exc
    return path.suffix, data


def save(store, spend_id, receipt):
    extension, data = receipt
    folder = store.root / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{spend_id}{extension}"
    created = False
    try:
        with target.open("xb") as stream:
            created = True
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return target
