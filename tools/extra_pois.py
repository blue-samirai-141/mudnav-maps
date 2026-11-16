"""Dodatkowe punkty mapy MudNav: pomniki przyrody, wodospady, źródła rzek, kapliczki i krzyże, wieże widokowe.

W OSM pomnik przyrody to zwykle drzewo albo skała z dopiskiem denotation=natural_monument – a drzew są setki
tysięcy, więc zapis mapy nie może brać wszystkich. Tu wybieramy tylko te ciekawe i zapisujemy je jako osobne punkty
z jednym tagiem mn_poi=<rodzaj> (+ nazwa i wysokość), który styl MudNav rysuje własną ikoną.
Id punktów przesunięte o OFFSET (rosnąco), więc plik da się scalić `osmium merge`.

Użycie: python3 extra_pois.py dane.osm.pbf wynik.osm.pbf
"""
import datetime
import math
import sys

import osmium

OFFSET = 2 * 10 ** 12


# Odcinek potoku nazwany jak wodospad (np. „Wodogrzmoty Mickiewicza” – w OSM to fragment Roztoki, a pojedyncze
# progi to Wyżni/Pośredni/Niżni Wodogrzmot). Taka nazwa to „zespół wodospadów” – jeden punkt zamiast trzech.
GROUP_WORDS = ('wodogrzmot', 'wodospad', 'vodopád', 'vodopad', 'kaskad', 'kaskád')
GROUP_HIDES_M = 300


def group_waterfall(t):
    return t.get('waterway') in ('stream', 'river') and any(w in t.get('name', '').lower() for w in GROUP_WORDS)


def kind(t):
    if t.get('denotation') == 'natural_monument' or 'pomnik przyrody' in t.get('name', '').lower():
        return 'monument'
    if t.get('waterway') == 'waterfall' or t.get('natural') == 'waterfall':
        return 'waterfall'
    if t.get('natural') == 'spring' and any(w in t.get('name', '').lower() for w in ('źródło', 'źródła', 'zdroj', 'prameň')):
        return 'source'
    if t.get('historic') in ('wayside_shrine', 'wayside_cross') or (t.get('historic') == 'memorial' and t.get('memorial') == 'cross'):
        return 'shrine'
    if t.get('man_made') == 'tower' and t.get('tower:type') == 'observation':
        return 'tower'
    return None


def main(src, out):
    now = datetime.datetime.now(datetime.timezone.utc)
    found = []
    for o in osmium.FileProcessor(src).with_locations().with_filter(osmium.filter.EmptyTagFilter()):
        k = 'waterfall_group' if o.is_way() and group_waterfall(o.tags) else kind(o.tags)
        if not k or (k != 'waterfall_group' and o.is_way() and o.tags.get('waterway') in ('stream', 'river')):
            continue
        if o.is_node():
            loc = o.location
            lat, lon = loc.lat, loc.lon
        elif o.is_way():
            pts = [n.location for n in o.nodes if n.location.valid()]
            if not pts:
                continue
            lat, lon = sum(p.lat for p in pts) / len(pts), sum(p.lon for p in pts) / len(pts)
        else:
            continue
        tags = {'mn_poi': k}
        for key in ('name', 'ele'):
            if key in o.tags:
                tags[key] = o.tags[key]
        found.append((lat, lon, tags))
    groups = [(lat, lon) for lat, lon, t in found if t['mn_poi'] == 'waterfall_group']

    def near_group(lat, lon):
        k = math.cos(math.radians(lat)) * 111_320
        return any(math.hypot((lat - a) * 111_320, (lon - b) * k) < GROUP_HIDES_M for a, b in groups)

    # Pojedyncze progi przy zespole wypadają (na mapie i przy nazywaniu punktu trasy byłby „Niżni Wodogrzmot”).
    found = [(lat, lon, {**t, 'mn_poi': 'waterfall'}) if t['mn_poi'] == 'waterfall_group' else (lat, lon, t)
             for lat, lon, t in found if t['mn_poi'] != 'waterfall' or not near_group(lat, lon)]
    with osmium.SimpleWriter(out, overwrite=True) as w:
        for i, (lat, lon, tags) in enumerate(found):
            w.add_node(osmium.osm.mutable.Node(id=OFFSET + i + 1, version=1, timestamp=now, location=(lon, lat), tags=tags))
    counts = {}
    for *_, t in found:
        counts[t['mn_poi']] = counts.get(t['mn_poi'], 0) + 1
    print('dodatkowe punkty:', counts)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
