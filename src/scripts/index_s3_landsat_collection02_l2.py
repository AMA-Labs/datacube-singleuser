#!/usr/bin/python3
import boto3, json, re, uuid, logging, datacube
from datacube.index.hl import Doc2Dataset
from datacube.utils import changes
from datetime import datetime

from osgeo import osr, ogr
import osgeo.gdal
from packaging import version
import click

MTL_PAIRS_RE = re.compile(r'(\w+)\s=\s(.*)')
LON_LAT_ORDER = version.parse(osgeo.gdal.__version__) < version.parse("3.0.0")

oli_tirs = [
    ('BAND_1', 'coastal_aerosol'),
    ('BAND_2', 'blue'),
    ('BAND_3', 'green'),
    ('BAND_4', 'red'),
    ('BAND_5', 'nir'),
    ('BAND_6', 'swir1'),
    ('BAND_7', 'swir2'),
    ('BAND_ST_B10', 'thermal_infrared'),
    ('THERMAL_RADIANCE', 'thermal_radiance'),
    ('UPWELL_RADIANCE', 'upwelled_radiance'),
    ('DOWNWELL_RADIANCE', 'downwelled_radiance'),
    ('ATMOSPHERIC_TRANSMITTANCE', 'atmospheric_transmittance'),
    ('EMISSIVITY', 'emissivity'),
    ('EMISSIVITY_STDEV', 'emissivity_stdev'),
    ('CLOUD_DISTANCE', 'cloud_distance'),
    ('QUALITY_L1_PIXEL', 'l1_quality_pixel'),
    ('QUALITY_L1_RADIOMETRIC_SATURATION', 'l1_quality_radiometric_saturation'),
    ('QUALITY_L2_AEROSOL', 'l2_sr_aerosol_quality'),
    ('QUALITY_L2_SURFACE_TEMPERATURE', 'l2_st_quality')
]

etm = [
    ('BAND_1', 'BAND_1'),
    ('BAND_2', 'BAND_2'),
    ('BAND_3', 'BAND_3'),
    ('BAND_4', 'BAND_4'),
    ('BAND_5', 'BAND_5'),
    ('BAND_ST_B6', 'BAND_ST_B6'),
    ('BAND_7', 'BAND_7'),
    ('THERMAL_RADIANCE', 'THERMAL_RADIANCE'),
    ('UPWELL_RADIANCE', 'UPWELL_RADIANCE'),
    ('DOWNWELL_RADIANCE', 'DOWNWELL_RADIANCE'),    
    ('ATMOSPHERIC_TRANSMITTANCE', 'ATMOSPHERIC_TRANSMITTANCE'),
    ('EMISSIVITY', 'EMISSIVITY'),
    ('EMISSIVITY_STDEV', 'EMISSIVITY_STDEV'),
    ('CLOUD_DISTANCE', 'CLOUD_DISTANCE'),
    ('ATMOSPHERIC_OPACITY', 'ATMOSPHERIC_OPACITY'),
    ('QUALITY_L2_SURFACE_REFLECTANCE_CLOUD', 'QUALITY_L2_SURFACE_REFLECTANCE_CLOUD'),
    ('QUALITY_L2_SURFACE_TEMPERATURE', 'QUALITY_L2_SURFACE_TEMPERATURE'),
    ('QUALITY_L1_PIXEL', 'QUALITY_L1_PIXEL'),
    ('QUALITY_L1_RADIOMETRIC_SATURATION', 'QUALITY_L1_RADIOMETRIC_SATURATION')
]

tm = [
    ('BAND_1', 'BAND_1'),
    ('BAND_2', 'BAND_2'),
    ('BAND_3', 'BAND_3'),
    ('BAND_4', 'BAND_4'),
    ('BAND_5', 'BAND_5'),
    ('BAND_ST_B6', 'BAND_ST_B6'),
    ('BAND_7', 'BAND_7'),
    ('THERMAL_RADIANCE', 'THERMAL_RADIANCE'),
    ('UPWELL_RADIANCE', 'UPWELL_RADIANCE'),
    ('DOWNWELL_RADIANCE', 'DOWNWELL_RADIANCE'),    
    ('ATMOSPHERIC_TRANSMITTANCE', 'ATMOSPHERIC_TRANSMITTANCE'),
    ('EMISSIVITY', 'EMISSIVITY'),
    ('EMISSIVITY_STDEV', 'EMISSIVITY_STDEV'),
    ('CLOUD_DISTANCE', 'CLOUD_DISTANCE'),
    ('ATMOSPHERIC_OPACITY', 'ATMOSPHERIC_OPACITY'),
    ('QUALITY_L2_SURFACE_REFLECTANCE_CLOUD', 'QUALITY_L2_SURFACE_REFLECTANCE_CLOUD'),
    ('QUALITY_L2_SURFACE_TEMPERATURE', 'QUALITY_L2_SURFACE_TEMPERATURE'),
    ('QUALITY_L1_PIXEL', 'QUALITY_L1_PIXEL'),
    ('QUALITY_L1_RADIOMETRIC_SATURATION', 'QUALITY_L1_RADIOMETRIC_SATURATION')
]

# bucket = "landsat-pds"
# key = "L8/001/002/LC80010022016230LGN00/LC80010022016230LGN00_MTL.json"

def get_s3_url(bucket_name, obj_key):
    return 's3://{bucket_name}/{obj_key}'.format(
        bucket_name=bucket_name, obj_key=obj_key)

def _parse_value(s):
    s = s.strip('"')
    for parser in [int, float]:
        try:
            return parser(s)
        except ValueError:
            pass
    return s

def _parse_group(lines):
    tree = {}
    for line in lines:
        match = MTL_PAIRS_RE.findall(line)
        if match:
            key, value = match[0]
            if key == 'GROUP':
                tree[value] = _parse_group(lines)
            elif key == 'END_GROUP':
                break
            else:
                tree[key] = _parse_value(value)
    return tree

def get_geo_ref_points(info):
    return {
        'ul': {'x': float(info['CORNER_UL_PROJECTION_X_PRODUCT']), 'y': float(info['CORNER_UL_PROJECTION_Y_PRODUCT'])},
        'ur': {'x': float(info['CORNER_UR_PROJECTION_X_PRODUCT']), 'y': float(info['CORNER_UR_PROJECTION_Y_PRODUCT'])},
        'll': {'x': float(info['CORNER_LL_PROJECTION_X_PRODUCT']), 'y': float(info['CORNER_LL_PROJECTION_Y_PRODUCT'])},
        'lr': {'x': float(info['CORNER_LR_PROJECTION_X_PRODUCT']), 'y': float(info['CORNER_LR_PROJECTION_Y_PRODUCT'])},
    }

def get_coords(geo_ref_points, spatial_ref):
    t = osr.CoordinateTransformation(spatial_ref, spatial_ref.CloneGeogCS())

    def transform(p):
        if LON_LAT_ORDER:
            # GDAL 2.0 order
            lon, lat, z = t.TransformPoint(p['x'], p['y'])
        else:
            # GDAL 3.0 order
            lat, lon, z = t.TransformPoint(p['x'], p['y'])
            
        return {'lon': lon, 'lat': lat}
        
    return {key: transform(p) for key, p in geo_ref_points.items()}

def satellite_ref(sensor_id):
    """
    To load the band_names for referencing either LANDSAT8 or LANDSAT7 bands
    """
    if sensor_id == 'OLI_TIRS':
        sat_img = oli_tirs
    elif sensor_id == 'ETM' :
        sat_img = etm
    elif sensor_id == 'TM':
        sat_img = tm
    else:
        raise ValueError('Satellite data Not Supported')
    return sat_img

def format_obj_key(obj_key):
    obj_key = '/'.join(obj_key.split("/")[:-1])
    return obj_key

def absolutify_paths(doc, bucket_name, obj_key):
    objt_key = format_obj_key(obj_key)
    for band in doc['image']['bands'].values():
        band['path'] = get_s3_url(bucket_name, objt_key + '/' + band['path'])
    return doc

def make_metadata_doc(mtl_data, bucket_name, object_key):
    mtl_product_info = mtl_data['IMAGE_ATTRIBUTES']
    mtl_metadata_info = mtl_data['PRODUCT_CONTENTS']
    satellite = mtl_product_info['SPACECRAFT_ID']
    instrument = mtl_product_info['SENSOR_ID']
    acquisition_date = mtl_product_info['DATE_ACQUIRED']
    scene_center_time = mtl_product_info['SCENE_CENTER_TIME']
    level = mtl_metadata_info['PROCESSING_LEVEL']
    product_type = mtl_metadata_info['PROCESSING_LEVEL']
    sensing_time = acquisition_date + ' ' + scene_center_time
    cs_code = 32600 + int(mtl_data['PROJECTION_ATTRIBUTES']['UTM_ZONE'])
    label = mtl_metadata_info['LANDSAT_PRODUCT_ID']
    spatial_ref = osr.SpatialReference()
    spatial_ref.ImportFromEPSG(cs_code)
    geo_ref_points = get_geo_ref_points(mtl_data['PROJECTION_ATTRIBUTES'])
    coordinates = get_coords(geo_ref_points, spatial_ref)
    bands = satellite_ref(instrument)
    doc = {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, get_s3_url(bucket_name, object_key))),
        'processing_level': level,
        'product_type': product_type,
        'creation_dt': str(acquisition_date),
        'label': label,
        'platform': {'code': satellite},
        'instrument': {'name': instrument},
        'extent': {
            'from_dt': sensing_time,
            'to_dt': sensing_time,
            'center_dt': sensing_time,
            'coord': coordinates,
        },
        'format': {'name': 'GeoTiff'},
        'grid_spatial': {
            'projection': {
                'geo_ref_points': geo_ref_points,
                'spatial_reference': 'EPSG:%s' % cs_code,
            }
        },
        'image': {
            'bands': {
                band[1]: {
                    'path': mtl_metadata_info['FILE_NAME_' + band[0]],
                    'layer': 1,
                } for band in bands
            }
        },
        'lineage': {'source_datasets': {}},
    }
    doc = absolutify_paths(doc, bucket_name, object_key)
    return doc

def convert_ll_to_pr(extent, ascending, path):
    """ Convert lat, lon to pathrows """
    logging.info("Starting the conversion from ll to pathrow for area: {}".format(extent))
    driver = ogr.GetDriverByName('ESRI Shapefile')
    file_path = '/vsizip/' + path 
    dataSource = driver.Open(file_path, 0) # 0 means read-only. 1 means writeable.
    if not dataSource:
        logging.error("Failed to open the file: {}".format(file_path))
        return
    layer = dataSource.GetLayer()

    ring = ogr.Geometry(ogr.wkbLinearRing)
    # Stupid geometry is lat, lon instead of lon, lat...
    ring.AddPoint(extent[0], extent[2])
    ring.AddPoint(extent[0], extent[3])
    ring.AddPoint(extent[1], extent[3])
    ring.AddPoint(extent[1], extent[2])
    ring.AddPoint(extent[0], extent[2])
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)

    logging.info("Usion bbox filter: {}".format(poly.ExportToJson()))
    layer.SetSpatialFilter(poly)

    if not ascending:
        layer.SetAttributeFilter("MODE = 'A'")
    else:
        layer.SetAttributeFilter("MODE = 'D'")


    logging.info("Found {} features.".format(layer.GetFeatureCount()))
    pathRows = []
    for pInfo in layer:
        pathRows.append([pInfo.GetField('PATH'), pInfo.GetField('ROW')])

    return pathRows

def add_dataset(doc, uri, index, **kwargs):
    logging.info("Indexing %s", uri)
    resolver = Doc2Dataset(index, **kwargs)
    dataset, err = resolver(doc, uri)
    if err is not None:
        logging.error("%s", err)
    else:
        try:
            index.datasets.add(dataset)  # Source policy to be checked in sentinel 2 datase types
        except changes.DocumentMismatchError as e:
            index.datasets.update(dataset, {tuple(): changes.allow_any})
        except Exception as e:
            err = e
            logging.error("Unhandled exception %s", e)

    return dataset, err

@click.command()
@click.option('--extents', '-e', default="35,43.4,29.4,37.3", help="Extent to index in the form lon_min,lon_max,lat_min,latmax [default=35,43.4,29.4,37.3]")
@click.option('--pathrow_file', '-p', default="/opt/odc/data/wrs2_descending.zip", help="Absolute path to the pathrow file, e.g., /tmp/example.zip [default=/opt/odc/data/wrs2_descending.zip]")
@click.option('--start_date', default="1980-01-01", help="Start date of the acquisitions to index, in YYYY-MM-DD format [default=1980-01-01]")
@click.option('--end_date', default="2099-12-31", help="End date of the acquisitions to index, in YYYY-MM-DD format [default=2099-12-31]")
@click.option('--prefix', '-p', default="collection02", help="Pass the prefix of the object to the bucket [default=collection02]")
@click.option('--level', '-l', default="level-2", help="What level of product(level-1, level-2) [default=level-2]")
@click.option('--sensor', '-z', default="oli-tirs", help="What sensor to use(etm, oli-tirs, tm) [default=oli-tirs]")
@click.option('--suffix', '-s', default=".json", help="Defines the suffix of the metadata_docs that will be used to load datasets. For AWS PDS bucket use MTL.txt [default=.json]")
def main(extents, pathrow_file, start_date, end_date, prefix, level, sensor, suffix):
    bucket = "usgs-landsat"
    odc = boto3.session.Session() #for specific profile add: profile_name="odc" to Session definition boto3.session.Session(profile_name="odc")
    s3 = odc.client("s3")
    logging.info("Bucket : %s prefix: %s Level: %s", bucket, str(prefix), level)
    dc = datacube.Datacube()
    index = dc.index
    lon_min, lon_max, lat_min, lat_max = map(float, extents.split(','))
    pathRows = convert_ll_to_pr([lon_min, lon_max, lat_min, lat_max], True, pathrow_file)        
    sdate = datetime.strptime(start_date,"%Y-%m-%d")       
    edate = datetime.strptime(end_date,"%Y-%m-%d")
    logging.info("indexing summary: years: {}->{} path/rows: {}".format(sdate.year, edate.year,pathRows))
    nrindexed=0
    for year in range(sdate.year,edate.year+1):
        for pr in pathRows:        
            key_base = "{}/{}/standard/{}/{}/{}/{}/".format(prefix, level, sensor, year,str(pr[0]).zfill(3),str(pr[1]).zfill(3))
            s3list = s3.list_objects(Bucket=bucket, Prefix=key_base, RequestPayer='requester')
            # print(s3list)
            if "Contents" in s3list:
                for k in s3list["Contents"]:
                    key = k["Key"]
                    if "MTL.json" in key:
                        nrindexed+=1
                        # logging.info("indexing s3://{}/{}".format(bucket,key))
                        obj = s3.get_object(Bucket=bucket, Key=key, RequestPayer='requester')
                        # # mtl_raw = obj["Body"].read().decode('utf8')
                        # # mtl_obj = _parse_group(iter(mtl_raw.split("\n")))
                        mtl_obj = json.loads(obj["Body"].read().decode('utf-8'))["LANDSAT_METADATA_FILE"]
                        # print(json.dumps(mtl_obj, indent=1))
                        datacube_yaml = make_metadata_doc(mtl_obj, bucket, key)
                        # print(json.dumps(datacube_yaml, indent=1))
                        add_dataset(datacube_yaml,get_s3_url(bucket, key),index)
    
    logging.info("indexing successfully completed. Indexed {} scenes".format(nrindexed))


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
    main()