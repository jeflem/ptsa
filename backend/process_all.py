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

# mark parents/leaves
regions['is_parent'] = False
for i in regions.index:
    parent_id = regions.loc[i, 'parent_osm_id']
    if parent_id != 0:
        regions.loc[parent_id, 'is_parent'] = True

# get regions to process
if config['regions_mode'] == 'include':
    include_mask = regions['code'].isin(config['regions_codes'])
else:  # exclude
    include_mask = ~regions['code'].isin(config['regions_codes'])
parent_mask = regions['is_parent']
to_process = regions.loc[include_mask & ~parent_mask, :].index
logger.info(f'regions to process: {len(to_process)}')

# process regions
for osm_id in to_process:
    code = regions.loc[osm_id, 'code'].lower()

    # enable logging to region's log file
    file_handler = logging.FileHandler(f'{config["logs_path"]}{code}.log', mode='w')
    file_handler.setFormatter(formatter)
    region_logger.addHandler(file_handler)

    # process region
    region = regions.loc[osm_id, :]
    logger.info(f'processing region {region["name"]} ({code})...')
    config['region'] = region['name']
    config['meters_crs'] = f'+proj=aeqd +lat_0={region["lat"]} +lon_0={region["lon"]}'
    config['region_code'] = code
    config['osm_id'] = osm_id
    try:
        success = process(config)
    except Exception as e:
        logger.exception(e)
        success = False
    if success:
        logger.info('...done')
    else:
        logger.error('...failed')
    
    # disable logging to region's log file
    region_logger.removeHandler(file_handler)
    del file_handler

# join tiles from all regions
logger.info('joining tiles...')
os.system(f'mkdir {config["tiles_tmp_path"]}')
cmd = f'tile-join --output-to-directory={config["tiles_tmp_path"]} --no-tile-compression {config["export_path"]}*.mbtiles'
os.system(cmd)
logger.info('removing old tiles...')
os.system(f'rm -r {config["tiles_path"]}')
logger.info('moving new tiles to destination path...')
os.system(f'mv {config["tiles_tmp_path"]} {config["tiles_path"]}')
logger.info('...done')

# update regions data
regions.to_csv(config['regions_path'])
