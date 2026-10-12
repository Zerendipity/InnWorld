# Players' site (Crónica de Esthelm)

Static Spanish site for the players. Built by `build.py` into `dist/` (not committed).

## The safety rule

The site is built **only** from `_Site/content/` (hand-curated, player-safe Spanish text) and from
images under `Assets/`. It never reads `GM/`, `World/`, `Party/`, `Live/`, `Sessions/` or `Rules/`.
`build.py` also fails if the output contains GM markers (UNRESOLVED, T-0xx thread IDs, GM, STATUS:, ...).
Edit the list in `build.py` (`FORBIDDEN`) or `content/site.yml` (`forbidden:`) to add more.

## Layout

- `content/site.yml` — title, home headline, open leads, hero cards
- `content/personajes|grupos|lugares|cronica/*.md` — one file per entry (front matter + Spanish body)
- `static/` — `style.css`, `app.js`
- `media/` — optimized .webp made from `Assets/` (commit these; CI has no Assets)
- `dist/` — generated site

## Front matter (personajes)

`title`, `tagline`, `race`, `role`, `class` (shown as [Class]), `card` or `portrait` (path under `Assets/`),
`groups: [grupo-slug]`, `places: [lugar-slug]`, `met_by: [PC names]`, `sessions: [sesion-slug]`,
`unknown: [things the players do not know yet]`.
Link entries in text with `[[Name]]` or `[[slug|label]]`; a broken link stops the build.

## Build

    pip install -r _Site/requirements.txt
    python3 _Site/build.py

Open `_Site/dist/index.html` through any static server (links are relative, so it also works
from a GitHub Pages sub-path).
