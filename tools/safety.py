"""Codzienny checker bezpieczeństwa dla MudNav (uruchamiany w GitHub Actions).

1. Zamknięte odcinki szlaków z OSM (Overpass, regiony z regions.json) → closures.tsv (format aplikacji).
2. Zagrożenie lawinowe: Słowacja (CAAML v6, laviny.sk), TOPR i GOPR Karkonosze (próba odczytu stopnia ze strony).
3. Komunikaty parków narodowych: linki ze stron głównych zawierające słowa kluczowe (zamknięcia, lawiny, oblodzenie).
Wynik: safety.json + closures.tsv. Każde źródło jest niezależne – błąd jednego nie blokuje reszty.
"""
import datetime, html, json, re, sys, time, urllib.parse, urllib.request

UA = {"User-Agent": "MudNav-safety-checker/1.0 (+https://github.com/blue-samirai-141/mudnav-maps)"}
SCALE = 100000

def get(url, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def log(*a):
    print(*a, flush=True)

# ---------------------------------------------------------------- 1. zamknięcia z OSM

def encode_rule(tags):
    keys = ["highway", "access", "foot", "access:conditional", "foot:conditional"]
    return "|".join(f"{k}={tags[k].replace('|', '/').replace(chr(9), ' ')}" for k in keys if k in tags)

def encode_coords(geom):
    out, plat, plon = [], 0, 0
    for p in geom:
        lat, lon = round(p["lat"] * SCALE), round(p["lon"] * SCALE)
        out += [str(lat - plat), str(lon - plon)]
        plat, plon = lat, lon
    return ",".join(out)

CLOSED = ("no", "private")

def relevant(t):
    """Tylko faktyczne zakazy (no/private) i ograniczenia czasowe – resztę i tak odrzuca aplikacja."""
    if any(k.endswith(":conditional") for k in t if k.startswith(("access", "foot"))):
        return True
    return t.get("access") in CLOSED or t.get("foot") in CLOSED

def overpass(src, q, rid):
    for attempt in range(3):
        for ep in src["overpass"]:
            try:
                return json.loads(get(ep, urllib.parse.urlencode({"data": q}).encode(), timeout=240))
            except Exception as ex:
                log("overpass", ep, rid, "próba", attempt + 1, "błąd:", ex)
                time.sleep(20)
        time.sleep(60 * (attempt + 1))
    raise RuntimeError(f"Overpass niedostępny dla {rid}")

def previous_closures():
    """Wczorajszy closures.tsv z wydania – zapas dla pasm, których Overpass dziś nie oddał."""
    try:
        return get("https://github.com/blue-samirai-141/mudnav-maps/releases/download/latest/closures.tsv", timeout=60).splitlines()
    except Exception as ex:
        log("brak wczorajszych zamknięć:", ex)
        return []

def first_point(line):
    try:
        nums = line.split("\t")[2].split(",")
        return int(nums[0]) / SCALE, int(nums[1]) / SCALE
    except Exception:
        return None

def in_bbox(pt, bbox):
    s, w, n, e = bbox
    return pt is not None and s <= pt[0] <= n and w <= pt[1] <= e

def closures(cfg, src):
    """Zwraca (liczba odcinków, obszary kompletne dziś). Nieudane pasmo: wczorajsze dane, bez pokrycia."""
    seen, lines, covered, failed = set(), [], [], []
    for r in cfg["ranges"]:
        s, w, n, e = r["bbox"]
        q = f"""[out:json][timeout:300];
rel[route~"^(hiking|foot)$"]({s},{w},{n},{e})->.r;
way(r.r)[~"^(access|foot)(:conditional)?$"~"."]({s},{w},{n},{e});
out tags geom;"""
        try:
            data = overpass(src, q, r["id"])
        except Exception as ex:
            log("zamknięcia", r["id"], "– pomijam dziś:", ex)
            failed.append(r)
            continue
        for el in data.get("elements", []):
            if el.get("type") != "way" or el["id"] in seen or len(el.get("geometry", [])) < 2:
                continue
            seen.add(el["id"])
            t = el.get("tags", {})
            if not relevant(t):
                continue
            lines.append(f"{encode_rule(t)}\t{(t.get('name:pl') or t.get('name') or '').replace(chr(9), ' ')}\t{encode_coords(el['geometry'])}")
        covered.append(r["bbox"])
        log("zamknięcia", r["id"], "odcinki z tagami:", len(seen), "po filtrze (razem):", len(lines))
        time.sleep(15)
    if failed:
        prev = previous_closures()
        kept = [l for l in prev if any(in_bbox(first_point(l), r["bbox"]) for r in failed)
                and not any(in_bbox(first_point(l), b) for b in covered)]
        log("z wczoraj dla", [r["id"] for r in failed], ":", len(kept))
        lines += kept
    if not covered and not lines:
        raise RuntimeError("Overpass niedostępny dla wszystkich pasm")
    with open("closures.tsv", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return len(lines), covered

# ---------------------------------------------------------------- 2. lawiny

WORDS = [("bardzo wysokie", 5), ("wysokie", 4), ("znaczne", 3), ("umiarkowane", 2), ("niskie", 1)]
LEVELS = {"low": 1, "moderate": 2, "considerable": 3, "high": 4, "very_high": 5}
SK_RANGES = {
    "VYSOKE_TATRY": ["Vysoké Tatry", "Belianske Tatry", "High Tatras"],
    "ZAPADNE_TATRY": ["Západné Tatry", "Western Tatras"],
    "NIZKE_TATRY": ["Nízke Tatry", "Low Tatras"],
    "MALA_FATRA": ["Malá Fatra", "Little Fatra"],
    "VELKA_FATRA": ["Veľká Fatra", "Great Fatra"],
    "CHOCSKE": ["Chočské vrchy"],
}

def slovakia(src):
    out = []
    today = datetime.date.today()
    for d in (today, today - datetime.timedelta(days=1)):
        base = f"{src['slovakia']['base']}{d.isoformat()}/"
        try:
            index = get(base)
        except Exception as ex:
            log("laviny.sk", d, ex)
            continue
        files = re.findall(r'href="([^"]*CAAMLv6[^"]*\.json)"', index)
        log("laviny.sk pliki", d, files)
        f = next((x for x in files if "_sk" in x), files[0] if files else None)
        if not f:
            continue
        body = json.loads(get(base + f.split("/")[-1]))
        bulletins = body.get("bulletins", body if isinstance(body, list) else [])
        for rng, names in SK_RANGES.items():
            best = None
            for b in bulletins:
                rnames = [x.get("name", "") for x in b.get("regions", [])]
                if not any(k.lower() in n.lower() for n in rnames for k in names):
                    continue
                lvl = max((LEVELS.get(r.get("mainValue"), 0) for r in b.get("dangerRatings", [])), default=0)
                if lvl and (best is None or lvl > best):
                    best = lvl
            if best:
                out.append({"range": rng, "level": best, "source": "HZS Słowacja", "url": src["slovakia"]["url"], "date": d.isoformat()})
        if out:
            break
    return out

def page_level(entry):
    """Stopień zagrożenia ze strony (TOPR/GOPR nie mają otwartego API) – tylko gdy odczyt jest jednoznaczny."""
    try:
        text = get(entry["widget"])
    except Exception as ex:
        log(entry["source"], "błąd:", ex)
        return None
    plain = re.sub(r"<[^>]+>", " ", html.unescape(text))
    plain = re.sub(r"\s+", " ", plain)
    log(entry["source"], "fragment:", plain[:600])
    m = re.findall(r"(?:stopie[ńn]|stopnia)\D{0,40}?([1-5])\b", plain, re.I) or re.findall(r"\blaw0?([1-5])\b", text, re.I)
    levels = set(int(x) for x in m)
    w = re.search(r"określono jako:?\s*(bardzo wysokie|wysokie|znaczne|umiarkowane|niskie)", plain, re.I)
    if w:
        levels.add(dict(WORDS)[w.group(1).lower()])
    levels = sorted(levels)
    if len(levels) == 1:
        return {"range": entry["range"], "level": levels[0], "source": entry["source"], "url": entry["url"], "date": datetime.date.today().isoformat()}
    log(entry["source"], "niejednoznaczne:", levels)
    return None

# ---------------------------------------------------------------- 3. komunikaty parków

STRONG = ("zamkn", "zamyka", "uzavr", "uzávier", "uzavret", "oblodz", "utrudnie", "wiatroł", "nieprzejezd", "nieprzejść")

def announcements(src):
    out = []
    kw = [k.lower() for k in src["keywords"]]
    for a in src["announcements"]:
        try:
            page = get(a["url"])
        except Exception as ex:
            log(a["source"], "błąd:", ex)
            continue
        found = 0
        for href, title in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', page, re.I | re.S):
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(title))).strip()
            if len(t) < 12 or len(t) > 200:
                continue
            low = t.lower()
            if not any(k in low for k in kw) or not any(k in low for k in STRONG):
                continue
            url = urllib.parse.urljoin(a["url"], href)
            if not url.startswith("http"):
                continue
            out.append({"source": a["source"], "title": t, "url": url, "bbox": a["bbox"]})
            found += 1
            if found >= 5:
                break
        log(a["source"], "komunikaty:", found)
    return out

def main():
    cfg = json.load(open("regions.json", encoding="utf-8"))
    src = json.load(open("sources.json", encoding="utf-8"))
    result = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "avalanche": [], "announcements": [], "closures": None, "coverage": []}
    try:
        # coverage: obszary, w których closures.tsv jest dziś kompletny – tam aplikacja ufa tylko świeżym danym.
        result["closures"], result["coverage"] = closures(cfg, src)
    except Exception as ex:
        log("zamknięcia – pomijam:", ex)
    try:
        result["avalanche"] += slovakia(src)
    except Exception as ex:
        log("Słowacja – pomijam:", ex)
    for e in src["avalanche"]:
        lvl = page_level(e)
        if lvl:
            result["avalanche"].append(lvl)
    try:
        result["announcements"] = announcements(src)
    except Exception as ex:
        log("komunikaty – pomijam:", ex)
    json.dump(result, open("safety.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(json.dumps(result, ensure_ascii=False)[:3000])
    return 0

if __name__ == "__main__":
    sys.exit(main())
