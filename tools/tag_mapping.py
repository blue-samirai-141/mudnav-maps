"""Tag-mapping dla mapsforge-map-writer: domyślny z pliku jar + szlaki (trail_*), poziomice (mn_contour), schroniska-budynki.

Użycie: python3 tag_mapping.py mapsforge-map-writer.jar tag-mapping.xml
"""
import sys
import zipfile

TRAILS = ''.join(
    f'        <osm-tag key="trail_{c}" value="yes" zoom-appear="11"/>\n'
    for c in ('red', 'blue', 'green', 'yellow', 'black')
)

# Poziomice z tools/contours.py: co 100 m widać najwcześniej, co 10 m dopiero w dużym zbliżeniu.
CONTOURS = ''.join(
    f'        <osm-tag key="mn_contour" value="{v}" zoom-appear="{z}"/>\n'
    for v, z in (('100', 11), ('50', 12), ('20', 13), ('10', 15))
)
# Schroniska bywają w OSM budynkiem (linią), nie punktem – domyślny zestaw zna je tylko jako punkty.
HUTS = ''.join(
    f'        <osm-tag key="tourism" value="{v}" zoom-appear="11"/>\n' for v in ('alpine_hut', 'wilderness_hut')
)

xml = zipfile.ZipFile(sys.argv[1]).read('tag-mapping.xml').decode('utf-8')
at = xml.rindex('</tag-mapping>')
xml = xml[:at] + '    <!-- MudNav: szlaki turystyczne, poziomice, schroniska-budynki -->\n    <ways>\n' + TRAILS + CONTOURS + (HUTS if 'key="tourism" value="alpine_hut"' not in xml[xml.find('<ways>'):] else '') + '    </ways>\n' + xml[at:]
open(sys.argv[2], 'w', encoding='utf-8').write(xml)
print('tag-mapping ze szlakami i poziomicami:', sys.argv[2])
