from flask import Flask, request, send_file, render_template, jsonify
import os
import sys
import tempfile
import json
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import zipfile

# Import functions from create_map_poster.py
sys.path.append('.')
from create_map_poster import (
    get_available_themes,
    load_theme,
    generate_output_filename,
    get_coordinates,
    fetch_subdistrict_boundary,
    fetch_city_boundary,
    create_poster,
    fetch_graph,
    fetch_features,
    fetch_graph_from_polygon,
    fetch_features_from_polygon
)

app = Flask(__name__)

# Store temp outputs inside project directory
BASE_DIR = Path(__file__).resolve().parent
TEMP_OUTPUT_DIR = BASE_DIR / "temp_outputs"
TEMP_OUTPUT_DIR.mkdir(exist_ok=True)

# Global variable to track progress
progress_status = {}
progress_lock = threading.Lock()

def _update_progress(task_id, payload):
    with progress_lock:
        current = progress_status.get(task_id, {})
        current.update(payload)
        progress_status[task_id] = current

def _is_cancelled(task_id):
    return progress_status.get(task_id, {}).get('cancelled', False)

def fetch_map_data_parallel(boundary, point, dist, task_id):
    """Fetch map data in parallel for better performance"""
    results = {}
    progress_steps = {
        'fetching_streets': 0,
        'fetching_water': 0,
        'fetching_parks': 0
    }
    cache_hits = {
        'streets': False,
        'water': False,
        'parks': False
    }

    def cache_cb(name, hit):
        if name in cache_hits:
            cache_hits[name] = bool(hit)
        _update_progress(task_id, {'cache_hits': cache_hits})

    def fetch_streets():
        progress_steps['fetching_streets'] = 10
        _update_progress(task_id, {
            'status': 'fetching_streets',
            'message': 'Mengunduh jaringan jalan...',
            'details': progress_steps
        })
        if _is_cancelled(task_id):
            return None
        if boundary is not None:
            return fetch_graph_from_polygon(boundary, cache_cb=cache_cb)
        else:
            return fetch_graph(point, dist, cache_cb=cache_cb)

    def fetch_water():
        progress_steps['fetching_water'] = 10
        _update_progress(task_id, {
            'status': 'fetching_water',
            'message': 'Mengunduh fitur air...',
            'details': progress_steps
        })
        if _is_cancelled(task_id):
            return None
        try:
            if boundary is not None and not boundary.empty:
                return fetch_features_from_polygon(boundary, {'natural': 'water', 'waterway': 'riverbank'}, 'water', cache_cb=cache_cb)
            else:
                return fetch_features(point, dist, {'natural': 'water', 'waterway': 'riverbank'}, 'water', cache_cb=cache_cb)
        except Exception as e:
            print(f"Warning: Failed to fetch water: {e}")
            return None

    def fetch_parks():
        progress_steps['fetching_parks'] = 10
        _update_progress(task_id, {
            'status': 'fetching_parks',
            'message': 'Mengunduh taman dan ruang hijau...',
            'details': progress_steps
        })
        if _is_cancelled(task_id):
            return None
        try:
            if boundary is not None and not boundary.empty:
                return fetch_features_from_polygon(boundary, {'leisure': 'park', 'landuse': 'grass'}, 'parks', cache_cb=cache_cb)
            else:
                return fetch_features(point, dist, {'leisure': 'park', 'landuse': 'grass'}, 'parks', cache_cb=cache_cb)
        except Exception as e:
            print(f"Warning: Failed to fetch parks: {e}")
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all tasks
        future_streets = executor.submit(fetch_streets)
        future_water = executor.submit(fetch_water)
        future_parks = executor.submit(fetch_parks)

        # Collect results as they complete
        results['G'] = future_streets.result()
        results['water'] = future_water.result()
        results['parks'] = future_parks.result()

    # Mark each fetch as complete
    progress_steps['fetching_streets'] = 100
    progress_steps['fetching_water'] = 100
    progress_steps['fetching_parks'] = 100
    _update_progress(task_id, {
        'status': 'fetching_data',
        'message': 'Semua data berhasil diambil',
        'details': progress_steps
    })

    # Validate results
    if results['G'] is None:
        raise ValueError("Failed to fetch street network data")

    return results

def create_poster_parallel(city, country, point, dist, output_file, output_format, boundary=None, width_cm=30.48, height_cm=40.64, clean=False, task_id=None, dpi=None):
    """Parallel version of create_poster for better performance"""
    try:
        print(f"\nMembuat peta untuk {city}, {country}...")

        # Convert cm to inches (1 inch = 2.54 cm)
        width_inches = width_cm / 2.54
        height_inches = height_cm / 2.54
        print(f"Ukuran poster: {width_cm} cm x {height_cm} cm ({width_inches:.2f} inci x {height_inches:.2f} inci)")

        # Validate inputs
        if point is None and boundary is None:
            raise ValueError("Either point coordinates or boundary must be provided")
        if point is not None and (not isinstance(point, (list, tuple)) or len(point) < 2):
            raise ValueError(f"Invalid point format: {point}")

        print(f"Input validation passed. Point: {point}, Boundary: {boundary is not None}")

        # Fetch all map data in parallel
        print("Mengunduh data peta secara paralel...")
        map_data = fetch_map_data_parallel(boundary, point, dist, task_id)
        G = map_data['G']
        water = map_data['water']
        parks = map_data['parks']

        # Validate fetched data
        if G is None:
            raise ValueError("Failed to fetch street network data")

        print("✓ Semua data berhasil diambil!")

        # Continue with the rest of create_poster logic
        print("Merender peta...")

        # Import matplotlib here to avoid issues
        import matplotlib.pyplot as plt
        from create_map_poster import THEME, ox, get_edge_colors_by_type, get_edge_widths_by_type

        # Validate THEME
        if THEME is None:
            raise ValueError("Theme not loaded properly")
        print(f"Using theme: {THEME.get('name', 'Unknown')}")

        display_point = point
        if display_point is None and boundary is not None and not boundary.empty:
            try:
                boundary_wgs84 = boundary
                if boundary_wgs84.crs is not None and boundary_wgs84.crs.to_epsg() != 4326:
                    boundary_wgs84 = boundary_wgs84.to_crs(epsg=4326)
                centroid = boundary_wgs84.geometry.iloc[0].centroid
                display_point = (centroid.y, centroid.x)
            except Exception as e:
                print(f"Warning: Failed to compute centroid for coordinates: {e}")

        projected_crs = None
        if boundary is not None and not boundary.empty:
            boundary = ox.project_gdf(boundary)
            projected_crs = boundary.crs
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

        render_dpi = dpi if isinstance(dpi, (int, float)) and dpi > 0 else 150
        fig, ax = plt.subplots(figsize=(width_inches, height_inches), facecolor=THEME['bg'], dpi=render_dpi)
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        ax.set_facecolor(THEME['bg'])
        ax.set_position([0, 0, 1, 1])
        ax.set_aspect('equal', adjustable='datalim')

        # Plot layers
        if water is not None and not water.empty:
            water_polys = water[water.geometry.type.isin(['Polygon', 'MultiPolygon'])]
            if not water_polys.empty:
                water_polys.plot(ax=ax, facecolor=THEME['water'], edgecolor='none', zorder=1)

        if parks is not None and not parks.empty:
            parks_polys = parks[parks.geometry.type.isin(['Polygon', 'MultiPolygon'])]
            if not parks_polys.empty:
                parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=2)

        if boundary is not None:
            boundary.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=2, zorder=2.5)

        if G is None:
            raise ValueError("Gagal mengambil jaringan jalan (hasil kosong).")

        print("Menerapkan warna hierarki jalan...")
        edge_colors = get_edge_colors_by_type(G)
        edge_widths = get_edge_widths_by_type(G)

        # Validate edge colors and widths
        if edge_colors is None or edge_widths is None:
            raise ValueError("Failed to generate edge colors or widths")

        ox.plot_graph(
            G, ax=ax, bgcolor=THEME['bg'],
            node_size=0,
            edge_color=edge_colors,
            edge_linewidth=edge_widths,
            show=False
        )

        # Add text if not clean
        if not clean:
            # Add title and location text
            ax.text(0.02, 0.98, f"{city.upper()}", transform=ax.transAxes,
                    fontsize=24, fontweight='bold', color=THEME['text'],
                    verticalalignment='top', family='sans-serif')

            ax.text(0.02, 0.02, f"{country.upper()}", transform=ax.transAxes,
                    fontsize=16, color=THEME['text'],
                    verticalalignment='bottom', family='sans-serif')

            # Add coordinates if available
            if display_point and len(display_point) >= 2:
                ax.text(0.98, 0.02, f"{display_point[0]:.4f}, {display_point[1]:.4f}", transform=ax.transAxes,
                        fontsize=10, color=THEME['text'],
                        verticalalignment='bottom', horizontalalignment='right', family='sans-serif')

        # Remove axes
        ax.set_axis_off()

        # Save the figure
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

        plt.savefig(output_file, dpi=render_dpi, facecolor=THEME['bg'], pad_inches=0)
        plt.close(fig)

        print(f"✓ Poster disimpan ke: {output_file}")

    except Exception as e:
        print(f"Error in create_poster_parallel: {str(e)}")
        raise

def create_poster_async(task_id, data):
    """Create poster in a separate thread with progress updates"""
    try:
        _update_progress(task_id, {
            'status': 'starting',
            'message': 'Memulai pembuatan poster...',
            'started_at': time.time(),
            'cancelled': False,
            'cache_hits': {}
        })

        # Extract parameters
        kota = data.get('kota')
        negara = data.get('negara')
        kecamatan = data.get('kecamatan')
        use_coordinates = data.get('use_coordinates', False)
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        custom_city = data.get('custom_city', '')
        custom_country = data.get('custom_country', '')
        transparent_bg = data.get('transparent_bg', False)
        tema = data.get('tema', 'feature_based')
        custom_theme = data.get('custom_theme')  # Custom theme data
        skala = int(data.get('skala', 29000))
        format_output = data.get('format', 'png')
        quality = data.get('quality', 'medium')
        dpi = data.get('dpi')
        width = float(data.get('width', 30.48))
        height = float(data.get('height', 40.64))
        unit = data.get('unit', 'cm')  # 'cm', 'mm', or 'px'
        use_delineation = data.get('use_delineation', False)
        show_boundary_edge = data.get('show_boundary_edge', True)
        clean = data.get('clean', False)
        all_themes = data.get('all_themes', False)

        # Convert units to cm
        if unit == 'mm':
            width = width / 10
            height = height / 10
        elif unit == 'px':
            # Assume 300 DPI for pixel to cm conversion
            conversion_dpi = 300
            width = (width / conversion_dpi) * 2.54
            height = (height / conversion_dpi) * 2.54

        # Resolve DPI from quality or explicit value
        if dpi is None:
            quality_map = {
                'low': 100,
                'medium': 150,
                'high': 300,
                'ultra': 600,
                'lossless': 600
            }
            dpi = quality_map.get(quality, 150)
        try:
            dpi = int(dpi)
        except (TypeError, ValueError):
            dpi = 150
        dpi = max(72, min(dpi, 1200))

        _update_progress(task_id, {'status': 'validating', 'message': 'Memvalidasi input...'})

        # Validate theme
        available_themes = get_available_themes()
        if tema != 'custom' and tema not in available_themes:
            _update_progress(task_id, {'status': 'error', 'message': f'Tema "{tema}" tidak ditemukan'})
            return

        # Validate required parameters
        if use_coordinates:
            if latitude is None or longitude is None:
                _update_progress(task_id, {'status': 'error', 'message': 'Latitude dan longitude wajib diisi'})
                return
        elif not kecamatan and not negara:
            _update_progress(task_id, {'status': 'error', 'message': 'Isi kecamatan, atau kota + negara, atau negara saja'})
            return

        _update_progress(task_id, {'status': 'loading_theme', 'message': 'Memuat tema...'})

        # Load theme and set global THEME
        import create_map_poster
        theme_list = available_themes if all_themes and tema != 'custom' else [tema]
        if tema == 'custom':
            theme_list = ['custom']

        # Get coordinates or boundary
        boundary = None
        location_name = ""
        location_country = ""
        coords = None

        if use_coordinates:
            coords = (float(latitude), float(longitude))
            location_name = custom_city or "Lokasi Kustom"
            location_country = custom_country or ""
        elif kecamatan:
            _update_progress(task_id, {'status': 'fetching_boundary', 'message': f'Mengambil batas untuk kecamatan: {kecamatan}'})
            boundary = fetch_subdistrict_boundary(kecamatan)
            if boundary is None or boundary.empty:
                _update_progress(task_id, {'status': 'error', 'message': 'Tidak dapat mengambil batas kecamatan. Pastikan nama kecamatan lengkap dengan kota dan negara.'})
                return
            location_name = kecamatan
            location_country = ""
        elif use_delineation and kota and negara:
            # Try to get boundary for city
            _update_progress(task_id, {'status': 'fetching_boundary', 'message': f'Mengambil batas untuk {kota}, {negara}'})
            boundary = fetch_city_boundary(f"{kota}, {negara}")
            if boundary is None or boundary.empty:
                _update_progress(task_id, {'status': 'error', 'message': f'Tidak dapat menemukan batas untuk {kota}, {negara}. Coba gunakan radius biasa.'})
                return
            location_name = f"{kota}, {negara}"
            location_country = negara
        elif not kota and negara:
            _update_progress(task_id, {'status': 'fetching_boundary', 'message': f'Mengambil batas untuk {negara}'})
            boundary = fetch_city_boundary(negara)
            if boundary is None or boundary.empty:
                _update_progress(task_id, {'status': 'error', 'message': f'Tidak dapat menemukan batas untuk {negara}.'})
                return
            location_name = negara
            location_country = negara
        else:
            _update_progress(task_id, {'status': 'geocoding', 'message': f'Mencari koordinat untuk {kota}, {negara}'})
            coords = get_coordinates(kota, negara)
            if coords is None:
                _update_progress(task_id, {'status': 'error', 'message': f'Tidak dapat menemukan koordinat untuk {kota}, {negara}. Pastikan nama kota dan negara benar.'})
                return
            location_name = f"{kota}, {negara}"
            location_country = negara or ""
            location_country = negara or ""

        _update_progress(task_id, {'status': 'fetching_data', 'message': 'Mengunduh data peta...'})

        # Prepare output file(s)
        output_file = None
        output_files = []

        try:
            # Use original poster creation function
            def report(status, message):
                if _is_cancelled(task_id):
                    raise RuntimeError("cancelled")
                _update_progress(task_id, {'status': status, 'message': message})
            def cache_cb(name, hit):
                cache_hits = progress_status.get(task_id, {}).get('cache_hits', {})
                cache_hits[name] = bool(hit)
                _update_progress(task_id, {'cache_hits': cache_hits})

            if boundary is not None and not boundary.empty:
                # For delineation, pass location_name as both city and country for consistent display
                # Split location_name to use for display
                display_city = location_name.split(',')[0].strip() if ',' in location_name else location_name
                display_country = ', '.join(location_name.split(',')[1:]).strip() if ',' in location_name else ""
                for theme_name in theme_list:
                    theme_data = custom_theme if theme_name == 'custom' else load_theme(theme_name)
                    if theme_data is None:
                        _update_progress(task_id, {'status': 'error', 'message': f'Gagal memuat tema "{theme_name}"'})
                        return
                    create_map_poster.THEME = theme_data
                    with tempfile.NamedTemporaryFile(suffix=f'.{format_output}', delete=False, dir=TEMP_OUTPUT_DIR) as tmp_file:
                        output_file = tmp_file.name
                    output_files.append({'file': output_file, 'theme': theme_name, 'format': format_output})
                    create_poster(display_city, display_country, None, None, output_file, format_output,
                                boundary=boundary, width_cm=width, height_cm=height, clean=clean,
                                show_boundary_edge=show_boundary_edge, progress_cb=report, dpi=dpi, quality=quality,
                                cache_cb=cache_cb, transparent_bg=transparent_bg)
            else:
                city_label = custom_city if use_coordinates and custom_city else kota
                country_label = custom_country if use_coordinates and custom_country else location_country
                for theme_name in theme_list:
                    theme_data = custom_theme if theme_name == 'custom' else load_theme(theme_name)
                    if theme_data is None:
                        _update_progress(task_id, {'status': 'error', 'message': f'Gagal memuat tema "{theme_name}"'})
                        return
                    create_map_poster.THEME = theme_data
                    with tempfile.NamedTemporaryFile(suffix=f'.{format_output}', delete=False, dir=TEMP_OUTPUT_DIR) as tmp_file:
                        output_file = tmp_file.name
                    output_files.append({'file': output_file, 'theme': theme_name, 'format': format_output})
                    create_poster(city_label or "LOKASI", country_label or "", coords, skala, output_file, format_output,
                                width_cm=width, height_cm=height, clean=clean, progress_cb=report, dpi=dpi, quality=quality,
                                cache_cb=cache_cb, transparent_bg=transparent_bg)

            if output_files:
                _update_progress(task_id, {'status': 'completed', 'message': 'Poster berhasil dibuat!', 'files': output_files})
            else:
                _update_progress(task_id, {'status': 'completed', 'message': 'Poster berhasil dibuat!', 'file': output_file})

        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(output_file):
                os.unlink(output_file)
            if str(e) == 'cancelled':
                _update_progress(task_id, {'status': 'error', 'message': 'Dibatalkan oleh pengguna'})
            else:
                _update_progress(task_id, {'status': 'error', 'message': f'Error saat membuat poster: {str(e)}'})

    except Exception as e:
        msg = 'Dibatalkan oleh pengguna' if str(e) == 'cancelled' else f'Error tidak terduga: {str(e)}'
        _update_progress(task_id, {'status': 'error', 'message': msg})

@app.route('/')
def index():
    """Serve the main page"""
    themes = get_available_themes()
    return render_template('index.html', themes=themes)

@app.route('/api/themes')
def api_themes():
    """API endpoint to get available themes"""
    themes = get_available_themes()
    return jsonify({'themes': themes})

@app.route('/api/create_poster', methods=['POST'])
def api_create_poster():
    """API endpoint to create a poster"""
    try:
        data = request.json
        task_id = str(hash(str(data) + str(time.time())))  # Simple unique ID

        # Start poster creation in background thread
        thread = threading.Thread(target=create_poster_async, args=(task_id, data))
        thread.daemon = True
        thread.start()

        return jsonify({'task_id': task_id, 'status': 'started'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    """Get progress status for a task"""
    if task_id in progress_status:
        status = progress_status[task_id].copy()
        status_percent_map = {
            'starting': 5,
            'validating': 10,
            'loading_theme': 15,
            'fetching_data': 20,
            'fetching_boundary': 25,
            'geocoding': 25,
            'fetching_streets': 35,
            'fetching_water': 45,
            'fetching_parks': 55,
            'render_setup': 60,
            'render_layers_water': 65,
            'render_layers_parks': 70,
            'render_boundary': 75,
            'render_roads': 85,
            'render_gradients': 90,
            'render_text': 95,
            'render_save': 97,
            'completed': 100
        }
        status['percent'] = status_percent_map.get(status.get('status'), status.get('percent'))
        started_at = status.get('started_at')
        if started_at:
            elapsed = max(0, time.time() - started_at)
            status['elapsed_seconds'] = elapsed
            percent = status.get('percent')
            if isinstance(percent, (int, float)) and percent > 0:
                remaining = elapsed * (100 / percent - 1)
                status['eta_seconds'] = max(0, remaining)
        if status.get('status') == 'completed':
            # Don't include file path in response for security
            status.pop('file', None)
            if status.get('files'):
                status['files'] = [
                    {'index': idx, 'theme': f.get('theme'), 'format': f.get('format', 'png')}
                    for idx, f in enumerate(status.get('files', []))
                ]
        return jsonify(status)
    return jsonify({'status': 'not_found'})

@app.route('/api/cancel/<task_id>', methods=['POST'])
def api_cancel(task_id):
    if task_id in progress_status:
        _update_progress(task_id, {'cancelled': True})
        return jsonify({'status': 'cancelling'})
    return jsonify({'status': 'not_found'}), 404

@app.route('/api/download/<task_id>')
def api_download(task_id):
    """Download completed poster"""
    if task_id in progress_status:
        status = progress_status[task_id]
        if status.get('status') == 'completed':
            file_path = None
            theme_name = None
            files = status.get('files')
            if files:
                try:
                    index = int(request.args.get('index', 0))
                except ValueError:
                    index = 0
                index = max(0, min(index, len(files) - 1))
                file_path = files[index].get('file')
                theme_name = files[index].get('theme')
            else:
                file_path = status.get('file')

            if file_path and os.path.exists(file_path):
                # Determine filename
                data = request.args.get('data', '{}')
                try:
                    data = json.loads(data)
                    if data.get('kecamatan'):
                        location_name = data.get('kecamatan')
                    elif data.get('custom_city'):
                        location_name = data.get('custom_city')
                    elif data.get('kota') and data.get('negara'):
                        location_name = f"{data.get('kota')}, {data.get('negara')}"
                    else:
                        location_name = data.get('negara') or "poster"
                    format_output = data.get('format', 'png')
                    theme_suffix = f"_{theme_name}" if theme_name else ""
                    filename = f"poster_{location_name.replace(' ', '_').replace(',', '')}{theme_suffix}.{format_output}"
                except:
                    filename = f"poster.{status.get('format', 'png')}"

                response = send_file(file_path, as_attachment=True, download_name=filename)
                # Prevent proxies/browsers from transforming (compressing) the binary output
                response.headers['Cache-Control'] = 'no-transform'
                response.headers['Content-Encoding'] = 'identity'
                return response

    return jsonify({'error': 'File not found'}), 404

@app.route('/api/download_all/<task_id>')
def api_download_all(task_id):
    """Download all theme outputs as a ZIP."""
    if task_id in progress_status:
        status = progress_status[task_id]
        files = status.get('files')
        if status.get('status') == 'completed' and files:
            # Build zip
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False, dir=TEMP_OUTPUT_DIR) as tmp_zip:
                zip_path = tmp_zip.name
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    file_path = f.get('file')
                    theme_name = f.get('theme') or 'theme'
                    if file_path and os.path.exists(file_path):
                        ext = os.path.splitext(file_path)[1].lower()
                        zf.write(file_path, arcname=f"{theme_name}{ext}")

            data = request.args.get('data', '{}')
            try:
                data = json.loads(data)
                if data.get('kecamatan'):
                    location_name = data.get('kecamatan')
                elif data.get('custom_city'):
                    location_name = data.get('custom_city')
                elif data.get('kota') and data.get('negara'):
                    location_name = f"{data.get('kota')}, {data.get('negara')}"
                else:
                    location_name = data.get('negara') or "poster"
                filename = f"poster_{location_name.replace(' ', '_').replace(',', '')}_all_themes.zip"
            except:
                filename = "posters_all_themes.zip"

            response = send_file(zip_path, as_attachment=True, download_name=filename)
            response.headers['Cache-Control'] = 'no-transform'
            response.headers['Content-Encoding'] = 'identity'
            return response

    return jsonify({'error': 'File not found'}), 404

@app.route('/api/preview/<task_id>')
def api_preview(task_id):
    """Inline preview for completed poster (PNG/SVG/PDF)."""
    if task_id in progress_status:
        status = progress_status[task_id]
        if status.get('status') == 'completed':
            file_path = None
            files = status.get('files')
            if files:
                try:
                    index = int(request.args.get('index', 0))
                except ValueError:
                    index = 0
                index = max(0, min(index, len(files) - 1))
                file_path = files[index].get('file')
            else:
                file_path = status.get('file')

            if file_path and os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext not in ['.png', '.svg', '.pdf']:
                    return jsonify({'error': 'Preview hanya tersedia untuk PNG/SVG/PDF'}), 415
                if ext == '.png':
                    mimetype = 'image/png'
                elif ext == '.svg':
                    mimetype = 'image/svg+xml'
                else:
                    mimetype = 'application/pdf'
                response = send_file(file_path, mimetype=mimetype, as_attachment=False)
                response.headers['Cache-Control'] = 'no-transform'
                response.headers['Content-Encoding'] = 'identity'
                return response
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
