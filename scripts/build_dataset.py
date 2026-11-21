"""Build the offline AthensShade bundle from public source snapshots."""

import argparse
import json
import math
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from statistics import quantiles
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.mask import mask
from shapely import STRtree, make_valid, transform, union_all
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape


PROJECT = Path(__file__).resolve().parents[1]
CITY = 'https://opendata.cityofathens.gr/dataset/'
CITY_LICENSE = 'CC BY 3.0 Greece · https://creativecommons.org/licenses/by/3.0/gr/'
ATLAS_PAGE = CITY + 'gis-athens-057aff6a-f337-11ee-b64b-0242ac120004'
ATLAS_CATALOG = 'https://data.gov.gr/dataset/cityofathens-63a5a390-256b-4ca9-b266-1b4689db033d'
DISTRICTS_PAGE = CITY + 'gis-athens-26fc7f34-6439-11ee-88f1-0242ac120004'
SCHOOLS_PAGE = CITY + 'gis-athens-3bbfb156-7722-11ee-bdf0-0242ac120004'
TREES_PAGE = 'https://athenstrees.cityofathens.gr/'
PARKS_PAGE = 'https://www.cityofathens.gr/poy-tha-vro-pocket-parks-stin-athina/'
PARKS_WFS = 'https://api.gis.cityofathens.gr/geoserver/ows?' + urlencode({
    'service': 'WFS',
    'version': '2.0.0',
    'request': 'GetFeature',
    'typeNames': 'athensgis:pois_pocketparks',
    'outputFormat': 'application/json',
    'srsName': 'EPSG:4326',
    'count': 200,
})
CANOPY_SERVICE = (
    'https://image.discomap.eea.europa.eu/arcgis/rest/services/'
    'GioLandPublic/HRL_TreeCoverDensity_2018/ImageServer/exportImage'
)
CANOPY_EXPORT = CANOPY_SERVICE + '?' + urlencode({
    'bbox': '23.675,37.944,23.795,38.047',
    'bboxSR': 4326,
    'imageSR': 3857,
    'size': '1336,1455',
    'format': 'tiff',
    'pixelType': 'U8',
    'interpolation': 'RSP_NearestNeighbor',
    'renderingRule': '{"rasterFunction":"None"}',
    'f': 'image',
})
COUNCIL_DECISION = 'https://www.cityofathens.gr/wp-content/uploads/2025/11/717-25.pdf'
TENDER_BASE = 'https://www.cityofathens.gr/wp-content/uploads/2024/'
TREE_TENDER = TENDER_BASE + (
    '01/timologio-dimopratisis-erga-odopoiias-kai-diktyon-omvrion-apocheteysis-periochi-elaiona-2024.pdf#page=110'
)
SHADE_TENDER = TENDER_BASE + (
    '06/timologio-dimopratisis-ergo-syntiriseis-scholikon-ktirion-dimoy-athinaion-7i-dimotiki-koinotita.pdf#page=74'
)
ROOF_TENDER = (
    'https://www.ppel.gov.gr/wp-content/uploads/2022/07/'
    '5.-%CE%A4%CE%99%CE%9C%CE%9F%CE%9B%CE%9F%CE%93%CE%99%CE%9F-'
    '%CE%91%CE%A3%CE%A4%CE%95%CE%A1%CE%9F%CE%A3%CE%9A%CE%9F%CE%A0%CE%95%CE%99%CE%9F.pdf'
)
POPULATION_PAGE = 'https://data.jrc.ec.europa.eu/dataset/98336641-fd1c-4992-8c7b-c470dd5eb81e'
POPULATION_DOWNLOAD = (
    'https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/MAPS/JRC-ESTAT_Census_Population_2021_100m/'
    'JRC-ESTAT_Census_Population_2021_100m.zip'
)
POPULATION_MEMBER = 'JRC-ESTAT_Census_Population_2021_100m_rev0726.tif'

GRID_M = 175
SITE_RADIUS_M = 100
MIN_HEAT_COVERAGE = 0.7
ATHENS_CRS = 'EPSG:2100'
WEB_CRS = 'EPSG:3857'
GEOGRAPHIC_CRS = 'EPSG:4326'

# Public-space reference points from Annex 3 of City Council Decision 717/2025.
# The coordinates describe vicinity reference points, not proposed construction footprints.
# The final three values are scenario quantities: trees, shadow sails in m², greenery in m².
SITES = (
    ('attiki', 'Πλατεία Αττικής', 475472.0005, 4205144.521, 60, 300, 0),
    ('victoria', 'Πλατεία Βικτωρίας', 476140.5178, 4204806.948, 32, 220, 0),
    ('agios-panteleimonas', 'Πλατεία Αγίου Παντελεήμονα', 475898.8735, 4205161.754, 40, 320, 0),
    ('amerikis', 'Πλατεία Αμερικής', 476441.164, 4205858.980, 36, 240, 210),
    ('fokionos', 'Φωκίωνος Νέγρη', 477120.7875, 4205826.792, 30, 180, 160),
    ('koumoundourou', 'Πλατεία Κουμουνδούρου', 475420.8922, 4203469.083, 64, 360, 0),
    ('kotzia', 'Πλατεία Κοτζιά', 475989.5156, 4203569.897, 74, 420, 0),
    ('kerameikos', 'Πλατεία Κεραμεικού', 474522.6835, 4203206.368, 55, 400, 230),
    ('avdi', 'Πλατεία Αυδή', 475235.8110, 4203639.822, 36, 220, 170),
    ('dourouti', 'Πλατεία Δουρούτι', 475238.9125, 4203697.382, 28, 180, 185),
    ('ramnes', 'Πλατεία Ραμνές', 474904.3928, 4204001.223, 40, 210, 175),
)

# Published municipal school IDs paired with assumed pilot treatment areas in m².
ROOF_SCENARIOS = {369: 180, 77: 240, 120: 220}


def source(id_, title, url, period, kind, **details):
    return dict(id=id_, title=title, url=url, period=period, kind=kind, **details)


def source_registry(snapshot_date):
    return [
        source('athens-atlas', 'Athens Temperature Atlas · Δήμος Αθηναίων', ATLAS_PAGE,
               'Ιούνιος–Αύγουστος 2016–2020', 'heat', license=CITY_LICENSE,
               catalog_url=ATLAS_CATALOG,
               credit='EXTREMA Global Services και ARTi Analytics BV',
               description='Μέση ημερήσια θερμοκρασία επιφάνειας σε °C. Σταθμισμένος μέσος ανά κελί 175 μ.'),
        source('athens-districts', 'Δημοτικές κοινότητες · Δήμος Αθηναίων', DISTRICTS_PAGE,
               'Δημοτικό σύνολο GIS', 'boundary', license=CITY_LICENSE),
        source('athens-schools', 'Δημόσια σχολεία · Δήμος Αθηναίων', SCHOOLS_PAGE,
               '2023', 'schools', license=CITY_LICENSE),
        source('athens-pocket-parks', 'Πάρκα τσέπης · Δήμος Αθηναίων', PARKS_PAGE,
               'Στιγμιότυπο δημοτικού GIS', 'pocket_parks', catalog_url=PARKS_WFS),
        source('athens-sites', 'Σημεία αναφοράς δημοσίων χώρων · Απόφαση 717/2025', COUNCIL_DECISION,
               '2025', 'locations'),
        source('copernicus-canopy', 'Δενδροκάλυψη · Copernicus / EEA',
               'https://doi.org/10.2909/486f77da-d605-423e-93a9-680760ab6791',
               '2018', 'canopy', license='Copernicus Land Monitoring Service · πλήρης, δωρεάν και ανοικτή πρόσβαση',
               description='Tree Cover Density 10 μ. Μέσο ποσοστό στην ακτίνα ή στο κελί. Δεδομένα Copernicus προσαρμοσμένα από AthensShade.'),
        source('athens-trees', 'Καταγραφές νέων φυτεύσεων · AthensTrees / ΔΑΕΜ', TREES_PAGE,
               f'Από 01/01/2024 · λήψη {snapshot_date}', 'plantings',
               description='Δημόσια σημεία του χάρτη, ομαδοποιημένα σε κελιά 175 μ. Ο μετρητής αφορά εγγραφές σημείων.'),
        source('athens-tree-tender', 'Τιμολόγιο δημοπράτησης Ελαιώνα · Άρθρο Ε-8.2', TREE_TENDER,
               'Δεκέμβριος 2023', 'cost', description='220 € ανά δέντρο κατηγορίας Δ9 για προμήθεια.'),
        source('athens-shade-tender', 'Τιμολόγιο δημοπράτησης σχολείων · Άρθρο 428', SHADE_TENDER,
               '2024', 'cost', description='49,43 €/m² για σύστημα εξωτερικής σκίασης με ιστία.'),
        source('public-roof-tender', 'Τιμολόγιο Κρυονερίου · Περιφέρεια Πελοποννήσου', ROOF_TENDER,
               '2022', 'cost', description='Άρθρα Η.62–Η.64: ενδεικτική βάση για αποστράγγιση, φίλτρο και υπόστρωμα.'),
        source('planning-assumptions', 'Παραδοχές προϋπολογισμού · AthensShade', None,
               'Σενάριο MVP', 'cost', description='Ενδεικτικές ποσότητες και δαπάνες σεναρίου, προ ΦΠΑ.'),
        source('jrc-estat-population', 'Πληθυσμός 2021 · JRC και Eurostat', POPULATION_PAGE,
               'Απογραφή 2021 · αναθεώρηση 07/2026', 'population',
               license='European Commission reuse notice · αναφορά πηγής',
               description='Εκτιμώμενοι μόνιμοι κάτοικοι ανά km², από κατανομή της απογραφής σε κάνναβο 100 μ.'),
    ]


def download(url, path):
    request = Request(url, headers={'User-Agent': 'AthensShade/1.0', 'Accept': '*/*'})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_bytes(payload)
    temporary.replace(path)


def download_catalog_archive(package, path):
    if path.exists():
        return
    metadata_url = 'https://opendata.cityofathens.gr/api/3/action/package_show?id=' + package
    with urlopen(metadata_url, timeout=30) as response:
        metadata = json.load(response)
    archives = [entry for entry in metadata['result']['resources'] if
                entry.get('format') == 'ZIP' and entry.get('url_type') == 'upload']
    if len(archives) != 1:
        raise ValueError(f'Expected exactly one uploaded CKAN archive for {package}')
    download(archives[0]['url'], path)


def read_catalog_geojson(path):
    # CKAN's Download All archives reuse the member name "ows" for multiple formats.
    with ZipFile(path) as archive:
        for member in archive.infolist():
            if member.filename != 'ows':
                continue
            with archive.open(member) as stream:
                if stream.read(32).lstrip().startswith(b'{'):
                    collection = json.load(archive.open(member))
                    if collection.get('type') == 'FeatureCollection':
                        return collection
    raise ValueError(f'No GeoJSON FeatureCollection found in {path}')


@lru_cache
def transformer(source_crs, destination_crs):
    return Transformer.from_crs(source_crs, destination_crs, always_xy=True).transform


def change_crs(geometry, source_crs, destination_crs):
    if source_crs == destination_crs:
        return geometry
    return transform(geometry, transformer(source_crs, destination_crs), interleaved=False)


def polygonal(geometry):
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    if geometry.geom_type == 'GeometryCollection':
        return union_all([part for part in geometry.geoms if isinstance(part, (Polygon, MultiPolygon))])
    return Polygon()


def geojson_geometry(geometry, source_crs=ATHENS_CRS):
    transformed = mapping(change_crs(geometry, source_crs, GEOGRAPHIC_CRS))

    def round_coordinates(coordinates):
        if isinstance(coordinates[0], (float, int)):
            return [round(value, 6) for value in coordinates]
        return [round_coordinates(item) for item in coordinates]

    return dict(type=transformed['type'], coordinates=round_coordinates(transformed['coordinates']))


def feature(geometry, **properties):
    return dict(type='Feature', geometry=geojson_geometry(geometry), properties=properties)


def collection(features):
    return dict(type='FeatureCollection', features=features)


def heat_geometries(raw_features):
    geometries, temperatures = [], []
    for entry in raw_features:
        temperature = entry['properties'].get('avgLST')
        if temperature is None or not math.isfinite(temperature) or temperature <= 0:
            continue
        geometry = polygonal(make_valid(change_crs(shape(entry['geometry']), WEB_CRS, ATHENS_CRS)))
        if not geometry.is_empty:
            geometries.append(geometry)
            temperatures.append(temperature)
    return geometries, temperatures


def weighted_heat(area, geometries, temperatures, index):
    numerator = denominator = 0.0
    for offset in index.query(area, predicate='intersects'):
        overlap = area.intersection(geometries[offset]).area
        numerator += overlap * temperatures[offset]
        denominator += overlap
    if denominator < area.area * MIN_HEAT_COVERAGE:
        return None
    return round(numerator / denominator, 2)


def cells(boundary):
    min_x, min_y, max_x, max_y = boundary.bounds
    for x in range(math.floor(min_x / GRID_M), math.ceil(max_x / GRID_M)):
        for y in range(math.floor(min_y / GRID_M), math.ceil(max_y / GRID_M)):
            area = polygonal(boundary.intersection(box(x * GRID_M, y * GRID_M, (x + 1) * GRID_M, (y + 1) * GRID_M)))
            if not area.is_empty and area.area >= 150:
                yield area


def canopy_mean(raster, area):
    projected = change_crs(area, ATHENS_CRS, raster.crs)
    try:
        pixels, _ = mask(raster, [mapping(projected)], crop=True, filled=False, indexes=1)
    except ValueError:
        return None
    values = pixels.compressed()
    values = values[(values >= 0) & (values <= 100)]
    if values.size == 0:
        return None
    return round(float(np.mean(values)), 1)


def population_density(raster, area):
    projected = change_crs(area, ATHENS_CRS, raster.crs)
    try:
        values, affine = mask(raster, [mapping(projected)], all_touched=True, crop=True, filled=False, indexes=1)
    except ValueError:
        return None
    weighted_population = covered_area = 0.0
    cell_area = abs(affine.a * affine.e)
    for row, column in zip(*np.nonzero(~np.ma.getmaskarray(values))):
        left, top = affine * (column, row)
        right, bottom = affine * (column + 1, row + 1)
        overlap = projected.intersection(box(left, bottom, right, top)).area
        covered_area += overlap
        weighted_population += float(values[row, column]) * overlap / cell_area
    if covered_area < projected.area * 0.9:
        return None
    return round(weighted_population * 1_000_000 / covered_area)


def school_name_map(archive):
    # The WFS archive contains replacement characters in Greek attributes. The original DBF's
    # source encoding is UTF-8. Preserve WFS geometry and recover labels by school ID.
    from io import BytesIO

    import shapefile

    with ZipFile(archive) as outer:
        with ZipFile(BytesIO(outer.read('379'))) as inner:
            name = next(name for name in inner.namelist() if name.endswith('.dbf'))
            reader = shapefile.Reader(dbf=BytesIO(inner.read(name)), encoding='utf-8')
            return {record['sc_id']: record['sc_descr'].strip() for record in reader.iterRecords()}


def normalized_context(districts, schools, school_names):
    district_shapes = {int(row['properties']['no']): polygonal(make_valid(shape(row['geometry'])))
                       for row in districts}
    features = [feature(geometry.simplify(3), kind='district', name=f'{number}η Δημοτική Κοινότητα',
                        district=f'{number}η ΔΚ', source_id='athens-districts')
                for number, geometry in sorted(district_shapes.items())]
    for row in schools:
        school_id = row['properties']['sc_id']
        geometry = shape(row['geometry'])
        for point in geometry.geoms if geometry.geom_type == 'MultiPoint' else (geometry,):
            features.append(feature(point, kind='school', name=school_names[school_id], source_id='athens-schools'))
    return district_shapes, features


def pocket_parks(path, boundary):
    raw = json.loads(path.read_text(encoding='utf-8'))
    if raw.get('type') != 'FeatureCollection' or not raw.get('features'):
        raise ValueError('Municipal pocket park WFS returned no feature collection')
    parks = []
    for row in sorted(raw['features'], key=lambda row: row['id']):
        geometry = shape(row['geometry'])
        point = change_crs(geometry, GEOGRAPHIC_CRS, ATHENS_CRS)
        name = row['properties'].get('descr')
        if point.geom_type != 'Point' or not isinstance(name, str) or not name.strip() or not boundary.covers(point):
            raise ValueError(f'Invalid municipal pocket park: {row["id"]}')
        parks.append(feature(point, kind='pocket_park', name=name.strip(),
                             street=row['properties'].get('streetname'), source_id='athens-pocket-parks'))
    return parks


def planting_points(rows, boundary):
    projection = Transformer.from_crs(WEB_CRS, ATHENS_CRS, always_xy=True)
    points = {}
    for row in rows:
        # The public OpenLayers map feeds these x/y numbers directly into EPSG:3857 geometries.
        point = Point(projection.transform(row['latitude'], row['longitude']))
        if boundary.covers(point):
            points[row['map_location_id']] = point
    if not points:
        raise ValueError('No AthensTrees points matched the municipal boundary and expected CRS')
    return list(points.values())


def planting_features(points):
    cells_by_coordinates = defaultdict(list)
    for point in points:
        cells_by_coordinates[(int(point.x // GRID_M), int(point.y // GRID_M))].append(point)
    features = []
    for _, records in sorted(cells_by_coordinates.items()):
        center = Point(sum(point.x for point in records) / len(records), sum(point.y for point in records) / len(records))
        features.append(feature(center, kind='planting', name='Καταγραφές φυτεύσεων',
                                planting_records_count=len(records), source_id='athens-trees'))
    return features


def intervention_options(site_id, trees, shade_area, greens_area, canopy, planting_count):
    options = []

    def option(kind, cost, cost_source, rationale, shade_projection=None):
        options.append(dict(id=f'{site_id}-{kind}', location_id=site_id, type=kind, cost_eur=cost,
                            feasibility='requires_site_inspection', cost_source_id=cost_source,
                            cost_status='indicative', rationale=rationale, shade_projection=shade_projection))

    if canopy is not None and canopy < 15:
        allowance = 8_000 + trees * 80
        planting_context = (' Ελέγξτε τις υφιστάμενες καταγραφές πριν οριστούν νέες θέσεις.' if planting_count else '')
        projected_crowns = dict(unit_count=trees, unit_projection_min_m2=7.1, unit_projection_max_m2=19.6,
                                horizon='at_tree_maturity', assumption=(
                                    'Ενδεικτική οριζόντια προβολή ώριμης κυκλικής κόμης διαμέτρου 3–5 μ. ανά δέντρο. '
                                    'Η επιφάνεια εξαρτάται από το είδος, τη θέση και την επικάλυψη των κομών.'))
        option('tree_planting', trees * 220 + allowance, 'athens-tree-tender',
               f'Σενάριο {trees} δέντρων × 220 € και ενδεικτική πρόβλεψη {allowance} € για έργα και εγκατάσταση.'
               ' Η διαθέσιμη επιφάνεια, τα δίκτυα, το έδαφος και η άρδευση ελέγχονται στην αυτοψία.' + planting_context,
               projected_crowns)

    shade_allowance = 12_000 + 20 * shade_area
    projected_roof = dict(unit_count=1, unit_projection_min_m2=shade_area, unit_projection_max_m2=shade_area,
                          horizon='after_installation', assumption=(
                              'Οριζόντια επιφάνεια ιστίων του σεναρίου. Η σκιά στο έδαφος μεταβάλλεται '
                              'με τον ήλιο και τη γεωμετρία της κατασκευής.'))
    option('shade_structure', round(49.43 * shade_area + shade_allowance, 2), 'athens-shade-tender',
           f'Σενάριο {shade_area} m² × 49,43 € με πρόβλεψη {shade_allowance} € για προσαρμογή και συνοδά έργα.'
           ' Η υφιστάμενη σκίαση, τα θεμέλια και η όδευση ελέγχονται στην αυτοψία.', projected_roof)

    if greens_area and canopy is not None and canopy < 15:
        option('greenery', 10_000 + greens_area * 80, 'planning-assumptions',
               f'Σενάριο μικρής ζώνης πρασίνου {greens_area} m² με παραδοχή 80 €/m² και 10.000 € για συνοδά έργα.'
               ' Η επιφάνεια και οι δυνατότητες φύτευσης ελέγχονται στην αυτοψία.')
    return options


def roof_option(site_id, area):
    # Reference components: drainage €24.20/m², filter €2.10/m², 8 cm of substrate at €280/m³.
    # The treatment area, thickness and allowances are provisional project inputs.
    cost = round(area * (24.20 + 2.10 + 280 * .08 + 32) + 8_000, 2)
    rationale = (
        f'Σενάριο εκτατικού φυτεμένου δώματος {area} m². Τιμές αναφοράς για αποστράγγιση, '
        'φίλτρο και υπόστρωμα 8 εκ., συν ενδεικτική πρόβλεψη 32 €/m² και 8.000 € για λοιπές εργασίες και μελέτη. '
        'Η διαθέσιμη επιφάνεια, η στατική επάρκεια, η στεγάνωση, η άρδευση και η πρόσβαση ελέγχονται επιτόπου.'
    )
    return dict(id=f'{site_id}-green-roof', location_id=site_id, type='green_roof', cost_eur=cost,
                feasibility='requires_site_inspection', cost_source_id='public-roof-tender',
                cost_status='indicative', rationale=rationale, greened_roof_area_m2=area)


def roof_sites(schools, names):
    available = {row['properties']['sc_id']: shape(row['geometry']) for row in schools}
    for school_id, area in ROOF_SCENARIOS.items():
        geometry = available[school_id]
        if geometry.geom_type == 'MultiPoint' and len(geometry.geoms) == 1:
            geometry = geometry.geoms[0]
        if geometry.geom_type != 'Point':
            raise ValueError(f'Ambiguous geometry for school ID {school_id}')
        yield f'school-{school_id}', names[school_id], geometry, area


def build(raw, snapshot_date):
    paths = {key: raw / filename for key, filename in {
        'atlas': 'municipal-atlas.zip', 'districts': 'municipal-boundary.zip', 'schools': 'municipal-schools.zip',
        'canopy': 'copernicus-tcd2018.tif', 'plantings': 'athenstrees-map.json',
        'population': 'jrc-census-pop-2021.zip',
        'parks': 'municipal-pocket-parks.geojson',
    }.items()}
    for key, page in [('atlas', ATLAS_PAGE), ('districts', DISTRICTS_PAGE), ('schools', SCHOOLS_PAGE)]:
        download_catalog_archive(page.rsplit('/', 1)[-1], paths[key])
    if not paths['canopy'].exists():
        download(CANOPY_EXPORT, paths['canopy'])
    if not paths['plantings'].exists():
        download(TREES_PAGE + 'api/public/map-locations', paths['plantings'])
    if not paths['population'].exists():
        download(POPULATION_DOWNLOAD, paths['population'])
    if not paths['parks'].exists():
        download(PARKS_WFS, paths['parks'])

    atlas, districts, schools = (read_catalog_geojson(paths[key]) for key in ('atlas', 'districts', 'schools'))
    school_names = school_name_map(paths['schools'])
    district_shapes, context = normalized_context(districts['features'], schools['features'], school_names)
    boundary = union_all(list(district_shapes.values()))
    context.extend(pocket_parks(paths['parks'], boundary))
    atlas_polygons, atlas_temperatures = heat_geometries(atlas['features'])
    atlas_index = STRtree(atlas_polygons)
    plantings = planting_points(json.loads(paths['plantings'].read_text(encoding='utf-8')), boundary)
    planting_index = STRtree(plantings)
    trees = planting_features(plantings)
    heat, locations, interventions = [], [], []
    population_raster_path = 'zip://' + paths['population'].resolve().as_posix() + '!' + POPULATION_MEMBER
    site_records = [(site_id, name, Point(x, y), (trees, shade, greens), None)
                    for site_id, name, x, y, trees, shade, greens in SITES]
    site_records.extend((site_id, name, point, None, roof_area)
                        for site_id, name, point, roof_area in roof_sites(schools['features'], school_names))

    with rasterio.open(paths['canopy']) as canopy_raster, rasterio.open(population_raster_path) as census:
        if canopy_raster.count != 1 or canopy_raster.crs.to_epsg() != 3857:
            raise ValueError('The canopy export must be a one-band EPSG:3857 percentage raster')
        if census.count != 1 or census.crs.to_epsg() != 3035 or census.res != (100, 100):
            raise ValueError('The population source must be an equal-area, 100-metre EPSG:3035 raster')
        for area in cells(boundary):
            temperature = weighted_heat(area, atlas_polygons, atlas_temperatures, atlas_index)
            display_area = area.simplify(3)
            if temperature is not None:
                heat.append(feature(display_area, temperature_c=temperature, source_id='athens-atlas'))
            canopy = canopy_mean(canopy_raster, area)
            if canopy is not None:
                trees.append(feature(display_area, kind='canopy', canopy_percent=canopy, source_id='copernicus-canopy'))

        for site_id, name, point, street_quantities, roof_area in site_records:
            district = next((number for number, region in district_shapes.items() if region.covers(point)), None)
            if district is None:
                raise ValueError(f'Site falls outside Athens municipal boundaries: {site_id}')
            vicinity = point.buffer(SITE_RADIUS_M).intersection(boundary)
            temperature = weighted_heat(vicinity, atlas_polygons, atlas_temperatures, atlas_index)
            canopy = canopy_mean(canopy_raster, vicinity)
            density = population_density(census, vicinity)
            planting_count = len(planting_index.query(vicinity, predicate='covers'))
            longitude, latitude = geojson_geometry(point)['coordinates']
            reference_source = 'athens-schools' if roof_area else 'athens-sites'
            source_ids = [reference_source, 'athens-districts', 'athens-trees']
            if temperature is not None:
                source_ids.append('athens-atlas')
            if canopy is not None:
                source_ids.append('copernicus-canopy')
            if density is not None:
                source_ids.append('jrc-estat-population')
            locations.append(dict(id=site_id, name=name, district=f'{district}η ΔΚ', latitude=latitude,
                                  longitude=longitude, heat_c=temperature, canopy_percent=canopy,
                                  shade_status='unknown', source_ids=source_ids, plantings_count=None,
                                  planting_records_count=planting_count, planting_documented=planting_count > 0,
                                  population_density_per_km2=density,
                                  population_source_id='jrc-estat-population' if density is not None else None,
                                  population_grid_m=100 if density is not None else None))
            if temperature is not None:
                if roof_area:
                    interventions.append(roof_option(site_id, roof_area))
                else:
                    interventions.extend(intervention_options(site_id, *street_quantities, canopy, planting_count))

    if len(heat) < 500 or len(atlas_polygons) < 1000:
        raise ValueError('Heat layer has unexpectedly little valid coverage. Check the municipal source.')

    temperatures = [item['properties']['temperature_c'] for item in heat]
    print(f'Heat cells: {len(heat)}, range {min(temperatures):.2f}–{max(temperatures):.2f} °C, '
          f'quartiles {quantiles(temperatures, n=4, method="inclusive")}')
    print(f'{len(plantings)} planting records, {len(context)} context features, {len(interventions)} interventions')
    for location in locations:
        print(location['id'], location['heat_c'], location['canopy_percent'], location['planting_records_count'],
              location['population_density_per_km2'])

    return dict(dataset_version=f'athens-{snapshot_date}.3', sources=source_registry(snapshot_date),
                heat=collection(heat), trees=collection(trees), context=collection(context),
                locations=locations, interventions=interventions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=PROJECT / 'data' / 'raw')
    parser.add_argument('--output', type=Path, default=PROJECT / 'data' / 'processed' / 'athens.json')
    parser.add_argument('--snapshot-date', type=date.fromisoformat, required=True,
                        help='Actual retrieval date of the cached AthensTrees response, in YYYY-MM-DD')
    options = parser.parse_args()
    options.raw.mkdir(parents=True, exist_ok=True)
    payload = build(options.raw, options.snapshot_date)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = options.output.with_suffix('.json.part')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n',
                         encoding='utf-8')
    temporary.replace(options.output)
    print(f'Wrote {options.output.stat().st_size:,} bytes to {options.output}')


if __name__ == '__main__':
    main()
