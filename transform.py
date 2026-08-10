#!/usr/bin/env python3
"""
MSN feed -> Centrum.cz RSS transform.

Cte hotovy MSN feed (https://radim-create.github.io/msn-feed/feed.xml)
a prepisuje ho do struktury, kterou pouziva Centrum.cz
(vzor: https://www.kodenigma.cz/rss/articles-cs.xml).

Rozdily proti MSN feedu:
  * poradi namespacu: atom, content, media
  * <channel> navic obsahuje <image>, <pubDate>, <atom:link rel="self">, <docs>
  * misto <lastBuildDate> se pouziva <pubDate>
  * poradi elementu v <item>:
        title, link, description, content:encoded,
        media:content, pubDate, category, guid
  * <media:content> ma vnorene <media:title> (misto <media:credit>)
  * kazda polozka ma <category>
  * pubDate se prevadi do casu Europe/Prague (+0200 / +0100),
    MSN feed je v GMT

Zadne externi zavislosti (jen stdlib), takze to bezi na holem GitHub runneru.
"""

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, format_datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Prague")
except Exception:  # pragma: no cover - fallback, kdyby chybela tzdata
    TZ = timezone.utc

# ------------------------------------------------------------------ nastaveni

SOURCE_URL = os.environ.get(
    "SOURCE_URL", "https://radim-create.github.io/msn-feed/feed.xml")
OUTPUT = Path(os.environ.get("OUTPUT", "docs/feed.xml"))

# adresa, na ktere bude tenhle feed verejne dostupny (atom:link rel="self")
SELF_URL = os.environ.get(
    "SELF_URL", "https://radim-create.github.io/centrum-feed/feed.xml")

CHANNEL_TITLE = os.environ.get("CHANNEL_TITLE", "Kinobox.cz")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://www.kinobox.cz")
CHANNEL_DESCRIPTION = os.environ.get(
    "CHANNEL_DESCRIPTION",
    "Kinobox.cz - filmové recenze, novinky v kinech, aktuality ze světa "
    "českého i světového filmu")
CHANNEL_LANGUAGE = os.environ.get("CHANNEL_LANGUAGE", "cs")
CHANNEL_IMAGE_URL = os.environ.get(
    "CHANNEL_IMAGE_URL", "https://radim-create.github.io/centrum-feed/logo.png")

# Centrum vzor ma u kazde polozky <category>; MSN feed kategorii neobsahuje,
# takze se pouzije tahle pevna hodnota.
DEFAULT_CATEGORY = os.environ.get("DEFAULT_CATEGORY", "Film")

# Nahledovy obrazek musi byt u KAZDE polozky. Zdrojovy MSN feed ho ale nekdy
# nema - msn-feed pipeline kontroluje nahledy Claudem na viditelne nasili a
# zavadne vyhazuje. To je pozadavek MSN Partner Hubu, Centrum.cz ho nema.
# Obrazky v tele clanku (content:encoded) msn-feed nefiltruje, takze kdyz
# nahled chybi, vezme se prvni obrazek z tela. Az kdyz ani tam zadny neni,
# nastoupi FALLBACK_IMAGE_URL.
FALLBACK_IMAGE_URL = os.environ.get(
    "FALLBACK_IMAGE_URL", "https://radim-create.github.io/centrum-feed/logo.png")

# Video embed.
# MSN zakazuje iframy, takze msn-feed je maze a nahrazuje vetou VIDEO_LINE
# s odkazem na clanek. Pro ctenare na Centru je ten odkaz slepy - vede na
# clanek, ktery ho posle zpatky na Centrum. Centrum ale iframy povoluje
# (partner.centrum.cz/jak-to-funguje/dokumentace, sekce Embedded content),
# takze vetu nahradime skutecnym prehravacem.
#
# Samotne id videa uz v MSN feedu neni. msn-feed ho proto pri mazani iframu
# zapisuje do embeds.json (mapa "id clanku" -> "id videa"), odkud se sem cte.
EMBEDS_URL = os.environ.get(
    "EMBEDS_URL",
    "https://raw.githubusercontent.com/radim-create/msn-feed/main/embeds.json")

VIDEO_LINE = "Video si můžete přehrát na Kinoboxu."
EMBED_BASE = os.environ.get("EMBED_BASE", "https://www.kinobox.cz/embed/")
EMBED_WIDTH = os.environ.get("EMBED_WIDTH", "580")
EMBED_HEIGHT = os.environ.get("EMBED_HEIGHT", "326")
EMBED_TITLE = "Kinobox video player"

DOCS_URL = "https://www.rssboard.org/rss-specification"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


# -------------------------------------------------------------------- pomocne

def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def field(item: str, tag: str) -> str:
    """Vytahne obsah tagu a rozbali pripadne CDATA."""
    m = re.search(rf"<{tag}(?:\s[^>]*)?>(.*?)</{tag}>", item, re.S)
    if not m:
        return ""
    val = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*)\]\]>$", val, re.S)
    return cd.group(1) if cd else val


def esc(s: str) -> str:
    """Escapovani pro plain-textove elementy (title, link, description...)."""
    return html.escape(s, quote=True)


def cdata(s: str) -> str:
    return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def rfc822_prague(dt: datetime) -> str:
    """'Tue, 04 Aug 2026 13:13:00 +0200' - stejny tvar jako ma Centrum vzor."""
    return format_datetime(dt.astimezone(TZ))


def mime_for(url: str) -> str:
    ext = re.sub(r"[?#].*$", "", url).lower().rsplit(".", 1)[-1]
    return {
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "avif": "image/avif",
    }.get(ext, "image/jpeg")


def article_id(link: str) -> str:
    """Kinobox id clanku z .../clanky/{kategorie}/{id}-{slug}."""
    m = re.search(r"/clanky/[^/]+/(\d+)-", link)
    return m.group(1) if m else link


def video_iframe(embed_id: str) -> str:
    return (
        f'<p><iframe width="{esc(EMBED_WIDTH)}" height="{esc(EMBED_HEIGHT)}" '
        f'src="{esc(EMBED_BASE + embed_id)}" title="{esc(EMBED_TITLE)}" '
        f'frameborder="0" allowfullscreen></iframe></p>'
    )


def embed_video(content: str, link: str, embeds: dict, stats: dict,
                title: str) -> str:
    """Nahradi vetu 'Video si muzete prehrat na Kinoboxu.' realnym embedem.

    Kdyz pro clanek zadne id videa neznam, necha vetu byt - lepsi slepy
    odkaz nez zmizely obsah.
    """
    if VIDEO_LINE not in content:
        return content

    embed_id = embeds.get(article_id(link))
    if not embed_id:
        stats["video_bez_id"].append(title)
        return content

    # msn-feed prida presne: <p><b><a href="{link}">VIDEO_LINE</a></b></p>
    pattern = (r"<p>\s*<b>\s*<a\b[^>]*>\s*" + re.escape(VIDEO_LINE)
               + r"\s*</a>\s*</b>\s*</p>")
    new, n = re.subn(pattern, video_iframe(embed_id), content, count=1)
    if n == 0:
        # Odstavec vypada jinak, nez cekame - nahradime aspon samotnou vetu,
        # aby se obsah neztratil a nezustal slepy odkaz.
        new = content.replace(VIDEO_LINE, "", 1)
        new += video_iframe(embed_id)
        stats["video_jiny_tvar"].append(title)
    else:
        stats["video_embed"].append(title)
    return new


def first_body_image(content: str) -> str:
    """Prvni http(s) obrazek z tela clanku. Pouziva se, kdyz chybi nahled."""
    for m in re.finditer(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']',
                         content, re.I):
        url = html.unescape(m.group(1)).strip()
        if url.startswith(("http://", "https://")):
            return url
    return ""


_OG_CACHE: dict = {}


def og_image(link: str) -> str:
    """Nahledovy obrazek z <meta property="og:image"> na strance clanku.

    Zachrana pro clanky, ktere nemaji ani nahled v MSN feedu, ani zadny
    obrazek v tele - to je bezne u kratkych zprav a recenzi, kde je jedinym
    vizualem prave ten nahled. Kinobox ma og:image u kazdeho clanku.
    """
    if link in _OG_CACHE:
        return _OG_CACHE[link]
    url = ""
    try:
        page = http_get(link, timeout=20).decode("utf-8", "replace")
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ):
            m = re.search(pat, page, re.I)
            if m:
                cand = html.unescape(m.group(1)).strip()
                if cand.startswith(("http://", "https://")):
                    url = cand
                    break
    except Exception as e:
        print(f"  ! og:image se nepodarilo nacist ({e}): {link}", file=sys.stderr)
    _OG_CACHE[link] = url
    return url


# ------------------------------------------------------------------ transform

def transform_item(item: str, stats: dict,
                   embeds: dict) -> tuple[datetime, str] | None:
    title = field(item, "title")
    link = field(item, "link")
    desc = field(item, "description")
    content = field(item, "content:encoded")
    pub = field(item, "pubDate")

    guid_m = re.search(r"<guid[^>]*>(.*?)</guid>", item, re.S)
    guid = (guid_m.group(1).strip() if guid_m else link)
    cd = re.match(r"^<!\[CDATA\[(.*)\]\]>$", guid, re.S)
    if cd:
        guid = cd.group(1)

    if not (title and link and pub):
        stats["skipped"].append(title or "(bez nazvu)")
        return None

    try:
        pub_dt = parsedate_to_datetime(pub)
    except Exception:
        stats["skipped"].append(title)
        return None
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)

    content = embed_video(content, link, embeds, stats, title)

    # Nahledovy obrazek. Trojstupnovy fallback, aby ho mela KAZDA polozka:
    #   1) <media:content> ze zdrojoveho MSN feedu
    #   2) prvni obrazek z tela clanku (kdyz MSN nahled vyhodil vetting nasili)
    #   3) FALLBACK_IMAGE_URL
    img_url = attrs = inner = ""
    m = re.search(r'<media:content\s+url="([^"]+)"([^>]*)>(.*?)</media:content>',
                  item, re.S)
    if m:
        img_url, attrs, inner = m.group(1), m.group(2), m.group(3)
    else:
        m = re.search(r'<media:content\s+url="([^"]+)"([^>]*?)/\s*>', item, re.S)
        if m:
            img_url, attrs = m.group(1), m.group(2)

    if img_url:
        source = "feed"
        t = re.search(r'type="([^"]+)"', attrs)
        img_type = t.group(1) if t else mime_for(img_url)
    else:
        img_url = first_body_image(content)
        if img_url:
            source = "body"
            stats["image_from_body"].append(title)
        else:
            img_url = og_image(link)
            if img_url:
                source = "og"
                stats["image_from_og"].append(title)
            else:
                img_url = FALLBACK_IMAGE_URL
                source = "fallback"
                stats["image_fallback"].append(title)
        img_type = mime_for(img_url)

    media_title = field(inner, "media:title") if inner else ""
    media_xml = (
        "                                    <media:content\n"
        f'                        url="{esc(img_url)}"\n'
        f'                        type="{img_type}"\n'
        '                        medium="image"\n'
        "                    >\n"
        "                        \n"
        f"                        <media:title>{esc(media_title)}</media:title>\n"
        "                        \n"
        "                    </media:content>\n"
    )
    stats["with_image"] += 1
    stats["image_source"][source] = stats["image_source"].get(source, 0) + 1

    stats["published"].append(title)

    xml = (
        "                                <item>\n"
        f"                <title>{esc(title)}</title>\n"
        f"                                <link>{esc(link)}</link>\n"
        f"                <description>{esc(desc)}</description>\n"
        f"                <content:encoded>{cdata(content)}</content:encoded>\n"
        f"{media_xml}"
        f"                                <pubDate>{rfc822_prague(pub_dt)}</pubDate>\n"
        f"                                    <category>{esc(DEFAULT_CATEGORY)}</category>\n"
        f'                                <guid isPermaLink="true">{esc(guid)}</guid>\n'
        "            </item>"
    )
    return pub_dt, xml


def load_embeds() -> dict:
    """Mapa 'id clanku' -> 'id videa' z msn-feed repa.

    Nedostupnost neni fatalni: feed se postavi bez embedu, jen se to nahlasi.
    """
    path = os.environ.get("EMBEDS_FILE")
    try:
        raw = (Path(path).read_text(encoding="utf-8") if path
               else http_get(EMBEDS_URL, timeout=30).decode("utf-8"))
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("embeds.json neni objekt")
        return {str(k): str(v) for k, v in data.items()}
    except Exception as e:
        print(f"WARNING: embeds.json se nepodarilo nacist ({e}) - "
              f"videa zustanou jako textovy odkaz", file=sys.stderr)
        return {}


def main() -> int:
    src = os.environ.get("SOURCE_FILE")
    xml = (Path(src).read_text(encoding="utf-8") if src
           else http_get(SOURCE_URL).decode("utf-8"))

    parts = re.split(r"<item>", xml)
    items = [p[: p.find("</item>")] for p in parts[1:] if "</item>" in p]
    if not items:
        print("ERROR: ve zdrojovem feedu nejsou zadne <item> elementy",
              file=sys.stderr)
        return 1

    embeds = load_embeds()

    stats = {"published": [], "skipped": [], "with_image": 0,
             "image_from_body": [], "image_from_og": [], "image_fallback": [],
             "image_source": {},
             "video_embed": [], "video_bez_id": [], "video_jiny_tvar": []}
    built = [x for x in (transform_item(i, stats, embeds) for i in items) if x]
    if not built:
        print("ERROR: zadna polozka neprosla transformaci", file=sys.stderr)
        return 1

    out_items = [x[1] for x in built]
    newest = max(x[0] for x in built)

    feed = (
        '<rss\n'
        '    version="2.0"\n'
        '    xmlns:atom="http://www.w3.org/2005/Atom"\n'
        '    xmlns:content="http://purl.org/rss/1.0/modules/content/"\n'
        '    xmlns:media="http://search.yahoo.com/mrss/"\n'
        '>\n'
        '    <channel>\n'
        f'        <title>{esc(CHANNEL_TITLE)}</title>\n'
        f'        <link>{esc(CHANNEL_LINK)}</link>\n'
        f'        <description>{esc(CHANNEL_DESCRIPTION)}</description>\n'
        '        <image>\n'
        f'            <url>{esc(CHANNEL_IMAGE_URL)}</url>\n'
        f'            <title>{esc(CHANNEL_TITLE)}</title>\n'
        f'            <link>{esc(CHANNEL_LINK)}</link>\n'
        '        </image>\n'
        f'        <language>{esc(CHANNEL_LANGUAGE)}</language>\n'
        f'        <pubDate>{rfc822_prague(newest)}</pubDate>\n'
        '        <atom:link\n'
        '            rel="self"\n'
        '            type="application/rss+xml"\n'
        f'            href="{esc(SELF_URL)}"\n'
        '        />\n'
        f'        <docs>{DOCS_URL}</docs>\n'
        + "\n".join(out_items)
        + "\n    </channel>\n</rss>\n"
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(feed, encoding="utf-8")

    n = len(stats["published"])
    print(f"published={n} "
          f"with_image={stats['with_image']}/{n} "
          f"img_feed={stats['image_source'].get('feed', 0)} "
          f"img_body={stats['image_source'].get('body', 0)} "
          f"img_og={stats['image_source'].get('og', 0)} "
          f"img_fallback={stats['image_source'].get('fallback', 0)} "
          f"video_embed={len(stats['video_embed'])} "
          f"video_bez_id={len(stats['video_bez_id'])} "
          f"skipped={len(stats['skipped'])} "
          f"newest={rfc822_prague(newest)}")
    for t in stats["video_embed"]:
        print(f"  video: vlozen iframe: {t}")
    for t in stats["video_jiny_tvar"]:
        print(f"  ! video: odstavec mel jiny tvar, iframe pripojen na konec: {t}")
    for t in stats["video_bez_id"]:
        print(f"  ! video: chybi zaznam v embeds.json, zustava odkaz: {t}")
    for t in stats["image_from_body"]:
        print(f"  nahled z tela clanku (MSN nahled chybel): {t}")
    for t in stats["image_from_og"]:
        print(f"  nahled z og:image na strance clanku: {t}")
    for t in stats["image_fallback"]:
        print(f"  !! LOGO misto nahledu - clanek nema obrazek nikde "
              f"(ani og:image): {t}")
    for t in stats["skipped"]:
        print(f"  preskoceno (chybi title/link/pubDate): {t}")

    # Tvrda garance: kazda publikovana polozka musi mit nahledovy obrazek.
    if stats["with_image"] != n:
        print(f"ERROR: {n - stats['with_image']} polozek bez obrazku",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
