#!/usr/bin/env python3

import sys
from time import sleep

import Ice

Ice.loadSlice('-I{} spotifice_v0.ice'.format(Ice.getSliceDir()))
import Spotifice  # type: ignore # noqa: E402


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


def main(ic):
    server = get_proxy(ic, 'MediaServer.Proxy', Spotifice.MediaServerPrx)
    render = get_proxy(ic, 'MediaRender.Proxy', Spotifice.MediaRenderPrx)

    print("Fetching all tracks...")
    tracks = server.get_all_tracks()
    for t in tracks:
        print(f"- {t.title}")

    if not tracks:
        print("No tracks found.")
        return

    print(f"Requesting info for track {tracks[0].id}")
    print(f"Track title: {tracks[0].title}")

    render.bind_media_server(server)
    render.stop()

    print("Loading track into MediaRender...")
    render.load_track(tracks[0].id)
    render.play()
    sleep(5)  # Let it play for 5 seconds

    render.stop()
    render.load_track(tracks[1].id)
    render.play()

    # track 1 continues playing...


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Usage: media_control.py <config-file>")

    with Ice.initialize(sys.argv[1]) as communicator:
        main(communicator)
