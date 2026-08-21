# A Wednesday on the German rail network

A 24-hour time-lapse of one real day of German rail traffic — every scheduled
long-distance and regional train in the country, drawn from the official
nationwide timetable. At sunset the map flips to night.

Open `index.html` — it is self-contained, so a local double-click works as well
as GitHub Pages. No server, no build step, no network calls except the webfont.

## What is on screen

**Wednesday 13 May 2026**, from the DELFI dataset: 27,757 trains at 7,552
stations across all sixteen states.

| Category | Trips | Drawn as |
|---|---|---|
| **ICE / TGV / RJ** | 800 | high-speed, full-size dot |
| **IC / EC / FLX** | 534 | intercity, full-size dot |
| **RE / RB / MEX** | 26,410 | regional, half-size dot — deliberately the quietest mark |
| **NJ / EN** | 13 | night services, **yellow** |

Urban transit — S-Bahn, U-Bahn, tram, bus, dial-a-ride — is filtered out; at
national scale it would bury everything else. Rail-replacement buses carrying
RE/RB-style names are excluded too. Each train carries a tail so the direction
of travel reads at a glance: ten minutes for the mainline categories, six for
regional, which is also drawn at 60% of their dot size. Only the
largest cities are named, anchored by coordinate rather than by station name
(every state's data supplier names stations differently). A faint outline of
Germany with its state borders sits underneath for orientation.

The animation opens at the quietest minute of the day, found by scanning
per-minute occupancy rather than hard-coded, and runs at 4x by default: a full
day in about 90 seconds. Hover a train for its line and destination. Space bar
toggles playback. On
phones the map keeps a full screen to itself and the legend, figures and
controls sit below the fold.

The night-train count is genuinely small: DELFI carries only the NightJet and
EuroNight runs the operators deliver to it, and ordinary ICE/IC services
finishing after midnight stay in their own categories.

## Day and night

The switch is driven by the real position of the sun over central Germany
(NOAA low-precision solar position). Whenever the sun is below the horizon the
whole map is dark — one clean change at sunset rather than a gradual fade. For
13 May that lands at about 20:56.

## The data

`data/trains.json` is built from the **official DELFI e.V. GTFS dataset**
(licensed CC-BY), the Germany-wide timetable aggregated from all federal
states' data suppliers. The snapshot used is version 2026-01-24, valid
2026-01-10 to 2026-06-13.

The DELFI dataset normally requires a (free) registration at
[opendata-oepnv.de](https://www.opendata-oepnv.de). This copy came from the
[Mobility Database](https://mobilitydatabase.org)'s public mirror on Google
Cloud Storage — where it sits filed under catalog entry `mdb-784`, labeled
"Rursee-Schifffahrt KG" after one of the 1,174 agencies inside it rather than
after its publisher:

```
https://storage.googleapis.com/mdb-latest/de-unknown-rursee-schifffahrt-kg-gtfs-784.zip
```

`feed_info.txt` inside identifies it as published by DELFI e.V.

`data/germany.json` is the basemap: the national outline and the sixteen state
borders, from [`isellsoap/deutschlandGeoJSON`](https://github.com/isellsoap/deutschlandGeoJSON)
(Unlicense, public domain), reduced to three-decimal coordinates.

## Rebuilding

```sh
curl -o delfi.zip "https://storage.googleapis.com/mdb-latest/de-unknown-rursee-schifffahrt-kg-gtfs-784.zip"
unzip -d delfi delfi.zip agency.txt calendar.txt calendar_dates.txt \
    feed_info.txt routes.txt stops.txt trips.txt stop_times.txt
python3 build/build_gtfs.py delfi 20260513 -o data/trains.json \
    --note "All categories cover the whole country, from the official DELFI dataset (timetable of 13 May 2026)."
python3 build/bundle.py          # inlines the JSON back into index.html
```

`build_gtfs.py` takes one or more GTFS feeds and any service date they share,
so a different day, a newer DELFI snapshot, or a combination of separate
long-distance and regional feeds (such as the [gtfs.de](https://gtfs.de/en/feeds/)
`de_fv` + `de_rv` pair) all work unchanged. Classification is type-first where
a feed uses extended GTFS route types (DELFI: 101 high-speed, 102
long-distance, 105 sleeper, 106 regional rail) and name-first for plain
type-2 feeds. Times are stored in whole minutes to keep the JSON compact.

The basemap only needs rebuilding if you change the geometry:

```sh
python3 build/build_geo.py outline.geo.json states.geo.json -o data/germany.json
```

## Layout

```
index.html            the whole visualisation, data inlined
data/trains.json      generated timetable extract
data/germany.json     generated basemap rings
build/build_gtfs.py   GTFS feed(s) -> JSON, merged onto one service date
build/build_geo.py    GeoJSON -> compact rings
build/bundle.py       both JSON files -> inlined into index.html
```

## Colour and rendering

High-speed, intercity and regional use the first three slots of a
colourblind-safe categorical palette, which clear all-pairs CVD and
normal-vision separation against both the day and the night background.

Night services are yellow, and yellow is the awkward one: bright enough to
separate cleanly from the intercity orange and it falls outside the palette's
lightness band on the light surface; dark enough to sit in the band and it
closes on orange. The two surfaces therefore get different steps — a deep gold
`#caa500` by day (passes every gate, with a CVD-separation warning against
orange in the 6-8 band) and a bright `#ffd93d` at night (passes outright). The
warning is acceptable here because the category is thirteen trips that run
almost exclusively while the map is dark, and because dot size, the legend and
the figures table all carry the identity independently of hue.

Sky, land and the ~7,500 station dots are rendered once per sunset flip onto an
offscreen canvas and blitted each frame, so the per-frame cost is the moving
trains alone — the page stays fluid with 1,600+ trains on screen.
