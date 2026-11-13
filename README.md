# Mapy offline MudNav

Mapy [Mapsforge](https://github.com/mapsforge/mapsforge) z danych OpenStreetMap dla aplikacji MudNav:
pasma górskie (małe pliki) oraz kraje – Polska (w trzech częściach: południe, środek, północ), Czechy, Słowacja. Budowane co tydzień w czwartek w nocy (przed weekendowymi wyjściami) przez GitHub Actions
(`.github/workflows/maps.yml`) z wyciągów [Geofabrik](https://download.geofabrik.de) i publikowane w wydaniu
[`latest`](../../releases/tag/latest) razem z katalogiem `maps.json` (nazwa, rozmiar, SHA-256), z którego korzysta aplikacja.

Regiony: `regions.json`. Ręczne zbudowanie: Actions → „Mapy offline” → Run workflow.

## Licencja danych

Dane © współtwórcy OpenStreetMap, udostępnione na licencji [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Pliki map są bazą pochodną OSM i podlegają tej samej licencji.

## Codzienny checker bezpieczeństwa

Workflow „Bezpieczeństwo (codziennie)” działa o **4:17 czasu polskiego** (przez cały rok – przed porannymi wyjściami w góry)
i publikuje w wydaniu `latest`:

- `closures.tsv` – zamknięte odcinki szlaków z OpenStreetMap (zakazy i okresowe zamknięcia `*:conditional`) w pasmach z `regions.json`,
- `safety.json` – zagrożenie lawinowe (Słowacja z CAAML, TOPR ze strony komunikatu), komunikaty parków narodowych o zamknięciach
  i obszary, dla których zamknięcia są kompletne.

Aplikacja pobiera oba pliki raz na dobę, gdy ma internet; bez internetu używa ostatnio pobranych. Źródła: `sources.json`.

## Czas budowania

Mapy krajów budowane są z odchudzonych danych (osmium `tags-filter`): bez zwykłych budynków i samych adresów,
z budynkami, które mają nazwę lub funkcję (schroniska, kościoły, sklepy). Najpierw w pamięci (`type=ram`, szybko),
a gdy się nie zmieści – na dysku (`type=hd`). Pasma górskie mają pełne dane i publikują się od razu po zbudowaniu.

Polska jest dzielona na trzy pasy (osmium `extract`, zakładka ok. 10 km), bo w całości nie mieściła się w pamięci
(budowa na dysku trwała prawie 3 h). Czechy i Słowacja w pamięci: ok. 10 min każda.
