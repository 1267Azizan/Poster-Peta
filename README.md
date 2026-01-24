
# Generator Poster Peta Kota

Buat poster peta yang indah dan minimalis untuk kota mana saja di dunia.

## 🚀 Web Interface (Mudah Digunakan)

Aplikasi ini sekarang memiliki antarmuka web yang memudahkan penggunaan tanpa perlu command line!

### Cara Menjalankan Web Interface:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install flask
   ```

2. **Jalankan server web:**
   ```bash
   python app.py
   ```

3. **Buka browser dan akses:**
   ```
   http://localhost:5000
   ```

### Fitur Web Interface:

- ✅ **Form input sederhana** - Pilih kota, negara, tema, dan pengaturan lainnya
- 📊 **Progress bar real-time** - Lihat progress pembuatan poster
- 📏 **Pilihan unit ukuran** - cm atau mm
- 🎨 **Preview tema** - Pilih dari berbagai tema yang tersedia
- 📥 **Download otomatis** - Poster langsung tersedia untuk diunduh
- ⚡ **Asynchronous processing** - Tidak perlu menunggu lama di browser

### Tangkapan Layar:

<img src="posters/singapore_neon_cyberpunk_20260108_184503.png" width="250">
<img src="posters/dubai_midnight_blue_20260108_174920.png" width="250">

## Examples


| Negara      | Kota           | Tema           | Poster |
|:-----------:|:--------------:|:--------------:|:------:|
| USA          | San Francisco  | sunset          | <img src="posters/san_francisco_sunset_20260108_184122.png" width="250"> |
| Spain        | Barcelona      | warm_beige      | <img src="posters/barcelona_warm_beige_20260108_172924.png" width="250"> |
| Italy        | Venice         | blueprint       | <img src="posters/venice_blueprint_20260108_165527.png" width="250"> |
| Japan        | Tokyo          | japanese_ink    | <img src="posters/tokyo_japanese_ink_20260108_165830.png" width="250"> |
| India        | Mumbai         | contrast_zones  | <img src="posters/mumbai_contrast_zones_20260108_170325.png" width="250"> |
| Morocco      | Marrakech      | terracotta      | <img src="posters/marrakech_terracotta_20260108_180821.png" width="250"> |
| Singapore    | Singapore      | neon_cyberpunk  | <img src="posters/singapore_neon_cyberpunk_20260108_184503.png" width="250"> |
| Australia    | Melbourne      | forest          | <img src="posters/melbourne_forest_20260108_181459.png" width="250"> |
| UAE          | Dubai          | midnight_blue   | <img src="posters/dubai_midnight_blue_20260108_174920.png" width="250"> |

## Instalasi

```bash
pip install -r requirements.txt
```

## Penggunaan

```bash
python create_map_poster.py --kota <kota> --negara <negara> [opsi]
```

### Opsi

| Opsi | Singkat | Deskripsi | Default |
|------|---------|-----------|---------|
| `--kota` | `-k` | Nama kota | wajib |
| `--negara` | `-n` | Nama negara | wajib |
| `--tema` | `-t` | Nama tema | feature_based |
| `--skala` | `-s` | Radius peta dalam meter | 29000 |
| `--daftar-tema` | | Daftar semua tema yang tersedia | |
| `--kecamatan` | | Nama kecamatan untuk peta berbasis batas | |
| `--width` | | Lebar poster dalam cm | 30.48 |
| `--height` | | Tinggi poster dalam cm | 40.64 |
| `--bersih` | | Buat poster tanpa teks | |

### Contoh

```bash
# Pola grid ikonik
python create_map_poster.py -k "New York" -n "USA" -t noir -s 12000           # Grid Manhattan
python create_map_poster.py -k "Barcelona" -n "Spain" -t warm_beige -s 8000   # Distrik Eixample

# Waterfront & canals
python create_map_poster.py -k "Venice" -n "Italy" -t blueprint -s 4000       # Jaringan kanal
python create_map_poster.py -k "Amsterdam" -n "Netherlands" -t ocean -s 6000  # Kanal konsentris
python create_map_poster.py -k "Dubai" -n "UAE" -t midnight_blue -s 15000     # Palma & garis pantai

# Radial patterns
python create_map_poster.py -k "Paris" -n "France" -t pastel_dream -s 10000   # Boulevard Haussmann
python create_map_poster.py -k "Moscow" -n "Russia" -t noir -s 12000          # Jalan lingkar

# Organic old cities
python create_map_poster.py -k "Tokyo" -n "Japan" -t japanese_ink -s 15000    # Jalan organik padat
python create_map_poster.py -k "Marrakech" -n "Morocco" -t terracotta -s 5000 # Labirin medina
python create_map_poster.py -k "Rome" -n "Italy" -t warm_beige -s 8000        # Tata letak kuno

# Coastal cities
python create_map_poster.py -k "San Francisco" -n "USA" -t sunset -s 10000    # Grid semenanjung
python create_map_poster.py -k "Sydney" -n "Australia" -t ocean -s 12000      # Kota pelabuhan
python create_map_poster.py -k "Mumbai" -n "India" -t contrast_zones -s 18000 # Semenanjung pesisir

# River cities
python create_map_poster.py -k "London" -n "UK" -t noir -s 15000              # Tikungan Thames
python create_map_poster.py -k "Budapest" -n "Hungary" -t copper_patina -s 8000  # Danube terbelah

# Daftar tema yang tersedia
python create_map_poster.py --daftar-tema
```

### Panduan Skala

| Skala | Terbaik untuk |
|-------|---------------|
| 4000-6000m | Kota kecil/padat (Venice, pusat Amsterdam) |
| 8000-12000m | Kota sedang, pusat kota fokus (Paris, Barcelona) |
| 15000-20000m | Metro besar, tampilan kota penuh (Tokyo, Mumbai) |

## Tema

17 tema tersedia di direktori `themes/`:

| Tema | Gaya |
|------|------|
| `feature_based` | Hitam & putih klasik dengan hierarki jalan |
| `gradient_roads` | Bayangan gradien halus |
| `contrast_zones` | Kontras tinggi kepadatan urban |
| `noir` | Latar belakang hitam murni, jalan putih |
| `midnight_blue` | Navy background with gold roads |
| `blueprint` | Architectural blueprint aesthetic |
| `neon_cyberpunk` | Dark with electric pink/cyan |
| `warm_beige` | Vintage sepia tones |
| `pastel_dream` | Soft muted pastels |
| `japanese_ink` | Minimalist ink wash style |
| `forest` | Deep greens and sage |
| `ocean` | Blues and teals for coastal cities |
| `terracotta` | Mediterranean warmth |
| `sunset` | Warm oranges and pinks |
| `autumn` | Seasonal burnt oranges and reds |
| `copper_patina` | Oxidized copper aesthetic |
| `monochrome_blue` | Single blue color family |

## Output

Posters are saved to `posters/` directory with format:
```
{city}_{theme}_{YYYYMMDD_HHMMSS}.png
```

## Menambahkan Tema Kustom

Buat file JSON di direktori `themes/`:

```json
{
  "name": "Tema Saya",
  "description": "Deskripsi tema",
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
```

## Struktur Proyek

```
map_poster/
├── create_map_poster.py          # Script utama
├── themes/               # File tema JSON
├── fonts/                # File font Roboto
├── posters/              # Poster yang dihasilkan
└── README.md
```

## Panduan Pengembang

Referensi cepat untuk kontributor yang ingin memperluas atau memodifikasi script.

### Gambaran Arsitektur

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   CLI Parser    │────▶│  Geocoding   │────▶│  Data Fetching  │
│   (argparse)    │     │  (Nominatim) │     │    (OSMnx)      │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                     │
                        ┌──────────────┐             ▼
                        │    Output    │◀────┌─────────────────┐
                        │  (matplotlib)│     │   Rendering     │
                        └──────────────┘     │  (matplotlib)   │
                                             └─────────────────┘
```

### Fungsi Utama

| Fungsi | Tujuan | Modifikasi saat... |
|--------|--------|-------------------|
| `get_coordinates()` | Kota → lat/lon via Nominatim | Mengganti penyedia geocoding |
| `create_poster()` | Pipeline rendering utama | Menambah layer peta baru |
| `get_edge_colors_by_type()` | Warna jalan berdasarkan tag OSM highway | Mengubah styling jalan |
| `get_edge_widths_by_type()` | Lebar jalan berdasarkan kepentingan | Menyesuaikan bobot garis |
| `create_gradient_fade()` | Efek fade atas/bawah | Memodifikasi overlay gradien |
| `load_theme()` | JSON tema → dict | Menambah properti tema baru |

### Layer Rendering (z-order)

```
z=11  Label teks (kota, negara, koordinat)
z=10  Fade gradien (atas & bawah)
z=3   Jalan (via ox.plot_graph)
z=2   Taman (poligon hijau)
z=1   Air (poligon biru)
z=0   Warna latar belakang
```

### Tipe Highway OSM → Hierarki Jalan

```python
# Di get_edge_colors_by_type() dan get_edge_widths_by_type()
motorway, motorway_link     → Tertebal (1.2), tergelap
trunk, primary              → Tebal (1.0)
secondary                   → Sedang (0.8)
tertiary                    → Tipis (0.6)
residential, living_street  → Tertidip (0.4), terang
```

### Menambah Fitur Baru

**Layer peta baru (contoh: rel kereta):**
```python
# Di create_poster(), setelah fetch taman:
try:
    railways = ox.features_from_point(point, tags={'railway': 'rail'}, dist=dist)
except:
    railways = None

# Kemudian plot sebelum jalan:
if railways is not None and not railways.empty:
    railways.plot(ax=ax, color=THEME['railway'], linewidth=0.5, zorder=2.5)
```

**Properti tema baru:**
1. Tambah ke JSON tema: `"railway": "#FF0000"`
2. Gunakan di kode: `THEME['railway']`
3. Tambah fallback di dict default `load_theme()`

### Posisi Tipografi

Semua teks menggunakan `transform=ax.transAxes` (koordinat normalisasi 0-1):
```
y=0.14  Nama kota (huruf berjarak)
y=0.125 Garis dekoratif
y=0.10  Nama negara
y=0.07  Koordinat
y=0.02  Atribusi (kanan bawah)
```

### Pola OSMnx Berguna

```python
# Dapatkan semua bangunan
buildings = ox.features_from_point(point, tags={'building': True}, dist=dist)

# Dapatkan amenity spesifik
cafes = ox.features_from_point(point, tags={'amenity': 'cafe'}, dist=dist)

# Tipe jaringan berbeda
G = ox.graph_from_point(point, dist=dist, network_type='drive')  # jalan saja
G = ox.graph_from_point(point, dist=dist, network_type='bike')   # jalur sepeda
G = ox.graph_from_point(point, dist=dist, network_type='walk')   # pejalan kaki
```

### Tips Performa

- Nilai `dist` besar (>20km) = download lambat + berat memori
- Cache koordinat lokal untuk menghindari batas rate Nominatim
- Gunakan `network_type='drive'` bukan `'all'` untuk render lebih cepat
- Kurangi `dpi` dari 300 ke 150 untuk preview cepat
=======
# Poster-Peta
>>>>>>> 2b09ec72dabb9fc974da44a76ac4e00a1bdcc93e

