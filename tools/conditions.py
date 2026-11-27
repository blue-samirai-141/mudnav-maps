#!/usr/bin/env python3
"""Pliki warunków dla aplikacji MudNav: komunikaty lawinowe w postaci, którą aplikacja maluje na mapie.

- conditions.json (kilka KB, co godzinę w sezonie): komunikaty – stopnie w strefach wysokości, problemy z wystawami,
  ważność, wydawca i regiony EAWS, których dotyczą. Aplikacja pobiera go przy każdym uruchomieniu.
- avalanche-regions.json (raz na jakiś czas): granice regionów EAWS (licencja CC0, regions.avalanches.org),
  uproszczone do ~50 m – aplikacja koloruje stoki tylko w regionie wydawcy (TOPR nie opisuje słowackiej strony).

Źródła (rozeznanie 27.11.2026, docs/KOMUNIKATY_LAWINOWE.md w MudNavProd):
  TOPR  – lawiny.topr.pl/wp-content/uploads/caaml/caaml_pl_DATA.json (zapas: archiwum EAWS, PL-12)
  HZS   – static.laviny.sk/bulletins/latest/SK_sk_CAAMLv6_2022.json (każdy biuletyn dla swoich mikroregionów SK-xx)
  GOPR  – lawiny.gopr.pl/api/bulletins (Karkonosze PL-01, Babia Góra PL-02, Bieszczady PL-03; Pilsko, Pieniny,
          Śnieżnik – komunikaty opisowe bez stopnia: tylko informacja i link, bez kopiowania treści)
  HS ČR – nie pobieramy (prognoza do użytku niekomercyjnego, adres JSON zwraca 403) – do czasu zgody.
Pokazujemy tylko fakty (stopień, wysokości, wystawy, typ problemu, ważność) i zawsze źródło z linkiem – bez opisów.

Użycie: python3 tools/conditions.py [--topr] [--slovakia] [--gopr] [--regions avalanche-regions.json]
                                    [--manual JSON [--region PL-12]] [--keep URL] conditions.json
Format --manual (przykład): {"validUntil":"2026-11-27T20:00:00+01:00","levels":[{"level":2,"minM":1600},{"level":1,"maxM":1600}],
  "problems":[{"type":"wind_slab","minM":"treeline","aspects":"all"}]}
"""
import argparse, datetime as dt, json, math, sys, urllib.request
sys.setrecursionlimit(100_000)

UA = "MudNav-maps/1.0 (warunki dla aplikacji MudNav)"
ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
TREELINE = {"PL-12": 1500, "PL-01": 1250, "PL-02": 1150, "PL-03": 1150}  # domyślnie 1500 (Tatry, Fatra)
PROBLEMS = {  # typy EAWS → nazwy jak w komunikatach TOPR
    "new_snow": "Świeży śnieg", "wind_slab": "Deski śnieżne utworzone przez wiatr",
    "persistent_weak_layers": "Słabe warstwy w starej pokrywie", "wet_snow": "Mokry śnieg", "gliding_snow": "Śnieg ślizgający się",
    "cornices": "Nawisy",
}
GEOJSON = "https://regions.avalanches.org/micro-regions/latest/{}_micro-regions.geojson.json"
TOPR_BASE = "https://lawiny.topr.pl/wp-content/uploads/caaml/"
EAWS_ARCHIVE = "https://static.avalanche.report/eaws_bulletins/{d}/{d}-{r}.json"
SK_LATEST = "https://static.laviny.sk/bulletins/latest/SK_sk_CAAMLv6_2022.json"
GOPR_API = "https://lawiny.gopr.pl/api/bulletins"
# GOPR: kod rejonu → region EAWS (z granicami) albo przybliżony prostokąt S, W, N, E (rejony bez poligonu EAWS).
GOPR_REGIONS = {
    "RKRK": ("PL-01", "Karkonosze", None), "RBBG": ("PL-02", "Babia Góra", None), "RBSZ": ("PL-03", "Bieszczady", None),
    "RPLS": (None, "Pilsko", [49.51, 19.27, 49.56, 19.36]),
    "RPPN": (None, "Pieniny", [49.38, 20.33, 49.44, 20.48]),
    "RSSN": (None, "Śnieżnik Kłodzki", [50.17, 16.80, 50.23, 16.90]),
}
NAMES = {"PL-12": "Tatry Wysokie i Tatry Zachodnie"}

def http(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()

def log(*a):
    print(*a, file=sys.stderr)

# ------------------------------------------------------------------ granice regionów (EAWS, CC0)

def simplify(pts, tol):
    """Douglas–Peucker na [lat, lon] (tolerancja w stopniach)."""
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        dx, dy = b[1] - a[1], b[0] - a[0]
        n = math.hypot(dx, dy)
        d = math.hypot(p[1] - a[1], p[0] - a[0]) if n == 0 else abs(dy * (p[1] - a[1]) - dx * (p[0] - a[0])) / n
        if d > dmax: dmax, idx = d, i
    if dmax <= tol: return [a, b]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)

def regions(countries=("PL-12", "PL", "SK", "CZ"), tol=0.0005):
    """id → {"rings": [[[lat, lon], …], …], "bbox": [S, W, N, E]} z GeoJSON EAWS (tylko pierścienie zewnętrzne i otwory)."""
    out = {}
    for c in countries:
        try:
            fc = json.loads(http(GEOJSON.format(c)))
        except Exception as ex:  # noqa: BLE001
            log("regiony", c, ex); continue
        for f in fc.get("features", []):
            rid = f.get("properties", {}).get("id")
            g = f.get("geometry") or {}
            polys = g.get("coordinates", []) if g.get("type") == "MultiPolygon" else [g.get("coordinates", [])]
            rings = []
            for poly in polys:
                for ring in poly:
                    pts = [[round(lat, 5), round(lon, 5)] for lon, lat in ring]
                    s = simplify(pts, tol)
                    if len(s) >= 4: rings.append(s)
            if rid and rings:
                lats = [p[0] for r in rings for p in r]; lons = [p[1] for r in rings for p in r]
                out[rid] = {"rings": rings, "bbox": [min(lats), min(lons), max(lats), max(lons)]}
    return out

def union_bbox(boxes):
    boxes = [b for b in boxes if b]
    if not boxes: return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]

# ------------------------------------------------------------------ komunikaty

def elev(v, treeline):
    if v is None or v == "": return None
    if isinstance(v, str) and "tree" in v.lower(): return treeline
    return int(float(v))

def norm_aspects(a):
    if a in (None, "all", "*"): return ASPECTS
    return [x for x in ASPECTS if x in a]

def iso(t):
    """Czas → ISO 8601 z przesunięciem. TOPR pisze np. „2026-11-27T20:00:00000” (bez strefy, czas polski)."""
    if not t: return None
    t = str(t).strip().replace(" ", "T")
    try:
        v = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
        if v.tzinfo is None: raise ValueError
        return v.isoformat()
    except ValueError:
        pass
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.fromisoformat(t[:19]).replace(tzinfo=ZoneInfo("Europe/Warsaw")).isoformat()
    except ValueError:
        return None

def tendency(t):
    if isinstance(t, list): t = t[0] if t else None
    if isinstance(t, dict): return t.get("tendencyType")
    return t if isinstance(t, str) else None

LEVELS = {"low": 1, "moderate": 2, "considerable": 3, "high": 4, "very_high": 5}

def bulletin(b, treeline):
    """Jeden biuletyn CAAML (v6 i odmiany TOPR/GOPR) → stopnie, problemy, czasy."""
    def bound(e, key):
        v = (e or {}).get(key)
        try:
            return elev(v, treeline)
        except (ValueError, TypeError):
            return None
    levels = []
    for r in b.get("dangerRatings", []) or []:
        lvl = LEVELS.get(str(r.get("mainValue", "")).lower())
        if lvl: levels.append({"level": lvl, "minM": bound(r.get("elevation"), "lowerBound"), "maxM": bound(r.get("elevation"), "upperBound")})
    problems = [{"type": p.get("problemType"), "name": PROBLEMS.get(p.get("problemType"), p.get("problemType")),
                 "minM": bound(p.get("elevation"), "lowerBound"), "maxM": bound(p.get("elevation"), "upperBound"),
                 "aspects": norm_aspects(p.get("aspects"))} for p in (b.get("avalancheProblems") or []) if p.get("problemType")]
    vt = b.get("validTime") or {}
    return {"publishedAt": iso(b.get("publicationTime") or b.get("publication_time")), "validFrom": iso(vt.get("startTime")),
            "validUntil": iso(vt.get("endTime")), "tendency": tendency(b.get("tendency")), "levels": levels, "problems": problems}

def bulletins_of(doc):
    if isinstance(doc, list): return doc
    if isinstance(doc, dict): return doc.get("bulletins") or [doc]
    return []

def entry(region, publisher, source, url, name, rids, reg, b, bbox=None, summary=None):
    return {"region": region, "publisher": publisher, "source": source, "url": url, "name": name, "regions": rids,
            "bbox": bbox or union_bbox([reg.get(r, {}).get("bbox") for r in rids]), "treelineM": TREELINE.get(rids[0] if rids else "", 1500),
            **b, **({"summary": summary} if summary else {})}

def topr(reg):
    """TOPR: plik z katalogu, z którego strona robi PDF (dziś albo wczoraj); zapas – archiwum EAWS (PL-12)."""
    today = dt.date.today()
    for d in (today, today - dt.timedelta(days=1)):
        for url in (f"{TOPR_BASE}caaml_pl_{d.isoformat()}.json", EAWS_ARCHIVE.format(d=d.isoformat(), r="PL-12")):
            try:
                docs = bulletins_of(json.loads(http(url)))
            except Exception as ex:  # noqa: BLE001
                log("TOPR", url, ex); continue
            if not docs: continue
            b = bulletin(docs[0], TREELINE["PL-12"])
            if b["levels"]:
                log("TOPR z", url)
                return [entry("PL-12", "TOPR", "TOPR", "https://lawiny.topr.pl/", NAMES["PL-12"], ["PL-12"], reg, b)]
    return []

def slovakia(reg):
    """HZS: każdy biuletyn dla swoich mikroregionów (SK-01 … SK-08)."""
    out = []
    for b in bulletins_of(json.loads(http(SK_LATEST))):
        rids = sorted({r.get("regionID") or r.get("regionId") for r in b.get("regions", []) if str(r.get("regionID") or r.get("regionId") or "").startswith("SK-")})
        if not rids: continue
        names = [r.get("name") for r in b.get("regions", []) if r.get("name")]
        data = bulletin(b, 1500)
        if data["levels"]:
            out.append(entry("+".join(rids), "HZS", "HZS (laviny.sk)", "https://www.laviny.sk/", ", ".join(names) or "Słowacja", rids, reg, data))
    return out

def gopr(reg):
    """GOPR: pełne komunikaty (PL-01…03) ze stopniem; rejony opisowe – tylko informacja o komunikacie, bez treści."""
    out = []
    seen = set()
    for b in bulletins_of(json.loads(http(GOPR_API))):
        if str(b.get("lang", "")).lower() != "pl": continue
        for r in b.get("regions", []):
            code = r.get("regionId") or r.get("regionID")
            if code not in GOPR_REGIONS or code in seen: continue
            seen.add(code)
            eaws, name, box = GOPR_REGIONS[code]
            data = bulletin(b, TREELINE.get(eaws or "", 1200))
            url = f"https://lawiny.gopr.pl/site/{code}"
            # GOPR nie podaje końca ważności – do następnego wydania, najdłużej 30 h od publikacji.
            if not data["validUntil"] and data["publishedAt"]:
                data["validUntil"] = (dt.datetime.fromisoformat(data["publishedAt"]) + dt.timedelta(hours=30)).isoformat()
            if data["levels"] and eaws:
                out.append(entry(eaws, "GOPR", "GOPR", url, name, [eaws], reg, data))
            else:
                data["levels"] = []; data["problems"] = []
                out.append(entry(code, "GOPR", "GOPR", url, name, [eaws] if eaws else [], reg, data, bbox=box or None,
                                 summary="Komunikat opisowy GOPR (bez stopnia zagrożenia) – przeczytaj na stronie GOPR."))
    return out

def from_manual(m, rid, reg):
    t = TREELINE.get(rid, 1500)
    b = {"publishedAt": m.get("publishedAt"), "validFrom": m.get("validFrom") or m.get("publishedAt"), "validUntil": m["validUntil"],
         "tendency": m.get("tendency"),
         "levels": [{k: elev(v, t) if k in ("minM", "maxM") else v for k, v in l.items()} for l in m["levels"]],
         "problems": [{"type": p["type"], "name": PROBLEMS.get(p["type"], p["type"]), "minM": elev(p.get("minM"), t),
                       "maxM": elev(p.get("maxM"), t), "aspects": norm_aspects(p.get("aspects"))} for p in m.get("problems", [])]}
    pub = "TOPR" if rid == "PL-12" else "GOPR" if rid.startswith("PL-") else "HZS" if rid.startswith("SK-") else "HSCR"
    return [entry(rid, pub, pub, m.get("url", "https://lawiny.topr.pl/"), NAMES.get(rid, rid), [rid], reg, b)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--topr", action="store_true"); ap.add_argument("--slovakia", action="store_true"); ap.add_argument("--gopr", action="store_true")
    ap.add_argument("--manual"); ap.add_argument("--region", default="PL-12")
    ap.add_argument("--regions", help="zapisz granice regionów (avalanche-regions.json)")
    ap.add_argument("--keep", help="poprzedni conditions.json: zostają jego wciąż ważne komunikaty regionów, których teraz nie ma")
    a = ap.parse_args()
    reg = regions()
    if a.regions:
        json.dump({"version": 1, "license": "CC0-1.0 (EAWS micro-regions, regions.avalanches.org)",
                   "regions": reg}, open(a.regions, "w"), separators=(",", ":"))
        log("regiony:", len(reg), ", ".join(sorted(reg)))
    found = []
    if a.manual:
        found += from_manual(json.loads(a.manual), a.region, reg)
    for flag, fn in ((a.topr, topr), (a.slovakia, slovakia), (a.gopr, gopr)):
        if not flag: continue
        if fn is topr and any(e["publisher"] == "TOPR" for e in found): continue
        try:
            found += fn(reg)
        except Exception as ex:  # noqa: BLE001 – brak jednego źródła nie może zatrzymać pliku
            import traceback; traceback.print_exc()
            log(fn.__name__, "błąd:", repr(ex))
    out = {"version": 1, "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "avalanche": found}
    if a.keep:
        try:
            old = json.loads(http(a.keep) if a.keep.startswith("http") else open(a.keep, "rb").read())
            now = dt.datetime.now(dt.timezone.utc)
            have = {e["region"] for e in found}
            for e in old.get("avalanche", []):
                until = e.get("validUntil")
                if e.get("region") in have or not until or "regions" not in e: continue
                if dt.datetime.fromisoformat(until.replace("Z", "+00:00")) >= now:
                    out["avalanche"].append(e)
        except Exception as ex:  # noqa: BLE001
            log("poprzedni plik:", ex)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])

if __name__ == "__main__":
    sys.exit(main())
