"""Graf dróg pieszych dla silnika tras MudNav (offline, Android i iOS).

Z pliku OSM bierze wszystko, po czym da się iść: ścieżki, chodniki, drogi gruntowe, ulice, schody – w mieście i w górach.
Autostrady, drogi ekspresowe i drogi z zakazem ruchu pieszego pomija. Każdy odcinek (między kolejnymi węzłami OSM)
dostaje: klasę drogi, trudność SAC (T1–T6), kolory szlaków znakowanych (z relacji route=hiking) i chodnik przy drodze.
Węzły dostają wysokość z SRTM 1" (te same kafle co poziomice – tools/contours.py).

Format (little-endian, cały plik w gzip):
  'MNWG' u16 wersja=1 u16 0 | i32 minLatE6 minLonE6 maxLatE6 maxLonE6 | i32 liczbaWęzłów i32 liczbaOdcinków
  węzły:    i32 latE6, i32 lonE6, i16 wysokość [m] (-32768 = brak)
  odcinki:  i32 a, i32 b, u16 flagi
            bity 0–3 klasa (0 ścieżka/chodnik, 1 schody, 2 droga gruntowa, 3 ulica osiedlowa/serwisowa,
                            4 droga lokalna, 5 droga wojewódzka, 6 droga krajowa, 7 via ferrata)
            bity 4–6 SAC (0 brak, 1–6), bity 7–11 kolory szlaków (czerwony, niebieski, zielony, żółty, czarny),
            bit 12 chodnik przy drodze,
            bit 13 tylko w kierunku a→b, bit 14 tylko w kierunku b→a (szlak jednokierunkowy, np. Orla Perć
            Zawrat → Kozi Wierch); bez bitów 13–14 – w obie strony. Starsze aplikacje bity ignorują (zgodne wstecz).

Użycie: python3 walkgraph.py wejście.osm.pbf S W N E wynik.walk.gz
"""
import gzip
import math
import os
import struct
import sys

import numpy as np
import osmium

sys.path.insert(0, os.path.dirname(__file__))
from contours import tile  # noqa: E402  – pobieranie kafli SRTM (wspólne z poziomicami)
from trails import color   # noqa: E402  – kolor szlaku z osmc:symbol (te same reguły co na mapie)

COLOR_BITS = {'red': 0, 'blue': 1, 'green': 2, 'yellow': 3, 'black': 4}
SAC = {'hiking': 1, 'mountain_hiking': 2, 'demanding_mountain_hiking': 3, 'alpine_hiking': 4,
       'demanding_alpine_hiking': 5, 'difficult_alpine_hiking': 6}
CLASS = {
    'path': 0, 'footway': 0, 'pedestrian': 0, 'bridleway': 0, 'cycleway': 0, 'corridor': 0,
    'steps': 1,
    'track': 2,
    'residential': 3, 'living_street': 3, 'service': 3, 'unclassified': 3, 'road': 3,
    'tertiary': 4, 'tertiary_link': 4,
    'secondary': 5, 'secondary_link': 5,
    'primary': 6, 'primary_link': 6, 'trunk': 6, 'trunk_link': 6,
    'via_ferrata': 7,
}
FOOT_OK = {'yes', 'designated', 'permissive', 'official'}
ONEWAY_FWD = 1 << 13
ONEWAY_BWD = 1 << 14
# „oneway” bez dopisku dotyczy pieszych tylko na drogach pieszych (na ulicy czy drodze rowerowej – pojazdów).
FOOT_WAYS = {'path', 'footway', 'steps', 'via_ferrata', 'pedestrian', 'corridor'}


def oneway(t):
    """Kierunek dla pieszego: ONEWAY_FWD (zgodnie z kolejnością węzłów drogi), ONEWAY_BWD (pod prąd) albo 0."""
    v = t.get('oneway:foot')
    if v is None:
        hw = t.get('highway')
        if hw not in FOOT_WAYS:
            return 0
        # Ścieżka rowerowa oznaczona jako „path”: jednokierunkowość dla rowerów, nie dla pieszych.
        if hw == 'path' and t.get('bicycle') == 'designated' and t.get('foot') not in ('designated',):
            return 0
        v = t.get('oneway')
    if v in ('yes', 'true', '1'):
        return ONEWAY_FWD
    if v in ('-1', 'reverse'):
        return ONEWAY_BWD
    return 0


def walkable(t):
    hw = t.get('highway')
    if hw not in CLASS:
        return None
    foot = t.get('foot', '')
    if foot == 'no' or t.get('access') in ('no', 'private') and foot not in FOOT_OK:
        return None
    if t.get('motorroad') == 'yes':
        return None
    # Droga ekspresowa / krajowa bez chodnika i bez jawnej zgody na pieszych – nie prowadzimy.
    if hw in ('trunk', 'trunk_link') and foot not in FOOT_OK and t.get('sidewalk', 'no') in ('no', 'none', 'separate'):
        return None
    return CLASS[hw]


class Relations(osmium.SimpleHandler):
    """Kolory szlaków: relacje route=hiking → bity kolorów dla dróg (z dziedziczeniem po relacji nadrzędnej)."""

    def __init__(self):
        super().__init__()
        self.rels = {}

    def relation(self, r):
        if r.tags.get('route') not in ('hiking', 'foot'):
            return
        self.rels[r.id] = (color(r.tags), [m.ref for m in r.members if m.type == 'w'],
                           [m.ref for m in r.members if m.type == 'r'])

    def way_colors(self):
        parent = {}
        for rid, (_, _, subs) in self.rels.items():
            for s in subs:
                parent.setdefault(s, rid)
        out = {}
        for rid, (c, ways, _) in self.rels.items():
            seen = set()
            cur = rid
            while c is None and cur in parent and cur not in seen:
                seen.add(cur)
                cur = parent[cur]
                c = self.rels.get(cur, (None,))[0]
            if c is None:
                continue
            for w in ways:
                out[w] = out.get(w, 0) | (1 << COLOR_BITS[c])
        return out


class Ways(osmium.SimpleHandler):
    def __init__(self, colors, box):
        super().__init__()
        self.colors = colors
        self.s, self.w, self.n, self.e = box
        self.index = {}       # id węzła OSM → numer w grafie
        self.nodes = []       # (lat, lon)
        self.edges = []       # (a, b, flagi)

    def node_id(self, n):
        i = self.index.get(n.ref)
        if i is None:
            i = len(self.nodes)
            self.index[n.ref] = i
            self.nodes.append((n.location.lat, n.location.lon))
        return i

    def way(self, w):
        t = w.tags
        cls = walkable(t)
        if cls is None:
            return
        sac = SAC.get(t.get('sac_scale', ''), 5 if cls == 7 else 0)
        sidewalk = 1 if t.get('sidewalk', 'no') not in ('no', 'none', 'separate') or t.get('footway') == 'sidewalk' else 0
        flags = cls | (sac << 4) | (self.colors.get(w.id, 0) << 7) | (sidewalk << 12) | oneway(t)
        prev = None
        for n in w.nodes:
            if not n.location.valid():
                prev = None
                continue
            inside = self.s <= n.location.lat <= self.n and self.w <= n.location.lon <= self.e
            cur = self.node_id(n) if inside else None
            if prev is not None and cur is not None and prev != cur:
                self.edges.append((prev, cur, flags))
            prev = cur


class Dem:
    """Wysokość z kafli SRTM 1" (dwuliniowo)."""

    def __init__(self):
        self.cache = {}

    def grid(self, lat, lon):
        key = (lat, lon)
        if key not in self.cache:
            self.cache[key], _ = tile(lat, lon)  # tablica wysokości (float32) albo None
        return self.cache[key]

    def at(self, lat, lon):
        g = self.grid(math.floor(lat), math.floor(lon))
        if g is None:
            return None
        y = (math.floor(lat) + 1 - lat) * 3600
        x = (lon - math.floor(lon)) * 3600
        r, c = min(int(y), 3599), min(int(x), 3599)
        fy, fx = y - r, x - c
        v = g[r:r + 2, c:c + 2].astype(float)
        return v[0, 0] * (1 - fx) * (1 - fy) + v[0, 1] * fx * (1 - fy) + v[1, 0] * (1 - fx) * fy + v[1, 1] * fx * fy


def main(src, s, w, n, e, out):
    rel = Relations()
    rel.apply_file(src)
    colors = rel.way_colors()
    ways = Ways(colors, (s, w, n, e))
    ways.apply_file(src, locations=True)
    dem = Dem()
    with gzip.open(out, 'wb', compresslevel=9) as f:
        f.write(b'MNWG' + struct.pack('<HH', 1, 0))
        f.write(struct.pack('<iiii', *(round(v * 1e6) for v in (s, w, n, e))))
        f.write(struct.pack('<ii', len(ways.nodes), len(ways.edges)))
        buf = bytearray()
        for lat, lon in ways.nodes:
            ele = dem.at(lat, lon)
            buf += struct.pack('<iih', round(lat * 1e6), round(lon * 1e6), -32768 if ele is None else round(ele))
        f.write(buf)
        buf = bytearray()
        for a, b, fl in ways.edges:
            buf += struct.pack('<iiH', a, b, fl)
        f.write(buf)
    marked = sum(1 for *_, fl in ways.edges if fl >> 7 & 31)
    sac = sum(1 for *_, fl in ways.edges if fl >> 4 & 7)
    one = sum(1 for *_, fl in ways.edges if fl & (ONEWAY_FWD | ONEWAY_BWD))
    print(f'{out}: węzłów {len(ways.nodes)}, odcinków {len(ways.edges)} (szlaki {marked}, SAC {sac}, jednokierunkowe {one}), '
          f'{os.path.getsize(out) / 1e6:.1f} MB')


if __name__ == '__main__':
    a = sys.argv
    main(a[1], float(a[2]), float(a[3]), float(a[4]), float(a[5]), a[6])
