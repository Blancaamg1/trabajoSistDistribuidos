#!/usr/bin/env python3

import logging
import json
import sys
import hashlib
import secrets
from pathlib import Path
from datetime import datetime

import Ice
from Ice import identityToString as id2str

Ice.loadSlice('-I{} spotifice_v2.ice'.format(Ice.getSliceDir()))
import Spotifice  # type: ignore # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MediaServer")


class StreamedFile:
    def __init__(self, track_info, media_dir):
        self.track = track_info
        filepath = media_dir / track_info.filename

        try:
            self.file = open(filepath, 'rb')
        except Exception as e:
            raise Spotifice.IOError(track_info.filename, f"Error opening media file: {e}")

    def read(self, size):
        return self.file.read(size)

    def close(self):
        try:
            if self.file:
                self.file.close()
        except Exception as e:
            logger.error(f"Error closing file for track '{self.track.id}': {e}")

    def __repr__(self):
        return f"<StreamState '{self.track.id}'>"

#Implemento la nueva interfaz que añade la gestión de sesiones de los usuarios
class SecureStreamManagerI(Spotifice.SecureStreamManager):
    def __init__(self, user_info, media_dir, tracks_library):
        self.user = user_info #Guardo la información del usuario de esta sesión para saber quién está escuchando
        self.media_dir = media_dir
        self.tracks_library = tracks_library
        self.current_stream = None
        logger.info(f"New session created for user: {user_info.username}")

    #Método que devuelve la información del usuario asociado a esta sesión
    def get_user_info(self, current=None):
        return self.user
    
    #Método que cierra la sesión del usuario y además limpia la memoria cerrando cualquier stream abierto
    def close(self, current=None):
        logger.info(f"Session closed for user: {self.user.username}")
        self.close_stream(current)
        current.adapter.remove(current.id)

    def open_stream(self, track_id, current=None): #Ya no necesito el render_id debido a que cada usuario tiene su propia sesión privada
        if track_id not in self.tracks_library:
            raise Spotifice.TrackError(track_id, "Track not found")

        if self.current_stream:
            self.current_stream.close()

        self.current_stream = StreamedFile(self.tracks_library[track_id], self.media_dir)

        logger.info(f"Open stream for track '{track_id}'")

    def close_stream(self, current=None):
        if self.current_stream:
            self.current_stream.close()
            self.current_stream=None
            logger.info("Closed stream")

    def get_audio_chunk(self, chunk_size, current=None):
        streamed_file = self.current_stream

        if not streamed_file:
            raise Spotifice.StreamError("Session", "No open stream for render")

        try:
            data = streamed_file.read(chunk_size)
            if not data:
                logger.info(f"Track exhausted: '{streamed_file.track.id}'")
                self.close_stream(current)
            return data

        except Exception as e:
            raise Spotifice.IOError(
                streamed_file.track.filename, f"Error reading file: {e}" 
            )




class MediaServerI(Spotifice.MediaServer):
    def __init__(self, media_dir, playlist_dir, users_file): #Añado users_file al constructor
        self.media_dir = Path(media_dir)
        self.playlist_dir = Path(playlist_dir)
        self.users_file = Path(users_file) #Guardo la ruta del fichero de usuarios

        self.tracks = {}
        self.playlists = {}
        self.users_db = {} 
        
        self.load_media()
        self.load_playlists()  
        self.load_users()

    def ensure_track_exists(self, track_id):
        if track_id not in self.tracks:
            raise Spotifice.TrackError(track_id, "Track not found")

    def load_media(self):
        for filepath in sorted(Path(self.media_dir).iterdir()):
            if not filepath.is_file() or filepath.suffix.lower() != ".mp3":
                continue

            self.tracks[filepath.name] = self.track_info(filepath)

        logger.info(f"Load media:  {len(self.tracks)} tracks")
    
    #Método para cargar los usuarios desde el fichero JSON
    def load_users(self):
        if not self.users_file.exists():
            logger.warning(f"Users file does not found: {self.users_file}")
            return

        try:
            with open(self.users_file, 'r', encoding='utf-8') as f:
                  raw_users = json.load(f)

            for username, data in raw_users.items():
                created_at_ts = 0
                date_str = data.get("created_at", "")
                if date_str:
                    try:
                        dt_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
                        created_at_ts = int(dt_obj.timestamp())
                    except ValueError:
                        logger.warning(f"Invalid date format for user '{username}': {date_str}. Using default timestamp")

                data['created_at_ts'] = created_at_ts
                self.users_db[username] = data #Guardo la información del usuario

            logger.info(f"Loaded users: {len(self.users_db)}")
        except Exception as e:
            logger.error(f"Error loading users from '{self.users_file}': {e}")

    
    @staticmethod
    def track_info(filepath):
        return  Spotifice.TrackInfo(
            id=filepath.name,
            title=filepath.stem,
            filename=filepath.name)

    def load_playlists(self):
        # Compruebo que la ruta de las playlists existe y es un directorio
        if not self.playlist_dir.exists() or not self.playlist_dir.is_dir(): 
            logger.warning("Playlist directory does not exist or is not a directory.")
            return
        #Itero sobre todos los archivos del directorio de playlists
        for filepath in sorted(self.playlist_dir.iterdir()):
            if not filepath.is_file() or filepath.suffix.lower() != ".playlist": #Ignoro los archivos que no son .playlist
                continue
            try:
                #Abro el archivo y cargo su contenido JSON
                with open(filepath, 'r', encoding='utf-8') as fd:
                    data = json.load(fd)
                    created_at_timestamp = 0 # Valor por defecto si no se proporciona una fecha válida (1 de enero de 1970)
                    date_str_input = data.get("created_at", "") #Obtengo la fecha de creación del JSON
                    
                    # Si se proporciona una fecha, intento convertirla a timestamp
                    if date_str_input:
                        try:
                            date_obj = datetime.strptime(date_str_input, "%d-%m-%Y") #Utilizo el formato dia-mes-año, creando un objeto datetime
                            created_at_timestamp = int(date_obj.timestamp()) #Convierto la fecha a timestamp(long)
                        except ValueError:
                            logger.warning(f"Formato de fecha no 'DD-MM-YYYY' en {filepath.name}: {date_str_input}. Usando valor por defecto (1 de enero de 1970).") #Manejo el error de formato de fecha lanznando una advertencia
        
                    valid_track_ids = [tid for tid in data.get("track_ids", []) if tid in self.tracks] #Filtro las listas de tracks para incluir solo las que existen en el servidor

                    #Creo el objeto Playlist
                    playlist = Spotifice.Playlist(
                        id=data["id"],
                        name=data["name"],
                        description=data.get("description", ""),
                        owner=data.get("owner", ""),
                        created_at=created_at_timestamp,
                        track_ids=valid_track_ids,
                    )
                    self.playlists[playlist.id] = playlist #Añado la playlist cargada al diccionario del servidor
            except Exception as e:
                logger.error(f"Error loading playlist from '{filepath.name}': {e}")
        
        logger.info(f"Load playlists: {len(self.playlists)} playlists")
    
    def get_all_playlists(self, current=None):
        # Devuelvo una lista con todas las playlists cargadas
        return list(self.playlists.values())
    
    def get_playlist(self, playlist_id, current=None):
        # Compruebo si el id de la playlist existe
        if playlist_id not in self.playlists:
            raise Spotifice.PlaylistError(playlist_id, "Playlist not found") #Lanzo la excepcion si no se encuentra
        return self.playlists[playlist_id] #Devuelvo la playlist solicitada

    # ---- MusicLibrary ----
    def get_all_tracks(self, current=None):
        return list(self.tracks.values())

    def get_track_info(self, track_id, current=None):
        self.ensure_track_exists(track_id)
        return self.tracks[track_id]

    # Implementación de AuthManager, que se encarga de verificar las credenciales de los usuarios

    #Miro si el usuario existe en mi diccionario de usuarios
    def authenticate(self, media_render, username, password, current=None):
        if username not in self.users_db:
            raise Spotifice.AuthError(username, "User not found")
        
        user_data = self.users_db[username]

        #Calculo el hash de la contraseña introducida por el usuario. MD5(contraseña que me pasan + salt guardada)
        calc = hashlib.md5((password + user_data["salt"]).encode('utf-8')).hexdigest()
        if not secrets.compare_digest(calc, user_data["digest"]): #Comparo los hashes de las contraseñas
            raise Spotifice.AuthError(username, "Invalid password")
        
        # Si las credenciales son correctas, creo un UserInfo con los datos del usuario
        user_info = Spotifice.UserInfo(
            username=username,
            fullname=user_data.get("fullname", ""),
            email=user_data.get("email", ""),
            is_premium=user_data.get("is_premium", False),
            created_at=user_data["created_at_ts"]
        )
        #Aqui creo una factoria de objetos remotos, para ello instancio una nueva clase SecureStreamManagerI exclusiva 
        # para este usuario y la registro dinamicamente en el adaptador de Ice
        stream_servant = SecureStreamManagerI(user_info, self.media_dir, self.tracks)
        proxy = current.adapter.addWithUUID(stream_servant) 
        logger.info(f"User '{username}' authenticated successfully")

        return Spotifice.SecureStreamManagerPrx.uncheckedCast(proxy)
    # # ---- StreamManager ----
    # def open_stream(self, track_id, render_id, current=None):
    #     str_render_id = id2str(render_id)
    #     self.ensure_track_exists(track_id)

    #     if not render_id.name:
    #         raise Spotifice.BadIdentity(str_render_id, "Invalid render identity")

    #     self.active_streams[str_render_id] = StreamedFile(
    #         self.tracks[track_id], self.media_dir)

    #     logger.info("Open stream for track '{}' on render '{}'".format(
    #         track_id, str_render_id))

    # def close_stream(self, render_id, current=None):
    #     str_render_id = id2str(render_id)
    #     if stream_state := self.active_streams.pop(str_render_id, None):
    #         stream_state.close()
    #         logger.info(f"Closed stream for render '{str_render_id}'")

    # def get_audio_chunk(self, render_id, chunk_size, current=None):
    #     str_render_id = id2str(render_id)
    #     try:
    #         streamed_file = self.active_streams[str_render_id]
    #     except KeyError:
    #         raise Spotifice.StreamError(str_render_id, "No open stream for render")

    #     try:
    #         data = streamed_file.read(chunk_size)
    #         if not data:
    #             logger.info(f"Track exhausted: '{streamed_file.track.id}'")
    #             self.close_stream(render_id, current)
    #         return data

    #     except Exception as e:
    #         raise Spotifice.IOError(
    #             streamed_file.track.filename, f"Error reading file: {e}")

def main(ic):
   properties = ic.getProperties()
   media_dir = properties.getPropertyWithDefault('MediaServer.Content', 'media')
   playlist_dir = properties.getPropertyWithDefault('MediaServer.Playlists', 'playlists')
   users_file = properties.getPropertyWithDefault('MediaServer.UsersFile', 'users.json')

   adapter = ic.createObjectAdapter("MediaServerAdapter")
   servant = MediaServerI(Path(media_dir), Path(playlist_dir), Path(users_file))
   server_identity = ic.getProperties().getProperty("Ice.ProgramName")
   proxy = adapter.add(servant, ic.stringToIdentity(server_identity))
   #proxy = adapter.add(servant, ic.stringToIdentity("mediaServer1"))

   logger.info(f"MediaServer: {proxy}")

   adapter.activate()
   ic.waitForShutdown()

   logger.info("Shutdown")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: media_server.py <config-file>")

    # 1. Crear propiedades base cogiendo los argumentos de consola (Lo que manda IceGrid)
    props = Ice.createProperties(sys.argv)
    
    # 2. Cargar explícitamente tu fichero de configuración encima
    props.load(sys.argv[1])
    
    # 3. Preparar los datos de inicialización
    init_data = Ice.InitializationData()
    init_data.properties = props

    try:
        # 4. Inicializar usando esos datos combinados
        with Ice.initialize(sys.argv, init_data) as communicator:
            main(communicator)
    except KeyboardInterrupt:
        logger.info("Server interrupted by user.")
