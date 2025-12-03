import Ice

from media_server import Spotifice, main

from .icetest import IceTestCase


class TestServer(IceTestCase):
    server_port = 10000

    def setUp(self):
        server_props = {
            'MediaServerAdapter.Endpoints': f'tcp -p {self.server_port}',
            'MediaServer.Content': 'test/media'
        }
        server_endpoint = f'mediaServer1:default -p {self.server_port} -t 500'
        self.create_server(main, server_props)
        self.sut = self.create_proxy(server_endpoint, Spotifice.MediaServerPrx)


class MusicLibraryTests(TestServer):
    def test_get_all_tracks(self):
        tracks = self.sut.get_all_tracks()
        self.assertEqual(len(tracks), 4)
        self.assertEqual(tracks[0].id, '1s.mp3')

    def test_get_track_info(self):
        track = self.sut.get_track_info('1s.mp3')
        self.assertEqual(track.id, '1s.mp3')
        self.assertEqual(track.title, '1s')

    def test_get_track_info_wrong_track(self):
        with self.assertRaises(Spotifice.TrackError) as cm:
            self.sut.get_track_info('bad-track-id')

        self.assertEqual(cm.exception.item, 'bad-track-id')
        self.assertEqual(cm.exception.reason, 'Track not found')


class StreamManagerTests(TestServer):
    def test_open_stream_wrong_track(self):
        track_id = 'bad-track-id'
        render_id = self.client_ic.stringToIdentity('bad-render-id')

        with self.assertRaises(Spotifice.TrackError) as cm:
            self.sut.open_stream(track_id, render_id)

        self.assertEqual(cm.exception.item, 'bad-track-id')
        self.assertEqual(cm.exception.reason, 'Track not found')

    def test_open_stream_wrong_render(self):
        tracks = self.sut.get_all_tracks()
        track_id = tracks[0].id
        render_id = Ice.Identity(name='')

        with self.assertRaises(Spotifice.BadIdentity) as cm:
            self.sut.open_stream(track_id, render_id)

        self.assertEqual(cm.exception.item, '')
        self.assertEqual(cm.exception.reason, 'Invalid render identity')

    def test_get_audio_chunk(self):
        track_id = self.sut.get_all_tracks()[0].id
        render_id = Ice.Identity(name='fake-render-id')

        self.sut.open_stream(track_id, render_id)
        chunk = self.sut.get_audio_chunk(render_id, 1024)

        self.assertGreater(len(chunk), 0)

        # check same bytes as actual file
        with open('test/media/1s.mp3', 'rb') as f:
            expected = f.read(len(chunk))
            self.assertEqual(chunk, expected)

    def test_get_audio_chunk_not_open_stream(self):
        render_id = Ice.Identity(name='missing-render-id')

        with self.assertRaises(Spotifice.StreamError) as cm:
            self.sut.get_audio_chunk(render_id, 1024)

        self.assertEqual(cm.exception.item, 'missing-render-id')
        self.assertEqual(cm.exception.reason, 'No open stream for render')
