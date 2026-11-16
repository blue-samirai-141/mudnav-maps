"""Szlaki turystyczne do map offline.

Z relacji route=hiking bierze kolor szlaku (osmc:symbol, np. „red:white:red_bar”, albo colour) i dla każdej
drogi, po której biegnie szlak, dopisuje osobną linię z tagami trail_red / trail_blue / … = yes. Linia ma te same
punkty co droga i id przesunięte o OFFSET (rosnąco, więc plik da się scalić `osmium merge`). Mapsforge nie zna
relacji – bez tego mapa offline nie wie, którędy idzie szlak.

Użycie: python3 trails.py hiking.osm.pbf trails.osm.pbf
(hiking.osm.pbf = osmium tags-filter dane.osm.pbf r/route=hiking – relacje z drogami)
"""
import math
import sys

import osmium

# Uproszczenie linii szlaku (Douglas–Peucker) – ok. 4 m. Szlaki w skałach mają w OSM dziesiątki drobnych zygzaków;
# linia przesunięta w bok (kilka szlaków obok siebie) robiła na nich kolce zlewające się w czarne plamy.
TOLERANCE_M = 4.0


def simplify(pts, tol=TOLERANCE_M):
    """pts: [(id, lat, lon)] – zwraca id punktów zostających w linii (pierwszy i ostatni zawsze)."""
    if len(pts) < 3:
        return [p[0] for p in pts]
    lat0 = math.radians(pts[0][1])
    xy = [(p[2] * 111_320 * math.cos(lat0), p[1] * 110_540) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            d = abs(dy * (xy[i][0] - ax) - dx * (xy[i][1] - ay)) / norm
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p[0] for p, k in zip(pts, keep) if k]

COLORS = ('red', 'blue', 'green', 'yellow', 'black')
OFFSET = 10 ** 12


def color(tags):
    sym = tags.get('osmc:symbol', '')
    c = sym.split(':', 1)[0].strip().lower() if sym else ''
    if c not in COLORS:
        c = tags.get('colour', '').strip().lower()
    return c if c in COLORS else None


def main(src, out):
    ways = {}
    for rel in osmium.FileProcessor(src, osmium.osm.RELATION):
        if rel.tags.get('route') != 'hiking':
            continue
        c = color(rel.tags)
        if not c:
            continue
        for m in rel.members:
            if m.type == 'w':
                ways.setdefault(m.ref, set()).add(c)
    n = 0
    with osmium.SimpleWriter(out, overwrite=True) as w:
        for way in osmium.FileProcessor(src).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
            cols = ways.get(way.id)
            if not cols or len(way.nodes) < 2:
                continue
            # Trasy narciarskie wpisane do relacji szlaku (bez drogi/ścieżki) nie są szlakiem pieszym.
            if 'piste:type' in way.tags and 'highway' not in way.tags:
                continue
            tags = {f'trail_{c}': 'yes' for c in sorted(cols)}
            # Wersja i czas jak w oryginale – osmosis odrzuca obiekty bez nich.
            w.add_way(osmium.osm.mutable.Way(
                id=OFFSET + way.id, version=max(way.version, 1), timestamp=way.timestamp,
                nodes=simplify([(nd.ref, nd.location.lat, nd.location.lon) for nd in way.nodes if nd.location.valid()])
                if all(nd.location.valid() for nd in way.nodes) else [nd.ref for nd in way.nodes], tags=tags,
            ))
            n += 1
    print(f'szlaki: {len(ways)} dróg w relacjach, {n} linii szlaków')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
