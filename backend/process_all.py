import json
import logging
import numpy as np
import pandas as pd
import time


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
        'code': str,
        'admin_level': np.uint8,
        'name': str,
        'meters_crs': str,
        'ignore': bool,
        'timestamp': np.uint64
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

# process regions
for code in regions.index:

    # enable logging to region's log file
    file_handler = logging.FileHandler(f'{config['logs_path']}{code}.log', mode='w')
    file_handler.setFormatter(formatter)
    region_logger.addHandler(file_handler)

    # process region
    region = regions.loc[code, :]
    if region['ignore']:
        logger.info(f'ignoring region {region['name']} ({code})')
        continue
    logger.info(f'processing region {region['name']} ({code})')
    regions.loc[code, 'timestamp'] = int(time.time())
    # TODO: process region
    
    # disable logging to region's log file
    region_logger.removeHandler(file_handler)
    del file_handler

# update regions data
regions.to_csv(config['regions_path'])
