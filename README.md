# A Wednesday on the German rail network

A 24-hour time-lapse of one real day of German rail traffic — every scheduled
long-distance train in the country, plus the full regional service of the VBB
area (Berlin-Brandenburg) — drawn from published timetables. At sunset the map
flips to night.

Open `index.html` — it is self-contained, so a local double-click works as well
as GitHub Pages. No server, no build step, no network calls except the webfont.

## What is on screen

| Category | Drawn as |
|---|---|
| **ICE / TGV / RJ** | high-speed, full-size dot |
| **IC / EC** | intercity, full-size dot |
| **RE / RB / IRE** | regional, half-size dot — deliberately the quietest mark |
| **NJ / EN** | night services, neutral grey |

Urban transit — S-Bahn, U-Bahn, tram, bus — is filtered out; at national scale
it would bury everything else. Each train carries a 20-minute tail so the
direction of travel reads at a glance. Only the largest cities are named. A
faint outline of Germany with its state borders sits underneath for orientation.

Hover a train for its number and destination. Space bar toggles playback. On
phones the map keeps a full screen to itself and the legend, figures and
controls sit below the fold.

## Day and night

The switch is driven by the real position of the sun over central Germany
(NOAA low-precision solar position). Whenever the sun is below the horizon the
whole map is dark — one clean change at sunset rather than a gradual fade. For
6 March that lands at about 17:58.

## The data

Two feeds, one real day: **Wednesday 4 May 2016**, the busiest ordinary
Wednesday the two sources have in common. 2,179 trains, 948 stations.

**Long distance** comes from [`fredlockheed/db-fv-gtfs`](https://github.com/fredlockheed/db-fv-gtfs)
(CC BY 4.0 API data), an unofficial GTFS conversion of DB's public API by
Patrick Brosi — 618 ICE/IC/EC plus TGV, RJ and D trains nationwide.

**Regional** comes from the 2016 VBB GTFS
([`derhuerst/vbb-gtfs`](https://github.com/derhuerst/vbb-gtfs), CC BY 3.0,
originally published on Berlin's open-data portal). The CSVs were deleted from
that repository's working tree years ago but survive as plain blobs in its git
history; `build/extract_vbb.py` pulls the rail slice straight out of commit
`53995ef` (valid 2016-04-21 to 2016-12-10). That gives 1,529 real RE/RB/IRE
runs on the day — **for the VBB area only**. No nationwide regional timetable
is publicly mirrored anywhere this build environment can reach; swapping in the
full gtfs.de regional feed (below) removes that limitation.

Night services are complete: every NJ/EN/CNL/D night run in the national feed
survives the filters, and trips crossing midnight are drawn on both sides of
it. Rail-replacement buses carrying RE/RB-style names (VBB route_type 700) are
excluded, as is all urban transit.

## Rebuilding

```sh
git clone https://github.com/fredlockheed/db-fv-gtfs /tmp/db-fv-gtfs
git clone --filter=blob:none --no-checkout \
    https://github.com/derhuerst/vbb-gtfs /tmp/vbb-gtfs
python3 build/extract_vbb.py /tmp/vbb-gtfs /tmp/vbb-regional
python3 build/build_gtfs.py /tmp/db-fv-gtfs/2016 /tmp/vbb-regional 20160504 \
    -o data/trains.json --note "Regional coverage is the VBB area ..."
python3 build/bundle.py          # inlines the JSON back into index.html
```

`build_gtfs.py` takes one or more GTFS feeds and any service date they share. It reads `calendar.txt`
and `calendar_dates.txt`, keeps rail and drops urban transit, and writes a
compact JSON of stations and stop-time sequences. Nothing in `index.html` is
specific to this feed.

The basemap only needs rebuilding if you change the geometry:

```sh
python3 build/build_geo.py outline.geo.json states.geo.json -o data/germany.json
```

### Adding real regional trains

[gtfs.de](https://gtfs.de/en/feeds/) publishes Germany-wide feeds derived from
the DELFI dataset under CC BY-SA 4.0 — `de_rv` is regional rail, `de_fv` is
long distance. Both work with the extractor as-is:

```sh
curl -o de_rv.zip https://download.gtfs.de/germany/rv_free/latest.zip
unzip -d de_rv de_rv.zip
python3 build/build_gtfs.py de_fv de_rv 20260826 -o data/trains.json
python3 build/bundle.py
```

That replaces the VBB-only regional layer with nationwide coverage and moves
the day to the present. The nationwide regional feed is roughly 20,000 trips a
day, so expect a much heavier JSON; thin the trip list if the animation drops
frames. The 2016 extracts are bundled only because they are what is reachable
from this build environment.

## Layout

```
index.html            the whole visualisation, data inlined
data/trains.json      generated timetable extract
data/germany.json     generated basemap rings
build/build_gtfs.py   GTFS feed(s) -> JSON, merged onto one service date
build/extract_vbb.py  VBB rail-regional slice out of git history
build/build_geo.py    GeoJSON -> compact rings
build/bundle.py       both JSON files -> inlined into index.html
```

## Colour

The four categories use the first three slots of a colourblind-safe categorical
palette plus a neutral. The three hues clear all-pairs CVD and normal-vision
separation against *both* the day and the night background; no fourth hue does,
which is why night trains are grey rather than a fourth colour.
