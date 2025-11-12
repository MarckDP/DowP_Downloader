import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
import requests
from packaging import version
from main import PROJECT_ROOT, BIN_DIR, FFMPEG_BIN_DIR

DENO_BIN_DIR = os.path.join(BIN_DIR, "deno")
DENO_VERSION_FILE = os.path.join(DENO_BIN_DIR, "deno_version.txt")
FFMPEG_VERSION_FILE = os.path.join(FFMPEG_BIN_DIR, "ffmpeg_version.txt")

def check_and_install_python_dependencies(progress_callback):
    """Verifica e instala dependencias de Python, reportando el progreso."""
    progress_callback("Verificando dependencias de Python...", 5)
    try:
        import customtkinter
        import PIL
        import requests
        import yt_dlp
        import flask_socketio
        import gevent
        progress_callback("Dependencias de Python verificadas.", 15)
        return True
    except ImportError:
        progress_callback("Instalando dependencias necesarias...", 10)
    requirements_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    if not os.path.exists(requirements_path):
        progress_callback("ERROR: No se encontró 'requirements.txt'.", -1)
        return False
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "-r", requirements_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, process.args, output=stdout, stderr=stderr)
        progress_callback("Dependencias instaladas.", 15)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Falló la instalación de dependencias con pip: {e.stderr}")
        progress_callback(f"Error al instalar dependencias.", -1)
        return False

def get_latest_ffmpeg_info(progress_callback):
    """Consulta la API de GitHub para la última versión de FFMPEG."""
    progress_callback("Consultando la última versión de FFmpeg...", 5)
    try:
        api_url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        releases = response.json()
        latest_release_data = next((r for r in releases if r['tag_name'] != 'latest'), None)
        if not latest_release_data:
            return None, None
        tag_name = latest_release_data["tag_name"]
        system = platform.system()
        file_identifier = ""
        if system == "Windows": file_identifier = "win64-gpl.zip"
        elif system == "Linux": file_identifier = "linux64-gpl.tar.xz"
        elif system == "Darwin": file_identifier = "osx64-gpl.zip"
        else: return None, None
        for asset in latest_release_data["assets"]:
            if file_identifier in asset["name"] and "shared" not in asset["name"]:
                progress_callback("Información de FFmpeg encontrada.", 10)
                return tag_name, asset["browser_download_url"]
        return tag_name, None
    except requests.RequestException as e:
        progress_callback(f"Error de red al buscar FFmpeg: {e}", -1)
        return None, None
    except (IndexError, KeyError) as e:
        progress_callback(f"Error en respuesta de API de FFmpeg: {e}", -1)
        return None, None

def download_and_install_ffmpeg(tag, url, progress_callback):
    """Descarga e instala FFMPEG, reportando el progreso de forma optimizada."""
    try:
        file_name = url.split('/')[-1]
        archive_name = os.path.join(PROJECT_ROOT, file_name)
        last_reported_progress = -1
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded_size = 0
            with open(archive_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = 40 + (downloaded_size / total_size) * 40
                        if int(progress) > last_reported_progress:
                            progress_callback(f"Descargando FFmpeg: {downloaded_size / 1024 / 1024:.1f}/{total_size / 1024 / 1024:.1f} MB", progress)
                            last_reported_progress = int(progress)
        progress_callback("Extrayendo archivos de FFmpeg...", 85)
        temp_extract_path = os.path.join(PROJECT_ROOT, "ffmpeg_temp_extract")
        if os.path.exists(temp_extract_path): shutil.rmtree(temp_extract_path)
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(archive_name, 'r') as zip_ref: zip_ref.extractall(temp_extract_path)
        else:
            with tarfile.open(archive_name, 'r:xz') as tar_ref: tar_ref.extractall(temp_extract_path)

        os.makedirs(FFMPEG_BIN_DIR, exist_ok=True)
        bin_content_path = os.path.join(temp_extract_path, os.listdir(temp_extract_path)[0], 'bin')
        for item in os.listdir(bin_content_path):
            dest_path = os.path.join(FFMPEG_BIN_DIR, item) 
            if os.path.exists(dest_path): os.remove(dest_path)
            shutil.move(os.path.join(bin_content_path, item), dest_path)

        shutil.rmtree(temp_extract_path)
        os.remove(archive_name)
        with open(FFMPEG_VERSION_FILE, "w") as f: f.write(tag)
        progress_callback(f"FFmpeg {tag} instalado.", 95)
        return True
    except Exception as e:
        progress_callback(f"Error al instalar FFmpeg: {e}", -1)
        return False
    

def get_latest_deno_info(progress_callback):
    """Consulta la API de GitHub para la última versión de Deno."""
    progress_callback("Consultando la última versión de Deno...", 5)
    try:
        api_url = "https://api.github.com/repos/denoland/deno/releases/latest"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        latest_release_data = response.json()
        
        tag_name = latest_release_data["tag_name"]
        
        system = platform.system()
        file_identifier = ""
        if system == "Windows": file_identifier = "deno-x86_64-pc-windows-msvc.zip"
        elif system == "Linux": file_identifier = "deno-x86_64-unknown-linux-gnu.zip"
        elif system == "Darwin": file_identifier = "deno-x86_64-apple-darwin.zip"
        else: return None, None
        
        for asset in latest_release_data["assets"]:
            if file_identifier in asset["name"]:
                progress_callback("Información de Deno encontrada.", 10)
                return tag_name, asset["browser_download_url"]
                
        return tag_name, None
    except requests.RequestException as e:
        progress_callback(f"Error de red al buscar Deno: {e}", -1)
        return None, None
    except (IndexError, KeyError) as e:
        progress_callback(f"Error en respuesta de API de Deno: {e}", -1)
        return None, None

def download_and_install_deno(tag, url, progress_callback):
    """Descarga e instala Deno en la carpeta bin/deno/."""
    try:
        file_name = url.split('/')[-1]
        archive_name = os.path.join(PROJECT_ROOT, file_name)
        last_reported_progress = -1
        
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded_size = 0
            with open(archive_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk: continue
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = 40 + (downloaded_size / total_size) * 40
                        if int(progress) > last_reported_progress:
                            progress_callback(f"Descargando Deno: {downloaded_size / 1024 / 1024:.1f}/{total_size / 1024 / 1024:.1f} MB", progress)
                            last_reported_progress = int(progress)
                            
        progress_callback("Extrayendo archivos de Deno...", 85)
        
        # Crear el directorio de Deno (bin/deno/)
        os.makedirs(DENO_BIN_DIR, exist_ok=True)
        
        # Extraer el zip
        with zipfile.ZipFile(archive_name, 'r') as zip_ref:
            # El zip de Deno solo contiene el ejecutable (ej: deno.exe)
            for member in zip_ref.namelist():
                if member.lower().startswith('deno'):
                    zip_ref.extract(member, DENO_BIN_DIR)
                    # Moverlo si está en un subdirectorio (aunque Deno no suele hacerlo)
                    extracted_path = os.path.join(DENO_BIN_DIR, member)
                    final_path = os.path.join(DENO_BIN_DIR, os.path.basename(member))
                    if extracted_path != final_path:
                         shutil.move(extracted_path, final_path)
        
        os.remove(archive_name)
        with open(DENO_VERSION_FILE, "w") as f: f.write(tag)
        progress_callback(f"Deno {tag} instalado.", 95)
        return True
    except Exception as e:
        progress_callback(f"Error al instalar Deno: {e}", -1)
        return False

def check_environment_status(progress_callback):
    """
    Verifica el estado del entorno (dependencias, FFmpeg) sin instalar nada.
    Devuelve un diccionario con el estado y la información necesaria para la UI.
    """
    try:
        if not check_and_install_python_dependencies(progress_callback):
            return {"status": "error", "message": "Fallo crítico: No se pudieron instalar las dependencias de Python."}
        
        # --- Paso 1: Comprobar existencia de archivos locales ---
        ffmpeg_path = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
        ffmpeg_exists = os.path.exists(ffmpeg_path)
        
        deno_exe_name = "deno.exe" if platform.system() == "Windows" else "deno"
        deno_path = os.path.join(DENO_BIN_DIR, deno_exe_name)
        deno_exists = os.path.exists(deno_path)

        # --- Paso 2: Obtener versiones locales ---
        local_tag = ""
        if os.path.exists(FFMPEG_VERSION_FILE):
            with open(FFMPEG_VERSION_FILE, 'r') as f:
                local_tag = f.read().strip()

        local_deno_tag = ""
        if os.path.exists(DENO_VERSION_FILE):
            with open(DENO_VERSION_FILE, 'r') as f:
                local_deno_tag = f.read().strip()

        # --- Paso 3: Intentar obtener información de la API ---
        # (Estos pueden ser None si falla la conexión)
        latest_tag, download_url = get_latest_ffmpeg_info(progress_callback)
        latest_deno_tag, deno_download_url = get_latest_deno_info(progress_callback)

        # --- Paso 4: Construir el diccionario de estado FINAL ---
        # Este diccionario siempre se devuelve, incluso si las API fallan.
        return {
            "status": "success", # <-- Siempre es 'success' si Python está bien
            
            "ffmpeg_path_exists": ffmpeg_exists,
            "local_version": local_tag,
            "latest_version": latest_tag,     # (puede ser None)
            "download_url": download_url,     # (puede ser None)
            
            "deno_path_exists": deno_exists,
            "local_deno_version": local_deno_tag,
            "latest_deno_version": latest_deno_tag, # (puede ser None)
            "deno_download_url": deno_download_url  # (puede ser None)
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Error en la verificación del entorno: {e}"}
    
def check_app_update(current_version_str):
    """Consulta GitHub para ver si hay una nueva versión de la app y obtiene la URL del instalador .exe."""
    print(f"INFO: Verificando actualizaciones para la versión actual: {current_version_str}")
    try:
        # --- CAMBIO 1: URL del nuevo repositorio ---
        api_url = "https://api.github.com/repos/MarckDP/DowP_App_y_Extension/releases"

        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        releases = response.json()

        if not releases:
            return {"update_available": False}

        # Encontrar la release más reciente (no pre-release a menos que no haya otra)
        latest_release = None
        for r in releases:
            if not r.get("prerelease", False):
                latest_release = r
                break
        if not latest_release: # Si solo hay pre-releases, toma la primera
            latest_release = releases[0]

        latest_version_str = latest_release.get("tag_name", "0.0.0").lstrip('v')
        release_url = latest_release.get("html_url") # Mantenemos la URL de la página por si acaso

        # --- CAMBIO 2: Buscar la URL de descarga del .exe ---
        installer_url = None
        expected_filename_prefix = f"DowP_v{latest_version_str}_setup"
        for asset in latest_release.get("assets", []):
            if asset.get("name", "").startswith(expected_filename_prefix) and asset.get("name", "").endswith(".exe"):
                installer_url = asset.get("browser_download_url")
                break # Encontramos el .exe, salimos del bucle

        current_v = version.parse(current_version_str)
        latest_v = version.parse(latest_version_str)

        if latest_v > current_v:
            print(f"INFO: ¡Actualización encontrada! Nueva versión: {latest_version_str}")
            return {
                "update_available": True,
                "latest_version": latest_version_str,
                "release_url": release_url, # URL de la página
                # --- CAMBIO 3: Devolver la URL del instalador ---
                "installer_url": installer_url, # URL directa al .exe (puede ser None si no se encontró)
                "is_prerelease": latest_release.get("prerelease", False)
            }
        else:
            print("INFO: La aplicación está actualizada.")
            return {"update_available": False}

    except requests.RequestException as e:
        print(f"ERROR: No se pudo verificar la actualización de la app (error de red): {e}")
        return {"error": "No se pudo conectar para verificar."}
    except Exception as e:
        print(f"ERROR: Ocurrió un error inesperado al verificar la actualización: {e}")
        return {"error": "Ocurrió un error inesperado."}