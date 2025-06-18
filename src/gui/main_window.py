# src/gui/main_window.py

import customtkinter as ctk
from customtkinter import filedialog
from PIL import Image
import requests
from io import BytesIO
import threading
import os
import re
from pathlib import Path
import subprocess
import json
import time

from src.core.downloader import get_video_info, download_media
from src.core.processor import FFmpegProcessor, CODEC_PROFILES

# Constante para el archivo de configuración
SETTINGS_FILE = "app_settings.json"

# Excepción personalizada para manejar cancelaciones de usuario
class UserCancelledError(Exception):
    """Excepción lanzada cuando el usuario cancela una operación."""
    pass

class MainWindow(ctk.CTk):
    # Criterios para considerar un formato "lento" para recodificar
    SLOW_FORMAT_CRITERIA = {
        "video_codecs": ["av01", "vp9", "hevc"], # Códecs que pueden ser más demandantes para decodificar/recodificar
        "min_height_for_slow": 2160,             # 4K y superior
        "min_fps_for_slow": 50                   # Alta tasa de frames (ej. 1080p60, 4K60)
    }

    # Criterios para considerar un formato "compatible" con editores de video
    EDITOR_FRIENDLY_CRITERIA = {
        # yt-dlp/FFmpeg códecs de video comúnmente compatibles
        "compatible_vcodecs": ["avc1", "h264", "prores", "dnxhd", "cfhd"],
        # Extensiones/contenedores comúnmente compatibles
        "compatible_exts": ["mp4", "mov"],
    }

    def __init__(self):
        super().__init__()
        self.title("Descargador de Medios")
        self.geometry("800x800")
        self.minsize(720, 650)
        ctk.set_appearance_mode("Dark")

        # Atributos de datos (variables de estado)
        self.video_formats = {}
        self.audio_formats = {}
        self.thumbnail_label = None
        self.pil_image = None
        self.last_download_path = None
        self.video_duration = 0

        # Atributos para el control de cancelación
        self.active_subprocess_pid = None # PID del subproceso actualmente activo (análisis, descarga, recodificación)
        self.cancellation_event = threading.Event() # Evento para señalar cancelación entre hilos

        # Guardar el estado original de los botones para restablecerlos
        self.original_analyze_text = "Analizar"
        self.original_analyze_command = self.start_analysis_thread
        self.original_analyze_fg_color = None # Se establecerá en create_widgets

        self.original_download_text = "Iniciar Descarga"
        self.original_download_command = self.start_download_thread
        self.original_download_fg_color = None # Se establecerá en create_widgets


        # Variables de configuración que se guardarán/cargarán
        self.default_download_path = ""
        self.cookies_path = "" # Ruta al archivo cookies.txt
        self.cookies_mode_saved = "No usar" # "No usar", "Archivo Manual...", "chrome", etc.
        self.selected_browser_saved = "chrome" # Navegador seleccionado
        self.browser_profile_saved = "" # Perfil del navegador

        # Cargar configuraciones al inicio de la aplicación
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_file_path = os.path.join(script_dir, SETTINGS_FILE)

        try:
            print(f"DEBUG: Intentando cargar configuración desde: {settings_file_path}")
            if os.path.exists(settings_file_path):
                with open(settings_file_path, 'r') as f:
                    settings = json.load(f)
                    self.default_download_path = settings.get("default_download_path", "")
                    self.cookies_path = settings.get("cookies_path", "")
                    self.cookies_mode_saved = settings.get("cookies_mode", "No usar")
                    self.selected_browser_saved = settings.get("selected_browser", "chrome")
                    self.browser_profile_saved = settings.get("browser_profile", "")
                print(f"DEBUG: Configuración cargada exitosamente. Ruta de descarga: '{self.default_download_path}'")
            else:
                print("DEBUG: Archivo de configuración no encontrado. Usando valores por defecto.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: Fallo al cargar configuración: {e}")
            pass

        # Instancia del procesador de FFmpeg
        self.ffmpeg_processor = FFmpegProcessor()

        # Crear la interfaz
        self.create_widgets()

        # Asegurarse de que los valores iniciales de los widgets reflejen la configuración cargada
        self.output_path_entry.insert(0, self.default_download_path)
        self.cookie_mode_menu.set(self.cookies_mode_saved)
        if self.cookies_path:
            self.cookie_path_entry.insert(0, self.cookies_path)
        self.browser_var.set(self.selected_browser_saved)
        self.browser_profile_entry.insert(0, self.browser_profile_saved)
        self.on_cookie_mode_change(self.cookies_mode_saved)

        # Iniciar la detección de FFmpeg DESPUÉS de que toda la UI esté creada
        self.ffmpeg_processor.run_detection_async(self.on_ffmpeg_detection_complete)


    def create_widgets(self):
        # Frame de URL
        url_frame = ctk.CTkFrame(self)
        url_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(url_frame, text="URL del Video:").pack(side="left", padx=(10, 5))
        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="Pega la URL aquí...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=5)
        # Asignar comando y texto originales al botón de analizar
        self.analyze_button = ctk.CTkButton(url_frame, text=self.original_analyze_text, command=self.original_analyze_command)
        self.analyze_button.pack(side="left", padx=(5, 10))
        # Guardar el color original del botón de analizar
        self.original_analyze_fg_color = self.analyze_button.cget("fg_color")

        # Frame principal de información
        info_frame = ctk.CTkFrame(self)
        info_frame.pack(pady=10, padx=10, fill="both", expand=True)

        # Panel Izquierdo
        left_panel_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        left_panel_frame.pack(side="left", padx=10, pady=10, anchor="n")
        self.thumbnail_container = ctk.CTkFrame(left_panel_frame, width=320, height=180)
        self.thumbnail_container.pack()
        self.thumbnail_container.pack_propagate(False)
        self.create_placeholder_label()
        actions_frame = ctk.CTkFrame(left_panel_frame)
        actions_frame.pack(fill="x", pady=(10,0))
        self.save_thumbnail_button = ctk.CTkButton(actions_frame, text="Descargar Miniatura...", state="disabled", command=self.save_thumbnail)
        self.save_thumbnail_button.pack(fill="x", padx=10, pady=5)
        self.auto_save_thumbnail_check = ctk.CTkCheckBox(actions_frame, text="Descargar miniatura con el video", command=self.toggle_manual_thumbnail_button)
        self.auto_save_thumbnail_check.pack(padx=10, pady=5, anchor="w")
        ctk.CTkLabel(actions_frame, text="Usar Cookies:", font=ctk.CTkFont(size=12)).pack(padx=10, pady=(10,0), anchor="w")

        # Opciones de Cookies
        self.cookie_mode_menu = ctk.CTkOptionMenu(actions_frame, values=["No usar", "Archivo Manual...", "chrome", "firefox", "edge", "opera", "vivaldi", "brave"], command=self.on_cookie_mode_change)
        self.cookie_mode_menu.pack(fill="x", padx=10, pady=(0, 5))

        self.manual_cookie_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        self.cookie_path_entry = ctk.CTkEntry(self.manual_cookie_frame, placeholder_text="Ruta al archivo cookies.txt...")
        self.cookie_path_entry.pack(fill="x")
        self.cookie_path_entry.bind("<KeyRelease>", lambda event: self.save_settings())
        self.select_cookie_file_button = ctk.CTkButton(self.manual_cookie_frame, text="Elegir Archivo...", command=lambda: self.select_cookie_file())
        self.select_cookie_file_button.pack(fill="x", pady=(5,0))

        # Widgets para modo "Desde Navegador"
        self.browser_options_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        ctk.CTkLabel(self.browser_options_frame, text="Navegador:").pack(padx=10, pady=(5,0), anchor="w")
        self.browser_var = ctk.StringVar(value=self.selected_browser_saved)
        self.browser_menu = ctk.CTkOptionMenu(self.browser_options_frame, values=["chrome", "firefox", "edge", "opera", "vivaldi", "brave"], variable=self.browser_var, command=self.save_settings)
        self.browser_menu.pack(fill="x", padx=10)

        ctk.CTkLabel(self.browser_options_frame, text="Perfil (Opcional):").pack(padx=10, pady=(5,0), anchor="w")
        self.browser_profile_entry = ctk.CTkEntry(self.browser_options_frame, placeholder_text="Ej: Default, Profile 1")
        self.browser_profile_entry.pack(fill="x", padx=10)
        self.browser_profile_entry.bind("<KeyRelease>", lambda event: self.save_settings())


        # Panel Derecho
        details_frame = ctk.CTkFrame(info_frame)
        details_frame.pack(side="left", fill="both", expand=True, padx=(0,10), pady=10)
        ctk.CTkLabel(details_frame, text="Título:", anchor="w").pack(fill="x", padx=5, pady=(5,0))
        self.title_entry = ctk.CTkEntry(details_frame, font=("", 14))
        self.title_entry.pack(fill="x", padx=5, pady=(0,10))

        options_frame = ctk.CTkFrame(details_frame)
        options_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(options_frame, text="Modo:").pack(side="left", padx=(0, 10))
        self.mode_selector = ctk.CTkSegmentedButton(options_frame, values=["Video+Audio", "Solo Audio"], command=self.on_mode_change)
        self.mode_selector.set("Video+Audio")
        self.mode_selector.pack(side="left", expand=True, fill="x")

        self.video_quality_label = ctk.CTkLabel(details_frame, text="Calidad de Video:", anchor="w")
        self.video_quality_menu = ctk.CTkOptionMenu(details_frame, state="disabled", values=["-"], command=self.on_video_quality_change)
        self.audio_quality_label = ctk.CTkLabel(details_frame, text="Calidad de Audio:", anchor="w")
        self.audio_quality_menu = ctk.CTkOptionMenu(details_frame, state="disabled", values=["-"])

        self.slow_format_warning_label = ctk.CTkLabel(details_frame, text="Este formato puede recodificarse lentamente.", text_color="orange", font=ctk.CTkFont(size=12, weight="bold"))
        self.slow_format_warning_label.pack(fill="x", padx=5, pady=(0,5))
        self.slow_format_warning_label.pack_forget()

        self.editor_warning_label = ctk.CTkLabel(details_frame, text="Este formato puede requerir recodificación o proxies para edición fluida.", text_color="red", font=ctk.CTkFont(size=12, weight="bold"))
        self.editor_warning_label.pack(fill="x", padx=5, pady=(0,5))
        self.editor_warning_label.pack_forget()

        recode_main_frame = ctk.CTkFrame(self)
        recode_main_frame.pack(pady=(0, 10), padx=10, fill="x")

        ctk.CTkLabel(recode_main_frame, text="Opciones de Recodificación", font=ctk.CTkFont(weight="bold")).pack(pady=(5,10))
        self.recode_checkbox = ctk.CTkCheckBox(recode_main_frame, text="Activar Recodificación", command=self.toggle_recode_panel, state="disabled")
        self.recode_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

        self.recode_options_frame = ctk.CTkFrame(recode_main_frame)

        self.proc_type_var = ctk.StringVar(value="CPU")
        proc_frame = ctk.CTkFrame(self.recode_options_frame, fg_color="transparent")
        proc_frame.pack(fill="x", padx=10, pady=5)
        self.cpu_radio = ctk.CTkRadioButton(proc_frame, text="CPU", variable=self.proc_type_var, value="CPU", command=self.update_codec_menu)
        self.cpu_radio.pack(side="left", padx=10)
        self.gpu_radio = ctk.CTkRadioButton(proc_frame, text="GPU (Detectando...)", variable=self.proc_type_var, value="GPU", state="disabled", command=self.update_codec_menu)
        self.gpu_radio.pack(side="left", padx=20)

        codec_options_frame = ctk.CTkFrame(self.recode_options_frame)
        codec_options_frame.pack(fill="x", padx=10, pady=5)
        codec_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(codec_options_frame, text="Codec:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.recode_codec_menu = ctk.CTkOptionMenu(codec_options_frame, values=["-"], state="disabled", command=self.update_profile_menu)
        self.recode_codec_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(codec_options_frame, text="Perfil/Calidad:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.recode_profile_menu = ctk.CTkOptionMenu(codec_options_frame, values=["-"], state="disabled")
        self.recode_profile_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        container_frame = ctk.CTkFrame(self.recode_options_frame, fg_color="transparent")
        container_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(container_frame, text="Contenedor:").pack(side="left")
        self.recode_container_label = ctk.CTkLabel(container_frame, text="-", font=ctk.CTkFont(weight="bold"))
        self.recode_container_label.pack(side="left", padx=5)

        download_frame = ctk.CTkFrame(self)
        download_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(download_frame, text="Carpeta de Salida:").pack(side="left", padx=(10, 5))
        self.output_path_entry = ctk.CTkEntry(download_frame, placeholder_text="Selecciona una carpeta...")
        self.output_path_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.select_folder_button = ctk.CTkButton(download_frame, text="...", width=40, command=lambda: self.select_output_folder())
        self.select_folder_button.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(download_frame, text="Límite (MB/s):").pack(side="left", padx=(10, 5))
        self.speed_limit_entry = ctk.CTkEntry(download_frame, width=80)
        self.speed_limit_entry.pack(side="left", padx=(0, 10))
        # Asignar comando y texto originales al botón de descarga
        self.download_button = ctk.CTkButton(download_frame, text=self.original_download_text, state="disabled", command=self.original_download_command)
        self.download_button.pack(side="left", padx=(5, 10))
        # Guardar el color original del botón de descarga
        self.original_download_fg_color = self.download_button.cget("fg_color")

        # El pre-llenado de la ruta se hace en __init__ después de cargar settings.
        if not self.default_download_path:
            try:
                downloads_path = Path.home() / "Downloads"
                if downloads_path.exists() and downloads_path.is_dir():
                    self.output_path_entry.insert(0, str(downloads_path))
            except Exception as e:
                print(f"No se pudo establecer la carpeta de descargas por defecto: {e}")

        progress_frame = ctk.CTkFrame(self)
        progress_frame.pack(pady=(0, 10), padx=10, fill="x")
        self.progress_label = ctk.CTkLabel(progress_frame, text="Esperando...")
        self.progress_label.pack(pady=(5,0))
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0,5), padx=10, fill="x")
        help_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        help_frame.pack(fill="x", padx=10, pady=(0, 5))
        speed_help_label = ctk.CTkLabel(help_frame, text="Límite: Dejar vacío para velocidad máxima.", font=ctk.CTkFont(size=11), text_color="gray")
        speed_help_label.pack(side="left")
        error_help_label = ctk.CTkLabel(help_frame, text="Consejo: Si una descarga falla, pruebe a limitar la velocidad (ej: 2).", font=ctk.CTkFont(size=11), text_color="gray")
        error_help_label.pack(side="right")

        self.on_mode_change(self.mode_selector.get())

    def save_settings(self, event=None):
        """ Guarda la configuración actual de la aplicación en un archivo JSON. """
        settings_to_save = {
            "default_download_path": self.default_download_path,
            "cookies_path": self.cookies_path,
            "cookies_mode": self.cookie_mode_menu.get(),
            "selected_browser": self.browser_var.get(),
            "browser_profile": self.browser_profile_entry.get()
        }
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_file_path = os.path.join(script_dir, SETTINGS_FILE)

        print(f"DEBUG: Intentando guardar configuración en: {settings_file_path}")
        print(f"DEBUG: Guardando default_download_path: '{self.default_download_path}'")
        try:
            with open(settings_file_path, 'w') as f:
                json.dump(settings_to_save, f, indent=4)
            print("DEBUG: Configuración guardada exitosamente.")
        except IOError as e:
            print(f"ERROR: Fallo al guardar configuración: {e}")

    def on_ffmpeg_detection_complete(self, success, message):
        """Callback que se ejecuta cuando FFmpegProcessor termina."""
        if success:
            if self.ffmpeg_processor.gpu_vendor:
                self.gpu_radio.configure(text=f"GPU ({self.ffmpeg_processor.gpu_vendor})", state="normal")
                self.cpu_radio.pack_forget()
                self.gpu_radio.pack_forget()
                self.gpu_radio.pack(side="left", padx=10)
                self.cpu_radio.pack(side="left", padx=20)
            else:
                self.gpu_radio.configure(text="GPU (No detectada)")
                self.proc_type_var.set("CPU")
                self.gpu_radio.configure(state="disabled")

            self.recode_checkbox.configure(state="normal")
            self.update_codec_menu()
        else:
            print(f"FFmpeg detection error: {message}")
            self.recode_checkbox.configure(text="Recodificación no disponible (Error FFmpeg)", state="disabled")

    def toggle_recode_panel(self):
        """Muestra u oculta el panel de opciones de recodificación."""
        is_checked = self.recode_checkbox.get() == 1
        is_audio_only = self.mode_selector.get() == "Solo Audio"

        if is_checked:
            if is_audio_only:
                self.proc_type_var.set("CPU")
                self.cpu_radio.configure(state="normal")
                self.gpu_radio.configure(state="disabled")
            else:
                self.cpu_radio.configure(state="normal")
                if self.ffmpeg_processor.gpu_vendor:
                    self.gpu_radio.configure(state="normal")

            self.recode_options_frame.pack(fill="x", padx=5, pady=5)
            self.update_codec_menu()
        else:
            self.recode_options_frame.pack_forget()

    def update_codec_menu(self, *args):
        proc_type = self.proc_type_var.get()
        mode = self.mode_selector.get()

        codecs = ["-"]
        is_recode_panel_visible = self.recode_options_frame.winfo_ismapped()

        if self.ffmpeg_processor.is_detection_complete and is_recode_panel_visible:
            category = "Audio" if mode == "Solo Audio" else "Video"
            effective_proc = "CPU" if category == "Audio" else proc_type

            available = self.ffmpeg_processor.available_encoders.get(effective_proc, {}).get(category, {})
            if available:
                codecs = list(available.keys())

        self.recode_codec_menu.configure(values=codecs, state="normal" if codecs and codecs[0] != "-" else "disabled")
        if codecs:
            self.recode_codec_menu.set(codecs[0])
            self.update_profile_menu(codecs[0])
        else:
            self.update_profile_menu("-")

    def update_profile_menu(self, selected_codec_name):
        proc_type = self.proc_type_var.get()
        mode = self.mode_selector.get()

        profiles = ["-"]
        container = "-"

        if selected_codec_name != "-":
            category = "Audio" if mode == "Solo Audio" else "Video"
            effective_proc = "CPU" if category == "Audio" else proc_type

            available_codecs = self.ffmpeg_processor.available_encoders.get(effective_proc, {}).get(category, {})
            if selected_codec_name in available_codecs:
                codec_data = available_codecs[selected_codec_name]
                ffmpeg_codec_name = list(codec_data.keys())[0]
                container = codec_data.get("container", "-")

                profile_data = codec_data.get(ffmpeg_codec_name, {})
                if profile_data:
                    profiles = list(profile_data.keys())

        self.recode_profile_menu.configure(values=profiles, state="normal" if profiles and profiles[0] != "-" else "disabled")
        self.recode_profile_menu.set(profiles[0] if profiles else "-")
        self.recode_container_label.configure(text=container)

    def on_mode_change(self, mode):
        self.video_quality_label.pack_forget()
        self.video_quality_menu.pack_forget()
        self.audio_quality_label.pack_forget()
        self.audio_quality_menu.pack_forget()
        self.slow_format_warning_label.pack_forget()
        self.editor_warning_label.pack_forget()

        if mode == "Video+Audio":
            self.video_quality_label.pack(fill="x", padx=5, pady=(10,0))
            self.video_quality_menu.pack(fill="x", padx=5, pady=(0,5))
            self.audio_quality_label.pack(fill="x", padx=5, pady=(10,0))
            self.audio_quality_menu.pack(fill="x", padx=5, pady=(0,5))
            self.on_video_quality_change(self.video_quality_menu.get())
        elif mode == "Solo Audio":
            self.audio_quality_label.pack(fill="x", padx=5, pady=(10,0))
            self.audio_quality_menu.pack(fill="x", padx=5, pady=(0,5))

        self.toggle_recode_panel()
        self.update_codec_menu()

    def on_video_quality_change(self, selected_label):
        """Muestra u oculta los avisos de formato (lento y compatibilidad) según la selección."""
        if "Potencialmente Lento para Recodificar" in selected_label:
            self.slow_format_warning_label.pack(fill="x", padx=5, pady=(0,5))
        else:
            self.slow_format_warning_label.pack_forget()

        clean_label = selected_label.replace(" (Potencialmente Lento para Recodificar)", "").replace(" (Ideal para Edición)", "").replace(" (Puede requerir Recodificación para Edición)", "")
        selected_format_info = self.video_formats.get(clean_label)

        if selected_format_info:
            if not self._is_format_editor_friendly(selected_format_info):
                self.editor_warning_label.pack(fill="x", padx=5, pady=(0,5))
            else:
                self.editor_warning_label.pack_forget()
        else:
            self.editor_warning_label.pack_forget()

    def _is_format_editor_friendly(self, format_dict):
        """
        Determina si un formato de video es considerado 'amigable para edición'.
        """
        vcodec = format_dict.get('vcodec', '').split('.')[0]
        ext = format_dict.get('ext', '')

        if vcodec in self.EDITOR_FRIENDLY_CRITERIA["compatible_vcodecs"] and \
           ext in self.EDITOR_FRIENDLY_CRITERIA["compatible_exts"]:
            return True
        return False

    def sanitize_filename(self, filename): return re.sub(r'[\\/:\*\?"<>|]', '', filename)
    def create_placeholder_label(self, text="Miniatura"):
        if self.thumbnail_label: self.thumbnail_label.destroy()
        self.thumbnail_label = ctk.CTkLabel(self.thumbnail_container, text=text)
        self.thumbnail_label.pack(expand=True, fill="both")
        self.pil_image = None
        if hasattr(self, 'save_thumbnail_button'): self.save_thumbnail_button.configure(state="disabled")
        if hasattr(self, 'auto_save_thumbnail_check'): self.auto_save_thumbnail_check.deselect()

    def on_cookie_mode_change(self, mode):
        """Muestra u oculta las opciones de cookies según el modo seleccionado."""
        if mode == "Archivo Manual...":
            self.manual_cookie_frame.pack(fill="x", padx=10, pady=(0, 10))
            self.browser_options_frame.pack_forget()
        elif mode != "No usar":
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack(fill="x", padx=10, pady=(0, 10))
            self.browser_var.set(mode)
        else:
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack_forget()
        self.save_settings()

    def toggle_manual_thumbnail_button(self):
        is_checked = self.auto_save_thumbnail_check.get() == 1
        has_image = self.pil_image is not None
        if is_checked or not has_image: self.save_thumbnail_button.configure(state="disabled")
        else: self.save_thumbnail_button.configure(state="normal")

    def select_output_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, folder_path)
            self.default_download_path = folder_path
            self.save_settings()

    def select_cookie_file(self):
        filepath = filedialog.askopenfilename(title="Selecciona tu archivo cookies.txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filepath:
            self.cookie_path_entry.delete(0, 'end')
            self.cookie_path_entry.insert(0, filepath)
            self.cookies_path = filepath
            self.save_settings()

    def save_thumbnail(self):
        if not self.pil_image: return
        clean_title = self.sanitize_filename(self.title_entry.get() or "miniatura")
        save_path = filedialog.asksaveasfilename(defaultextension=".jpg", filetypes=[("JPEG Image", "*.jpg"), ("PNG Image", "*.png")], initialfile=f"{clean_title}.jpg")
        if save_path:
            try:
                if save_path.lower().endswith((".jpg", ".jpeg")): self.pil_image.convert("RGB").save(save_path, quality=95)
                else: self.pil_image.save(save_path)
                self.update_progress(100, f"Miniatura guardada en {os.path.basename(save_path)}")
            except Exception as e: self.update_progress(0, f"Error al guardar miniatura: {e}")

    # Nuevo método para manejar la cancelación de operaciones.
    def cancel_operation(self):
        print("DEBUG: Botón de Cancelar presionado.")
        self.cancellation_event.set() # Establecer la bandera de cancelación

        # Intentar terminar el subproceso activo si existe
        if self.active_subprocess_pid:
            try:
                os.kill(self.active_subprocess_pid, 9) # Envía SIGKILL (terminación forzosa)
                print(f"DEBUG: Proceso con PID {self.active_subprocess_pid} terminado.")
            except OSError as e:
                print(f"ERROR: No se pudo terminar el proceso {self.active_subprocess_pid}: {e}")
            self.active_subprocess_pid = None # Limpiar el PID

        # Restablecer los botones inmediatamente
        self._reset_buttons_to_original_state() # Esto se encarga de restablecer ambos botones

        self.update_progress(0, "Operación cancelada por el usuario.")
        self.title_entry.delete(0, 'end')
        self.title_entry.insert(0, "Análisis/Descarga cancelada.")


    def start_download_thread(self):
        url = self.url_entry.get()
        output_path = self.output_path_entry.get()
        if not url or not output_path:
            self.progress_label.configure(text="Error: Faltan la URL o la carpeta de salida.")
            return

        # Cambiar el botón de "Iniciar Descarga" a "Cancelar"
        self.download_button.configure(text="Cancelar", fg_color="red", command=self.cancel_operation)
        self.analyze_button.configure(state="disabled") # Desactivar botón de analizar durante la descarga

        self.cancellation_event.clear() # Limpiar cualquier señal de cancelación previa
        self.progress_bar.set(0)
        self.update_progress(0, "Preparando descarga...")

        options = {
            "url": url, "output_path": output_path,
            "title": self.title_entry.get() or "video_descargado",
            "mode": self.mode_selector.get(),
            "video_format_label": self.video_quality_menu.get(),
            "audio_format_label": self.audio_quality_menu.get(),
            "recode_enabled": self.recode_checkbox.get() == 1,
            "recode_proc": self.proc_type_var.get(),
            "recode_codec_name": self.recode_codec_menu.get(),
            "recode_profile_name": self.recode_profile_menu.get(),
            "recode_container": self.recode_container_label.cget("text"),
            "speed_limit": self.speed_limit_entry.get(),
            "cookie_mode": self.cookie_mode_menu.get(),
            "cookie_path": self.cookie_path_entry.get(),
            "selected_browser": self.browser_var.get(),
            "browser_profile": self.browser_profile_entry.get(),
        }

        threading.Thread(target=self._execute_download_and_recode, args=(options,), daemon=True).start()

    def _execute_download_and_recode(self, options):
        downloaded_filepath = None
        try:
            self.after(0, self.update_progress, 0, "Iniciando descarga...")

            # --- SEÑAL DE CANCELACIÓN: Antes de iniciar operaciones largas ---
            if self.cancellation_event.is_set():
                raise UserCancelledError("Descarga cancelada por el usuario.")

            video_format_id = self.video_formats.get(options["video_format_label"], {}).get('format_id')
            audio_format_id = self.audio_formats.get(options["audio_format_label"], {}).get('format_id')

            format_selector = ""
            postprocessors = []
            mode = options["mode"]
            clean_title = self.sanitize_filename(options['title'])

            # Determine the suffix based on mode
            audio_suffix = " (Audio)" if mode == "Solo Audio" else ""

            if options["recode_enabled"]:
                temp_filename = f"{clean_title}_temp.%(ext)s"
                output_template = os.path.join(options["output_path"], temp_filename)
            else:
                # Use the new audio_suffix here
                final_filename = f"{clean_title}{audio_suffix}.%(ext)s"
                output_template = os.path.join(options["output_path"], final_filename)

            if mode == "Video+Audio":
                if video_format_id and audio_format_id:
                    format_selector = f"{video_format_id}+{audio_format_id}"
                else:
                    format_selector = video_format_id or audio_format_id

            elif mode == "Solo Audio":
                format_selector = audio_format_id
                if not options["recode_enabled"]:
                    postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
                else:
                    postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'})

            ydl_opts = {'format': format_selector, 'outtmpl': output_template,
                        'postprocessors': postprocessors, 'noplaylist': True}

            if options["speed_limit"]:
                try:
                    limit_bytes = float(options["speed_limit"]) * 1024 * 1024
                    ydl_opts['ratelimit'] = limit_bytes
                except ValueError:
                    print("Límite de velocidad no es un número válido. Ignorando.")

            cookie_mode = options["cookie_mode"]
            if cookie_mode == "Archivo Manual..." and options["cookie_path"]:
                ydl_opts['cookiefile'] = options["cookie_path"]
            elif cookie_mode != "No usar":
                browser_arg = options["selected_browser"]
                if options["browser_profile"]:
                    browser_arg += f":{options['browser_profile']}"
                ydl_opts['cookiesfrombrowser'] = (browser_arg,)

            # PASAR EL CANCELLATION_EVENT A download_media
            downloaded_filepath = download_media(options["url"], ydl_opts, self.update_progress, self.cancellation_event)

            if not downloaded_filepath:
                raise Exception("La descarga falló o no devolvió una ruta de archivo.")

            # --- SEÑAL DE CANCELACIÓN: Después de la descarga, antes de la recodificación ---
            if self.cancellation_event.is_set():
                raise UserCancelledError("Recodificación cancelada por el usuario.")

            # --- FASE 2: Recodificación con FFmpeg (si está habilitada) ---
            if options["recode_enabled"]:
                self.after(0, self.update_progress, 0, "Preparando recodificación...")

                category = "Audio" if mode == "Solo Audio" else "Video"
                proc = "CPU" if category == "Audio" else options["recode_proc"]

                codec_db = self.ffmpeg_processor.available_encoders[proc][category]
                codec_data = codec_db.get(options["recode_codec_name"])
                if not codec_data: raise Exception("Codec de recodificación no encontrado en la base de datos.")

                ffmpeg_codec_name = list(codec_data.keys())[0]
                profile_params = codec_data[ffmpeg_codec_name].get(options["recode_profile_name"])
                if not profile_params: raise Exception("Perfil de recodificación no válido.")

                final_container = options["recode_container"]
                # Include the audio_suffix for recoded files when in "Solo Audio" mode
                final_output_path = os.path.join(options["output_path"], f"{clean_title}{audio_suffix}{final_container}")

                recode_opts = {
                    "input_file": downloaded_filepath,
                    "output_file": final_output_path,
                    "duration": self.video_duration,
                    "ffmpeg_params": profile_params
                }

                if mode == "Video+Audio":
                    if "-c:a" not in profile_params:
                        recode_opts["ffmpeg_params"] += " -c:a copy"

                # PASAR EL CANCELLATION_EVENT A execute_recode
                final_path = self.ffmpeg_processor.execute_recode(recode_opts, self.update_progress, self.cancellation_event)

            else: # Si no había recodificación, el archivo descargado es el final.
                final_path = downloaded_filepath
                self.on_process_finished(True, "Descarga completada", downloaded_filepath)

        except UserCancelledError as e:
            self.on_process_finished(False, str(e), None)
            # Limpiar archivo temporal si la cancelación ocurre durante la descarga o justo antes de la recodificación
            if downloaded_filepath and os.path.exists(downloaded_filepath):
                try:
                    os.remove(downloaded_filepath)
                    print(f"DEBUG: Archivo temporal {downloaded_filepath} eliminado tras cancelación.")
                except OSError as cleanup_e:
                    print(f"ERROR: No se pudo eliminar el archivo temporal {downloaded_filepath} tras cancelación: {cleanup_e}")
        except Exception as e:
            self.on_process_finished(False, f"Error: {e}", None)
        finally:
            self.active_subprocess_pid = None
            self._reset_buttons_to_original_state()

    def _reset_buttons_to_original_state(self):
        """ Restablece los botones de analizar y descargar a su estado original (texto, comando y color). """
        self.analyze_button.configure(
            text=self.original_analyze_text,
            fg_color=self.original_analyze_fg_color,
            command=self.original_analyze_command,
            state="normal"
        )
        self.download_button.configure(
            text=self.original_download_text,
            fg_color=self.original_download_fg_color,
            command=self.original_download_command,
            state="normal"
        )


    def on_process_finished(self, success, message, filepath):
        """Callback unificado para el final del proceso. Se ejecuta en el hilo principal."""
        def _update_ui():
            self.last_download_path = filepath
            final_message = message

            if success and self.auto_save_thumbnail_check.get() == 1 and self.pil_image and self.last_download_path:
                try:
                    base_name = os.path.splitext(self.last_download_path)[0]
                    thumb_path = f"{base_name}.jpg"
                    self.pil_image.convert("RGB").save(thumb_path, quality=95)
                    final_message += " y miniatura guardada."
                except Exception as e:
                    print(f"No se pudo guardar la miniatura automáticamente: {e}")
                    final_message += " (falló guardado de miniatura)."

            self.progress_label.configure(text=final_message)
            self._reset_buttons_to_original_state()

            if success:
                self.progress_bar.set(1)
            else:
                self.progress_bar.set(0)

        self.after(0, _update_ui)

    def update_progress(self, percentage, message):
        """Actualiza la barra de progreso y el texto. Se llama desde cualquier hilo."""
        capped_percentage = max(0, min(percentage, 100))
        def _update():
            self.progress_bar.set(capped_percentage / 100)
            self.progress_label.configure(text=message)
        self.after(0, _update)

    def start_analysis_thread(self):
        url = self.url_entry.get()
        if not url: return

        # Cambiar el botón de "Analizar" a "Cancelar"
        self.analyze_button.configure(text="Cancelar", fg_color="red", command=self.cancel_operation)
        self.download_button.configure(state="disabled") # Desactivar botón de descarga durante el análisis

        self.cancellation_event.clear()
        self.create_placeholder_label("Analizando...")
        self.title_entry.delete(0, 'end') # Clear before inserting the new title
        self.title_entry.insert(0, "Analizando...") # Mostrar "Analizando..." en el título
        self.video_quality_menu.configure(state="disabled", values=["-"])
        self.audio_quality_menu.configure(state="disabled", values=["-"])
        self.slow_format_warning_label.pack_forget()
        self.editor_warning_label.pack_forget()

        threading.Thread(target=self._run_analysis_subprocess, args=(url,), daemon=True).start()


    def _run_analysis_subprocess(self, url):
        """
        Ejecuta yt-dlp como un subproceso con un timeout para analizar la URL,
        proporcionando feedback más granular al usuario.
        """
        try:
            self.after(0, self.update_progress, 0, "Analizando URL...")

            command = [
                'yt-dlp', '-j', url, '--no-warnings',
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                '--referer', url,
                '--no-playlist'
            ]

            cookie_mode = self.cookie_mode_menu.get()
            if cookie_mode == "Archivo Manual..." and self.cookie_path_entry.get():
                command.extend(['--cookies', self.cookie_path_entry.get()])
            elif cookie_mode != "No usar":
                browser_arg = self.browser_var.get()
                profile = self.browser_profile_entry.get()
                if profile:
                    browser_arg += f":{profile}"
                command.extend(['--cookies-from-browser', browser_arg])

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=creationflags
            )
            self.active_subprocess_pid = process.pid # Almacenar el PID del proceso

            json_output_lines = []
            info_received = False

            start_time = time.time()
            while True:
                # Comprobar cancelación por el usuario o timeout
                if self.cancellation_event.is_set():
                    print("DEBUG: Análisis detectó señal de cancelación. Terminando proceso.")
                    process.terminate()
                    raise UserCancelledError("Análisis cancelado por el usuario.")

                if time.time() - start_time > 45:
                    process.terminate()
                    raise subprocess.TimeoutExpired(cmd=command, timeout=45)

                line = process.stdout.readline() or process.stderr.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                    continue

                line_stripped = line.strip()
                if "[youtube]" in line_stripped or "[extractors]" in line_stripped:
                    self.after(0, self.update_progress, 0.1, "Estableciendo conexión y buscando extractores...")
                elif "[info]" in line_stripped:
                    self.after(0, self.update_progress, 0.3, "Extrayendo metadatos del video...")
                elif "[download]" in line_stripped:
                    self.after(0, self.update_progress, 0.5, "Procesando información de descarga...")

                if line_stripped.startswith('{') or line_stripped.startswith('['):
                    json_output_lines.append(line_stripped)
                    info_received = True
                elif info_received:
                    json_output_lines.append(line_stripped)

                self.after(0, self.update_progress, 0.05, f"Analizando... {line_stripped[:80]}...")

            stdout, stderr = process.communicate()
            full_stdout = "".join(json_output_lines) + stdout
            full_stderr = stderr

            if process.returncode != 0:
                error_output = full_stderr.strip() or "Error desconocido de yt-dlp."
                raise Exception(f"yt-dlp error: {error_output}")

            info = json.loads(full_stdout)

            if info.get('is_live', False) or (info.get('duration') in [None, 0] and info.get('live_status') in ['is_live', 'was_live', 'post_live']):
                self.after(0, self.on_analysis_complete, None, "AVISO: La URL apunta a una transmisión en vivo o a contenido no-video estándar. Las opciones de descarga podrían ser limitadas o no estar disponibles para un video VOD.")
                return

            self.after(0, self.on_analysis_complete, info)

        except subprocess.TimeoutExpired:
            self.after(0, self.on_analysis_complete, None, "ERROR: La operación de análisis de la URL ha excedido el tiempo límite (45s). Intenta de nuevo o verifica la URL.")
        except json.JSONDecodeError as e:
            self.after(0, self.on_analysis_complete, None, f"ERROR: yt-dlp no devolvió una respuesta JSON válida. ({e}). La salida fue: {full_stdout[:500]}...")
        except UserCancelledError:
            pass
        except Exception as e:
            self.after(0, self.on_analysis_complete, None, f"ERROR: Fallo al analizar la URL: {e}.")
        finally:
            self.active_subprocess_pid = None

    def on_analysis_complete(self, info, error_message=None):
        self.create_placeholder_label("Miniatura")
        self.title_entry.delete(0, 'end') # Clear before inserting the new title
        if info:
            self.title_entry.insert(0, info.get('title', 'Sin título'))
            self.video_duration = info.get('duration', 0)
            self.populate_format_menus(info)
            self.download_button.configure(state="normal")
            if thumbnail_url := info.get('thumbnail'):
                threading.Thread(target=self.load_thumbnail, args=(thumbnail_url,), daemon=True).start()
        else:
            self.title_entry.insert(0, error_message or "ERROR: No se pudo obtener la información.")
            self.create_placeholder_label("Fallo el análisis")

        self._reset_buttons_to_original_state()

    def load_thumbnail(self, url):
        try:
            self.after(0, self.create_placeholder_label, "Cargando miniatura...")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            img_data = response.content
            self.pil_image = Image.open(BytesIO(img_data))
            display_image = self.pil_image.copy()
            display_image.thumbnail((320, 180), Image.Resampling.LANCZOS)
            ctk_image = ctk.CTkImage(light_image=display_image, dark_image=display_image, size=display_image.size)

            def set_new_image():
                if self.thumbnail_label: self.thumbnail_label.destroy()
                self.thumbnail_label = ctk.CTkLabel(self.thumbnail_container, text="", image=ctk_image)
                self.thumbnail_label.pack(expand=True)
                self.thumbnail_label.image = ctk_image
                self.save_thumbnail_button.configure(state="normal")
                self.toggle_manual_thumbnail_button()

            self.after(0, set_new_image)
        except Exception as e:
            print(f"Error al cargar la miniatura: {e}")
            self.after(0, self.create_placeholder_label, "Error de miniatura")

    def populate_format_menus(self, info):
        formats = info.get('formats', [])
        video_entries, audio_entries = [], []

        for f in formats:
            filesize = f.get('filesize') or f.get('filesize_approx')
            size_mb = f"{filesize / (1024*1024):.2f} MB" if filesize else "Tamaño desc."
            ext = f.get('ext', 'N/A')

            if f.get('vcodec') != 'none':
                vcodec = f.get('vcodec', 'N/A').split('.')[0]
                acodec = f.get('acodec', 'none').split('.')[0]
                height = f.get('height', 0)
                fps = f.get('fps', 0)

                is_slow = False
                if vcodec in self.SLOW_FORMAT_CRITERIA["video_codecs"] and height >= self.SLOW_FORMAT_CRITERIA["min_height_for_slow"]:
                    is_slow = True
                elif height >= self.SLOW_FORMAT_CRITERIA["min_height_for_slow"] and fps >= self.SLOW_FORMAT_CRITERIA["min_fps_for_slow"]:
                     is_slow = True
                elif height >= 3840:
                    is_slow = True

                is_editor_friendly = self._is_format_editor_friendly(f)

                if acodec != 'none':
                    label = f"{f.get('height', 0)}p ({ext}, {vcodec}+{acodec}) - {size_mb}"
                else:
                    label = f"{f.get('height', 0)}p ({ext}, {vcodec}) - {size_mb}"

                if is_slow:
                    label += " (Potencialmente Lento para Recodificar)"

                if is_editor_friendly:
                    if not is_slow:
                        label += " (Ideal para Edición)"
                elif not is_editor_friendly and not is_slow:
                    label += " (Puede requerir Recodificación para Edición)"
                elif not is_editor_friendly and is_slow:
                    pass

                video_entries.append({'label': label, 'format': f, 'has_audio': acodec != 'none'})

            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                abr = f.get('abr')
                acodec = f.get('acodec', 'N/A').split('.')[0]
                if abr and abr > 0:
                    label = f"{abr:.0f}kbps ({acodec}, {ext}) - {size_mb}"
                else:
                    label = f"Audio ({acodec}, {ext}) - {size_mb}"
                audio_entries.append({'label': label, 'format': f})

        # Custom sort for video entries to put "Tamaño desc." at the end
        def sort_video_key(entry):
            if "Tamaño desc." in entry['label']:
                return (-1, entry['format'].get('height') or 0) # Sort by (is_size_unknown, height_or_0)
            return (0, entry['format'].get('height') or 0)

        # Custom sort for audio entries to put "Tamaño desc." at the end
        def sort_audio_key(entry):
            if "Tamaño desc." in entry['label']:
                return (-1, entry['format'].get('abr') or 0) # Sort by (is_size_unknown, abr_or_0)
            return (0, entry['format'].get('abr') or 0)

        video_entries.sort(key=sort_video_key, reverse=True) # Still reverse to get higher quality first among known sizes
        audio_entries.sort(key=sort_audio_key, reverse=True) # Still reverse to get higher quality first among known sizes


        self.video_formats = {entry['label']: {'format_id': entry['format'].get('format_id'), 'has_audio': entry.get('has_audio', False), 'vcodec': entry['format'].get('vcodec'), 'ext': entry['format'].get('ext')} for entry in video_entries}
        self.audio_formats = {entry['label']: {'format_id': entry['format'].get('format_id')} for entry in audio_entries}


        v_opts = list(self.video_formats.keys()) or ["-"]
        a_opts = list(self.audio_formats.keys()) or ["-"]

        self.video_quality_menu.configure(state="normal" if v_opts[0] != "-" else "disabled", values=v_opts)
        self.video_quality_menu.set(v_opts[0])
        self.on_video_quality_change(v_opts[0])

        self.audio_quality_menu.configure(state="normal" if a_opts[0] != "-" else "disabled", values=a_opts)
        self.audio_quality_menu.set(a_opts[0])

        self.on_mode_change(self.mode_selector.get())