"""Ubezpieczenia i ekspozycja na szlakach – co naprawdę jest w danych OSM (przed oznaczeniem łańcuchów na mapie i w 3D).

Dla dróg pieszych w prostokącie liczy wszystkie znaczniki (poza nazwami i źródłami) na odcinkach trudnych (sac_scale od
T3 albo highway=via_ferrata) i na ich węzłach, oraz urwiska (natural=cliff) w odległości do 30 m od takich odcinków.
Wynik: lista klucz=wartość z liczbą wystąpień i przykładowymi drogami – na tej podstawie wybieramy, które znaczniki
(np. via_ferrata_scale, safety_rope, ladder, hazard) wziąć do map i grafu tras. Nic nie zapisuje do map.

Użycie: python3 hazards_probe.py wejście.osm.pbf S W N E [wynik.md]
Przykład (Orla Perć i okolice): python3 hazards_probe.py malopolskie-latest.osm.pbf 49.20 19.95 49.25 20.10
"""
import math
import sys
from collections import Counter, defaultdict

import osmium

SAC = {'hiking': 1, 'mountain_hiking': 2, 'demanding_mountain_hiking': 3, 'alpine_hiking': 4,
       'demanding_alpine_hiking': 5, 'difficult_alpine_hiking': 6}
FOOT = {'path', 'footway', 'steps', 'via_ferrata', 'track', 'ladder'}
SKIP = ('name', 'source', 'note', 'fixme', 'description', 'wikidata', 'wikipedia', 'osmc:', 'ref', 'operator', 'created_by')
# Znaczniki, o które pytamy wprost (kandydaci na „łańcuchy / klamry / drabinki / ekspozycja”) – także gdy ich nie ma.
CANDIDATES = ('highway=via_ferrata', 'via_ferrata_scale', 'safety_rope', 'safety:rope', 'climbing', 'ladder', 'highway=ladder',
              'handrail', 'hazard', 'exposure', 'chain', 'chains', 'trail_visibility', 'scramble', 'sac_scale')


def keep(k):
    return not any(k == s or k.startswith(s) for s in SKIP)


class Probe(osmium.SimpleHandler):
    def __init__(self, box):
        super().__init__()
        self.s, self.w, self.n, self.e = box
        self.way_tags = Counter()
        self.examples = defaultdict(list)
        self.node_tags = Counter()
        self.hard_nodes = {}       # id węzła → (lat, lon)
        self.cliffs = []           # listy punktów urwisk
        self.hard_ways = 0
        self.tagged_nodes = {}     # id → tagi (wszystkie węzły z tagami w prostokącie)

    def inside(self, lat, lon):
        return self.s <= lat <= self.n and self.w <= lon <= self.e

    def node(self, n):
        if n.tags and self.inside(n.location.lat, n.location.lon):
            self.tagged_nodes[n.id] = {t.k: t.v for t in n.tags if keep(t.k)}

    def way(self, w):
        t = {x.k: x.v for x in w.tags}
        pts = [(nd.location.lat, nd.location.lon) for nd in w.nodes if nd.location.valid()]
        if not pts or not any(self.inside(*p) for p in pts):
            return
        if t.get('natural') == 'cliff':
            self.cliffs.append(pts)
            return
        hw = t.get('highway')
        if hw not in FOOT:
            return
        hard = SAC.get(t.get('sac_scale', ''), 0) >= 3 or hw == 'via_ferrata'
        if not hard:
            return
        self.hard_ways += 1
        label = f"{t.get('name', '(bez nazwy)')} (w{w.id})"
        for k, v in t.items():
            if keep(k):
                kv = f'{k}={v}'
                self.way_tags[kv] += 1
                if len(self.examples[kv]) < 3:
                    self.examples[kv].append(label)
        for nd in w.nodes:
            if nd.location.valid():
                self.hard_nodes[nd.ref] = (nd.location.lat, nd.location.lon)


def dist_m(a, b):
    dy = (a[0] - b[0]) * 111_000
    dx = (a[1] - b[1]) * 111_000 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def main(src, s, w, n, e, out=None):
    p = Probe((s, w, n, e))
    p.apply_file(src, locations=True)
    for nid in p.hard_nodes:
        for k, v in p.tagged_nodes.get(nid, {}).items():
            p.node_tags[f'{k}={v}'] += 1
    # Urwiska blisko trudnych odcinków: siatka węzłów (komórki ~50 m), sprawdzamy komórkę punktu urwiska i sąsiednie.
    cell = 0.0005
    grid = defaultdict(list)
    for q in p.hard_nodes.values():
        grid[(int(q[0] // cell), int(q[1] // cell))].append(q)

    def close(a):
        cy, cx = int(a[0] // cell), int(a[1] // cell)
        return any(dist_m(a, b) <= 30 for dy in (-1, 0, 1) for dx in (-1, 0, 1) for b in grid.get((cy + dy, cx + dx), ()))
    near = sum(1 for c in p.cliffs if any(close(a) for a in c))
    lines = [f'# Ubezpieczenia i ekspozycja – {src} [{s},{w},{n},{e}]', '',
             f'Trudnych odcinków (T3+ / via ferrata): {p.hard_ways}; urwisk (natural=cliff) w prostokącie: {len(p.cliffs)}, '
             f'z tego do 30 m od trudnych odcinków: {near}.', '', '## Kandydaci (łańcuchy, klamry, drabinki, ekspozycja)', '']
    for c in CANDIDATES:
        hits = {kv: x for kv, x in list(p.way_tags.items()) + list(p.node_tags.items()) if kv == c or kv.split('=')[0] == c}
        lines.append(f'- `{c}`: ' + (', '.join(f'`{kv}` ×{x}' for kv, x in sorted(hits.items(), key=lambda i: -i[1])) or 'brak'))
    lines += ['', '## Wszystkie znaczniki trudnych odcinków', '', '| znacznik | odcinków | przykłady |', '|---|---|---|']
    for kv, x in p.way_tags.most_common():
        lines.append(f'| `{kv}` | {x} | {"; ".join(p.examples[kv])} |')
    lines += ['', '## Znaczniki węzłów na trudnych odcinkach', '', '| znacznik | węzłów |', '|---|---|']
    for kv, x in p.node_tags.most_common():
        lines.append(f'| `{kv}` | {x} |')
    text = '\n'.join(lines) + '\n'
    if out:
        open(out, 'w', encoding='utf-8').write(text)
    print(text)


if __name__ == '__main__':
    a = sys.argv
    main(a[1], float(a[2]), float(a[3]), float(a[4]), float(a[5]), a[6] if len(a) > 6 else None)
