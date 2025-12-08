import Ice
import sys

# Importar el módulo generado a partir del Slice
# (Asegúrate de haber compilado tu archivo .ice con ice-slice)
try:
    import Spotifice
except ImportError:
    print("Error: No se encontró el módulo Spotifice. Asegúrate de haber compilado el Slice.")
    sys.exit(1)

# Creamos el comunicador con la configuración del Locator
class Client(Ice.Application):
    def run(self, args):
        # 1. Configuración del Locator
        locator_proxy = "IceGrid/Locator:tcp -h 127.0.0.1 -p 4061"
        self.communicator().getProperties().setProperty("Ice.Default.Locator", locator_proxy)
        print(f"Buscando Locator en: {locator_proxy}")

        # 2. Obtener el proxy indirecto por identidad (Proxy Indirecto)
        # "ClientServer" es la identidad definida en el Spotifice.xml
        proxy = self.communicator().stringToProxy("ClientServer")
        
        if not proxy:
            print("Error: No se pudo obtener el proxy 'ClientServer'.")
            return 1
        
        # 3. Cast del proxy a la interfaz de Spotifice
        try:
            # Asume que ClientI es tu interfaz principal
            client_service = Spotifice.ClientIPrx.checkedCast(proxy)
        except Ice.Exception as e:
            print(f"Error de casting: {e}")
            return 1

        if not client_service:
            print("Error: Proxy obtenido, pero el servidor no está disponible o la interfaz es incorrecta.")
            return 1

        # 4. Llamada de prueba (Adaptar a tu interfaz IDL)
        print("Conexión exitosa al servicio ClientServer a través del Locator.")
        # Llama a alguna función sencilla de tu interfaz IDL
        try:
            # Reemplaza 'getPlaylist' y 'mi_usuario' con una llamada real de tu IDL
            client_service.someTestFunction() 
            print("Llamada de prueba (someTestFunction) ejecutada con éxito.")
        except AttributeError:
             print("Advertencia: No se encontró la función de prueba. Solo se verificó la conexión.")
        except Ice.LocalException as e:
             print(f"Error durante la llamada remota (Proxy válido, pero falló la comunicación): {e}")

        return 0

if __name__ == '__main__':
    # Usamos try-except para manejar la inicialización de Ice
    try:
        app = Client()
        sys.exit(app.main(sys.argv))
    except Exception as e:
        print(f"Fallo general del cliente: {e}")
        sys.exit(1)