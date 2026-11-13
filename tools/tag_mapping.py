"""Tag-mapping dla mapsforge-map-writer: domyślny z pliku jar + tagi szlaków (trail_*).

Użycie: python3 tag_mapping.py mapsforge-map-writer.jar tag-mapping.xml
"""
import sys
import zipfile

TRAILS = ''.join(
    f'        <osm-tag key="trail_{c}" value="yes" zoom-appear="11"/>\n'
    for c in ('red', 'blue', 'green', 'yellow', 'black')
)

xml = zipfile.ZipFile(sys.argv[1]).read('tag-mapping.xml').decode('utf-8')
at = xml.rindex('</tag-mapping>')
xml = xml[:at] + '    <!-- MudNav: szlaki turystyczne -->\n    <ways>\n' + TRAILS + '    </ways>\n' + xml[at:]
open(sys.argv[2], 'w', encoding='utf-8').write(xml)
print('tag-mapping ze szlakami:', sys.argv[2])
