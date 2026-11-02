# «⚔️ Битва фанатов» — art

Drop finished files here (`.webp` or `.png`); they replace the drawn
placeholders without code changes (`lib/fanBattle.ts` → `fanArt`).

| File | Size | Where |
| --- | --- | --- |
| `banner.webp` | 1200×400 | home banner and the event header |
| `side-fire.webp`, `side-ice.webp` | 256×256 | side emblems (named by the side `code` from the admin page) |
| `badge-fan.webp` | 256×256 | the «Фанат 2026» milestone row |

The «Перебежчик» boss goes to `src/assets/bosses/kontra-turncoat.webp`
(384×384); until then `boss-turncoat-placeholder.svg` is shown. Badge
pictures shown next to names live in `backend/static/badges/` and are set on
the badge row (`badges.image_path`).
