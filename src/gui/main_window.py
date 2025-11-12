from flask import Flask, jsonify, request
from flask_socketio import SocketIO
import threading
import webbrowser
from tkinter import messagebox
import tkinter
import customtkinter as ctk
from customtkinter import filedialog
from PIL import Image
import requests
from io import BytesIO
import gc
import os
import re
import sys
from pathlib import Path
import subprocess
import json
import time
import shutil
import platform
import yt_dlp
import io

from datetime import datetime, timedelta
from src.core.downloader import get_video_info, download_media
from src.core.processor import FFmpegProcessor, CODEC_PROFILES
from src.core.exceptions import UserCancelledError, LocalRecodeFailedError
from src.core.processor import clean_and_convert_vtt_to_srt
from contextlib import redirect_stdout
from .batch_download_tab import BatchDownloadTab
from .single_download_tab import SingleDownloadTab

from .dialogs import ConflictDialog, LoadingWindow, CompromiseDialog, SimpleMessageDialog, SavePresetDialog, PlaylistErrorDialog
from src.core.constants import (
    VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, SINGLE_STREAM_AUDIO_CONTAINERS,
    FORMAT_MUXER_MAP, LANG_CODE_MAP, LANGUAGE_ORDER, DEFAULT_PRIORITY,
    EDITOR_FRIENDLY_CRITERIA, COMPATIBILITY_RULES
)


def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para desarrollo y para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

from main import PROJECT_ROOT, BIN_DIR

flask_app = Flask(__name__)
socketio = SocketIO(flask_app, async_mode='gevent', cors_allowed_origins='*')
main_app_instance = None

LATEST_FILE_PATH = None
LATEST_FILE_LOCK = threading.Lock()
ACTIVE_TARGET_SID = None  
CLIENTS = {}
AUTO_LINK_DONE = False

@socketio.on('connect')
def handle_connect():
    """Se ejecuta cuando un panel de extensión se conecta."""
    print(f"INFO: Nuevo cliente conectado con SID: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Se ejecuta cuando un panel de extensión se desconecta."""
    global ACTIVE_TARGET_SID
    if request.sid in CLIENTS:
        print(f"INFO: Cliente '{CLIENTS[request.sid]}' (SID: {request.sid}) se ha desconectado.")
        if request.sid == ACTIVE_TARGET_SID:
            ACTIVE_TARGET_SID = None
            print("INFO: El objetivo activo se ha desconectado. Ningún objetivo está enlazado.")
            socketio.emit('active_target_update', {'activeTarget': None})
        del CLIENTS[request.sid]

@socketio.on('register')
def handle_register(data):
    """
    Cuando un cliente se registra, comprobamos si es el que lanzó la app
    para enlazarlo automáticamente.
    
    CORREGIDO: Ahora valida si el cliente ya está registrado para evitar duplicados.
    """
    global ACTIVE_TARGET_SID, AUTO_LINK_DONE
    app_id = data.get('appIdentifier')
    
    if app_id:
        # ✅ NUEVA VALIDACIÓN: Solo registra si es la primera vez
        if request.sid not in CLIENTS:
            CLIENTS[request.sid] = app_id
            print(f"INFO: Cliente SID {request.sid} registrado como '{app_id}'.")
            
            # Solo intenta auto-enlace si es la primera vez
            if main_app_instance and not AUTO_LINK_DONE and app_id == main_app_instance.launch_target:
                ACTIVE_TARGET_SID = request.sid
                AUTO_LINK_DONE = True 
                print(f"INFO: Auto-enlace exitoso con '{app_id}' (SID: {request.sid}).")
                socketio.emit('active_target_update', {'activeTarget': CLIENTS[ACTIVE_TARGET_SID]})
            else:
                active_app = CLIENTS.get(ACTIVE_TARGET_SID)
                socketio.emit('active_target_update', {'activeTarget': active_app}, to=request.sid)
        else:
            # ✅ OPCIONAL: Si ya estaba registrado, solo envía el estado actual
            # Sin imprimir nada (evita spam en logs)
            active_app = CLIENTS.get(ACTIVE_TARGET_SID)
            socketio.emit('active_target_update', {'activeTarget': active_app}, to=request.sid)

@socketio.on('get_active_target')
def handle_get_active_target():
    """
    Un cliente pregunta quién es el objetivo activo.
    (Usado para la actualización periódica del estado en el panel).
    """
    active_app = CLIENTS.get(ACTIVE_TARGET_SID)
    socketio.emit('active_target_update', {'activeTarget': active_app}, to=request.sid)

@socketio.on('set_active_target')
def handle_set_active_target(data):
    """Un cliente solicita ser el nuevo objetivo activo."""
    global ACTIVE_TARGET_SID
    target_app_id = data.get('targetApp')
    sid_to_set = None
    for sid, app_id in CLIENTS.items():
        if app_id == target_app_id:
            sid_to_set = sid
            break
    if sid_to_set:
        ACTIVE_TARGET_SID = sid_to_set
        print(f"INFO: Nuevo objetivo activo establecido: '{CLIENTS[ACTIVE_TARGET_SID]}' (SID: {ACTIVE_TARGET_SID})")
        socketio.emit('active_target_update', {'activeTarget': CLIENTS[ACTIVE_TARGET_SID]})

@socketio.on('clear_active_target')
def handle_clear_active_target():
    """Un cliente solicita desvincularse sin desconectarse."""
    global ACTIVE_TARGET_SID

    if request.sid == ACTIVE_TARGET_SID:
        print(f"INFO: El objetivo activo '{CLIENTS.get(request.sid, 'desconocido')}' (SID: {request.sid}) se ha desvinculado.")

        ACTIVE_TARGET_SID = None

        socketio.emit('active_target_update', {'activeTarget': None})

def run_flask_app():
    """Función que corre el servidor. Usa gevent para WebSockets."""
    print("INFO: Iniciando servidor de integración en el puerto 7788 con WebSockets.")
    socketio.run(flask_app, host='0.0.0.0', port=7788, log_output=False)

if getattr(sys, 'frozen', False):
    APP_BASE_PATH = os.path.dirname(sys.executable)
else:
    APP_BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

class LoadingWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Iniciando...")
        self.geometry("350x120")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None) 
        self.transient(master) 
        self.lift()
        self.error_state = False
        win_width = 350
        win_height = 120
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = (screen_width // 2) - (win_width // 2)
        pos_y = (screen_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        self.label = ctk.CTkLabel(self, text="Preparando la aplicación, por favor espera...", wraplength=320)
        self.label.pack(pady=(20, 10), padx=20)
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.grab_set() 

    def update_progress(self, text, value):
        if not self.winfo_exists():
            return
        self.label.configure(text=text)
        if value >= 0:
            self.progress_bar.set(value)
        else: 
            self.error_state = True 
            self.progress_bar.configure(progress_color="red")
            self.progress_bar.set(1)

class MainWindow(ctk.CTk):
        
    def _get_best_available_info(self, url, options):
        """
        Ejecuta una simulación usando la API de yt-dlp para obtener información
        sobre el mejor formato disponible cuando la selección del usuario falla.
        """
        try:
            mode = options.get("mode", "Video+Audio")
            
            ydl_opts = {
                'no_warnings': True,
                'noplaylist': True,
                'quiet': True,
                'ffmpeg_location': self.ffmpeg_processor.ffmpeg_path
            }
            
            # Determinar el selector según el modo
            if mode == "Solo Audio":
                ydl_opts['format'] = 'ba/best'
            else:
                # Intentar con audio si está disponible, sino solo video
                ydl_opts['format'] = 'bv+ba/bv/best'

            # Configurar cookies
            cookie_mode = options.get("cookie_mode")
            if cookie_mode == "Archivo Manual..." and options.get("cookie_path"):
                ydl_opts['cookiefile'] = options["cookie_path"]
            elif cookie_mode != "No usar":
                browser_arg = options.get("selected_browser", "chrome")
                if options.get("browser_profile"):
                    browser_arg += f":{options['browser_profile']}"
                ydl_opts['cookiesfrombrowser'] = (browser_arg,)

            # Extraer información
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                return "No se pudo obtener información del video."

            # Construir mensaje detallado según el modo
            if mode == "Solo Audio":
                abr = info.get('abr') or info.get('tbr', 0)
                acodec = info.get('acodec', 'desconocido')
                if acodec and acodec != 'none':
                    acodec = acodec.split('.')[0].upper()
                
                ext = info.get('ext', 'N/A')
                filesize = info.get('filesize') or info.get('filesize_approx')
                
                message = f"🎵 Mejor audio disponible:\n\n"
                message += f"• Bitrate: ~{abr:.0f} kbps\n"
                message += f"• Códec: {acodec}\n"
                message += f"• Formato: {ext}\n"
                
                if filesize:
                    size_mb = filesize / (1024 * 1024)
                    message += f"• Tamaño: ~{size_mb:.1f} MB\n"
                
                return message
            
            else:  # Video+Audio
                # Información de video
                width = info.get('width', 'N/A')
                height = info.get('height', 'N/A')
                vcodec = info.get('vcodec', 'desconocido')
                if vcodec and vcodec != 'none':
                    vcodec = vcodec.split('.')[0].upper()
                
                fps = info.get('fps', 'N/A')
                vext = info.get('ext', 'N/A')
                
                # Información de audio
                acodec = info.get('acodec', 'desconocido')
                if acodec and acodec != 'none':
                    acodec = acodec.split('.')[0].upper()
                else:
                    acodec = "Sin audio"
                
                abr = info.get('abr') or info.get('tbr', 0)
                
                # Tamaño
                filesize = info.get('filesize') or info.get('filesize_approx')
                
                message = f"🎬 Mejor calidad disponible:\n\n"
                message += f"📹 Video:\n"
                message += f"   • Resolución: {width}x{height}\n"
                message += f"   • Códec: {vcodec}\n"
                
                if fps != 'N/A':
                    message += f"   • FPS: {fps}\n"
                
                message += f"   • Formato: {vext}\n\n"
                
                message += f"🔊 Audio:\n"
                message += f"   • Códec: {acodec}\n"
                
                if acodec != "Sin audio":
                    message += f"   • Bitrate: ~{abr:.0f} kbps\n"
                
                if filesize:
                    size_mb = filesize / (1024 * 1024)
                    message += f"\n📦 Tamaño estimado: ~{size_mb:.1f} MB"
                
                return message

        except Exception as e:
            error_msg = str(e)
            print(f"ERROR: Falló la simulación de descarga: {error_msg}")
            
            # Mensaje más amigable para el usuario
            return (
                "❌ No se pudieron obtener los detalles del formato alternativo.\n\n"
                f"Razón: {error_msg[:100]}...\n\n"
                "Puedes intentar:\n"
                "• Verificar la URL\n"
                "• Configurar cookies si el video es privado\n"
                "• Intentar más tarde si hay límite de peticiones"
            )

    def __init__(self, launch_target=None, project_root=None):
        super().__init__()

        self.VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
        self.AUDIO_EXTENSIONS = AUDIO_EXTENSIONS
        self.SINGLE_STREAM_AUDIO_CONTAINERS = SINGLE_STREAM_AUDIO_CONTAINERS
        self.FORMAT_MUXER_MAP = FORMAT_MUXER_MAP
        self.LANG_CODE_MAP = LANG_CODE_MAP
        self.LANGUAGE_ORDER = LANGUAGE_ORDER
        self.DEFAULT_PRIORITY = DEFAULT_PRIORITY
        self.EDITOR_FRIENDLY_CRITERIA = EDITOR_FRIENDLY_CRITERIA
        self.COMPATIBILITY_RULES = COMPATIBILITY_RULES

        global main_app_instance, ACTIVE_TARGET_SID, LATEST_FILE_LOCK, socketio
        main_app_instance = self

        # --- Adjuntar globales para pasarlos a las pestañas ---
        self.ACTIVE_TARGET_SID_accessor = lambda: ACTIVE_TARGET_SID
        self.LATEST_FILE_LOCK = LATEST_FILE_LOCK
        self.socketio = socketio

        # --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
        # 2. Determina la ruta base (PARA LOS BINARIOS)
        if getattr(sys, 'frozen', False):
            # Modo .exe: la ruta es el directorio del ejecutable
            self.APP_BASE_PATH = os.path.dirname(sys.executable)
        elif project_root:
            # Modo Dev: usamos la ruta pasada desde main.py
            self.APP_BASE_PATH = project_root
        else:
            # Fallback (no debería usarse, pero es seguro tenerlo)
            self.APP_BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

        # 3. Define las rutas de configuración (PARA LOS DATOS DE USUARIO)
        
        # --- INICIO DE LA MODIFICACIÓN (LA BUENA) ---
        # 1. Definir la carpeta de datos del usuario en %APPDATA%
        self.APP_DATA_DIR = os.path.join(os.path.expandvars('%APPDATA%'), 'DowP')

        # 2. Asegurarse de que esa carpeta exista
        try:
            os.makedirs(self.APP_DATA_DIR, exist_ok=True)
        except Exception as e:
            print(f"ERROR: No se pudo crear la carpeta de datos en %APPDATA%: {e}")
            # Fallback a la carpeta antigua si %APPDATA% falla
            self.APP_DATA_DIR = self.APP_BASE_PATH

        # 3. Definir las rutas usando la nueva carpeta de datos
        self.SETTINGS_FILE = os.path.join(self.APP_DATA_DIR, "app_settings.json")
        self.PRESETS_FILE = os.path.join(self.APP_DATA_DIR, "presets.json") 
        # --- FIN DE LA MODIFICACIÓN ---

        self.launch_target = launch_target
        self.is_shutting_down = False
        self.cancellation_event = threading.Event()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.title(f"DowP {SingleDownloadTab.APP_VERSION}")
        self.iconbitmap(resource_path("DowP-icon.ico"))
        win_width = 835
        win_height = 950
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = (screen_width // 2) - (win_width // 2)
        pos_y = (screen_height // 2) - (win_height // 2)

        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        self.is_updating_dimension = False
        self.current_aspect_ratio = None
        self.minsize(835, 915)
        ctk.set_appearance_mode("Dark")
        server_thread = threading.Thread(target=run_flask_app, daemon=True)
        server_thread.start()
        print("INFO: Servidor de integración iniciado en el puerto 7788.")
        
        self.ui_request_event = threading.Event()
        self.ui_request_data = {}
        self.ui_response_event = threading.Event()
        self.ui_response_data = {}
        
        # --- INICIALIZAR VALORES POR DEFECTO ---
        # Define todos los atributos ANTES del bloque try
        self.default_download_path = ""
        self.batch_download_path = "" # <-- AÑADE ESTA LÍNEA
        self.cookies_path = ""
        self.cookies_mode_saved = "No usar"
        self.selected_browser_saved = "firefox"
        self.browser_profile_saved = ""
        self.ffmpeg_update_snooze_until = None
        self.custom_presets = []
        self.batch_playlist_analysis_saved = True
        self.batch_auto_import_saved = True
        self.quick_preset_saved = ""
        self.recode_settings = {}
        self.apply_quick_preset_checkbox_state = False
        self.keep_original_quick_saved = True
        
        # --- INTENTAR CARGAR CONFIGURACIÓN GUARDADA ---
        try:
            print(f"DEBUG: Intentando cargar configuración desde: {self.SETTINGS_FILE}")
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    # Sobrescribe los valores por defecto con los que están guardados
                    self.default_download_path = settings.get("default_download_path", self.default_download_path)
                    self.batch_download_path = settings.get("batch_download_path", self.batch_download_path)
                    self.cookies_path = settings.get("cookies_path", self.cookies_path)
                    self.cookies_mode_saved = settings.get("cookies_mode", self.cookies_mode_saved)
                    self.selected_browser_saved = settings.get("selected_browser", self.selected_browser_saved)
                    self.browser_profile_saved = settings.get("browser_profile", self.browser_profile_saved)
                    snooze_str = settings.get("ffmpeg_update_snooze_until")
                    self.batch_playlist_analysis_saved = settings.get("batch_playlist_analysis", self.batch_playlist_analysis_saved)
                    self.batch_auto_import_saved = settings.get("batch_auto_import", self.batch_auto_import_saved)
                    self.quick_preset_saved = settings.get("quick_preset_saved", self.quick_preset_saved)
                    if snooze_str:
                        self.ffmpeg_update_snooze_until = datetime.fromisoformat(snooze_str)
                    self.recode_settings = settings.get("recode_settings", self.recode_settings)
                
                    self.apply_quick_preset_checkbox_state = settings.get("apply_quick_preset_enabled", self.apply_quick_preset_checkbox_state)
                    self.keep_original_quick_saved = settings.get("keep_original_quick_enabled", self.keep_original_quick_saved) 
                print(f"DEBUG: Configuración cargada exitosamente.")
            else:
                print("DEBUG: Archivo de configuración no encontrado. Usando valores por defecto.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: Fallo al cargar configuración: {e}. Usando valores por defecto.")
            # No se necesita 'pass' porque los valores por defecto ya están establecidos

        self.ffmpeg_processor = FFmpegProcessor()
        self.tab_view = ctk.CTkTabview(self, anchor="nw")
        self.tab_view.pack(expand=True, fill="both", padx=5, pady=5)
        
        # (Cargará la clase de nuestro nuevo archivo)
        self.tab_view.add("Proceso Único")
        self.single_tab = SingleDownloadTab(master=self.tab_view.tab("Proceso Único"), app=self)
        
        # Añadir la pestaña de Lotes (como placeholder)
        self.tab_view.add("Proceso por Lotes")
        self.batch_tab = BatchDownloadTab(master=self.tab_view.tab("Proceso por Lotes"), app=self)

        

        self.run_initial_setup()
        self._check_for_ui_requests()
        self._last_clipboard_check = "" 
        self.bind("<FocusIn>", self._on_app_focus)
    
    def run_initial_setup(self):
        """
        Inicia la aplicación, configura la UI y lanza una comprobación de
        FFmpeg en segundo plano (solo si es necesario).
        """
        print("INFO: Configurando UI y lanzando comprobación de FFmpeg en segundo plano...")

        # 1. Comprobación de actualización de la app (esto se queda igual)
        from src.core.setup import check_app_update
        threading.Thread(
            target=lambda: self.on_update_check_complete(check_app_update(self.single_tab.APP_VERSION)), # CORREGIDO
            daemon=True
        ).start()
        
        from src.core.setup import check_environment_status
        
        # 2. Definir rutas
        ffmpeg_exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        ffmpeg_path = os.path.join(BIN_DIR, ffmpeg_exe_name)
        
        # --- AÑADIR ESTAS LÍNEAS ---
        deno_exe_name = "deno.exe" if platform.system() == "Windows" else "deno"
        # (main.py ya define DENO_BIN_DIR, pero main_window.py necesita su propia referencia)
        DENO_BIN_DIR = os.path.join(BIN_DIR, "deno")
        deno_path = os.path.join(DENO_BIN_DIR, deno_exe_name)

        # 3. Comprobar si AMBOS existen
        if not os.path.exists(ffmpeg_path) or not os.path.exists(deno_path): # <-- MODIFICADO
            # 4a. NO EXISTE (alguno de los dos): ...
            print("INFO: FFmpeg o Deno no detectados. Ejecutando comprobador de entorno completo...")
            threading.Thread(
                target=lambda: self.on_status_check_complete(check_environment_status(lambda text, val: None)),
                daemon=True
            ).start()
        else:
            # 4b. SÍ EXISTE: Cargar solo la versión local, sin llamar a la API.
            print("INFO: FFmpeg detectado localmente. Omitiendo la comprobación de API de GitHub.")
            
            local_version = "Desconocida"
            version_file = os.path.join(BIN_DIR, "ffmpeg_version.txt")
            if os.path.exists(version_file):
                try:
                    with open(version_file, 'r') as f:
                        local_version = f.read().strip()
                except Exception as e:
                    print(f"ADVERTENCIA: No se pudo leer el archivo de versión de FFmpeg: {e}")
            
            # 5. Actualizar la UI directamente con la info local
            self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Instalado)")
            self.single_tab.update_ffmpeg_button.configure(state="normal", text="Buscar Actualizaciones de FFmpeg")

            # --- AÑADIR Lógica de Deno ---
            local_deno_version = "Desconocida"
            deno_version_file = os.path.join(DENO_BIN_DIR, "deno_version.txt")
            if os.path.exists(deno_version_file):
                try:
                    with open(deno_version_file, 'r') as f:
                        local_deno_version = f.read().strip()
                except Exception as e:
                    print(f"ADVERTENCIA: No se pudo leer el archivo de versión de Deno: {e}")
            
            self.single_tab.deno_status_label.configure(text=f"Deno: {local_deno_version} \n(Instalado)")
            self.single_tab.update_deno_button.configure(state="normal", text="Buscar Actualizaciones de Deno")
        
        # 6. Detección de códecs (esto se ejecuta siempre, pero es local, no usa API)
        self.ffmpeg_processor.run_detection_async(self.on_ffmpeg_detection_complete) # CORREGIDO
        
    def on_update_check_complete(self, update_info):
        """Callback que se ejecuta cuando la comprobación de versión termina. Ahora inicia la descarga."""
        if update_info.get("update_available"):
            latest_version = update_info.get("latest_version")
            self.single_tab.release_page_url = update_info.get("release_url") # Guardamos por si acaso

            is_prerelease = update_info.get("is_prerelease", False)
            version_type = "Pre-release" if is_prerelease else "versión"
            status_text = f"¡Nueva {version_type} {latest_version} disponible!"

            self.single_tab.app_status_label.configure(text=status_text, text_color="#52a2f2")

            # --- CAMBIO: INICIA EL PROCESO DE ACTUALIZACIÓN ---
            installer_url = update_info.get("installer_url")
            if installer_url:
                # Preguntar al usuario si quiere actualizar AHORA
                user_response = messagebox.askyesno(
                    "Actualización Disponible",
                    f"Hay una nueva {version_type} ({latest_version}) de DowP disponible.\n\n"
                    "¿Deseas descargarla e instalarla ahora?\n\n"
                    "(DowP se cerrará para completar la instalación)"
                )
                self.lift() # Asegura que la ventana principal esté al frente
                self.focus_force()

                if user_response:
                    # Llamar a la nueva función para descargar y ejecutar
                    # Pasamos la URL y la versión para mostrar en el progreso
                    self._iniciar_auto_actualizacion(installer_url, latest_version)
                else:
                    # El usuario dijo NO, solo configuramos el botón para que pueda hacerlo manualmente
                    self.single_tab.update_app_button.configure(text=f"Descargar v{latest_version}", state="normal", fg_color=self.single_tab.DOWNLOAD_BTN_COLOR)
            else:
                # No se encontró el .exe, solo habilitar el botón para ir a la página
                print("ADVERTENCIA: Se detectó una nueva versión pero no se encontró el instalador .exe en los assets.")
                self.single_tab.update_app_button.configure(text=f"Ir a Descargas (v{latest_version})", state="normal", fg_color=self.single_tab.DOWNLOAD_BTN_COLOR)


        elif "error" in update_info:
            self.single_tab.app_status_label.configure(text=f"DowP v{self.single_tab.APP_VERSION} - Error al verificar", text_color="orange")
            self.single_tab.update_app_button.configure(text="Reintentar", state="normal", fg_color="gray")
        else:
            self.single_tab.app_status_label.configure(text=f"DowP v{self.single_tab.APP_VERSION} - Estás al día ✅")
            self.single_tab.update_app_button.configure(text="Sin actualizaciones", state="disabled")


    def on_status_check_complete(self, status_info, force_check=False):
        """
        Callback FINAL que gestiona el estado de FFmpeg.
        """
        status = status_info.get("status")
        
        self.single_tab.update_ffmpeg_button.configure(state="normal", text="Buscar Actualizaciones de FFmpeg")
        self.single_tab.update_deno_button.configure(state="normal", text="Buscar Actualizaciones de Deno")

        if status == "error":
            messagebox.showerror("Error Crítico de Entorno", status_info.get("message"))
            return

        # --- Variables de FFmpeg ---
        local_version = status_info.get("local_version") or "No encontrado"
        latest_version = status_info.get("latest_version")
        download_url = status_info.get("download_url")
        ffmpeg_exists = status_info.get("ffmpeg_path_exists")
        
        # --- AÑADIR: Variables de Deno ---
        local_deno_version = status_info.get("local_deno_version") or "No encontrado"
        latest_deno_version = status_info.get("latest_deno_version")
        deno_download_url = status_info.get("deno_download_url")
        deno_exists = status_info.get("deno_path_exists")
        
        should_download = False
        should_download_deno = False # <-- AÑADIR
        
        # --- Lógica de descarga de FFmpeg (existente) ---
        if not ffmpeg_exists:
            print("INFO: FFmpeg no encontrado. Iniciando descarga automática.")
            self.single_tab.update_progress(0, "FFmpeg no encontrado. Iniciando descarga automática...")
            should_download = True
        else:
            update_available = local_version != latest_version
            snoozed = self.ffmpeg_update_snooze_until and datetime.now() < self.ffmpeg_update_snooze_until
                        
            # La condición "(not snoozed or force_check)" se ha cambiado a "force_check"
            # Ahora el pop-up solo saldrá si el usuario presionó el botón (force_check=True)
            if update_available and force_check:
            
                user_response = messagebox.askyesno(
                    "Actualización Disponible",
                    f"Hay una nueva versión de FFmpeg disponible.\n\n"
                    f"Versión Actual: {local_version}\n"
                    f"Versión Nueva: {latest_version}\n\n"
                    "¿Deseas actualizar ahora?"
                )
                self.lift() 
                if user_response:
                    should_download = True
                    self.ffmpeg_update_snooze_until = None 
                else:
                    self.ffmpeg_update_snooze_until = datetime.now() + timedelta(days=15)
                    self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualización pospuesta)") 
                self.single_tab.save_settings()
                self.batch_tab.save_settings()
                
            elif update_available and snoozed:
                print(f"DEBUG: Actualización de FFmpeg omitida. Snooze activo hasta {self.ffmpeg_update_snooze_until}.")
                self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualización pospuesta)") 
            else:
                self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualizado)") 

        # --- AÑADIR: Lógica de descarga de Deno ---
        if not deno_exists:
            print("INFO: Deno no encontrado. Iniciando descarga automática.")
            self.single_tab.update_progress(0, "Deno (requerido por YouTube) no encontrado. Iniciando descarga...")
            should_download_deno = True
        else:
            deno_update_available = local_deno_version != latest_deno_version
            # (No hay 'snooze' para Deno por ahora, podemos añadirlo luego si quieres)
            
            if deno_update_available and force_check:
                user_response = messagebox.askyesno(
                    "Actualización de Deno Disponible",
                    f"Hay una nueva versión de Deno disponible.\n\n"
                    f"Versión Actual: {local_deno_version}\n"
                    f"Versión Nueva: {latest_deno_version}\n\n"
                    "¿Deseas actualizar ahora?"
                )
                self.lift() 
                if user_response:
                    should_download_deno = True
            elif deno_update_available:
                 self.single_tab.deno_status_label.configure(text=f"Deno: {local_deno_version} \n(Actualización disponible)")
            else:
                self.single_tab.deno_status_label.configure(text=f"Deno: {local_deno_version} \n(Actualizado)")

        if should_download:
            if not download_url:
                messagebox.showerror("Error", "No se pudo obtener la URL de descarga para FFmpeg.")
                return

            self.single_tab.update_progress(0, f"Iniciando descarga de FFmpeg {latest_version}...") 
            from src.core.setup import download_and_install_ffmpeg
            
            def download_task():
                success = download_and_install_ffmpeg(latest_version, download_url, self.single_tab._handle_download_progress) 
                if success:
                    # --- AÑADIR ESTE BLOQUE ---
                    # (main.py define FFMPEG_BIN_DIR, pero necesitamos la ruta aquí)
                    ffmpeg_bin_path = os.path.join(BIN_DIR, "ffmpeg")
                    if ffmpeg_bin_path not in os.environ['PATH']:
                        print(f"INFO: Actualizando PATH en tiempo de ejecución con: {ffmpeg_bin_path}")
                        os.environ['PATH'] = ffmpeg_bin_path + os.pathsep + os.environ['PATH']
                    # --- FIN DEL BLOQUE ---

                    self.after(0, self.ffmpeg_processor.run_detection_async,  
                            lambda s, m: self.on_ffmpeg_detection_complete(s, m, show_ready_message=True))
                    self.after(0, lambda: self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {latest_version} \n(Instalado)")) 
                else:
                    self.after(0, self.single_tab.update_progress, 0, "Falló la descarga de FFmpeg.") 

            threading.Thread(target=download_task, daemon=True).start()

        # --- AÑADIR: Lógica de Hilo de Descarga (Deno) ---
        if should_download_deno:
            if not deno_download_url:
                messagebox.showerror("Error", "No se pudo obtener la URL de descarga para Deno.")
                return

            self.single_tab.update_progress(0, f"Iniciando descarga de Deno {latest_deno_version}...") 
            from src.core.setup import download_and_install_deno # <-- Importar la nueva función
            
            def download_deno_task():
                success = download_and_install_deno(latest_deno_version, deno_download_url, self.single_tab._handle_download_progress) 
                if success:
                    # (main.py define DENO_BIN_DIR, pero necesitamos la ruta aquí)
                    deno_bin_path = os.path.join(BIN_DIR, "deno")
                    if deno_bin_path not in os.environ['PATH']:
                        print(f"INFO: Actualizando PATH en tiempo de ejecución con: {deno_bin_path}")
                        os.environ['PATH'] = deno_bin_path + os.pathsep + os.environ['PATH']
                    
                    # Deno no necesita "detección" como los códecs de FFmpeg, solo actualizamos la UI
                    self.after(0, lambda: self.single_tab.deno_status_label.configure(text=f"Deno: {latest_deno_version} \n(Instalado)")) 
                    self.after(0, self.single_tab.update_progress, 100, "✅ Deno instalado correctamente. Listo para usar.")
                else:
                    self.after(0, self.single_tab.update_progress, 0, "Falló la descarga de Deno.")

            threading.Thread(target=download_deno_task, daemon=True).start()

    def on_ffmpeg_detection_complete(self, success, message, show_ready_message=False):
        if success:
            self.single_tab.recode_video_checkbox.configure(text="Recodificar Video", state="normal") 
            self.single_tab.recode_audio_checkbox.configure(text="Recodificar Audio", state="normal")
            
            self.single_tab.apply_quick_preset_checkbox.configure(text="Activar recodificación Rápida", state="normal")
            
            if self.ffmpeg_processor.gpu_vendor:
                self.single_tab.gpu_radio.configure(text="GPU", state="normal")
                self.single_tab.cpu_radio.pack_forget() 
                self.single_tab.gpu_radio.pack_forget() 
                self.single_tab.gpu_radio.pack(side="left", padx=10) 
                self.single_tab.cpu_radio.pack(side="left", padx=20) 
            else:
                self.single_tab.gpu_radio.configure(text="GPU (No detectada)")
                self.single_tab.proc_type_var.set("CPU") 
                self.single_tab.gpu_radio.configure(state="disabled") 
            
            self.single_tab.update_codec_menu()
            
            if show_ready_message:
                self.single_tab.update_progress(100, "✅ FFmpeg instalado correctamente. Listo para usar.") 
        else:
            print(f"FFmpeg detection error: {message}")
            self.single_tab.recode_video_checkbox.configure(text="Recodificación no disponible", state="disabled") 
            self.single_tab.recode_audio_checkbox.configure(text="(Error FFmpeg)", state="disabled") 
            
            self.single_tab.apply_quick_preset_checkbox.configure(text="Recodificación no disponible (Error FFmpeg)", state="disabled") 
            self.single_tab.apply_quick_preset_checkbox.deselect() 

    def _iniciar_auto_actualizacion(self, installer_url, version_str):
        """
        Descarga el instalador de la nueva versión en un hilo separado,
        lo ejecuta y cierra la aplicación actual.
        """
        print(f"INFO: Iniciando descarga de la actualización v{version_str} desde {installer_url}")

        # Deshabilitar botones mientras se descarga
        self.single_tab.update_app_button.configure(text=f"Descargando v{version_str}...", state="disabled")
        self.single_tab.update_ffmpeg_button.configure(state="disabled") # Opcional: deshabilitar también este
        self.single_tab.download_button.configure(state="disabled") # Deshabilitar descarga/proceso principal

        # Mostrar progreso inicial
        self.single_tab.update_progress(0, f"Descargando actualización v{version_str}...")

        def download_and_run():
            temp_dir = None # Inicializar fuera del try
            try:
                # --- Descargar el instalador ---
                import tempfile # Importar aquí para mantenerlo local
                import requests # Ya deberías tenerlo importado arriba
                import subprocess # Ya deberías tenerlo importado arriba
                import os # Ya deberías tenerlo importado arriba

                # Crear un directorio temporal seguro
                temp_dir = tempfile.mkdtemp(prefix="dowp_update_")
                installer_filename = os.path.basename(installer_url) # Ej: DowP_v1.2.1_setup.exe
                installer_path = os.path.join(temp_dir, installer_filename)

                # Descargar con progreso (similar a como se descarga FFmpeg)
                last_reported_progress = -1
                with requests.get(installer_url, stream=True, timeout=180) as r: # Timeout más largo por si acaso
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded_size = 0
                    with open(installer_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192 * 4): # Chunk más grande
                            if not chunk: continue
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            if total_size > 0:
                                progress_percent = (downloaded_size / total_size) * 100
                                # Actualiza la UI desde el hilo principal usando 'after'
                                self.after(0, self.single_tab.update_progress, progress_percent / 100.0,
                                           f"Descargando: {downloaded_size / (1024*1024):.1f} / {total_size / (1024*1024):.1f} MB")
                                last_reported_progress = int(progress_percent)

                self.after(0, self.single_tab.update_progress, 1.0, "Descarga completa. Iniciando instalador...")
                print(f"INFO: Instalador descargado en: {installer_path}")

                # --- Ejecutar el instalador y cerrar DowP ---
                # Usamos Popen para que no espere a que termine
                # CREATE_NEW_PROCESS_GROUP es para que el instalador no se cierre si cerramos la consola
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                subprocess.Popen([installer_path], creationflags=creationflags)

                print("INFO: Instalador iniciado. Cerrando DowP para permitir la actualización...")
                # Programar el cierre de la ventana principal desde el hilo principal
                self.after(500, self.destroy) # Espera medio segundo antes de cerrar

            except Exception as e:
                print(f"ERROR: Falló el proceso de auto-actualización: {e}")
                # Si falla, informa al usuario y reactiva los botones
                self.after(0, lambda: messagebox.showerror("Error de Actualización",
                                                           f"No se pudo completar la actualización automática:\n\n{e}\n\n"
                                                           "Puedes intentar descargarla manualmente desde la página de releases."))
                # Reactivar botones en la UI desde el hilo principal
                self.after(0, self._reset_buttons_to_original_state) # Reutiliza tu función de reseteo
                self.after(0, lambda: self.single_tab.update_progress(0, "❌ Falló la actualización automática."))
                # Limpiar directorio temporal si se creó y falló
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        import shutil
                        shutil.rmtree(temp_dir)
                        print(f"DEBUG: Directorio temporal de actualización eliminado: {temp_dir}")
                    except Exception as clean_e:
                        print(f"ADVERTENCIA: No se pudo eliminar el directorio temporal {temp_dir}: {clean_e}")

        # Iniciar la descarga en un hilo separado para no bloquear la UI
        threading.Thread(target=download_and_run, daemon=True).start()

    def _check_for_ui_requests(self):
        """
        Verifica si un hilo secundario ha solicitado una acción de UI.
        """
        if self.ui_request_event.is_set(): # CORREGIDO
            self.ui_request_event.clear() # CORREGIDO
            request_type = self.ui_request_data.get("type") # CORREGIDO

            if request_type == "ask_yes_no":
                title = self.ui_request_data.get("title", "Confirmar") # CORREGIDO
                message = self.ui_request_data.get("message", "¿Estás seguro?") # CORREGIDO
                
                result = messagebox.askyesno(title, message)
                
                self.ui_response_data["result"] = result # CORREGIDO
                self.lift() # CORREGIDO
                self.ui_response_event.set() # CORREGIDO

            elif request_type == "ask_conflict":
                filename = self.ui_request_data.get("filename", "") # CORREGIDO
                dialog = ConflictDialog(self, filename)


                self.wait_window(dialog) # CORREGIDO
                self.lift() # CORREGIDO
                self.focus_force() # CORREGIDO
                self.ui_response_data["result"] = dialog.result # CORREGIDO
                self.ui_response_event.set() # CORREGIDO
                
            elif request_type == "ask_compromise":
                details = self.ui_request_data.get("details", "Detalles no disponibles.") 
                dialog = CompromiseDialog(self, details)
                self.wait_window(dialog) 
                self.lift() 
                self.focus_force() 
                self.ui_response_data["result"] = dialog.result 
                self.ui_response_event.set() 
            
            elif request_type == "ask_playlist_error":
                url_fragment = self.ui_request_data.get("filename", "esta URL")
                dialog = PlaylistErrorDialog(self, url_fragment)
                
                self.wait_window(dialog)
                self.lift()
                self.focus_force()
                self.ui_response_data["result"] = dialog.result
                self.ui_response_event.set()
                
        self.after(100, self._check_for_ui_requests) # CORREGIDO

    def save_settings(self):
        """
        Recopila todos los ajustes de la app y los guarda en app_settings.json.
        Esta es la ÚNICA función que debe escribir en el archivo.
        """
        # --- CORRECCIÓN APLICADA: Sincronizar desde las pestañas antes de guardar ---
        # Guardar primero la pestaña NO activa, luego la ACTIVA, para que la activa tenga prioridad
        # en los ajustes globales (como default_download_path).
        current_tab = self.tab_view.get()
        if current_tab == "Proceso Único":
             if hasattr(self, 'batch_tab'): self.batch_tab.save_settings()
             if hasattr(self, 'single_tab'): self.single_tab.save_settings()
        else:
             if hasattr(self, 'single_tab'): self.single_tab.save_settings()
             if hasattr(self, 'batch_tab'): self.batch_tab.save_settings()
        # --- FIN DE LA CORRECCIÓN ---

        # 3. Crear el diccionario de configuración final
        settings_to_save = {
            "default_download_path": self.default_download_path,
            "batch_download_path": self.batch_download_path,
            "ffmpeg_update_snooze_until": self.ffmpeg_update_snooze_until.isoformat() if self.ffmpeg_update_snooze_until else None,
            "custom_presets": self.custom_presets,

            # Cookies
            "cookies_path": self.cookies_path,
            "cookies_mode": self.cookies_mode_saved,
            "selected_browser": self.selected_browser_saved,
            "browser_profile": self.browser_profile_saved,

            # Pestaña Individual (Modo Rápido)
            "apply_quick_preset_enabled": self.apply_quick_preset_checkbox_state,
            "keep_original_quick_enabled": self.keep_original_quick_saved,
            "quick_preset_saved": self.quick_preset_saved,

            # Pestaña Individual (Modo Manual)
            "recode_settings": self.recode_settings,

            # Pestaña de Lotes
            "batch_playlist_analysis": self.batch_playlist_analysis_saved,
            "batch_auto_import": self.batch_auto_import_saved
        }

        # 4. Escribir en el archivo
        try:
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(settings_to_save, f, indent=4)
        except IOError as e:
            print(f"ERROR: Fallo al guardar configuración central: {e}")

    def on_closing(self):
        """
        Se ejecuta cuando el usuario intenta cerrar la ventana.
        Gestiona la cancelación, limpieza y confirmación de forma robusta.
        """
        if self.single_tab.active_operation_thread and self.single_tab.active_operation_thread.is_alive():
            if messagebox.askokcancel("Confirmar Salida", "Hay una operación en curso. ¿Estás seguro de que quieres salir?"):
                self.is_shutting_down = True 
                self.attributes("-disabled", True)
                self.single_tab.progress_label.configure(text="Cancelando y limpiando, por favor espera...")
                self.cancellation_event.set()
                self.after(100, self._wait_for_thread_to_finish_and_destroy)
        else:
            self.save_settings() 
            self.destroy()

    def _wait_for_thread_to_finish_and_destroy(self):
        """
        Vigilante que comprueba si el hilo de trabajo ha terminado.
        Una vez que termina (después de su limpieza), cierra la ventana.
        """
        if self.single_tab.active_operation_thread and self.single_tab.active_operation_thread.is_alive():
            self.after(100, self._wait_for_thread_to_finish_and_destroy)
        else:
            self.save_settings() 
            self.destroy()

    # --- AÑADIR ESTA NUEVA FUNCIÓN (disparador con retraso) ---
    def _on_app_focus(self, event=None):
        """
        Se llama cuando la ventana de la aplicación gana el foco.
        Espera 50ms para que la UI (como el cambio de pestaña) se estabilice
        antes de comprobar el portapapeles.
        """
        self.after(50, self._check_clipboard_and_paste)

    # --- ESTA ES LA FUNCIÓN ANTERIOR RENOMBRADA ---
    def _check_clipboard_and_paste(self):
        """
        Comprueba el portapapeles y pega automáticamente si es una URL.
        """
        try:
            clipboard_content = self.clipboard_get()
        except (tkinter.TclError, Exception):
            clipboard_content = "" # Portapapeles vacío o con datos no-texto

        # 1. Evitar re-pegar si el contenido no ha cambiado
        if not clipboard_content or clipboard_content == self._last_clipboard_check:
            return
        
        # 2. Actualizar el contenido "visto"
        self._last_clipboard_check = clipboard_content

        # 3. Validar si es una URL (regex simple)
        url_regex = re.compile(r'^(https|http)://[^\s/$.?#].[^\s]*$')
        if not url_regex.match(clipboard_content):
            return # No es una URL válida

        # 4. Determinar qué pestaña está activa (AHORA SÍ FUNCIONA)
        active_tab_name = self.tab_view.get()
        target_entry = None

        if active_tab_name == "Proceso Único":
            target_entry = self.single_tab.url_entry
        elif active_tab_name == "Proceso por Lotes":
            target_entry = self.batch_tab.url_entry

        # 5. Pegar la URL, REEMPLAZANDO el contenido
        if target_entry:
            # Si el texto ya es el mismo, no hacer nada (evita re-pegar)
            if target_entry.get() == clipboard_content:
                return

            print(f"DEBUG: URL detectada en portapapeles. Reemplazando en '{active_tab_name}'.")
            target_entry.delete(0, 'end') # BORRAR contenido actual
            target_entry.insert(0, clipboard_content) # INSERTAR nuevo contenido
            
            # Actualizar el estado del botón en la pestaña individual
            if active_tab_name == "Proceso Único":
                self.single_tab.update_download_button_state()