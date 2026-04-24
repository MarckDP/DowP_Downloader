import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
import requests

from packaging import version
from main import PROJECT_ROOT, BIN_DIR, FFMPEG_BIN_DIR, REMBG_MODELS_DIR, UPSCALING_DIR
from src.core.constants import UPSCALING_TOOLS, FFMPEG_SAFE_VERSION, FFMPEG_SAFE_URL 

DENO_BIN_DIR = os.path.join(BIN_DIR, "deno")
POPPLER_BIN_DIR = os.path.join(BIN_DIR, "poppler") 
INKSCAPE_BIN_DIR = os.path.join(BIN_DIR, "inkscape")
GHOSTSCRIPT_BIN_DIR = os.path.join(BIN_DIR, "ghostscript")
YTDLP_BIN_DIR = os.path.join(BIN_DIR, "ytdlp")

# --- ARCHIVOS DE VERSIÓN ---
DENO_VERSION_FILE = os.path.join(DENO_BIN_DIR, "deno_version.txt")
FFMPEG_VERSION_FILE = os.path.join(FFMPEG_BIN_DIR, "ffmpeg_version.txt")
POPPLER_VERSION_FILE = os.path.join(POPPLER_BIN_DIR, "poppler_version.txt")
INKSCAPE_VERSION_FILE = os.path.join(INKSCAPE_BIN_DIR, "inkscape_version.txt")
YTDLP_VERSION_FILE = os.path.join(YTDLP_BIN_DIR, "ytdlp_version.txt")

def check_and_install_python_dependencies(progress_callback):
    """Verifica e instala dependencias de Python, reportando el progreso."""
    # Saltarse comprobaciones en un .exe compilado
    if getattr(sys, 'frozen', False):
        progress_callback("Ejecutable compilado detectado.", 15)
        return True
        
    progress_callback("Verificando dependencias de Python...", 5)
    
    import importlib.util
    required_packages = ['customtkinter', 'PIL', 'requests', 'flask_socketio', 'gevent', 'py7zr', 'rembg']
    missing_packages = []
    
    for pkg in required_packages:
        if importlib.util.find_spec(pkg) is None:
            missing_packages.append(pkg)
            
    if not missing_packages:
        progress_callback("Dependencias de Python verificadas.", 15)
        return True

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

# ==========================================================
# YT-DLP (ZipApp dinámico)
# ==========================================================

def get_latest_ytdlp_info(progress_callback):
    """Consulta la API de GitHub para la última versión de yt-dlp."""
    progress_callback("Consultando la última versión de yt-dlp...", 5)
    try:
        api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        latest_release_data = response.json()
        
        tag_name = latest_release_data["tag_name"]
        
        for asset in latest_release_data.get("assets", []):
            if asset["name"] == "yt-dlp": # Archivo sin extensión (el zipapp nativo)
                progress_callback("Información de yt-dlp encontrada.", 10)
                return tag_name, asset["browser_download_url"]
                
        return tag_name, None
    except requests.RequestException as e:
        progress_callback(f"Error de red al buscar yt-dlp: {e}", -1)
        return None, None
    except (IndexError, KeyError) as e:
        progress_callback(f"Error en respuesta de API de yt-dlp: {e}", -1)
        return None, None

def download_and_install_ytdlp(tag, url, progress_callback):
    """Descarga el ZipApp de yt-dlp en bin/ytdlp/yt-dlp.zip."""
    try:
        os.makedirs(YTDLP_BIN_DIR, exist_ok=True)
        archive_name = os.path.join(YTDLP_BIN_DIR, "yt-dlp.zip")
        last_reported_progress = -1
        
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded_size = 0
            
            import time
            if os.path.exists(archive_name):
                try: os.remove(archive_name)
                except:
                    try: os.rename(archive_name, archive_name + f".old_{int(time.time())}")
                    except: pass
                    
            with open(archive_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk: continue
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = 40 + (downloaded_size / total_size) * 40
                        if int(progress) > last_reported_progress:
                            c_mb = downloaded_size / 1024 / 1024
                            t_mb = total_size / 1024 / 1024
                            progress_callback(f"Descargando yt-dlp: {c_mb:.1f}/{t_mb:.1f} MB", progress, c_mb, t_mb)
                            last_reported_progress = int(progress)
                            
        # --- NUEVO: Limpieza del shebang para compatibilidad con zipfile ---
        # yt-dlp es un zipapp que en recientes versiones empieza con #!/usr/bin/env python3
        # Esto hace que Python's zipfile (usado por pkg_resources/importlib) falle
        # con "bad local file header". Eliminamos cualquier byte antes de PK\x03\x04.
        try:
            with open(archive_name, "rb") as f:
                content = f.read()
            start_idx = content.find(b"PK\x03\x04")
            if start_idx > 0:
                with open(archive_name, "wb") as f:
                    f.write(content[start_idx:])
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo limpiar el shebang de yt-dlp: {e}")

        with open(YTDLP_VERSION_FILE, "w") as f: f.write(tag)
        progress_callback(f"yt-dlp {tag} descargado exitosamente.", 100)
        return True
    except Exception as e:
        progress_callback(f"Error al descargar yt-dlp: {e}", -1)
        return False
        
def check_ytdlp_status(progress_callback):
    """Verifica el estado de yt-dlp.zip local."""
    try:
        ytdlp_path = os.path.join(YTDLP_BIN_DIR, "yt-dlp.zip")
        ytdlp_exists = os.path.exists(ytdlp_path)

        local_tag = ""
        if os.path.exists(YTDLP_VERSION_FILE):
            with open(YTDLP_VERSION_FILE, 'r') as f:
                local_tag = f.read().strip()

        latest_tag, download_url = get_latest_ytdlp_info(progress_callback)

        return {
            "status": "success",
            "ytdlp_path_exists": ytdlp_exists,
            "local_ytdlp_version": local_tag,
            "latest_ytdlp_version": latest_tag,
            "ytdlp_download_url": download_url
        }
    except Exception as e:
        return {"status": "error", "message": f"Error en la verificación de yt-dlp: {e}"}

def get_latest_ffmpeg_info(progress_callback):
    """Consulta la API de GitHub para la última versión ESTABLE de FFMPEG (GyanD)."""
    progress_callback("Consultando la última versión de FFmpeg (Estable)...", 5)
    try:
        # Se cambia de BtbN (Nightly) a GyanD (Releases estables)
        api_url = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        latest_release = response.json()
        
        tag_name = latest_release["tag_name"]
        
        # GyanD ofrece versiones estables para Windows. Buscamos el ZIP full.
        file_identifier = "full_build.zip"
        
        for asset in latest_release.get("assets", []):
            if file_identifier in asset["name"] and "shared" not in asset["name"]:
                progress_callback("Información de FFmpeg estable encontrada.", 10)
                return tag_name, asset["browser_download_url"]
                
        return tag_name, None
    except requests.RequestException as e:
        progress_callback(f"Error de red al buscar FFmpeg: {e}", -1)
        return None, None
    except (IndexError, KeyError) as e:
        progress_callback(f"Error en respuesta de API de FFmpeg: {e}", -1)
        return None, None

def get_safe_ffmpeg_info(progress_callback):
    """Devuelve la información de la versión segura de FFmpeg (8.0.1)."""
    progress_callback("Obteniendo información de la versión de FFmpeg segura...", 10)
    return FFMPEG_SAFE_VERSION, FFMPEG_SAFE_URL

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
                            c_mb = downloaded_size / 1024 / 1024
                            t_mb = total_size / 1024 / 1024
                            progress_callback(f"Descargando FFmpeg: {c_mb:.1f}/{t_mb:.1f} MB", progress, c_mb, t_mb)
                            last_reported_progress = int(progress)
        progress_callback("Extrayendo archivos de FFmpeg...", 85)
        temp_extract_path = os.path.join(PROJECT_ROOT, "ffmpeg_temp_extract")
        if os.path.exists(temp_extract_path): shutil.rmtree(temp_extract_path)
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(archive_name, 'r') as zip_ref: zip_ref.extractall(temp_extract_path)
        else:
            with tarfile.open(archive_name, 'r:xz') as tar_ref: tar_ref.extractall(temp_extract_path)

        os.makedirs(FFMPEG_BIN_DIR, exist_ok=True)
        
        # Buscar dinámicamente la carpeta 'bin/' dentro de lo extraído
        bin_content_path = None
        for root, dirs, files in os.walk(temp_extract_path):
            if "ffmpeg.exe" in files:
                bin_content_path = root
                break

        if not bin_content_path:
            raise Exception("No se encontró ffmpeg.exe dentro del archivo descargado.")

        # Mover archivos a FFMPEG_BIN_DIR de forma segura (evita WinError 5)
        for item in os.listdir(bin_content_path):
            dest_path = os.path.join(FFMPEG_BIN_DIR, item)
            if os.path.exists(dest_path):
                import time
                try: os.remove(dest_path)
                except:
                    try: os.rename(dest_path, dest_path + f".old_{int(time.time())}")
                    except: pass
            shutil.move(os.path.join(bin_content_path, item), dest_path)

        # --- NUEVO: LIMPIEZA DE FFMPEG (LA DIETA) ---
        # 1. Eliminar ffplay.exe (No se usa)
        ffplay_path = os.path.join(FFMPEG_BIN_DIR, "ffplay.exe")
        if os.path.exists(ffplay_path):
            try:
                os.remove(ffplay_path)
                print("INFO: ffplay.exe eliminado para ahorrar espacio.")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo borrar ffplay.exe: {e}")

        try: shutil.rmtree(temp_extract_path)
        except: pass
        try: os.remove(archive_name)
        except: pass
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
            
            import time
            if os.path.exists(archive_name):
                try: os.remove(archive_name)
                except:
                    try: os.rename(archive_name, archive_name + f".old_{int(time.time())}")
                    except: pass
                    
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
                    final_path = os.path.join(DENO_BIN_DIR, os.path.basename(member))
                    if os.path.exists(final_path):
                        import time
                        try: os.remove(final_path)
                        except:
                            try: os.rename(final_path, final_path + f".old_{int(time.time())}")
                            except: pass
                            
                    zip_ref.extract(member, DENO_BIN_DIR)
                    # Moverlo si está en un subdirectorio (aunque Deno no suele hacerlo)
                    extracted_path = os.path.join(DENO_BIN_DIR, member)
                    if extracted_path != final_path:
                         shutil.move(extracted_path, final_path)
        
        try: os.remove(archive_name)
        except: pass
        with open(DENO_VERSION_FILE, "w") as f: f.write(tag)
        progress_callback(f"Deno {tag} instalado.", 95)
        return True
    except Exception as e:
        progress_callback(f"Error al instalar Deno: {e}", -1)
        return False
    
def get_latest_poppler_info(progress_callback):
    """Consulta la API de GitHub para la última versión de Poppler."""
    progress_callback("Consultando la última versión de Poppler...", 5)
    try:
        # Repositorio específico solicitado
        api_url = "https://api.github.com/repos/oschwartz10612/poppler-windows/releases/latest"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        latest_release_data = response.json()
        
        tag_name = latest_release_data["tag_name"]
        
        for asset in latest_release_data["assets"]:
            # Buscamos el archivo .zip (generalmente Release-XX.XX.X-0.zip)
            if asset["name"].endswith(".zip") and "Release" in asset["name"]:
                progress_callback("Información de Poppler encontrada.", 10)
                return tag_name, asset["browser_download_url"]
                
        return tag_name, None
    except requests.RequestException as e:
        progress_callback(f"Error de red al buscar Poppler: {e}", -1)
        return None, None
    except (IndexError, KeyError) as e:
        progress_callback(f"Error en respuesta de API de Poppler: {e}", -1)
        return None, None

def download_and_install_poppler(tag, url, progress_callback):
    """Descarga e instala Poppler en bin/poppler/."""
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
                            progress_callback(f"Descargando Poppler: {downloaded_size / 1024 / 1024:.1f}/{total_size / 1024 / 1024:.1f} MB", progress)
                            last_reported_progress = int(progress)
                            
        progress_callback("Extrayendo archivos de Poppler...", 85)
        
        # Limpiar/Crear directorio de forma segura
        os.makedirs(POPPLER_BIN_DIR, exist_ok=True)
        
        temp_extract_path = os.path.join(PROJECT_ROOT, "poppler_temp")
        if os.path.exists(temp_extract_path): shutil.rmtree(temp_extract_path)

        with zipfile.ZipFile(archive_name, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_path)
            
        # Lógica para encontrar la carpeta 'Library/bin' dentro del zip extraído
        bin_source_path = None
        for root, dirs, files in os.walk(temp_extract_path):
            if "pdfinfo.exe" in files: # Buscamos un ejecutable clave
                bin_source_path = root
                break
        
        if bin_source_path:
            # Mover el contenido de esa carpeta bin a nuestro POPPLER_BIN_DIR de forma segura
            for item in os.listdir(bin_source_path):
                dest_path = os.path.join(POPPLER_BIN_DIR, item)
                if os.path.exists(dest_path):
                    import time
                    try: os.remove(dest_path)
                    except:
                        try: os.rename(dest_path, dest_path + f".old_{int(time.time())}")
                        except: pass
                shutil.move(os.path.join(bin_source_path, item), dest_path)
        else:
            raise Exception("No se encontró la carpeta bin/ con ejecutables dentro del zip de Poppler.")

        # Limpieza
        try: shutil.rmtree(temp_extract_path)
        except: pass
        try: os.remove(archive_name)
        except: pass
        
        with open(POPPLER_VERSION_FILE, "w") as f: f.write(tag)
        progress_callback(f"Poppler {tag} instalado.", 95)
        return True
    except Exception as e:
        progress_callback(f"Error al instalar Poppler: {e}", -1)
        return False

def check_poppler_status(progress_callback):
    """Verifica el estado únicamente de Poppler."""
    try:
        poppler_exe = "pdfinfo.exe" if platform.system() == "Windows" else "pdfinfo"
        poppler_path = os.path.join(POPPLER_BIN_DIR, poppler_exe)
        poppler_exists = os.path.exists(poppler_path)

        local_tag = ""
        if os.path.exists(POPPLER_VERSION_FILE):
            with open(POPPLER_VERSION_FILE, 'r') as f:
                local_tag = f.read().strip()

        latest_tag, download_url = get_latest_poppler_info(progress_callback)

        return {
            "status": "success",
            "poppler_path_exists": poppler_exists,
            "local_poppler_version": local_tag,
            "latest_poppler_version": latest_tag,
            "poppler_download_url": download_url
        }
    except Exception as e:
        return {"status": "error", "message": f"Error en la verificación de Poppler: {e}"}

def check_environment_status(progress_callback, check_updates=True): # <--- NUEVO PARAMETRO
    """
    Verifica el estado del entorno.
    Si check_updates=False, salta las consultas lentas a GitHub.
    """
    try:
        # Importar dependencias (Esto es rápido si ya están instaladas)
        if not check_and_install_python_dependencies(progress_callback):
            return {"status": "error", "message": "Fallo crítico en dependencias Python."}
        
        # --- 1. Chequeo Local (Rápido) ---
        # Definir rutas (esto ya lo tienes, asegúrate de que coincida con tu código)
        ffmpeg_exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        ffmpeg_path = os.path.join(FFMPEG_BIN_DIR, ffmpeg_exe)
        ffmpeg_exists = os.path.exists(ffmpeg_path)
        
        local_tag = ""
        if os.path.exists(FFMPEG_VERSION_FILE):
            with open(FFMPEG_VERSION_FILE, 'r') as f: local_tag = f.read().strip()
        
        # --- 1. FFmpeg ---
        ffmpeg_path = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
        ffmpeg_exists = os.path.exists(ffmpeg_path)
        
        local_tag = ""
        if os.path.exists(FFMPEG_VERSION_FILE):
            with open(FFMPEG_VERSION_FILE, 'r') as f:
                local_tag = f.read().strip()
        # Deno...
        deno_exe = "deno.exe" if platform.system() == "Windows" else "deno"
        deno_path = os.path.join(DENO_BIN_DIR, deno_exe)
        deno_exists = os.path.exists(deno_path)
        local_deno_tag = ""
        if os.path.exists(DENO_VERSION_FILE):
            with open(DENO_VERSION_FILE, 'r') as f: local_deno_tag = f.read().strip()

        # Poppler...
        poppler_exe = "pdfinfo.exe" if platform.system() == "Windows" else "pdfinfo"
        poppler_path = os.path.join(POPPLER_BIN_DIR, poppler_exe)
        poppler_exists = os.path.exists(poppler_path)
        local_poppler_tag = ""
        if os.path.exists(POPPLER_VERSION_FILE):
            with open(POPPLER_VERSION_FILE, 'r') as f: local_poppler_tag = f.read().strip()

        # --- 2. Chequeo Remoto (Lento) - SOLO SI ES NECESARIO ---
        latest_tag, download_url = None, None
        latest_deno_tag, deno_download_url = None, None
        latest_poppler_tag, poppler_download_url = None, None
        latest_ytdlp_tag, ytdlp_download_url = None, None

        if check_updates:
            # Solo consultamos GitHub si nos lo piden explícitamente
            latest_tag, download_url = get_latest_ffmpeg_info(progress_callback)
            latest_deno_tag, deno_download_url = get_latest_deno_info(progress_callback)
            latest_poppler_tag, poppler_download_url = get_latest_poppler_info(progress_callback)
            latest_ytdlp_tag, ytdlp_download_url = get_latest_ytdlp_info(progress_callback)
        else:
            progress_callback("Verificación rápida de entorno completada.", 20)
            
        # ytdlp local check
        ytdlp_path = os.path.join(YTDLP_BIN_DIR, "yt-dlp.zip")
        ytdlp_exists = os.path.exists(ytdlp_path)
        local_ytdlp_tag = ""
        if os.path.exists(YTDLP_VERSION_FILE):
             with open(YTDLP_VERSION_FILE, 'r') as f: local_ytdlp_tag = f.read().strip()

        # --- Construir diccionario FINAL ---
        return {
            "status": "success", 
            
            # FFmpeg
            "ffmpeg_path_exists": ffmpeg_exists,
            "local_version": local_tag,
            "latest_version": latest_tag,     # Será None si check_updates=False
            "download_url": download_url,
            
            # Deno
            "deno_path_exists": deno_exists,
            "local_deno_version": local_deno_tag,
            "latest_deno_version": latest_deno_tag,
            "deno_download_url": deno_download_url,

            # Poppler 
            "poppler_path_exists": poppler_exists,
            "local_poppler_version": local_poppler_tag,
            "latest_poppler_version": latest_poppler_tag,
            "poppler_download_url": poppler_download_url,
            
            # yt-dlp
            "ytdlp_path_exists": ytdlp_exists,
            "local_ytdlp_version": local_ytdlp_tag,
            "latest_ytdlp_version": latest_ytdlp_tag,
            "ytdlp_download_url": ytdlp_download_url
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Error en la verificación del entorno: {e}"}
    
def check_and_download_rembg_models(progress_callback):
    """
    Verifica y descarga los modelos de rembg (u2netp, u2net, isnet-general-use)
    en la carpeta bin/models/rembg.
    """
    # Diccionario de modelos: Nombre archivo -> URL directa
    models_to_check = {
        "u2netp.onnx": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
        "isnet-general-use.onnx": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx",
        "u2net.onnx": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
    }

    os.makedirs(REMBG_MODELS_DIR, exist_ok=True)
    
    total_models = len(models_to_check)
    downloaded_count = 0
    
    try:
        for i, (filename, url) in enumerate(models_to_check.items()):
            file_path = os.path.join(REMBG_MODELS_DIR, filename)
            
            # Verificar si existe y no está vacío
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(f"INFO: Modelo IA encontrado: {filename}")
                continue
            
            # Si no existe, descargar
            progress_msg = f"Descargando modelo IA ({i+1}/{total_models}): {filename}..."
            print(f"INFO: {progress_msg}")
            # Usamos un valor base alto (50%) para que se note en la barra de carga inicial
            progress_callback(progress_msg, 50 + (i * 10))
            
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded_size = 0
                
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if not chunk: continue
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        # Opcional: Log detallado de progreso intra-archivo si fuera necesario
            
            print(f"INFO: ✅ {filename} descargado exitosamente.")
            downloaded_count += 1
            
        if downloaded_count > 0:
            progress_callback(f"Se descargaron {downloaded_count} modelos de IA.", 90)
        else:
            progress_callback("Todos los modelos de IA están listos.", 90)
            
        return True

    except Exception as e:
        print(f"ERROR CRÍTICO descargando modelos de IA: {e}")
        progress_callback(f"Error descargando modelos: {e}", -1)
        return False
    
def check_ffmpeg_status(progress_callback):
    """
    Verifica el estado únicamente de FFmpeg.
    """
    try:
        ffmpeg_path = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
        ffmpeg_exists = os.path.exists(ffmpeg_path)

        local_tag = ""
        if os.path.exists(FFMPEG_VERSION_FILE):
            with open(FFMPEG_VERSION_FILE, 'r') as f:
                local_tag = f.read().strip()

        latest_tag, download_url = get_latest_ffmpeg_info(progress_callback)

        return {
            "status": "success",
            "ffmpeg_path_exists": ffmpeg_exists,
            "local_version": local_tag,
            "latest_version": latest_tag,
            "download_url": download_url
        }
    except Exception as e:
        return {"status": "error", "message": f"Error en la verificación de FFmpeg: {e}"}

def check_deno_status(progress_callback):
    """
    Verifica el estado únicamente de Deno.
    """
    try:
        deno_exe_name = "deno.exe" if platform.system() == "Windows" else "deno"
        deno_path = os.path.join(DENO_BIN_DIR, deno_exe_name)
        deno_exists = os.path.exists(deno_path)

        local_deno_tag = ""
        if os.path.exists(DENO_VERSION_FILE):
            with open(DENO_VERSION_FILE, 'r') as f:
                local_deno_tag = f.read().strip()

        latest_deno_tag, deno_download_url = get_latest_deno_info(progress_callback)

        return {
            "status": "success",
            "deno_path_exists": deno_exists,
            "local_deno_version": local_deno_tag,
            "latest_deno_version": latest_deno_tag,
            "deno_download_url": deno_download_url
        }
    except Exception as e:
        return {"status": "error", "message": f"Error en la verificación de Deno: {e}"}
    
def check_app_update(current_version_str):
    """Consulta GitHub para ver si hay una nueva versión y busca el instalador LIGHT en ZIP."""
    print(f"INFO: Verificando actualizaciones para la versión actual: {current_version_str}")
    try:
        api_url = "https://api.github.com/repos/MarckDP/DowP/releases"

        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        releases = response.json()

        if not releases:
            return {"update_available": False}

        # Encontrar la release más reciente
        latest_release = None
        for r in releases:
            if not r.get("prerelease", False):
                latest_release = r
                break
        if not latest_release: 
            latest_release = releases[0]

        latest_version_str = latest_release.get("tag_name", "0.0.0").lstrip('v')
        release_url = latest_release.get("html_url")

        installer_url = None
        
        # --- CAMBIO: Buscamos el ZIP ---
        expected_suffix = "Light_setup.zip" 
        
        for asset in latest_release.get("assets", []):
            asset_name = asset.get("name", "")
            
            # Verificamos versión y sufijo
            if f"v{latest_version_str}" in asset_name and asset_name.endswith(expected_suffix):
                installer_url = asset.get("browser_download_url")
                print(f"INFO: Instalador Light (ZIP) encontrado: {asset_name}")
                break 
        
        # Fallback: Si no encuentra el Light ZIP, buscar cualquier .zip (Full o normal)
        if not installer_url:
             print("ADVERTENCIA: No se encontró ZIP 'Light', buscando ZIP genérico...")
             for asset in latest_release.get("assets", []):
                if asset.get("name", "").endswith(".zip") and "setup" in asset.get("name", "").lower():
                    installer_url = asset.get("browser_download_url")
                    break

        current_v = version.parse(current_version_str)
        latest_v = version.parse(latest_version_str)

        if latest_v > current_v:
            return {
                "update_available": True,
                "latest_version": latest_version_str,
                "release_url": release_url,
                "installer_url": installer_url, # URL del .zip
                "is_prerelease": latest_release.get("prerelease", False)
            }
        else:
            return {"update_available": False}

    except Exception as e:
        print(f"ERROR verificando actualización: {e}")
        return {"error": "Error al verificar."}
    
# --- FUNCIONES DE INKSCAPE (NUEVO) ---

def get_latest_inkscape_info(progress_callback):
    """Consulta la API de GitHub (Mirror oficial) para la última versión de Inkscape."""
    progress_callback("Consultando última versión de Inkscape (GitHub)...", 5)
    try:
        # ✅ CAMBIO: Usamos la API de GitHub en lugar de GitLab. 
        # Es mucho más fiable para obtener el enlace directo del .7z
        api_url = "https://api.github.com/repos/inkscape/inkscape/releases/latest"
        
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        latest_release = response.json()
        
        tag_name = latest_release["tag_name"]
        download_url = None
        
        # Buscar el archivo .7z para Windows x64 en los assets de GitHub
        for asset in latest_release.get("assets", []):
            name = asset.get("name", "").lower()
            
            # Lógica de filtrado estricta:
            # 1. Debe ser .7z (portable)
            # 2. Debe ser x64 (64 bits)
            # 3. No debe ser un .exe ni .msi (instaladores)
            if "x64" in name and name.endswith(".7z") and "exe" not in name:
                download_url = asset.get("browser_download_url")
                break
        
        if download_url:
             progress_callback("Información de Inkscape encontrada.", 10)
             return tag_name, download_url
        
        # Si no se encuentra, lanzamos error para que la UI lo sepa
        progress_callback("No se encontró el archivo .7z en la release.", -1)
        return tag_name, None

    except Exception as e:
        progress_callback(f"Error al buscar Inkscape: {e}", -1)
        return None, None

def download_and_install_inkscape(tag, url, progress_callback):
    """Descarga e instala Inkscape (formato .7z)."""
    try:
        import py7zr # Importación tardía para asegurar que se instaló
        
        file_name = "inkscape_portable.7z"
        archive_name = os.path.join(PROJECT_ROOT, file_name)
        last_reported_progress = -1
        
        # 1. Descargar
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
                            progress_callback(f"Descargando Inkscape: {downloaded_size / 1024 / 1024:.1f}/{total_size / 1024 / 1024:.1f} MB", progress)
                            last_reported_progress = int(progress)

        progress_callback("Extrayendo Inkscape (esto puede tardar)...", 85)
        
        # 2. Preparar directorios
        if os.path.exists(INKSCAPE_BIN_DIR): shutil.rmtree(INKSCAPE_BIN_DIR)
        # No creamos el dir todavía, el extractor lo creará o extraerá una carpeta
        
        temp_extract_path = os.path.join(PROJECT_ROOT, "inkscape_temp")
        if os.path.exists(temp_extract_path): shutil.rmtree(temp_extract_path)
        os.makedirs(temp_extract_path, exist_ok=True)

        # 3. Extraer 7z
        with py7zr.SevenZipFile(archive_name, mode='r') as z:
            z.extractall(path=temp_extract_path)
            
        # 4. Organizar archivos
        # Inkscape suele extraerse en una carpeta tipo "inkscape-1.x.x-..."
        extracted_items = os.listdir(temp_extract_path)
        source_folder = None
        
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_path, extracted_items[0])):
             source_folder = os.path.join(temp_extract_path, extracted_items[0])
        else:
             source_folder = temp_extract_path # Se extrajo suelto (raro en inkscape)

        # Mover todo a bin/inkscape
        shutil.move(source_folder, INKSCAPE_BIN_DIR)
        
        # 5. Limpieza
        if os.path.exists(temp_extract_path): shutil.rmtree(temp_extract_path)
        os.remove(archive_name)
        
        # Guardar versión
        with open(INKSCAPE_VERSION_FILE, "w") as f: f.write(tag)
        
        progress_callback(f"Inkscape {tag} instalado.", 100)
        return True
        
    except Exception as e:
        progress_callback(f"Error al instalar Inkscape: {e}", -1)
        print(f"ERROR DETALLADO INKSCAPE: {e}")
        return False
    
def check_inkscape_status(progress_callback):
    """
    Verifica si Inkscape está instalado manualmente en bin/inkscape.
    """
    progress_callback("Verificando Inkscape...", 10)
    try:
        # Buscamos el ejecutable principal
        inkscape_exe = "inkscape.exe" if platform.system() == "Windows" else "inkscape"
        inkscape_path = os.path.join(INKSCAPE_BIN_DIR, inkscape_exe)
        
        exists = os.path.exists(inkscape_path)
        
        if exists:
            progress_callback("Inkscape detectado.", 100)
            return {
                "status": "success",
                "exists": True,
                "path": inkscape_path
            }
        else:
            progress_callback("Inkscape no encontrado en bin/inkscape.", 100)
            return {
                "status": "success", # No es un error crítico, solo 'no encontrado'
                "exists": False,
                "path": None
            }
            
    except Exception as e:
        return {"status": "error", "message": f"Error verificando Inkscape: {e}"}

def check_ghostscript_status(progress_callback):
    """
    Verifica si Ghostscript está instalado manualmente en bin/ghostscript.
    Busca gswin64c.exe, gswin32c.exe o gs (Linux/Mac).
    """
    progress_callback("Verificando Ghostscript...", 10)
    try:
        # Nombres posibles del ejecutable
        if platform.system() == "Windows":
            gs_exes = ["gswin64c.exe", "gswin32c.exe", "gs.exe"]
        else:
            gs_exes = ["gs"]

        gs_path = None
        exists = False

        # Buscar cualquiera de los ejecutables
        for exe in gs_exes:
            potential_path = os.path.join(GHOSTSCRIPT_BIN_DIR, exe)
            if os.path.exists(potential_path):
                exists = True
                gs_path = potential_path
                break

        if exists:
            progress_callback("Ghostscript detectado.", 100)
            return {
                "status": "success",
                "exists": True,
                "path": gs_path
            }
        else:
            progress_callback("Ghostscript no encontrado en bin/ghostscript.", 100)
            return {
                "status": "success", # No es error crítico
                "exists": False,
                "path": None
            }
            
    except Exception as e:
        return {"status": "error", "message": f"Error verificando Ghostscript: {e}"}
    
def sanitize_upscayl_models(models_dir):
    """
    Purga modelos conocidos por causar errores graves o que han sido descartados.
    Actualmente elimina Anime Video v3 x2 y x3 por inestabilidad.
    """
    if not os.path.exists(models_dir):
        return
        
    blacklist = [
        "realesr-animevideov3-x2",
        "realesr-animevideov3-x3"
    ]
    
    purged_any = False
    for name in blacklist:
        for ext in [".bin", ".param"]:
            file_path = os.path.join(models_dir, name + ext)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"INFO: Modelo purgado por seguridad (Vía Código): {name}{ext}")
                    purged_any = True
                except Exception as e:
                    print(f"ADVERTENCIA: No se pudo purgar el modelo {name}{ext}: {e}")
    
    return purged_any
    
def migrate_old_upscaling_models():
    """Migra los modelos antiguos de Real-ESRGAN y RealSR a la carpeta de Upscayl."""
    old_folders = ["realesrgan", "realsr"]
    upscayl_models_dir = os.path.join(UPSCALING_DIR, "upscayl", "models")
    
    migrated_any = False
    for folder in old_folders:
        old_dir = os.path.join(UPSCALING_DIR, folder)
        if os.path.exists(old_dir):
            if not os.path.exists(upscayl_models_dir):
                os.makedirs(upscayl_models_dir, exist_ok=True)
            
            # Find all .bin and .param in old_dir
            for root, dirs, files in os.walk(old_dir):
                for file in files:
                    if file.endswith(('.bin', '.param')):
                        src_file = os.path.join(root, file)
                        
                        # --- NUEVO: Renombrado inteligente (paridad con lógica de descarga) ---
                        # Si el modelo es genérico (ej: "x4.bin" en RealSR), le ponemos el prefijo de la carpeta.
                        dst_name = file
                        if file.startswith("x4"):
                            parent_name = os.path.basename(root)
                            # Quitamos el prefijo "models-" si existe para limpiar el nombre
                            prefix = parent_name.replace("models-", "")
                            # Evitamos duplicar el prefijo si ya lo tiene
                            if not file.startswith(prefix):
                                dst_name = f"{prefix}_{file}"
                        
                        dst_file = os.path.join(upscayl_models_dir, dst_name)
                        try:
                            if not os.path.exists(dst_file):
                                shutil.copy2(src_file, dst_file)
                                migrated_any = True
                        except Exception as e:
                            print(f"ADVERTENCIA: No se pudo migrar {file} como {dst_name}: {e}")
            
            try:
                shutil.rmtree(old_dir)
                print(f"INFO: Carpeta antigua '{folder}' eliminada tras migración.")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo eliminar '{folder}': {e}")
                
    if migrated_any:
        print("INFO: Se han migrado con éxito modelos antiguos a la carpeta de Upscayl.")
        sanitize_upscayl_models(upscayl_models_dir)

def check_and_download_upscaling_tools(progress_callback, target_tool=None):
    """
    Verifica y descarga las herramientas de reescalado con reporte de porcentaje real.
    Si target_tool se especifica (ej: "Real-ESRGAN"), solo descarga esa.
    """
    os.makedirs(UPSCALING_DIR, exist_ok=True)
    
    if not target_tool or target_tool == "Upscayl":
        migrate_old_upscaling_models()
    
    # Filtrar herramientas si se especifica una
    tools_to_process = UPSCALING_TOOLS
    if target_tool:
        # Manejar coincidencia parcial (ej: "RealSR" coincide con la key "RealSR")
        # o búsqueda inversa si el nombre varía.
        if target_tool in UPSCALING_TOOLS:
            tools_to_process = {target_tool: UPSCALING_TOOLS[target_tool]}
        else:
            print(f"ERROR: Herramienta '{target_tool}' no encontrada en constantes.")
            return False

    total_tools = len(tools_to_process)
    processed_count = 0
    
    try:
        # Iteramos sobre el diccionario filtrado
        for key, info in tools_to_process.items():
            tool_name = info["name"]
            folder_name = info["folder"]
            exe_name = info["exe"]
            url = info["url"]
            
            target_folder = os.path.join(UPSCALING_DIR, folder_name)
            target_exe = os.path.join(target_folder, exe_name)
            
            # Verificar si ya existe
            if os.path.exists(target_exe):
                print(f"INFO: {tool_name} encontrado en {target_folder}")
                processed_count += 1
                continue
                
            # --- INICIO DESCARGA CON PROGRESO DETALLADO ---
            print(f"INFO: Iniciando descarga de {tool_name}...")
            
            # Descargar ZIP
            zip_filename = f"{folder_name}_temp.zip"
            zip_path = os.path.join(UPSCALING_DIR, zip_filename)
            
            try:
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded_size = 0
                    last_reported_pct = -1
                    
                    with open(zip_path, 'wb') as f:
                        # Chunk de 64KB para velocidad
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk: 
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                
                                # Calcular porcentaje
                                if total_size > 0:
                                    percent = int(downloaded_size * 100 / total_size)
                                    
                                    # Actualizar UI solo si cambió el porcentaje (para no saturar)
                                    if percent > last_reported_pct:
                                        last_reported_pct = percent
                                        
                                        dl_mb = downloaded_size / (1024 * 1024)
                                        tot_mb = total_size / (1024 * 1024)
                                        
                                        # Mensaje estilo: "⬇️ Real-ESRGAN: 45% (15.2/30.5 MB)"
                                        status_text = f"⬇️ {tool_name}: {percent}% ({dl_mb:.1f}/{tot_mb:.1f} MB)"
                                        
                                        # Valor numérico para barra de progreso global (opcional)
                                        progress_callback(status_text, percent)
                
                # --- EXTRACCIÓN ---
                progress_callback(f"Extrayendo {tool_name}...", 100)
                
                # Descomprimir
                temp_extract_dir = os.path.join(UPSCALING_DIR, f"{folder_name}_temp_extract")
                if os.path.exists(temp_extract_dir):
                    shutil.rmtree(temp_extract_dir) # Limpiar residuos anteriores
                    
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract_dir)
                
                # Mover contenido: Buscar la carpeta interna
                extracted_items = os.listdir(temp_extract_dir)
                source_path = temp_extract_dir
                
                # Si solo hay una carpeta dentro, entramos en ella
                if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, extracted_items[0])):
                    source_path = os.path.join(temp_extract_dir, extracted_items[0])
                
                # Mover a destino final (bin/models/upscaling/realesrgan)
                # --- OPTIMIZACIÓN: Fusión segura en lugar de borrar todo ---
                # Esto evita borrar los modelos que el usuario ya migró manualmente.
                try:
                    os.makedirs(target_folder, exist_ok=True)
                    # Fusionar contenidos (sobrescribe archivos del binario, pero respeta otros como 'models')
                    shutil.copytree(source_path, target_folder, dirs_exist_ok=True)
                    # Limpiar carpeta temporal
                    shutil.rmtree(source_path)
                except Exception as e:
                    print(f"ADVERTENCIA: Falló la fusión, intentando reemplazo total: {e}")
                    if os.path.exists(target_folder):
                        shutil.rmtree(target_folder)
                    shutil.move(source_path, target_folder)
                
                # --- NUEVO: Descarga de modelos adicionales si existen ---
                if "models_url" in info:
                    models_url = info["models_url"]
                    progress_callback(f"⬇️ {tool_name} (Modelos): Iniciando descarga...", -1)
                    
                    models_zip_path = os.path.join(UPSCALING_DIR, f"{folder_name}_models_temp.zip")
                    with requests.get(models_url, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        total_models_size = int(r.headers.get('content-length', 0))
                        dl_models_size = 0
                        last_reported_m_pct = -1
                        with open(models_zip_path, 'wb') as fm:
                            for chunk in r.iter_content(chunk_size=65536):
                                if chunk:
                                    fm.write(chunk)
                                    dl_models_size += len(chunk)
                                    if total_models_size > 0:
                                        m_percent = int(dl_models_size * 100 / total_models_size)
                                        if m_percent > last_reported_m_pct:
                                            last_reported_m_pct = m_percent
                                            dl_mb2 = dl_models_size / (1024*1024)
                                            tot_mb2 = total_models_size / (1024*1024)
                                            progress_callback(f"⬇️ {tool_name} (Modelos): {dl_mb2:.1f}/{tot_mb2:.1f} MB", m_percent)
                                    else:
                                        dl_mb2 = dl_models_size / (1024*1024)
                                        if int(dl_mb2) > last_reported_m_pct:
                                            last_reported_m_pct = int(dl_mb2)
                                            progress_callback(f"⬇️ {tool_name} (Modelos): {dl_mb2:.1f} MB descargados...", -1)
                    
                    progress_callback(f"Extrayendo Modelos de {tool_name}...", 100)
                    temp_models_dir = os.path.join(UPSCALING_DIR, f"{folder_name}_models_extract")
                    if os.path.exists(temp_models_dir):
                        shutil.rmtree(temp_models_dir)
                    with zipfile.ZipFile(models_zip_path, 'r') as mzip:
                        mzip.extractall(temp_models_dir)
                    
                    m_extracted = os.listdir(temp_models_dir)
                    m_source = temp_models_dir
                    if len(m_extracted) == 1 and os.path.isdir(os.path.join(temp_models_dir, m_extracted[0])):
                        m_source = os.path.join(temp_models_dir, m_extracted[0])
                        
                    # Buscar la subcarpeta "models" real dentro de la extracción (Ej: custom-models-main/models)
                    inner_models = os.path.join(m_source, "models")
                    if os.path.exists(inner_models) and os.path.isdir(inner_models):
                        m_source = inner_models
                        
                    models_target = os.path.join(target_folder, "models")
                    # --- OPTIMIZACIÓN: Fusión de modelos en lugar de borrar la carpeta ---
                    # Esto permite que los modelos migrados de RealSR no se borren.
                    try:
                        os.makedirs(models_target, exist_ok=True)
                        shutil.copytree(m_source, models_target, dirs_exist_ok=True)
                        shutil.rmtree(m_source)
                    except Exception as e:
                        print(f"ADVERTENCIA: Falló la fusión de modelos: {e}")
                        if os.path.exists(models_target):
                            shutil.rmtree(models_target)
                        shutil.move(m_source, models_target)
                    
                    # Evitar WinError 32 reintentando el borrado del temporal
                    import time
                    for _ in range(3):
                        try:
                            os.remove(models_zip_path)
                            break
                        except Exception:
                            time.sleep(0.5)
                    try:
                        shutil.rmtree(temp_models_dir, ignore_errors=True)
                    except: pass
                
                # --- NUEVO: Descargar modelos de familias antiguas para usarlos en Upscayl ---
                if folder_name == "upscayl":
                    legacy_zips = [
                        ("Real-ESRGAN", "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"),
                        ("RealSR", "https://github.com/nihui/realsr-ncnn-vulkan/releases/download/20220728/realsr-ncnn-vulkan-20220728-windows.zip")
                    ]
                    models_target = os.path.join(target_folder, "models")
                    os.makedirs(models_target, exist_ok=True)
                    
                    for leg_name, leg_url in legacy_zips:
                        # --- OPTIMIZACIÓN FINAL: Saltar descarga si ya existen modelos clave ---
                        # Evitamos bajar ~200MB si ya migramos o descargamos esto antes.
                        canary = "realesrgan-x4plus.bin" if leg_name == "Real-ESRGAN" else "DF2K_x4.bin"
                        if os.path.exists(os.path.join(models_target, canary)):
                            print(f"INFO: Modelos de {leg_name} ya detectados. Saltando descarga de ZIP de {leg_name}.")
                            continue
                            
                        progress_callback(f"⬇️ Modelos Adicionales ({leg_name}): Descargando...", -1)
                        leg_zip_path = os.path.join(UPSCALING_DIR, f"{leg_name}_temp.zip")
                        try:
                            with requests.get(leg_url, stream=True, timeout=120) as r:
                                r.raise_for_status()
                                with open(leg_zip_path, 'wb') as fm:
                                    for chunk in r.iter_content(chunk_size=65536):
                                        if chunk: fm.write(chunk)
                            progress_callback(f"Extrayendo Modelos de {leg_name}...", 100)
                            leg_temp_dir = os.path.join(UPSCALING_DIR, f"{leg_name}_temp_extract")
                            if os.path.exists(leg_temp_dir):
                                shutil.rmtree(leg_temp_dir)
                            with zipfile.ZipFile(leg_zip_path, 'r') as legzip:
                                legzip.extractall(leg_temp_dir)
                            
                            # Buscar .bin y .param y mover a models_target
                            for root_d, _, files_d in os.walk(leg_temp_dir):
                                for f in files_d:
                                    if f.endswith('.bin') or f.endswith('.param'):
                                        src_p = os.path.join(root_d, f)
                                        # Prevenir colisión de nombres genéricos en carpetas distintas (Ej: RealSR modelos 'x4')
                                        dst_name = f
                                        parent_name = os.path.basename(root_d)
                                        if f.startswith("x4") and parent_name.startswith("models-"):
                                            prefix = parent_name.replace("models-", "")
                                            dst_name = f"{prefix}_{f}"
                                            
                                        dst_p = os.path.join(models_target, dst_name)
                                        if not os.path.exists(dst_p):
                                            shutil.copy2(src_p, dst_p)
                                            
                            # Purgar modelos prohibidos tras extracción de legacy
                            sanitize_upscayl_models(models_target)
                            
                            # Limpiar
                            for _ in range(3):
                                try: os.remove(leg_zip_path); break
                                except Exception: time.sleep(0.5)
                            shutil.rmtree(leg_temp_dir, ignore_errors=True)
                        except Exception as e:
                            print(f"ADVERTENCIA: No se pudo descargar legacy models de {leg_name}: {e}")

                # --- PURGA FINAL DE SEGURIDAD ---
                sanitize_upscayl_models(os.path.join(target_folder, "models"))

                print(f"INFO: [OK] {tool_name} instalado correctamente.")
                
                # Limpieza final
                for _ in range(3):
                    try:
                        os.remove(zip_path)
                        break
                    except Exception:
                        import time
                        time.sleep(0.5)
                if os.path.exists(temp_extract_dir):
                    shutil.rmtree(temp_extract_dir)
                    
            except Exception as e:
                print(f"ERROR descargando {tool_name}: {e}")
                # Limpiar en caso de error
                if os.path.exists(zip_path): 
                    try: os.remove(zip_path)
                    except: pass
                return False
            
            processed_count += 1
            
        return True

    except Exception as e:
        print(f"ERROR CRÍTICO gestionando herramientas de reescalado: {e}")
        progress_callback(f"Error en Upscaling: {e}", -1)
        return False

def install_custom_upscayl_model(parent_app):
    """
    Permite al usuario seleccionar un modelo de Upscayl (.bin o .param),
    busca su pareja, solicita un apodo y los instala en la carpeta interna.
    """
    import customtkinter as ctk
    from tkinter import filedialog, messagebox

    # 1. Seleccionar archivo
    file_path = filedialog.askopenfilename(
        title="Selecciona un archivo de modelo Upscayl (.bin o .param)",
        filetypes=[("Modelos Upscayl", "*.bin *.param"), ("Todos", "*.*")]
    )
    if not file_path:
        return False

    # 2. Determinar base y pareja
    base_path, ext = os.path.splitext(file_path)
    ext = ext.lower()
    partner_ext = ".param" if ext == ".bin" else ".bin"
    partner_path = base_path + partner_ext
    
    real_name_base = os.path.basename(base_path)

    if not os.path.exists(partner_path):
        messagebox.showerror(
            "Error de Pareja",
            f"No se encontró el archivo pareja '{os.path.basename(partner_path)}' en la misma carpeta.\n\n"
            "Los modelos NCNN requieren tanto el archivo .bin como el .param con el mismo nombre."
        )
        return False

    # 3. Solicitar Apodo (Diálogo centrado y con icono)
    from src.gui.dialogs import ModelNicknameDialog
    dialog = ModelNicknameDialog(parent_app, default_name=real_name_base)
    nickname = dialog.get_result()
    
    if nickname is None: # Cancelado
        return False

    # 4. Definir destino
    upscayl_models_dir = os.path.join(UPSCALING_DIR, "upscayl", "models")
    os.makedirs(upscayl_models_dir, exist_ok=True)

    # 5. Copiar
    try:
        shutil.copy2(file_path, os.path.join(upscayl_models_dir, real_name_base + ext))
        shutil.copy2(partner_path, os.path.join(upscayl_models_dir, real_name_base + partner_ext))
        
        # 6. Guardar en ajustes
        if not hasattr(parent_app, 'upscayl_custom_models'):
            parent_app.upscayl_custom_models = {}
            
        parent_app.upscayl_custom_models[real_name_base] = nickname
        parent_app.save_settings()
        
        messagebox.showinfo("Éxito", f"Modelo '{nickname}' instalado correctamente.")
        return True
    except Exception as e:
        messagebox.showerror("Error de Copia", f"No se pudo copiar el modelo: {e}")
        return False

def delete_custom_upscayl_model(real_name_base, parent_app):
    """
    Elimina físicamente los archivos del modelo y lo quita de los ajustes.
    """
    upscayl_models_dir = os.path.join(UPSCALING_DIR, "upscayl", "models")
    bin_file = os.path.join(upscayl_models_dir, real_name_base + ".bin")
    param_file = os.path.join(upscayl_models_dir, real_name_base + ".param")

    try:
        if os.path.exists(bin_file): os.remove(bin_file)
        if os.path.exists(param_file): os.remove(param_file)
        
        if hasattr(parent_app, 'upscayl_custom_models') and real_name_base in parent_app.upscayl_custom_models:
            del parent_app.upscayl_custom_models[real_name_base]
            parent_app.save_settings()
        return True
    except Exception as e:
        print(f"ERROR: No se pudo eliminar el modelo {real_name_base}: {e}")
        return False
    
def get_remote_file_size(url):
    """Obtiene el tamaño de un archivo remoto en bytes sin descargarlo."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return int(response.headers.get('content-length', 0))
        return 0
    except Exception:
        return 0

def format_size(size_bytes):
    """Formatea bytes a MB/GB."""
    if size_bytes == 0:
        return "Desconocido"
    
    size_mb = size_bytes / (1024 * 1024)
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    return f"{size_mb:.1f} MB"