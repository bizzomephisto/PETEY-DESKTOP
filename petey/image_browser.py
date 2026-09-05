"""Token-scoped local image browsing for the desktop visual picker."""

from __future__ import annotations

import io
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
MAX_BROWSER_AGE = 60 * 60
MAX_THUMBNAIL_SOURCE = 100 * 1024 * 1024
MAX_CACHED_IMAGE_METADATA = 4096
MAX_CACHED_THUMBNAILS = 256


class ImageBrowserError(ValueError):
    pass


class ImageBrowser:
    def __init__(self):
        self._roots: dict[str, tuple[Path, float]] = {}
        self._lock = threading.RLock()
        self._metadata_cache: OrderedDict[tuple[str, int, int], tuple[int | None, int | None]] = OrderedDict()
        self._thumbnail_cache: OrderedDict[tuple[str, int, int], bytes] = OrderedDict()

    @staticmethod
    def _signature(path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return str(path), stat.st_mtime_ns, stat.st_size

    def _cached_metadata(self, path: Path) -> tuple[int | None, int | None]:
        signature = self._signature(path)
        with self._lock:
            cached = self._metadata_cache.get(signature)
            if cached is not None:
                self._metadata_cache.move_to_end(signature)
                return cached
        width = height = None
        try:
            with Image.open(path) as image:
                width, height = image.size
        except (OSError, UnidentifiedImageError):
            pass
        with self._lock:
            self._metadata_cache[signature] = (width, height)
            self._metadata_cache.move_to_end(signature)
            while len(self._metadata_cache) > MAX_CACHED_IMAGE_METADATA:
                self._metadata_cache.popitem(last=False)
        return width, height

    def open(self, folder: str) -> dict:
        try:
            root = Path(str(folder or "")).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ImageBrowserError("Choose an existing image folder.") from exc
        if not root.is_dir():
            raise ImageBrowserError("Choose an existing image folder.")
        token = uuid.uuid4().hex
        with self._lock:
            now = time.time()
            self._roots = {
                key: value for key, value in self._roots.items() if now - value[1] < MAX_BROWSER_AGE
            }
            self._roots[token] = (root, now)
        return {"token": token, "name": root.name or str(root), "path": str(root)}

    def resolve(self, token: str, relative: str = "") -> tuple[Path, Path]:
        with self._lock:
            item = self._roots.get(str(token or ""))
        if item is None or time.time() - item[1] >= MAX_BROWSER_AGE:
            raise ImageBrowserError("This image folder session expired. Choose the folder again.")
        root = item[0]
        relative = str(relative or "").replace("\\", "/").lstrip("/")
        try:
            target = (root / relative).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ImageBrowserError("That image path is no longer available.") from exc
        if target != root and root not in target.parents:
            raise ImageBrowserError("That path escapes the selected image folder.")
        return root, target

    def list_directory(self, token: str, relative: str = "") -> dict:
        root, directory = self.resolve(token, relative)
        if not directory.is_dir():
            raise ImageBrowserError("That path is not a folder.")
        folders = []
        images = []
        try:
            children = sorted(directory.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError as exc:
            raise ImageBrowserError(f"Could not read the image folder: {exc}") from exc
        for child in children[:1500]:
            try:
                resolved = child.resolve(strict=True)
                if resolved != root and root not in resolved.parents:
                    continue
                relative_path = child.relative_to(root).as_posix()
                if resolved.is_dir():
                    folders.append({"name": child.name, "path": relative_path})
                elif resolved.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                    width, height = self._cached_metadata(resolved)
                    images.append(
                        {"name": child.name, "path": relative_path, "size": resolved.stat().st_size,
                         "width": width, "height": height}
                    )
            except OSError:
                continue
        return {
            "path": directory.relative_to(root).as_posix(), "folders": folders, "images": images
        }

    def image_file(self, token: str, relative: str) -> Path:
        _, path = self.resolve(token, relative)
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ImageBrowserError("That path is not a supported image.")
        return path

    def thumbnail(self, token: str, relative: str) -> io.BytesIO:
        path = self.image_file(token, relative)
        signature = self._signature(path)
        if signature[2] > MAX_THUMBNAIL_SOURCE:
            raise ImageBrowserError("That image is too large to preview.")
        with self._lock:
            cached = self._thumbnail_cache.get(signature)
            if cached is not None:
                self._thumbnail_cache.move_to_end(signature)
                return io.BytesIO(cached)
        try:
            with Image.open(path) as image:
                image.seek(0)
                preview = ImageOps.exif_transpose(image).convert("RGB")
                preview.thumbnail((360, 260))
                output = io.BytesIO()
                preview.save(output, format="JPEG", quality=82, optimize=True)
                encoded = output.getvalue()
            with self._lock:
                self._thumbnail_cache[signature] = encoded
                self._thumbnail_cache.move_to_end(signature)
                while len(self._thumbnail_cache) > MAX_CACHED_THUMBNAILS:
                    self._thumbnail_cache.popitem(last=False)
            return io.BytesIO(encoded)
        except (OSError, UnidentifiedImageError) as exc:
            raise ImageBrowserError("Could not create a preview for that image.") from exc
