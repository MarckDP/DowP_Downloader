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
    """Actualiza yt-dlp y plugins a la última versión antes de compilar."""
    print("🔄 Verificando actualizaciones de yt-dlp y plugins...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "yt-dlp-ejs"])
        print("✅ yt-dlp y yt-dlp-ejs están actualizados.")
    except Exception as e:
        print(f"⚠️ Warning: No se pudo actualizar automáticamente: {e}")

def build():
    # 1. Actualizar dependencias críticas
    update_ytdlp()
    
    # 2. Obtener versión
    version = get_version()
    print(f"\n🚀 Iniciando compilación de {APP_NAME} v{version}...")
    
    # Separador de PATH en PyInstaller según SO
    path_sep = ';'
    
    # Preparar los argumentos de PyInstaller
    args = [
        ENTRY_POINT,
        '--name=%s' % f"{APP_NAME}_{version}",
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
        
        '--hidden-import=yt_dlp',
        '--hidden-import=packaging',
        
        # ------------------------------
        # COLLECT ALL (Crucial para SocketIO y dependencias complejas)
        # ------------------------------
        '--collect-all=customtkinter',
        '--collect-all=tkinterdnd2',
        '--collect-all=flask_socketio',
        '--collect-all=engineio',
        '--collect-all=yt_dlp',
        '--collect-all=yt_dlp_ejs',
    ]
    
    print("\n📦 Argumentos configurados. Iniciando PyInstaller...")
    
    # Ejecutar PyInstaller
    try:
        PyInstaller.__main__.run(args)
        print(f"\n✅ Compilación finalizada!")
        print(f"📁 El ejecutable y su carpeta están en: dist/{APP_NAME}_{version}/")
    except Exception as e:
        print(f"\n❌ Error en la compilación: {e}")

if __name__ == "__main__":
    build()
