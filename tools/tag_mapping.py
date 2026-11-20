"""Tag-mapping dla mapsforge-map-writer: domyślny z pliku jar + szlaki (trail_*), poziomice (mn_contour), schroniska-budynki.

Użycie: python3 tag_mapping.py mapsforge-map-writer.jar tag-mapping.xml
"""
import sys
import zipfile

TRAILS = ''.join(
    f'        <osm-tag key="trail_{c}" value="{v}" zoom-appear="11"/>\n'
    for c in ('red', 'blue', 'green', 'yellow', 'black')
    # Pas szlaku (tools/trails.py: LANES); „yes” – starsze dane bez pasów.
    for v in ('yes', 'm4', 'm3', 'm2', 'm1', '0', 'p1', 'p2', 'p3', 'p4')
)

# Poziomice z tools/contours.py: co 100 m widać najwcześniej, co 10 m dopiero w dużym zbliżeniu.
CONTOURS = ''.join(
    f'        <osm-tag key="mn_contour" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('100', 11), ('50', 12), ('20', 13), ('10', 15))
)
# Skały, ostańce, urwiska, granie i grzędy – domyślny zestaw ich nie zapisuje, a w górach to ważna część mapy.
# Obszary chronione z tools/protected.py (multipolygony z mn_protect).
PROTECT = ''.join(
    f'        <osm-tag key="mn_protect" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('national_park', 8), ('landscape_park', 9), ('reserve', 12), ('natura2000', 11))
)
ROCK_WAYS = ''.join(
    f'        <osm-tag key="natural" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('bare_rock', 11), ('rock', 13), ('stone', 15), ('cliff', 13), ('arete', 12), ('ridge', 12))
)
ROCK_POIS = ''.join(
    f'        <osm-tag key="natural" value="{v}" zoom-appear="{z}"/>\n' for v, z in (('rock', 14), ('stone', 15))
) + ''.join(
    # Punkty z tools/extra_pois.py: pomniki przyrody, wodospady, źródła rzek, kapliczki, wieże widokowe.
    f'        <osm-tag key="mn_poi" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('monument', 13), ('waterfall', 12), ('source', 12), ('shrine', 15), ('tower', 12))
) + ''.join(
    f'        <osm-tag key="mn_protect_label" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('national_park', 8), ('landscape_park', 9), ('reserve', 12), ('natura2000', 11))
) + ''.join(
    f'        <osm-tag key="mn_dog" value="{v}" zoom-appear="9"/>\n' for v in ('zakaz_wstepu', 'na_smyczy', 'dozwolone')
) + ''.join(
    # Podpisy jezior z tools/water_labels.py: duże jeziora widać z daleka, stawy dopiero z bliska.
    f'        <osm-tag key="mn_water_label" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('huge', 9), ('big', 11), ('medium', 13), ('small', 15))
)
# Schroniska bywają w OSM budynkiem (linią), nie punktem – domyślny zestaw zna je tylko jako punkty.
HUTS = ''.join(
    f'        <osm-tag key="tourism" value="{v}" zoom-appear="11"/>\n' for v in ('alpine_hut', 'wilderness_hut')
)

xml = zipfile.ZipFile(sys.argv[1]).read('tag-mapping.xml').decode('utf-8')
at = xml.rindex('</tag-mapping>')
# Przepusty (ciek pod ścieżką, tunnel=culvert) – na mapie rysowane jak mostek; w OSM to częsty sposób oznaczenia
# kładki nad potokiem (np. park w Swoszowicach). Do tego mosty-kładki i wiadukty. Tylko te, których brak w zestawie
# domyślnym (powtórzony wpis psułby mapowanie).
CROSSINGS = ''.join(
    f'        <osm-tag key="{k}" value="{v}" zoom-appear="15"/>\n'
    for k, v in (('tunnel', 'culvert'), ('bridge', 'boardwalk'), ('bridge', 'viaduct'))
    if f'key="{k}" value="{v}"' not in xml[xml.find('<ways>'):]
)
xml = xml[:at] + '    <!-- MudNav: skały -->\n    <pois>\n' + ROCK_POIS + '    </pois>\n' + '    <!-- MudNav: szlaki turystyczne, poziomice, schroniska-budynki, skały -->\n    <ways>\n' + TRAILS + CONTOURS + ROCK_WAYS + PROTECT + CROSSINGS + (HUTS if 'key="tourism" value="alpine_hut"' not in xml[xml.find('<ways>'):] else '') + '    </ways>\n' + xml[at:]
open(sys.argv[2], 'w', encoding='utf-8').write(xml)
print('tag-mapping ze szlakami i poziomicami:', sys.argv[2])
