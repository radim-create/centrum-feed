# centrum-feed

RSS feed pro **Centrum.cz**, generovany z hotoveho MSN feedu.

- **Zdroj:** https://radim-create.github.io/msn-feed/feed.xml
- **Vystup:** https://radim-create.github.io/centrum-feed/feed.xml (soubor `docs/feed.xml`)
- **Vzor formatu:** https://www.kodenigma.cz/rss/articles-cs.xml

## Jak to funguje

`transform.py` stahne MSN feed a prepise ho do struktury, kterou pouziva Centrum:

| | MSN feed | Centrum feed |
|---|---|---|
| poradi namespacu | content, media, atom | atom, content, media |
| cas buildu | `<lastBuildDate>` | `<pubDate>` v `<channel>` |
| logo kanalu | – | `<image>` |
| self odkaz | – | `<atom:link rel="self">` |
| `<docs>` | – | ano |
| poradi v `<item>` | title, description, content, media, pubDate, link, guid | title, link, description, content, media, pubDate, category, guid |
| obrazek | `<media:credit>` | `<media:title>` |
| kategorie | – | `<category>Film</category>` |
| casova zona | GMT | Europe/Prague (`+0200` / `+0100`) |

Vsechna pravidla z MSN pipeline (cutoff datum, vyrazeni "Recenzujte a vyhrajte",
odstraneni iframu, stabilni pubDate) uz jsou obsazena ve zdrojovem feedu, takze
se tady neopakuji.

## Nahledovy obrazek ma vzdy kazda polozka

MSN pipeline kontroluje nahledy Claudem na viditelne nasili a zbrane a zavadne
z feedu vyhazuje (pravidlo 5 v `msn-feed/transform.py`). To je pozadavek MSN
Partner Hubu -- Centrum.cz ho nema. Nektere polozky proto prijdou ze zdroje bez
`<media:content>`.

Obrazky v tele clanku (`content:encoded`) msn-feed nefiltruje, takze se pouzije
trojstupnovy fallback:

1. `<media:content>` ze zdrojoveho MSN feedu
2. prvni `http(s)` obrazek z tela clanku (relativni cesty a `data:` URI se
   preskakuji)
3. `FALLBACK_IMAGE_URL`

Pokud by i tak nejaka polozka zustala bez obrazku, skript skonci s chybou a
workflow spadne -- radeji hlasita chyba nez tichy feed s dirou.

V logu buildu je videt rozpad: `img_feed=19 img_body=1 img_fallback=0`,
plus u kazde polozky s nahradou i jeji nazev.

## Spousteni

GitHub Actions, cron `6 * * * *` – kazdou hodinu v 6. minute.
Jde spustit i rucne pres **Actions -> Build Centrum feed -> Run workflow**.

> Pozn.: GitHub cron neni presny na minutu, pri zatizeni se bezne opozdi o 5–15 minut.
> Pokud je potreba presny cas, spousti se workflow externe pres
> `workflow_dispatch` API (stejne jako u `msn-feed` pres Cloudflare Worker).

## Konfigurace

Vse jde prepsat pres env promenne (viz zacatek `transform.py`):

| promenna | default |
|---|---|
| `SOURCE_URL` | `https://radim-create.github.io/msn-feed/feed.xml` |
| `SELF_URL` | `https://radim-create.github.io/centrum-feed/feed.xml` |
| `OUTPUT` | `docs/feed.xml` |
| `CHANNEL_TITLE` | `Kinobox.cz` |
| `CHANNEL_LINK` | `https://www.kinobox.cz` |
| `CHANNEL_DESCRIPTION` | popis Kinoboxu |
| `CHANNEL_IMAGE_URL` | `https://radim-create.github.io/centrum-feed/logo.png` (soubor `docs/logo.png`) |
| `DEFAULT_CATEGORY` | `Film` |
| `FALLBACK_IMAGE_URL` | `https://radim-create.github.io/centrum-feed/logo.png` |

## Nastaveni repa

1. **Settings -> Pages** -> Source: `Deploy from a branch`, branch `main`, folder `/docs`.
2. **Settings -> Actions -> General** -> Workflow permissions: `Read and write permissions`.
