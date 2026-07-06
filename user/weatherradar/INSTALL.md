# Weather Radar Panel — Installation Guide

Adds a looping radar animation panel to the WeatherFlow PiConsole.  
Data comes from the free [RainViewer API](https://www.rainviewer.com/api.html) overlaid on OpenStreetMap tiles.  
No API keys are needed.

---

## Files

```
user/
  customPanels.py            ← panel Python classes
  customPanels.kv            ← panel Kivy UI definition
  weatherradar/
    __init__.py
    radar_fetcher.py         ← tile fetching & compositing logic
    weatherradar_config.json ← your configuration (edit this)
    frames/                  ← created at runtime (PNG frame cache)
    base_map.png             ← created at runtime (base map tile cache)
```

---

## Step 1 — Copy files to the Raspberry Pi

From your development machine (replace `pi@raspberrypi.local` with your Pi's address):

```bash
scp user/customPanels.py   pi@raspberrypi.local:~/wfpiconsole/user/
scp user/customPanels.kv   pi@raspberrypi.local:~/wfpiconsole/user/
scp -r user/weatherradar/  pi@raspberrypi.local:~/wfpiconsole/user/
```

---

## Step 2 — Install Python dependencies

SSH into the Pi, activate the console's virtual environment, then install:

```bash
source ~/wfpiconsole/.venv/bin/activate
pip install Pillow requests
```

`requests` may already be present; `Pillow` handles the image compositing.

---

## Step 3 — Edit the configuration

Open `~/wfpiconsole/user/weatherradar/weatherradar_config.json` on the Pi:

```json
{
    "zip_code": "29403",
    "country": "us",
    "zoom": 7,
    "tile_grid": 3,
    "tile_theme": "carto_dark",
    "history_hours": 3,
    "refresh_interval": 300,
    "color_scheme": 6,
    "smooth": 1,
    "snow": 0,
    "frame_delay": 0.2
}
```

| Key | Description | Recommended values |
|-----|-------------|-------------------|
| `zip_code` | Your postal code | any valid code |
| `country` | Country code for zippopotam.us | `us`, `ca`, `gb`, etc. |
| `zoom` | Map zoom level | `6`–`7` (7 = regional; max supported by RainViewer) |
| `tile_grid` | Grid of tiles around center (N×N) | `1`–`5` (3 = good regional view) |
| `tile_theme` | Base map style | see **Map themes** table below |
| `history_hours` | Hours of radar history to keep and animate | `1`–`3` (3 = ~18 frames) |
| `refresh_interval` | Seconds between data refreshes | `300` (RainViewer updates every ~10 min) |
| `color_scheme` | RainViewer color palette (0–8) | `6` = vivid, `1` = original |
| `smooth` | Smooth radar edges (0 or 1) | `1` |
| `snow` | Show snow as separate color (0 or 1) | `0` |
| `frame_delay` | Seconds between animation frames | `0.15`–`0.4` |

**Map themes (all free, no API key required):**

| `tile_theme` | Appearance |
|---|---|
| `osm` | Standard OpenStreetMap — light, detailed |
| `carto_dark` | Dark grey land and water, minimal labels |
| `carto_light` | Light grey, minimal |
| `carto_voyager` | Blue water, light/cream land |

---

**Coverage guide for `zoom` + `tile_grid`:**

| zoom | Single tile width | 3×3 grid width |
|------|-------------------|----------------|
| 6    | ~310 mi           | ~930 mi        |
| 7    | ~155 mi           | ~465 mi ✓      |
| 8    | ~78 mi            | ~234 mi        |
| 9    | ~39 mi            | ~117 mi        |

> **Note:** RainViewer only serves radar tiles up to zoom 7. Setting `zoom`
> higher than 7 will cause tiles to display an "unsupported zoom level" message
> instead of radar data. Keep `zoom` at 7 or below.
>
> To get a closer or wider view without changing zoom, adjust `tile_grid`
> instead — a 5×5 grid at zoom 7 gives ~775 mi coverage, a 2×2 grid gives
> ~310 mi for a tighter local view.

---

## Step 4 — Enable the panel in the console

1. Start the console and open **Menu → Settings**.
2. Go to **Primary Panels** or **Secondary Panels**.
3. Select a panel slot and choose **WeatherRadar** from the dropdown.
4. Save and restart the console.

The panel button labelled **Weather Radar** will appear in the bottom bar.

---

## How the frame cache works

Frames are stored as `frames/frame_{timestamp}.png`, keyed by the RainViewer
Unix timestamp.  On each refresh cycle:

1. Frames older than `history_hours` are **purged** from disk automatically.
2. RainViewer is queried for all available timestamps within the history window.
3. Only timestamps **not already on disk** are downloaded and composited — so
   a refresh that finds no new data does almost no work.
4. The animation plays all cached frames oldest → newest.

On first launch, RainViewer provides up to ~13 frames (their maximum).  The
cache grows to a full `history_hours` window (~18 frames for 3 h) over the
first hour as new radar data arrives and is appended.

> **First launch note:** The initial run downloads the base map tiles plus all
> available radar frames (~120 HTTP requests for a 3×3 grid × 13 frames).
> This takes 20–60 seconds on a typical Pi connection.  Subsequent refreshes
> are much faster because the base map is cached and only new frames are fetched.

---

## Upgrading from an earlier version

If you previously installed this panel, clear the old frame files before
restarting (the old naming scheme `frame_00.png` is no longer used):

```bash
rm ~/wfpiconsole/user/weatherradar/frames/frame_*.png
```

---

## Troubleshooting

**"Radar unavailable" is shown:**
- Check internet connectivity on the Pi.
- Run the fetcher manually from the `wfpiconsole/` directory:
  ```bash
  source .venv/bin/activate
  python3 -c "import user.weatherradar.radar_fetcher as r; print(r.fetch_radar_frames(r.load_config()))"
  ```

**Panel shows a blank/black image:**
- Verify Pillow is installed in the venv: `python3 -c "from PIL import Image; print('OK')"`.
- Check that `user/weatherradar/frames/` contains PNG files after the first refresh.

**Base map tiles show as grey squares:**
- Tile servers rate-limit aggressive fetching. Wait a minute and restart.
- If using `carto_dark` or `carto_light`, try switching to `osm` temporarily to confirm connectivity.

**Switching `tile_theme` shows the old map:**
- Delete the cached base map so it rebuilds with the new theme:
  ```bash
  rm ~/wfpiconsole/user/weatherradar/base_map.png
  rm ~/wfpiconsole/user/weatherradar/base_map_key.txt
  ```

**Animation is jerky:**
- Increase `frame_delay` to `0.3` or `0.4` to reduce CPU during animation.
- Reduce `tile_grid` to `2` or `1` to decrease tiles fetched per refresh.

---

## Attribution

- Radar data: [RainViewer](https://www.rainviewer.com/) (free for personal/educational use)
- Base map (osm): © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- Base map (carto_*): © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, © [CARTO](https://carto.com/attributions)
