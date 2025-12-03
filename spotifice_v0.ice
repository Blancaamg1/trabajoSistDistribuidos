[["underscore"]]
#include <Ice/Identity.ice>

module Spotifice {
    class TrackInfo {
        string id;
        string title;
        string filename;
    };

    sequence<byte> AudioChunk;
    sequence<TrackInfo> TrackInfoSeq;

    exception Error {
        optional(1) string item;
        string reason;
    };

    exception IOError extends Error{};
    exception BadIdentity extends Error{};
    exception BadReference extends Error{};
    exception PlayerError extends Error{};
    exception StreamError extends Error{};
    exception TrackError extends Error{};

    interface MusicLibrary {
        TrackInfoSeq get_all_tracks() throws IOError;
        TrackInfo get_track_info(string track_id) throws IOError, TrackError;
    };

    interface StreamManager {
        idempotent void open_stream(string track_id, Ice::Identity media_render_id)
            throws BadIdentity, IOError, TrackError;
        idempotent void close_stream(Ice::Identity media_render_id);
        AudioChunk get_audio_chunk(Ice::Identity media_render_id, int chunk_size)
            throws IOError, StreamError;
    };

    interface MediaServer extends MusicLibrary, StreamManager {};

    interface RenderConnectivity {
        idempotent void bind_media_server(MediaServer* media_server) throws BadReference;
        idempotent void unbind_media_server();
    };

    interface ContentManager {
        idempotent void load_track(string track_id)
            throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent TrackInfo get_current_track();
    };

    interface PlaybackController {
        void play() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void stop() throws PlayerError;
    };

    interface MediaRender extends RenderConnectivity, ContentManager, PlaybackController {};
};
