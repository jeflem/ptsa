// workaround for error in vectorgrid code
// cf. https://github.com/Leaflet/Leaflet.VectorGrid/issues/148
//L.DomEvent.fakeStop = () => 0;
L.Canvas.Tile.include({
	_onClick: function (e) {
		var point = this._map.mouseEventToLayerPoint(e).subtract(this.getOffset());
		var layer;
		var clickedLayer;

		for (var id in this._layers) {
			layer = this._layers[id];
			if (
				layer.options.interactive &&
				layer._containsPoint(point) &&
				!this._map._draggableMoved(layer)
			) {
				clickedLayer = layer;
			}
		}
		if (clickedLayer) {
                         // offending code used to be right here
			clickedLayer.fireEvent(e.type, undefined, true);
		}
	},
});

//----------------------------------------------------------------------------

const ptsaTilesUrl = "http://localhost/tiles/{z}/{x}/{y}.pbf";

//----------------------------------------------------------------------------

var map = L.map('map', {
    center: [50.8391871, 12.9242809], //[50.868378, 12.864990],
    minZoom: 0,
    maxZoom: 19,
    zoomControl: false,
    zoom: 19,
});

var osmBaseLayer = L.tileLayer(
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {
        maxZoom: 19,
        maxNativeZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }
).addTo(map);


//----------------------------------------------------------------------------

const searchParams = new URLSearchParams(window.location.search);
var plole_id = searchParams.get('plole');
var okay = false;
if (plole_id != null) {
    plole_id = parseInt(plole_id);
    okay = true;
} else {
    okay = false;
    document.body.innerHTML = 'invalid plole ID';
}
region = searchParams.get('region');
if (region == null) {
    okay = false;
    document.body.innerHTML = 'invalid region code';
}

if (okay == true) {
    fetch('ploles/' + region + plole_id + '.json')
        .then((response) => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then((json) => show_data(json))
        .catch((err) => document.body.innerHTML = ('error: ' + err.message));
}

const all_mods = ['bus', 'trolley_bus', 'share_taxi', 'tram', 'light_rail', 'train', 'monorail', 'subway', 'funicular', 'ferry', 'aerialway'];

function osm_link(type, id, text) {
    html = '<a href="https://osm.org/';
    if (type == 'plafo' && id > 0) {
        osm_type = 'way';
        osm_id = id;
    } else if (type == 'plafo' && id < 0) {
        osm_type = 'relation';
        osm_id = -id;
    } else {
        osm_type = 'node';
        osm_id = id;
    }
    html += osm_type + '/' + osm_id;
    html += '" target="_blank">';
    html += text;
    html += '</a> (<a href="https://osm.org/edit?' + osm_type + '=' + osm_id + '" target="_blank">edit in iD</a>)';
    return html;
}

function makeModsRow(title, mods, maybe_mods) {
    var html = '<tr><td class="head">' + title + '</td>';
    for (const mod of all_mods) {
        if (mods.includes(mod)) {
            c = 'green';
        } else if (maybe_mods.includes(mod)) {
            c = 'yellow';
        } else {
            c = 'red';
        }
        html += '<td class="' + c + '">■</td>';
    }
    html += '</tr>';
    return html;
}

function makeTagsRow(title, mods_match, tags, score) {
    var html = '<tr><td class="head">' + title + '</td>';
    if (typeof mods_match === 'string') {
        c = '';
        text = mods_match;
    } else if (mods_match == true) {
            c = 'green';
            text = 'yes';
    } else {
        c = 'red';
        text = 'no';
    }
    html += '<td class="' + c + '">' + text + '</td>';
    for (const key of ['ref:IFOPT', 'ref', 'local_ref', 'ref_name', 'name']) {
        if (typeof score !== 'number') {
            c = '';
        } else {
            if (tags[key + '_match'] > 0) {
                c = 'green';
            } else if (tags[key + '_match'] == 0) {
                c = 'yellow';
            } else {
                c = 'red';
            }
        }
        html += '<td class="' + c + '">' + tags[key] + '</td>';
    }
    if (typeof score !== 'number') {
        c = '';
    } else {
        if (score > 0) {
            c = 'green';
        } else {
            c = 'red';
        }
    }
    html += '<td class="' + c + '">' + score + '</td>';
    html += '</tr>';
    return html;
}

function getStopoLabel(stopo_id) {
    return stopo_ids.indexOf(parseInt(stopo_id)) + 1;
}

var plafo_id = null;
var pole_id = null;
var stopo_ids = null;

function show_data(data) {

    // show objects on map
    plafo_id = data.plafo_id;
    pole_id = data.pole_id;
    stopo_ids = [];
    if (plafo_id != 0) {
        for (const [stopo_id, stopo_info] of Object.entries(data.plafo_stopos)) {
            stopo_ids.push(parseInt(stopo_id));
        }
        lat = data.plafo_lat;
        lon = data.plafo_lon;
    }
    if (pole_id > 0) {
        for (const [stopo_id, stopo_info] of Object.entries(data.pole_stopos)) {
            if (!stopo_ids.includes(parseInt(stopo_id))) {
                stopo_ids.push(parseInt(stopo_id));
            }
        }
        lat = data.pole_lat;
        lon = data.pole_lon;
    }
    map.panTo(new L.LatLng(lat, lon));
    /*if (plafo_id != 0) {
        L.marker([data.plafo_lat, data.plafo_lon], {icon: L.divIcon({
            className: 'map_label',
            html: 'P'
        })}).addTo(map);
    }
    if (pole_id > 0) {
        L.marker([data.pole_lat, data.pole_lon], {icon: L.divIcon({
            className: 'map_label',
            html: 'P'
        })}).addTo(map);
    }*/
    if (plafo_id != 0) {
        for (const [stopo_id, stopo_info] of Object.entries(data.plafo_stopos)) {
            L.marker([stopo_info.lat, stopo_info.lon], {icon: L.divIcon({
                className: 'map_label',
                iconAnchor: [-2, -2],
                html: getStopoLabel(stopo_id)
            })}).addTo(map);
        }
    }
    if (pole_id > 0) {
        for (const [stopo_id, stopo_info] of Object.entries(data.pole_stopos)) {
            L.marker([stopo_info.lat, stopo_info.lon], {icon: L.divIcon({
                className: 'map_label',
                iconAnchor: [-2, -2],
                html: getStopoLabel(stopo_id)
            })}).addTo(map);
        }
    }
    
    // modalities
    var html = '';
    if (plafo_id != 0) {
        html += makeModsRow('platform', data.plafo_mods, data.plafo_maybe_mods);
    }
    if (pole_id > 0) {
        html += makeModsRow('pole', data.pole_mods, data.pole_maybe_mods);
    }
    if (plafo_id != 0 && pole_id > 0) {
        html += makeModsRow('plole', data.plole_mods, data.plole_maybe_mods);
    }
    listed_stopos = []
    if (data.plafo_id != 0) {
        for (const [stopo_id, stopo_info] of Object.entries(data.plafo_stopos)) {
            listed_stopos.push(stopo_id);
            html += makeModsRow('stop position ' + getStopoLabel(stopo_id), stopo_info.mods, []);
        }
    }
    if (data.pole_id > 0) {
        for (const [stopo_id, stopo_info] of Object.entries(data.pole_stopos)) {
            if (!listed_stopos.includes(stopo_id)) {
                html += makeModsRow('stop position ' + getStopoLabel(stopo_id), stopo_info.mods, []);
            }
        }
    }
    document.getElementById('mods_tbody').innerHTML = html;
    
    // plafo-stopo matching
    if (plafo_id == 0) {
        document.getElementById('plafo').style.display = 'none';
    } else {
        html = '';
        html += makeTagsRow(osm_link('plafo', plafo_id, 'platform'), '', data.plafo_tags, '-');
        for (const [stopo_id, stopo_info] of Object.entries(data.plafo_stopos)) {
            html += makeTagsRow(osm_link('stopo', stopo_id, 'stop position ' + getStopoLabel(stopo_id)), stopo_info.mods_match, stopo_info, stopo_info.score);

        }
        document.getElementById('plafo_tbody').innerHTML = html;
    }
    
    // pole-stopo matching
    if (pole_id <= 0) {
        document.getElementById('pole').style.display = 'none';
    } else {
        html = '';
        html += makeTagsRow(osm_link('pole', pole_id, 'pole'), '', data.pole_tags, '-');
        for (const [stopo_id, stopo_info] of Object.entries(data.pole_stopos)) {
            html += makeTagsRow(osm_link('stopo', stopo_id, 'stop position ' + getStopoLabel(stopo_id)), stopo_info.mods_match, stopo_info, stopo_info.score);
        }
        document.getElementById('pole_tbody').innerHTML = html;
    }
    
    // plole-stopo matching
    html = '';
    for (const [stopo_id, stopo_info] of Object.entries(data.plole_stopos)) {
        html += '<tr>';
        html += '<td class="head">' + osm_link('stopo', stopo_id, 'stop position ' + getStopoLabel(stopo_id)) + '</td>';
        html += '<td>' + stopo_info.score + '</td>';
        if (stopo_info.stop_id > -1) {
            c = 'green';
        } else {
            c = 'red';
        }
        html += '<td class="'+ c + '">' + stopo_info.reason + '</td>';
        html += '</tr>';
    }
    document.getElementById('plole_tbody').innerHTML = html;
    if (Object.entries(data.plole_stopos).length == 0) {
        document.getElementById('plole').innerHTML = '<h2>Stop positions for plole</h2>no stop positions for this plole';
    }
    
    
    //throw new Error('test error');
}


//----------------------------------------------------------------------------
var ptsaLayer = new L.VectorGrid.Protobuf(
    ptsaTilesUrl,
    {
        rendererFactory: L.canvas.tile,
        interactive: false,
        attribution: '',
        maxNativeZoom: 19,
        minZoom: 0,
        pane: map.getPane('overlayPane'),
        vectorTileLayerStyles: {
            a_stops: noStyler,
            b_plafos: plafosStyler,
            c_poles: polesStyler,
            d_stopos: stoposStyler,
            e_nstops: noStyler,
            f_dubobs: noStyler,
        }
    }
).addTo(map);

function noStyler(props, zoom) {
    return [];
}

function stoposStyler(props, zoom) {
    if (!stopo_ids.includes(props.id)) {
        return [];
    }
    return({
        radius: 4,
        color: '#000000',
        opacity: 1.0,
        weight: 1,
        fill: true,
        fillColor: '#ff00ff',
        fillOpacity: 1.0,
    });
}

function polesStyler(props, zoom) {
    if (props.id != pole_id || pole_id <= 0) {
        return [];
    }
    return({
        radius: 7,
        color: '#000000',
        opacity: 1.0,
        weight: 1,
        fill: true,
        fillColor: '#ff00ff',
        fillOpacity: 1.0,
    });
}

function plafosStyler(props, zoom) {
    if (props.id != plafo_id) {
        return [];
    }
    return({
        color: '#000000',
        opacity: 1.0,
        weight: 1,
        fill: true,
        fillColor: '#ff00ff',
        fillOpacity: 1.0,
    });
}

function redraw() {
    ptsaLayer.redraw();
}