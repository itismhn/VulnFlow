"""Immutable report assets. Only content hashes, never client paths, reach storage."""

import base64
import hashlib
import io
import re
import warnings
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.storage import storage_path
from app.schemas.report import TemplateConfig

MAX_UPLOAD = 20 * 1024 * 1024


def asset_path(asset_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}\.(png|jpg)", asset_id):
        raise ValueError("Invalid report asset")
    return storage_path("report-assets", asset_id)


def image_uri(asset_id: str | None) -> str:
    if not asset_id:
        return ""
    if not asset_id.endswith((".png", ".jpg")):
        raise ValueError("Expected a report image")
    data = asset_path(asset_id).read_bytes()
    mime = "image/png" if asset_id.endswith(".png") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def validate_assets(config: TemplateConfig) -> None:
    ids = [config.branding.logo_asset]
    for page in config.opening_pages:
        ids.append(page.background_asset)
        ids.extend(block.asset for block in page.blocks)
    for asset in ids:
        if asset and not asset_path(asset).is_file():
            raise ValueError("A report image is missing. Upload it again.")


def store_asset(data: bytes, filename: str) -> dict[str, Any]:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Upload a non-empty file smaller than 20 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG") or image.width * image.height > 24_000_000:
                    raise ValueError("Use a PNG or JPEG image up to 24 megapixels")
                image.verify()
            # Re-encode to discard metadata and non-image payloads.
            with Image.open(io.BytesIO(data)) as image:
                out = io.BytesIO()
                ext = "png" if image.format == "PNG" else "jpg"
                image.save(out, format="PNG" if ext == "png" else "JPEG")
                data = out.getvalue()
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Use a valid PNG or JPEG image up to 24 megapixels") from exc
    asset_id = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    path = asset_path(asset_id)
    path.write_bytes(data)
    return {
        "id": asset_id,
        "filename": Path(filename).name[:255],
        "size_bytes": len(data),
    }
