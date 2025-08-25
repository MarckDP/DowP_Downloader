import yt_dlp
from .exceptions import UserCancelledError
import threading 

def get_video_info(url):
    """
    Extrae la información de un video usando yt-dlp.
    Devuelve el diccionario de información o None si hay un error.
    Se ha añadido un timeout para evitar que se quede cargando indefinidamente.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'timeout': 30,
        'client': 'tv',
        'impersonate': True, 
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
        return info_dict
    except yt_dlp.utils.DownloadError as e:
        print(f"Error de yt-dlp al obtener información: {e}")
        return None
    except Exception as e:
        print(f"Un error inesperado ocurrió: {e}")
        return None

def download_media(url, ydl_opts, progress_callback, cancellation_event: threading.Event):
    """
    Descarga y procesa el medio, esperando a que todas las etapas (incluida la fusión) terminen.
    Devuelve la ruta final y definitiva del archivo.
    Se ha añadido un mecanismo de cancelación limpia.
    """

    def hook(d):
        if cancellation_event.is_set():
            raise UserCancelledError("Descarga cancelada por el usuario.")
        status = d.get('status', 'N/A')
        if status == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            if total_bytes > 0:
                percentage = (downloaded_bytes / total_bytes) * 100
                speed = d.get('speed')
                speed_str = f"{speed / 1024:.1f} KB/s" if speed else "N/A"
                progress_callback(percentage, f"Descargando... {percentage:.1f}% a {speed_str}")
        elif status == 'finished':
            progress_callback(100, "Descarga completada. Fusionando archivos si es necesario...")
        elif status == 'error':
            raise yt_dlp.utils.DownloadError("yt-dlp reportó un error durante la descarga.")
    ydl_opts['progress_hooks'] = [hook]
    ydl_opts.setdefault('downloader', 'native')
    try:
        if cancellation_event.is_set():
            raise UserCancelledError("Descarga cancelada por el usuario antes de iniciar.")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
        final_filepath = info_dict.get('filepath')
        if not final_filepath and 'requested_downloads' in info_dict:
            final_filepath = info_dict['requested_downloads'][0].get('filepath')
        if not final_filepath:
            raise Exception("No se pudo determinar la ruta del archivo descargado después del proceso.")
        return final_filepath
    except UserCancelledError as e:
        print(f"DEBUG: Operación de descarga interrumpida: {e}")
        raise e
    except Exception as e:
        print(f"Error en el proceso de descarga de yt-dlp: {e}")
        raise e