# A Wednesday on the German rail network

A 24-hour time-lapse of one real day of German rail traffic — every scheduled
long-distance and regional train in the country, drawn from the official
nationwide timetable. The map is dark at every hour, so the trains are the
only bright thing on it.

**Live: https://chillchamp1.github.io/github.io/**

Open `index.html` — it is self-contained, so a local double-click works as well
as GitHub Pages. No server, no build step, no network calls except the webfont.
Every push to `main` republishes the site via `.github/workflows/pages.yml`; the
whole page is one 6.7 MB file, so the first load takes a moment on a slow link.

## What is on screen

**Wednesday 13 May 2026**, from the DELFI dataset: 27,757 trains at 7,552
stations across all sixteen states.

| Category | Trips | Drawn as |
|---|---|---|
| **ICE / TGV / RJ** | 800 | high-speed, full-size dot |
| **IC / EC / FLX** | 493 | intercity, full-size dot |
| **RE / RB / MEX** | 26,410 | regional, half-size dot — deliberately the quietest mark |
| **NJ / EN** | 54 | night services, **yellow** |

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
day in about 90 seconds. A ring opens outward at the station where a service
begins, in that service's colour — a regional ring travels a tenth as far as a
mainline one, since at full reach twenty-six thousand of them bury the
intercity and high-speed events — so at 4x the 05:00–07:00 ramp reads as the
whole country blooming awake. Terminations are not marked: one ring per service
is already dense, and two left the map permanently speckled. The strip behind
the scrubber counts the same starts across the day, in one ink because the
categorical hues stay reserved for the trains.

A compact key — swatch, code, one word — is drawn on the map itself, in the
open ground below Saxony. It costs the frame nothing and means a screen
recording carries its own legend; the panel below the map keeps the full
labels, the live counts and the note.

The clock sits on the Baltic about 30 km off the Fischland-Darß coast, where
the nearest station is far enough away that it never covers the network. Giving
it open water rather than a reserved band hands the whole stage to the map.

Hover a train for its line and destination. Space bar toggles playback.

The window itself adapts to its container: whichever axis has room to spare is widened
towards the reach of the feed's international services. A phone in portrait
gets Germany filling the screen rather than a small map marooned between two
empty bands; a wide desktop gets the neighbours. On
phones the map keeps a full screen to itself and the legend, figures and
controls sit below the fold.

Finding the night trains takes more than matching on "NJ". DELFI names most
NightJet and EuroNight runs by their long-distance line number with an N
suffix — `12N` Basel–Berlin, `91N` Amsterdam–Wien, `20N` Hamburg–Basel — and
only a couple of partner-operated legs literally "NJ", so a name match alone
found 13 of the 54 and left the other 41 drawn as orange intercity trains. The
builder now reads any N-suffixed line as a night service, scoped to route_type
102, where every one of them is. Ordinary ICE/IC services finishing after
midnight still stay in their own categories.

## The US page

`usa.html` is the same animation for the United States: **Wednesday 10 June
2026, 5,737 trains** — Amtrak nationwide (Acela drawn as the high-speed
category, the fifteen overnight long-distance routes as the night category)
plus every commuter rail operator with a *current* open timetable, twenty
feeds from Metra to SunRail. The US spans four time zones, so every feed is
shifted to Eastern using its GTFS agency_timezone; the page says so and shows
one Eastern clock. Subways, light rail and streetcars are excluded, matching
the German page's exclusion of the S-Bahn.

Honesty over coverage: operators whose published GTFS was stale for the
chosen day are **left out rather than drawn from an old schedule** —
Metrolink (expired 2023), VRE, ACE, Shore Line East, Rio Metro Rail Runner
(2024), Tri-Rail (base calendar ended August 2025), DCTA (February 2026),
TEXRail (absent from its operator's feed) and the Alaska Railroad (no GTFS at
all). Together they run roughly 400 trains a day; what is shown is about 93%
of US mainline passenger service, and every one of the 5,737 trips was
verified stop-by-stop against the raw feeds by an independent audit script,
Eastern-time conversion included.

```sh
python3 build/build_us.py <feeds-dir> 20260610 -o data/us-trains.json
python3 build/build_geo_us.py us-states.json -o data/us-geo.json
python3 build/bundle.py -d data/us-trains.json -g data/us-geo.json -p usa.html
```

The national frame leaves the busy corridors tiny, so the dock offers
**region presets** — Northeast, Chicago, Bay Area, Pacific Northwest — that
reframe the same animation; each carries its own water anchors for the clock
and key, the legend counts only what is inside the frame, and `#chicago`-style
URL fragments deep-link a region. A Los Angeles view is deliberately absent:
without Metrolink (stale feed, see above) it would be misleadingly empty.

Basemap: Census Bureau 1:10M state boundaries via topojson/us-atlas
(`states-10m.json`, shoreline-clipped, public-domain data), decoded from
TopoJSON by `build/build_geo_us.py` itself. Alaska, Hawaii and Puerto Rico
are dropped — no feed in the bundle serves them, and Alaska alone would
double the frame.

## The Tokyo page

`tokyo.html` is Greater Tokyo's entire urban rail network over one generic
weekday: **34,206 trains** on 179 lines at 2,201 stations — JR East, both
subway operators, every private railway, monorails and trams. Unlike the
national pages it *includes* subways, because they are the fabric of Tokyo
rail. Three classes: limited expresses and fee-charging liners, the
rapid/express family, and locals. The 14,693 through-running handovers in
the source are stitched into single journeys, so a Tokyu train continuing
into the subway neither dies at the boundary nor blooms a false origin
ring — a Yamanote set even runs its consecutive loops as one dot.

Data: the [mini-tokyo-3d](https://github.com/nagix/mini-tokyo-3d) dataset,
MIT license, © Akihiko Kusanagi, itself derived from ODPT open data. It
publishes weekday/holiday *patterns* rather than dated calendars, so the
page shows "one weekday" and the snapshot date. There is no open Shinkansen
timetable, so Tokyo has no high-speed category. Built by
`build/build_tokyo.py`; audit: 586 of 600 sampled trips matched the raw
files row-for-row, the other 14 are stitched chains verified by hand.

## The Berlin page

`berlin.html` answers "what does *everything on rails* in one city look
like": **16,456 services on Wednesday 11 March 2026** — 308 long-distance,
1,458 regional, 3,116 S-Bahn, 4,294 U-Bahn and 7,280 tram runs (Potsdam's
trams included; only buses and ferries are excluded). Five classes, with the
S-Bahn in its green and the U-Bahn in its traditional yellow; trams take a
fifth hue (#ff8fd8). Same DELFI dataset as the national page, cut to a
Berlin/Potsdam box by `build/build_berlin.py`.

The date differs from the national page deliberately: BVG's U-Bahn and tram
calendars in this DELFI snapshot end on 30 April 2026, so 13 May would show
a Berlin without a U-Bahn. 11 March is the latest ordinary Wednesday with
every mode at full service — found by scanning, not assumed.

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

A portrait video for phones and social posts comes from the page itself:

```sh
node build/export_video.js --seconds 60 --start 00:00 --out german-rail-day.mp4
```

That gives 1080x1920 H.264. Playback is not screen-recorded -- the page is
paused and the scrubber stepped one frame at a time, so each frame lands on an
exact simulated minute however long the render takes, and the whole day fits
the requested length regardless of machine speed. Frames go out as JPEG
because PNG encoding at that size costs more per frame than the page takes to
draw. `--start HH:MM` picks the clock time the day opens on; omit it to start
where the page does, at the quietest minute of the night. Needs playwright and
ffmpeg (`pip install imageio-ffmpeg` supplies one).

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
build/export_video.js index.html -> portrait MP4
```

## Colour and rendering

There is one surface — a near-black ground — and that is what makes the palette
work. Freed from also having to read against a light background, the four hues
are chosen purely for separation and luminance against the dark:

| | |
|---|---|
| high-speed | `#5aa9ff` |
| intercity | `#ff7a45` |
| regional | `#35d69a` |
| night | `#ffd93d` |

All-pairs CVD separation is worst at ΔE 9.9 (deutan) and 7.3 (tritan), normal
vision at 21.3, and every hue clears 3:1 contrast against the ground. They sit
above the categorical lightness band deliberately: that band is a proxy for
readability against the surface, and here the direct contrast measurement
supersedes it. Against the earlier two-surface palette this roughly doubles
tritan separation, which had been its weakest point.

The marks are small enough that pixel geometry matters. Device pixel ratio is
honoured up to 3x, and any dot whose radius falls below about 1.3 device pixels
is snapped to the device grid and drawn as a hard square rather than a circle —
same apparent size, none of the antialiasing smudge that made the regional
trains look blurred. Trail widths have a one-device-pixel floor for the same
reason.

Sky, land and the ~7,500 station dots are rendered once onto an offscreen
canvas and blitted each frame, so the per-frame cost is the moving trains
alone: around 60 fps with 1,660 trains on screen at 3x pixel density. The day
profile is likewise drawn once per resize and blitted.

Origin rings come from a time-sorted event index — one entry per service — so
each frame binary-searches the live window instead of rescanning 27,757 trips. Ring lifetime scales with the playback multiplier, so
an event stays visible for roughly two thirds of a second at any speed.
