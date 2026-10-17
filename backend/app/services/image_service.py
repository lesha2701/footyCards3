import io
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import AppError
from app.models.enums import Rarity

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
PLAYERS_DIR = STATIC_DIR / "players"
COACHES_DIR = STATIC_DIR / "coaches"
STADIUMS_DIR = STATIC_DIR / "stadiums"
PACKS_DIR = STATIC_DIR / "packs" / "uploads"
CARD_COLLECTIONS_DIR = STATIC_DIR / "card_collections" / "uploads"
BADGES_DIR = STATIC_DIR / "badges" / "uploads"
TROPHIES_DIR = STATIC_DIR / "trophies" / "uploads"
GIFT_SETS_DIR = STATIC_DIR / "gift_sets" / "uploads"
LEAGUE_TIERS_DIR = STATIC_DIR / "leagues" / "uploads"
LIFESTYLE_DIR = STATIC_DIR / "lifestyle" / "uploads"
ARTIFACTS_DIR = STATIC_DIR / "artifacts" / "uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# Longest side, in pixels, an upload is scaled down to (never up). Card art
# is shown at most ~300 css px wide on a phone, so 768 px covers 2–3x
# screens; icons-sized assets need far less. Anything bigger only costs
# players download time — admin uploads used to land as-is (PNGs of 2.5 MB).
MAX_SIDE = {
    "players": 768,
    "coaches": 768,
    "stadiums": 768,
    "packs": 768,
    "card_collections": 768,
    "gift_sets": 512,
    "lifestyle": 512,
    "artifacts": 512,
    "leagues": 384,
    "badges": 256,
    "trophies": 256,
}
WEBP_QUALITY = 82

_SAFE_CHARS = re.compile(r"[^a-z0-9_-]+")


def _safe_stub(display_name: str) -> str:
    stub = display_name.strip().lower().replace(" ", "_")
    stub = _SAFE_CHARS.sub("", stub)
    return stub or "player"


def _sanitize_filename(display_name: str, extension: str) -> str:
    stub = _safe_stub(display_name)
    unique = uuid.uuid4().hex[:8]
    return f"{stub}_{unique}.{extension}"


def optimize_image(contents: bytes, extension: str, max_side: int) -> tuple[bytes, str]:
    """Best-effort shrink + WebP re-encode of an uploaded image.

    Returns (bytes, extension) to store. GIFs are kept as they are (they may
    be animated); anything Pillow can't decode is kept as uploaded, exactly as
    before this optimisation existed — the upload validation above is the
    gate, this step only ever makes a valid image smaller. The original is
    also kept when re-encoding wouldn't actually make it smaller."""
    if extension == "gif":
        return contents, extension
    try:
        with Image.open(io.BytesIO(contents)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if has_alpha else "RGB")
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return contents, extension
    encoded = out.getvalue()
    if extension == "webp" and len(encoded) >= len(contents):
        return contents, extension
    return encoded, "webp"


async def _read_validated(upload: UploadFile) -> tuple[bytes, str]:
    if not upload.filename or "." not in upload.filename:
        raise AppError("invalid_file", "File has no extension", 400)

    extension = upload.filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError("invalid_file_type", f"Extension .{extension} is not allowed", 400)
    if upload.content_type and upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise AppError("invalid_file_type", f"Content-Type {upload.content_type} is not allowed", 400)

    contents = await upload.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise AppError("file_too_large", f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit", 400)
    if len(contents) == 0:
        raise AppError("invalid_file", "Uploaded file is empty", 400)
    return contents, extension


async def _save_upload(upload: UploadFile, target_dir: Path, relative_prefix: str, name: str, kind: str) -> str:
    """Validate, optimise and store an upload; returns the DB-stored relative path."""
    contents, extension = await _read_validated(upload)
    contents, extension = optimize_image(contents, extension, MAX_SIDE[kind])
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name, extension)
    (target_dir / filename).write_bytes(contents)
    return f"{relative_prefix}/{filename}"


def _delete_static(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_player_image(upload: UploadFile, rarity: Rarity, display_name: str) -> str:
    """Validates and stores an uploaded player image; returns the DB-stored relative path."""
    return await _save_upload(upload, PLAYERS_DIR / rarity.value, f"players/{rarity.value}", display_name, "players")


def delete_player_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_coach_image(upload: UploadFile, rarity: Rarity, display_name: str) -> str:
    """Validates and stores an uploaded coach image; returns the DB-stored relative path."""
    return await _save_upload(upload, COACHES_DIR / rarity.value, f"coaches/{rarity.value}", display_name, "coaches")


def delete_coach_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_stadium_image(upload: UploadFile, rarity: Rarity, display_name: str) -> str:
    """Validates and stores an uploaded stadium image; returns the DB-stored relative path."""
    return await _save_upload(upload, STADIUMS_DIR / rarity.value, f"stadiums/{rarity.value}", display_name, "stadiums")


def delete_stadium_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_pack_image(upload: UploadFile, slug: str) -> str:
    """Validates and stores an uploaded pack image; returns the DB-stored relative path."""
    return await _save_upload(upload, PACKS_DIR, "packs/uploads", slug, "packs")


def delete_pack_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_collection_image(upload: UploadFile, slug: str) -> str:
    """Validates and stores an uploaded card-collection image; returns the DB-stored relative path."""
    return await _save_upload(upload, CARD_COLLECTIONS_DIR, "card_collections/uploads", slug, "card_collections")


def delete_collection_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_badge_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded badge image; returns the DB-stored relative path."""
    return await _save_upload(upload, BADGES_DIR, "badges/uploads", name, "badges")


def delete_badge_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_trophy_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded trophy image; returns the DB-stored relative path."""
    return await _save_upload(upload, TROPHIES_DIR, "trophies/uploads", name, "trophies")


def delete_trophy_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_gift_set_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded gift-set image; returns the DB-stored relative path."""
    return await _save_upload(upload, GIFT_SETS_DIR, "gift_sets/uploads", name, "gift_sets")


def delete_gift_set_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_league_tier_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded league-tier badge image; returns the DB-stored relative path."""
    return await _save_upload(upload, LEAGUE_TIERS_DIR, "leagues/uploads", name, "leagues")


def delete_league_tier_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_lifestyle_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded «Имущество» item image; returns the DB-stored relative path."""
    return await _save_upload(upload, LIFESTYLE_DIR, "lifestyle/uploads", name, "lifestyle")


def delete_lifestyle_image(relative_path: str | None) -> None:
    _delete_static(relative_path)


async def save_artifact_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded «Артефакт» image; returns the DB-stored relative path."""
    return await _save_upload(upload, ARTIFACTS_DIR, "artifacts/uploads", name, "artifacts")


def delete_artifact_image(relative_path: str | None) -> None:
    _delete_static(relative_path)
