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
    center: [50.7162946, 12.4952878],
    minZoom: 0,
    maxZoom: 19,
    zoomControl: false,
    zoom: 4,
});

var osmBaseLayer = L.tileLayer(
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {
        maxZoom: 19,
        maxNativeZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }
).addTo(map);

var blackLayer = L.imageOverlay(
    'black.png',
    [[-90, -180], [90, 180]],
    {
        opacity: 0.5,
        maxZoom: 17,

    }
).addTo(map);

var ptsaLayer = new L.VectorGrid.Protobuf(
    ptsaTilesUrl,
    {
        rendererFactory: L.canvas.tile,
        interactive: true,
        attribution: '<a href="https://whz.de/~jef19jdw">Jens Flemming</a>',
        maxNativeZoom: 19,
        minZoom: 0,
        pane: map.getPane('overlayPane'),
        vectorTileLayerStyles: {
            a_stops: stopsStyler,
            b_plafos: plafosStyler,
            c_poles: polesStyler,
            d_stopos: stoposStyler,
            e_nstops: nstopsStyler,
            f_dubobs: dubobsStyler,
        }
    }
).addTo(map);

//----------------------------------------------------------------------------

const neutralColor = '#808080';

const renderColors = {
    0: neutralColor,
    1: '#ff0000',
    2: '#ffff00',
    3: '#00ff00',
    4: '#00ffc0'
}

const ptv2Colors = {
    0: neutralColor,
    1: '#ff0000',
    2: '#ffff00',
    3: '#00ff00'
}

const warnColors = {
    warn: '#ff0000',
    comm: '#ffff00',
    none: '#00ff00'
}

const structColors = {
    s: '#ffff00',
    sp: '#0000ff',
    sf: '#0000ff',
    spf: '#00ffff',
    p: '#ffff00',
    f: '#ffff00',
    pf: '#ff0000'
}

const dubobsColor = '#ff00ff';

function mods_visible(mods_str) {
    var mods = mods_str.split(', ');
    for (let i = 0; i < mods.length; i++) {
        if (mods[i] == '' || mods[i] == 'NO_MODALITY') {
            if (document.getElementById('mod_none').checked == true) {
                return true;
            } else {
                return false;
            }
        }
        if (document.getElementById('mod_' + mods[i]).checked == true) {
            return true;
        }
    }
    return false;
}

function getWarnColor(props) {
    var comm = props['comments'] != '';
    var warn = props['warnings'] != '';
    if (warn == true && document.getElementById('warn_warn').checked == true) {
        return warnColors['warn'];
    } else if (comm == true && document.getElementById('warn_comm').checked == true) {
        return warnColors['comm'];
    } else if (warn == false && comm == false && document.getElementById('warn_none').checked == true) {
        return warnColors['none'];
    } else {
        return null;
    }
}

function stoposStyler(props, zoom) {
    vis = document.getElementById('stopos').checked;
    mods_vis = mods_visible(props['mods']);
    if (!(vis == true && mods_vis == true)) {
        return [];
    }
    if (document.getElementById('warn').checked == true) {
        color = getWarnColor(props);
        if (color == null) {
            color = neutralColor;
        }
    } else {
        color = neutralColor;
    }
    return({
        radius: 4,
        color: '#000000',
        opacity: 1.0,
        weight: 1,
        fill: true,
        fillColor: color,
        fillOpacity: 1.0,
    });
}

function polesStyler(props, zoom) {
    if (props['id'] > 0) {
        vis = document.getElementById('poles').checked;
    } else {
        vis = document.getElementById('vpoles').checked;
    }
    mods_vis = mods_visible(props['mods']);
    if (!(vis == true && mods_vis == true)) {
        return [];
    }
    if (document.getElementById('warn').checked == true) {
        color = getWarnColor(props);
        if (color == null) {
            color = neutralColor;
        }
    } else {
        color = neutralColor;
    }
    return({
        radius: 7,
        color: '#000000',
        opacity: 1.0,
        weight: 1,
        fill: true,
        fillColor: color,
        fillOpacity: 1.0,
    });
}

function plafosStyler(props, zoom) {
    vis = document.getElementById('plafos').checked;
    mods_vis = mods_visible(props['mods']);
    if (!(vis == true && mods_vis == true)) {
        return [];
    }
    if (document.getElementById('warn').checked == true) {
        color = getWarnColor(props);
        if (color == null) {
            color = neutralColor;
        }
    } else {
        color = neutralColor;
    }
    return({
        color: '#000000',
        opacity: 1.0,
        weight: 1,
        fill: true,
        fillColor: color,
        fillOpacity: 1.0,
    });
}

function getStopColor(props) {

    if (document.getElementById('stops').checked == false) {
        return null;
    }
         
    if (mods_visible(props['mods']) == false) {
        return null;
    }
    
    if (document.getElementById('warn').checked == true) {
        var comm = props['member_comments'];
        var warn = props['member_warnings'] || props['warnings'] != '';
        if (warn == true && document.getElementById('warn_warn').checked == true) {
            return warnColors['warn'];
        } else if (comm == true && document.getElementById('warn_comm').checked == true) {
            return warnColors['comm'];
        } else if (warn == false && comm == false && document.getElementById('warn_none').checked == true) {
            return warnColors['none'];
        } else {
            return null;
        }
    } else if (document.getElementById('render').checked == true) {
        if (props['render'] == 1 && document.getElementById('render_no').checked == true) {
            return renderColors[1];
        } else if (props['render'] == 2 && document.getElementById('render_inc').checked == true) {
            return renderColors[2];
        } else if (props['render'] == 3 && document.getElementById('render_good').checked == true) {
            return renderColors[3];
        } else if (props['render'] == 4 && document.getElementById('render_station').checked == true) {
            return renderColors[4];
        } else {
            return null;
        }
    } else if (document.getElementById('ptv2').checked == true) {
        if (props['ptv2'] == 1 && document.getElementById('ptv2_no').checked == true) {
            return ptv2Colors[1];
        } else if (props['ptv2'] == 2 && document.getElementById('ptv2_mix').checked == true) {
            return ptv2Colors[2];
        } else if (props['ptv2'] == 3 && document.getElementById('ptv2_yes').checked == true) {
            return ptv2Colors[3];
        } else {
            return null;
        }
    } else if (document.getElementById('struct').checked == true) {
        struct = '';
        if (props['stopo_id'] > 0) {
            struct = struct + 's';
        }
        if (props['pole_id'] > 0) {
            struct = struct + 'p';
        }
        if (props['plafo_id'] != 0) {
            struct = struct + 'f';
        }
        if (document.getElementById('struct_' + struct).checked == true) {
            return structColors[struct];
        } else {
            return null;
        }
    }
        
    return null;
}

function stopsStyler(props, zoom) {
    color = getStopColor(props);
    if (color != null) {
        return ({
            color: '#000000',
            weight: 1,
            opacity: 1.0,
            fill: true,
            fillColor: color,
            fillOpacity: 0.5,
        });
    } else {
        return [];
    }
}

function nstopsStyler(props, zoom) {
    color = getStopColor(props);
    if (color != null) {
        radius = 5;
        if ((zoom <= 13) && (zoom >= 11)) {
            radius = zoom - 9;
        } else if (zoom < 11) {
            radius = 1;
        }
        return ({
            radius: radius,
            color: color,
            weight: 1,
            opacity: 1.0,
            fill: true,
            fillColor: color,
            fillOpacity: 1.0,
        });
    } else {
        return [];
    }
}

function dubobsStyler(props, zoom) {
    vis = document.getElementById('dubobs').checked;
    if (vis == true) {
        return({
            radius: 7,
            color: '#000000',
            opacity: 1.0,
            weight: 1,
            fill: true,
            fillColor: dubobsColor,
            fillOpacity: 1.0,
        });
    } else {
        return [];
    }
}

//----------------------------------------------------------------------------

ptsaLayer.addEventListener('click', ptsaLayerClickHandler);

function osm_link(type, id) {
    return '<a href="https://osm.org/' + type + '/' + id + '" target="_blank">' + id + '</a>';
}

function comments2html(comments) {
    var html = '';
    if (comments != '') {
        html += '<p><span class="parahead">comments:</span></p><ul>';
        for (const comment of comments.split(';')) {
            html += '<li>' + comment + '</li>';
        }
        html += '</ul>';
    }
    return html;
}

function warnings2html(warnings) {
    var html = '';
    if (warnings != '') {
        html += '<p><span class="parahead">warnings:</span></p><ul>';
        for (const warning of warnings.split(';')) {
            html += '<li>' + warning + '</li>';
        }
        html += '</ul>';
    }
    return html;
}

function mods2html(mods, maybe_mods) {
    var html = '<p><span class="parahead">modalities:</span> ';
    if (mods != '' && mods != 'NO_MODALITY') {
        html += mods;
    } else {
        html += 'none';
    }
    if (maybe_mods != '' && maybe_mods != 'NO_MODALITY') {
        html += ' (maybe ' + maybe_mods + ')';
    }
    html += '</p>';
    return html;
}

function ptsaLayerClickHandler(e) {
    var props = e.layer.properties
    if (!props.lat) { return; };
    var html = '<div class="popup">';

    if (props.type == 'stopo') {
        html += '<h1>Stop position</h1>'
        html += '<p>node ' + osm_link('node', props.id) + '</p>';
        html += mods2html(props.mods, '');
        html += comments2html(props.comments);
        html += warnings2html(props.warnings);
    } else if (props.type == 'pole' && props.id > 0) {
        html += '<h1>Pole</h1>'
        html += '<p>node ' + osm_link('node', props.id) + '</p>';
        html += mods2html(props.mods, props.maybe_mods);
        html += comments2html(props.comments);
        html += warnings2html(props.warnings);
    } else if (props.type == 'pole' && props.id < 0) {
        html += '<h1>Virtual pole</h1>'
        html += '<p>ID ' + (-props.id) + '</p>';
    } else if (props.type == 'plafo') {
        html += '<h1>Platform</h1>'
        if (props.id > 0) {
            html += '<p>way ' + osm_link('way', props.id) + '</p>';
        } else {
            html += '<p>relation ' + osm_link('relation', -props.id) + '</p>';
        }
        html += mods2html(props.mods, props.maybe_mods);
        html += comments2html(props.comments);
        html += warnings2html(props.warnings);
    } else if (props.type == 'stop') {
        html += '<h1>Stop</h1>'
        if (props.stopo_id > 0) {
            stopo = 'node ' + osm_link('node', props.stopo_id);
        } else {
            stopo = 'none';
        }
        if (props.pole_id > 0) {
            pole = 'node ' + osm_link('node', props.pole_id);
        } else {
            pole = 'none';
        }
        if (props.plafo_id > 0) {
            plafo = 'way ' + osm_link('way', props.plafo_id);
        } else if (props.plafo_id < 0) {
            plafo = 'relation ' + osm_link('relation', -props.plafo_id);
        } else {
            plafo = 'none';
        }
        html += '<p><span class="parahead">stop position:</span> ' + stopo + '</p>';
        html += '<p><span class="parahead">pole:</span> ' + pole + '</p>';
        html += '<p><span class="parahead">platform:</span> ' + plafo + '</p>';
        html += mods2html(props.mods, props.maybe_mods);
        html += warnings2html(props.warnings);
        if (props.member_comments == true) {
            html += '<p>Some stop components have comments.</p>';
        }
        if (props.member_warnings == true) {
            html += '<p>Some stop components have warnings.</p>';
        }
        if (props.plole_id > -1) {
            html += '<p><a href="details.html?region=' + props.region + '&plole=' + props.plole_id + '" target="_blank">Plole details</a></p>';
        }
    } else if (props.type == 'dubob') {
        html += '<h1>Dubious object</h1>'
        if (props.osm_type == 'node') {
            html += '<p>node ' + osm_link('node', props.osm_id) + '</p>';
        } else if (props.osm_type == 'way_area') {
            html += '<p>way ' + osm_link('way', props.osm_id) + '</p>';
        } else { // mupo_area
            html += '<p>relation ' + osm_link('relation', -props.osm_id) + '</p>';
        }
        html += comments2html(props.comments);
        html += warnings2html(props.warnings);
    }
    
    html += '</div>'
    L.popup([props.lat, props.lon])
    .setContent(html)
    .openOn(map);
};

//----------------------------------------------------------------------------

function toggle_sidebar() {
    var boxes = document.getElementsByClassName('sidebar_content');
    for (let i = 0; i < boxes.length; i++) {
        if (boxes[i].style.display == 'none') {
            boxes[i].style.display = 'block';
            if (i == 0) {
                var sb = document.getElementById('sidebar');
                sb.style.height = '100%';
                sb.style.width = '300px';
            }
        } else {
            boxes[i].style.display = 'none';
            if (i == 0) {
                var sb = document.getElementById('sidebar');
                sb.style.height = 'auto';
                sb.style.width = 'auto';
            }
        }
    }
}

function redraw() {
    ptsaLayer.redraw();
}