"""Szlaki turystyczne do map offline.

Z relacji route=hiking bierze kolor szlaku (osmc:symbol, np. „red:white:red_bar”, albo colour) i dla każdej
drogi, po której biegnie szlak, dopisuje osobną linię z tagami trail_red / trail_blue / … = yes. Linia ma te same
punkty co droga i id przesunięte o OFFSET (rosnąco, więc plik da się scalić `osmium merge`). Mapsforge nie zna
relacji – bez tego mapa offline nie wie, którędy idzie szlak.

Użycie: python3 trails.py hiking.osm.pbf trails.osm.pbf
(hiking.osm.pbf = osmium tags-filter dane.osm.pbf r/route=hiking – relacje z drogami)
"""
import sys
import osmium

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
        for way in osmium.FileProcessor(src, osmium.osm.WAY):
            cols = ways.get(way.id)
            if not cols or len(way.nodes) < 2:
                continue
            tags = {f'trail_{c}': 'yes' for c in sorted(cols)}
            # Wersja i czas jak w oryginale – osmosis odrzuca obiekty bez nich.
            w.add_way(osmium.osm.mutable.Way(
                id=OFFSET + way.id, version=max(way.version, 1), timestamp=way.timestamp,
                nodes=[nd.ref for nd in way.nodes], tags=tags,
            ))
            n += 1
    print(f'szlaki: {len(ways)} dróg w relacjach, {n} linii szlaków')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
