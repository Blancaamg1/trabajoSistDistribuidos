from gst_player import GstPlayer
from media_render import Spotifice
from media_render import main as render_main
from media_server import main as server_main

from .icetest import IceTestCase


class TestRender(IceTestCase):
    render_port = 10001
    server_port = 10000

    def setUp(self):
        server_props = {
            'MediaServerAdapter.Endpoints': f'tcp -p {self.server_port}',
            'MediaServer.Content': 'test/media'}
        server_endpoint = f'mediaServer1:default -p {self.server_port} -t 500'
        self.create_server(server_main, server_props)

        player = GstPlayer()
        player.start()
        self.addCleanup(player.shutdown)

        render_props = {
            'MediaRenderAdapter.Endpoints': f'tcp -p {self.render_port}'}
        render_enpoint = f'mediaRender1:default -p {self.render_port} -t 500'
        self.create_server(render_main, render_props, player)

        self.server = self.create_proxy(server_endpoint, Spotifice.MediaServerPrx)
        self.sut = self.create_proxy(render_enpoint, Spotifice.MediaRenderPrx)


class PlaybackTests(TestRender):
    def test_id(self):
        self.assertEqual(self.sut.ice_id(), '::Spotifice::MediaRender')

    def test_stop_is_idempotent(self):
        self.sut.stop()
        self.sut.stop()

    def test_play_unbound_server(self):
        with self.assertRaises(Spotifice.BadReference) as cm:
            self.sut.play()

        self.assertEqual(cm.exception.reason, "No MediaServer bound")

    def test_play_unloaded_track(self):
        self.sut.bind_media_server(self.server)

        with self.assertRaises(Spotifice.TrackError) as cm:
            self.sut.play()

        self.assertEqual(cm.exception.reason, "No track loaded")

    def test_normal_play(self):
        tracks = self.server.get_all_tracks()
        self.sut.bind_media_server(self.server)
        self.sut.load_track(tracks[1].id)

        self.sut.play()

    def test_can_not_play_if_player_busy(self):
        tracks = self.server.get_all_tracks()
        self.sut.bind_media_server(self.server)
        self.sut.load_track(tracks[1].id)

        self.sut.play()

        with self.assertRaises(Spotifice.PlayerError) as cm:
            self.sut.play()

        self.assertEqual(cm.exception.reason, "Already playing")
