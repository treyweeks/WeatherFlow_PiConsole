""" Weather Radar panel helper for the Raspberry Pi Python console for
WeatherFlow Tempest and Smart Home Weather stations.

Fetches radar tile frames from the free RainViewer API and composites them
onto OpenStreetMap base tiles using Pillow.  Frames are cached by timestamp
so only new data is downloaded on each refresh.  Frames older than
`history_hours` are automatically purged.

Free data sources (no API key required):
  - Radar:    https://www.rainviewer.com/api.html
  - Geocode:  https://api.zippopotam.us/
  - Base map: https://tile.openstreetmap.org/ (OSM tile usage policy applies)

Dependencies:
  pip install Pillow requests
"""

import io
import json
import math
import os
import time

import requests
from PIL import Image

# ---------------------------------------------------------------------------
# Paths relative to this file's directory
# ---------------------------------------------------------------------------
_HERE         = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH   = os.path.join(_HERE, 'weatherradar_config.json')
FRAMES_DIR    = os.path.join(_HERE, 'frames')
BASE_MAP_PATH = os.path.join(_HERE, 'base_map.png')
BASE_KEY_PATH = os.path.join(_HERE, 'base_map_key.txt')

_HEADERS       = {'User-Agent': 'WeatherFlow-PIConsole/RadarPanel/1.0 (personal use)'}
_RAINVIEWER    = 'https://api.rainviewer.com/public/weather-maps.json'
_ZIPPOPOTAM    = 'https://api.zippopotam.us/{country}/{zip}'
_RADAR_TILE    = '{host}{path}/256/{z}/{x}/{y}/{color}/{smooth}_{snow}.png'
_TILE_PX       = 256

# Base map tile sources — CartoDB subdomains are rotated to spread requests
_TILE_THEMES = {
    'osm':        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    'carto_dark': 'https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png',
    'carto_light': 'https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
}
_CARTO_SUBDOMAINS = ['a', 'b', 'c', 'd']


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config():
    """Return the parsed weatherradar_config.json dict."""
    with open(CONFIG_PATH, 'r') as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------
def zip_to_coords(zip_code, country='us'):
    """Return (lat, lng) floats for a postal code via zippopotam.us."""
    url  = _ZIPPOPOTAM.format(country=country, zip=zip_code)
    resp = requests.get(url, timeout=10, headers=_HEADERS)
    resp.raise_for_status()
    place = resp.json()['places'][0]
    return float(place['latitude']), float(place['longitude'])


def coords_to_tile(lat, lng, zoom):
    """Convert (lat, lng) to Web Mercator tile (x, y) at *zoom*."""
    lat_r = math.radians(lat)
    n     = 2 ** zoom
    tx    = int((lng + 180.0) / 360.0 * n)
    ty    = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return tx, ty


# ---------------------------------------------------------------------------
# Internal tile fetch
# ---------------------------------------------------------------------------
def _fetch_image(url, timeout=15):
    """GET *url* and return a PIL RGBA Image."""
    resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert('RGBA')


# ---------------------------------------------------------------------------
# OSM base map
# ---------------------------------------------------------------------------
def _ensure_base_map(tile_x, tile_y, zoom, grid_size, theme='osm'):
    """
    Return a stitched base-map PIL Image for the given tile grid,
    rebuilding it only when the view parameters or theme change.
    """
    os.makedirs(FRAMES_DIR, exist_ok=True)
    key = f'{zoom}_{tile_x}_{tile_y}_{grid_size}_{theme}'

    cached_key = ''
    if os.path.exists(BASE_KEY_PATH):
        with open(BASE_KEY_PATH) as fh:
            cached_key = fh.read().strip()

    if cached_key == key and os.path.exists(BASE_MAP_PATH):
        return Image.open(BASE_MAP_PATH).convert('RGBA')

    tile_url_template = _TILE_THEMES.get(theme, _TILE_THEMES['osm'])
    print(f'[WeatherRadar] Rebuilding base map zoom={zoom} grid={grid_size}x{grid_size} theme={theme}')
    half   = grid_size // 2
    size   = _TILE_PX * grid_size
    canvas = Image.new('RGBA', (size, size))
    sub_i  = 0  # subdomain rotation index for CartoDB

    for row in range(grid_size):
        for col in range(grid_size):
            tx  = tile_x - half + col
            ty  = tile_y - half + row
            s   = _CARTO_SUBDOMAINS[sub_i % len(_CARTO_SUBDOMAINS)]
            sub_i += 1
            url = tile_url_template.format(z=zoom, x=tx, y=ty, s=s)
            try:
                tile = _fetch_image(url)
                tile = tile.resize((_TILE_PX, _TILE_PX), Image.LANCZOS)
                canvas.paste(tile, (col * _TILE_PX, row * _TILE_PX))
            except Exception as exc:
                print(f'[WeatherRadar] Base tile {zoom}/{tx}/{ty} failed: {exc}')

    canvas.save(BASE_MAP_PATH)
    with open(BASE_KEY_PATH, 'w') as fh:
        fh.write(key)
    return canvas


# ---------------------------------------------------------------------------
# Frame cache helpers
# ---------------------------------------------------------------------------
def _frame_path(timestamp):
    """Canonical path for a cached frame PNG, keyed by RainViewer timestamp."""
    return os.path.join(FRAMES_DIR, f'frame_{timestamp}.png')


def _purge_old_frames(history_hours):
    """Delete any cached frame PNG older than *history_hours*."""
    cutoff = time.time() - history_hours * 3600
    if not os.path.isdir(FRAMES_DIR):
        return
    for name in os.listdir(FRAMES_DIR):
        if not (name.startswith('frame_') and name.endswith('.png')):
            continue
        try:
            ts = int(name[len('frame_'):-len('.png')])
            if ts < cutoff:
                os.remove(os.path.join(FRAMES_DIR, name))
                print(f'[WeatherRadar] Purged old frame {name}')
        except ValueError:
            pass


def _cached_frame_paths(history_hours):
    """
    Return all cached frame paths within the history window,
    sorted oldest → newest.
    """
    cutoff = time.time() - history_hours * 3600
    paths  = []
    if not os.path.isdir(FRAMES_DIR):
        return paths
    for name in os.listdir(FRAMES_DIR):
        if not (name.startswith('frame_') and name.endswith('.png')):
            continue
        try:
            ts = int(name[len('frame_'):-len('.png')])
            if ts >= cutoff:
                paths.append((ts, os.path.join(FRAMES_DIR, name)))
        except ValueError:
            pass
    paths.sort(key=lambda t: t[0])
    return [p for _, p in paths]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_radar_frames(config):
    """
    Incrementally update the rolling radar frame cache and return the full
    list of cached frame paths (oldest → newest) within the history window.

    Only timestamps not already on disk are downloaded and composited.
    Frames older than `history_hours` are automatically purged.
    Returns an empty list on any unrecoverable error.
    """
    try:
        zip_code      = str(config.get('zip_code', ''))
        country       = config.get('country', 'us')
        zoom          = int(config.get('zoom', 7))
        grid_size     = int(config.get('tile_grid', 3))
        tile_theme    = config.get('tile_theme', 'osm')
        history_hours = float(config.get('history_hours', 3))
        color         = int(config.get('color_scheme', 6))
        smooth        = int(config.get('smooth', 1))
        snow          = int(config.get('snow', 0))
        half          = grid_size // 2

        # Purge frames outside the history window first
        _purge_old_frames(history_hours)

        lat, lng       = zip_to_coords(zip_code, country)
        tile_x, tile_y = coords_to_tile(lat, lng, zoom)
        base           = _ensure_base_map(tile_x, tile_y, zoom, grid_size, tile_theme)

        # Fetch RainViewer frame list (all past frames they provide)
        rv       = requests.get(_RAINVIEWER, timeout=10, headers=_HEADERS)
        rv.raise_for_status()
        rv_data  = rv.json()
        host     = rv_data['host']
        cutoff   = time.time() - history_hours * 3600
        # Only keep frames within our history window
        meta_list = [m for m in rv_data['radar']['past'] if m['time'] >= cutoff]

        if not meta_list:
            print('[WeatherRadar] No frames within history window')
            return _cached_frame_paths(history_hours)

        new_count = 0
        for meta in meta_list:
            ts        = meta['time']
            out_path  = _frame_path(ts)

            # Skip frames we already have on disk
            if os.path.exists(out_path):
                continue

            frame = base.copy()
            for row in range(grid_size):
                for col in range(grid_size):
                    tx  = tile_x - half + col
                    ty  = tile_y - half + row
                    url = _RADAR_TILE.format(
                        host=host, path=meta['path'],
                        z=zoom, x=tx, y=ty,
                        color=color, smooth=smooth, snow=snow)
                    try:
                        radar = _fetch_image(url)
                        frame.paste(radar, (col * _TILE_PX, row * _TILE_PX), radar)
                    except Exception as exc:
                        print(f'[WeatherRadar] Radar tile error: {exc}')

            frame.convert('RGB').save(out_path)
            new_count += 1

        if new_count:
            print(f'[WeatherRadar] Downloaded {new_count} new frame(s)')

        all_paths = _cached_frame_paths(history_hours)
        print(f'[WeatherRadar] {len(all_paths)} frames in cache ({history_hours}h window)')
        return all_paths

    except Exception as exc:
        print(f'[WeatherRadar] fetch_radar_frames failed: {exc}')
        # Return whatever is cached rather than showing nothing
        return _cached_frame_paths(config.get('history_hours', 3))
