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
from .dialogs import ConflictDialog, LoadingWindow, CompromiseDialog, SimpleMessageDialog, SavePresetDialog
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
from main import PROJECT_ROOT

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
    """
    global ACTIVE_TARGET_SID, AUTO_LINK_DONE
    app_id = data.get('appIdentifier')
    
    if app_id:
        CLIENTS[request.sid] = app_id
        print(f"INFO: Cliente SID {request.sid} registrado como '{app_id}'.")
        
        if main_app_instance and not AUTO_LINK_DONE and app_id == main_app_instance.launch_target:
            ACTIVE_TARGET_SID = request.sid
            AUTO_LINK_DONE = True 
            print(f"INFO: Auto-enlace exitoso con '{app_id}' (SID: {request.sid}).")
            socketio.emit('active_target_update', {'activeTarget': CLIENTS[ACTIVE_TARGET_SID]})
        else:
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

SETTINGS_FILE = os.path.join(APP_BASE_PATH, "app_settings.json")
PRESETS_FILE = os.path.join(APP_BASE_PATH, "presets.json") 


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
        Ejecuta una simulación usando la API de yt-dlp, incluyendo toda la lógica de cookies.
        """
        try:
            ydl_opts = {
                'no_warnings': True,
                'noplaylist': True,
                'format': 'ba' if options.get("mode") == "Solo Audio" else 'bv+ba',
                'ffmpeg_location': self.ffmpeg_processor.ffmpeg_path
            }

            cookie_mode = options.get("cookie_mode")
            if cookie_mode == "Archivo Manual..." and options.get("cookie_path"):
                ydl_opts['cookiefile'] = options["cookie_path"]
            elif cookie_mode != "No usar":
                browser_arg = options.get("selected_browser")
                if options.get("browser_profile"):
                    browser_arg += f":{options['browser_profile']}"
                ydl_opts['cookiesfrombrowser'] = (browser_arg,)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if options.get("mode") == "Solo Audio":
                abr = info.get('abr', 0)
                acodec = info.get('acodec', 'N/A').split('.')[0]
                return f"Audio: ~{abr:.0f} kbps ({acodec})"
            
            vcodec = info.get('vcodec', 'N/A').split('.')[0]
            resolution = f"{info.get('width')}x{info.get('height')}"
            abr = info.get('abr', 0)
            acodec = info.get('acodec', 'N/A').split('.')[0]
            return f"Video: {resolution} ({vcodec})  |  Audio: ~{abr:.0f} kbps ({acodec})"

        except Exception as e:
            print(f"ERROR: Falló la simulación de descarga (API Completa): {e}")
            return "No se pudieron obtener los detalles."

    def __init__(self, launch_target=None):
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

        global main_app_instance, ACTIVE_TARGET_SID, LATEST_FILE_LOCK, socketio, SETTINGS_FILE, PRESETS_FILE
        main_app_instance = self

        # --- Adjuntar globales para pasarlos a las pestañas ---
        self.ACTIVE_TARGET_SID_accessor = lambda: ACTIVE_TARGET_SID # Usamos una función para obtener el valor *actual*
        self.LATEST_FILE_LOCK = LATEST_FILE_LOCK
        self.socketio = socketio
        self.SETTINGS_FILE = SETTINGS_FILE
        self.PRESETS_FILE = PRESETS_FILE

        self.launch_target = launch_target
        self.is_shutting_down = False
        self.cancellation_event = threading.Event()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.title("DowP")
        self.iconbitmap(resource_path("DowP-icon.ico"))
        win_width = 835
        win_height = 915
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
        self.cookies_path = ""
        self.cookies_mode_saved = "No usar"
        self.selected_browser_saved = "firefox"
        self.browser_profile_saved = ""
        self.auto_download_subtitle_saved = False
        self.ffmpeg_update_snooze_until = None
        self.custom_presets = []
        self.recode_settings = {}
        self.apply_quick_preset_checkbox_state = False
        self.keep_original_quick_saved = True
        
        # --- INTENTAR CARGAR CONFIGURACIÓN GUARDADA ---
        try:
            print(f"DEBUG: Intentando cargar configuración desde: {SETTINGS_FILE}")
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    # Sobrescribe los valores por defecto con los que están guardados
                    self.default_download_path = settings.get("default_download_path", self.default_download_path)
                    self.cookies_path = settings.get("cookies_path", self.cookies_path)
                    self.cookies_mode_saved = settings.get("cookies_mode", self.cookies_mode_saved)
                    self.selected_browser_saved = settings.get("selected_browser", self.selected_browser_saved)
                    self.browser_profile_saved = settings.get("browser_profile", self.browser_profile_saved)
                    self.auto_download_subtitle_saved = settings.get("auto_download_subtitle", self.auto_download_subtitle_saved)
                    snooze_str = settings.get("ffmpeg_update_snooze_until")
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
        
        # Añadir la pestaña de Descarga Única
        # (Cargará la clase de nuestro nuevo archivo)
        self.tab_view.add("Descarga Única")
        self.single_tab = SingleDownloadTab(master=self.tab_view.tab("Descarga Única"), app=self)
        
        # Añadir la pestaña de Lotes (como placeholder)
        self.tab_view.add("Descarga por Lotes")
        self.batch_tab = BatchDownloadTab(master=self.tab_view.tab("Descarga por Lotes"), app=self)

        self.run_initial_setup()
        self._check_for_ui_requests()
    
    def run_initial_setup(self):
        """
        Inicia la aplicación, configura la UI y lanza una comprobación de
        FFmpeg en segundo plano.
        """
        print("INFO: Configurando UI y lanzando comprobación de FFmpeg en segundo plano...")

        from src.core.setup import check_app_update
        threading.Thread(
            target=lambda: self.on_update_check_complete(check_app_update(self.single_tab.APP_VERSION)), # CORREGIDO
            daemon=True
        ).start()

        from src.core.setup import check_environment_status
        threading.Thread(
            target=lambda: self.on_status_check_complete(check_environment_status(lambda text, val: None)), # CORREGIDO
            daemon=True
        ).start()

        self.ffmpeg_processor.run_detection_async(self.on_ffmpeg_detection_complete) # CORREGIDO

    def on_update_check_complete(self, update_info):
        """Callback que se ejecuta cuando la comprobación de versión termina."""
        if update_info.get("update_available"):
            latest_version = update_info.get("latest_version")
            self.single_tab.release_page_url = update_info.get("release_url") # CORREGIDO
            
            is_prerelease = update_info.get("is_prerelease", False)
            if is_prerelease:
                status_text = f"¡Nueva Pre-release {latest_version} disponible!"
            else:
                status_text = f"¡Nueva versión {latest_version} disponible!"
            
            self.single_tab.app_status_label.configure(text=status_text, text_color="#52a2f2") # CORREGIDO
            
            self.single_tab.update_app_button.configure(text=f"Descargar v{latest_version}", state="normal", fg_color=self.single_tab.DOWNLOAD_BTN_COLOR) # CORREGIDO

        elif "error" in update_info:
            self.single_tab.app_status_label.configure(text=f"DowP v{self.single_tab.APP_VERSION} - Error al verificar", text_color="orange") # CORREGIDO
            self.single_tab.update_app_button.configure(text="Reintentar", state="normal", fg_color="gray") # CORREGIDO

        else: 
            self.single_tab.app_status_label.configure(text=f"DowP v{self.single_tab.APP_VERSION} - Estás al día ✅") # CORREGIDO
            self.single_tab.update_app_button.configure(text="Sin actualizaciones", state="disabled") # CORREGIDO


    def on_status_check_complete(self, status_info, force_check=False):
        """
        Callback FINAL que gestiona el estado de FFmpeg.
        """
        status = status_info.get("status")
        
        self.single_tab.update_ffmpeg_button.configure(state="normal", text="Buscar Actualizaciones de FFmpeg") # CORREGIDO

        if status == "error":
            messagebox.showerror("Error Crítico de Entorno", status_info.get("message"))
            return

        local_version = status_info.get("local_version") or "No encontrado"
        latest_version = status_info.get("latest_version")
        download_url = status_info.get("download_url")
        ffmpeg_exists = status_info.get("ffmpeg_path_exists")
        
        should_download = False
        
        if not ffmpeg_exists:
            print("INFO: FFmpeg no encontrado. Iniciando descarga automática.")
            self.single_tab.update_progress(0, "FFmpeg no encontrado. Iniciando descarga automática...") # CORREGIDO
            should_download = True
        
        else:
            update_available = local_version != latest_version
            snoozed = self.ffmpeg_update_snooze_until and datetime.now() < self.ffmpeg_update_snooze_until
            
            if update_available and (not snoozed or force_check):
                user_response = messagebox.askyesno(
                    "Actualización Disponible",
                    f"Hay una nueva versión de FFmpeg disponible.\n\n"
                    f"Versión Actual: {local_version}\n"
                    f"Versión Nueva: {latest_version}\n\n"
                    "¿Deseas actualizar ahora?"
                )
                self.lift() # CORREGIDO
                if user_response:
                    should_download = True
                    self.ffmpeg_update_snooze_until = None 
                else:
                    self.ffmpeg_update_snooze_until = datetime.now() + timedelta(days=15)
                    self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualización pospuesta)") # CORREGIDO
                self.single_tab.save_settings() # CORREGIDO
                
            elif update_available and snoozed:
                print(f"DEBUG: Actualización de FFmpeg omitida. Snooze activo hasta {self.ffmpeg_update_snooze_until}.")
                self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualización pospuesta)") # CORREGIDO
            else:
                self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualizado)") # CORREGIDO

        if should_download:
            if not download_url:
                messagebox.showerror("Error", "No se pudo obtener la URL de descarga para FFmpeg.")
                return

            self.single_tab.update_progress(0, f"Iniciando descarga de FFmpeg {latest_version}...") # CORREGIDO
            from src.core.setup import download_and_install_ffmpeg
            
            def download_task():
                success = download_and_install_ffmpeg(latest_version, download_url, self.single_tab._handle_download_progress) # CORREGIDO
                if success:
                    self.after(0, self.ffmpeg_processor.run_detection_async,  # CORREGIDO
                            lambda s, m: self.on_ffmpeg_detection_complete(s, m, show_ready_message=True))
                    self.after(0, lambda: self.single_tab.ffmpeg_status_label.configure(text=f"FFmpeg: {latest_version} \n(Instalado)")) # CORREGIDO
                else:
                    self.after(0, self.single_tab.update_progress, 0, "Falló la descarga de FFmpeg.") # CORREGIDO

            threading.Thread(target=download_task, daemon=True).start()

    def on_ffmpeg_detection_complete(self, success, message, show_ready_message=False):
        if success:
            self.single_tab.recode_video_checkbox.configure(text="Recodificar Video", state="normal") # CORREGIDO
            self.single_tab.recode_audio_checkbox.configure(text="Recodificar Audio", state="normal") # CORREGIDO
            
            self.single_tab.apply_quick_preset_checkbox.configure(text="Activar recodificación Rápida", state="normal") # CORREGIDO
            
            if self.ffmpeg_processor.gpu_vendor:
                self.single_tab.gpu_radio.configure(text="GPU", state="normal") # CORREGIDO
                self.single_tab.cpu_radio.pack_forget() # CORREGIDO
                self.single_tab.gpu_radio.pack_forget() # CORREGIDO
                self.single_tab.gpu_radio.pack(side="left", padx=10) # CORREGIDO
                self.single_tab.cpu_radio.pack(side="left", padx=20) # CORREGIDO
            else:
                self.single_tab.gpu_radio.configure(text="GPU (No detectada)") # CORREGIDO
                self.single_tab.proc_type_var.set("CPU") # CORREGIDO
                self.single_tab.gpu_radio.configure(state="disabled") # CORREGIDO
            
            self.single_tab.update_codec_menu() # CORREGIDO
            
            if show_ready_message:
                self.single_tab.update_progress(100, "✅ FFmpeg instalado correctamente. Listo para usar.") # CORREGIDO
        else:
            print(f"FFmpeg detection error: {message}")
            self.single_tab.recode_video_checkbox.configure(text="Recodificación no disponible", state="disabled") # CORREGIDO
            self.single_tab.recode_audio_checkbox.configure(text="(Error FFmpeg)", state="disabled") # CORREGIDO
            
            self.single_tab.apply_quick_preset_checkbox.configure(text="Recodificación no disponible (Error FFmpeg)", state="disabled") # CORREGIDO
            self.single_tab.apply_quick_preset_checkbox.deselect() # CORREGIDO

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
                details = self.ui_request_data.get("details", "Detalles no disponibles.") # CORREGIDO
                dialog = CompromiseDialog(self, details)
                self.wait_window(dialog) # CORREGIDO
                self.lift() # CORREGIDO
                self.focus_force() # CORREGIDO
                self.ui_response_data["result"] = dialog.result # CORREGIDO
                self.ui_response_event.set() # CORREGIDO
                
        self.after(100, self._check_for_ui_requests) # CORREGIDO

    def on_closing(self):
        """
        Se ejecuta cuando el usuario intenta cerrar la ventana.
        Gestiona la cancelación, limpieza y confirmación de forma robusta.
        """
        # CORREGIDO: (Ahora apunta a self.single_tab.active_operation_thread)
        if self.single_tab.active_operation_thread and self.single_tab.active_operation_thread.is_alive():
            if messagebox.askokcancel("Confirmar Salida", "Hay una operación en curso. ¿Estás seguro de que quieres salir?"):
                self.is_shutting_down = True # CORREGIDO: (self, no self.app)
                self.attributes("-disabled", True)
                # CORREGIDO: (Apunta a self.single_tab.progress_label)
                self.single_tab.progress_label.configure(text="Cancelando y limpiando, por favor espera...")
                self.cancellation_event.set()
                # CORREGIDO: (self.after, no self.app.after)
                self.after(100, self._wait_for_thread_to_finish_and_destroy)
        else:
            # CORREGIDO: (La función save_settings() vive en la pestaña)
            self.single_tab.save_settings()
            self.destroy()

    def _wait_for_thread_to_finish_and_destroy(self):
        """
        Vigilante que comprueba si el hilo de trabajo ha terminado.
        Una vez que termina (después de su limpieza), cierra la ventana.
        """
        # CORREGIDO: (Apunta a self.single_tab.active_operation_thread)
        if self.single_tab.active_operation_thread and self.single_tab.active_operation_thread.is_alive():
            # CORREGIDO: (self.after, no self.app.after)
            self.after(100, self._wait_for_thread_to_finish_and_destroy)
        else:
            # CORREGIDO: (La función save_settings() vive en la pestaña)
            self.single_tab.save_settings()
            self.destroy()