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
ctyrstupnovy fallback:

1. `<media:content>` ze zdrojoveho MSN feedu
2. **`thumbs.json`** -- puvodni nahled clanku, jak ho msn-feed videl PRED
   vettingem (stejny postranni kanal jako `embeds.json`)
3. prvni `http(s)` obrazek z tela clanku (relativni cesty a `data:` URI se
   preskakuji)
4. `og:image` ze stranky clanku
5. `FALLBACK_IMAGE_URL` (logo)

Krok 2 dela veskerou praci a je to zamerne ten spravny obrazek -- clanku
skutecne patri, msn-feed ho jen vyradil kvuli pravidlum MSN.

**Krok 4 z CI temer nikdy neprojde:** kinobox.cz vraci GitHub runnerum
`403 Forbidden`. Overeno 10. 8. 2026 -- proto ta oklika pres `thumbs.json`.
Z lokalniho stroje `og:image` funguje, takze krok 4 zustava jako zaloha.

Krok 3 taky casto nepomuze: kratke zpravy a recenze **nemaji v tele zadny
obrazek**, jedinym vizualem je prave ten nahled.

Pokud by i tak nejaka polozka zustala bez obrazku, skript skonci s chybou a
workflow spadne -- radeji hlasita chyba nez tichy feed s dirou.

V logu buildu je videt rozpad, napr. `img_feed=18 img_body=1 img_og=1
img_fallback=0`, plus u kazde polozky s nahradou i jeji nazev. Radek zacinajici
`!! LOGO misto nahledu` znamena, ze clanek nema obrazek opravdu nikde -- stoji
za to se na nej podivat rucne.

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
| `EMBEDS_URL` | `https://raw.githubusercontent.com/radim-create/msn-feed/main/embeds.json` |
| `EMBED_BASE` | `https://www.kinobox.cz/embed/` |
| `EMBED_WIDTH` / `EMBED_HEIGHT` | `580` / `326` |

## Video se prehraje primo v clanku

MSN iframy zakazuje, takze je `msn-feed` maze a nahrazuje vetou
**"Video si můžete přehrát na Kinoboxu."** s odkazem na clanek. Pro ctenare na
Centru je ten odkaz slepy: vede na Kinobox clanek, ktery ho posle zpatky na
Centrum, a video nevidi.

Centrum ale iframy povoluje ([dokumentace][doc], sekce *Pokrocile komponenty ->
Embedded content*), takze se veta nahrazuje skutecnym prehravacem:

```html
<p><iframe width="580" height="326" src="https://www.kinobox.cz/embed/2050725"
   title="Kinobox video player" frameborder="0" allowfullscreen></iframe></p>
```

Samotne id videa uz v MSN feedu neni. `msn-feed` ho proto **pred** smazanim
iframu zapisuje do `embeds.json` (mapa `id clanku` -> `id videa`), odkud se sem
cte. Vystup pro MSN se tim nemeni ani o bajt -- je to jednosmerny postranni
kanal.

```
Kinobox API --> msn-feed --> docs/feed.xml   (beze zmeny, bez iframu)
                    |
                    +------> embeds.json     {"56695": "2050725"}
                                  |
              centrum-feed <------+  slozi iframe zpet
```

Kdyz pro clanek zaznam chybi (nebo je `embeds.json` nedostupny), veta s odkazem
zustane, jak byla -- lepsi slepy odkaz nez zmizely obsah. V logu je to videt
jako `video_bez_id=N`.

Video konci na konci clanku, ne na sve puvodni pozici. To je dane tim, ze
`msn-feed` iframe vyrizne a vetu prilepi az za text; puvodni umisteni se
nikam neuklada.

## Kviz -- pripraveno, ale zatim neaktivni

U kvizovych clanku vklada msn-feed vetu **"Kvíz můžete vyplnit na Kinoboxu"**
s odkazem na clanek. Ten je pro ctenare na Centru stejne slepy jako drive
u videa.

Kviz jde vlozit primo -- bezi jako samostatna aplikace na
`kinobox-quiz-lake.vercel.app/embed/{uuid}` a v iframu funguje. Podpora je
hotova: `embed_quiz()` vetu nahradi prehravacem, jakmile najde kvizovy `src`
v `iframes.json`.

**Zatim se ale neuplatni.** Zdrojovy Kinobox feed kvizovy iframe neobsahuje --
overeno 12. 8. 2026: `iframes.json` mel 19 zaznamu ze 13 clanku a vsechny byly
z `www.kinobox.cz` (videa), kvizovy clanek 56722 tam nebyl vubec. Obsah toho
clanku ve feedu neobsahuje `<iframe>`, `<div>`, `<script>` ani zminku o kvizu;
widget se dokresluje az v prohlizeci na kinobox.cz.

Aby to zacalo fungovat, musi kvizovy iframe **prijit uz ve zdrojovem feedu**
`https://www.kinobox.cz/api/rss-centrum` -- stejne, jako tam uz je iframe
videa. Pak se to chytne samo, bez dalsich zasahu.

Do te doby veta s odkazem zustava, jak byla, a v logu se objevi
`kviz_bez_src=1` s nazvem clanku.

[doc]: https://partner.centrum.cz/jak-to-funguje/dokumentace

## Kdyz je verejna URL starsi nez git

`docs/feed.xml` v gitu je vzdy zdroj pravdy. Verejna adresa ho ale servíruje az
po nasazeni **pages build and deployment**, a to obcas selze nebo se vubec
nespusti (videno 6. 8. 2026: dva neuspesne deploye za sebou, verejny feed
zamrzly na 5 hodin, GitHub Status pritom hlasil vse v poradku).

Poznas to tak, ze `<pubDate>` v `<channel>` na verejne URL je starsi nez
v gitu. Kontrola:

- https://github.com/radim-create/centrum-feed/actions -> workflow
  *pages build and deployment*, posledni beh musi byt zeleny a na aktualnim SHA
- https://github.com/radim-create/centrum-feed/deployments -> stav posledniho
  nasazeni

Nespravi se to samo. Nejspolehlivejsi je vynutit novy deploy jakymkoli pushem
do `main` (staci uprava README) -- nasazeni se pak spusti na aktualni commit.

## Nastaveni repa

1. **Settings -> Pages** -> Source: `Deploy from a branch`, branch `main`, folder `/docs`.
2. **Settings -> Actions -> General** -> Workflow permissions: `Read and write permissions`.
