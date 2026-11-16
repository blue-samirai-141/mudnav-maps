"""Poziomice do map offline – z danych wysokościowych (SRTM 1", kafle „skadi” z otwartego zbioru Terrain Tiles na AWS).

Dla prostokąta mapy składa kafle wysokości w jedną siatkę, lekko wygładza i wyznacza poziomice co 10 m. Wynik to plik
OSM z liniami o tagu mn_contour = 100 / 50 / 20 / 10 (najwyższa klasa, do której należy wysokość) – styl MudNav pokazuje
je stopniowo przy zbliżaniu. Poziomice co 100 m mają wysokość w tagu name (podpis na linii).
Przy okazji zapisuje odchudzone kafle wysokości (3", format HGT) – z nich aplikacja liczy cieniowanie rzeźby terenu.

Użycie: python3 contours.py S W N E wynik.osm.pbf [katalog_kafli_hgt]
"""
import datetime
import gzip
import math
import os
import subprocess
import sys
import urllib.request

import numpy as np
import osmium
from contourpy import contour_generator
from shapely.geometry import LineString

SRC = 'https://s3.amazonaws.com/elevation-tiles-prod/skadi/{ns}/{ns}{ew}.hgt.gz'
N1 = 3601          # próbek na stopień + 1 (SRTM 1")
NODE0, WAY0 = 9 * 10 ** 12, 9 * 10 ** 12
TOLERANCE = 0.00004  # ok. 4 m – upraszczanie linii


def tile(lat, lon, cache='dem-cache'):
    ns, ew = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}", f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
    path = os.path.join(cache, f'{ns}{ew}.hgt')
    if not os.path.exists(path):
        os.makedirs(cache, exist_ok=True)
        url = SRC.format(ns=ns, ew=ew)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    open(path, 'wb').write(gzip.decompress(r.read()))
                break
            except Exception as e:  # brak kafla (morze) albo chwilowy błąd sieci
                if attempt == 3:
                    print('brak kafla', url, e)
                    return None, f'{ns}{ew}'
    a = np.fromfile(path, dtype='>i2').reshape(N1, N1).astype(np.float32)
    a[a < -500] = 0  # dziury w danych
    return a, f'{ns}{ew}'


def smooth(a):
    k = np.array([1, 2, 1], dtype=np.float32) / 4
    a = np.apply_along_axis(lambda m: np.convolve(m, k, mode='same'), 0, a)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode='same'), 1, a)


def klass(ele):
    return '100' if ele % 100 == 0 else '50' if ele % 50 == 0 else '20' if ele % 20 == 0 else '10'


def main(s, w, n, e, out, hgt_out=None):
    lat0, lat1, lon0, lon1 = math.floor(s), math.ceil(n), math.floor(w), math.ceil(e)
    rows, cols = (lat1 - lat0) * (N1 - 1) + 1, (lon1 - lon0) * (N1 - 1) + 1
    grid = np.zeros((rows, cols), dtype=np.float32)
    for la in range(lat0, lat1):
        for lo in range(lon0, lon1):
            a, name = tile(la, lo)
            if a is None:
                continue
            r, c = (lat1 - 1 - la) * (N1 - 1), (lo - lon0) * (N1 - 1)
            grid[r:r + N1, c:c + N1] = a
            if hgt_out:  # kafel 3" (1201 × 1201) do cieniowania w aplikacji
                os.makedirs(hgt_out, exist_ok=True)
                smooth(a)[::3, ::3].round().astype('>i2').tofile(os.path.join(hgt_out, name + '.hgt'))
    # Wycinek z marginesem, żeby poziomice dochodziły do krawędzi mapy.
    m = 0.01
    r0, r1 = max(0, int((lat1 - (n + m)) * 3600)), min(rows, int((lat1 - (s - m)) * 3600) + 1)
    c0, c1 = max(0, int((w - m - lon0) * 3600)), min(cols, int((e + m - lon0) * 3600) + 1)
    sub = smooth(grid[r0:r1, c0:c1])
    lons, lats = lon0 + np.arange(c0, c1) / 3600, lat1 - np.arange(r0, r1) / 3600
    gen = contour_generator(x=lons, y=lats, z=sub)
    now = datetime.datetime.now(datetime.timezone.utc)
    lines, npts = [], 0
    for ele in range(int(sub.min() // 10 * 10) + 10, int(sub.max()) + 1, 10):
        if ele <= 0:
            continue
        for ln in gen.lines(ele):
            if len(ln) < 8:
                continue
            xy = np.asarray(LineString(ln).simplify(TOLERANCE, preserve_topology=False).coords)
            if len(xy) >= 2:
                lines.append((ele, xy))
                npts += len(xy)
    node, way = NODE0, WAY0
    nodes_file = out + '.nodes.osm.pbf'
    with osmium.SimpleWriter(nodes_file, overwrite=True) as wr:
        for ele, xy in lines:
            for lo, la in xy:
                node += 1
                wr.add_node(osmium.osm.mutable.Node(id=node, version=1, timestamp=now, location=(float(lo), float(la))))
    # Osmosis chce najpierw wszystkie punkty, potem linie – drugi przebieg dopisuje linie do osobnego pliku.
    ways_file = out + '.ways.osm.pbf'
    node = NODE0
    with osmium.SimpleWriter(ways_file, overwrite=True) as wr:
        for ele, xy in lines:
            ids = list(range(node + 1, node + 1 + len(xy)))
            node += len(xy)
            # Poziomica zamknięta w pętlę ZOSTAJE otwartą linią (ostatni punkt to osobny węzeł w tym samym miejscu):
            # zamkniętą drogę zapis mapy traktuje jak obszar i przycina do kafli z prostymi bokami – na mapie
            # wychodziła siatka kwadratów z podpisami wysokości w złych miejscach.
            # Mapsforge przyjmuje linie do 2000 punktów bez problemu – dłuższe tniemy.
            for i in range(0, len(ids) - 1, 1900):
                part = ids[i:i + 1901]
                if len(part) < 2:
                    continue
                way += 1
                tags = {'mn_contour': klass(ele)}
                if ele % 100 == 0:
                    tags['name'] = str(ele)
                wr.add_way(osmium.osm.mutable.Way(id=way, version=1, timestamp=now, nodes=part, tags=tags))
    subprocess.run(['osmium', 'cat', nodes_file, ways_file, '-o', out, '--overwrite'], check=True)
    os.remove(nodes_file)
    os.remove(ways_file)
    print(f'poziomice: {len(lines)} linii, {npts} punktów, {way - WAY0} odcinków ({sub.min():.0f}–{sub.max():.0f} m)')


if __name__ == '__main__':
    a = sys.argv
    main(float(a[1]), float(a[2]), float(a[3]), float(a[4]), a[5], a[6] if len(a) > 6 else None)
