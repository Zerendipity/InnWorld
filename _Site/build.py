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
    "biblioteca": "Biblioteca",
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

# Secciones ocultas (site.yml → hidden: [cronica]): no se generan, no salen en el
# menú y cualquier enlace hacia ellas se escribe como texto plano.
HIDDEN = set(SITE.get("hidden") or [])
unknown = HIDDEN - set(SECTIONS)
if unknown:
    print(f"ERROR: secciones ocultas desconocidas: {sorted(unknown)}", file=sys.stderr)
    sys.exit(1)
NAV = {k: v for k, v in SECTIONS.items() if k not in HIDDEN}
COUNT_WORDS = {
    "personajes": ("personaje", "personajes"),
    "grupos": ("grupo", "grupos"),
    "lugares": ("lugar", "lugares"),
    "cronica": ("sesión", "sesiones"),
    "biblioteca": ("libro", "libros"),
}

by_section = {s: [e for (sec, _), e in ENTRIES.items() if sec == s] for s in SECTIONS}
for s in ("personajes", "grupos"):
    by_section[s].sort(key=lambda e: sort_key(e.title))
by_section["lugares"].sort(key=lambda e: (e.meta.get("order", 99), sort_key(e.title)))
by_section["cronica"].sort(key=lambda e: e.meta.get("order", 0), reverse=True)
by_section["biblioteca"].sort(key=lambda e: e.meta.get("order", 99))

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


LOGO_WIDTHS = (480, 960, 1600)


def make_logo():
    """Logo de la campaña: varias anchuras en webp (con transparencia) y una
    imagen 1200x630 para la vista previa al compartir el enlace."""
    src = SITE.get("logo")
    if not src:
        return False
    names = [make_webp(src, f"site-logo-{w}.webp", w) for w in LOGO_WIDTHS]
    og = MEDIA / "site-og.jpg"
    srcfile = ASSETS / src
    if srcfile.exists() and (not og.exists() or og.stat().st_mtime < srcfile.stat().st_mtime):
        logo = Image.open(srcfile).convert("RGBA")
        W, H = 1200, 630
        w = 1100
        logo = logo.resize((w, round(logo.height * w / logo.width)), Image.LANCZOS)
        bg = Image.new("RGBA", (W, H), (18, 27, 39, 255))
        bg.alpha_composite(logo, ((W - logo.width) // 2, (H - logo.height) // 2))
        bg.convert("RGB").save(og, "JPEG", quality=86, optimize=True)
        print(f"  imagen site-og.jpg ({og.stat().st_size // 1024} KB)")
    return bool(names)


def logo_img(root, big=False):
    alt = esc(SITE.get("logo_alt", SITE["title"]))
    srcset = ", ".join(f"{root}img/site-logo-{w}.webp {w}w" for w in LOGO_WIDTHS)
    sizes = "(max-width: 940px) calc(100vw - 2rem), 900px" if big else "240px"
    return (f'<img src="{root}img/site-logo-{960 if big else 480}.webp" srcset="{srcset}" '
            f'sizes="{sizes}" alt="{alt}" width="2172" height="724" decoding="async"'
            f'{" fetchpriority=high" if big else ""}>')


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
    if e.section in HIDDEN:
        return esc(label or e.title)
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
    home = "home" in cls.split()
    home_href = root or "./"
    if SITE.get("logo"):
        mast = (f'<a class="mast logo{" big" if home else ""}" href="{home_href}">'
                f'{logo_img(root, big=home)}<span class="sr">{esc(SITE["title"])}</span></a>')
    else:
        mast = f'<a class="mast" href="{home_href}">{esc(SITE["title"])}</a>'
    og = ""
    if SITE.get("base_url") and SITE.get("logo"):
        base = SITE["base_url"].rstrip("/") + "/"
        og = (f'<meta property="og:type" content="website">\n'
              f'<meta property="og:site_name" content="{esc(SITE["title"])}">\n'
              f'<meta property="og:title" content="{esc(full)}">\n'
              f'<meta property="og:description" content="{esc(desc)}">\n'
              f'<meta property="og:image" content="{base}img/site-og.jpg">\n'
              f'<meta property="og:image:width" content="1200">\n'
              f'<meta property="og:image:height" content="630">\n'
              f'<meta name="twitter:card" content="summary_large_image">\n')
    nav = "".join(
        f'<a class="br{" on" if k == active else ""}" href="{root}{k}/"'
        f'{" aria-current=page" if k == active else ""}>{esc(v)}</a>'
        for k, v in NAV.items()
    )
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="description" content="{esc(desc)}">
<title>{esc(full)}</title>
{og}<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{root}assets/style.css">
</head>
<body class="{cls}">
<a class="skip" href="#contenido">Saltar al contenido</a>
<header class="top{" top-home" if home else ""}">
  {mast}
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
    art = (f'<span class="art {kind}">{img_tag(name, root)}</span>' if name else
           f'<span class="art none"><span class="ph">{esc(e.title[:1])}</span></span>')
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
    def count_label(k):
        n = len(by_section[k])
        one, many = COUNT_WORDS[k]
        return f"{n} {one if n == 1 else many}"
    doors = "".join(
        f'<li><a href="{k}/"><span class="d-name br">{esc(SECTIONS[k])}</span>'
        f'<span class="d-text">{esc(SITE["doors"][k])}</span>'
        f'<span class="d-count">{esc(count_label(k))}</span></a></li>' for k in NAV)
    if "cronica" in HIDDEN:
        second_btn = '<a class="btn ghost" href="lugares/esthelm/">Recorrer Esthelm</a>'
        last_block = ""
    else:
        last = by_section["cronica"][0]
        first_par = md(last.body, root).split("</p>")[0] + "</p>"
        second_btn = f'<a class="btn ghost" href="cronica/#{last.slug}">Leer la última sesión</a>'
        last_block = f"""
<section class="wrap block">
  <h2 class="br">Última sesión</h2>
  <article class="lastsession">
    <h3>Sesión {esc(str(last.meta['label']))}: {esc(last.title)}</h3>
    <div class="prose">{first_par}</div>
    <p><a class="ref" href="cronica/#{last.slug}">Seguir leyendo la crónica</a></p>
  </article>
</section>
"""
    body = f"""
<section class="hero">
  <div class="hero-text">
    <h1>{esc(SITE['headline'])}</h1>
    <p class="lead">{esc(SITE['lead'])}</p>
    <p class="actions"><a class="btn" href="personajes/">Ver a los personajes</a>
    {second_btn}</p>
  </div>
  <div class="fan" aria-label="Algunos personajes que habéis conocido">{''.join(fan)}</div>
</section>

<section class="wrap block">
  <h2 class="br">Pistas abiertas</h2>
  <p class="intro">{esc(SITE['leads_intro'])}</p>
  <ul class="leads">{''.join(leads)}</ul>
</section>

{last_block}
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


def gaps_html(m, root):
    if not m.get("unknown"):
        return ""
    return ('<h2 class="small">Lo que aún no sabéis</h2><ul class="gaps">' +
            "".join(f"<li>{md_inline(u, root)}</li>" for u in m["unknown"]) + "</ul>")


def meta_row(label, value):
    return f"<dt>{esc(label)}</dt><dd>{value}</dd>" if value else ""


def page_personaje(e):
    root = "../../"
    name, kind = image_for(e)
    m = e.meta
    art = f'<div class="art big none"><span class="ph">{esc(e.title[:1])}</span></div>'
    if name:
        art = f'<div class="art big {kind}">{img_tag(name, root, eager=True)}</div>'
    cls = f'<span class="classtag br">{esc(m["class"])}</span>' if m.get("class") else ""
    def session_ref(s):
        label = f'Sesión {esc(str(get("cronica", s).meta["label"]))}'
        if "cronica" in HIDDEN:
            return label
        return f'<a class="ref" href="{root}cronica/#{s}">{label}</a>'
    sessions = ", ".join(session_ref(s) for s in m.get("sessions", []))
    rows = "".join([
        meta_row("Especie", esc(m.get("race", ""))),
        meta_row("Clase", cls),
        meta_row("Grupos", tag_list(m.get("groups", []), root, "grupos")),
        meta_row("Lugares", tag_list(m.get("places", []), root, "lugares")),
        meta_row("Lo conoce", esc(", ".join(m.get("met_by", [])))),
        meta_row("Aparece en", sessions),
    ])
    gaps = gaps_html(m, root)
    story = ""
    if m.get("story"):
        story = f'<h2 class="small">Su historia</h2><div class="prose story">{md(m["story"], root)}</div>'
    body = f"""
<article class="wrap profile">
  <p class="crumb"><a class="ref" href="{root}personajes/">Personajes</a></p>
  <aside>{art}</aside>
  <div class="profile-main">
    <h1>{esc(e.title)}</h1>
    <p class="tagline">{esc(m.get("tagline", ""))}</p>
    <dl class="meta">{rows}</dl>
    <h2 class="small">Lo que sabéis</h2>
    <div class="prose">{md(e.body, root)}</div>
    {story}
    {gaps}
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
    fig = ""
    if g.meta.get("image"):
        iname = make_webp(g.meta["image"], f"{g.section}-{g.slug}-image.webp", 1000)
        fig = (f'<figure class="group-art"><img src="{root}img/{iname}" alt="{esc(g.meta.get("image_alt", ""))}" '
               f'width="1000" height="750" loading="lazy" decoding="async"></figure>')
    body = f"""
<article class="wrap prose-page">
  <p class="crumb"><a class="ref" href="{root}grupos/">Grupos</a></p>
  <h1>{esc(g.title)}</h1>
  <p class="tagline">{esc(g.meta.get("tagline", ""))}</p>
  {fig}
  <div class="prose">{md(g.body, root)}</div>
  {gaps_html(g.meta, root)}
  {mem}
</article>
"""
    write(f"{g.path}index.html", layout(g.title, body, root, "grupos", g.meta.get("tagline")))


def page_lugares_index():
    root = "../"
    items = "".join(
        f'<li><a href="{p.slug}/"><span class="d-name">{esc(p.title)}</span>'
        f'<span class="d-text">{esc(p.meta.get("tagline", ""))}</span>'
        f'{"<span class=" + chr(34) + "d-count small" + chr(34) + ">En construcción</span>" if p.meta.get("wip") else ""}</a></li>'
        for p in by_section["lugares"])
    body = f"""
<section class="wrap page-head">
  <h1>Lugares</h1>
  <p class="intro">Las ciudades y los sitios que conocéis. Si algo dice «aún no lo sabéis», nadie lo ha descubierto todavía.</p>
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
    city_map = ""
    if m.get("map"):
        mname = make_webp(m["map"], f"{p.section}-{p.slug}-map.webp", m.get("map_width", 1254))
        alt = esc(m.get("map_alt", f"Mapa de {p.title}"))
        city_map = (f'<figure class="citymap"><a href="{root}img/{mname}" target="_blank" rel="noopener">'
                    f'<img src="{root}img/{mname}" alt="{alt}" width="1254" height="1254" loading="lazy" decoding="async"></a>'
                    f'<figcaption>Pulsa el mapa para verlo a tamaño completo.</figcaption></figure>')
    wip = ""
    if m.get("wip"):
        text = esc(m.get("wip_text", "Esta página todavía se está preparando. "
                                     "Muy pronto encontraréis aquí lo que sabéis de este lugar."))
        if SITE.get("wip_image"):
            wname = make_webp(SITE["wip_image"], "site-wip.webp", 1200)
            wip = (f'<figure class="wip-banner"><img src="{root}img/{wname}" '
                   f'alt="{esc(SITE.get("wip_image_alt", "Página en construcción"))}" '
                   f'width="1200" height="400" decoding="async"><figcaption>{text}</figcaption></figure>')
        else:
            wip = f'<div class="wip"><p class="wip-tag br">En construcción</p><p>{text}</p></div>'
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
  {wip}
  {city_map}
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


def page_biblioteca_index():
    root = "../"
    items = []
    for b in by_section["biblioteca"]:
        if b.meta.get("soon"):
            items.append(f'<li class="soon"><div class="row"><span class="d-name">{esc(b.title)}</span>'
                         f'<span class="d-text">{esc(b.meta.get("tagline", ""))}</span>'
                         f'<span class="d-count small">Próximamente</span></div></li>')
        else:
            extra = "Texto" + (f" y audio · {b.meta['audio_length']}" if b.meta.get("audio") else "")
            items.append(f'<li><a href="{b.slug}/"><span class="d-name">{esc(b.title)}</span>'
                         f'<span class="d-text">{esc(b.meta.get("tagline", ""))}</span>'
                         f'<span class="d-count small">{esc(extra)}</span></a></li>')
    body = f"""
<section class="wrap page-head">
  <h1>Biblioteca</h1>
  <p class="intro">Lecturas de fondo sobre el mundo de Innworld, con su texto completo y, cuando existe, el audio para escucharlas.</p>
  <ul class="doors rows">{''.join(items)}</ul>
</section>
"""
    write("biblioteca/index.html", layout("Biblioteca", body, root, "biblioteca", "Libros sobre el mundo de Innworld."))


def page_libro(b):
    root = "../../"
    m = b.meta
    player = ""
    if m.get("audio"):
        player = (f'<div class="listen"><p class="listen-label">Escuchar el libro entero'
                  f'<span> · {esc(m.get("audio_length", ""))}</span></p>'
                  f'<audio controls preload="none" src="{root}audio/{esc(m["audio"])}">'
                  f'Tu navegador no puede reproducir el audio.</audio></div>')
    heads = re.findall(r"^## (.+?) \{#([\w-]+)\}\s*$", b.body, re.M)
    toc = ""
    if heads:
        toc = ('<nav class="toc" aria-label="Contenido del libro">' +
               "".join(f'<a class="ref" href="#{a}">{esc(t)}</a>' for t, a in heads) + "</nav>")
    author = f'<p class="byline">Crónica de {esc(m["author"])}</p>' if m.get("author") else ""
    body = f"""
<article class="wrap prose-page book">
  <p class="crumb"><a class="ref" href="{root}biblioteca/">Biblioteca</a></p>
  <h1>{esc(b.title)}</h1>
  <p class="tagline">{esc(m.get("tagline", ""))}</p>
  {author}
  {player}
  {toc}
  <div class="prose book-text">{md(b.body, root)}</div>
</article>
"""
    write(f"{b.path}index.html", layout(b.title, body, root, "biblioteca", m.get("tagline")))


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
    for sec in HIDDEN:
        if (DIST / sec).exists():
            fail(f"la sección oculta {sec}/ sigue en dist/ (bórrala a mano o vuelve a construir)")
        for f in DIST.rglob("*.html"):
            if re.search(rf'href="[^"]*\b{sec}/', f.read_text(encoding="utf-8")):
                bad.append(f"{f.relative_to(DIST)}: enlace a {sec}/")
    if bad:
        fail("enlaces a secciones ocultas:\n  " + "\n  ".join(bad))


def main():
    print("Construyendo el sitio...")
    if DIST.exists():
        try:
            shutil.rmtree(DIST)
        except OSError:
            print("aviso: no puedo borrar dist/, sobrescribo los archivos (puede haber restos antiguos)")
    DIST.mkdir(exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    make_logo()
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
    if "cronica" not in HIDDEN:
        page_cronica()
    page_biblioteca_index()
    for e in by_section["biblioteca"]:
        if not e.meta.get("soon"):
            page_libro(e)
    page_404()
    shutil.copytree(STATIC, DIST / "assets", dirs_exist_ok=True)
    (DIST / "img").mkdir(exist_ok=True)
    for f in [*MEDIA.glob("*.webp"), *MEDIA.glob("site-og.jpg")]:
        shutil.copy(f, DIST / "img" / f.name)
    if (HERE / "audio").is_dir():
        shutil.copytree(HERE / "audio", DIST / "audio", dirs_exist_ok=True)
    (DIST / ".nojekyll").write_text("")
    (DIST / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    check_forbidden()
    n = sum(1 for _ in DIST.rglob("*.html"))
    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    print(f"Listo: {n} páginas, {size:.1f} MB en {DIST}")


if __name__ == "__main__":
    main()
