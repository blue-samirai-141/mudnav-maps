#!/usr/bin/env python3
"""Diagnostyka: skąd i w jakim formacie da się czytać komunikat lawinowy TOPR (i komunikat turystyczny TPN).

Zapisuje surowe strony i wszystko, co wygląda na źródło danych (JSON, XML/CAAML, adresy API w skryptach),
do katalogu wyjściowego i krótkie podsumowanie w Markdown. Uruchamiane ręcznie w akcji avalanche-probe.yml.
Użycie: python3 tools/avalanche_probe.py WYJŚCIE
"""
import json, os, re, sys, urllib.request, urllib.parse

UA = "MudNav-maps/1.0 (diagnostyka komunikatu lawinowego; kontakt przez GitHub)"
PAGES = [
    "https://lawiny.topr.pl/",
    "https://lawiny.topr.pl/en",
    "https://tpn.gov.pl/komunikat-turystyczny",
    "https://www.laviny.sk/",
]
# Typowe miejsca danych w serwisach EAWS (CAAML v6) – sprawdzamy, czy istnieją.
GUESSES = [
    "https://lawiny.topr.pl/api/bulletin", "https://lawiny.topr.pl/api/bulletins", "https://lawiny.topr.pl/api/v1/bulletin",
    "https://lawiny.topr.pl/caaml", "https://lawiny.topr.pl/bulletin.json", "https://lawiny.topr.pl/feed", "https://lawiny.topr.pl/rss",
    "https://lawiny.topr.pl/wp-json/testapi/v1", "https://lawiny.topr.pl/getwidget",
]

def caaml_guesses():
    """Katalog uploads/caaml (stąd PDF komunikatu) – możliwe nazwy pliku danych na dziś i wczoraj."""
    import datetime as dt
    base = "https://lawiny.topr.pl/wp-content/uploads/caaml/"
    out = [base]
    for d in (dt.date.today(), dt.date.today() - dt.timedelta(days=1)):
        s = d.isoformat()
        for name in (f"{s}.json", f"{s}.xml", f"caaml_{s}.json", f"caaml_{s}.xml", f"caaml_pl_{s}.json", f"caaml_pl_{s}.xml",
                     f"json_pl_{s}.json", f"xml_pl_{s}.xml", f"pl_{s}.json", f"pl_{s}.xml", f"bulletin_{s}.json", f"bulletin_pl_{s}.json",
                     f"caamlv6_{s}.json", f"CAAMLv6_{s}.json", f"{s}_pl.json", f"{s}_pl.xml", f"caaml_en_{s}.json", f"json_en_{s}.json"):
            out.append(base + name)
    return out

def get(url, limit=3_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(limit)
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", b""
    except Exception as e:  # noqa: BLE001 – diagnostyka, zapisujemy każdy błąd
        return 0, str(e), b""

def safe(url):
    return re.sub(r"[^A-Za-z0-9]+", "_", url)[:120]

def main(out):
    os.makedirs(out, exist_ok=True)
    md = ["# Komunikat lawinowy – diagnostyka źródeł", ""]
    seen = set()
    queue = list(PAGES)
    found = []
    while queue:
        url = queue.pop(0)
        if url in seen or len(seen) > 60:
            continue
        seen.add(url)
        status, ctype, body = get(url)
        md.append(f"- `{status}` {ctype[:40]} – {url} ({len(body)} B)")
        if not body:
            continue
        open(os.path.join(out, safe(url)), "wb").write(body)
        text = body.decode("utf-8", "replace")
        if "json" in ctype or "xml" in ctype or text.lstrip().startswith(("{", "[", "<?xml")):
            found.append((url, ctype, text[:400]))
        if "html" in ctype or "javascript" in ctype:
            base = url
            # Skrypty i odwołania do danych (fetch/axios/XHR, .json, api, caaml).
            for m in re.finditer(r"""(?:src|href)=["']([^"']+\.js[^"']*)["']""", text):
                queue.append(urllib.parse.urljoin(base, m.group(1)))
            for m in re.finditer(r"""["'`]((?:https?://[^"'`\s]+|/[^"'`\s]*)(?:api|json|caaml|bulletin|komunikat|lawin)[^"'`\s]*)["'`]""", text, re.I):
                u = urllib.parse.urljoin(base, m.group(1))
                if u.startswith("http") and not u.endswith((".png", ".jpg", ".svg", ".css", ".woff", ".woff2")):
                    queue.append(u)
    for g in GUESSES + caaml_guesses():
        status, ctype, body = get(g)
        md.append(f"- zgadywane `{status}` {ctype[:40]} – {g} ({len(body)} B)")
        if body:
            open(os.path.join(out, safe(g)), "wb").write(body)
            found.append((g, ctype, body[:400].decode("utf-8", "replace")))
    md += ["", "## Dane (JSON / XML)", ""]
    for url, ctype, head in found:
        md += [f"### {url}", f"`{ctype}`", "```", head.replace("```", "'''"), "```", ""]
    if not found:
        md.append("Brak źródeł JSON/XML – komunikat trzeba czytać z HTML (zapisane strony w artefakcie).")
    open(os.path.join(out, "wynik.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "probe")
