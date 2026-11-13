"""Buduje maps.json (katalog dla aplikacji) z gotowych plików .map i regions.json."""
import datetime, hashlib, json, os, sys

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def main(maps_dir, out, merge=None, url_base=None):
    cfg = json.load(open('regions.json', encoding='utf-8'))
    today = datetime.date.today().isoformat()
    regions = []
    for kind, items in (('range', cfg['ranges']), ('country', cfg['countries'])):
        for r in items:
            path = os.path.join(maps_dir, r['id'] + '.map')
            if not os.path.exists(path):
                print('brak', path)
                continue
            regions.append({
                'id': r['id'], 'name': r['name'], 'kind': kind, 'file': r['id'] + '.map',
                'sizeBytes': os.path.getsize(path), 'sha256': sha256(path),
                'bbox': r.get('bbox', []), 'date': today,
                # Niezmienny adres tej wersji (wydanie maps-<przebieg>): rozpoczęte pobieranie dokończy się,
                # nawet gdy w międzyczasie wyjdą nowe mapy.
                **({'url': url_base.rstrip('/') + '/' + r['id'] + '.map'} if url_base else {}),
            })
    # Częściowa publikacja (np. same pasma): mapy niezbudowane teraz zostają z poprzedniego katalogu.
    if merge and os.path.exists(merge):
        try:
            old = json.load(open(merge, encoding='utf-8')).get('regions', [])
        except ValueError:
            old = []
        fresh = {r['id'] for r in regions}
        known = {r['id'] for items in (cfg['ranges'], cfg['countries']) for r in items}
        regions += [r for r in old if r.get('id') not in fresh and r.get('id') in known]
        order = [r['id'] for items in (cfg['ranges'], cfg['countries']) for r in items]
        regions.sort(key=lambda r: order.index(r['id']))
    json.dump({'generated': today, 'baseUrl': '', 'regions': regions}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(len(regions), 'map w katalogu')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[4] if len(sys.argv) > 4 else None)
