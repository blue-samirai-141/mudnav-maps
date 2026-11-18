"""Trasy wzorcowe z BRoutera (brouter.de, profil hiking-mountain) do porównania z silnikiem tras MudNav.

Użycie: python3 brouter_ref.py routing-tests.json katalog_wynikowy
Dla każdej trasy zapisuje <nr>.geojson (pierwszy wariant BRoutera).
"""
import json
import os
import sys
import time
import urllib.request

URL = 'https://brouter.de/brouter?lonlats={ll}&profile=hiking-mountain&alternativeidx=0&format=geojson'


def main(tests, out):
    os.makedirs(out, exist_ok=True)
    cfg = json.load(open(tests, encoding='utf-8'))
    for i, r in enumerate(cfg['routes']):
        ll = '|'.join(f'{lon:.6f},{lat:.6f}' for lat, lon in r['points'])
        for attempt in range(3):
            try:
                req = urllib.request.Request(URL.format(ll=ll), headers={'User-Agent': 'MudNav-routing-test'})
                body = urllib.request.urlopen(req, timeout=60).read()
                open(os.path.join(out, f'{i:02d}.geojson'), 'wb').write(body)
                props = json.loads(body)['features'][0]['properties']
                print(f"{i:02d} {r['name']}: {int(props['track-length']) / 1000:.2f} km, ↑{props.get('filtered ascend')} m, "
                      f"{int(props['total-time']) // 60} min")
                break
            except Exception as e:  # serwer publiczny – chwilowe błędy
                print(f'{i:02d} {r["name"]}: próba {attempt + 1} nieudana: {e}')
                time.sleep(5)
        time.sleep(2)  # nie obciążamy publicznego serwera


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
