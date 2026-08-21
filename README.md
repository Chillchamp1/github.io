# A Wednesday on the German rail network

A 24-hour time-lapse of every scheduled long-distance train in Germany, drawn
from the published timetable. At sunset the map flips to night.

Open `index.html` — it is self-contained, so a local double-click works as well
as GitHub Pages. No server, no build step, no network calls except the webfont.

## What is on screen

| Category | Drawn as |
|---|---|
| **ICE / TGV / RJ** | high-speed, full-size dot |
| **IC / EC** | intercity, full-size dot |
| **RE / RB** | regional, half-size dot — deliberately the quietest mark |
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

`data/trains.json` is built from [`fredlockheed/db-fv-gtfs`](https://github.com/fredlockheed/db-fv-gtfs),
an unofficial GTFS conversion of DB's public API by Patrick Brosi. The bundled
extract is **Wednesday 6 March 2019**, a normal midweek day away from holidays
and timetable changes: 713 trains, 565 stations.

Night services are complete for that day: 20 NightJet and 9 EuroNight runs, none
dropped by the filters. Sixty trips cross midnight, and they are drawn on both
sides of it; note that half of those are ordinary ICE and IC services finishing
late, not night trains.

**The feed is long-distance only.** It carries four regional routes in total, so
that category is nearly empty — a property of the source, not of the German
network, which runs on the order of 20,000 regional services a day. Regional
coverage needs a second feed; see below.

`data/germany.json` is the basemap: the national outline and the sixteen state
borders, from [`isellsoap/deutschlandGeoJSON`](https://github.com/isellsoap/deutschlandGeoJSON)
(Unlicense, public domain), reduced to three-decimal coordinates.

## Rebuilding

```sh
git clone https://github.com/fredlockheed/db-fv-gtfs /tmp/db-fv-gtfs
python3 build/build_gtfs.py /tmp/db-fv-gtfs/2019 20190306 -o data/trains.json
python3 build/bundle.py          # inlines the JSON back into index.html
```

`build_gtfs.py` takes any GTFS feed and any service date. It reads `calendar.txt`
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
python3 build/build_gtfs.py de_rv 20260826 -o data/trains.json
python3 build/bundle.py
```

The regional feed is far larger, so expect a heavier JSON and thin the trip list
if the animation drops frames. For a current long-distance feed use `de_fv` the
same way — the 2019 extract is bundled only because it is small.

## Layout

```
index.html            the whole visualisation, data inlined
data/trains.json      generated timetable extract
data/germany.json     generated basemap rings
build/build_gtfs.py   GTFS -> JSON
build/build_geo.py    GeoJSON -> compact rings
build/bundle.py       both JSON files -> inlined into index.html
```

## Colour

The four categories use the first three slots of a colourblind-safe categorical
palette plus a neutral. The three hues clear all-pairs CVD and normal-vision
separation against *both* the day and the night background; no fourth hue does,
which is why night trains are grey rather than a fourth colour.
