"""Obszary chronione do map MudNav: parki narodowe, parki krajobrazowe, rezerwaty, Natura 2000.

W OSM są to zwykle relacje type=boundary – zapis mapy Mapsforge bierze tylko relacje type=multipolygon, więc
np. Tatrzański Park Narodowy w ogóle nie trafiał do mapy. Tu granica każdego obszaru staje się liniami z tagiem
mn_protect=<rodzaj>, a nazwa punktem mn_protect_label=<rodzaj> – styl MudNav rysuje każdy rodzaj inaczej.
Plik wynikowy scala się z danymi `osmium merge` (drogi i węzły granic są już w danych).

Użycie: python3 protected.py granice.osm.pbf wynik.osm.pbf
(granice.osm.pbf = osmium tags-filter dane.osm.pbf r/boundary=national_park,protected_area r/leisure=nature_reserve)
"""
import datetime
import sys

import osmium

OFFSET = 3 * 10 ** 12
# Psy – z tagu dog= na obszarze w OSM (tylko gdy jest wpisany; bez tagu nic nie pokazujemy, żeby nie zgadywać).
DOG = {'no': 'zakaz_wstepu', 'leashed': 'na_smyczy', 'yes': 'dozwolone'}


def kind(t):
    b, pc = t.get('boundary'), t.get('protect_class', '')
    title = (t.get('protection_title', '') + ' ' + t.get('name', '')).lower()
    if b == 'national_park' or pc == '2' or 'park narodowy' in title or 'národný park' in title or 'národní park' in title:
        return 'national_park'
    if 'natura 2000' in title or pc == '97' or t.get('designation', '').lower().startswith('natura'):
        return 'natura2000'
    if 'park krajobrazowy' in title or 'chránená krajinná oblasť' in title or 'chráněná krajinná oblast' in title or pc == '5':
        return 'landscape_park'
    if t.get('leisure') == 'nature_reserve' or pc in ('1', '1a', '1b', '4') or 'rezerwat' in title or 'rezervácia' in title or 'rezervace' in title:
        return 'reserve'
    return None


def main(src, out):
    """Granica każdego obszaru jako OTWARTE linie (zamknięte zapis mapy przycinałby do kafli – siatka kwadratów)
    i nazwa jako jeden punkt w środku obszaru (podpis raz, a nie w każdym kaflu)."""
    rels = []
    for r in osmium.FileProcessor(src, osmium.osm.RELATION):
        k = kind(r.tags)
        if k:
            rels.append((k, r.tags.get('name'), [m.ref for m in r.members if m.type == 'w' and m.role != 'inner'], DOG.get(r.tags.get('dog', ''))))
    need = {ref for _, _, refs in rels for ref in refs}
    ways = {}
    for w in osmium.FileProcessor(src).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
        if w.id in need:
            ways[w.id] = [(n.ref, n.location.lat, n.location.lon) for n in w.nodes if n.location.valid()]
    now = datetime.datetime.now(datetime.timezone.utc)
    nodes, lines, n = [], [], {}
    nid = wid = OFFSET
    for k, name, refs, dog in rels:
        pts_all = []
        for ref in refs:
            pts = ways.get(ref)
            if not pts or len(pts) < 2:
                continue
            ids = [p[0] for p in pts]
            pts_all += pts
            if ids[0] == ids[-1]:  # zamknięta – ostatni punkt jako osobny węzeł w tym samym miejscu
                nid += 1
                nodes.append((nid, pts[-1][1], pts[-1][2], {}))
                ids[-1] = nid
            wid += 1
            lines.append((wid, ids, {'mn_protect': k}))
        if name and pts_all:
            lat = sum(p[1] for p in pts_all) / len(pts_all)
            lon = sum(p[2] for p in pts_all) / len(pts_all)
            nid += 1
            nodes.append((nid, lat, lon, {'mn_protect_label': k, 'name': name, **({'mn_dog': dog} if dog else {})}))
        n[k] = n.get(k, 0) + 1
    with osmium.SimpleWriter(out, overwrite=True) as w:
        for i, lat, lon, tags in nodes:
            w.add_node(osmium.osm.mutable.Node(id=i, version=1, timestamp=now, location=(lon, lat), tags=tags))
        for i, ids, tags in lines:
            w.add_way(osmium.osm.mutable.Way(id=i, version=1, timestamp=now, nodes=ids, tags=tags))
    print('obszary chronione:', n)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
