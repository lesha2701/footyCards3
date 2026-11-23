"""scripts/optimize_static_images.optimise (run once by migration 0334):
old PNG uploads referenced by any `image_path` become WebP next to the
original, the rows are repointed, the rest is left alone. Real Postgres
(real_pg): it lists the tables through information_schema."""
import io
import uuid

from PIL import Image

from app.models.league import LeagueTier
from app.models.trophy import TrophyDefinition
from scripts.optimize_static_images import optimise


def _png(size: int) -> bytes:
    out = io.BytesIO()
    # Noise compresses badly as PNG, like a real photo would.
    Image.frombytes("RGB", (size, size), uuid.uuid4().bytes * (size * size * 3 // 16 + 1)).save(out, "PNG")
    return out.getvalue()


async def test_old_pngs_become_webp_and_rows_follow(real_pg, tmp_path):
    tag = uuid.uuid4().hex[:8]
    (tmp_path / "leagues" / "uploads").mkdir(parents=True)
    (tmp_path / "trophies" / "uploads").mkdir(parents=True)
    big = f"leagues/uploads/t_{tag}.png"
    (tmp_path / big).write_bytes(_png(1200))
    gif = f"trophies/uploads/t_{tag}.gif"
    (tmp_path / gif).write_bytes(b"GIF89a")
    gone = f"trophies/uploads/gone_{tag}.png"

    async with real_pg() as s:
        tier = LeagueTier(name=f"t{tag}", min_rating=int(uuid.uuid4().int % 10**8) + 10**6, image_path=big)
        trophy = TrophyDefinition(code=f"t{tag}", name="t", image_path=gif)
        broken = TrophyDefinition(code=f"g{tag}", name="g", image_path=gone)
        s.add_all([tier, trophy, broken])
        await s.commit()
        tier_id, trophy_id = tier.id, trophy.id

    async with real_pg() as s:
        conn = await s.connection()
        report = await conn.run_sync(lambda c: optimise(c, apply=True, log=lambda _m: None, static_dir=tmp_path))
        await s.commit()
    webp = big[: -len(".png")] + ".webp"
    assert (tmp_path / webp).is_file()
    assert (tmp_path / big).is_file()  # the original stays
    assert (tmp_path / webp).stat().st_size < (tmp_path / big).stat().st_size
    with Image.open(tmp_path / webp) as img:
        assert max(img.size) <= 384  # MAX_SIDE["leagues"]
    assert report["changed"] >= 1
    assert report["missing"] >= 1  # the row whose file is gone is only counted

    async with real_pg() as s:
        assert (await s.get(LeagueTier, tier_id)).image_path == webp
        assert (await s.get(TrophyDefinition, trophy_id)).image_path == gif  # GIFs untouched

    # Idempotent: a second run finds nothing of ours left to do.
    async with real_pg() as s:
        conn = await s.connection()
        again = await conn.run_sync(lambda c: optimise(c, apply=False, log=lambda _m: None, static_dir=tmp_path))
    assert again["changed"] == 0
