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


def first_body_image(content: str) -> str:
    """Prvni http(s) obrazek z tela clanku. Pouziva se, kdyz chybi nahled."""
    for m in re.finditer(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']',
                         content, re.I):
        url = html.unescape(m.group(1)).strip()
        if url.startswith(("http://", "https://")):
            return url
    return ""


# ------------------------------------------------------------------ transform

def transform_item(item: str, stats: dict) -> tuple[datetime, str] | None:
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

    stats = {"published": [], "skipped": [], "with_image": 0,
             "image_from_body": [], "image_fallback": [], "image_source": {}}
    built = [x for x in (transform_item(i, stats) for i in items) if x]
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
          f"img_fallback={stats['image_source'].get('fallback', 0)} "
          f"skipped={len(stats['skipped'])} "
          f"newest={rfc822_prague(newest)}")
    for t in stats["image_from_body"]:
        print(f"  nahled z tela clanku (MSN nahled chybel): {t}")
    for t in stats["image_fallback"]:
        print(f"  ! nahled z FALLBACK_IMAGE_URL (v tele zadny obrazek): {t}")
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
