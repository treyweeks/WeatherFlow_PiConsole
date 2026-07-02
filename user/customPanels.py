""" Define custom user panels for the Raspberry Pi Python console for
WeatherFlow Tempest and Smart Home Weather stations.
Copyright (C) 2018-2025 Peter Davis

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

# Load required modules
import threading
from kivy.uix.relativelayout import RelativeLayout
from kivy.clock              import Clock
from kivy.core.image         import Image as CoreImage
from panels.template         import panelTemplate


# ==============================================================================
# WeatherRadar CUSTOM PANEL
# ==============================================================================
class WeatherRadarPanel(panelTemplate):
    """
    Displays a looping weather radar animation fetched from the free
    RainViewer API, composited onto OpenStreetMap base tiles.

    Configuration lives in user/weatherradar/weatherradar_config.json.
    Frames are refreshed in a background thread on the configured interval.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._config         = None
        self._frame_textures = []   # pre-loaded Kivy textures
        self._frame_index    = 0
        self._anim_event     = None
        self._refresh_event  = None
        # Defer startup so the full widget tree is available
        Clock.schedule_once(self._start, 3)

    # ------------------------------------------------------------------
    # Startup & refresh scheduling
    # ------------------------------------------------------------------
    def _start(self, dt):
        from user.weatherradar.radar_fetcher import load_config
        self._config = load_config()
        self._do_refresh()
        interval = self._config.get('refresh_interval', 300)
        self._refresh_event = Clock.schedule_interval(
            lambda dt: self._do_refresh(), interval)

    def _do_refresh(self):
        """Kick off a background thread to fetch new radar data."""
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        """Background: fetch frames, then hand off to the main thread."""
        from user.weatherradar.radar_fetcher import fetch_radar_frames
        paths = fetch_radar_frames(self._config)
        if paths:
            Clock.schedule_once(lambda dt: self._load_textures(paths), 0)
        else:
            Clock.schedule_once(lambda dt: self._show_error(), 0)

    # ------------------------------------------------------------------
    # Texture loading & animation (always called on the Kivy main thread)
    # ------------------------------------------------------------------
    def _load_textures(self, paths):
        """Pre-load all frame PNGs into GPU textures and start the loop."""
        textures = []
        for path in paths:
            try:
                ci = CoreImage(path, nocache=True)
                textures.append(ci.texture)
            except Exception as exc:
                print(f'[WeatherRadar] Texture load failed ({path}): {exc}')
        if not textures:
            self._show_error()
            return

        self._frame_textures = textures
        self._frame_index    = 0

        # Hide the status label now that we have real data
        if 'status_label' in self.ids:
            self.ids.status_label.opacity = 0

        # (Re)start the animation clock
        delay = self._config.get('frame_delay', 0.2)
        if self._anim_event:
            self._anim_event.cancel()
        self._anim_event = Clock.schedule_interval(self._advance_frame, delay)
        self._render_frame(0)

    def _advance_frame(self, dt):
        if not self._frame_textures:
            return
        self._frame_index = (self._frame_index + 1) % len(self._frame_textures)
        self._render_frame(self._frame_index)

    def _render_frame(self, index):
        if 'radar_image' not in self.ids or not self._frame_textures:
            return
        self.ids.radar_image.texture = self._frame_textures[index]

    def _show_error(self):
        if 'status_label' in self.ids:
            self.ids.status_label.text    = 'Radar unavailable\nCheck connection'
            self.ids.status_label.opacity = 1


class WeatherRadarButton(RelativeLayout):
    pass
