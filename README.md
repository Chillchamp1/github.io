# A day on the rails

24-hour time-lapses of one real day of rail traffic, built from official
open timetables: ten networks, from a cross-border map of five countries
down to single cities. Every dot is a scheduled train. The map is dark at
every hour, so the trains are the only bright thing on it.

**Live: https://chillchamp1.github.io/github.io/**

The landing map is the combined one — Germany, the Benelux, Switzerland and
France, where trains cross borders instead of stopping at them. The ten networks live in one
app at `index.html`, switched by the pills in the top-left corner or by URL
fragment: `#eu`, `#de`, `#nl`, `#us` (plus `#us/ne`, `#us/chi`, `#us/bay`,
`#us/nyc`), `#tokyo`, `#berlin`, `#ny`, `#fr`, `#ch`, `#london`. Every network carries a "Data notes & gaps"
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

A compact key — a swatch and one word per category — is drawn on the map
itself, pinned to the bottom-right corner above the play controls. It costs
the frame nothing and means a screen recording carries its own legend; the
panel below the map keeps the full labels, the live counts and the note.

The words are the same on every map that has an equivalent: **high-speed,
intercity, regional, night**. A high-speed train is a high-speed train
whether the operator calls it ICE, TGV or Eurostar, and a legend that
renames the same thing per country is a legend you have to re-read. Where
there is no cross-border equivalent the network names its own — Berlin's
S-Bahn, U-Bahn and tram, Tokyo's limited express, Switzerland's rack
railways — which is why the key visibly changes when the city maps come up.

The clock sits on the Baltic about 30 km off the Fischland-Darß coast, where
the nearest station is far enough away that it never covers the network. Giving
it open water rather than a reserved band hands the whole stage to the map.

Hover a train for its line and destination. Space bar toggles playback.
**The map zooms**: mouse wheel or double-click on desktop, two fingers on a
phone — one finger still scrolls the page down to the legend, so the map
never traps the scroll. Drag with the mouse to pan; the button in the
controls shows how far in you are and takes you back out. Because every
coordinate is stored in lon/lat and re-projected, zooming reveals real
detail rather than magnifying pixels: minor city labels appear as the scale
passes each network's threshold, and the coastline and station dots thicken
so the map does not turn to thread. The limit is the source data, not the
renderer — the German feed's own route geometry is coarse enough that
simplifying it to 50 m instead of 200 m costs only 10 kB, so past roughly
20× the polylines, not the drawing, are what you see.
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

## The combined map

`#eu` is the landing page and the only one where a border is just a line on
the ground: **Germany, the Benelux, Switzerland and France**, 70,427 trains,
from national feeds merged onto one map. A EuroCity from
Zürich to Hamburg is one dot for its whole run instead of stopping where
one country's data ends.
The national outlines are drawn a shade brighter than on the single-country
maps -- enough to read where you are, not enough to argue with the trains,
which is the whole point of the page.

The shared date is what makes it honest. DELFI runs out on 13 June 2026 and
the Luxembourg feed starts on 6 May, so **Wednesday 10 June 2026** is the
one window the sources agree on — Île-de-France Mobilités included, whose
mirror runs 31 May to 2 July 2026. `build/build_eu.py` folds the national
class schemes into five (high-speed, intercity, regional including S-Bahn
and the RER, Swiss rack and panorama, night) and adds Eurostar's own feed
for the Paris and London legs the national datasets do not carry.

Trains are published by *both* countries they run through — and SKI+ turns
out to carry some 3,700 French regional services that SNCF publishes as well
— so services are deduplicated across feeds, keeping whichever copy lists
more stops. Long distance matches on class, line name, destination and a
departure within twenty minutes; the two copies rarely agree exactly (an ICE
43 to Hamburg-Altona appeared once with 20 stops and once with 19), which is
why that match is deliberately loose. Regional cannot be matched that way,
because "S1" runs in half of Europe, so it is matched on geography instead:
two different trains do not share an origin, a destination and a departure
minute. A match only ever counts between two different feeds — what one
publisher lists twice is its own business. That merge finds 3,538
duplicates, most of them French regional trains that were being drawn twice.

SNCF's own trains are the one date that could not be reconciled: the newest
openly mirrored TER, TGV and Intercités timetable is from early 2025 and has
no overlap at all with the 2026 windows of the others, so those run on their
own Wednesday beside everyone else's. Two weekday timetables a year apart
differ in detail, not in character — but the page says so in the meta line,
the legend and the data notes. Paris is the exception to the exception: the
RER and Transilien come from Île-de-France Mobilités and *are* on 10 June
2026.

**It starts light.** The full map is 70,427 trains and 4.4 MB gzipped, most
of it regional services. Waiting for all of that before the first frame is
the wrong trade, so `build/split_layers.py` cuts the dataset in two: the
long-distance spine — 7,205 trains, **390 kB** — paints immediately, and the
63,222 regional services are fetched afterwards and merged in. Nothing is
dropped; the small trains simply arrive a moment later. First paint is
eleven times lighter than it was.

For the fullest version of any one country, its own map is still there.

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
reframe the same animation; each carries its own water anchor for the clock,
the legend counts only what is inside the frame, and `#chicago`-style
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

## The France page

`#fr` is **14,996 trains**: 14,256 TER, RER and Transilien, 645 TGV, 87
Intercités and 8 Intercités de Nuit. The TGV star radiating out of Paris is
the whole French network in one picture, and the green knot at its centre is
the RER.

Two things to know, and the page leads with both. **The date is old on
purpose.** SNCF publishes TER, TGV and Intercités as open GTFS, but its own
servers and `transport.data.gouv.fr` are unreachable from this build
environment; the only copies within reach are Mobility Database mirrors
carrying a January-to-April 2025 timetable, and the TGV mirror's window
closes on 21 February. Rather than dress an old schedule up as current, the
map is built on a real Wednesday inside that window — Wednesday 5 February
2025, labelled as 2025 everywhere it appears.

**Paris runs on a different day.** SNCF's own Transilien mirror is a 2019
snapshot, far too old to draw, and for a long time that meant the busiest
suburban network in Europe was simply absent and Paris looked like a modest
provincial city. Île-de-France Mobilités publishes the whole region and its
mirror *is* current — 31 May to 2 July 2026 — so the RER and Transilien come
from there, on Wednesday 10 June 2026. That is 5,162 trains, a third of the
map, keeping a clock sixteen months away from their neighbours', which is a
real flaw and still the better of the two: an empty Paris was the bigger
lie. Only heavy rail is taken from that feed; the Métro and the trams are a
city network, not this map.

Night trains took a small piece of detective work: the Intercités de Nuit
are not labelled as night services and run under plain line numbers (770B
is Paris Austerlitz to Nice), so `build/build_fr.py` identifies them by the
hours they keep — still under way at two in the morning. That finds all
eight and leaves the last suburban runs of the evening alone.

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

The landscape tour is a second exporter. Where `export_video.js` holds one
frame still for a whole day, `export_tour.js` moves: a scripted camera flies
over France, the Benelux, Switzerland and Germany while the clock runs,
lingering on the morning hours when the network fills up, and closes in on
Berlin -- where the city's own map, the S-Bahn, U-Bahn and trams the national
feeds leave out, fades in over the top.

```sh
python3 -m http.server 8000 &
node build/export_tour.js --url http://localhost:8000/index.html \
     --out rail-tour.mp4
```

The route is the `KEYS` table at the top of the file: `[video second, clock
time, longitude, latitude, span in degrees]`. The camera eases in and out of
every key, and its span is interpolated multiplicatively so flying in reads
as evenly as flying out; a span of `0` means the network's own full frame.
The clock is deliberately *not* eased -- an ease has zero slope at each key,
so an eased clock would stop the day dead every time the flight settled. It
runs on a monotone cubic through the same keys instead, which keeps the rate
continuous without ever letting it reach zero: time never stalls.

The clock times themselves are measured, not chosen. "Too slow" is a
judgement about pixels: a wide shot and a close-up can run the same
simulated minutes per second and look nothing alike, because at the
whole-Europe frame a 200 km/h train crosses a handful of pixels a second and
over Berlin an S-Bahn crosses fifty. Left alone this route ran from 6 to 237
px/s -- a 39x spread -- and the wide stretches read as a crawl.

```sh
node build/export_tour.js --timeline /tmp/tl.json
python3 build/tour_pace.py /tmp/tl.json data/eu-trains.json \
        data/eu-trains-2.json --alpha 0.6 --keys 0 7 15 26 38 44 50 56 62 \
        72 82 90 99 110 118 126 136
```

`tour_pace.py` walks the same dataset the film draws, steps it by one video
second at each point along the route, and reports the median pixel speed of
the dots inside the frame. Apparent speed is proportional to the clock rate,
so it can then solve for the clock that evens it out and print the column to
paste back into `KEYS`. `--alpha 1` flattens the film to one constant speed,
which turns out to be too much -- a constant speed spends so little clock
over Berlin that the close-up drifts out of the evening peak entirely.
**0.6** is what shipped: 10 to 88 px/s, an 8x spread, the slowest stretches
nearly doubled and a city still visibly busier than a continent. The Berlin close-up is
rendered a second time against `#berlin` with the identical camera and clock
and cross-faded on by ffmpeg, which is why the legend changes to the city's
categories as it appears. The camera is driven through `window.railCam`, a
hook the page exposes for this: synthesised wheel events cannot place a frame
precisely enough to interpolate.
Frames are kept under `--frames` and reused if they are already there, so
retouching one pass costs minutes rather than half an hour.

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
build/export_tour.js  index.html -> landscape flyover MP4
build/tour_pace.py    measures the flyover's on-screen train speed
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

**Code: MIT** — see [`LICENSE`](LICENSE). That covers `index.html`, the
builders under `build/` and this documentation. Use it for anything,
including commercially; fork it, change it, ship it. The single condition is
that the copyright notice travels with it, which is the standard way of
saying "credit where it came from".

**Data: not MIT.** Everything under `data/` is derived from
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
| Paris region timetable | Île-de-France Mobilités | publisher's open-data terms |
| France timetable | SNCF open data (TER, TGV, Intercités), via the Mobility Database mirror | SNCF's open licence |
| Cross-border high-speed | Eurostar (incl. former Thalys) | publisher's open-data terms |
| Combined-map basemap, France basemap | [Natural Earth](https://www.naturalearthdata.com/) via world-atlas | public domain |
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
