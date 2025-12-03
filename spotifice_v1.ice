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
    exception PlaylistError extends Error{};  // new in version 1

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

    // new in version 1
    sequence<string> TrackIdSeq;

    // new in version 1
    struct Playlist {
        string id;
        string name;
        string description;
        string owner;
        long created_at;
        TrackIdSeq track_ids;
    };

    // new in version 1
    sequence<Playlist> PlaylistSeq;

    // new in version 1
    interface PlaylistManager {
        idempotent PlaylistSeq get_all_playlists();
        idempotent Playlist get_playlist(string playlist_id) throws PlaylistError;
    };

    interface MediaServer extends MusicLibrary, StreamManager, PlaylistManager {};

    // new in version 1
    enum PlaybackState {
        STOPPED,
        PLAYING,
        PAUSED
    };

    // new in version 1
    class PlaybackStatus {
        PlaybackState state;
        string current_track_id;
        bool repeat;
    };

    interface RenderConnectivity {
        idempotent void bind_media_server(MediaServer* media_server) throws BadReference;
        idempotent void unbind_media_server();
    };

    interface ContentManager {
        idempotent void load_track(string track_id)
            throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent TrackInfo get_current_track();

        // new in version 1
        idempotent void load_playlist(string playlist_id)
            throws PlaylistError, TrackError, PlayerError;
    };

    interface PlaybackController {
        void play() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void stop() throws PlayerError;

        // new in version 1
        void pause() throws PlayerError;
        idempotent PlaybackStatus get_status();
        void next() throws PlaylistError;
        void previous() throws PlaylistError;
        idempotent void set_repeat(bool value);
    };

    interface MediaRender extends RenderConnectivity, ContentManager, PlaybackController {};
};
