"""Graf dróg pieszych MudNav w kaflach 0,5° × 0,5° (format MNWT) – cała Polska, Czechy i Słowacja, miasta, lasy i góry.

Silnik tras w telefonie dociąga kafle w trakcie liczenia trasy, więc trasa może iść przez dowolną liczbę kafli
(Kraków → Zakopane tak samo jak spacer po parku). Graf jest „ściągnięty”: zostają tylko skrzyżowania (i węzły na
brzegu kafla), a kształt drogi między nimi zapisany jest jako lista punktów pośrednich w różnicach współrzędnych.

Każdy odcinek OSM (dwa kolejne węzły drogi) należy do kafla swojego pierwszego węzła. Węzeł, który występuje
w kilku kaflach, jest w każdym z nich węzłem brzegowym z listą pozostałych kafli – silnik łączy kafle po
identycznych współrzędnych (ten sam węzeł OSM).

Format pliku <nazwa>.mnwt (cały w gzip), liczby jako varint (bez znaku), wartości ze znakiem jako zigzag:
  'MNWT' u16 wersja=1 u16 0 | i32 latIdx i32 lonIdx (kafel: lat = idx·0,5 − 90, lon = idx·0,5 − 180)
  varint liczbaWęzłów, liczbaOdcinków, liczbaBrzegowych
  węzły:     zz Δlat, zz Δlon [mikrostopnie, względem poprzedniego węzła; pierwszy względem rogu kafla],
             varint wysokość+1000 (0 = brak)
  odcinki:   varint a, zz (b − a), varint flagi (jak w walkgraph.py), varint liczbaPunktówPośrednich,
             punkty: zz Δlat, zz Δlon (względem poprzedniego punktu, zaczynając od węzła a), zz Δwysokości
             (pierwszy względem wysokości węzła a; brak wysokości = 0)
  brzegowe:  varint węzeł, varint liczbaKafli, dla każdego zz ΔlatIdx, zz ΔlonIdx

Użycie:
  python3 walktiles.py osm wejście.osm.pbf S W N E katalog   – kafle w prostokącie S W N E (wyrównanym do 0,5°)
  python3 walktiles.py v1 graf.walk.gz katalog               – kafle z grafu walkgraph.py (testy porównawcze)
"""
import gzip
import math
import os
import struct
import sys
from collections import defaultdict

TILE = 0.5
NO_ELE = None


def tile_of(lat, lon):
    return (math.floor((lat + 90) / TILE), math.floor((lon + 180) / TILE))


def tile_name(t):
    lat = t[0] * TILE - 90
    lon = t[1] * TILE - 180
    return f"{'N' if lat >= 0 else 'S'}{round(abs(lat) * 100):04d}{'E' if lon >= 0 else 'W'}{round(abs(lon) * 100):05d}"


def varint(buf, v):
    if v < 0:
        raise ValueError(v)
    while v >= 0x80:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    buf.append(v)


def zz(buf, v):
    varint(buf, (v << 1) if v >= 0 else ((-v << 1) - 1))


def build_tiles(lat, lon, ele, edges, out_dir, only=None):
    """lat/lon: listy mikrostopni, ele: wysokości (int albo None), edges: (a, b, flagi).
    only: zbiór kafli do zapisania (None – wszystkie). Zwraca listę (nazwa, rozmiar)."""
    node_tile = [tile_of(la / 1e6, lo / 1e6) for la, lo in zip(lat, lon)]
    by_tile = defaultdict(list)          # kafel → numery odcinków
    appears = defaultdict(set)           # węzeł → kafle, w których występuje
    for i, (a, b, _) in enumerate(edges):
        t = node_tile[a]
        by_tile[t].append(i)
        appears[a].add(t)
        appears[b].add(t)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for t, eids in sorted(by_tile.items()):
        if only is not None and t not in only:
            continue
        data = encode_tile(t, eids, lat, lon, ele, edges, appears)
        path = os.path.join(out_dir, tile_name(t) + '.mnwt')
        with gzip.open(path, 'wb', compresslevel=9) as f:
            f.write(data)
        written.append((tile_name(t), os.path.getsize(path)))
    return written


def encode_tile(t, eids, lat, lon, ele, edges, appears):
    # Sąsiedztwo w obrębie kafla.
    adj = defaultdict(list)  # węzeł → [(odcinek, sąsiad)]
    for i in eids:
        a, b, _ = edges[i]
        if a == b:
            continue
        adj[a].append((i, b))
        adj[b].append((i, a))

    def junction(n):
        nb = adj[n]
        if len(nb) != 2 or len(appears[n]) > 1:
            return True
        return edges[nb[0][0]][2] != edges[nb[1][0]][2]

    junctions = {n for n in adj if junction(n)}
    used = set()
    chains = []  # (a, b, flagi, [węzły pośrednie])

    def walk(start, first_edge, nxt):
        path = []
        e, cur, prev = first_edge, nxt, start
        used.add(e)
        while cur not in junctions:
            path.append(cur)
            (e1, n1), (e2, n2) = adj[cur]
            e, nn = (e2, n2) if e1 == e else (e1, n1)
            if e in used:
                break
            used.add(e)
            prev, cur = cur, nn
        return cur, path

    for j in sorted(junctions):
        for e, n in adj[j]:
            if e in used:
                continue
            end, mids = walk(j, e, n)
            chains.append((j, end, edges[e][2], mids))
    # Pętle bez skrzyżowania (np. droga dookoła stawu bez odgałęzień) – jeden węzeł staje się skrzyżowaniem.
    for n in sorted(adj):
        for e, nb in adj[n]:
            if e in used:
                continue
            junctions.add(n)
            end, mids = walk(n, e, nb)
            chains.append((n, end, edges[e][2], mids))

    # Węzły posortowane przestrzennie (komórki ~1 km, wężykiem) – małe różnice współrzędnych.
    def key(n):
        cy, cx = lat[n] // 10000, lon[n] // 10000
        return (cy, cx if cy % 2 == 0 else -cx, lat[n], lon[n])

    order = sorted(junctions, key=key)
    idx = {n: i for i, n in enumerate(order)}
    corner_lat = round((t[0] * TILE - 90) * 1e6)
    corner_lon = round((t[1] * TILE - 180) * 1e6)
    buf = bytearray(b'MNWT')
    buf += struct.pack('<HHii', 1, 0, t[0], t[1])
    boundary = [n for n in order if len(appears[n]) > 1]
    varint(buf, len(order)); varint(buf, len(chains)); varint(buf, len(boundary))
    pl, po = corner_lat, corner_lon
    for n in order:
        zz(buf, lat[n] - pl); zz(buf, lon[n] - po)
        pl, po = lat[n], lon[n]
        varint(buf, 0 if ele[n] is None else max(0, ele[n] + 1000))
    for a, b, fl, mids in sorted(chains, key=lambda c: (idx[c[0]], idx[c[1]])):
        ia, ib = idx[a], idx[b]
        varint(buf, ia); zz(buf, ib - ia); varint(buf, fl); varint(buf, len(mids))
        pl, po = lat[a], lon[a]
        pe = ele[a] if ele[a] is not None else 0
        for m in mids:
            zz(buf, lat[m] - pl); zz(buf, lon[m] - po)
            me = ele[m] if ele[m] is not None else pe
            zz(buf, me - pe)
            pl, po, pe = lat[m], lon[m], me
    for n in boundary:
        varint(buf, idx[n])
        others = sorted(appears[n] - {t})
        varint(buf, len(others))
        for o in others:
            zz(buf, o[0] - t[0]); zz(buf, o[1] - t[1])
    return bytes(buf)


def from_v1(path):
    raw = gzip.open(path).read()
    assert raw[:4] == b'MNWG'
    n, e = struct.unpack_from('<ii', raw, 24)
    lat, lon, ele = [], [], []
    p = 32
    for _ in range(n):
        la, lo, el = struct.unpack_from('<iih', raw, p)
        p += 10
        lat.append(la); lon.append(lo); ele.append(None if el == -32768 else el)
    edges = []
    for _ in range(e):
        a, b, fl = struct.unpack_from('<iiH', raw, p)
        p += 10
        edges.append((a, b, fl))
    return lat, lon, ele, edges


def from_osm(src, s, w, n, e):
    """Wszystkie drogi piesze z pliku (całe drogi, także wystające poza prostokąt – potrzebne do brzegów kafli)."""
    sys.path.insert(0, os.path.dirname(__file__))
    from walkgraph import Relations, Ways, Dem  # noqa: E402
    rel = Relations()
    rel.apply_file(src)
    ways = Ways(rel.way_colors(), (-90, -180, 90, 180))
    ways.apply_file(src, locations=True)
    dem = Dem()
    lat = [round(la * 1e6) for la, _ in ways.nodes]
    lon = [round(lo * 1e6) for _, lo in ways.nodes]
    ele = []
    for la, lo in ways.nodes:
        v = dem.at(la, lo) if s - 0.1 <= la <= n + 0.1 and w - 0.1 <= lo <= e + 0.1 else None
        ele.append(None if v is None else round(v))
    return lat, lon, ele, ways.edges


def main(argv):
    if argv[1] == 'v1':
        lat, lon, ele, edges = from_v1(argv[2])
        out, only = argv[3], None
    else:
        s, w, n, e = (float(x) for x in argv[3:7])
        lat, lon, ele, edges = from_osm(argv[2], s, w, n, e)
        out = argv[7]
        t0, t1 = tile_of(s + 1e-9, w + 1e-9), tile_of(n - 1e-9, e - 1e-9)
        only = {(a, b) for a in range(t0[0], t1[0] + 1) for b in range(t0[1], t1[1] + 1)}
    written = build_tiles(lat, lon, ele, edges, out, only)
    total = sum(sz for _, sz in written)
    print(f'kafle: {len(written)}, razem {total / 1e6:.1f} MB (węzłów OSM {len(lat)}, odcinków {len(edges)})')
    for name, sz in written:
        print(f'  {name} {sz / 1e3:.0f} kB')


if __name__ == '__main__':
    main(sys.argv)
