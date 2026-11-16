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
    # Relacje szlaków bywają zagnieżdżone: długi szlak (np. Główny Szlak Beskidzki) dzieli się na etapy, a kolor
    # (osmc:symbol) ma tylko relacja nadrzędna. Etap bez koloru dziedziczy go od rodzica – inaczej odpadał z mapy
    # i szlak był urywany.
    rels = {}
    for rel in osmium.FileProcessor(src, osmium.osm.RELATION):
        if rel.tags.get('route') not in ('hiking', 'foot'):
            continue
        rels[rel.id] = (color(rel.tags), [m.ref for m in rel.members if m.type == 'w'],
                        [m.ref for m in rel.members if m.type == 'r'])
    resolved = {rid: c for rid, (c, _, _) in rels.items() if c}
    for _ in range(4):  # do czterech poziomów zagnieżdżenia
        changed = False
        for rid, (c, _, children) in rels.items():
            pc = resolved.get(rid)
            if not pc:
                continue
            for ch in children:
                if ch in rels and ch not in resolved:
                    resolved[ch] = pc
                    changed = True
        if not changed:
            break
    ways = {}
    for rid, (_, members, _) in rels.items():
        c = resolved.get(rid)
        if not c:
            continue
        for ref in members:
            ways.setdefault(ref, set()).add(c)
    # Odcinki szlaku: każda droga osobno (w mieście ulica bywa pocięta na dziesiątki krótkich kawałków).
    parts = []
    for way in osmium.FileProcessor(src).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
        cols = ways.get(way.id)
        if not cols or len(way.nodes) < 2:
            continue
        # Trasy narciarskie wpisane do relacji szlaku (bez drogi/ścieżki) nie są szlakiem pieszym.
        if 'piste:type' in way.tags and 'highway' not in way.tags:
            continue
        if not all(nd.location.valid() for nd in way.nodes):
            continue
        parts.append((way.id, tuple(sorted(cols)), [(nd.ref, nd.location.lat, nd.location.lon) for nd in way.nodes],
                      max(way.version, 1), way.timestamp))
    # Łączenie kolejnych odcinków o tych samych kolorach w długie linie – kreskowanie szlaku idzie wtedy równo,
    # a nie zaczyna się od nowa na każdym kawałku ulicy (szlaki w miastach wyglądały na poszarpane).
    merged = []
    by_cols = {}
    for p in parts:
        by_cols.setdefault(p[1], []).append(p)
    for cols, group in by_cols.items():
        ends = {}
        for idx, p in enumerate(group):
            ends.setdefault(p[2][0][0], []).append(idx)
            ends.setdefault(p[2][-1][0], []).append(idx)
        used = [False] * len(group)
        for idx, p in enumerate(group):
            if used[idx]:
                continue
            used[idx] = True
            line = list(p[2])
            for forward in (True, False):
                while True:
                    tip = line[-1][0] if forward else line[0][0]
                    nxt = next((k for k in ends.get(tip, []) if not used[k]), None)
                    if nxt is None:
                        break
                    used[nxt] = True
                    seg = group[nxt][2]
                    if forward:  # dokładamy na końcu: odcinek ma zaczynać się w tip
                        if seg[0][0] != tip:
                            seg = seg[::-1]
                        line = line + seg[1:]
                    else:  # dokładamy na początku: odcinek ma kończyć się w tip
                        if seg[-1][0] != tip:
                            seg = seg[::-1]
                        line = seg[:-1] + line
            merged.append((p[0], cols, line, p[3], p[4]))
    n = 0
    with osmium.SimpleWriter(out, overwrite=True) as w:
        for wid, cols, line, ver, ts in sorted(merged, key=lambda m: m[0]):
            nodes = simplify(line)
            for i in range(0, len(nodes) - 1, 1900):
                chunk = nodes[i:i + 1901]
                if len(chunk) < 2:
                    continue
                w.add_way(osmium.osm.mutable.Way(
                    id=OFFSET + wid * 4 + (i // 1900) % 4, version=ver, timestamp=ts, nodes=chunk,
                    tags={f'trail_{c}': 'yes' for c in cols},
                ))
                n += 1
    print(f'szlaki: {len(ways)} dróg w relacjach, {len(parts)} odcinków połączonych w {n} linii')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
