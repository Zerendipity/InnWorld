#!/usr/bin/env python3
"""Genera el sitio de jugadores (Crónica de Esthelm) en _Site/dist.

Regla de seguridad: el sitio se construye SOLO desde _Site/content (textos
curados para jugadores) y desde imágenes de Assets/. Nada de GM/, World/,
Party/ ni Live/ entra nunca. El build falla si el texto contiene marcas
de notas del GM.

Uso:  python3 _Site/build.py
Necesita: pip install markdown pyyaml pillow
"""
import html
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import markdown
import yaml
from PIL import Image

HERE = Path(__file__).resolve().parent
CONTENT = HERE / "content"
STATIC = HERE / "static"
MEDIA = HERE / "media"
DIST = HERE / "dist"
ASSETS = HERE.parent / "Assets"

SECTIONS = {
    "personajes": "Personajes",
    "grupos": "Grupos",
    "lugares": "Lugares",
    "cronica": "Crónica",
}

FORBIDDEN = [
    r"UNRESOLVED", r"\bT-\d{3}\b", r"GM[ -]?ONLY", r"\bGM\b", r"STATUS:",
    r"visibility", r"Revenant", r"Spymaster", r"\[\[", r"GM IDEA", r"AI RULE",
]

esc = html.escape


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def sort_key(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- carga
class Entry:
    def __init__(self, section, slug, meta, body):
        self.section, self.slug, self.meta, self.body = section, slug, meta, body
        self.title = meta["title"]

    @property
    def path(self):
        return f"{self.section}/{self.slug}/"


def load_entries():
    entries = {}
    for section in SECTIONS:
        for f in sorted((CONTENT / section).glob("*.md")):
            text = f.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
            if not m:
                fail(f"{f.name}: falta el bloque de datos (---)")
            meta = yaml.safe_load(m.group(1)) or {}
            if "title" not in meta:
                fail(f"{f.name}: falta 'title'")
            entries[(section, f.stem)] = Entry(section, f.stem, meta, m.group(2).strip())
    return entries


ENTRIES = load_entries()
SITE = yaml.safe_load((CONTENT / "site.yml").read_text(encoding="utf-8"))

by_section = {s: [e for (sec, _), e in ENTRIES.items() if sec == s] for s in SECTIONS}
for s in ("personajes", "grupos"):
    by_section[s].sort(key=lambda e: sort_key(e.title))
by_section["lugares"].sort(key=lambda e: (e.meta.get("order", 99), sort_key(e.title)))
by_section["cronica"].sort(key=lambda e: e.meta.get("order", 0), reverse=True)

LOOKUP = {}
for e in ENTRIES.values():
    for k in [e.slug, e.title] + list(e.meta.get("aliases", [])):
        LOOKUP[sort_key(str(k))] = e


def get(section, slug):
    e = ENTRIES.get((section, slug))
    if not e:
        fail(f"referencia rota: {section}/{slug}")
    return e


# ---------------------------------------------------------------- imágenes
def media_name(e, kind):
    return f"{e.section}-{e.slug}-{kind}.webp"


def make_webp(src_rel, dst_name, width):
    if ".." in src_rel or src_rel.startswith("/"):
        fail(f"ruta de imagen no permitida: {src_rel}")
    src, dst = ASSETS / src_rel, MEDIA / dst_name
    if src.exists():
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            im = Image.open(src)
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            h = round(im.height * width / im.width)
            im.resize((width, h), Image.LANCZOS).save(dst, "WEBP", quality=82, method=6)
            print(f"  imagen {dst_name} ({dst.stat().st_size // 1024} KB)")
    elif not dst.exists():
        fail(f"no encuentro la imagen {src_rel} ni su copia optimizada {dst_name}")
    return dst_name


def image_for(e):
    """Devuelve (nombre_archivo, tipo) para la ilustración principal de una ficha."""
    if e.meta.get("card"):
        return make_webp(e.meta["card"], media_name(e, "card"), 520), "card"
    if e.meta.get("portrait"):
        return make_webp(e.meta["portrait"], media_name(e, "portrait"), 640), "portrait"
    return None, None


# ---------------------------------------------------------------- texto
WIKI = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def link_to(e, root, label=None):
    return f'<a class="ref" href="{root}{e.path}">{esc(label or e.title)}</a>'


def resolve_wikilinks(text, root):
    def sub(m):
        target = LOOKUP.get(sort_key(m.group(1).strip()))
        if not target:
            fail(f"enlace [[{m.group(1)}]] no existe en el contenido")
        return link_to(target, root, (m.group(2) or m.group(1)).strip())
    return WIKI.sub(sub, text)


def md(text, root):
    return markdown.markdown(resolve_wikilinks(text, root), extensions=["extra", "sane_lists"])


def md_inline(text, root):
    out = md(text, root).strip()
    return re.sub(r"^<p>(.*)</p>$", r"\1", out, flags=re.S)


# ---------------------------------------------------------------- plantillas
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' rx='12' fill='%23121b27'/%3E"
           "%3Ctext x='32' y='45' font-size='40' font-family='Georgia,serif' font-weight='700' "
           "text-anchor='middle' fill='%237db8ff'%3E%5BE%5D%3C/text%3E%3C/svg%3E")

FONTS = ("https://fonts.googleapis.com/css2?family=Alegreya:ital,wght@0,400..900;1,400..900"
         "&family=Alegreya+Sans:ital,wght@0,400;0,500;0,700;1,400&display=swap")


def layout(title, body, root, active=None, desc=None, cls=""):
    full = f"{title} · {SITE['title']}" if title else SITE["title"]
    desc = desc or SITE["description"]
    nav = "".join(
        f'<a class="br{" on" if k == active else ""}" href="{root}{k}/"'
        f'{" aria-current=page" if k == active else ""}>{esc(v)}</a>'
        for k, v in SECTIONS.items()
    )
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="description" content="{esc(desc)}">
<title>{esc(full)}</title>
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{root}assets/style.css">
</head>
<body class="{cls}">
<a class="skip" href="#contenido">Saltar al contenido</a>
<header class="top">
  <a class="mast" href="{root or './'}">{esc(SITE['title'])}</a>
  <nav aria-label="Secciones">{nav}</nav>
</header>
<main id="contenido">
{body}
</main>
<footer class="foot">
  <p>{esc(SITE['footer'])} Actualizado tras la sesión {SITE['through_session']}.</p>
</footer>
<script src="{root}assets/app.js" defer></script>
</body>
</html>
"""


def img_tag(name, root, eager=False):
    return (f'<img src="{root}img/{name}" alt="" width="520" height="728" '
            f'{"" if eager else "loading=lazy "}decoding="async">')


def tile(e, root):
    name, kind = image_for(e)
    groups = " ".join(e.meta.get("groups", []))
    hay = sort_key(" ".join([e.title, e.meta.get("tagline", ""), e.meta.get("role", ""),
                             " ".join(e.meta.get("aliases", []))]))
    art = f'<span class="art {kind}">{img_tag(name, root)}</span>' if name else '<span class="art none"></span>'
    return (f'<a class="tile" href="{root}{e.path}" data-groups="{groups}" data-text="{esc(hay)}">'
            f'{art}<span class="name">{esc(e.title)}</span>'
            f'<span class="role">{esc(e.meta.get("role", ""))}</span></a>')


def tag_list(items, root, section):
    return ", ".join(link_to(get(section, s), root) for s in items)


# ---------------------------------------------------------------- páginas
def write(rel, html_text):
    out = DIST / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")


def page_home():
    root = ""
    fan = []
    for i, slug in enumerate(SITE["hero_cards"]):
        e = get("personajes", slug)
        name, kind = image_for(e)
        fan.append(f'<a class="c{i}" style="--i:{i}" href="{e.path}" aria-label="{esc(e.title)}">'
                   f'{img_tag(name, root, eager=True)}</a>')
    leads = []
    for lead in SITE["leads"]:
        rel = []
        for ref in lead.get("related", []):
            sec, slug = ref.split("/")
            rel.append(link_to(get(sec, slug), root))
        relp = f'<p class="rel">Relacionado: {", ".join(rel)}</p>' if rel else ""
        leads.append(f'<li><h3>{esc(lead["title"])}</h3><p>{md_inline(lead["text"], root)}</p>{relp}</li>')
    last = by_section["cronica"][0]
    counts = {k: len(v) for k, v in by_section.items()}
    doors = "".join(
        f'<li><a href="{k}/"><span class="d-name br">{esc(SECTIONS[k])}</span>'
        f'<span class="d-text">{esc(SITE["doors"][k])}</span>'
        f'<span class="d-count">{counts[k]}</span></a></li>' for k in SECTIONS)
    first_par = md(last.body, root).split("</p>")[0] + "</p>"
    body = f"""
<section class="hero">
  <div class="hero-text">
    <h1>{esc(SITE['headline'])}</h1>
    <p class="lead">{esc(SITE['lead'])}</p>
    <p class="actions"><a class="btn" href="personajes/">Ver a los personajes</a>
    <a class="btn ghost" href="cronica/#{last.slug}">Leer la última sesión</a></p>
  </div>
  <div class="fan" aria-label="Algunos personajes que habéis conocido">{''.join(fan)}</div>
</section>

<section class="wrap block">
  <h2 class="br">Pistas abiertas</h2>
  <p class="intro">{esc(SITE['leads_intro'])}</p>
  <ul class="leads">{''.join(leads)}</ul>
</section>

<section class="wrap block">
  <h2 class="br">Última sesión</h2>
  <article class="lastsession">
    <h3>Sesión {esc(str(last.meta['label']))}: {esc(last.title)}</h3>
    <div class="prose">{first_par}</div>
    <p><a class="ref" href="cronica/#{last.slug}">Seguir leyendo la crónica</a></p>
  </article>
</section>

<section class="wrap block">
  <h2 class="br">Por dónde empezar</h2>
  <ul class="doors">{doors}</ul>
</section>
"""
    write("index.html", layout(None, body, root, desc=SITE["description"], cls="home"))


def page_personajes_index():
    root = "../"
    groups = [g for g in by_section["grupos"]
              if any(g.slug in p.meta.get("groups", []) for p in by_section["personajes"])]
    chips = ('<button class="chip br" type="button" data-group="" aria-pressed="true">Todos</button>' +
             "".join(f'<button class="chip br" type="button" data-group="{g.slug}" aria-pressed="false">'
                     f'{esc(g.title)}</button>' for g in groups))
    tiles = "".join(tile(p, root) for p in by_section["personajes"])
    body = f"""
<section class="wrap page-head">
  <h1>Personajes</h1>
  <p class="intro">Las personas que habéis conocido en Esthelm y sus alrededores. Solo aparece lo que vuestros personajes saben.</p>
</section>
<section class="wrap filters" aria-label="Filtros">
  <label class="search"><span class="sr">Buscar por nombre u oficio</span>
    <input type="search" id="q" placeholder="Buscar por nombre u oficio" autocomplete="off"></label>
  <div class="chips" role="group" aria-label="Filtrar por grupo">{chips}</div>
  <p class="count" id="count" aria-live="polite"></p>
</section>
<section class="wrap">
  <div class="grid" id="grid">{tiles}</div>
  <p class="empty" id="empty" hidden>Nadie coincide con esa búsqueda. Prueba con otro nombre o quita el filtro de grupo.</p>
</section>
"""
    write("personajes/index.html", layout("Personajes", body, root, "personajes",
          "Quién es quién en Esthelm."))


def meta_row(label, value):
    return f"<dt>{esc(label)}</dt><dd>{value}</dd>" if value else ""


def page_personaje(e):
    root = "../../"
    name, kind = image_for(e)
    m = e.meta
    art = ""
    if name:
        art = f'<div class="art big {kind}">{img_tag(name, root, eager=True)}</div>'
    cls = f'<span class="classtag br">{esc(m["class"])}</span>' if m.get("class") else ""
    sessions = ", ".join(
        f'<a class="ref" href="{root}cronica/#{s}">Sesión {esc(str(get("cronica", s).meta["label"]))}</a>'
        for s in m.get("sessions", []))
    rows = "".join([
        meta_row("Especie", esc(m.get("race", ""))),
        meta_row("Clase", cls),
        meta_row("Grupos", tag_list(m.get("groups", []), root, "grupos")),
        meta_row("Lugares", tag_list(m.get("places", []), root, "lugares")),
        meta_row("Lo conoce", esc(", ".join(m.get("met_by", [])))),
        meta_row("Aparece en", sessions),
    ])
    story = ""
    if m.get("story"):
        story = f'<h2 class="small">Su historia</h2><div class="prose story">{md(m["story"], root)}</div>'
    body = f"""
<article class="wrap profile">
  <aside>{art}</aside>
  <div class="profile-main">
    <p class="crumb"><a class="ref" href="{root}personajes/">Personajes</a></p>
    <h1>{esc(e.title)}</h1>
    <p class="tagline">{esc(m.get("tagline", ""))}</p>
    <dl class="meta">{rows}</dl>
    <h2 class="small">Lo que sabéis</h2>
    <div class="prose">{md(e.body, root)}</div>
    {story}
  </div>
</article>
"""
    write(f"{e.path}index.html", layout(e.title, body, root, "personajes", m.get("tagline")))


def page_grupos_index():
    root = "../"
    items = []
    for g in by_section["grupos"]:
        members = [p for p in by_section["personajes"] if g.slug in p.meta.get("groups", [])]
        n = (f"{len(members)} {'persona' if len(members) == 1 else 'personas'} en la crónica"
             if members else "Sin personas en la crónica todavía")
        items.append(f'<li><a href="{g.slug}/"><span class="d-name">{esc(g.title)}</span>'
                     f'<span class="d-text">{esc(g.meta.get("tagline", ""))}</span>'
                     f'<span class="d-count small">{esc(n)}</span></a></li>')
    body = f"""
<section class="wrap page-head">
  <h1>Grupos</h1>
  <p class="intro">Gremios, facciones y bandos con los que os habéis cruzado, y cómo se relacionan con vosotros.</p>
  <ul class="doors rows">{''.join(items)}</ul>
</section>
"""
    write("grupos/index.html", layout("Grupos", body, root, "grupos", "Gremios y facciones."))


def page_grupo(g):
    root = "../../"
    members = [p for p in by_section["personajes"] if g.slug in p.meta.get("groups", [])]
    mem = ""
    if members:
        mem = ('<h2 class="small">Personas</h2><div class="grid mini">' +
               "".join(tile(p, root) for p in members) + "</div>")
    body = f"""
<article class="wrap prose-page">
  <p class="crumb"><a class="ref" href="{root}grupos/">Grupos</a></p>
  <h1>{esc(g.title)}</h1>
  <p class="tagline">{esc(g.meta.get("tagline", ""))}</p>
  <div class="prose">{md(g.body, root)}</div>
  {mem}
</article>
"""
    write(f"{g.path}index.html", layout(g.title, body, root, "grupos", g.meta.get("tagline")))


def page_lugares_index():
    root = "../"
    items = "".join(
        f'<li><a href="{p.slug}/"><span class="d-name">{esc(p.title)}</span>'
        f'<span class="d-text">{esc(p.meta.get("tagline", ""))}</span></a></li>'
        for p in by_section["lugares"])
    body = f"""
<section class="wrap page-head">
  <h1>Lugares</h1>
  <p class="intro">La ciudad y los sitios que usáis. Si algo dice «aún no lo sabéis», nadie lo ha descubierto todavía.</p>
  <ul class="doors rows">{items}</ul>
</section>
"""
    write("lugares/index.html", layout("Lugares", body, root, "lugares", "Esthelm y sus sitios."))


def page_lugar(p):
    root = "../../"
    m = p.meta
    sites = ""
    if m.get("sites"):
        lis = "".join(
            f'<li><h3>{esc(s["name"])}</h3><p>{md_inline(s["text"], root)}</p></li>' for s in m["sites"])
        sites = f'<h2 class="small">Sitios</h2><ul class="sites">{lis}</ul>'
    plans = ""
    if m.get("plans"):
        figs = []
        for i, pl in enumerate(m["plans"]):
            name = make_webp(pl["file"], f"{p.section}-{p.slug}-plan{i}.webp", 1400)
            figs.append(f'<figure class="plan" data-label="{esc(pl["label"])}">'
                        f'<img src="{root}img/{name}" alt="Plano: {esc(pl["label"])}" loading="lazy" '
                        f'width="1400" height="1050"><figcaption>{esc(pl["label"])}</figcaption></figure>')
        plans = f'<h2 class="small">Planos</h2><div class="plans" id="plans">{"".join(figs)}</div>'
    people = [q for q in by_section["personajes"] if p.slug in q.meta.get("places", [])]
    ppl = ""
    if people:
        ppl = ('<h2 class="small">Gente de aquí</h2><div class="grid mini">' +
               "".join(tile(q, root) for q in people) + "</div>")
    body = f"""
<article class="wrap prose-page">
  <p class="crumb"><a class="ref" href="{root}lugares/">Lugares</a></p>
  <h1>{esc(p.title)}</h1>
  <p class="tagline">{esc(m.get("tagline", ""))}</p>
  <div class="prose">{md(p.body, root)}</div>
  {plans}
  {sites}
  {ppl}
</article>
"""
    write(f"{p.path}index.html", layout(p.title, body, root, "lugares", m.get("tagline")))


def page_cronica():
    root = "../"
    arts = []
    for s in by_section["cronica"]:
        who = ""
        if s.meta.get("people"):
            who = ('<p class="rel">Aparecen: ' +
                   ", ".join(link_to(get("personajes", x), root) for x in s.meta["people"]) + "</p>")
        arts.append(f'<li id="{s.slug}"><p class="when">Sesión {esc(str(s.meta["label"]))}</p>'
                    f'<h2>{esc(s.title)}</h2><div class="prose">{md(s.body, root)}</div>{who}</li>')
    body = f"""
<section class="wrap page-head">
  <h1>Crónica</h1>
  <p class="intro">Lo que ha pasado, de la sesión más reciente a la primera.</p>
  <ol class="timeline">{''.join(arts)}</ol>
</section>
"""
    write("cronica/index.html", layout("Crónica", body, root, "cronica", "Resumen de cada sesión."))


def page_404():
    body = ('<section class="wrap page-head"><h1>Esta página no existe</h1>'
            '<p class="intro">Puede que el enlace esté mal escrito o que la ficha aún no se haya publicado. '
            '<a class="ref" href="./">Volver al inicio</a>.</p></section>')
    write("404.html", layout("Página no encontrada", body, ""))


# ---------------------------------------------------------------- comprobación
def check_forbidden():
    bad = []
    for f in DIST.rglob("*.html"):
        text = re.sub(r"<[^>]+>", " ", f.read_text(encoding="utf-8"))
        for pat in FORBIDDEN + SITE.get("forbidden", []):
            for m in re.finditer(pat, text):
                bad.append(f"{f.relative_to(DIST)}: «{m.group(0)}»")
    if bad:
        fail("marcas de notas del GM en el sitio:\n  " + "\n  ".join(bad))


def main():
    print("Construyendo el sitio...")
    if DIST.exists():
        try:
            shutil.rmtree(DIST)
        except OSError:
            print("aviso: no puedo borrar dist/, sobrescribo los archivos (puede haber restos antiguos)")
    DIST.mkdir(exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    page_home()
    page_personajes_index()
    for e in by_section["personajes"]:
        page_personaje(e)
    page_grupos_index()
    for e in by_section["grupos"]:
        page_grupo(e)
    page_lugares_index()
    for e in by_section["lugares"]:
        page_lugar(e)
    page_cronica()
    page_404()
    shutil.copytree(STATIC, DIST / "assets", dirs_exist_ok=True)
    (DIST / "img").mkdir(exist_ok=True)
    for f in MEDIA.glob("*.webp"):
        shutil.copy(f, DIST / "img" / f.name)
    (DIST / ".nojekyll").write_text("")
    (DIST / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    check_forbidden()
    n = sum(1 for _ in DIST.rglob("*.html"))
    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    print(f"Listo: {n} páginas, {size:.1f} MB en {DIST}")


if __name__ == "__main__":
    main()
