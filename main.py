import sys
import os
import subprocess
import platform
import requests
import zipfile
import tarfile
import shutil

# --- CONFIGURACIÓN GENERAL ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
FFMPEG_VERSION_FILE = os.path.join(BIN_DIR, "ffmpeg_version.txt")

# --- FUNCIONES ---

def check_and_install_python_dependencies():
    """
    Verifica si las dependencias de Python están instaladas.
    Si no, las instala desde requirements.txt.
    """
    print("Verificando dependencias de Python...")
    try:
        import customtkinter
        import PIL
        import requests
        import yt_dlp
        print("Todas las dependencias de Python ya están instaladas.")
        return True
    except ImportError:
        print("Faltan una o más dependencias de Python. Intentando instalar...")
        
    requirements_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    if not os.path.exists(requirements_path):
        print(f"ERROR: No se encontró el archivo 'requirements.txt' en la carpeta.")
        print("Por favor, crea el archivo con el contenido necesario.")
        sys.exit(1)
        
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
        print("Dependencias de Python instaladas correctamente.")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Falló la instalación de dependencias con pip: {e}")
        print("Por favor, intenta instalar las dependencias manualmente con: pip install -r requirements.txt")
        sys.exit(1)


def get_latest_ffmpeg_info():
    """
    Consulta la API de GitHub para obtener el tag de la última versión Y
    el enlace de descarga directo para el sistema operativo actual.
    """
    print("Consultando API de GitHub para la última versión de FFMPEG...")
    try:
        api_url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        
        latest_release_data = response.json()[0]
        tag_name = latest_release_data["tag_name"]
        
        if tag_name == 'latest':
            latest_release_data = response.json()[1]
            tag_name = latest_release_data["tag_name"]

        system = platform.system()
        file_identifier = ""
        if system == "Windows": file_identifier = "win64-gpl.zip"
        elif system == "Linux": file_identifier = "linux64-gpl.tar.xz"
        elif system == "Darwin": file_identifier = "osx64-gpl.zip"
        else: return None, None

        for asset in latest_release_data["assets"]:
            if file_identifier in asset["name"] and "shared" not in asset["name"]:
                return tag_name, asset["browser_download_url"]
        
        return tag_name, None
        
    except requests.RequestException as e:
        print(f"ERROR: No se pudo conectar a la API de GitHub: {e}")
        return None, None
    except (IndexError, KeyError) as e:
        print(f"ERROR: La respuesta de la API no tuvo el formato esperado: {e}")
        return None, None


def download_and_install_ffmpeg(tag, url):
    """Descarga e instala FFMPEG desde un enlace directo."""
    print(f"Iniciando descarga de FFMPEG versión: {tag}")
    try:
        file_name = url.split('/')[-1]
        archive_name = os.path.join(PROJECT_ROOT, file_name)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            print(f"Descargando: {file_name} ({total_size / 1024 / 1024:.2f} MB)")
            with open(archive_name, 'wb') as f:
                downloaded_size = 0
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = int(50 * downloaded_size / total_size)
                        sys.stdout.write(f"\r[{'█' * progress}{' ' * (50 - progress)}] {downloaded_size * 100 / total_size:.2f}%")
                        sys.stdout.flush()

        print("\nExtrayendo archivos...")
        temp_extract_path = os.path.join(PROJECT_ROOT, "ffmpeg_temp_extract")
        if os.path.exists(temp_extract_path): shutil.rmtree(temp_extract_path)
        
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(archive_name, 'r') as zip_ref: zip_ref.extractall(temp_extract_path)
        else:
            with tarfile.open(archive_name, 'r:xz') as tar_ref: tar_ref.extractall(temp_extract_path)
        
        os.makedirs(BIN_DIR, exist_ok=True)
        bin_content_path = os.path.join(temp_extract_path, os.listdir(temp_extract_path)[0], 'bin')
        
        for item in os.listdir(bin_content_path):
            dest_path = os.path.join(BIN_DIR, item)
            if os.path.exists(dest_path): os.remove(dest_path)
            shutil.move(os.path.join(bin_content_path, item), dest_path)

        shutil.rmtree(temp_extract_path)
        os.remove(archive_name)
        
        with open(FFMPEG_VERSION_FILE, "w") as f: f.write(tag)
        print(f"FFMPEG versión {tag} instalado correctamente.")
        return True
    except Exception as e:
        print(f"\nERROR durante la descarga o extracción: {e}"); return False


def setup_environment():
    """Gestiona las dependencias externas al iniciar el programa."""
    print("\n--- Configurando el entorno ---")
    
    # 1. Actualizar yt-dlp
    print("Verificando yt-dlp...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "-q"])
        print("yt-dlp está actualizado.")
    except subprocess.CalledProcessError:
        print("No se pudo actualizar yt-dlp.")

    # 2. Gestionar FFMPEG
    print("Verificando FFMPEG...")
    latest_tag, download_url = get_latest_ffmpeg_info()
    
    if not latest_tag or not download_url:
        print("ADVERTENCIA: No se pudo obtener la información de FFMPEG. Se omitirá la comprobación.")
        return

    ffmpeg_path = os.path.join(BIN_DIR, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    local_tag = ""
    if os.path.exists(FFMPEG_VERSION_FILE):
        with open(FFMPEG_VERSION_FILE, 'r') as f: local_tag = f.read().strip()
    
    if os.path.exists(ffmpeg_path):
        if local_tag == latest_tag:
            print(f"FFMPEG está actualizado (versión: {local_tag}).")
        else:
            print(f"Nueva versión de FFMPEG disponible. Local: {local_tag or 'desconocida'}, Última: {latest_tag}.")
            download_and_install_ffmpeg(latest_tag, download_url)
    else:
        print("FFMPEG no encontrado. Instalando la última versión...")
        download_and_install_ffmpeg(latest_tag, download_url)

    print("--- Configuración finalizada ---\n")

# --- EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    # Paso 1: Instalar dependencias de Python. Es lo primero que se debe hacer.
    check_and_install_python_dependencies()
    
    # Paso 2: Configurar dependencias externas (FFMPEG, etc.)
    setup_environment()
    
    # Paso 3: Añadir la carpeta 'bin' al PATH para que el programa encuentre ffmpeg.exe
    if os.path.isdir(BIN_DIR) and BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = BIN_DIR + os.pathsep + os.environ['PATH']

    # Paso 4: Añadir la raíz del proyecto al path para asegurar importaciones de 'src'
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
        
    print("Iniciando la aplicación...")
    
    # Paso 5: Iniciar la aplicación
    from src.gui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()