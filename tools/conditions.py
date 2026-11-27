#!/usr/bin/env python3
"""Plik warunków dla aplikacji (conditions.json): komunikat lawinowy w postaci, którą MudNav maluje na mapie.

Aplikacja pobiera ten plik (1–2 KB) przy każdym uruchomieniu i sama koloruje stoki z kafli wysokości, które już ma
(nachylenie ≥ 30°, wysokość, wystawa) – nowy komunikat nie wymaga pobierania map.

Źródła:
  --caaml URL|PLIK   komunikat w standardzie EAWS CAAML v6 (JSON) – jeśli TOPR go udostępni (sprawdza avalanche-probe.yml);
  --manual JSON      komunikat wpisany ręcznie (akcja conditions.yml, pole „manual”) – do testów i do czasu parsera TOPR.
Format --manual (przykład, komunikat TOPR z 26.11.2026):
  {"validUntil":"2026-11-27T20:00:00+01:00","publishedAt":"2026-11-26T17:17:00+01:00","tendency":"steady",
   "levels":[{"level":2,"minM":1600},{"level":1,"maxM":1600}],
   "problems":[{"type":"persistent_weak_layers","minM":1800,"aspects":"all"},
               {"type":"wind_slab","minM":"treeline","aspects":"all"},{"type":"new_snow","maxM":"treeline","aspects":"all"}]}
Użycie: python3 tools/conditions.py [--caaml X | --manual JSON] [--region tatry-pl] WYJŚCIE.json
"""
import argparse, datetime as dt, json, sys, urllib.request

ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
REGIONS = {
    # S, W, N, E; kraj – aplikacja koloruje tylko stoki w tym kraju (komunikat TOPR nie dotyczy słowackiej strony).
    "tatry-pl": {"name": "Tatry Wysokie i Tatry Zachodnie", "source": "TOPR", "url": "https://lawiny.topr.pl/",
                 "bbox": [49.14, 19.72, 49.33, 20.25], "country": "PL", "treelineM": 1500},
}
PROBLEMS = {  # typy EAWS → nazwy jak w komunikacie TOPR
    "new_snow": "Świeży śnieg", "wind_slab": "Deski śnieżne utworzone przez wiatr",
    "persistent_weak_layers": "Słabe warstwy w starej pokrywie", "wet_snow": "Mokry śnieg", "gliding_snow": "Śnieg ślizgający się",
}

def elev(v, treeline):
    if v is None or v == "": return None
    if isinstance(v, str) and v.lower() == "treeline": return treeline
    return int(v)

def norm_aspects(a):
    if a in (None, "all", "*"): return ASPECTS
    return [x for x in ASPECTS if x in a]

def from_manual(m, region):
    t = region["treelineM"]
    return {
        "publishedAt": m.get("publishedAt"), "validFrom": m.get("validFrom") or m.get("publishedAt"), "validUntil": m["validUntil"],
        "tendency": m.get("tendency"),
        "levels": [{k: elev(v, t) if k in ("minM", "maxM") else v for k, v in l.items()} for l in m["levels"]],
        "problems": [{"type": p["type"], "name": PROBLEMS.get(p["type"], p["type"]), "minM": elev(p.get("minM"), t),
                      "maxM": elev(p.get("maxM"), t), "aspects": norm_aspects(p.get("aspects"))} for p in m.get("problems", [])],
    }

def from_caaml(doc, region):
    """EAWS CAAML v6 JSON: bulletins[].dangerRatings / avalancheProblems (bez części „pm” – pierwszy okres)."""
    b = (doc.get("bulletins") or [doc])[0]
    t = region["treelineM"]
    def bound(e, key):
        v = (e or {}).get(key)
        return elev(v, t) if v is not None else None
    levels = []
    names = {"low": 1, "moderate": 2, "considerable": 3, "high": 4, "very_high": 5}
    for r in b.get("dangerRatings", []):
        lvl = names.get(r.get("mainValue"))
        if lvl: levels.append({"level": lvl, "minM": bound(r.get("elevation"), "lowerBound"), "maxM": bound(r.get("elevation"), "upperBound")})
    problems = [{"type": p.get("problemType"), "name": PROBLEMS.get(p.get("problemType"), p.get("problemType")),
                 "minM": bound(p.get("elevation"), "lowerBound"), "maxM": bound(p.get("elevation"), "upperBound"),
                 "aspects": norm_aspects(p.get("aspects"))} for p in b.get("avalancheProblems", [])]
    vt = b.get("validTime", {})
    return {"publishedAt": b.get("publicationTime"), "validFrom": vt.get("startTime"), "validUntil": vt.get("endTime"),
            "tendency": ((b.get("tendency") or [{}])[0]).get("tendencyType"), "levels": levels, "problems": problems}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--caaml"); ap.add_argument("--manual"); ap.add_argument("--region", default="tatry-pl")
    a = ap.parse_args()
    region = REGIONS[a.region]
    if a.manual:
        bulletin = from_manual(json.loads(a.manual), region)
    elif a.caaml:
        raw = urllib.request.urlopen(a.caaml, timeout=30).read() if a.caaml.startswith("http") else open(a.caaml, "rb").read()
        bulletin = from_caaml(json.loads(raw), region)
    else:
        bulletin = None
    out = {"version": 1, "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "avalanche": []}
    if bulletin and bulletin["levels"]:
        out["avalanche"].append({"region": a.region, **{k: region[k] for k in ("name", "source", "url", "bbox", "country", "treelineM")}, **bulletin})
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    sys.exit(main())
