# Mapy offline MudNav

Mapy [Mapsforge](https://github.com/mapsforge/mapsforge) z danych OpenStreetMap dla aplikacji MudNav:
pasma górskie (małe pliki) oraz całe kraje – Polska, Czechy, Słowacja. Budowane co tydzień w czwartek w nocy (przed weekendowymi wyjściami) przez GitHub Actions
(`.github/workflows/maps.yml`) z wyciągów [Geofabrik](https://download.geofabrik.de) i publikowane w wydaniu
[`latest`](../../releases/tag/latest) razem z katalogiem `maps.json` (nazwa, rozmiar, SHA-256), z którego korzysta aplikacja.

Regiony: `regions.json`. Ręczne zbudowanie: Actions → „Mapy offline” → Run workflow.

## Licencja danych

Dane © współtwórcy OpenStreetMap, udostępnione na licencji [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Pliki map są bazą pochodną OSM i podlegają tej samej licencji.
