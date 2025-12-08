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
    exception PlaylistError extends Error{};
    exception AuthError extends Error{};  // new in version 2

    interface MusicLibrary {
        TrackInfoSeq get_all_tracks() throws IOError;
        TrackInfo get_track_info(string track_id) throws IOError, TrackError;
    };

    sequence<string> TrackIdSeq;

    struct Playlist {
        string id;
        string name;
        string description;
        string owner;
        long created_at;
        TrackIdSeq track_ids;
    };

    sequence<Playlist> PlaylistSeq;

    interface PlaylistManager {
        idempotent PlaylistSeq get_all_playlists();
        idempotent Playlist get_playlist(string playlist_id) throws PlaylistError;
    };

    // new in version 2
    struct UserInfo {
        string username;
        string fullname;
        string email;
        bool is_premium;
        long created_at;
    };

    // new in version 2
    interface Session {
        idempotent UserInfo get_user_info();
        idempotent void close();
    };

    // new in version 2
    ["deprecate:StreamManager is deprecated, use authenticate()"]
    interface StreamManager {};

    // new in version 2
    interface SecureStreamManager extends Session {
        idempotent void open_stream(string track_id) throws IOError, TrackError;
        idempotent void close_stream();
        AudioChunk get_audio_chunk(int chunk_size) throws IOError, StreamError;
    };

    interface MediaRender;

    // new in version 2
    interface AuthManager {
        SecureStreamManager* authenticate(
            MediaRender* media_render, string username, string password)
            throws AuthError, BadReference;
    };

    interface MediaServer extends MusicLibrary, PlaylistManager, AuthManager {};

    enum PlaybackState {
        STOPPED,
        PLAYING,
        PAUSED
    };

    class PlaybackStatus {
        PlaybackState state;
        string current_track_id;
        bool repeat;
    };

    interface RenderConnectivity {
        // modified in version 2
        idempotent void bind_media_server(
            MediaServer* media_server, SecureStreamManager* stream_manager)
            throws BadReference;
        idempotent void unbind_media_server();
    };

    interface ContentManager {
        idempotent TrackInfo get_current_track();
        idempotent void load_track(string track_id)
            throws BadReference, PlayerError, StreamError, TrackError;
        idempotent void load_playlist(string playlist_id)
            throws PlaylistError, TrackError, PlayerError;
    };

    interface PlaybackController {
        void play() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void stop() throws PlayerError;
        void pause() throws PlayerError;
        idempotent PlaybackStatus get_status();
        void next() throws PlaylistError;
        void previous() throws PlaylistError;
        idempotent void set_repeat(bool value);
    };

    interface MediaRender extends PlaybackController, ContentManager, RenderConnectivity {};
};
