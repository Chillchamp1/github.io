# A day on the rails

24-hour time-lapses of one real day of rail traffic, built from official
open timetables: eight networks, from whole countries down to single
cities. Every dot is a scheduled train. The map is dark at every hour, so
the trains are the only bright thing on it.

**Live: https://chillchamp1.github.io/github.io/**

The eight networks — Germany, the Benelux, the USA, Greater Tokyo, Berlin,
New York, Switzerland and London — live in one
app at `index.html`, switched by the pills in the top-left corner or by URL
fragment: `#de`, `#nl`, `#us` (plus `#us/ne`, `#us/chi`, `#us/bay`,
`#us/nyc`), `#tokyo`, `#berlin`, `#ny`, `#ch`, `#london`. Every network carries a "Data notes & gaps"
section in its Figures panel — what is missing, what is weak, and why. The old per-country pages redirect there. Each dataset is
fetched when its network is first opened, so the app needs http(s) — GitHub
Pages, or `python3 -m http.server` locally; a bare file:// open cannot fetch.
Every day starts at midnight, and a network that sleeps overnight — Tokyo,
Switzerland, London — fast-forwards while few trains are moving: 5× through the
thinning shoulders, three times that where the map is literally empty, so
nobody waits through three dead hours. New York is the exception that proves
it: its subway runs around the clock and never drops below 126 trains, so it
plays in real time throughout. City labels are placed by a collision pass at
layout time: each tries four vertical slots on either side of its dot, nothing
may cover the clock, the on-canvas key or another label, and a label that finds
no free slot is simply not drawn — two names printed over each other are worse
than one missing. Every push to `main` republishes the site
via `.github/workflows/pages.yml`.

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
The Glow button adds an optional bloom around the trains — off by default,
with diameter (⌀) and intensity (☀) sliders; starting values follow the
zoom, bigger for city frames than for national ones. The glow lives on a
small overlay canvas that the compositor stretches and screens over the
map, so it costs almost nothing even without a GPU.

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
**region presets** — Northeast, Chicago, Bay Area, New York — that
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

## The Benelux page

`#nl` is the Benelux: **11,024 trains on Wednesday 10 June 2026** — the
OVapi/NDOV national GTFS for the Netherlands, SNCB/NMBS for Belgium, the
Luxembourg national feed for CFL, and European Sleeper's own feed (absent
from the aggregates). The day is 10 June because Luxembourg's open feed
covers early summer only — the latest Wednesday inside all four validity
windows. One time-scale rule covers every network: a city-scale frame
(under ~300 km across) defaults to 2×, a national one to 4×, so trains
cover pixels at a comparable rate whether the frame is Berlin or the US. Basemap: Natural Earth 1:10M country shapes
(world-atlas) with CBS province lines inside the Netherlands. Metro, tram,
bus and ferries excluded.

## The New York page

`#ny` is everything on rails around the harbour: **11,803 trains on
Wednesday 26 August 2026** at 920 stations, from four current agency feeds
— MTA's subway (Staten Island Railway included), the Long Island Rail
Road, Metro-North and NJ Transit's rail and light rail. `build/build_ny.py`
merges them onto one service date and follows each feed's `shapes.txt`, so
every one of the 11,803 trains runs on its published route geometry. Two
gaps, both stale feeds rather than choices: PATH's open GTFS expired on
1 June 2026 and the JFK AirTrain's stopped in 2021. Unlike the national US
map this one needs no clock shifting — it is all Eastern time. Basemap: US
Census counties (us-atlas 1:10M, public domain), whose lines double as the
coastline of Manhattan, Long Island and the Jersey shore.

## The Switzerland page

`#ch` is the whole country: **15,988 trains on Wednesday 26 August 2026**,
from the official national aggregate published by SKI+ / SBB through
opentransportdata.swiss — every operator in one file, so rail coverage is
complete. Six classes: IC/EC/TGV, InterRegio, regional, S-Bahn, night, and
a sixth the other maps have no use for — **rack railways and the panorama
expresses** (Glacier Express, Bernina Express, Jungfrau, Pilatus, Rigi),
drawn in violet, because half the point of Swiss rail is that it climbs.
Trams, the Lausanne metro, funiculars, cable cars, boats and buses are left
out, matching the German map's rule that a national map shows trains. The
feed carries no route geometry, so trains interpolate straight between
stops. Basemap: Natural Earth 1:10M cantons, neighbouring country outlines
and the big lakes — Swiss rail runs along the water and the map is
unreadable without it.

## The London page

`#london` is **11,075 trains on Wednesday 26 August 2026**: the
Underground (8,785), the DLR (1,584) and Tramlink (706).

This is the honest limit of British open data. The Department for
Transport's [Bus Open Data Service](https://www.bus-data.dft.gov.uk/) is
the only current open GTFS that carries British rail at all, and what it
carries for London is those three operators — the aggregate is otherwise
13,327 bus routes. National Rail's timetable, which would add the
Overground, the Elizabeth line, Thameslink, Southern and the rest of the
suburban network, is published through Rail Delivery Group channels that
require registration, so roughly half of London's rail journeys are missing
and the page says so in its data notes. The Mobility Database's TfL entry
is a 2017 snapshot and was rejected for that reason. Operators are selected
by name rather than by bounding box, so the Tyne and Wear Metro, Edinburgh
Trams, Manchester Metrolink and the other British tramways in the same file
stay out. Basemap: ONS local authority districts for the Greater London
boroughs, plus the Thames from Natural Earth.

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

On the Germany and Berlin maps the trains follow the **route geometry the
feed itself publishes** (`shapes.txt`), not straight lines between stations:
each kept shape is Douglas-Peucker-simplified (200 m nationally, 25 m for
Berlin — both below the maps' meters-per-pixel), each stop is projected onto
its trip's polyline, and the page interpolates along the line between the
two stops' positions. No map-matching against OSM (pfaedle-style) is needed
because DELFI ships shapes for essentially every trip. Shapes are stored
delta-encoded and deduplicated; trips reference them by index plus per-stop
per-mille fractions, so a network without shapes simply falls back to the
straight-line path.

## Rebuilding

```sh
curl -o delfi.zip "https://storage.googleapis.com/mdb-latest/de-unknown-rursee-schifffahrt-kg-gtfs-784.zip"
unzip -d delfi delfi.zip agency.txt calendar.txt calendar_dates.txt \
    feed_info.txt routes.txt stops.txt trips.txt stop_times.txt shapes.txt
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
python3 -m http.server 8000 &
node build/export_video.js --url http://localhost:8000/index.html#de \
     --seconds 60 --start 00:00 --out german-rail-day.mp4
# Tokyo sleeps overnight: add --warp 60 so the video fast-forwards the gap
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

## Licensing

**Code: public domain** ([the Unlicense](https://unlicense.org), see
[`LICENSE`](LICENSE)). That covers `index.html`, the builders under `build/`
and this documentation. Take it, change it, ship it, sell it — no credit
required, no conditions at all. This is deliberately more open than MIT,
which would have obliged you to carry a copyright notice around.

**Data: not public domain.** Everything under `data/` is derived from
third-party open datasets that keep their own licences and attribution
requirements. No licence of ours can relicense them, and several of them —
DELFI, the Swiss national feed, the UK Bus Open Data Service, Ordnance
Survey boundaries — do require you to name the source. If you reuse the
datasets, credit the original publishers:

| Data | Source | Terms |
|---|---|---|
| Germany, Berlin timetables | DELFI e.V. | CC-BY |
| Benelux timetables | OVapi/NDOV (NL), SNCB/NMBS (BE), the Luxembourg national feed, European Sleeper | each publisher's open-data terms |
| US timetables | Amtrak and twenty commuter operators, via the Mobility Database mirror | each operator's published feed terms |
| New York timetables | MTA (subway, LIRR, Metro-North), NJ Transit | each operator's published feed terms |
| Switzerland timetable | SKI+ / SBB, opentransportdata.swiss | open use, source must be named |
| Tokyo timetable | [mini-tokyo-3d](https://github.com/nagix/mini-tokyo-3d) dataset, © Akihiko Kusanagi, derived from ODPT open data | MIT (dataset), ODPT terms upstream |
| London Underground, DLR, Tramlink | Bus Open Data Service, Department for Transport | Open Government Licence v3.0 |
| London National Rail | ATOC-derived snapshot via the Mobility Database mirror | original publisher's terms |
| Germany, Berlin basemaps | [deutschlandGeoJSON](https://github.com/isellsoap/deutschlandGeoJSON) | Unlicense (public domain) |
| Netherlands provinces | CBS via [cartomap](https://github.com/cartomap/nl) | CBS open data |
| US and New York basemaps | [us-atlas](https://github.com/topojson/us-atlas) (ISC) from US Census geometry | public domain |
| Switzerland, Benelux, Thames | [Natural Earth](https://www.naturalearthdata.com/) | public domain |
| London boroughs | ONS and Ordnance Survey boundaries via [UK-GeoJSON](https://github.com/martinjc/UK-GeoJSON) | OS OpenData / OGL v3.0 — contains OS data © Crown copyright and database right |

None of the datasets are redistributed in their original form: each is filtered
to one service date, reduced to the fields the animation needs and re-encoded.
Where a licence requires attribution, the app names the source on screen in the
provenance line and in the "Data notes & gaps" panel of every network.
