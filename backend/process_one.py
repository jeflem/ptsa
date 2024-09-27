import json
import logging
import geopandas as gpd
import os
import requests
import shapely
from shapely.geometry import Point, LineString

from utils import *


def process(config):

    logger = logging.getLogger('region') 

    # -------------------------------------------------------------------------
    # get public transport related OSM objects
    
    logger.info('sending query to overpass')
    query = '''
    area({osm_id})->.roi;
    (
        nwr["highway"~"^((bus_stop|platform);?)*$"](area.roi);
        nwr["public_transport"~"^((stop_position|platform|station);?)*$"](area.roi);
        nwr["amenity"~"^((bus_stop|bus_station|ferry_terminal);?)*$"](area.roi);
        nwr["railway"~"^((platform|station|halt|stop|tram_stop);?)*$"](area.roi);
        nwr["station"~"^((subway|light_rail|train|monorail|funicular|tram);?)*$"](area.roi);
        nwr["aerialway"~"^((yes|station);?)*$"](area.roi);
        nwr["share_taxi"="yes"](area.roi);
        nwr["shared_taxi"="yes"](area.roi);
    )->.all;
    (
        nw.all["access"!="private"];
        rel.all["type"="multipolygon"];
    );
    out;

    >;
    out skel;
    '''.format(osm_id=config['osm_id'] + 3600000000)

    nodes, ways, rels = overpass(query, config)
    del query
    if len(nodes) == 0 and len(ways) == 0 and len(rels) == 0:
        logger.error('overpass did not return anything, aborting')
        return False

    # -------------------------------------------------------------------------
    # make areas from ways and multipolygons

    nodes_dict = {n.id: n for n in nodes}
    ways_dict = {w.id: w for w in ways}
    areas = [Area(w, nodes_dict=nodes_dict) for w in ways] \
            + [Area(r, nodes_dict=nodes_dict, ways_dict=ways_dict) for r in rels]
    del nodes_dict, ways_dict
    logger.info(f'areas: {len(areas)}')

    # -------------------------------------------------------------------------
    # roughly classify nodes and areas by tags

    stopos = []
    poles = []
    plafos = []
    stations = []
    dubobs = []

    for n in nodes:
        if len(n.tags) == 0:
            continue
        dubious = True
        if n.has_tag('public_transport', 'stop_position') \
        or (n.has_tag('highway', 'bus_stop')
            and not n.has_tag('public_transport', 'platform')) \
        or n.has_tag('amenity', 'bus_stop') \
        or n.has_tag('amenity', 'ferry_terminal') \
        or n.has_tag('railway', 'stop') \
        or (n.has_tag('railway', 'tram_stop') \
            and not n.has_tag('public_transport', 'platform')
            and not n.has_tag('public_transport', 'station')) \
        or n.has_tag('aerialway', 'station'):
            stopos.append(n)
            dubious = False
        if n.has_tag('public_transport', 'platform') \
        or (n.has_tag('highway', 'bus_stop')
            and not n.has_tag('public_transport', 'stop_position')) \
        or n.has_tag('amenity', 'bus_stop') \
        or n.has_tag('highway', 'platform') \
        or n.has_tag('railway', 'platform'):
            poles.append(n)
            dubious = False
        if n.has_tag('public_transport', 'station') \
        or n.has_tag('amenity', 'bus_station') \
        or n.has_tag('railway', 'station') \
        or n.has_tag('railway', 'halt'):
            stations.append(n)
            dubious = False
        if dubious:
            n.warning('node somehow related to public transport, but how?')
            dubobs.append(n)

    for a in areas:
        if len(a.tags) == 0:
            continue
        dubious = True
        if a.has_tag('public_transport', 'platform') \
        or a.has_tag('highway', 'bus_stop') \
        or a.has_tag('highway', 'platform') \
        or a.has_tag('amenity', 'bus_stop') \
        or a.has_tag('railway', 'platform') \
        or a.has_tag('amenity', 'ferry_terminal'):
            plafos.append(a)
            dubious = False
        if a.has_tag('public_transport', 'station') \
        or a.has_tag('amenity', 'bus_station') \
        or a.has_tag('railway', 'station') \
        or a.has_tag('railway', 'halt') \
        or a.has_tag('aerialway', 'station'):
            stations.append(a)
            dubious = False
        if dubious:
            a.warning('area somehow related to public transport, but how?')
            dubobs.append(a)

    del dubious, nodes
    logger.info(f'stop positions: {len(stopos)}')
    logger.info(f'poles: {len(poles)}')
    logger.info(f'platforms: {len(plafos)}')
    logger.info(f'stations: {len(stations)}')
    logger.info(f'dubious objects: {len(dubobs)}')

    # -------------------------------------------------------------------------
    # make data frames for stopos, poles, plafos

    stopos = gpd.GeoDataFrame(
        data = [[n.id, Point(n.lon, n.lat), n] for n in stopos],
        columns = ('id', 'geo', 'obj'),
        crs = config['lon_lat_crs'],
        geometry = 'geo'
    ).set_index('id').to_crs(config['meters_crs'])

    poles = gpd.GeoDataFrame(
        data = [[n.id, Point(n.lon, n.lat), n] for n in poles],
        columns = ('id', 'geo', 'obj'),
        crs = config['lon_lat_crs'],
        geometry = 'geo'
    ).set_index('id').to_crs(config['meters_crs'])

    plafos = gpd.GeoDataFrame(
        # note: shapely.unary_union is optional
        #       (joins adjacent polygons to one polygon)
        data = [[
            a.id,
            a.geometry if a.from_line \
                else shapely.unary_union(shapely.polygonize(a.geometry)),
            a
        ] for a in plafos],
        columns = ('id', 'geo', 'obj'),
        crs = config['lon_lat_crs'],
        geometry = 'geo'
    ).set_index('id').to_crs(config['meters_crs'])

    # replace lines by polygons
    mask = plafos['obj'].apply(lambda obj: obj.from_line)
    plafos.loc[mask, 'geo'] \
        = plafos.loc[mask, 'geo'] \
        .buffer(config['half_plafo_width'], cap_style=2)
    del mask

    logger.info(f'stop positions: {len(stopos)}')
    logger.info(f'poles: {len(poles)}')
    logger.info(f'platforms: {len(plafos)}')



    # -------------------------------------------------------------------------
    # check for empty geometries
    
    to_drop = []
    for plafo_id in plafos.index:
        if plafos.loc[plafo_id, 'geo'].is_empty:
            to_drop.append(plafo_id)
    if len(to_drop) > 0:
        logger.warning(f'Dropping plafos with empty geometry: {str(to_drop)}')
        plafos = plafos.drop(index=to_drop)

    # -------------------------------------------------------------------------
    # make data frame for stations

    geos = []
    for station in stations:
        if station.type == 'node':
            geos.append(Point(station.lon, station.lat))
        else:
            if station.from_line:
                geos.append(station.geometry)
            else:
                # note: shapely.unary_union is optional
                #       (joins adjacent polygons to one polygon)
                geos.append(shapely.unary_union(shapely.polygonize(station.geometry)))

    stations = gpd.GeoDataFrame(
        data = [[geo, obj] for geo, obj in zip(geos, stations)],
        columns = ('geo', 'obj'),
        crs = config['lon_lat_crs'],
        geometry = 'geo'
    ).to_crs(config['meters_crs'])
    stations.index.name = 'id'
    del geos

    # make areas from nodes and lines
    mask = stations['obj'].apply(lambda obj: obj.type == 'node')
    stations.loc[mask, 'geo'] = stations.loc[mask, 'geo'].buffer(config['station_radius'], cap_style=1, resolution=4)
    mask = stations['obj'].apply(lambda obj: obj.type != 'node' and obj.from_line)
    stations.loc[mask, 'geo'] \
        = stations.loc[mask, 'geo'] \
        .buffer(config['station_radius'], cap_style=1, resolution=4)
    del mask


    # -------------------------------------------------------------------------
    # add modalities
    for df in [stopos, poles, plafos, stations]:
        df['tag_mods'] = [set() for _ in df.index]
        df['tag_maybe_mods'] = [set() for _ in df.index]
        for mod, mod_props in mods_props.items():
            is_mod = df['obj'].apply(mod_props['is_func'])
            df.loc[is_mod == 1, 'tag_mods'].apply(add_mods, args=({mod}, ))
            df.loc[is_mod == 0, 'tag_maybe_mods'].apply(add_mods, args=({mod}, ))   
            
    
    #-------------------------------------------------------------------------
    # get track types for stopos and poles

    track_keys = {key for mod_props in mods_props.values()
                    for key in mod_props['track_tags']}
    for df in [stopos, poles]:

        # fetch all ways
        query = '''
        node(id: {node_ids});
        way(bn)->.all;
        ({way_filters});
        out;
        '''.format(
            node_ids=','.join([str(id_) for id_ in df.index]),
            way_filters='\n'.join([f'way.all[{key}];' for key in track_keys])
        )
        _, ways, _ = overpass(query, config)

        # assign modalities to ways
        ways_mods = [set() for _ in range(len(ways))]
        for mod, mod_props in mods_props.items():
            for w, w_mods in zip(ways, ways_mods):
                # note: We have to test for multi-modality tracks via modality flag
                #       tags. But for ways with highway=platform (and some other)
                #       flags might be set although it's not a way for such
                #       vehicles. Thus, we avoid flag tag checking in such cases.
                if w.has_tag(mod, 'yes') \
                and not w.has_tag('highway', 'platform') \
                and not w.has_tag('railway', 'platform') \
                and not w.has_tag('public_transport', 'platform'):
                    w_mods.add(mod)
                    continue
                if w.has_tag(mod, 'no'):
                    continue
                for key, values in mod_props['track_tags'].items():
                    if any([w.has_tag(key, value) for value in values]):
                        w_mods.add(mod)
                        break
                    if w.has_tag(key, 'construction') \
                    and any([w.has_tag('construction', value) for value in values]):
                        w_mods.add(mod)
                        break
            
        # assign ways to nodes
        df['track_mods'] = [set() for _ in df.index]
        for w, w_mods in zip(ways, ways_mods):
            for n_id in df.index.intersection(w.node_ids):
                df.loc[n_id, 'track_mods'].update(w_mods)
                if w.tags.get('layer'):
                    if 'layer' not in df.loc[n_id, 'obj'].tags:
                        df.loc[n_id, 'obj'].tags['layer'] = w.tags.get('layer')
                    else: # belongs to multiple layers
                        df.loc[n_id, 'obj'].multiple_values = True
                        df.loc[n_id, 'obj'].tags['layer'] += ';' + w.tags.get('layer')
                if w.tags.get('level'):
                    if 'level' not in df.loc[n_id, 'obj'].tags:
                        df.loc[n_id, 'obj'].tags['level'] = w.tags.get('level')
                    else: # belongs to multiple levels
                        df.loc[n_id, 'obj'].multiple_values = True
                        df.loc[n_id, 'obj'].tags['level'] += ';' + w.tags.get('level')

    del ways, ways_mods

    # -------------------------------------------------------------------------
    # remove modalities from stopos if not on corresponding track

    pole_ids = []  # dropped stopos that are in poles data frame
    to_dubobs_ids = []  # dropped stopos that are not in poles data frame

    stopos['mods'] = [set() for _ in stopos.index]

    for id_ in stopos.index:
        tag_mods = stopos.loc[id_, 'tag_mods']
        tag_maybe_mods = stopos.loc[id_, 'tag_maybe_mods']
        track_mods = stopos.loc[id_, 'track_mods']
        mods = stopos.loc[id_, 'mods']
        obj = stopos.loc[id_, 'obj']
        if track_mods == set():
            if id_ in poles.index:
                obj.comment(f'looking at tags only, node could be a stop position for {mods2str(tag_mods | tag_maybe_mods)}, but is not on suitable track')
                pole_ids.append(id_)
            elif tag_mods == set():
                if tag_maybe_mods == set():
                    obj.warning(f'node tagged as stop position but neither has modality tags nor is on any relevant track')
                    to_dubobs_ids.append(id_)
                else:
                    obj.warning(f'node tagged as stop position with ambiguous modalities {mods2str(tag_maybe_mods)}, but node is not on any relevant track')
                    to_dubobs_ids.append(id_)
            else:  # there are modality tags
                obj.warning(f'node is tagged as stop position for {mods2str(tag_mods)}, but is not on any relevant track')
                to_dubobs_ids.append(id_)
        else:  # node is on some track
            all_tag_mods = tag_mods | tag_maybe_mods
            if all_tag_mods == set():
                mods.update(track_mods - {'trolleybus', 'share_taxi'})
                obj.warning(f'stop position without modality tags, assuming {mods2str(mods)} because node is on suitable track')
            else:  # there are tagged mods
                mods.update(all_tag_mods & track_mods)
                if mods == set():
                    obj.warning(f'stop position for which tagged modalities {mods2str(all_tag_mods)} do not match track modalities {mods2str(track_mods)}')
                    to_dubobs_ids.append(id_)

    # remove invalid stopos
    dubobs.extend(stopos.loc[to_dubobs_ids, 'obj'].to_list())
    stopos = stopos.drop(index=to_dubobs_ids + pole_ids)
    logger.info(f'moved {len(to_dubobs_ids)} invalid stopos to dubobs, removed {len(pole_ids)} invalid stopos that are poles')

    stopos = stopos.drop(columns=['tag_mods', 'tag_maybe_mods', 'track_mods'])
    
    # -------------------------------------------------------------------------
    # remove modalities from poles if on corresponding track

    to_dubobs_ids = []  # dropped poles

    stopo_ids = []  # dropped poles that are in stopos data frame
    poles['mods'] = [set() for _ in poles.index]
    poles['maybe_mods'] = [set() for _ in poles.index]

    for id_ in poles.index:
        tag_mods = poles.loc[id_, 'tag_mods']
        tag_maybe_mods = poles.loc[id_, 'tag_maybe_mods']
        track_mods = poles.loc[id_, 'track_mods']
        mods = poles.loc[id_, 'mods']
        maybe_mods = poles.loc[id_, 'maybe_mods']
        obj = poles.loc[id_, 'obj']

        mods.update(tag_mods)
        on_track_mods = tag_mods & track_mods
        if len(on_track_mods) > 0:
            obj.comment(f'from tags only node looks like a pole for {mods2str(on_track_mods)}, but node is on track, not beside')
            mods.difference_update(on_track_mods)
            
        maybe_mods.update(tag_maybe_mods)
        on_track_mods = tag_maybe_mods & track_mods
        if len(on_track_mods) > 0:
            obj.comment(f'from tags only node could be a pole for {mods2str(on_track_mods)}, but node is on track, not beside')
            maybe_mods.difference_update(on_track_mods)

        if len(mods) == 0 and len(maybe_mods) == 0:
            if id_ in stopos.index:
                stopo_ids.append(id_)
            else:
                obj.warning('pole without modalities')
                to_dubobs_ids.append(id_)
        elif len(mods) == 0:
            obj.comment('pole with ambiguous modality tags')

    # remove invalid poles
    dubobs.extend(poles.loc[to_dubobs_ids, 'obj'].to_list())
    poles = poles.drop(index=to_dubobs_ids + stopo_ids)
    logger.info(f'moved {len(to_dubobs_ids)} invalid poles to dubobs, removed {len(stopo_ids)} invalid poles that are stopos')

    # remove poles that also are stop positions
    pole_ids = stopos.index.intersection(poles.index)
    poles = poles.drop(index=pole_ids)
    for id_ in pole_ids:
        stopos.loc[id_, 'obj'].warning('stop position with pole-like tags')
    logger.info(f'removed {len(pole_ids)} poles that also are stop positions')

    del pole_ids
    poles = poles.drop(columns=['tag_mods', 'tag_maybe_mods', 'track_mods'])

    # -------------------------------------------------------------------------
    # log dubious objects
    
    logger.info(f'dubious objects: {len(dubobs)}')
    for obj in dubobs:
        logger.info(f'{obj} {obj.comments} {obj.warnings}')

    # -------------------------------------------------------------------------
    # Rename mod columns in plafos df and stations df (tags are the only source for mods here)

    plafos = plafos.rename(columns={ 'tag_mods': 'mods', 'tag_maybe_mods': 'maybe_mods' })
    stations = stations.rename(columns={ 'tag_mods': 'mods', 'tag_maybe_mods': 'maybe_mods' })

    logger.info(f'stop positions: {len(stopos)}')
    logger.info(f'poles: {len(poles)}')
    logger.info(f'platforms: {len(plafos)}')

    # -------------------------------------------------------------------------
    # assign stopos to poles/plafos (=ploles)

    def mods_stopos_to_ploles(plole_mods, plole_maybe_mods, stopo):
        stopo_mods = stopo['mods']
        if (plole_mods | plole_maybe_mods) & stopo_mods != set():
            return True
        else:
            return False
        
    def score_stopos_to_ploles(plole, stopo):
        matches = []
        keys = plole.tags.keys() & stopo.tags.keys()
        if 'ref:IFOPT' in keys:
            if stopo.tags['ref:IFOPT'] in plole.tags['ref:IFOPT'] \
            or plole.tags['ref:IFOPT'] in stopo.tags['ref:IFOPT']:
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'ref' in keys:
            if stopo.has_tag('ref', plole.tags['ref']) \
            or plole.has_tag('ref', stopo.tags['ref']):
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'local_ref' in keys:
            if stopo.has_tag('local_ref', plole.tags['local_ref']) \
            or plole.has_tag('local_ref', stopo.tags['local_ref']):
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'ref_name' in keys:
            if stopo.tags['ref_name'] in plole.tags['ref_name'] \
            or plole.tags['ref_name'] in stopo.tags['ref_name']:
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'name' in keys:
            if stopo.tags['name'] in plole.tags['name'] \
            or plole.tags['name'] in stopo.tags['name']:
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        layers = set(stopo.tags.get('layer', '0').split(';')) & set(plole.tags.get('layer', '0').split(';'))
        if 'layer' in keys:
            if layers == set():
                matches.append(0) # both have layer tag (then != 0), but layers differ
            else:
                matches.append(1) # both have layer tag (then != 0), common layer
        else:
            if layers == set():
                matches.append(-1) # only one has layer tag
            else:
                matches.append(0) # both without layer tag (only 0 in intersection)
        levels = set(stopo.tags.get('level', '0').split(';')) & set(plole.tags.get('level', '0').split(';'))
        if levels != set():
            if '0' in levels:
                matches.append(0)
            else:
                matches.append(1)
        else:
            matches.append(-1)
        return matches

    get_nearby_nodes(stopos, poles, 'stopo', config['pole_stopo_dist'],
                    mods_stopos_to_ploles, score_stopos_to_ploles)

    get_nearby_nodes(stopos, plafos, 'stopo', config['plafo_stopo_dist'],
                    mods_stopos_to_ploles, score_stopos_to_ploles)

    # -------------------------------------------------------------------------
    # assign poles to plafos

    def mods_poles_to_plafos(plafo_mods, plafo_maybe_mods, pole):
        pole_mods = pole['mods']
        pole_maybe_mods = pole['maybe_mods']
        plafo_all_mods = plafo_mods | plafo_maybe_mods
        if (pole_mods != set() and pole_mods <= plafo_all_mods) \
        or (pole_mods == set() and pole_maybe_mods & plafo_all_mods != set()):
            return True
        else:
            return False

    def score_poles_to_plafos(plafo, pole):
        matches = []
        keys = plafo.tags.keys() & pole.tags.keys()
        if 'ref:IFOPT' in keys:
            # note: pole IFOPT may be longer than plafo IFOPT if plafo is used for
            #       multiple poles
            if plafo.tags['ref:IFOPT'] in pole.tags['ref:IFOPT']:
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'ref' in keys:
            # note: plafo may have multiple ref values if plafo is used for
            #       multiple poles
            if plafo.has_tag('ref', pole.tags['ref']):
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'local_ref' in keys:
            if plafo.has_tag('local_ref', pole.tags['local_ref']):
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'ref_name' in keys:
            if plafo.tags['ref_name'] in pole.tags['ref_name']:
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        if 'name' in keys:
            if plafo.tags['name'] in pole.tags['name']:
                matches.append(1)
            else:
                matches.append(-1)
        else:
            matches.append(0)
        layers = set(plafo.tags.get('layer', '0').split(';')) & set(pole.tags.get('layer', '0').split(';'))
        if 'layer' in keys:
            if layers == set():
                matches.append(0) # both have layer tag (then != 0), but layers differ
            else:
                matches.append(1) # both have layer tag (then != 0), common layer
        else:
            if layers == set():
                matches.append(-1) # only one has layer tag
            else:
                matches.append(0) # both without layer tag (only 0 in intersection)
        levels = set(plafo.tags.get('level', '0').split(';')) & set(pole.tags.get('level', '0').split(';'))
        if levels != set():
            if '0' in levels:
                matches.append(0)
            else:
                matches.append(1)
        else:
            matches.append(-1)
        return matches

    get_nearby_nodes(poles, plafos, 'pole', config['plafo_pole_dist'],
                    mods_poles_to_plafos, score_poles_to_plafos)    
    
    # -------------------------------------------------------------------------
    # make ploles

    poles['has_plafo'] = False  # True, if pole is in plole with plafo
    plafos['has_poles'] = False  # True, if plafo is in plole with pole

    ploles = {'plafo_id': [], 'pole_id': [], 'mods': [], 'maybe_mods': [],
            'stopo_ids': [], 'stopo_infos': []}

    # ploles for plafo-pole combinations
    for plafo_id in plafos.index:
        plafo = plafos.loc[plafo_id, :]
        weight = 1 if len(plafo['pole_ids']) == 1 else 0.5  # for averaging scores
        for pole_id in plafo['pole_ids']:
            pole = poles.loc[pole_id, :]
            if pole['has_plafo']:
                pole['obj'].warning(f'Pole is already assigned to a platform. Cannot assign pole to platform {plafo_id}.')
                continue

            # combine mods
            mods = (plafo['mods'] & (pole['mods'] | pole['maybe_mods'])) \
                | (pole['mods'] & (plafo['mods'] | plafo['maybe_mods']))
            maybe_mods = plafo['maybe_mods'] & pole['maybe_mods']

            # intersect stopo sets and average stopo scores
            stopo_ids = []
            stopo_infos = {}
            for id_ in set(plafo['stopo_ids']) & set(pole['stopo_ids']):
                stopo_ids.append(id_)
                score = weight * plafo['stopo_infos'][id_]['score'] \
                        + (1 - weight) * pole['stopo_infos'][id_]['score']
                stopo_infos[id_] = {'score': score, 'mods_match': True}

            # sort stopos by score
            stopo_ids.sort(key=lambda id_: stopo_infos[id_]['score'], reverse=True)

            # create plole
            poles.loc[pole_id, 'has_plafo'] = True
            plafos.loc[plafo_id, 'has_poles'] = True
            ploles['plafo_id'].append(plafo_id)
            ploles['pole_id'].append(pole_id)
            ploles['mods'].append(mods)
            ploles['maybe_mods'].append(maybe_mods)
            ploles['stopo_ids'].append(stopo_ids)
            ploles['stopo_infos'].append(stopo_infos)

    # make ploles data frame including pole-only and plafo-only ploles
    cols = ['mods', 'maybe_mods', 'stopo_ids', 'stopo_infos']
    pole_ploles = poles.loc[~poles['has_plafo'], cols]
    pole_ploles = pole_ploles.reset_index(names='pole_id')
    pole_ploles['plafo_id'] = 0
    plafo_ploles = plafos.loc[~plafos['has_poles'], cols]
    plafo_ploles = plafo_ploles.reset_index(names='plafo_id')
    plafo_ploles['pole_id'] = 0
    # if ploles dict is empty, then ploles data frame will have float as default
    # dtype (data frame created from empty lists) resulting in float pole and
    # platform IDs; avoid creating empty data frames
    if len(ploles['pole_id']) > 0:
        dfs = (gpd.pd.DataFrame(ploles), pole_ploles, plafo_ploles)
    else:
        dfs = (pole_ploles, plafo_ploles)
    ploles = gpd.pd.concat(dfs, ignore_index=True)

    # -------------------------------------------------------------------------
    # make stops

    stopos['in_stop'] = False

    stops = {'plole_id': [], 'plafo_id': [], 'pole_id': [], 'stopo_id': [], 'stopo_reason': []}

    len_stopo_ids = ploles['stopo_ids'].apply(len)

    # ploles without stopo
    for plole_id in ploles.index[len_stopo_ids == 0]:
        stops['plole_id'].append(plole_id)
        stops['plafo_id'].append(ploles.loc[plole_id, 'plafo_id'])
        stops['pole_id'].append(ploles.loc[plole_id, 'pole_id'])
        stops['stopo_id'].append(0)
        stops['stopo_reason'].append('')

    # add one stopo to each plole
    for plole_id in ploles.index[len_stopo_ids > 0]:
        stopo_id = ploles.loc[plole_id, 'stopo_ids'][0]
        stopos.loc[stopo_id, 'in_stop'] = True
        ploles.loc[plole_id, 'stopo_infos'][stopo_id]['stop_id'] = len(stops['plole_id'])
        stops['plole_id'].append(plole_id)
        stops['plafo_id'].append(ploles.loc[plole_id, 'plafo_id'])
        stops['pole_id'].append(ploles.loc[plole_id, 'pole_id'])
        stops['stopo_id'].append(stopo_id)
        stops['stopo_reason'].append('best match by score (and modalities match)')

    # add further stopos to ploles if stopos have new relevant mods or are unused
    pp_stopos = {}  # postponed stopos
    for plole_id in ploles.index[len_stopo_ids > 1]:
        mods = stopos.loc[ploles.loc[plole_id, 'stopo_ids'][0], 'mods'].copy()
        for stopo_id in ploles.loc[plole_id, 'stopo_ids'][1:]:
            score = ploles.loc[plole_id, 'stopo_infos'][stopo_id]['score']
            if (stopos.loc[stopo_id, 'mods'] & mods == set() \
            and stopos.loc[stopo_id, 'mods'] & ploles.loc[plole_id, 'mods'] != set()):
                mods.update(stopos.loc[stopo_id, 'mods'])
                stopos.loc[stopo_id, 'in_stop'] = True
                ploles.loc[plole_id, 'stopo_infos'][stopo_id]['stop_id'] = len(stops['plole_id'])
                stops['plole_id'].append(plole_id)
                stops['plafo_id'].append(ploles.loc[plole_id, 'plafo_id'])
                stops['pole_id'].append(ploles.loc[plole_id, 'pole_id'])
                stops['stopo_id'].append(stopo_id)
                stops['stopo_reason'].append('adds relevant modality to plole')
            elif not stopos.loc[stopo_id, 'in_stop']:
                # unused stopo with same mods like some other stopo already assigned
                # to current plole; if score is better than for other matching
                # plole, remember stopo-plole combination for processing after all
                # stopos relevant for plole mods have been processed
                if stopo_id not in pp_stopos or score > pp_stopos[stopo_id][1]:
                    pp_stopos[stopo_id] = (plole_id, score)
    for stopo_id, (plole_id, score) in pp_stopos.items():            
        if stopos.loc[stopo_id, 'in_stop']:
            continue
        stopos.loc[stopo_id, 'in_stop'] = True
        ploles.loc[plole_id, 'stopo_infos'][stopo_id]['stop_id'] = len(stops['plole_id'])
        stops['plole_id'].append(plole_id)
        stops['plafo_id'].append(ploles.loc[plole_id, 'plafo_id'])
        stops['pole_id'].append(ploles.loc[plole_id, 'pole_id'])
        stops['stopo_id'].append(stopo_id)
        stops['stopo_reason'].append('third choice for all nearby ploles; best score with this plole')

    # stopos without plole
    for stopo_id in stopos.index[~stopos['in_stop']]:
        stops['plole_id'].append(-1)
        stops['plafo_id'].append(0)
        stops['pole_id'].append(0)
        stops['stopo_id'].append(stopo_id)
        stops['stopo_reason'].append('')

    stopos = stopos.drop(columns=['in_stop'])    

    # -------------------------------------------------------------------------
    # make data frame from stops dict

    stops['geo'] = len(stops['plafo_id']) * [Point()]

    stops = gpd.GeoDataFrame(
        data = stops,
        crs = config['meters_crs'],
        geometry = 'geo'
    )

    stops['warnings'] = [[] for _ in stops.index]

    # -------------------------------------------------------------------------
    # make virtual poles

    # plafos with stopo
    mask = (stops['plafo_id'] != 0) & (stops['pole_id'] == 0) & (stops['stopo_id'] != 0)
    vpoles = {'id': [], 'geo': []}
    for stop_id in stops.index[mask]:
        vpoles['id'].append(-stop_id)
        point, _ = shapely.ops.nearest_points(
            plafos.loc[stops.loc[stop_id, 'plafo_id'], 'geo'],
            stopos.loc[stops.loc[stop_id, 'stopo_id'], 'geo']
        )
        vpoles['geo'].append(point)
    if vpoles['id'] != []:
        stops.loc[mask, 'pole_id'] = vpoles['id']

    # plafos without stopo
    mask = (stops['pole_id'] == 0) & (stops['stopo_id'] == 0)
    new_vpole_ids = -stops.index[mask]
    if len(new_vpole_ids) > 0:
        vpoles['id'].extend(new_vpole_ids)
        stops.loc[mask, 'pole_id'] = new_vpole_ids
        vpoles['geo'].extend(plafos.loc[stops.loc[mask, 'plafo_id'], 'geo'].centroid)

    # stopos without plafo/pole
    mask = (stops['plafo_id'] == 0) & (stops['pole_id'] == 0)
    new_vpole_ids = -stops.index[mask]
    if len(new_vpole_ids) > 0:
        vpoles['id'].extend(new_vpole_ids)
        stops.loc[mask, 'pole_id'] = new_vpole_ids
        vpoles['geo'].extend(stopos.loc[stops.loc[mask, 'stopo_id'], 'geo'])

    # append vpoles to poles data frame
    vpoles = gpd.GeoDataFrame(data=vpoles, geometry='geo', crs=config['meters_crs']).set_index('id')
    vpoles['in_stop'] = True
    poles = gpd.pd.concat((poles, vpoles))

    # -------------------------------------------------------------------------
    # make stop geometries (outline)

    plafo_geos_web = plafos['geo'].to_crs(config['web_crs'])
    pole_geos_web = poles['geo'].to_crs(config['web_crs'])
    stopo_geos_web = stopos['geo'].to_crs(config['web_crs'])
    stop_geos_web = gpd.GeoSeries(
        index = stops.index,
        data = len(stops) * [Point()],
        crs = config['web_crs']
    )
        
    for stop_id in stops.index:
        plafo_id = stops.loc[stop_id, 'plafo_id']
        pole_id = stops.loc[stop_id, 'pole_id']
        stopo_id = stops.loc[stop_id, 'stopo_id']
        if plafo_id != 0:
            plafo_geo = plafo_geos_web.loc[plafo_id]
        else:
            plafo_geo = Point()
        if pole_id != 0:
            pole_geo = pole_geos_web.loc[pole_id]
        else:
            pole_geo = Point()
        if stopo_id != 0:
            stopo_geo = stopo_geos_web.loc[stopo_id]
        else:
            stopo_geo = Point()
        plafo_buffer = plafo_geo.buffer(config['stop_buffer_size'], cap_style=1, resolution=4)
        nodes_buffer = shapely.unary_union([pole_geo, stopo_geo]).convex_hull.buffer(config['stop_buffer_size'], cap_style=1, resolution=4)
        stop_geos_web.loc[stop_id] = shapely.unary_union([plafo_buffer, nodes_buffer])
        
    stops['geo'] = stop_geos_web.to_crs(config['meters_crs'])

    # -------------------------------------------------------------------------
    # get stop mods

    stops['mods'] = [set() for _ in stops.index]
    stops['maybe_mods'] = [set() for _ in stops.index]

    for i in stops.index:
        plole_id = stops.loc[i, 'plole_id']
        stopo_id = stops.loc[i, 'stopo_id']
        plole_mods = ploles.loc[plole_id, 'mods'] if plole_id > -1 else set()
        plole_maybe_mods = ploles.loc[plole_id, 'maybe_mods'] if plole_id > -1 else set()
        stopo_mods = stopos.loc[stopo_id, 'mods'] if stopo_id > 0 else set()
        mods = stops.loc[i, 'mods']
        maybe_mods = stops.loc[i, 'maybe_mods']
        
        if plole_id == -1:
            mods.update(stopo_mods)
        elif stopo_id == 0:
            if plole_mods != set():
                mods.update(plole_mods)
                maybe_mods.update(plole_maybe_mods)
            elif len(plole_maybe_mods) == 1:
                mods.update(plole_maybe_mods)
            else:
                maybe_mods.update(plole_maybe_mods)
        else:
            if plole_mods & stopo_mods != set():
                mods.update(plole_mods & stopo_mods)
                maybe_mods.update(plole_maybe_mods & stopo_mods)
            elif len(plole_maybe_mods & stopo_mods) == 1 \
            or (stops['stopo_id'] == stopo_id).sum() == 1:
                mods.update(plole_maybe_mods & stopo_mods)
            else:
                maybe_mods.update(plole_maybe_mods & stopo_mods)
                
    # -------------------------------------------------------------------------
    # warnings about stops with no mods (maybe_mods only)

    for i in stops.index[(stops['mods'] == set())]:
        stop = stops.loc[i, :]
        if stop['pole_id'] == 0 and stop['stopo_id'] == 0:
            # platform-only stop
            stop['warnings'].append(f'platform-only stop with ambiguous modalities {mods2str(stop['maybe_mods'])} (add a stop position to clarify modalities)')
        elif stop['pole_id'] > 0:
            # most likely it's a bus pole on a road
            pole = poles.loc[stop['pole_id'], :]
            if pole['obj'].has_tag('public_transport', 'platform') \
            and pole['obj'].has_tag('highway', 'bus_stop') \
            and 'bus' not in pole['mods'] \
            and not pole['obj'].has_tag('bus', 'no'):
                stop['warnings'].append(f'stop has a bus pole on a road (probably supposed to be a stop position)')
            elif stop['stopo_id'] == 0:
                stop['warnings'].append(f'stop with ambiguous modalities {mods2str(stop['maybe_mods'])} (add a stop position to clarify modalities)')
            else:
                stop['warnings'].append(f'stop with ambiguous modalities {mods2str(stop['maybe_mods'])} (check carefully, really really weird)')
        else:
            stop['warnings'].append(f'stop with ambiguous modalities {mods2str(stop['maybe_mods'])} (check carefully, really weird)')

    # -------------------------------------------------------------------------
    # add info about comments/warnings for plafo/pole/stop to stop

    def has_comments(obj):
        if type(obj) != float:
            return not obj.comments == []
        else:
            return False

    def has_warnings(obj):
        if type(obj) != float:
            return not obj.warnings == []
        else:
            return False

    for stop_id in stops.index:
        plafo_id = stops.loc[stop_id, 'plafo_id']
        pole_id = stops.loc[stop_id, 'pole_id']
        stopo_id = stops.loc[stop_id, 'stopo_id']
        stops.loc[stop_id, 'member_comments'] = False
        stops.loc[stop_id, 'member_warnings'] = False
        if plafo_id != 0:
            stops.loc[stop_id, 'member_comments'] = stops.loc[stop_id, 'member_comments'] or plafos.loc[plafo_id, 'obj'].comments != []
            stops.loc[stop_id, 'member_warnings'] = stops.loc[stop_id, 'member_warnings'] or plafos.loc[plafo_id, 'obj'].warnings != []
        if pole_id > 0:
            stops.loc[stop_id, 'member_comments'] = stops.loc[stop_id, 'member_comments'] or poles.loc[pole_id, 'obj'].comments != []
            stops.loc[stop_id, 'member_warnings'] = stops.loc[stop_id, 'member_warnings'] or poles.loc[pole_id, 'obj'].warnings != []
        if stopo_id > 0:
            stops.loc[stop_id, 'member_comments'] = stops.loc[stop_id, 'member_comments'] or stopos.loc[stopo_id, 'obj'].comments != []
            stops.loc[stop_id, 'member_warnings'] = stops.loc[stop_id, 'member_warnings'] or stopos.loc[stopo_id, 'obj'].warnings != []
            
    # -------------------------------------------------------------------------
    # bus stop rendering quality
    # 0 = no info (no bus stop)
    # 1 = invisible
    # 2 = incorrect (multiple symbols, symbol at wrong location)
    # 3 = good
    # 4 = plafo without bus symbol in bus station

    stops['render'] = 0

    for stop_id in stops.index:
        if not 'bus' in stops.loc[stop_id, 'mods']:
            continue
        stopo_id = stops.loc[stop_id, 'stopo_id']
        pole_id = stops.loc[stop_id, 'pole_id']
        plafo_id = stops.loc[stop_id, 'plafo_id']
        stopo_symbol = stopo_id > 0 \
                    and stopos.loc[stopo_id, 'obj'].has_tag('highway', 'bus_stop')
        pole_symbol = pole_id > 0 \
                    and poles.loc[pole_id, 'obj'].has_tag('highway', 'bus_stop')
        plafo_symbol = plafo_id != 0 \
                    and plafos.loc[plafo_id, 'obj'].has_tag('highway', 'bus_stop') \
                    and (plafos.loc[plafo_id, 'obj'].has_tag('area', 'yes') \
                            or 'building' in plafos.loc[plafo_id, 'obj'].tags)
        plafo_visible = plafo_id != 0 \
                        and (plafos.loc[plafo_id, 'obj'].has_tag('highway', 'platform') \
                            or plafos.loc[plafo_id, 'obj'].has_tag('railway', 'platform') \
                            or (plafos.loc[plafo_id, 'obj'].has_tag('highway', 'bus_stop')
                                and (plafos.loc[plafo_id, 'obj'].has_tag('area', 'yes') \
                                    or 'building' in plafos.loc[plafo_id, 'obj'].tags)))

        sum_symbol = [stopo_symbol, pole_symbol, plafo_symbol].count(True)
        if sum_symbol == 0:
            render = 1
        elif sum_symbol > 1:
            render = 2
        else:  # exactly one bus symbol
            if not plafo_visible and pole_id > 0 and not pole_symbol:
                render = 2
            elif not plafo_visible and pole_id <= 0:
                render = 2
            else:
                render = 3

        stops.loc[stop_id, 'render'] = render

    # -------------------------------------------------------------------------
    # set rendering quality for invisible bus stops in bus stations

    mask = stations['mods'].apply(lambda mods: 'bus' in mods)

    for stop_id in stops.index:
        if stops.loc[stop_id, 'render'] != 1 or 'bus' not in stops.loc[stop_id, 'mods']:
            continue
        plafo_id = stops.loc[stop_id, 'plafo_id']
        pole_id = stops.loc[stop_id, 'pole_id']
        stopo_id = stops.loc[stop_id, 'stopo_id']
        if (plafo_id != 0 and stations.loc[mask,'geo'].intersects(plafos.loc[plafo_id, 'geo']).any()) \
        or (pole_id > 0 and stations.loc[mask,'geo'].contains(poles.loc[pole_id, 'geo']).any()) \
        or (stopo_id > 0 and stations.loc[mask,'geo'].contains(stopos.loc[stopo_id, 'geo']).any()):
            stops.loc[stop_id, 'render'] = 4
            continue

    del mask

    # -------------------------------------------------------------------------
    # new PTv2 tagging
    # 0 = no info (shouldn't happen)
    # 1 = no new PTv2 tags
    # 2 = some stop components use new tags, some do not
    # 3 = all components have new tags

    stops['ptv2'] = 0

    for stop_id in stops.index:
        stopo_id = stops.loc[stop_id, 'stopo_id']
        pole_id = stops.loc[stop_id, 'pole_id']
        plafo_id = stops.loc[stop_id, 'plafo_id']
        stopo_pt = stopo_id > 0 \
                and 'public_transport' in stopos.loc[stopo_id, 'obj'].tags
        pole_pt = pole_id > 0 \
                and 'public_transport' in poles.loc[pole_id, 'obj'].tags
        plafo_pt = plafo_id != 0 \
                and 'public_transport' in plafos.loc[plafo_id, 'obj'].tags

        sum_pt = [stopo_pt, pole_pt, plafo_pt].count(True)
        sum_obj = [stopo_id > 0, pole_id > 0, plafo_id != 0].count(True)
        if sum_pt == 0:
            ptv2 = 1
        elif sum_pt == sum_obj:
            ptv2 = 3
        else:
            ptv2 = 2

        stops.loc[stop_id, 'ptv2'] = ptv2
    
    # -------------------------------------------------------------------------
    # dubobs data frame

    dubobs_dict = {'osm_type': [], 'osm_id': [], 'obj': [], 'geo': []}

    for obj in dubobs:
        dubobs_dict['osm_type'].append(obj.type)
        dubobs_dict['osm_id'].append(obj.id)
        dubobs_dict['obj'].append(obj)
        if obj.type == 'node':
            geo = Point(obj.lon, obj.lat)
        elif obj.type in ['way_area', 'mupo_area']:
            geo = obj.geometry if obj.from_line \
                else shapely.unary_union(shapely.polygonize(obj.geometry))
        else:
            logger.error(f'ERROR: unhandled object type {obj.type}')
            geo = Point()
        dubobs_dict['geo'].append(geo)

    dubobs = gpd.GeoDataFrame(
        data = dubobs_dict,
        crs = config['lon_lat_crs'],
        geometry = 'geo'
    ).to_crs(config['meters_crs'])

    # -------------------------------------------------------------------------
    # set lon/lat for positioning popups on the map

    stopos['lon_lat'] = stopos.to_crs(config['lon_lat_crs'])['geo'].apply(lambda p: (p.x, p.y))
    poles['lon_lat'] = poles.to_crs(config['lon_lat_crs'])['geo'].apply(lambda p: (p.x, p.y))
    plafos['lon_lat'] = plafos['geo'].centroid.to_crs(config['lon_lat_crs']).apply(lambda p: (p.x, p.y))
    stops['lon_lat'] = poles.loc[stops['pole_id'], 'lon_lat'].set_axis(stops.index)
    dubobs['lon_lat'] = dubobs['geo'].centroid.to_crs(config['lon_lat_crs']).apply(lambda p: (p.x, p.y))

    for df in [stopos, poles, plafos, stops, dubobs]:
        if len(df) == 0:
            df['lon_lat'] = df['lon_lat'].astype('object') # else it's a further geometry column, causing troubles when writing to geojson
        df['lon'] = df['lon_lat'].apply(lambda x: x[0])
        df['lat'] = df['lon_lat'].apply(lambda x: x[1])
    
    # -------------------------------------------------------------------------
    # export plole-stopo matching details to JSON files

    for plole_id in ploles.index:
        plole = ploles.loc[plole_id, :]
        plafo_id = plole['plafo_id']
        plafo = plafos.loc[plafo_id, :] if plafo_id != 0 else None
        pole_id = plole['pole_id']
        pole = poles.loc[pole_id, :] if pole_id > 0 else None
        data = {}

        # general plole, plafo, pole data
        data['plole_id'] = int(plole_id)
        data['plafo_id'] = int(plafo_id)
        data['pole_id'] = int(pole_id)
        data['plole_mods'] = list(plole['mods'])
        data['plole_maybe_mods'] = list(plole['maybe_mods'])
        if plafo is not None:
            data['plafo_mods'] = list(plafo['mods'])
            data['plafo_maybe_mods'] = list(plafo['maybe_mods'])
            data['plafo_lon'] = plafo['lon']
            data['plafo_lat'] = plafo['lat']
        if pole is not None:
            data['pole_mods'] = list(pole['mods'])
            data['pole_maybe_mods'] = list(pole['maybe_mods'])
            data['pole_lon'] = pole['lon']
            data['pole_lat'] = pole['lat']

        # plafo and pole tags
        if plafo is not None:
            data['plafo_tags'] = {}
            for key in ['ref:IFOPT', 'ref', 'local_ref', 'ref_name', 'name', 'layer', 'level']:
                value = plafo['obj'].tags.get(key)
                data['plafo_tags'][key] = value if value else ''
        if pole is not None:
            data['pole_tags'] = {}
            for key in ['ref:IFOPT', 'ref', 'local_ref', 'ref_name', 'name', 'layer', 'level']:
                value = pole['obj'].tags.get(key)
                data['pole_tags'][key] = value if value else ''

        # plafo and pole stopos
        if plafo is not None:
            data['plafo_stopos'] = {int(k): v for k, v in plafo['stopo_infos'].items()}
            for stopo_id, stopo_info in data['plafo_stopos'].items():
                for key in ['ref:IFOPT', 'ref', 'local_ref', 'ref_name', 'name', 'layer', 'level']:
                    value = stopos.loc[stopo_id, 'obj'].tags.get(key)
                    stopo_info[key] = value if value else ''
                stopo_info['mods'] = list(stopos.loc[stopo_id, 'mods'])
                stopo_info['lon'] = stopos.loc[stopo_id, 'lon']
                stopo_info['lat'] = stopos.loc[stopo_id, 'lat']
                
        if pole is not None:
            data['pole_stopos'] = {int(k): v for k, v in pole['stopo_infos'].items()}
            for stopo_id, stopo_info in data['pole_stopos'].items():
                for key in ['ref:IFOPT', 'ref', 'local_ref', 'ref_name', 'name', 'layer', 'level']:
                    value = stopos.loc[stopo_id, 'obj'].tags.get(key)
                    stopo_info[key] = value if value else ''
                stopo_info['mods'] = list(stopos.loc[stopo_id, 'mods'])
                stopo_info['lon'] = stopos.loc[stopo_id, 'lon']
                stopo_info['lat'] = stopos.loc[stopo_id, 'lat']

        # plole stopos
        data['plole_stopos'] = {int(k): {'score': v['score']} for k, v in plole['stopo_infos'].items() if v['mods_match'] and v['score'] > 0}
        for stopo_id, stopo_info in data['plole_stopos'].items():
            stop_id = plole['stopo_infos'][stopo_id].get('stop_id')
            if stop_id:
                stopo_info['stop_id'] = stop_id
                stopo_info['reason'] = stops.loc[stop_id, 'stopo_reason']
            else:
                stopo_info['stop_id'] = -1
                stopo_info['reason'] = 'not required by this plole and better score with other plole'
            stopo_info['mods'] = list(stopos.loc[stopo_id, 'mods'])
            stopo_info['lon'] = stopos.loc[stopo_id, 'lon']
            stopo_info['lat'] = stopos.loc[stopo_id, 'lat']

        # write file
        file_name = config['ploles_path'] + config['region_code'] + str(plole_id) + '.json'
        with open(file_name, 'w') as f:
            json.dump(data, f)
        
    # -------------------------------------------------------------------------
    # lists to strings for comments and warnings

    def list2str(l):
        return ';'.join(l)

    for df in [stopos, poles, plafos, dubobs]:
        df['comments'] = df['obj'].apply(lambda obj: list2str(obj.comments) if type(obj) != float else '')
        df['warnings'] = df['obj'].apply(lambda obj: list2str(obj.warnings) if type(obj) != float else '')

    stops['warnings'] = stops['warnings'].apply(list2str)

    # -------------------------------------------------------------------------
    # mods to str

    stopos['mods'] = stopos['mods'].apply(mods2str)
    for df in [poles, plafos, stops]:
        df['mods'] = df['mods'].apply(lambda m: mods2str(m) if type(m) != float else '')
        df['maybe_mods'] = df['maybe_mods'].apply(lambda m: mods2str(m) if type(m) != float else '')    
    
    # -------------------------------------------------------------------------
    # object types (in JavaScript we cannot access an object's source)

    stopos['type'] = 'stopo'
    poles['type'] = 'pole'
    plafos['type'] = 'plafo'
    stops['type'] = 'stop'
    dubobs['type'] = 'dubob'

    # -------------------------------------------------------------------------
    # region code for stops

    stops['region'] = config['region_code']

    # -------------------------------------------------------------------------
    # export
    
    prefix = config['export_path'] + config['region_code'] + '_'
    
    stopos[['geo', 'lon', 'lat', 'comments', 'warnings', 'mods', 'type']] \
        .reset_index().to_crs(config['lon_lat_crs']).to_file(prefix + 'stopos.geojson', driver='GeoJSON')    
    poles[['geo', 'lon', 'lat', 'comments', 'warnings', 'mods', 'maybe_mods', 'type']] \
        .reset_index().to_crs(config['lon_lat_crs']).to_file(prefix + 'poles.geojson', driver='GeoJSON')    
    plafos[['geo', 'lon', 'lat', 'comments', 'warnings', 'mods', 'maybe_mods', 'type']] \
        .reset_index().to_crs(config['lon_lat_crs']).to_file(prefix + 'plafos.geojson', driver='GeoJSON')

    cols = ['geo', 'lon', 'lat', 'warnings', 'mods', 'maybe_mods', 'render', 'ptv2',
            'member_comments', 'member_warnings', 'plafo_id', 'pole_id', 'stopo_id',
            'plole_id', 'type', 'region']
    stops[cols].reset_index().to_crs(config['lon_lat_crs']).to_file(prefix + 'stops.geojson', driver='GeoJSON')
    stops['geo'] = stops['geo'].centroid
    stops[cols].reset_index().to_crs(config['lon_lat_crs']).to_file(prefix + 'nstops.geojson', driver='GeoJSON')    
        
    dubobs[['geo', 'lon', 'lat', 'osm_type', 'osm_id', 'warnings', 'comments', 'type']] \
        .reset_index().to_crs(config['lon_lat_crs']).to_file(prefix + 'dubobs.geojson', driver='GeoJSON')

    # -------------------------------------------------------------------------
    # make tiles
    
    logger.info('making tiles...')
    prefix = config['export_path'] + config['region_code'] + '_'
    os.system(f'tippecanoe --base-zoom=18 --minimum-zoom=18 --maximum-zoom=19 ' \
              f'--buffer=20 --drop-densest-as-needed --no-clipping ' \
              f'--no-tile-compression --force -t {config['export_path']} ' \
              f'--layer=a_stops --output={prefix}stops.mbtiles {prefix}stops.geojson')
    os.system(f'tippecanoe --base-zoom=18 --minimum-zoom=18 --maximum-zoom=19 ' \
              f'--buffer=20 --drop-densest-as-needed --no-clipping ' \
              f'--no-tile-compression --force -t {config['export_path']} ' \
              f'--layer=b_plafos --output={prefix}plafos.mbtiles {prefix}plafos.geojson')
    os.system(f'tippecanoe --base-zoom=18 --minimum-zoom=18 --maximum-zoom=19 ' \
              f'--buffer=20 --drop-densest-as-needed --no-clipping ' \
              f'--no-tile-compression --force -t {config['export_path']} ' \
              f'--layer=c_poles --output={prefix}poles.mbtiles {prefix}poles.geojson')
    os.system(f'tippecanoe --base-zoom=18 --minimum-zoom=18 --maximum-zoom=19 ' \
              f'--buffer=20 --drop-densest-as-needed --no-clipping ' \
              f'--no-tile-compression --force -t {config['export_path']} ' \
              f'--layer=d_stopos --output={prefix}stopos.mbtiles {prefix}stopos.geojson')
    os.system(f'tippecanoe --base-zoom=11 --minimum-zoom=0 --maximum-zoom=17 ' \
              f'--buffer=20 --drop-densest-as-needed --no-clipping ' \
              f'--no-tile-compression --force -t {config['export_path']} ' \
              f'--layer=e_nstops --output={prefix}nstops.mbtiles {prefix}nstops.geojson')
    os.system(f'tippecanoe --base-zoom=11 --minimum-zoom=0 --maximum-zoom=19 ' \
              f'--buffer=20 --drop-densest-as-needed --no-clipping ' \
              f'--no-tile-compression --force -t {config['export_path']} ' \
              f'--layer=f_dubobs --output={prefix}dubobs.mbtiles {prefix}dubobs.geojson')
    logger.info('...done')

    return True
