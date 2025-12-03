#!/usr/bin/env python3

import logging
import sys
from contextlib import contextmanager

import Ice
from Ice import identityToString as id2str

from gst_player import GstPlayer

Ice.loadSlice('-I{} spotifice_v2.ice'.format(Ice.getSliceDir()))
import Spotifice  # type: ignore # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MediaRender")


class MediaRenderI(Spotifice.MediaRender):
    def __init__(self, player):
        self.player = player
        self.server: Spotifice.MediaServerPrx = None
        self.stream_manager: Spotifice.SecureStreamManagerPrx = None # Guardo el proxy de SecureStreamManager

        self.current_track = None
        self.current_playlist = None
        self.playlist_index = 0
        self.repeat = False #Repetición desactivada por defecto
        self.history = []  #Historial de pistas reproducidas para previous
    
    def ensure_player_stopped(self):
        if self.player.is_playing():
            raise Spotifice.PlayerError(reason="Already playing")

    def ensure_server_bound(self):
        if not self.server:
            raise Spotifice.BadReference(reason="No MediaServer bound")

    # --- RenderConnectivity ---

    def bind_media_server(self, media_server, stream_manager, current=None): #Modifico el bind para poder recibir también el stream_manager
        try:
            media_server.ice_ping()
            stream_manager.ice_ping()
        except Ice.ConnectionRefusedException as e:
            raise Spotifice.BadReference(reason=f"MediaServer not reachable: {e}")

        self.server = media_server
        self.stream_manager = stream_manager #Guargo la referencia de la sesión de SecureStreamManager para poder usarla en el play
        self.history = [] #Reinicio el historial si cambio de servidor
        logger.info(f"Bound to MediaServer '{id2str(media_server.ice_getIdentity())}'")

    def unbind_media_server(self, current=None):
        self.stop(current)
        if self.stream_manager:
            try:
                self.stream_manager.close()
            except Exception as e:
                logger.warning(f"Error cerrando sesion: {e}")
        self.server = None
        self.stream_manager = None
        logger.info("Unbound MediaServer")

    # --- ContentManager ---

    def load_track(self, track_id, current=None):
        self.ensure_server_bound()

        try:
            with self.keep_playing_state(current):

                if self.current_track:
                    self.history.append(self.current_track.id) #Añado la pista actual al historial antes de cambiar.
              
                self.current_track = self.server.get_track_info(track_id)
                self.current_playlist = None
                self.playlist_index = 0

            logger.info(f"Current track set to: {self.current_track.title}")

        except Spotifice.TrackError as e:
            logger.error(f"Error setting track: {e.reason}")
            raise

    def get_current_track(self, current=None):
        return self.current_track

    #--- PlaylistManager ---
    def load_playlist(self, playlist_id, current=None):
        self.ensure_server_bound() 

        with self.keep_playing_state(current):
            self.current_playlist = self.server.get_playlist(playlist_id) #Obtengo la información de la playlist al servidor
            self.playlist_index = 0
        
            self.history = [] #Reinicio el historial al cargar una nueva playlist
            logger.info(f"Playlist loaded: {self.current_playlist.name}. History reset.")
        
            #Compruebo si la playlist tiene pistas
            if self.current_playlist.track_ids:
             first_track_id = self.current_playlist.track_ids[0]
             self.current_track = self.server.get_track_info(first_track_id) #Cargo la primera pista de la playlist
             logger.info(f"Loaded playlist: {self.current_playlist.name}, first track: {self.current_track.title}")
            
            else:
              self.current_track = None 
              logger.info(f"Loaded playlist: {self.current_playlist.name}, but it is empty.")

    # --- PlaybackController ---

    @contextmanager
    def keep_playing_state(self, current):
        #Obtengo el estado inicial del player
        initial_state = self.player.get_state()
        
        #Si no estaba parado, lo detengo antes de cambiar la pista
        if initial_state != 'STOP':
            self.stop(current)
        try:
            yield #Aquí realizo el cambio de pista
        finally:
            if initial_state == 'PLAYING': #Si estaba reproduciendo, vuelvo a reproducir la nueva pista
                self.play(current)
                

    def play(self, current=None):
        def get_chunk_hook(chunk_size):
            try:
                return self.stream_manager.get_audio_chunk(chunk_size)
            except Spotifice.IOError as e:
                logger.error(e)
            except Ice.Exception as e:
                logger.critical(e)
                
        # Función para manejar la repetición de una pista individual
        def handle_individual_repeat():
            # Si la repetición está activada y no hay playlist, repito la pista
            if self.repeat and not self.current_playlist:
                logger.info("Individual track finished, repeating...")
                try:
                    self.stream_manager.open_stream(self.current_track.id) #Abro el stream de la pista actual
                    self.player.configure(get_chunk_hook, track_exhausted_hook=handle_individual_repeat) #Reconfiguro el player con el hook
                    self.player.confirm_play_starts() #Confirmo que la reproducción ha comenzado
                    
                except Exception as e:
                    logger.error(f"Failed to repeat track: {e}")
                    
            else:
                logger.debug("Track finished, not repeating.")
                

        assert current, "remote invocation required"

        self.ensure_server_bound()
        player_state = self.player.get_state() #Obtengo el estado actual de GstPlayer

        if player_state == 'PAUSED':
            self.player.resume() #Reanudo la reproducción si estaba en pausa
            logger.info("Resuming playback")
            return
        
        if player_state == 'PLAYING':
            raise Spotifice.PlayerError(reason="Already playing")
        
        if not self.current_track:
            raise Spotifice.TrackError(reason="No track loaded")

        try:
            self.stream_manager.open_stream(self.current_track.id)
        except Spotifice.BadIdentity as e:
            logger.error(f"Error starting stream: {e.reason}")
            raise Spotifice.StreamError(reason="Stream setup failed")

        self.player.configure(get_chunk_hook, track_exhausted_hook=handle_individual_repeat)

        if not self.player.confirm_play_starts():
            raise Spotifice.PlayerError(reason="Failed to confirm playback")

    
    def pause(self, current=None):
        if not self.player.is_playing():
            raise Spotifice.PlayerError(reason="Not currently playing") #Si no se está reproduciendo nada, no lo puedo pausar.

        self.player.pause() #Pauso la reproducción
        logger.info("Paused playback")
    
    def get_status(self, current=None):
        player_state = self.player.get_state() #Obtengo el estado actual de GstPlayer
        
        #Convierto el string de GstPlayer al enum de PlaybackState de Ice
        if player_state == 'PLAYING':
            playback_state = Spotifice.PlaybackState.PLAYING
        elif player_state == 'PAUSED':
            playback_state = Spotifice.PlaybackState.PAUSED
        else:
            playback_state = Spotifice.PlaybackState.STOPPED

        # Obtengo el ID de la pista actual, si no hay pista, devuelvo cadena vacía
        if self.current_track:
            current_id = self.current_track.id
        else:
            current_id = ""

        #Creo y devuelvo el objeto PlaybackStatus
        return Spotifice.PlaybackStatus(
            state = playback_state,
            current_track_id = current_id,
            repeat = self.repeat
        )
    def next(self, current=None):
        if not self.current_playlist: #Si no hay ninguna playlist cargada, no puedo hacer next a la siguiente.
            logger.info("No playlist loaded, cannot go to next track.")
            return
        #Guardo la pista actual en el historial antes de avanzar.
        if self.current_track:
            self.history.append(self.current_track.id)

        num_tracks = len(self.current_playlist.track_ids) #Obtengo el número total de pistas en la playlist
        
        #Compruebo si hay una siguiente pista en la playlist
        if self.playlist_index + 1 < num_tracks:
            self.playlist_index += 1
            new_track_id = self.current_playlist.track_ids[self.playlist_index] #Obtengo el id de la siguiente pista
            with self.keep_playing_state(current):
                self.current_track = self.server.get_track_info(new_track_id) #Cargo la nueva pista
            logger.info(f"Playing next track: {self.current_track.title}")
        
        #Si estamos al final de la playlist y la opción repeat está activada, vuelvo al inicio
        elif self.repeat and num_tracks > 0:
             self.playlist_index = 0
             new_track_id = self.current_playlist.track_ids[self.playlist_index] #Obtengo el id de la primera pista
             with self.keep_playing_state(current):
                    self.current_track = self.server.get_track_info(new_track_id) #Cargo la nueva pista
             logger.info(f"Reached end of playlist, repeating from start: {self.current_track.title}")
        
        else: #Si no hay mas pistas y repeat está desactivado, no se avanza de pista
            logger.warning("Reached end of playlist, no more tracks to play.")
            if self.history:
                self.history.pop() #Elimino la pista actual del historial ya que no se ha cambiado.

    def previous(self, current=None):
        #Si no hay pistas en el historial, no puedo retroceder.
        if not self.history:
            logger.warning("No previous track available in history.")
            return
        
        last_track_id = self.history.pop() #Obtengo el id de la última pista del historial
        
        #Cargo la pista anterior manteniendo el estado de reproducción
        with self.keep_playing_state(current):
            self.current_track = self.server.get_track_info(last_track_id) #Cargo la pista anterior
        
        #Si la pista anterior está en la playlist actual, actualizo el índice de la playlist
        if self.current_playlist and last_track_id in self.current_playlist.track_ids:
            self.playlist_index = self.current_playlist.track_ids.index(last_track_id)
        else: #Si no está en la playlist actual, salgo del modo playlist
            self.current_playlist = None
            self.playlist_index = 0
        
        logger.info(f"Playing previous track: {self.current_track.title} from history.")

    def set_repeat(self,repeat, current=None):
        self.repeat = repeat
        logger.info(f"Set repeat to: {self.repeat}")

    def stop(self, current=None):
        if self.stream_manager:
            try:
                self.stream_manager.close_stream()
            except Exception: pass

        if not self.player.stop():
            raise Spotifice.PlayerError(reason="Failed to confirm stop")

        logger.info("Stopped")


def main(ic, player):
    servant = MediaRenderI(player)

    adapter = ic.createObjectAdapter("MediaRenderAdapter")
    proxy = adapter.add(servant, ic.stringToIdentity("mediaRender1"))
    logger.info(f"MediaRender: {proxy}")

    adapter.activate()
    ic.waitForShutdown()

    logger.info("Shutdown")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: media_render.py <config-file>")

    player = GstPlayer()
    player.start()
    try:
        with Ice.initialize(sys.argv[1]) as communicator:
            main(communicator, player)
    except KeyboardInterrupt:
        logger.info("Server interrupted by user.")
    finally:
        player.shutdown()