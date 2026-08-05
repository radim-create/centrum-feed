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
odstraneni iframu, vetovani obrazku, stabilni pubDate) uz jsou obsazena ve
zdrojovem feedu, takze se tady neopakuji.

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

## Nastaveni repa

1. **Settings -> Pages** -> Source: `Deploy from a branch`, branch `main`, folder `/docs`.
2. **Settings -> Actions -> General** -> Workflow permissions: `Read and write permissions`.
