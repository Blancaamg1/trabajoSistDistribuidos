#!/usr/bin/env python3

import logging
import os
import signal
import sys

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

import Ice

Ice.loadSlice('-I{} spotifice_v2.ice'.format(Ice.getSliceDir()))
import Spotifice

from media_control_v1 import (
    SpotificeControlWindow as BaseWindow,
    get_proxy,
)

try:
    from mpris2_support import MPRIS2Service
except ImportError:
    MPRIS2Service = lambda app: None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def acquire_credentials(communicator) -> tuple[str, str]:
    username = 'user'
    password = 'secret'

    if username and password:
        return username, password

    dialog = Gtk.Dialog(title="Spotifice Login")
    dialog.set_modal(True)
    dialog.set_transient_for(None)

    content = dialog.get_content_area()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_top(12)
    box.set_margin_bottom(12)
    box.set_margin_start(12)
    box.set_margin_end(12)

    user_entry = Gtk.Entry()
    user_entry.set_placeholder_text("Username")
    pass_entry = Gtk.Entry()
    pass_entry.set_placeholder_text("Password")
    pass_entry.set_visibility(False)

    box.append(Gtk.Label(label="Please authenticate to Spotifice"))
    box.append(user_entry)
    box.append(pass_entry)
    content.append(box)

    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Login", Gtk.ResponseType.OK)

    response = dialog.run()
    username = user_entry.get_text()
    password = pass_entry.get_text()
    dialog.destroy()

    if response != Gtk.ResponseType.OK:
        raise RuntimeError("Authentication canceled by user")

    if not username or not password:
        raise RuntimeError("Empty username or password")

    return username, password


class SpotificeControlWindowV2(BaseWindow):
    "Subclass of v1 window that only changes authentication/binding for v2."

    def __init__(self, app, communicator):
        self._v2_communicator = communicator
        super().__init__(app, communicator)
        self.set_title("Spotifice Control (v2)")

    def init_ice_proxies(self):
        try:
            server = get_proxy(self.communicator, 'MediaServer.Proxy', Spotifice.MediaServerPrx)
            render = get_proxy(self.communicator, 'MediaRender.Proxy', Spotifice.MediaRenderPrx)
            user, pwd = acquire_credentials(self.communicator)
            ssm = server.authenticate(render, user, pwd)
            render.bind_media_server(server, ssm)
        except Exception as e:
            logger.error(f"v2 authentication error: {e}")
            sys.exit(1)
        return server, render

    def load_initial_state(self):
        try:
            status = self.render.get_status()
        except Exception:
            self.update_status("Ready")
            return
        self.update_current_track()
        mapping = {
            Spotifice.PlaybackState.PLAYING: "Playing",
            Spotifice.PlaybackState.PAUSED: "Paused",
            Spotifice.PlaybackState.STOPPED: "Stopped",
        }
        self.update_status(mapping.get(status.state, "Ready"))
        self.update_button_states(status.state)
        self.update_repeat_button(status.repeat)


class SpotificeAppV2(Gtk.Application):
    def __init__(self, communicator):
        super().__init__(application_id='es.uclm.spotifice.v2')
        self.communicator = communicator
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = SpotificeControlWindowV2(self, self.communicator)
            MPRIS2Service(self.window)
        self.window.present()


def main(argv: list[str]):
    if len(argv) < 2:
        sys.exit('Usage: media_control_v2.py <config-file>')
    with Ice.initialize(argv[1]) as communicator:
        app = SpotificeAppV2(communicator)
        signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
        app.run(None)


if __name__ == '__main__':
    main(sys.argv)