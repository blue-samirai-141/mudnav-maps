"""Podpisy jezior do map MudNav – jeden na jezioro, w jego środku.

Zapis mapy Mapsforge tnie duże wielokąty na kawałki kafli i styl podpisywał każdy kawałek osobno („Śniardwy”
trzy razy na ekranie, „Guber” nawet na lesie obok). Tu dla każdego nazwanego zbiornika powstaje jeden punkt
mn_water_label=<wielkość> w miejscu najdalszym od brzegu (polylabel), a styl podpisuje tylko te punkty.
Wielkość decyduje, od którego przybliżenia widać podpis (duże jeziora wcześniej, stawy dopiero z bliska).

Użycie: python3 water_labels.py woda.osm.pbf wynik.osm.pbf
(woda.osm.pbf = osmium tags-filter dane.osm.pbf nwr/natural=water nwr/landuse=reservoir,basin nwr/water)
"""
import datetime
import math
import sys

import osmium
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import polylabel

OFFSET = 4 * 10 ** 12
SKIP_WATER = {'river', 'stream', 'canal', 'ditch', 'drain', 'wastewater', 'moat', 'stream_pool'}


def size(km2):
    if km2 >= 3:
        return 'huge'
    if km2 >= 0.3:
        return 'big'
    if km2 >= 0.03:
        return 'medium'
    return 'small'


def main(src, out):
    found = {}
    for a in osmium.FileProcessor(src).with_areas().with_filter(osmium.filter.EntityFilter(osmium.osm.AREA)):
        t = a.tags
        name = t.get('name')
        if not name:
            continue
        if not (t.get('natural') == 'water' or t.get('landuse') in ('reservoir', 'basin')):
            continue
        if t.get('water') in SKIP_WATER:
            continue
        polys = []
        for outer in a.outer_rings():
            ring = [(n.lon, n.lat) for n in outer if n.location.valid()]
            if len(ring) < 4:
                continue
            holes = [[(n.lon, n.lat) for n in inner if n.location.valid()] for inner in a.inner_rings(outer)]
            p = Polygon(ring, [h for h in holes if len(h) >= 4])
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty:
                polys.append(p)
        if not polys:
            continue
        shape = max(polys, key=lambda p: p.area) if len(polys) > 1 else polys[0]
        if isinstance(shape, MultiPolygon):
            shape = max(shape.geoms, key=lambda p: p.area)
        lat0 = shape.centroid.y
        k = 111.32 ** 2 * math.cos(math.radians(lat0))
        km2 = sum(p.area for p in polys) * k
        # Dokładność ~1/50 szerokości jeziora – szybko i wystarczająco do podpisu.
        minx, miny, maxx, maxy = shape.bounds
        pt = polylabel(shape, tolerance=max(maxx - minx, maxy - miny) / 50)
        key = (name, round(pt.y, 2), round(pt.x, 2))
        if key in found and found[key][3] >= km2:
            continue
        found[key] = (pt.y, pt.x, name, km2)
    now = datetime.datetime.now(datetime.timezone.utc)
    counts = {}
    with osmium.SimpleWriter(out, overwrite=True) as w:
        for i, (lat, lon, name, km2) in enumerate(sorted(found.values())):
            s = size(km2)
            counts[s] = counts.get(s, 0) + 1
            w.add_node(osmium.osm.mutable.Node(id=OFFSET + i + 1, version=1, timestamp=now, location=(lon, lat),
                                               tags={'mn_water_label': s, 'name': name}))
    print('podpisy jezior:', counts)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
