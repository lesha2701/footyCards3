import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import AppError
from app.models.enums import Rarity

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
PLAYERS_DIR = STATIC_DIR / "players"
PACKS_DIR = STATIC_DIR / "packs" / "uploads"
CARD_COLLECTIONS_DIR = STATIC_DIR / "card_collections" / "uploads"
BADGES_DIR = STATIC_DIR / "badges" / "uploads"
TROPHIES_DIR = STATIC_DIR / "trophies" / "uploads"
GIFT_SETS_DIR = STATIC_DIR / "gift_sets" / "uploads"
LEAGUE_TIERS_DIR = STATIC_DIR / "leagues" / "uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

_SAFE_CHARS = re.compile(r"[^a-z0-9_-]+")


def _safe_stub(display_name: str) -> str:
    stub = display_name.strip().lower().replace(" ", "_")
    stub = _SAFE_CHARS.sub("", stub)
    return stub or "player"


def _sanitize_filename(display_name: str, extension: str) -> str:
    stub = _safe_stub(display_name)
    unique = uuid.uuid4().hex[:8]
    return f"{stub}_{unique}.{extension}"


async def save_player_image(upload: UploadFile, rarity: Rarity, display_name: str) -> str:
    """Validates and stores an uploaded player image; returns the DB-stored relative path."""
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

    target_dir = PLAYERS_DIR / rarity.value
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = _sanitize_filename(display_name, extension)
    target_path = target_dir / filename
    target_path.write_bytes(contents)

    return f"players/{rarity.value}/{filename}"


def delete_player_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_pack_image(upload: UploadFile, slug: str) -> str:
    """Validates and stores an uploaded pack cover image; returns the DB-stored relative path."""
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

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(slug, extension)
    target_path = PACKS_DIR / filename
    target_path.write_bytes(contents)

    return f"packs/uploads/{filename}"


def delete_pack_image(relative_path: str | None) -> None:
    if not relative_path or relative_path.startswith("packs/templates/"):
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_collection_image(upload: UploadFile, slug: str) -> str:
    """Validates and stores an uploaded card-collection cover image; returns the DB-stored relative path."""
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

    CARD_COLLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(slug, extension)
    target_path = CARD_COLLECTIONS_DIR / filename
    target_path.write_bytes(contents)

    return f"card_collections/uploads/{filename}"


def delete_collection_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_badge_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded badge icon image; returns the DB-stored relative path."""
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

    BADGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name, extension)
    target_path = BADGES_DIR / filename
    target_path.write_bytes(contents)

    return f"badges/uploads/{filename}"


def delete_badge_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_trophy_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded trophy image; returns the DB-stored relative path."""
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

    TROPHIES_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name, extension)
    target_path = TROPHIES_DIR / filename
    target_path.write_bytes(contents)

    return f"trophies/uploads/{filename}"


def delete_trophy_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_gift_set_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded gift-set image; returns the DB-stored relative path."""
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

    GIFT_SETS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name, extension)
    target_path = GIFT_SETS_DIR / filename
    target_path.write_bytes(contents)

    return f"gift_sets/uploads/{filename}"


def delete_gift_set_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)


async def save_league_tier_image(upload: UploadFile, name: str) -> str:
    """Validates and stores an uploaded league-tier badge image; returns the DB-stored relative path."""
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

    LEAGUE_TIERS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name, extension)
    target_path = LEAGUE_TIERS_DIR / filename
    target_path.write_bytes(contents)

    return f"leagues/uploads/{filename}"


def delete_league_tier_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)
