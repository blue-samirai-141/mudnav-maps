"""Uproszczenie granic obszarów (lasy, łąki, pola, zabudowa, parki) w danych map MudNav.

Obszary to największa część map krajów (w Krakowie ok. 38%), a ich granice w OSM mają punkt co kilka metrów.
Przy największym przybliżeniu mapy (zoom 18) różnicy poniżej TOLERANCE_M nie widać, więc zostawiamy tylko punkty
potrzebne do kształtu (Douglas–Peucker). Uproszczone są całe linie OSM – granica wspólna dla dwóch obszarów zmienia
się w obu tak samo, więc między obszarami nie powstają szpary.

Bez zmian zostają linie, które są też drogą, torem, rzeką, granicą itp. (mają inne tagi niż obszar) i wody.

Wynik: plik z uproszczonymi liniami i plik z ich numerami (do `osmium removeid`, patrz maps.yml / map-size.yml).
Użycie: python3 areas.py wejście.osm.pbf linie.osm.pbf numery.txt
"""
import os
import sys

import osmium

sys.path.insert(0, os.path.dirname(__file__))
from trails import simplify  # noqa: E402

TOLERANCE_M = float(os.environ.get('MUDNAV_AREA_SIMPLIFY_M', '2.5'))
AREA_KEYS = ('landuse', 'natural', 'leisure')
# Obszary, których nie upraszczamy: wody (kształt brzegu jest ważny na mapie) i drobnica punktowa.
SKIP_NATURAL = {'water', 'coastline', 'bay', 'spring', 'peak', 'tree', 'cave_entrance', 'saddle', 'rock', 'stone'}
# Linia z takim kluczem to coś więcej niż granica obszaru – zostaje dokładna.
OTHER_KEYS = ('highway', 'railway', 'waterway', 'boundary', 'barrier', 'power', 'building', 'aeroway', 'man_made')


def is_area(tags):
    if tags.get('natural') in SKIP_NATURAL or tags.get('landuse') in ('reservoir', 'basin'):
        return False
    return any(k in tags for k in AREA_KEYS)


def main(src, out, ids_out):
    members = set()
    for r in osmium.FileProcessor(src).with_filter(osmium.filter.EntityFilter(osmium.osm.RELATION)):
        if r.tags.get('type') == 'multipolygon' and is_area(r.tags):
            members.update(m.ref for m in r.members if m.type == 'w')
    done = points_before = points_after = 0
    with osmium.SimpleWriter(out, overwrite=True) as w, open(ids_out, 'w') as ids:
        for o in osmium.FileProcessor(src).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
            t = o.tags
            if any(k in t for k in OTHER_KEYS):
                continue
            if not (is_area(t) or (o.id in members and len(t) == 0)):
                continue
            if len(o.nodes) < 5 or not all(n.location.valid() for n in o.nodes):
                continue
            closed = o.nodes[0].ref == o.nodes[-1].ref
            pts = [(n.ref, n.location.lat, n.location.lon) for n in o.nodes]
            keep = simplify(pts[:-1] if closed else pts, TOLERANCE_M)
            if closed:
                if len(keep) < 3:
                    continue
                keep = keep + [keep[0]]
            if len(keep) >= len(pts):
                continue
            w.add_way(o.replace(nodes=keep))
            ids.write(f'w{o.id}\n')
            done += 1
            points_before += len(pts)
            points_after += len(keep)
    print(f'obszary: uproszczono {done} linii, punkty {points_before} → {points_after}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
