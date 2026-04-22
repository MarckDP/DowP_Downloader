import PyInstaller.__main__
import os
import sys
import subprocess

# Configuración básica
APP_NAME = "DowP"
ICON_PATH = "DowP-icon.ico"
ENTRY_POINT = "main.py"

def get_version():
    """Extrae la versión desde main.py sin importar el archivo."""
    try:
        with open(ENTRY_POINT, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("APP_VERSION ="):
                    return line.split("=")[1].strip().strip('"').strip("'")
    except Exception as e:
        print(f"Error leyendo versión: {e}")
    return "unknown"

def update_ytdlp():
    """Descarga la última versión de yt-dlp (ZipApp) antes de compilar."""
    print("🔄 Descargando la última versión de yt-dlp (ZipApp)...")
    try:
        bin_dir = os.path.join("bin", "ytdlp")
        os.makedirs(bin_dir, exist_ok=True)
        zip_path = os.path.join(bin_dir, "yt-dlp.zip")
        version_path = os.path.join(bin_dir, "ytdlp_version.txt")
        
        import requests
        print("Obteniendo información de la última versión...")
        api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        latest_release_data = response.json()
        tag_name = latest_release_data["tag_name"]
        
        url = None
        for asset in latest_release_data.get("assets", []):
            if asset["name"] == "yt-dlp":
                url = asset["browser_download_url"]
                break
                
        if url:
            print(f"Descargando versión {tag_name}...")
            import urllib.request
            urllib.request.urlretrieve(url, zip_path)
            
            # Limpiar shebang para que PyInstaller / zipfile no fallen
            try:
                with open(zip_path, "rb") as f:
                    content = f.read()
                start_idx = content.find(b"PK\x03\x04")
                if start_idx > 0:
                    with open(zip_path, "wb") as f:
                        f.write(content[start_idx:])
            except Exception as e:
                print(f"⚠️ Warning: No se pudo limpiar el shebang de yt-dlp: {e}")

            with open(version_path, "w", encoding="utf-8") as f:
                f.write(tag_name)
            print(f"✅ yt-dlp.zip y versión {tag_name} guardados en {bin_dir}")
        else:
            print("⚠️ Warning: No se encontró URL de descarga en el release.")
    except Exception as e:
        print(f"⚠️ Warning: No se pudo descargar yt-dlp automáticamente: {e}")

def cleanup_build_files():
    import shutil
    print("\n🧹 Limpiando compilaciones anteriores (build, dist, .spec)...")
    for dir_name in ["build", "dist"]:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"  - Eliminado directorio: {dir_name}")
            except Exception as e:
                print(f"  - No se pudo eliminar {dir_name}: {e}")
                
    for item in os.listdir("."):
        if item.endswith(".spec"):
            try:
                os.remove(item)
                print(f"  - Eliminado archivo: {item}")
            except Exception as e:
                print(f"  - No se pudo eliminar {item}: {e}")

def build():
    # 0. Limpiar builds anteriores
    cleanup_build_files()
    
    # 1. Descargar yt-dlp externo
    update_ytdlp()
    
    # 2. Obtener versión
    version = get_version()
    print(f"\n🚀 Iniciando compilación de {APP_NAME} v{version}...")
    
    # Separador de PATH en PyInstaller según SO
    path_sep = ';'
    
    # Preparar los argumentos de PyInstaller
    args = [
        ENTRY_POINT,
        '--name=%s' % f"{APP_NAME}",
        '--onedir',
        '--windowed',
        '--noconfirm',
        '--clean',
        f'--icon={ICON_PATH}',
        
        # ------------------------------
        # DATOS
        # ------------------------------
        f'--add-data=src{path_sep}src',
        f'--add-data={ICON_PATH}{path_sep}.',
        
        # ------------------------------
        # HIDDEN IMPORTS
        # ------------------------------
        '--hidden-import=tkinterdnd2',
        '--hidden-import=customtkinter',
        '--hidden-import=PIL._tkinter_finder',
        '--hidden-import=PIL.ImageResampling',
        
        '--hidden-import=flask',
        '--hidden-import=flask_socketio',
        '--hidden-import=engineio',
        '--hidden-import=socketio',
        '--hidden-import=engineio.async_drivers.threading',
        
        '--hidden-import=packaging',
        
        # ------------------------------
        # EXCLUIR MÓDULOS (La dieta de DowP)
        # ------------------------------
        # '--exclude-module=yt_dlp', # Desactivado para evitar errores de librerías estandar (html.parser)
        # '--exclude-module=yt_dlp_ejs',
        
        # ------------------------------
        # COLLECT ALL (Crucial para SocketIO y dependencias complejas)
        # ------------------------------
        '--collect-all=customtkinter',
        '--collect-all=tkinterdnd2',
        '--collect-all=flask_socketio',
        '--collect-all=engineio',
    ]
    
    print("\n📦 Argumentos configurados. Iniciando PyInstaller...")
    
    # Ejecutar PyInstaller
    try:
        PyInstaller.__main__.run(args)
        
        # --- NUEVO: Copiar bin/ytdlp recién descargado al directorio dist/ directamente ---
        import shutil
        dist_dir = os.path.join("dist", f"{APP_NAME}")
        dist_bin_dir = os.path.join(dist_dir, "bin", "ytdlp")
        src_bin_dir = os.path.join("bin", "ytdlp")
        
        if os.path.exists(src_bin_dir):
            if os.path.exists(dist_bin_dir):
                shutil.rmtree(dist_bin_dir)
            shutil.copytree(src_bin_dir, dist_bin_dir)
            print(f"✅ Carpeta bin/ytdlp copiada directamente a {dist_dir} para actualizaciones portables.")
            
        print(f"\n✅ Compilación finalizada!")
        print(f"📁 El ejecutable y su carpeta están en: {dist_dir}/")
    except Exception as e:
        print(f"\n❌ Error en la compilación: {e}")

if __name__ == "__main__":
    build()
