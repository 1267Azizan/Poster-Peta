import osmnx as ox
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import matplotlib.colors as mcolors
import numpy as np
from geopy.geocoders import Nominatim
from tqdm import tqdm
import time
import json
import os
from datetime import datetime
import argparse
from pathlib import Path
from hashlib import md5
import pickle
from concurrent.futures import ThreadPoolExecutor
import geopandas as gpd
from shapely.geometry import Point, box

class CacheError(Exception):
    """Raised when a cache operation fails."""
    pass

CACHE_DIR_PATH = os.environ.get("CACHE_DIR", "cache")
CACHE_DIR = Path(CACHE_DIR_PATH)

CACHE_DIR.mkdir(exist_ok=True)
OSM_CACHE_DIR = CACHE_DIR / "osmnx"
OSM_CACHE_DIR.mkdir(exist_ok=True)

# OSMnx settings for faster repeated requests
ox.settings.use_cache = True
ox.settings.cache_folder = str(OSM_CACHE_DIR)
ox.settings.log_console = False

# Network type can be overridden for more detail: set OSM_NETWORK_TYPE=all
OSM_NETWORK_TYPE = os.environ.get("OSM_NETWORK_TYPE", "drive")

def cache_file(key: str) -> str:
    encoded = md5(key.encode()).hexdigest()
    return f"{encoded}.pkl"

def cache_get(name: str) -> dict | None:
    path = CACHE_DIR / cache_file(name)
    if path.exists():
        with path.open("rb") as f:
            return pickle.load(f)
    return None

def _report_cache(cache_cb, name, hit):
    if cache_cb:
        try:
            cache_cb(name, hit)
        except Exception:
            pass

def cache_set(name: str, obj) -> None:
    path = CACHE_DIR / cache_file(name)
    try:
        with path.open("wb") as f:
            pickle.dump(obj, f)
    except pickle.PickleError as e:
        raise CacheError(
            f"Serialization error while saving cache for '{name}': {e}"
        ) from e
    except (OSError, IOError) as e:
        raise CacheError(
            f"File error while saving cache for '{name}': {e}"
        ) from e

THEMES_DIR = "themes"
FONTS_DIR = "fonts"
POSTERS_DIR = "posters"

def load_fonts():
    """
    Load Roboto fonts from the fonts directory.
    Returns dict with font paths for different weights.
    """
    fonts = {
        'bold': os.path.join(FONTS_DIR, 'Roboto-Bold.ttf'),
        'regular': os.path.join(FONTS_DIR, 'Roboto-Regular.ttf'),
        'light': os.path.join(FONTS_DIR, 'Roboto-Light.ttf')
    }
    
    # Verify fonts exist
    for weight, path in fonts.items():
        if not os.path.exists(path):
            print(f"⚠ Font tidak ditemukan: {path}")
            return None
    
    return fonts

FONTS = load_fonts()

def generate_output_filename(city, theme_name, output_format):
    """
    Generate unique output filename with city, theme, and datetime.
    """
    if not os.path.exists(POSTERS_DIR):
        os.makedirs(POSTERS_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    city_slug = city.lower().replace(' ', '_')
    ext = output_format.lower()
    filename = f"{city_slug}_{theme_name}_{timestamp}.{ext}"
    return os.path.join(POSTERS_DIR, filename)

def get_available_themes():
    """
    Scans the themes directory and returns a list of available theme names.
    """
    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)
        return []
    
    themes = []
    for file in sorted(os.listdir(THEMES_DIR)):
        if file.endswith('.json'):
            theme_name = file[:-5]  # Remove .json extension
            themes.append(theme_name)
    return themes

def load_theme(theme_name="feature_based"):
    """
    Load theme from JSON file in themes directory.
    """
    theme_file = os.path.join(THEMES_DIR, f"{theme_name}.json")
    
    if not os.path.exists(theme_file):
        print(f"⚠ File tema '{theme_file}' tidak ditemukan. Menggunakan tema default feature_based.")
        # Fallback to embedded default theme
        return {
            "name": "Feature-Based Shading",
            "bg": "#FFFFFF",
            "text": "#000000",
            "gradient_color": "#FFFFFF",
            "water": "#C0C0C0",
            "parks": "#F0F0F0",
            "road_motorway": "#0A0A0A",
            "road_primary": "#1A1A1A",
            "road_secondary": "#2A2A2A",
            "road_tertiary": "#3A3A3A",
            "road_residential": "#4A4A4A",
            "road_default": "#3A3A3A"
        }
    
    with open(theme_file, 'r') as f:
        theme = json.load(f)
        print(f"✓ Tema dimuat: {theme.get('name', theme_name)}")
        if 'description' in theme:
            print(f"  {theme['description']}")
        return theme

# Load theme (can be changed via command line or input)
THEME = None  # Will be loaded later

def create_gradient_fade(ax, color, location='bottom', zorder=10):
    """
    Creates a fade effect at the top or bottom of the map.
    """
    vals = np.linspace(0, 1, 256).reshape(-1, 1)
    gradient = np.hstack((vals, vals))
    
    rgb = mcolors.to_rgb(color)
    my_colors = np.zeros((256, 4))
    my_colors[:, 0] = rgb[0]
    my_colors[:, 1] = rgb[1]
    my_colors[:, 2] = rgb[2]
    
    if location == 'bottom':
        my_colors[:, 3] = np.linspace(1, 0, 256)
        extent_y_start = 0
        extent_y_end = 0.25
    else:
        my_colors[:, 3] = np.linspace(0, 1, 256)
        extent_y_start = 0.75
        extent_y_end = 1.0

    custom_cmap = mcolors.ListedColormap(my_colors)
    
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    y_range = ylim[1] - ylim[0]
    
    y_bottom = ylim[0] + y_range * extent_y_start
    y_top = ylim[0] + y_range * extent_y_end
    
    ax.imshow(gradient, extent=[xlim[0], xlim[1], y_bottom, y_top], 
              aspect='auto', cmap=custom_cmap, zorder=zorder, origin='lower')

def get_edge_colors_by_type(G):
    """
    Assigns colors to edges based on road type hierarchy.
    Returns a list of colors corresponding to each edge in the graph.
    """
    if G is None:
        raise ValueError("Graph tidak tersedia untuk pewarnaan jalan.")
    edge_colors = []
    
    for u, v, data in G.edges(data=True):
        # Get the highway type (can be a list or string)
        highway = data.get('highway', 'unclassified')
        
        # Handle list of highway types (take the first one)
        if isinstance(highway, list):
            highway = highway[0] if highway else 'unclassified'
        
        # Assign color based on road type
        if highway in ['motorway', 'motorway_link']:
            color = THEME['road_motorway']
        elif highway in ['trunk', 'trunk_link', 'primary', 'primary_link']:
            color = THEME['road_primary']
        elif highway in ['secondary', 'secondary_link']:
            color = THEME['road_secondary']
        elif highway in ['tertiary', 'tertiary_link']:
            color = THEME['road_tertiary']
        elif highway in ['residential', 'living_street', 'unclassified']:
            color = THEME['road_residential']
        else:
            color = THEME['road_default']
        
        edge_colors.append(color)
    
    return edge_colors

def get_edge_widths_by_type(G):
    """
    Assigns line widths to edges based on road type.
    Major roads get thicker lines.
    """
    if G is None:
        raise ValueError("Graph tidak tersedia untuk lebar jalan.")
    edge_widths = []
    
    for u, v, data in G.edges(data=True):
        highway = data.get('highway', 'unclassified')
        
        if isinstance(highway, list):
            highway = highway[0] if highway else 'unclassified'
        
        # Assign width based on road importance
        if highway in ['motorway', 'motorway_link']:
            width = 1.2
        elif highway in ['trunk', 'trunk_link', 'primary', 'primary_link']:
            width = 1.0
        elif highway in ['secondary', 'secondary_link']:
            width = 0.8
        elif highway in ['tertiary', 'tertiary_link']:
            width = 0.6
        else:
            width = 0.4
        
        edge_widths.append(width)
    
    return edge_widths

def get_coordinates(city, country):
    """
    Fetches coordinates for a given city and country using geopy.
    Includes rate limiting to be respectful to the geocoding service.
    """
    coords = f"coords_{city.lower()}_{country.lower()}"
    cached = cache_get(coords)
    if cached:
        print(f"✓ Menggunakan koordinat cache untuk {city}, {country}")
        return cached

    print("Mencari koordinat...")
    geolocator = Nominatim(user_agent="city_map_poster", timeout=10)
    
    # Reduce delay for faster processing (Nominatim still respects rate limits)
    time.sleep(0.5)
    
    location = geolocator.geocode(f"{city}, {country}")
    
    if location:
        print(f"✓ Ditemukan: {location.address}")
        print(f"✓ Koordinat: {location.latitude}, {location.longitude}")
        try:
            cache_set(coords, (location.latitude, location.longitude))
        except CacheError as e:
            print(e)
        return (location.latitude, location.longitude)
    else:
        raise ValueError(f"Could not find coordinates for {city}, {country}")

def fetch_graph(point, dist, cache_cb=None):
    lat, lon = point
    graph = f"graph_{lat}_{lon}_{dist}_{OSM_NETWORK_TYPE}"
    cached = cache_get(graph)
    if cached is not None:
        print("✓ Menggunakan jaringan jalan cache")
        _report_cache(cache_cb, "streets", True)
        return cached
    _report_cache(cache_cb, "streets", False)

    try:
        G = ox.graph_from_point(point, dist=dist, dist_type='bbox', network_type=OSM_NETWORK_TYPE)
        if G is None or len(G) == 0:
            print(f"Warning: Empty graph returned for point {point}")
            return None
        # Rate limit between requests
        time.sleep(0.3)
        try:
            cache_set(graph, G)
        except CacheError as e:
            print(e)
        return G
    except Exception as e:
        print(f"Error OSMnx saat mengambil graph: {e}")
        return None

def fetch_features(point, dist, tags, name, cache_cb=None):
    lat, lon = point
    tag_str = "_".join(tags.keys())
    features = f"{name}_{lat}_{lon}_{dist}_{tag_str}"
    cached = cache_get(features)
    if cached is not None:
        print(f"✓ Menggunakan cache {name}")
        _report_cache(cache_cb, name, True)
        return cached
    _report_cache(cache_cb, name, False)

    try:
        data = ox.features_from_point(point, tags=tags, dist=dist)
        # Return None if no features found instead of empty GeoDataFrame
        if data is None or data.empty:
            print(f"No {name} features found")
            return None
        # Rate limit between requests
        time.sleep(0.2)
        try:
            cache_set(features, data)
        except CacheError as e:
            print(e)
        return data
    except Exception as e:
        print(f"Error OSMnx saat mengambil fitur {name}: {e}")
        return None

def fetch_subdistrict_boundary(subdistrict_name):
    """
    Fetch the boundary polygon for a given subdistrict name.
    """
    boundary_key = f"boundary_{subdistrict_name.replace(' ', '_').replace(',', '')}"
    cached = cache_get(boundary_key)
    if cached is not None:
        print("✓ Menggunakan batas kecamatan cache")
        return cached

    try:
        # Geocode the subdistrict to get its boundary
        gdf = ox.geocode_to_gdf(subdistrict_name)
        if gdf.empty:
            print(f"⚠ Tidak dapat menemukan batas untuk '{subdistrict_name}'")
            return None
        # Rate limit (reduced for faster processing)
        time.sleep(0.2)
        try:
            cache_set(boundary_key, gdf)
        except CacheError as e:
            print(e)
        return gdf
    except Exception as e:
        print(f"Error OSMnx saat mengambil batas kecamatan: {e}")
        return None

def fetch_city_boundary(city_name):
    """
    Fetch the boundary polygon for a given city name.
    """
    boundary_key = f"boundary_city_{city_name.replace(' ', '_').replace(',', '')}"
    cached = cache_get(boundary_key)
    if cached is not None:
        print("✓ Menggunakan batas kota cache")
        return cached

    try:
        # Geocode the city to get its boundary
        gdf = ox.geocode_to_gdf(city_name)
        if gdf.empty:
            print(f"⚠ Tidak dapat menemukan batas untuk '{city_name}'")
            return None
        # Rate limit (reduced for faster processing)
        time.sleep(0.2)
        try:
            cache_set(boundary_key, gdf)
        except CacheError as e:
            print(e)
        return gdf
    except Exception as e:
        print(f"Error OSMnx saat mengambil batas kota: {e}")
        return None

def fetch_graph_from_polygon(boundary, cache_cb=None):
    """
    Fetch street network within a polygon boundary.
    """
    # Create a cache key based on boundary geometry
    boundary_key = f"graph_polygon_{hash(str(boundary.geometry.iloc[0]))}_{OSM_NETWORK_TYPE}"
    cached = cache_get(boundary_key)
    if cached is not None:
        print("✓ Menggunakan jaringan jalan cache untuk polygon")
        _report_cache(cache_cb, "streets", True)
        return cached
    _report_cache(cache_cb, "streets", False)

    try:
        G = ox.graph_from_polygon(boundary.geometry.iloc[0], network_type=OSM_NETWORK_TYPE)
        time.sleep(0.2)
        try:
            cache_set(boundary_key, G)
        except CacheError as e:
            print(e)
        return G
    except Exception as e:
        print(f"Error OSMnx saat mengambil graph dari polygon: {e}")
        return None

def fetch_features_from_polygon(boundary, tags, name, cache_cb=None):
    """
    Fetch features within a polygon boundary.
    """
    tag_str = "_".join(tags.keys())
    boundary_key = f"{name}_polygon_{hash(str(boundary.geometry.iloc[0]))}_{tag_str}"
    cached = cache_get(boundary_key)
    if cached is not None:
        print(f"✓ Menggunakan cache {name} untuk polygon")
        _report_cache(cache_cb, name, True)
        return cached
    _report_cache(cache_cb, name, False)

    try:
        data = ox.features_from_polygon(boundary.geometry.iloc[0], tags=tags)
        time.sleep(0.15)
        try:
            cache_set(boundary_key, data)
        except CacheError as e:
            print(e)
        return data
    except Exception as e:
        print(f"Error OSMnx saat mengambil fitur dari polygon: {e}")
        return None

def build_canvas_boundary(point, dist, width_inches, height_inches):
    """
    Build a rectangular boundary that matches the canvas aspect ratio,
    centered on the point, so the map fills the page without stretching.
    """
    if point is None or dist is None:
        return None
    if width_inches <= 0 or height_inches <= 0:
        return None

    target_aspect = width_inches / height_inches
    if target_aspect <= 0:
        return None

    # Use dist as half-size for the shorter side, expand the longer side.
    if target_aspect >= 1:
        half_width = dist * target_aspect
        half_height = dist
    else:
        half_width = dist
        half_height = dist / target_aspect

    # Project point to meters, build rectangle, then reproject to lat/lon
    center = Point(point[1], point[0])  # lon, lat
    center_proj, proj_crs = ox.projection.project_geometry(center)
    rect = box(
        center_proj.x - half_width,
        center_proj.y - half_height,
        center_proj.x + half_width,
        center_proj.y + half_height
    )
    rect_gdf = gpd.GeoDataFrame(geometry=[rect], crs=proj_crs).to_crs(epsg=4326)
    return rect_gdf

def project_gdf_safe(gdf):
    """
    Project GeoDataFrame to a suitable planar CRS.
    Compatible across osmnx versions.
    """
    if gdf is None or gdf.empty:
        return gdf
    try:
        if hasattr(ox, "project_gdf"):
            return ox.project_gdf(gdf)
        proj_mod = getattr(ox, "projection", None)
        if proj_mod and hasattr(proj_mod, "project_gdf"):
            return proj_mod.project_gdf(gdf)
        if proj_mod and hasattr(proj_mod, "get_utm_crs"):
            geom = gdf.unary_union
            centroid = geom.centroid
            crs = proj_mod.get_utm_crs(centroid.y, centroid.x)
            return gdf.to_crs(crs)
        if proj_mod and hasattr(proj_mod, "get_projected_crs"):
            geom = gdf.unary_union
            centroid = geom.centroid
            crs = proj_mod.get_projected_crs(centroid.y, centroid.x)
            return gdf.to_crs(crs)
    except Exception:
        pass
    return gdf

def create_poster(city, country, point, dist, output_file, output_format, boundary=None, width_cm=30.48, height_cm=40.64, clean=False, show_boundary_edge=True, progress_cb=None, dpi=None, quality=None, cache_cb=None, transparent_bg=False):
    print(f"\nMembuat peta untuk {city}, {country}...")

    def report(status, message):
        if progress_cb:
            try:
                progress_cb(status, message)
            except Exception:
                pass
    
    # Convert cm to inches (1 inch = 2.54 cm)
    width_inches = width_cm / 2.54
    height_inches = height_cm / 2.54
    print(f"Ukuran poster: {width_cm} cm x {height_cm} cm ({width_inches:.2f} inci x {height_inches:.2f} inci)")
    
    # Build a boundary matching canvas aspect ratio to fill the page (non-stretch)
    fetch_boundary = boundary
    plot_boundary = boundary
    if boundary is None and point is not None and dist is not None:
        fetch_boundary = build_canvas_boundary(point, dist, width_inches, height_inches)

    # Progress bar for data fetching
    with tqdm(total=3, desc="Mengambil data peta", unit="step", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
        # 1. Fetch Street Network (largest payload first)
        pbar.set_description("Mengunduh jaringan jalan")
        report("fetching_streets", "Mengunduh jaringan jalan...")
        if fetch_boundary is not None:
            # Use boundary polygon
            G = fetch_graph_from_polygon(fetch_boundary, cache_cb=cache_cb)
        else:
            G = fetch_graph(point, dist, cache_cb=cache_cb)
        pbar.update(1)

        # 2-3. Fetch Water & Parks in parallel to reduce total wait time
        pbar.set_description("Mengunduh fitur air & taman")
        with ThreadPoolExecutor(max_workers=2) as executor:
            report("fetching_water", "Mengunduh fitur air...")
            if fetch_boundary is not None:
                water_future = executor.submit(
                    fetch_features_from_polygon,
                    fetch_boundary,
                    {'natural': 'water', 'waterway': 'riverbank'},
                    'water',
                    cache_cb
                )
            else:
                water_future = executor.submit(
                    fetch_features,
                    point,
                    dist,
                    {'natural': 'water', 'waterway': 'riverbank'},
                    'water',
                    cache_cb
                )

            report("fetching_parks", "Mengunduh taman dan ruang hijau...")
            if fetch_boundary is not None:
                parks_future = executor.submit(
                    fetch_features_from_polygon,
                    fetch_boundary,
                    {'leisure': 'park', 'landuse': 'grass'},
                    'parks',
                    cache_cb
                )
            else:
                parks_future = executor.submit(
                    fetch_features,
                    point,
                    dist,
                    {'leisure': 'park', 'landuse': 'grass'},
                    'parks',
                    cache_cb
                )

            water = water_future.result()
            pbar.update(1)
            parks = parks_future.result()
            pbar.update(1)
    
    if G is None:
        raise ValueError("Gagal mengambil jaringan jalan (hasil kosong). Coba kurangi skala atau lokasi lain.")

    print("✓ Semua data berhasil diambil!")

    display_point = point
    if display_point is None and plot_boundary is not None and not plot_boundary.empty:
        try:
            boundary_wgs84 = plot_boundary
            if boundary_wgs84.crs is not None and boundary_wgs84.crs.to_epsg() != 4326:
                boundary_wgs84 = boundary_wgs84.to_crs(epsg=4326)
            centroid = boundary_wgs84.geometry.iloc[0].centroid
            display_point = (centroid.y, centroid.x)
        except Exception as e:
            print(f"Warning: Failed to compute centroid for coordinates: {e}")
    
    # Project layers to a common CRS to avoid stretching
    projected_crs = None
    boundary_for_projection = fetch_boundary if fetch_boundary is not None else plot_boundary
    if boundary_for_projection is not None and not boundary_for_projection.empty:
        boundary_for_projection = project_gdf_safe(boundary_for_projection)
        projected_crs = boundary_for_projection.crs
        if plot_boundary is not None and not plot_boundary.empty:
            try:
                plot_boundary = plot_boundary.to_crs(projected_crs)
            except Exception as e:
                print(f"Warning: Failed to project boundary for plotting: {e}")
        try:
            G = ox.project_graph(G, to_crs=projected_crs)
        except Exception as e:
            print(f"Warning: Failed to project graph to boundary CRS: {e}")
    else:
        try:
            G = ox.project_graph(G)
            projected_crs = G.graph.get("crs")
        except Exception as e:
            print(f"Warning: Failed to project graph: {e}")

    if projected_crs is not None:
        if water is not None and not water.empty:
            try:
                water = water.to_crs(projected_crs)
            except Exception as e:
                print(f"Warning: Failed to project water features: {e}")
        if parks is not None and not parks.empty:
            try:
                parks = parks.to_crs(projected_crs)
            except Exception as e:
                print(f"Warning: Failed to project parks features: {e}")

    # 2. Setup Plot with optimized settings
    print("Merender peta...")
    report("render_setup", "Menyiapkan kanvas render...")
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend for faster rendering
    # Use configurable DPI to balance speed vs quality
    render_dpi = dpi if isinstance(dpi, (int, float)) and dpi > 0 else 150
    fig_face = 'none' if transparent_bg else THEME['bg']
    fig, ax = plt.subplots(figsize=(width_inches, height_inches), facecolor=fig_face, dpi=render_dpi)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_facecolor(fig_face)
    ax.set_position([0, 0, 1, 1])
    ax.axis('off')  # Turn off axes for cleaner look and faster rendering
    # Set aspect ratio BEFORE plotting to prevent stretching
    ax.set_aspect('equal', adjustable='datalim')
    
    # 3. Plot Layers
    # Layer 1: Polygons (filter to only plot polygon/multipolygon geometries, not points)
    report("render_layers_water", "Menggambar layer air...")
    if water is not None and not water.empty:
        # Filter to only polygon/multipolygon geometries to avoid point features showing as dots
        water_polys = water[water.geometry.type.isin(['Polygon', 'MultiPolygon'])]
        if not water_polys.empty:
            water_polys.plot(ax=ax, facecolor=THEME['water'], edgecolor='none', zorder=1)
    
    report("render_layers_parks", "Menggambar layer ruang hijau...")
    if parks is not None and not parks.empty:
        # Filter to only polygon/multipolygon geometries to avoid point features showing as dots
        parks_polys = parks[parks.geometry.type.isin(['Polygon', 'MultiPolygon'])]
        if not parks_polys.empty:
            parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=2)
    
    # Layer 1.5: Subdistrict Boundary (if provided)
    report("render_boundary", "Menggambar garis batas wilayah...")
    if plot_boundary is not None and not plot_boundary.empty and show_boundary_edge:
        # Use boundary color from theme if available, otherwise use text color
        boundary_color = THEME.get('boundary', THEME.get('text', 'black'))
        plot_boundary.plot(ax=ax, facecolor='none', edgecolor=boundary_color, linewidth=2, zorder=2.5)
    
    # Layer 2: Roads with hierarchy coloring
    print("Menerapkan warna hierarki jalan...")
    report("render_roads", "Menggambar jaringan jalan...")
    edge_colors = get_edge_colors_by_type(G)
    edge_widths = get_edge_widths_by_type(G)
    
    ox.plot_graph(
        G, ax=ax, bgcolor=THEME['bg'],
        node_size=0,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
        show=False, close=False
    )
    
    # Layer 3: Gradients (Top and Bottom) - skip for clean mode
    if not clean:
        report("render_gradients", "Menambahkan efek gradient...")
        create_gradient_fade(ax, THEME['gradient_color'], location='bottom', zorder=10)
        create_gradient_fade(ax, THEME['gradient_color'], location='top', zorder=10)
    
    # 4. Typography using Roboto font
    if not clean:
        report("render_text", "Menambahkan tipografi...")
        # Scale font sizes based on poster width for consistent horizontal balance
        scale_factor = width_inches / 16.0  # Base on 16 inches width
        base_font_size = 60 * scale_factor
        sub_font_size = 22 * scale_factor
        coords_font_size = 14 * scale_factor
        
        if FONTS:
            font_main = FontProperties(fname=FONTS['bold'], size=base_font_size)
            font_top = FontProperties(fname=FONTS['bold'], size=40 * scale_factor)
            font_sub = FontProperties(fname=FONTS['light'], size=sub_font_size)
            font_coords = FontProperties(fname=FONTS['regular'], size=coords_font_size)
        else:
            # Fallback to system fonts
            font_main = FontProperties(family='monospace', weight='bold', size=base_font_size)
            font_top = FontProperties(family='monospace', weight='bold', size=40 * scale_factor)
            font_sub = FontProperties(family='monospace', weight='normal', size=sub_font_size)
            font_coords = FontProperties(family='monospace', size=coords_font_size)
        
        spaced_city = "  ".join(list(city.upper()))
        
        # Dynamically adjust font size based on city name length to prevent truncation
        city_char_count = len(city)
        if city_char_count > 10:
            # Scale down font size for longer names
            name_scale_factor = 10 / city_char_count
            adjusted_font_size = max(base_font_size * name_scale_factor, base_font_size * 0.4)  # Minimum 40% of base
        else:
            adjusted_font_size = base_font_size
        
        if FONTS:
            font_main_adjusted = FontProperties(fname=FONTS['bold'], size=adjusted_font_size)
        else:
            font_main_adjusted = FontProperties(family='monospace', weight='bold', size=adjusted_font_size)

        # --- BOTTOM TEXT ---
        ax.text(0.5, 0.14, spaced_city, transform=ax.transAxes,
                color=THEME['text'], ha='center', fontproperties=font_main_adjusted, zorder=11)
        
        # Only display country if it's not empty
        if country.strip():
            ax.text(0.5, 0.10, country.upper(), transform=ax.transAxes,
                    color=THEME['text'], ha='center', fontproperties=font_sub, zorder=11)
            coords_y = 0.07
        else:
            coords_y = 0.10  # Adjust coordinate position if no country
        
        # Display coordinates (point or centroid when using boundary)
        if display_point is not None:
            lat, lon = display_point
            coords = f"{lat:.4f}° N / {lon:.4f}° E" if lat >= 0 else f"{abs(lat):.4f}° S / {lon:.4f}° E"
            if lon < 0:
                coords = coords.replace("E", "W")
            
            ax.text(0.5, coords_y, coords, transform=ax.transAxes,
                    color=THEME['text'], alpha=0.7, ha='center', fontproperties=font_coords, zorder=11)
            
            # Decorative line position and length scale with poster width
            line_y = 0.125 if country.strip() else 0.105
            line_half = 0.1 * scale_factor
            line_half = max(0.07, min(line_half, 0.2))
            ax.plot([0.5 - line_half, 0.5 + line_half], [line_y, line_y], transform=ax.transAxes,
                    color=THEME['text'], linewidth=1, zorder=11)

        # --- ATTRIBUTION (bottom right) ---
        # Removed OpenStreetMap attribution as requested
        # ax.text(0.98, 0.02, "© OpenStreetMap contributors", transform=ax.transAxes,
        #         color=THEME['text'], alpha=0.5, ha='right', va='bottom', 
        #         fontproperties=font_attr, zorder=11)

    # 5. Save
    print(f"Saving to {output_file}...")
    report("render_save", "Menyimpan hasil poster...")

    fmt = output_format.lower()
    # Expand bounds to match canvas aspect without distorting geometry
    try:
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        x_range = x1 - x0
        y_range = y1 - y0
        if x_range > 0 and y_range > 0:
            data_aspect = x_range / y_range
            target_aspect = width_inches / height_inches
            if data_aspect < target_aspect:
                new_x_range = y_range * target_aspect
                pad = (new_x_range - x_range) / 2
                ax.set_xlim(x0 - pad, x1 + pad)
            elif data_aspect > target_aspect:
                new_y_range = x_range / target_aspect
                pad = (new_y_range - y_range) / 2
                ax.set_ylim(y0 - pad, y1 + pad)
    except Exception:
        pass

    save_face = 'none' if transparent_bg else THEME["bg"]
    save_kwargs = dict(facecolor=save_face, pad_inches=0)

    # Use same DPI as figure for consistent output
    if fmt == "png":
        save_kwargs["dpi"] = render_dpi
        if quality == "lossless":
            # Use PIL kwargs when available (matplotlib compatibility varies)
            save_kwargs["pil_kwargs"] = {"compress_level": 0}
        if transparent_bg:
            save_kwargs["transparent"] = True

    try:
        plt.savefig(output_file, format=fmt, **save_kwargs)
    except TypeError:
        # Fallback for older matplotlib that doesn't support pil_kwargs
        save_kwargs.pop("pil_kwargs", None)
        plt.savefig(output_file, format=fmt, **save_kwargs)

    plt.close()
    print(f"✓ Done! Poster saved as {output_file}")


def print_examples():
    """Print usage examples."""
    print("""
City Map Poster Generator
=========================

Usage:
  python create_map_poster.py --city <city> --country <country> [options]

Examples:
  # Iconic grid patterns
  python create_map_poster.py -c "New York" -C "USA" -t noir -d 12000           # Manhattan grid
  python create_map_poster.py -c "Barcelona" -C "Spain" -t warm_beige -d 8000   # Eixample district grid
  
  # Waterfront & canals
  python create_map_poster.py -c "Venice" -C "Italy" -t blueprint -d 4000       # Canal network
  python create_map_poster.py -c "Amsterdam" -C "Netherlands" -t ocean -d 6000  # Concentric canals
  python create_map_poster.py -c "Dubai" -C "UAE" -t midnight_blue -d 15000     # Palm & coastline
  
  # Radial patterns
  python create_map_poster.py -c "Paris" -C "France" -t pastel_dream -d 10000   # Haussmann boulevards
  python create_map_poster.py -c "Moscow" -C "Russia" -t noir -d 12000          # Ring roads
  
  # Organic old cities
  python create_map_poster.py -c "Tokyo" -C "Japan" -t japanese_ink -d 15000    # Dense organic streets
  python create_map_poster.py -c "Marrakech" -C "Morocco" -t terracotta -d 5000 # Medina maze
  python create_map_poster.py -c "Rome" -C "Italy" -t warm_beige -d 8000        # Ancient street layout
  
  # Coastal cities
  python create_map_poster.py -c "San Francisco" -C "USA" -t sunset -d 10000    # Peninsula grid
  python create_map_poster.py -c "Sydney" -C "Australia" -t ocean -d 12000      # Harbor city
  python create_map_poster.py -c "Mumbai" -C "India" -t contrast_zones -d 18000 # Coastal peninsula
  
  # River cities
  python create_map_poster.py -c "London" -C "UK" -t noir -d 15000              # Thames curves
  python create_map_poster.py -c "Budapest" -C "Hungary" -t copper_patina -d 8000  # Danube split
  
  # List themes
  python create_map_poster.py --list-themes

Options:
  --city, -c        City name (required)
  --country, -C     Country name (required)
  --theme, -t       Theme name (default: feature_based)
  --distance, -d    Map radius in meters (default: 29000)
  --list-themes     List all available themes

Available themes can be found in the 'themes/' directory.
Generated posters are saved to 'posters/' directory.

Target Resolution (px) -> Inches (-W / -H):
  Instagram Post     1080 x 1080  -> 3.6 x 3.6
  Mobile Wallpaper   1080 x 1920  -> 3.6 x 6.4
  HD Wallpaper       1920 x 1080  -> 6.4 x 3.6
  4K Wallpaper       3840 x 2160  -> 12.8 x 7.2
  A4 Print           2480 x 3508  -> 8.3 x 11.7

Distance guide:
  4000-6000m   Small/dense cities (Venice, Amsterdam center)
  8000-12000m  Medium cities, focused downtown (Paris, Barcelona)
  15000-20000m Large metros, full city view (Tokyo, Mumbai)
""")

def list_themes():
    """List all available themes with descriptions."""
    available_themes = get_available_themes()
    if not available_themes:
        print("No themes found in 'themes/' directory.")
        return
    
    print("\nAvailable Themes:")
    print("-" * 60)
    for theme_name in available_themes:
        theme_path = os.path.join(THEMES_DIR, f"{theme_name}.json")
        try:
            with open(theme_path, 'r') as f:
                theme_data = json.load(f)
                display_name = theme_data.get('name', theme_name)
                description = theme_data.get('description', '')
        except:
            display_name = theme_name
            description = ''
        print(f"  {theme_name}")
        print(f"    {display_name}")
        if description:
            print(f"    {description}")
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Buat poster peta yang indah untuk kota mana saja",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python create_map_poster.py --kota "New York" --negara "USA"
  python create_map_poster.py --kota Tokyo --negara Japan --tema midnight_blue
  python create_map_poster.py --kota Paris --negara France --tema noir --skala 15000 --width 50 --height 70
  python create_map_poster.py --kecamatan "Menteng, Jakarta Pusat, Indonesia" --tema feature_based
  python create_map_poster.py --daftar-tema
        """
    )
    
    parser.add_argument('--kota', '-k', type=str, help='Nama kota')
    parser.add_argument('--negara', '-n', type=str, help='Nama negara')
    parser.add_argument('--tema', '-t', type=str, default='feature_based', help='Nama tema (default: feature_based)')
    parser.add_argument('--skala', '-s', type=int, default=29000, help='Skala peta dalam meter (default: 29000)')
    parser.add_argument('--daftar-tema', action='store_true', help='Daftar semua tema yang tersedia')
    parser.add_argument('--format', '-f', default='png', choices=['png', 'svg', 'pdf'],help='Format output untuk poster (default: png)')
    parser.add_argument('--all-themes', action='store_true', help='Generate posters untuk semua tema yang tersedia')
    parser.add_argument('--kecamatan', type=str, help='Nama kecamatan untuk peta berbasis batas (contoh: "Menteng, Jakarta Pusat, Indonesia")')
    parser.add_argument('--width', type=float, default=30.48, help='Lebar poster dalam cm (default: 30.48 cm, sama dengan 12 inci)')
    parser.add_argument('--height', type=float, default=40.64, help='Tinggi poster dalam cm (default: 40.64 cm, sama dengan 16 inci)')
    parser.add_argument('--bersih', action='store_true', help='Buat poster tanpa teks (nama kota, koordinat, dll.)')
    
    args = parser.parse_args()
    
    # If no arguments provided, show examples
    if len(os.sys.argv) == 1:
        print_examples()
        os.sys.exit(0)
    
    # List themes if requested
    if args.daftar_tema:
        list_themes()
        os.sys.exit(0)
    
    # Validate required arguments
    if not args.kecamatan and (not args.kota or not args.negara):
        print("Error: --kecamatan atau kedua --kota dan --negara diperlukan.\n")
        print_examples()
        os.sys.exit(1)
    
    # Validate theme exists (unless all-themes)
    available_themes = get_available_themes()
    if not args.all_themes and args.tema not in available_themes:
        print(f"Error: Tema '{args.tema}' tidak ditemukan.")
        print(f"Tema yang tersedia: {', '.join(available_themes)}")
        os.sys.exit(1)
    
    print("=" * 50)
    print("Generator Poster Peta Kota")
    print("=" * 50)
    
    # Load theme(s)
    theme_list = available_themes if args.all_themes else [args.tema]
    
    # Get coordinates and generate poster
    try:
        boundary = None
        if args.kecamatan:
            print(f"Mengambil batas untuk kecamatan: {args.kecamatan}")
            boundary = fetch_subdistrict_boundary(args.kecamatan)
            if boundary is None:
                print("Error: Tidak dapat mengambil batas kecamatan.")
                os.sys.exit(1)
            # Use subdistrict name for output if provided
            location_name = args.kecamatan
        else:
            location_name = f"{args.kota}, {args.negara}"
            coords = get_coordinates(args.kota, args.negara)

        for theme_name in theme_list:
            THEME = load_theme(theme_name)
            output_file = generate_output_filename(location_name.replace(',', '').replace(' ', '_'), theme_name, args.format)
            if boundary is not None and not boundary.empty:
                create_poster(location_name, "", None, None, output_file, args.format, boundary=boundary, width_cm=args.width, height_cm=args.height, clean=args.bersih)
            else:
                create_poster(args.kota, args.negara, coords, args.skala, output_file, args.format, width_cm=args.width, height_cm=args.height, clean=args.bersih)
        
        print("\n" + "=" * 50)
        print("✓ Pembuatan poster selesai!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        os.sys.exit(1)
