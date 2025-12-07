#!/usr/bin/env python3

import logging
import signal
import sys
from time import sleep

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

import Ice

Ice.loadSlice('-I{} spotifice_v1.ice'.format(Ice.getSliceDir()))
import Spotifice  # type: ignore # noqa: E402

try:
    from mpris2_support import MPRIS2Service
except ImportError:
    MPRIS2Service = lambda app: None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_proxy(ic, property, cls):
    proxy = ic.propertyToProxy(property)

    for _ in range(5):
        try:
            proxy.ice_ping()
            break
        except Ice.ConnectionRefusedException:
            sleep(0.5)

    object = cls.checkedCast(proxy)
    if object is None:
        raise RuntimeError(f'Invalid proxy for {property}')

    return object


def handle_action_error(func):
    "Decorator to handle exceptions in action methods"
    action_name = func.__name__.replace('on_', '').replace('_', ' ')
    def wrapper(self, button):
        try:
            return func(self, button)
        except Exception as e:
            self.update_status(f"Error in {action_name}(): {e}")
    return wrapper


class UIBuilder:
    "Builder pattern for creating the Spotifice Control UI"

    def __init__(self):
        self.main_box = None
        self.playlist_box = None
        self.playlist_dropdown = None
        self.playlist_model = None
        self.controls_box = None
        self.play_button = None
        self.pause_button = None
        self.stop_button = None
        self.repeat_button = None
        self.track_label = None
        self.status_label = None

    def build_main_container(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.main_box.set_margin_top(15)
        self.main_box.set_margin_bottom(15)
        self.main_box.set_margin_start(15)
        self.main_box.set_margin_end(15)
        return self

    def build_playlist_selector(self, on_changed_callback):
        self.playlist_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        playlist_label = Gtk.Label(label="Playlist:")
        playlist_label.set_size_request(70, -1)
        playlist_label.set_xalign(0)

        self.playlist_model = Gtk.StringList()
        self.playlist_dropdown = Gtk.DropDown(model=self.playlist_model)
        self.playlist_dropdown.set_hexpand(True)
        self.playlist_dropdown.connect("notify::selected", on_changed_callback)

        self.playlist_box.append(playlist_label)
        self.playlist_box.append(self.playlist_dropdown)
        return self

    def build_playback_controls(self, callbacks):
        self.controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.controls_box.set_halign(Gtk.Align.CENTER)
        self.controls_box.set_homogeneous(True)

        prev_button = self._create_button(
            "media-skip-backward", "Previous", callbacks['previous'])

        self.play_button = self._create_button(
            "media-playback-start", "Play", callbacks['play'])

        self.pause_button = self._create_button(
            "media-playback-pause", "Pause", callbacks['pause'])

        self.stop_button = self._create_button(
            "media-playback-stop", "Stop", callbacks['stop'])

        next_button = self._create_button(
            "media-skip-forward", "Next", callbacks['next'])

        self.repeat_button = self._create_toggle_button(
            "media-playlist-repeat", "Repeat", callbacks['repeat']
        )

        self.controls_box.append(prev_button)
        self.controls_box.append(self.play_button)
        self.controls_box.append(self.pause_button)
        self.controls_box.append(self.stop_button)
        self.controls_box.append(next_button)
        self.controls_box.append(self.repeat_button)
        return self

    def _create_button(self, icon_name, tooltip, callback):
        button = Gtk.Button()
        button.set_child(Gtk.Image.new_from_icon_name(icon_name))
        button.get_child().set_icon_size(Gtk.IconSize.LARGE)
        button.set_tooltip_text(tooltip)
        button.connect("clicked", callback)
        return button

    def _create_toggle_button(self, icon_name, tooltip, callback):
        button = Gtk.ToggleButton()
        button.set_child(Gtk.Image.new_from_icon_name(icon_name))
        button.get_child().set_icon_size(Gtk.IconSize.LARGE)
        button.set_tooltip_text(tooltip)
        button.connect("toggled", callback)
        return button

    def build_track_display(self):
        self.track_label = Gtk.Label(label="No track loaded")
        self.track_label.set_wrap(False)
        self.track_label.set_ellipsize(3)
        self.track_label.set_xalign(0.5)
        self.track_label.set_margin_top(10)
        self.track_label.set_selectable(True)
        self.track_label.add_css_class("title-3")
        self.track_label.set_width_chars(45)
        self.track_label.set_max_width_chars(45)
        self.track_label.set_size_request(400, -1)
        return self

    def build_status_bar(self):
        statusbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        statusbar_box.add_css_class("statusbar")

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0)
        self.status_label.set_margin_start(10)
        self.status_label.set_margin_end(10)
        self.status_label.set_margin_top(5)
        self.status_label.set_margin_bottom(5)

        statusbar_box.append(self.status_label)
        self.statusbar_box = statusbar_box
        return self

    def assemble(self):
        if self.playlist_box:
            self.main_box.append(self.playlist_box)
        if self.controls_box:
            self.main_box.append(self.controls_box)
        if self.track_label:
            self.main_box.append(self.track_label)
        if hasattr(self, 'statusbar_box'):
            self.main_box.append(self.statusbar_box)
        return self

    def get_result(self):
        return {
            'main_box': self.main_box,
            'playlist_dropdown': self.playlist_dropdown,
            'playlist_model': self.playlist_model,
            'play_button': self.play_button,
            'pause_button': self.pause_button,
            'stop_button': self.stop_button,
            'repeat_button': self.repeat_button,
            'track_label': self.track_label,
            'status_label': self.status_label,
        }


class SpotificeControlWindow(Gtk.ApplicationWindow):
    def __init__(self, app, communicator):
        super().__init__(application=app, title="Spotifice Control")
        self.set_resizable(False)

        self.communicator = communicator
        self.server, self.render = self.init_ice_proxies()
        self.create_ui()
        self.load_initial_state()
        self.load_playlists()

    def init_ice_proxies(self):
        try:
            server = get_proxy(
                self.communicator, 'MediaServer.Proxy', Spotifice.MediaServerPrx)
            render = get_proxy(
                self.communicator, 'MediaRender.Proxy', Spotifice.MediaRenderPrx)
            render.bind_media_server(server)
        except Exception as e:
            logger.error(f"Error initializing Ice proxies: {e}")
            sys.exit(1)

        return server, render

    def create_ui(self):
        callbacks = {
            'play': self.on_play,
            'pause': self.on_pause,
            'stop': self.on_stop,
            'previous': self.on_previous,
            'next': self.on_next,
            'repeat': self.on_repeat,
        }

        builder = UIBuilder()
        builder.build_main_container() \
               .build_playlist_selector(self.on_playlist_changed) \
               .build_playback_controls(callbacks) \
               .build_track_display() \
               .build_status_bar() \
               .assemble()

        ui = builder.get_result()
        self.playlist_dropdown = ui['playlist_dropdown']
        self.playlist_model = ui['playlist_model']
        self.play_button = ui['play_button']
        self.pause_button = ui['pause_button']
        self.stop_button = ui['stop_button']
        self.repeat_button = ui['repeat_button']
        self.track_label = ui['track_label']
        self.status_label = ui['status_label']

        self.track_full_text = ""
        self.track_scroll_offset = 0
        self.track_animation_timeout = None

        self.playlist_ids = []

        self.set_child(ui['main_box'])
        # flag to avoid triggering handlers while updating UI programmatically
        self._updating_ui = False

    def load_initial_state(self):
        try:
            status = self.render.get_status()
        except Exception as e:
            logger.error(f"Error loading initial state: {e}")
            self.update_status("Ready")
            return

        self.update_current_track()

        match status.state:
            case Spotifice.PlaybackState.PLAYING:
                status_message = "Playing"
            case Spotifice.PlaybackState.PAUSED:
                status_message = "Paused"
            case Spotifice.PlaybackState.STOPPED:
                status_message = "Stopped"
            case _:
                status_message = "Ready"

        self.update_status(status_message)
        self.update_button_states(status.state)
        self.update_repeat_button(status.repeat)

    def update_status(self, message):
        self.status_label.set_text(message)

    def update_button_states(self, state):
        self.play_button.remove_css_class("suggested-action")
        self.pause_button.remove_css_class("suggested-action")
        self.stop_button.remove_css_class("suggested-action")

        match state:
            case Spotifice.PlaybackState.PLAYING:
                self.play_button.add_css_class("suggested-action")
            case Spotifice.PlaybackState.PAUSED:
                self.pause_button.add_css_class("suggested-action")
            case Spotifice.PlaybackState.STOPPED:
                self.stop_button.add_css_class("suggested-action")

    def update_repeat_button(self, is_active: bool):
        # Avoid recursive signal handling
        self._updating_ui = True
        try:
            self.repeat_button.set_active(bool(is_active))
        finally:
            self._updating_ui = False

    def update_current_track(self):
        if self.track_animation_timeout is not None:
            GLib.source_remove(self.track_animation_timeout)
            self.track_animation_timeout = None

        try:
            track = self.render.get_current_track()
        except Exception as e:
            self.track_full_text = "No track loaded"
            self.track_label.set_text(self.track_full_text)
            logger.error(f"Error getting current track: {e}")
            return

        if not track or not track.title:
            self.track_full_text = "No track loaded"
            self.track_label.set_text(self.track_full_text)
            return

        self.track_full_text = track.title
        self.track_scroll_offset = 0

        if len(self.track_full_text) > 45:
            self.track_animation_timeout = GLib.timeout_add(
                200, self.animate_track_title
            )
        else:
            self.track_label.set_text(self.track_full_text)

    def animate_track_title(self):
        if not self.track_full_text or len(self.track_full_text) <= 45:
            return False

        display_text = self.track_full_text[
            self.track_scroll_offset:self.track_scroll_offset + 45
        ]

        if len(display_text) < 45:
            remaining = 45 - len(display_text) - 5
            display_text += " ... " + self.track_full_text[:remaining]

        self.track_label.set_text(display_text)

        self.track_scroll_offset += 1
        if self.track_scroll_offset >= len(self.track_full_text) + 5:
            self.track_scroll_offset = 0

        return True

    def load_playlists(self):
        try:
            playlists = self.server.get_all_playlists()
        except Exception as e:
            logger.error(f"Error loading playlists: {e}")
            self.update_status(f"Error loading playlists: {e}")
            return

        for playlist in playlists:
            self.playlist_model.append(playlist.name)
            self.playlist_ids.append(playlist.id)

        if playlists:
            self.playlist_dropdown.set_selected(0)

    def on_playlist_changed(self, dropdown, _pspec):
        selected_index = dropdown.get_selected()
        if selected_index == Gtk.INVALID_LIST_POSITION or selected_index >= len(self.playlist_ids):
            return

        playlist_id = self.playlist_ids[selected_index]

        try:
            self.render.stop()
            self.render.load_playlist(playlist_id)
        except Exception as e:
            self.update_status(f"Error loading playlist: {e}")
            return

        playlist_name = self.playlist_model.get_string(selected_index)
        self.update_status(f"Loaded playlist: {playlist_name}")
        self.update_current_track()
        self.update_button_states(Spotifice.PlaybackState.STOPPED)

    @handle_action_error
    def on_play(self, button):
        self.render.play()
        self.update_status("Playing")
        self.update_button_states(Spotifice.PlaybackState.PLAYING)
        self.update_current_track()

    @handle_action_error
    def on_pause(self, button):
        self.render.pause()
        self.update_status("Paused")
        self.update_button_states(Spotifice.PlaybackState.PAUSED)

    @handle_action_error
    def on_stop(self, button):
        self.render.stop()
        self.update_status("Stopped")
        self.update_button_states(Spotifice.PlaybackState.STOPPED)

    @handle_action_error
    def on_previous(self, button):
        self.render.previous()
        self.update_status("Previous track")
        self.update_current_track()

    @handle_action_error
    def on_next(self, button):
        self.render.next()
        self.update_status("Next track")
        self.update_current_track()

    @handle_action_error
    def on_repeat(self, button):
        if getattr(self, "_updating_ui", False):
            return
        is_active = bool(button.get_active())
        self.render.set_repeat(is_active)
        self.update_status("Repeat On" if is_active else "Repeat Off")


class SpotificeApp(Gtk.Application):
    def __init__(self, communicator):
        super().__init__(application_id='es.uclm.spotifice')
        self.communicator = communicator
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = SpotificeControlWindow(self, self.communicator)
            MPRIS2Service(self.window)
        self.window.present()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Usage: media_control_v1.py <config-file>")

    with Ice.initialize(sys.argv[1]) as communicator:
        app = SpotificeApp(communicator)
        signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
        app.run(None)
