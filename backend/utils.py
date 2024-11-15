import logging
import requests
from shapely.geometry import Point, LineString


logger = logging.getLogger('region') 


class OSMObject:

    def __init__(self, j, t):

        self.type = t
        self.id = j['id']
        if j.get('tags'):
            self.tags = j['tags']
        else:
            self.tags = dict()
        self.comments = []
        self.warnings = []

        # check for multiple values
        self.multiple_values = False
        for key, value in self.tags.items():
            if ';' in value:
                self.multiple_values = True
                #self.comment(f'multiple values for key {key}')

    def __str__(self):

        return f'{self.type} {self.id}'

    def __repr__(self):

        return f'{self.type} {self.id}'

    def comment(self, text):

        self.comments.append(text)
        
        logger.info(f'comment for {self.type} {self.id}: {text}')

    def warning(self, text):

        self.warnings.append(text)
        
        logger.info(f'warning for {self.type} {self.id}: {text}')
    
    def has_tag(self, key, value):

        # key exists?
        obj_value = self.tags.get(key)
        if not obj_value:
            return False

        # value matches?
        if  obj_value == value:
            return True

        # value matches in case of multiple values?
        if self.multiple_values:
            for single_value in obj_value.split(';'):
                if single_value == value:
                    return True

        # no match
        return False


class Node(OSMObject):

    def __init__(self, j):

        super().__init__(j, 'node')
        self.lon = j['lon']
        self.lat = j['lat']


class Way(OSMObject):

    def __init__(self, j):

        super().__init__(j, 'way')
        self.node_ids = j['nodes']


class RelMember:

    def __init__(self, type_, id_, role):

        self.type = type_
        self.id = id_
        self.role = role


class Relation(OSMObject):

    def __init__(self, j):

        super().__init__(j, 'rel')
        self.members = [RelMember(m['type'], m['ref'], m['role'])
                        for m in j['members']]

class Area(OSMObject):

    def __init__(self, base_obj, nodes_dict={}, ways_dict={}):

        if isinstance(base_obj, Way):
            self.id = base_obj.id
            self.type = 'way_area'
        elif isinstance(base_obj, Relation) \
        and base_obj.has_tag('type', 'multipolygon'):
            self.id = -base_obj.id
            self.type = 'mupo_area'
        else:
            raise Exception(f'Cannot make area from {str(base_obj)}!')
        
        self.tags = base_obj.tags
        self.multiple_values = base_obj.multiple_values
        self.comments = base_obj.comments.copy()
        self.warnings = base_obj.warnings.copy()

        if self.type == 'way_area':
            line = LineString([(nodes_dict[n_id].lon, nodes_dict[n_id].lat) \
                               for n_id in base_obj.node_ids])
            if base_obj.node_ids[0] != base_obj.node_ids[-1]:
                self.from_line = True
                self.geometry = line
            else:
                self.from_line = False
                self.geometry = [line]
        else:  # multipolgon
            self.from_line = False
            ways = [ways_dict[m.id] for m in base_obj.members 
                                    if m.type == 'way' and m.role == 'outer']
            if ways == []:  # no outer rings, use all ways
                ways = [ways_dict[m.id] for m in base_obj.members if m.type == 'way']
                self.warning('invalid area')
            self.geometry = [
                LineString([(nodes_dict[n_id].lon, nodes_dict[n_id].lat)
                            for n_id in w.node_ids])
                for w in ways
            ] 


def filesize2str(size):

    if size < 1000:
        return f'{size} byte'
    elif size < 1000 ** 2:
        return f'{size / 1000:.0f} kB'
    elif size < 1000 ** 3:
        return f'{size / (1000 ** 2):.0f} MB'
    else:
        return f'{size / (1000 ** 3):.0f} GB'
    

def overpass(query, config, ids_only=False, verbose=1):

    preamble = '[output: json][timeout: {timeout}];\n'.format(
        timeout=str(config['overpass_timeout']),
    )
    r = requests.post(
        config['overpass_url'],
        data={'data': preamble + query},
        headers={'X-API-Key': config['overpass_key']}
    )

    if r.status_code != 200:
        logger.error(f'overpass server returned {r.status_code} for query\n{query}')
        return [], [], []
    
    j = r.json()
    objects = j['elements']

    if verbose > 0:
        logger.info(f'overpass download size: {filesize2str(len(r.content))}')
        if j.get('remarks'):
            logger.warning(f'overpass remarks: {j['remarks']}')
        if len(objects) == 0:
            logger.error(f'overpass returned: {r.content.decode()}')

    if ids_only:
        nodes = [obj.get('id') for obj in objects if obj.get('type') == 'node']
        ways = [obj.get('id') for obj in objects if obj.get('type') == 'way']
        rels = [obj.get('id') for obj in objects if obj.get('type') == 'relation']
    else:
        nodes = [Node(obj) for obj in objects if obj.get('type') == 'node']
        ways = [Way(obj) for obj in objects if obj.get('type') == 'way']
        rels = [Relation(obj) for obj in objects if obj.get('type') == 'relation']

    if verbose > 0:
        logger.info(f'total OSM objects: {len(objects)}')
        logger.info(f'OSM nodes: {len(nodes)}')
        logger.info(f'OSM ways: {len(ways)}')
        logger.info(f'OSM relations: {len(rels)}')
    
    return nodes, ways, rels


def add_mods(mods1, mods2):
    mods1.update(mods2)

def mods2str(mods):
    if len(mods) == 0:
        return 'NO_MODALITY'
    elif len(mods) == 1:
        return list(mods)[0]
    else:
        return ', '.join(mods)
    

def is_bus(obj):
    # -1 = no, 0 = maybe, 1 = yes
    if obj.has_tag('bus', 'no'):
        return -1
    if obj.has_tag('bus', 'yes') or obj.has_tag('bus', 'school'):
        return 1
    if obj.has_tag('highway', 'bus_stop'):
        return 1
    if obj.has_tag('amenity', 'bus_stop'):
        return 1
    if obj.has_tag('amenity', 'bus_station'):
        return 1
    if obj.has_tag('highway', 'platform'):
        return 0  # hw=pf is for bus and tram!
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_trolleybus(obj):
    if obj.has_tag('trolleybus', 'no'):
        return -1
    if obj.has_tag('trolleybus', 'yes'):
        return 1
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_share_taxi(obj):
    if obj.has_tag('share_taxi', 'no'):
        return -1
    if obj.has_tag('shared_taxi', 'no'):
        return -1
    if obj.has_tag('share_taxi', 'yes'):
        return 1
    if obj.has_tag('shared_taxi', 'yes'):
        return 1

def is_tram(obj):
    if obj.has_tag('tram', 'no'):
        return -1
    if obj.has_tag('tram', 'yes'):
        return 1
    if obj.has_tag('station', 'tram'):
        return 1
    if obj.has_tag('railway', 'tram_stop'):
        return 0  # could also be light_rail (will be determined by rail type)
    if obj.has_tag('railway', 'station'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'halt'):
        return 0  # could by any type of railway station
    if obj.has_tag('highway', 'platform'):
        return 0  # hw=pf is for bus and tram!
    if obj.has_tag('railway', 'platform'):
        return 0
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_light_rail(obj):
    if obj.has_tag('light_rail', 'no'):
        return -1
    if obj.has_tag('light_rail', 'yes'):
        return 1
    if obj.has_tag('station', 'light_rail'):
        return 1
    if obj.has_tag('railway', 'tram_stop'):
        return 0  # could also be tram (will be determined by rail type)
    if obj.has_tag('railway', 'station'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'halt'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'platform'):
        return 0
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_train(obj):
    if obj.has_tag('train', 'no'):
        return -1
    if obj.has_tag('train', 'yes'):
        return 1
    if obj.has_tag('station', 'train'):
        return 1
    if obj.has_tag('railway', 'stop'):
        # note: even if pt=stop_position is set without train=yes, rw=stop could
        #       refer to trains as default rail modality
        return 0
    if obj.has_tag('railway', 'station'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'halt'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'platform'):
        return 0
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_monorail(obj):
    if obj.has_tag('monorail', 'no'):
        return -1
    if obj.has_tag('monorail', 'yes'):
        return 1
    if obj.has_tag('station', 'monorail'):
        return 1
    if obj.has_tag('railway', 'stop') \
    and not obj.has_tag('public_transport', 'stop_position'):
        # note: without PTv2 stopo tag rw=stop may refer to any rail modality
        return 0
    if obj.has_tag('railway', 'station'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'halt'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'platform'):
        return 0
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_subway(obj):
    if obj.has_tag('subway', 'no'):
        return -1
    if obj.has_tag('subway', 'yes'):
        return 1
    if obj.has_tag('station', 'subway'):
        return 1
    if obj.has_tag('railway', 'stop') \
    and not obj.has_tag('public_transport', 'stop_position'):
        # note: without PTv2 stopo tag rw=stop may refer to any rail modality
        return 0
    if obj.has_tag('railway', 'station'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'halt'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'platform'):
        return 0
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_funicular(obj):
    if obj.has_tag('funicular', 'no'):
        return -1
    if obj.has_tag('funicular', 'yes'):
        return 1
    if obj.has_tag('station', 'funicular'):
        return 1
    if obj.has_tag('railway', 'stop') \
    and not obj.has_tag('public_transport', 'stop_position'):
        # note: without PTv2 stopo tag rw=stop may refer to any rail modality
        return 0
    if obj.has_tag('railway', 'station'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'halt'):
        return 0  # could by any type of railway station
    if obj.has_tag('railway', 'platform'):
        return 0
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_ferry(obj):
    if obj.has_tag('ferry', 'no'):
        return -1
    if obj.has_tag('ferry', 'yes'):
        return 1
    if obj.has_tag('amenity', 'ferry_terminal'):
        return 1
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

def is_aerialway(obj):
    if obj.has_tag('aerialway', 'no'):
        return -1
    if obj.has_tag('aerialway', 'yes'):
        return 1
    if obj.has_tag('aerialway', 'station'):
        return 1
    if obj.has_tag('public_transport', 'platform'):
        return 0
    return -1

mods_props = {
    'bus': {
        'track': 'road',
        'is_func': is_bus,
        'track_tags': {
            'highway': [
                'motorway',
                'trunk',
                'primary',
                'secondary',
                'tertiary',
                'unclassified',
                'residential',
                'road',
                'busway',
                'bus_guideway',
                'service',
                'living_street',
                'construction',
                'track',
                'motorway_link',
                'trunk_link',
                'primary_link',
                'secondary_link',
                'tertiary_link'
            ],
            'psv': ['yes']
        }
    },
    'trolleybus': {
        'track': 'road',
        'is_func': is_trolleybus,
        'track_tags': {
            'highway': [
                'motorway',
                'trunk',
                'primary',
                'secondary',
                'tertiary',
                'unclassified',
                'residential',
                'road',
                'busway',
                'bus_guideway',
                'service',
                'living_street',
                'construction',
                'track',
                'motorway_link',
                'trunk_link',
                'primary_link',
                'secondary_link',
                'tertiary_link'
            ],
            'psv': ['yes']
        }
    },
    'share_taxi': {
        'track': 'road',
        'is_func': is_share_taxi,
        'track_tags': {
            'highway': [
                'motorway',
                'trunk',
                'primary',
                'secondary',
                'tertiary',
                'unclassified',
                'residential',
                'road',
                'busway',
                'bus_guideway',
                'service',
                'living_street',
                'construction',
                'track',
                'motorway_link',
                'trunk_link',
                'primary_link',
                'secondary_link',
                'tertiary_link'
            ],
            'psv': ['yes']
        }
    },
    'tram': {
        'track': 'tram',
        'is_func': is_tram,
        'track_tags': {
            'railway': ['tram'],
        }
    },
    'light_rail': {
        'track': 'light_rail',
        'is_func': is_light_rail,
        'track_tags': {
            'railway': ['light_rail'],
        }
    },
    'train': {
        'track': 'rail',
        'is_func': is_train,
        'track_tags': {
            'railway': ['miniature', 'narrow_gauge', 'rail', 'preserved']
        }
    },
    'monorail': {
        'track': 'monorail',
        'is_func': is_monorail,
        'track_tags': {
            'railway': ['monorail'],
        }
    },
    'subway': {
        'track': 'subway',
        'is_func': is_subway,
        'track_tags': {
            'railway': ['subway'],
        }
    },
    'funicular': {
        'track': 'funicular',
        'is_func': is_funicular,
        'track_tags': {
            'railway': ['funicular'],
        }
    },
    'ferry': {
        'track': 'sea',
        'is_func': is_ferry,
        'track_tags': {
            'route': ['ferry'],
        }
    },
    'aerialway': {
        'track': 'air',
        'is_func': is_aerialway,
        'track_tags': {
            'aerialway': [
                'cable_car',
                'gondola',
                'mixed_lift',
                'chair_lift',
                'drag_lift',
                't-bar',
                'j-bar',
                'platter',
                'rope_tow',
                'magic_carpet',
                'zip_line',
                'goods'
            ]
        }
    }
}
            

# function for assigning nodes to nodes or areas via neighborhood relations

def get_nearby_nodes(nodes, objects, col_prefix, radius, mods_func, score_func):

    infos_col = col_prefix + '_infos'
    ids_col = col_prefix + '_ids'
    objects[ids_col] = [[] for _ in objects.index]
    objects[infos_col] = [{} for _ in objects.index]

    # for each object get all nodes in neighborhood
    if len(objects) > 0:
        buffers = objects['geo'].buffer(radius, cap_style=3)
        result = nodes.sindex.query(buffers)
        for i_obj, i_node in zip(result[0], result[1]):
            obj_id = objects.index[i_obj]
            node_id = nodes.index[i_node]
            if buffers.loc[obj_id].contains(nodes.loc[node_id, 'geo']):
                objects.loc[obj_id, infos_col][node_id] = {}

    # for each object find all matching nearby nodes
    for obj_id in objects.index:
    
        # choose all nodes that match object's modalities
        obj_mods = objects.loc[obj_id, 'mods']
        obj_maybe_mods = objects.loc[obj_id, 'maybe_mods']
        node_ids = []  # nodes with matching mods
        for node_id, node_info in objects.loc[obj_id, infos_col].items():
            node_info['mods_match'] = mods_func(obj_mods, obj_maybe_mods, nodes.loc[node_id, :])
            if node_info['mods_match']:
                node_ids.append(node_id)
        
        # make scores
        osm_obj = objects.loc[obj_id, 'obj']
        for node_id in node_ids:
            node_info = objects.loc[obj_id, infos_col][node_id]
            node_info['ref:IFOPT_match'], node_info['ref_match'], \
            node_info['local_ref_match'], node_info['ref_name_match'], \
            node_info['name_match'], node_info['layer_match'], node_info['level_match'] \
                = score_func(osm_obj, nodes.loc[node_id, 'obj'])
            node_info['score'] = 10 * node_info['ref:IFOPT_match'] \
                                 + 2 * node_info['ref_match'] \
                                 + 2 * node_info['local_ref_match'] \
                                 + 1 * node_info['ref_name_match'] \
                                 + 1 * node_info['name_match'] \
                                 + 1 * node_info['layer_match'] \
                                 + 2 * node_info['level_match']

        # adjust scores by distance (add 0...1/2 for distance max...0)
        # note: this adjustment by distance only influences the ordering of
        #       scores for equal scores (because scores from tags differ at
        #       least by 1)
        dists = nodes.loc[node_ids, 'geo'].distance(objects.loc[obj_id, 'geo'])
        for node_id, dist in zip(node_ids, dists):
            node_info = objects.loc[obj_id, infos_col][node_id]
            node_info['score'] += (radius - dist) / (2 * radius)

        # sort nodes by score and remove nodes with negative score
        node_ids = [n_id for n_id in node_ids if objects.loc[obj_id, infos_col][n_id]['score'] > 0]
        node_ids.sort(key=lambda n_id: objects.loc[obj_id, infos_col][n_id]['score'], reverse=True)

        objects.loc[obj_id, ids_col].extend(node_ids)