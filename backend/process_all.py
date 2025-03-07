import json
import logging
import numpy as np
import os
import pandas as pd
import time

from process_one import *


# load config file
with open('config.json') as f:
    config = json.load(f)

# set up logging
os.system(f'mv {config['logs_path']}process_all.log {config['logs_path']}process_all.log.previous')
logger = logging.getLogger('process_all')
logger.setLevel(logging.DEBUG if config.get('debug') else logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler = logging.FileHandler(config['logs_path'] + 'process_all.log', mode='w')
handler.setFormatter(formatter)
logger.addHandler(handler)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)
del handler, formatter
if config.get('debug'):
    logger.info('started logging in debug mode')
else:
    logger.info('started logging with debug mode turned off')

# load regions
regions = pd.read_csv(
    config['regions_path'],
    sep=',',
    index_col=0,
    header=0,
    keep_default_na=False,
    dtype={
        'osm_id': np.int64,
        'name': str,
        'code': str,
        'admin_level': np.uint8,
        'parent_osm_id': np.int64,
        'lon': np.float32,
        'lat': np.float32,
        'radius': np.float32
    }
)
logger.info(f'found {len(regions)} regions')

# prepare per-region logging
region_logger = logging.getLogger('region')
region_logger.setLevel(logging.DEBUG if config.get('debug') else logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
region_logger.addHandler(handler)
del handler

# create temporary ploles and data path
logger.info('creating temporary ploles and data paths...')
os.system(f'mkdir {config["ploles_tmp_path"]}')
os.system(f'mkdir {config["data_tmp_path"]}')

# mark parents/leaves
regions['is_parent'] = False
for i in regions.index:
    parent_id = regions.loc[i, 'parent_osm_id']
    if parent_id != 0:
        regions.loc[parent_id, 'is_parent'] = True

# create world regions (for world statistics)
regions = pd.concat([regions, pd.DataFrame(data={
    'name': 'World',
    'code': 'WORLD',
    'admin_level': 0,
    'parent_osm_id': -1,
    'lon': 0,
    'lat': 0,
    'radius': 0,
    'is_parent': True
}, index=[0])])

# add colums for statistics (-1 for unprocessed parents)
regions['stops'] = 0
regions['plafos'] = 0
regions['poles'] = 0
regions['stopos'] = 0
regions['dubobs'] = 0
regions['process_start'] = ''
regions['process_end'] = ''
regions.loc[regions['is_parent'], 'stops'] = -1

# get regions to process
if config['regions_mode'] == 'include':
    include_mask = regions['code'].isin(config['regions_codes'])
else:  # exclude
    include_mask = ~regions['code'].isin(config['regions_codes'])
parent_mask = regions['is_parent']
to_process = regions.loc[include_mask & ~parent_mask, :].index
logger.info(f'regions to process: {len(to_process)}')

# process regions
for i, osm_id in enumerate(to_process):
    code = regions.loc[osm_id, 'code'].lower()

    # enable logging to region's log file
    file_handler = logging.FileHandler(f'{config["logs_path"]}{code}.log', mode='w')
    file_handler.setFormatter(formatter)
    region_logger.addHandler(file_handler)

    # process region
    region = regions.loc[osm_id, :]
    logger.info(f'processing region {i + 1}/{len(to_process)} ({region["name"]}, {code})...')
    regions.loc[osm_id, 'process_start'] = get_timestamp()
    config['region'] = region['name']
    config['meters_crs'] = f'+proj=aeqd +lat_0={region["lat"]} +lon_0={region["lon"]}'
    config['region_code'] = code
    config['osm_id'] = osm_id
    try:
        success, msg = process(config)
    except Exception as e:
        logger.exception(e)
        success = False
        msg = 'exception'
    if success:
        logger.info('...done')
    else:
        logger.error(f'...failed ({msg})')
        logger.info('copying region\'s old ploles to temporary plole location...')
        os.system(f'cp {config["ploles_path"]}{config['region_code']}*.json {config["ploles_tmp_path"]}')
        logger.info('...done copying old ploles')
        logger.info('copying region\'s old data to temporary data location...')
        os.system(f'cp {config["data_path"]}{config['region_code']}* {config["data_tmp_path"]}')
        logger.info('...done copying old data')
    regions.loc[osm_id, 'process_end'] = get_timestamp()
    
    # copy region stats to region's data frame
    try:
        stats = pd.read_csv(f'{config['data_tmp_path']}{config['region_code']}_stats.csv')
        i = stats.index[-1]
        regions.loc[osm_id, 'stops'] = stats.loc[i, 'stops']
        regions.loc[osm_id, 'plafos'] = stats.loc[i, 'plafos']
        regions.loc[osm_id, 'poles'] = stats.loc[i, 'poles']
        regions.loc[osm_id, 'stopos'] = stats.loc[i, 'stopos']
        regions.loc[osm_id, 'dubobs'] = stats.loc[i, 'dubobs']
    except:
        logger.warning('region has no stats file')
    
    # disable logging to region's log file
    region_logger.removeHandler(file_handler)
    del file_handler

# make stats for parent regions
logger.info('generating regions data')
parents_todo = [0]
while len(parents_todo) > 0:
    osm_id = parents_todo[-1]
    children_mask = regions['parent_osm_id'] == osm_id
    unprocessed_mask = children_mask & (regions['stops'] == -1)
    if unprocessed_mask.any():
        parents_todo.extend(list(regions.index[unprocessed_mask]))
    else:  # all children already processed
        regions.loc[osm_id, 'stops'] = regions.loc[children_mask, 'stops'].sum()
        regions.loc[osm_id, 'plafos'] = regions.loc[children_mask, 'plafos'].sum()
        regions.loc[osm_id, 'poles'] = regions.loc[children_mask, 'poles'].sum()
        regions.loc[osm_id, 'stopos'] = regions.loc[children_mask, 'stopos'].sum()
        regions.loc[osm_id, 'dubobs'] = regions.loc[children_mask, 'dubobs'].sum()
        date_mask = children_mask & (regions['process_start'] != '')
        if date_mask.any():
            regions.loc[osm_id, 'process_start'] = pd.to_datetime(
                regions.loc[date_mask, 'process_start'], utc=True, format='%Y-%m-%d %H:%M:%S'
            ).min().strftime('%Y-%m-%d %H:%M:%S')
            regions.loc[osm_id, 'process_end'] = pd.to_datetime(
                regions.loc[date_mask, 'process_end'], utc=True, format='%Y-%m-%d %H:%M:%S'
            ).max().strftime('%Y-%m-%d %H:%M:%S')
        parents_todo.pop()
regions.index.name = 'osm_id'
regions.to_csv(f'{config['data_tmp_path']}regions.csv')

# generate region table html
logger.info('generating data download page')
def region_html(osm_id, indent):
    html = '<tr>\n'
    html += f'<td>{indent * 5 * '&nbsp;'}'
    html += f'<a href="index.html#6/{regions.loc[osm_id, 'lat']}/{regions.loc[osm_id, 'lon']}">{regions.loc[osm_id, 'name']}</a> '
    html += f'({regions.loc[osm_id, 'code']})</td>\n'
    html += f'<td>{regions.loc[osm_id, 'process_end']}</td>\n'
    html += f'<td>{regions.loc[osm_id, 'stops']}</td>\n'
    html += f'<td>{regions.loc[osm_id, 'plafos']}</td>\n'
    html += f'<td>{regions.loc[osm_id, 'poles']}</td>\n'
    html += f'<td>{regions.loc[osm_id, 'stopos']}</td>\n'
    html += f'<td>{regions.loc[osm_id, 'dubobs']}</td>\n'
    if regions.loc[osm_id, 'is_parent'] or regions.loc[osm_id, 'process_end'] == '':
        html += f'<td>&nbsp;</td>\n'
    else:
        html += f'<td><a href="data/{regions.loc[osm_id, 'code'].lower()}_stops.csv">stops</a>, '
        html += f'<a href="data/{regions.loc[osm_id, 'code'].lower()}_stats.csv">statistics</a></td>\n'
    html += '</tr>\n'
    if regions.loc[osm_id, 'is_parent']:
        children = regions.loc[regions['parent_osm_id'] == osm_id, :].sort_values('name')
        for child_osm_id in children.index:
            html += region_html(child_osm_id, indent + 1)
    return html
html = region_html(0, 0)

# create data download page from template and region table html
with open(f'{config['data_html_path']}.template') as f:
    template_html = f.read()
with open(config['data_html_path'], 'w') as f:
    f.write(template_html.replace('<!--AUTOGENERATED_REGION_TABLE-->', html))

# join tiles from all regions
logger.info('joining tiles...')
os.system(f'mkdir {config["tiles_tmp_path"]}')
cmd = f'tile-join --no-tile-size-limit --output-to-directory={config["tiles_tmp_path"]} --no-tile-compression {config["export_path"]}*.mbtiles'
os.system(cmd)
logger.info('...done')

# replace tiles, ploles, data
logger.info('moving old tiles, ploles, data to temporary location...')
os.system(f'mv {config["tiles_path"]} {config["tiles_old_path"]}')
os.system(f'mv {config["ploles_path"]} {config["ploles_old_path"]}')
os.system(f'mv {config["data_path"]} {config["data_old_path"]}')
logger.info('moving new tiles, ploles, data to destination path...')
os.system(f'mv {config["tiles_tmp_path"]} {config["tiles_path"]}')
os.system(f'mv {config["ploles_tmp_path"]} {config["ploles_path"]}')
os.system(f'mv {config["data_tmp_path"]} {config["data_path"]}')
logger.info('removing old tiles, ploles, data...')
os.system(f'rm -r {config["tiles_old_path"]}')
os.system(f'rm -r {config["ploles_old_path"]}')
os.system(f'rm -r {config["data_old_path"]}')
logger.info('...done')
