"""Budynki do map krajów MudNav – w odchudzonej postaci.

Zwykłe budynki to około połowy danych OSM, dlatego mapy krajów ich dotąd nie miały. Tu zostaje sam obrys:
 - jeden tag building=yes (bez adresów, numerów domów, rodzaju, liczby pięter),
 - bez drobnicy: garaży, szop, wiat, altan i wszystkiego poniżej MIN_AREA_M2 (na mapie turystycznej to szum),
 - budynki z nazwą albo funkcją (schronisko, kościół, sklep…) pomijamy – te są już w danych z pełnymi tagami.
Wynik to same linie (bez punktów); punkty dobiera potem `osmium getid` (patrz maps.yml).

Użycie: python3 buildings.py budynki-zrodlo.osm.pbf budynki-linie.osm.pbf
"""
import math
import sys

import osmium

MIN_AREA_M2 = 30.0
SMALL = {'garage', 'garages', 'shed', 'hut', 'roof', 'carport', 'greenhouse', 'kiosk', 'toilets', 'container',
         'service', 'transformer_tower', 'outbuilding', 'gazebo', 'ruins', 'construction', 'no'}
# Klucze, po których dane kraju i tak zostawiają obiekt (filtr „Odchudzenie danych” w maps.yml).
KEPT_ELSEWHERE = ('name', 'highway', 'railway', 'aeroway', 'aerialway', 'waterway', 'natural', 'landuse', 'leisure',
                  'amenity', 'tourism', 'historic', 'man_made', 'place', 'sport', 'shop', 'military', 'water',
                  'wetland', 'mountain_pass', 'piste:type')


def area_m2(nodes):
    pts = [(n.location.lon, n.location.lat) for n in nodes if n.location.valid()]
    if len(pts) < 4:
        return 0.0
    k = math.cos(math.radians(pts[0][1])) * 111_320.0
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s += (x1 * k) * (y2 * 111_320.0) - (x2 * k) * (y1 * 111_320.0)
    return abs(s) / 2.0


def main(src, out):
    kept = small = other = 0
    with osmium.SimpleWriter(out, overwrite=True) as w:
        # Punkty służą tylko do policzenia powierzchni – do Pythona trafiają same linie (dużo szybciej).
        for o in osmium.FileProcessor(src).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
            t = o.tags
            b = t.get('building')
            if not b:
                continue
            if any(k in t for k in KEPT_ELSEWHERE) or t.get('power') in ('line', 'minor_line', 'tower'):
                other += 1
                continue
            if b in SMALL or len(o.nodes) < 4 or o.nodes[0].ref != o.nodes[-1].ref or area_m2(o.nodes) < MIN_AREA_M2:
                small += 1
                continue
            w.add_way(o.replace(tags={'building': 'yes'}))
            kept += 1
    print(f'budynki: {kept} obrysów, pominięto {small} drobnych i {other} z nazwą/funkcją (są już w danych)')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
