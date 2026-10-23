import io

from PIL import Image

from app.services.image_service import optimize_image


def _png(size: tuple[int, int], mode: str = "RGB") -> bytes:
    img = Image.new(mode, size, (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30))
    # Noise so the PNG isn't trivially compressible (closer to a real photo).
    for x in range(0, size[0], 7):
        for y in range(0, size[1], 5):
            img.putpixel((x, y), (x % 255, y % 255, 90, 255) if mode == "RGBA" else (x % 255, y % 255, 90))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_large_png_is_scaled_down_and_reencoded_as_webp():
    original = _png((2000, 1500))
    data, ext = optimize_image(original, "png", 768)
    assert ext == "webp"
    assert len(data) < len(original)
    with Image.open(io.BytesIO(data)) as img:
        assert img.format == "WEBP"
        assert max(img.size) == 768
        assert img.size == (768, 576)  # aspect ratio kept


def test_small_image_is_not_upscaled():
    data, ext = optimize_image(_png((300, 200)), "png", 768)
    with Image.open(io.BytesIO(data)) as img:
        assert ext == "webp" and img.size == (300, 200)


def test_transparency_survives():
    data, _ = optimize_image(_png((400, 400), mode="RGBA"), "png", 256)
    with Image.open(io.BytesIO(data)) as img:
        assert img.mode == "RGBA"
        assert img.getpixel((1, 1))[3] < 255


def test_gif_is_kept_as_is_because_it_may_be_animated():
    out = io.BytesIO()
    Image.new("P", (50, 50)).save(out, format="GIF")
    data, ext = optimize_image(out.getvalue(), "gif", 64)
    assert (data, ext) == (out.getvalue(), "gif")


def test_undecodable_bytes_are_stored_unchanged():
    raw = b"\x89PNG\r\n\x1a\nfake-bytes"
    assert optimize_image(raw, "png", 256) == (raw, "png")


def test_already_small_webp_is_not_made_bigger():
    out = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 10, 10)).save(out, format="WEBP", quality=30)
    data, ext = optimize_image(out.getvalue(), "webp", 768)
    assert ext == "webp" and len(data) <= len(out.getvalue())
