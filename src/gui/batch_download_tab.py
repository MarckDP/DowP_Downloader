import customtkinter as ctk
import threading
import os
from tkinter import StringVar, Menu
from customtkinter import filedialog
from src.core.batch_processor import QueueManager, Job
import sys
import yt_dlp
import io
from contextlib import redirect_stdout
from src.core.exceptions import UserCancelledError 
from src.core.downloader import get_video_info
from src.core.batch_processor import Job

import requests
from PIL import Image
from io import BytesIO


# Define widget types that can be disabled
INTERACTIVE_WIDGETS = (
    ctk.CTkButton, 
    ctk.CTkEntry, 
    ctk.CTkOptionMenu, 
    ctk.CTkCheckBox, 
    ctk.CTkSegmentedButton,
    ctk.CTkTextbox
)

class BatchDownloadTab(ctk.CTkFrame):
    """
    Contiene toda la UI y la lógica de interacción para la 
    pestaña de descarga por lotes.
    """
    # Colores copiados de SingleDownloadTab para consistencia visual
    DOWNLOAD_BTN_COLOR = "#28A745"
    DOWNLOAD_BTN_HOVER = "#218838"
    CANCEL_BTN_COLOR = "#DC3545"
    CANCEL_BTN_HOVER = "#C82333"
    DISABLED_TEXT_COLOR = "#D3D3D3"
    DISABLED_FG_COLOR = "#565b5f"
    
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.pack(expand=True, fill="both")
        
        self.app = app
        self.last_download_path = None
        self.thumbnail_label = None
        self.current_thumbnail_url = None
        
        self.job_widgets = {}

        self.selected_job_id: str | None = None
        self.current_video_formats: dict = {}
        self.current_audio_formats: dict = {}
        
        # NUEVO: Flag para prevenir actualizaciones recursivas
        self._updating_ui = False

        # Configuración de la Rejilla Principal (Layout)
        self.grid_columnconfigure(0, weight=35, minsize=350)
        self.grid_columnconfigure(1, weight=65, minsize=450)
        
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0) # <-- NUEVA FILA para botones de acción de cola
        self.grid_rowconfigure(3, weight=1) # <-- Fila principal (lista/config) movida de 2 a 3
        self.grid_rowconfigure(4, weight=0) # <-- Movida de 3 a 4
        self.grid_rowconfigure(5, weight=0)
        
        # Instanciar la lógica de la cola
        self.queue_manager = QueueManager(main_app=app, ui_callback=self.update_job_ui)
        
        # Iniciar el hilo de trabajo
        self.queue_manager.start_worker_thread()
        
        # Dibujar los widgets
        self._create_widgets()

    def _create_widgets(self):
        """Crea los componentes visuales de la pestaña."""
        
        # --- 1. Panel de Entrada (URL y Botones) ---
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.input_frame, text="URL:").grid(row=0, column=0, padx=(10, 5), pady=0)
        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Pega una URL de video o playlist...")
        self.url_entry.grid(row=0, column=1, padx=5, pady=0, sticky="ew")
        self.analyze_button = ctk.CTkButton(self.input_frame, text="Analizar", width=100, command=self._on_analyze_click)
        self.analyze_button.grid(row=0, column=2, padx=5, pady=0)
        self.import_button = ctk.CTkButton(self.input_frame, text="Importar", width=100)
        self.import_button.grid(row=0, column=3, padx=(0, 10), pady=0)

        # --- 2. Panel de Opciones Globales ---
        # --- 2. Panel de Opciones Globales ---
        self.global_options_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.global_options_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew")
        self.global_options_frame.grid_columnconfigure(0, weight=1)

        # --- NUEVO: Panel de Advertencia ---
        # (Este frame ocupa la fila 0)
        warning_frame = ctk.CTkFrame(self.global_options_frame, fg_color="#332222", corner_radius=5)
        warning_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 5))
        warning_frame.grid_columnconfigure(0, weight=1)

        warning_label = ctk.CTkLabel(
            warning_frame, 
            text="ADVERTENCIA: La pestaña 'Descarga por Lotes' está en desarrollo activo.\n"
                 "Aún no es estable y puede fallar de múltiples formas, quiero decir, ni la de descarga única es estable pero XD.\nÚsala con precaución.",
            text_color="#F08080", # Un rojo claro para el texto
            font=ctk.CTkFont(size=12, weight="bold"),
            justify="center"
        )
        warning_label.pack(pady=8, padx=10, fill="x", expand=True)
        # --- FIN Panel de Advertencia ---

        # LÍNEA 1: Checkbox de opciones globales (para futuro)
        global_line1_frame = ctk.CTkFrame(self.global_options_frame, fg_color="transparent")
        # --- CAMBIO: Movido de row=0 a row=1 ---
        global_line1_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(3, 0))

        self.global_options_checkbox = ctk.CTkCheckBox(
            global_line1_frame, 
            text="Aplicar opciones globales (Próximamente)",
            state="disabled"
        )
        self.global_options_checkbox.pack(side="left", padx=5)

        # LÍNEA 2: Radio buttons de miniaturas
        global_line2_frame = ctk.CTkFrame(self.global_options_frame, fg_color="transparent")
        # --- CAMBIO: Movido de row=1 a row=2 ---
        global_line2_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 3))

        ctk.CTkLabel(global_line2_frame, text="Miniaturas:").pack(side="left", padx=(5, 10))

        self.thumbnail_mode_var = StringVar(value="normal")

        self.radio_normal = ctk.CTkRadioButton(
            global_line2_frame, 
            text="Manual", 
            variable=self.thumbnail_mode_var, 
            value="normal",
            command=self._on_thumbnail_mode_change
        )
        self.radio_normal.pack(side="left", padx=5)

        self.radio_with_thumbnail = ctk.CTkRadioButton(
            global_line2_frame, 
            text="Con video/audio", 
            variable=self.thumbnail_mode_var, 
            value="with_thumbnail",
            command=self._on_thumbnail_mode_change
        )
        self.radio_with_thumbnail.pack(side="left", padx=5)

        self.radio_only_thumbnail = ctk.CTkRadioButton(
            global_line2_frame, 
            text="Solo miniaturas", 
            variable=self.thumbnail_mode_var, 
            value="only_thumbnail",
            command=self._on_thumbnail_mode_change
        )
        self.radio_only_thumbnail.pack(side="left", padx=5)
        
        # DESPUÉS (El bloque de código corregido y completo)

        # --- 3. Panel de Acciones de Cola (Botones Limpiar/Resetear) ---
        self.queue_actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.queue_actions_frame.grid(row=2, column=0, padx=(10, 5), pady=(0, 0), sticky="ew")
        
        self.clear_list_button = ctk.CTkButton(
            self.queue_actions_frame, 
            text="Limpiar Lista", 
            height=24,
            font=ctk.CTkFont(size=12),
            command=self._on_clear_list_click
        )
        self.clear_list_button.pack(side="left", padx=(0, 5), pady=5)
        
        self.reset_status_button = ctk.CTkButton(
            self.queue_actions_frame, 
            text="Resetear Estado", 
            height=24,
            font=ctk.CTkFont(size=12),
            command=self._on_reset_status_click
        )
        self.reset_status_button.pack(side="left", padx=5, pady=5)

        # --- 4. Panel de Cola (IZQUIERDA) ---
        self.queue_scroll_frame = ctk.CTkScrollableFrame(self)
        self.queue_scroll_frame.grid(row=3, column=0, padx=(10, 5), pady=(0, 10), sticky="nsew")
        self.queue_placeholder_label = ctk.CTkLabel(self.queue_scroll_frame, text="Aquí aparecerá la cola de trabajos...", font=ctk.CTkFont(size=14))
        self.queue_placeholder_label.pack(expand=True, pady=50, padx=20)
        
        # --- 5. Panel de Configuración (DERECHA) ---
        self.config_panel = ctk.CTkFrame(self)
        self.config_panel.grid(row=3, column=1, padx=(5, 10), pady=(0, 10), sticky="nsew")
        self.config_panel.grid_rowconfigure(0, weight=0)
        self.config_panel.grid_rowconfigure(1, weight=1)
        self.config_panel.grid_columnconfigure(0, weight=1)

        # --- 5a. Panel Superior (Miniatura, Info, Calidad) ---
        self.top_config_frame = ctk.CTkFrame(self.config_panel)
        self.top_config_frame.configure(height=250)
        self.top_config_frame.pack_propagate(False)
        self.top_config_frame.grid(row=0, column=0, sticky="new", padx=5, pady=5)
        self.top_config_frame.grid_columnconfigure(0, weight=0)
        self.top_config_frame.grid_columnconfigure(1, weight=1)

        # --- 5a - Izquierda: Miniatura ---
        self.miniature_frame = ctk.CTkFrame(self.top_config_frame)
        self.miniature_frame.grid(row=0, column=0, padx=(5, 10), pady=5, sticky="n")
        self.thumbnail_container = ctk.CTkFrame(self.miniature_frame, width=160, height=90)
        self.thumbnail_container.pack(pady=(0, 5))
        self.thumbnail_container.pack_propagate(False)
        self.create_placeholder_label(self.thumbnail_container, "Miniatura")
        self.save_thumbnail_button = ctk.CTkButton(
            self.miniature_frame, 
            text="Guardar Miniatura...",
            command=self._on_save_thumbnail_click
        )
        self.save_thumbnail_button.pack(fill="x", pady=5)

        self.auto_save_thumbnail_check = ctk.CTkCheckBox(
            self.miniature_frame, 
            text="Descargar miniatura",
            command=self._on_auto_save_thumbnail_toggle
        )
        self.auto_save_thumbnail_check.pack(fill="x", padx=10, pady=5)
        self.auto_save_thumbnail_check.configure(state="normal")

        # --- 5a - Derecha: Info y Calidad ---
        self.info_frame = ctk.CTkFrame(self.top_config_frame, fg_color="transparent")
        self.info_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        self.info_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.info_frame, text="Título:", anchor="w").pack(fill="x", padx=5, pady=(0,0))
        self.title_entry = ctk.CTkEntry(self.info_frame, font=("", 14), placeholder_text="Título del archivo...")
        self.title_entry.pack(fill="x", padx=5, pady=(0,5))

        self.mode_selector = ctk.CTkSegmentedButton(self.info_frame, values=["Video+Audio", "Solo Audio"], command=self._on_item_mode_change_and_save)
        self.mode_selector.set("Video+Audio")
        self.mode_selector.pack(fill="x", padx=5, pady=5)
        self.video_quality_label = ctk.CTkLabel(self.info_frame, text="Calidad de Video:", anchor="w")
        self.video_quality_label.pack(fill="x", padx=5, pady=(5,0))
        self.video_quality_menu = ctk.CTkOptionMenu(self.info_frame, values=["-"], command=self._on_batch_video_quality_change_and_save)
        self.video_quality_menu.pack(fill="x", padx=5, pady=(0,5))
        self.audio_options_frame = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        self.audio_quality_label = ctk.CTkLabel(self.audio_options_frame, text="Calidad de Audio:", anchor="w")
        self.audio_quality_label.pack(fill="x", padx=5, pady=(5,0))
        self.audio_quality_menu = ctk.CTkOptionMenu(self.audio_options_frame, values=["-"], command=self._on_batch_audio_quality_change_and_save)
        self.audio_quality_menu.pack(fill="x", padx=5, pady=(0,5))
        self.audio_options_frame.pack(fill="x", pady=0, padx=0)

        # --- 5b. Panel Inferior (Recodificación) ---
        self.recode_main_scrollframe = ctk.CTkScrollableFrame(self.config_panel, label_text="Opciones de Recodificación")
        self.recode_main_scrollframe.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.recode_main_scrollframe.grid_columnconfigure(0, weight=1)

        self.recode_main_frame = ctk.CTkFrame(self.recode_main_scrollframe, fg_color="transparent")
        self.recode_main_frame.pack(expand=True, fill="x")

        recode_mode_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        recode_mode_frame.pack(fill="x", padx=10, pady=(5, 10))
        ctk.CTkLabel(recode_mode_frame, text="Modo:").pack(side="left", padx=(0, 10))
        self.recode_mode_selector = ctk.CTkSegmentedButton(
            recode_mode_frame, 
            values=["Modo Rápido", "Modo Manual"], 
            command=self._on_recode_mode_change
        )
        self.recode_mode_selector.pack(side="left", expand=True, fill="x")

        self.recode_quick_frame = ctk.CTkFrame(self.recode_main_frame)
        self.apply_quick_preset_checkbox = ctk.CTkCheckBox(
            self.recode_quick_frame, 
            text="Activar recodificación Rápida", 
            command=self._on_quick_recode_toggle
        )
        self.apply_quick_preset_checkbox.pack(anchor="w", padx=10, pady=(5, 5))
        self.quick_recode_options_frame = ctk.CTkFrame(self.recode_quick_frame, fg_color="transparent")
        ctk.CTkLabel(self.quick_recode_options_frame, text="Preset de Conversión:").pack(pady=5, padx=10)
        self.recode_preset_menu = ctk.CTkOptionMenu(self.quick_recode_options_frame, values=["-"])
        self.recode_preset_menu.pack(pady=5, padx=10, fill="x")
        self.keep_original_quick_checkbox = ctk.CTkCheckBox(
            self.recode_quick_frame, 
            text="Mantener archivo original"
        )
        self.keep_original_quick_checkbox.pack(anchor="w", padx=10, pady=(0, 5))

        self.recode_manual_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        self.recode_quick_frame.pack(fill="x", padx=0, pady=0)
        self.recode_toggle_frame = ctk.CTkFrame(self.recode_manual_frame, fg_color="transparent")
        self.recode_toggle_frame.pack(side="top", fill="x", padx=10, pady=(0, 10)) 
        self.recode_toggle_frame.grid_columnconfigure((0, 1), weight=1)
        self.recode_video_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Recodificar Video", command=self._toggle_recode_panels)
        self.recode_video_checkbox.grid(row=0, column=0, padx=10, pady=(5, 5), sticky="w")
        self.recode_audio_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Recodificar Audio", command=self._toggle_recode_panels)
        self.recode_audio_checkbox.grid(row=0, column=1, padx=10, pady=(5, 5), sticky="w")
        self.keep_original_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Mantener archivo original")
        self.keep_original_checkbox.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="w")
        self.recode_manual_frame.pack_forget()
        self.recode_quick_frame.pack(fill="x", padx=0, pady=0)
        
        self.recode_options_frame = ctk.CTkFrame(self.recode_manual_frame)
        ctk.CTkLabel(self.recode_options_frame, text="Opciones de Video", font=ctk.CTkFont(weight="bold")).pack(pady=(5, 10), padx=10)
        self.proc_type_var = StringVar(value="")
        proc_frame = ctk.CTkFrame(self.recode_options_frame, fg_color="transparent")
        proc_frame.pack(fill="x", padx=10, pady=5)
        self.cpu_radio = ctk.CTkRadioButton(proc_frame, text="CPU", variable=self.proc_type_var, value="CPU", command=self.update_codec_menu)
        self.cpu_radio.pack(side="left", padx=10)
        self.gpu_radio = ctk.CTkRadioButton(proc_frame, text="GPU", variable=self.proc_type_var, value="GPU", command=self.update_codec_menu)
        self.gpu_radio.pack(side="left", padx=20)
        codec_options_frame = ctk.CTkFrame(self.recode_options_frame)
        codec_options_frame.pack(fill="x", padx=10, pady=5)
        codec_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(codec_options_frame, text="Codec:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.recode_codec_menu = ctk.CTkOptionMenu(codec_options_frame, values=["-"], command=self.update_profile_menu)
        self.recode_codec_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(codec_options_frame, text="Perfil/Calidad:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.recode_profile_menu = ctk.CTkOptionMenu(codec_options_frame, values=["-"], command=self.on_profile_selection_change)
        self.recode_profile_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(codec_options_frame, text="Contenedor:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.recode_container_label = ctk.CTkLabel(codec_options_frame, text="-", font=ctk.CTkFont(weight="bold"))
        self.recode_container_label.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        
        self.recode_audio_options_frame = ctk.CTkFrame(self.recode_manual_frame)
        self.recode_audio_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.recode_audio_options_frame, text="Opciones de Audio", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, pady=(5, 10), padx=10)
        ctk.CTkLabel(self.recode_audio_options_frame, text="Codec de Audio:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_codec_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], command=self.update_audio_profile_menu)
        self.recode_audio_codec_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.recode_audio_options_frame, text="Perfil de Audio:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_profile_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"])
        self.recode_audio_profile_menu.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # --- 6. Panel de Salida y Acción ---
        self.download_frame = ctk.CTkFrame(self)
        self.download_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="ew")
        
        line1_frame = ctk.CTkFrame(self.download_frame, fg_color="transparent")
        line1_frame.pack(fill="x", padx=0, pady=(0, 5))
        line1_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(line1_frame, text="Carpeta de Salida:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        self.output_path_entry = ctk.CTkEntry(line1_frame, placeholder_text="Selecciona una carpeta...")
        self.output_path_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.output_path_entry))
        self.output_path_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.select_folder_button = ctk.CTkButton(line1_frame, text="...", width=40, command=self.select_output_folder)
        self.select_folder_button.grid(row=0, column=2, padx=(0, 5), pady=5)
        
        self.open_folder_button = ctk.CTkButton(line1_frame, text="📁", width=40, font=ctk.CTkFont(size=16), command=self.open_last_download_folder, state="disabled")
        self.open_folder_button.grid(row=0, column=3, padx=(0, 5), pady=5)
        
        ctk.CTkLabel(line1_frame, text="Límite (MB/s):").grid(row=0, column=4, padx=(10, 5), pady=5, sticky="w")
        self.speed_limit_entry = ctk.CTkEntry(line1_frame, width=50)
        self.speed_limit_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.speed_limit_entry))
        self.speed_limit_entry.grid(row=0, column=5, padx=(0, 10), pady=5)
        
        line2_frame = ctk.CTkFrame(self.download_frame, fg_color="transparent")
        line2_frame.pack(fill="x", padx=0, pady=0)
        line2_frame.grid_columnconfigure(4, weight=1)
        
        ctk.CTkLabel(line2_frame, text="Si existe:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        self.conflict_policy_menu = ctk.CTkOptionMenu(
            line2_frame, 
            width=100,
            values=["Sobrescribir", "Renombrar", "Omitir"]
        )
        self.conflict_policy_menu.set("Sobrescribir")
        self.conflict_policy_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")
        
        self.create_subfolder_checkbox = ctk.CTkCheckBox(
            line2_frame, 
            text="Crear carpeta:", 
            command=self._toggle_subfolder_name_entry
        )
        self.create_subfolder_checkbox.grid(row=0, column=2, padx=(5, 5), pady=5, sticky="w")
        
        self.subfolder_name_entry = ctk.CTkEntry(line2_frame, width=120, placeholder_text="DowP List (opcional)")
        self.subfolder_name_entry.grid(row=0, column=3, padx=(0, 10), pady=5, sticky="w")
        self.subfolder_name_entry.configure(state="disabled")
        
        self.auto_download_checkbox = ctk.CTkCheckBox(line2_frame, text="Auto-descargar")
        self.auto_download_checkbox.grid(row=0, column=4, padx=5, pady=5, sticky="w")
        
        self.start_queue_button = ctk.CTkButton(
            line2_frame, text="Iniciar Cola", state="disabled", command=self.start_queue_processing, 
            fg_color=self.DOWNLOAD_BTN_COLOR, hover_color=self.DOWNLOAD_BTN_HOVER, 
            text_color_disabled=self.DISABLED_TEXT_COLOR, width=120
        )
        self.start_queue_button.grid(row=0, column=5, padx=(5, 10), pady=5, sticky="e")

        # --- 7. Panel de Progreso ---
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Esperando para iniciar la cola...")
        self.progress_label.pack(pady=(5,0))
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0,5), padx=10, fill="x")

        # --- Carga Inicial ---
        self.output_path_entry.insert(0, self.app.default_download_path)
        
        self.recode_mode_selector.set("Modo Rápido") 
        self._on_recode_mode_change("Modo Rápido")
        
        self._set_config_panel_state("disabled")

    def _toggle_subfolder_name_entry(self):
        """Habilita/deshabilita el entry de nombre de carpeta según el checkbox."""
        if self.create_subfolder_checkbox.get():
            self.subfolder_name_entry.configure(state="normal")
        else:
            self.subfolder_name_entry.configure(state="disabled")

    def _set_config_panel_state(self, state: str = "normal"):
        """
        Habilita o deshabilita todos los widgets interactivos dentro del panel de configuración derecho.
        state: "normal" o "disabled"
        """
        widgets_to_toggle = [
            self.save_thumbnail_button,
            self.title_entry, self.mode_selector,
            self.video_quality_menu, self.audio_quality_menu,
            self.recode_mode_selector,
            self.apply_quick_preset_checkbox, self.recode_preset_menu, 
            self.keep_original_quick_checkbox,
            self.recode_video_checkbox, self.recode_audio_checkbox,
            self.keep_original_checkbox, self.cpu_radio, self.gpu_radio,
            self.recode_codec_menu, self.recode_profile_menu,
            self.recode_audio_codec_menu, self.recode_audio_profile_menu
        ]
        
        for widget in widgets_to_toggle:
            if widget: 
                widget.configure(state=state)
         
        if state == "normal":
             self._on_recode_mode_change(self.recode_mode_selector.get())
        else:
             self.quick_recode_options_frame.pack_forget()
             self.recode_options_frame.pack_forget()
             self.recode_audio_options_frame.pack_forget()

    def create_placeholder_label(self, container, text="Miniatura", font_size=12):
        """Crea el placeholder para la miniatura."""
        for widget in container.winfo_children():
            if isinstance(widget, ctk.CTkLabel):
                widget.destroy()
                
        font = ctk.CTkFont(size=font_size)
        label = ctk.CTkLabel(container, text=text, font=font)
        label.pack(expand=True, fill="both")
        if container == self.thumbnail_container:
             self.thumbnail_label = label

    # NUEVO: Wrapper para audio quality
    def _on_batch_audio_quality_change_and_save(self, selected_label: str):
        """Guarda cuando cambia el audio."""
        if not self._updating_ui:
            self._on_batch_config_change()

    def _on_batch_video_quality_change(self, selected_label: str):
        """
        Solo actualiza la UI según el formato de video seleccionado.
        No guarda la configuración.
        """
        selected_format_info = self.current_video_formats.get(selected_label)
        
        if selected_format_info:
            if selected_format_info.get('is_combined'):
                self.audio_quality_menu.configure(state="disabled")
                self.audio_quality_menu.set("-")
            else:
                self.audio_quality_menu.configure(state="normal")
                
                if self.audio_quality_menu.get() == "-":
                    a_opts = self.audio_quality_menu.cget("values")
                    if a_opts and a_opts[0] != "-":
                        default_audio = next((opt for opt in a_opts if "✨" in opt), a_opts[0])
                        self.audio_quality_menu.set(default_audio)

    def _on_batch_video_quality_change_and_save(self, selected_label: str):
        """
        Wrapper que actualiza la UI Y guarda la configuración.
        """
        self._on_batch_video_quality_change(selected_label)
        if not self._updating_ui:
            self._on_batch_config_change()
        
    def _on_item_mode_change_and_save(self, mode: str):
        """Función wrapper que actualiza la UI Y guarda."""
        self._on_item_mode_change(mode)
        if not self._updating_ui:
            self._on_batch_config_change()
        
    def _on_item_mode_change(self, mode: str):
        """
        Muestra/oculta los menús de calidad en orden CONSISTENTE.
        """
        
        if mode == "Video+Audio":
            self.video_quality_label.pack_forget()
            self.video_quality_menu.pack_forget()
            self.audio_options_frame.pack_forget()
            
            self.video_quality_label.pack(fill="x", padx=5, pady=(5,0))
            self.video_quality_menu.pack(fill="x", padx=5, pady=(0,5))
            self.audio_options_frame.pack(fill="x", pady=0, padx=0)
            
            self._on_batch_video_quality_change(self.video_quality_menu.get())

        elif mode == "Solo Audio":
            self.video_quality_label.pack_forget()
            self.video_quality_menu.pack_forget()
            self.audio_options_frame.pack_forget()
            
            self.audio_options_frame.pack(fill="x", pady=0, padx=0)

    def update_job_ui(self, job_id: str, status: str, message: str):
        """
        Callback que el QueueManager usa para actualizar la UI.
        Se ejecuta en el hilo principal.
        """
        
        if job_id == "QUEUE_STATUS":
            if status == "RUNNING":
                self.start_queue_button.configure(text="Pausar Cola", fg_color=self.CANCEL_BTN_COLOR, hover_color=self.CANCEL_BTN_HOVER)
                self.progress_label.configure(text="Procesando cola...")
            elif status == "PAUSED":
                self.start_queue_button.configure(text="Reanudar Cola", fg_color=self.DOWNLOAD_BTN_COLOR, hover_color=self.DOWNLOAD_BTN_HOVER)
                self.progress_label.configure(text="Cola pausada.")
            return

        job_frame = self.job_widgets.get(job_id)

        if not job_frame:
            job_frame = ctk.CTkFrame(self.queue_scroll_frame, border_width=1, border_color="#555")
            job_frame.pack(fill="x", padx=5, pady=(0, 5))
            
            job_frame.grid_columnconfigure(0, weight=1)
            job_frame.grid_columnconfigure(1, weight=0) # Columna para Reset
            job_frame.grid_columnconfigure(2, weight=0) # Columna para Cerrar
            
            job_frame.title_label = ctk.CTkLabel(job_frame, text=message, anchor="w", wraplength=400)


            job_frame.title_label.grid(row=0, column=0, padx=10, pady=(5,0), sticky="ew")
            
            job_frame.status_label = ctk.CTkLabel(job_frame, text="Pendiente...", anchor="w", text_color="gray", font=ctk.CTkFont(size=11))
            job_frame.status_label.grid(row=1, column=0, padx=10, pady=(0,5), sticky="ew")

            job_frame.progress_bar = ctk.CTkProgressBar(job_frame, height=4)
            job_frame.progress_bar.set(0)
            job_frame.progress_bar.grid(row=2, column=0, columnspan=3, padx=10, pady=(0, 2), sticky="ew") # <-- columnspan=3
            job_frame.progress_bar.grid_remove()

            # Botón de Restaurar (NUEVO)
            job_frame.restore_button = ctk.CTkButton(
                job_frame, text="◁", width=28, height=28,
                font=ctk.CTkFont(size=16),
                fg_color="transparent", hover_color="#555",
                command=lambda jid=job_id: self._on_reset_single_job(jid)
            )
            job_frame.restore_button.grid(row=0, column=1, rowspan=2, padx=(0, 0), pady=5)
            job_frame.restore_button.grid_remove() # Oculto por defecto

            job_frame.close_button = ctk.CTkButton(
                job_frame, text="⨉", width=28, height=28, 
                fg_color="transparent", hover_color="#555",
                command=lambda jid=job_id: self._remove_job(jid)
            )
            job_frame.close_button.grid(row=0, column=2, rowspan=2, padx=(0, 5), pady=5) # <-- Columna 2
            
            job_frame.bind("<Button-1>", lambda e, jid=job_id: self._on_job_select(jid))

            
            job_frame.title_label.bind("<Button-1>", lambda e, jid=job_id: self._on_job_select(jid))
            job_frame.status_label.bind("<Button-1>", lambda e, jid=job_id: self._on_job_select(jid))

            self.job_widgets[job_id] = job_frame
            return

        if status == "RUNNING":
            job_frame.title_label.configure(text_color="white")
            job_frame.status_label.configure(text=message, text_color="#52a2f2") 
            job_frame.progress_bar.grid() 
            if "Descargando" in message:
                try:
                    percent_str = message.split("...")[1].split("%")[0].strip()
                    percent_float = float(percent_str) / 100.0
                    job_frame.progress_bar.set(percent_float)
                except (ValueError, IndexError):
                    job_frame.progress_bar.set(0)
            else:
                 job_frame.progress_bar.set(0) 

        elif status == "COMPLETED":
            job_frame.title_label.configure(text_color="#90EE90")
            job_frame.status_label.configure(text=message, text_color="#28A745") 
            job_frame.progress_bar.set(1)
            job_frame.progress_bar.grid()
            job_frame.restore_button.grid()

        elif status == "SKIPPED": # <-- BLOQUE NUEVO
            job_frame.title_label.configure(text_color="#FFA500") # Naranja
            job_frame.status_label.configure(text=message, text_color="#FF8C00") # Naranja oscuro
            job_frame.progress_bar.set(0)
            job_frame.progress_bar.grid_remove()
            job_frame.restore_button.grid()

        elif status == "FAILED":
            # Si el título actual es 'Analizando...', cámbialo.
            if job_frame.title_label.cget("text") == "Analizando...":
                job_frame.title_label.configure(text="Error de Análisis", text_color="#F08080")
            else:
                # Si ya tenía un título (p.ej. un reintento fallido), solo cambia el color
                job_frame.title_label.configure(text_color="#F08080")

            job_frame.status_label.configure(text=message, text_color="#DC3545", wraplength=400)
            job_frame.progress_bar.set(0)
            job_frame.progress_bar.grid_remove()
            job_frame.restore_button.grid()

        elif status == "PENDING":
            job_frame.title_label.configure(text_color="white")
            job_frame.status_label.configure(text=message, text_color="gray")
            job_frame.progress_bar.set(0)
            job_frame.progress_bar.grid_remove()
            job_frame.restore_button.grid_remove()

    def _remove_job(self, job_id: str):
        """Elimina un trabajo de la UI y de la cola."""
        if job_id in self.job_widgets:
            self.job_widgets[job_id].destroy()
            del self.job_widgets[job_id]
        
        self.queue_manager.remove_job(job_id)
        
        if self.selected_job_id == job_id:
            self.selected_job_id = None
            self._set_config_panel_state("disabled")
            self.create_placeholder_label(self.thumbnail_container, "Miniatura")
        
        if not self.job_widgets:
            self.queue_placeholder_label.pack(expand=True, pady=50, padx=20)
            self.start_queue_button.configure(state="disabled")
            self.progress_label.configure(text="Cola vacía. Analiza una URL para empezar.")

    def _on_job_select(self, job_id: str):
        """MODIFICADO: Previene actualizaciones recursivas con flag."""
        if job_id == self.selected_job_id:
            return

        # Guardar el job anterior MANUALMENTE (sin usar callbacks)
        if self.selected_job_id and not self._updating_ui:
            old_job = self.queue_manager.get_job_by_id(self.selected_job_id)
            if old_job and old_job.analysis_data:
                # Guardar DIRECTAMENTE sin disparar eventos
                old_job.config['title'] = self.title_entry.get()
                old_job.config['mode'] = self.mode_selector.get()
                old_job.config['video_format_label'] = self.video_quality_menu.get()
                old_job.config['audio_format_label'] = self.audio_quality_menu.get()

        # Deseleccionar el job anterior
        if self.selected_job_id and self.selected_job_id in self.job_widgets:
            old_frame = self.job_widgets[self.selected_job_id]
            old_frame.configure(border_color="#555")

        # Seleccionar el nuevo job
        new_frame = self.job_widgets.get(job_id)
        if not new_frame:
            return
            
        new_frame.configure(border_color="#007BFF")
        self.selected_job_id = job_id
        
        job = self.queue_manager.get_job_by_id(job_id)
        if not job or not job.analysis_data:
            print(f"ERROR: No se encontraron datos de análisis para el job {job_id}")
            self._set_config_panel_state("disabled")
            return
            
        self._set_config_panel_state("normal")
        self._populate_config_panel(job)
        
    def _populate_config_panel(self, job: Job):
        """
        MODIFICADO: Usa el flag _updating_ui para prevenir eventos recursivos.
        """
        # ACTIVAR FLAG para prevenir actualizaciones durante la población
        self._updating_ui = True
        
        try:
            info = job.analysis_data
            
            self.title_entry.delete(0, 'end')
            self.create_placeholder_label(self.thumbnail_container, "Cargando...")
            self.current_video_formats.clear()
            self.current_audio_formats.clear()
            
            title = job.config.get('title')
            
            if not title:
                title = info.get('title')
            
            if not title or not isinstance(title, str) or title == 'Sin título' or title == 'Analizando...':
                title = f"video_{job.job_id[:6]}"
            
            try:
                title_bytes = title.encode('utf-8', errors='ignore')
                title = title_bytes.decode('utf-8')
            except Exception:
                title = f"video_{job.job_id[:6]}"
            
            if not title.strip() or title == 'Sin título':
                title = f"video_{job.job_id[:6]}"
            
            self.title_entry.insert(0, title)
            
            thumbnail_url = info.get('thumbnail')
            if thumbnail_url:
                threading.Thread(target=self.load_thumbnail, args=(thumbnail_url,), daemon=True).start()
            elif any(f.get('acodec') != 'none' for f in info.get('formats', [])):
                 self.create_placeholder_label(self.thumbnail_container, "🎵", font_size=60)
            else:
                self.create_placeholder_label(self.thumbnail_container, "Miniatura")

            formats = info.get('formats', [])
            video_entries, audio_entries = [], []
            
            video_duration = info.get('duration', 0)

            for f in formats:
                format_type = self._classify_format(f)
                
                size_mb_str = "Tamaño desc."
                size_sort_priority = 0
                filesize = f.get('filesize') or f.get('filesize_approx')
                if filesize:
                    size_mb_str = f"{filesize / (1024*1024):.2f} MB"; size_sort_priority = 2
                else:
                    bitrate = f.get('tbr') or f.get('vbr') or f.get('abr')
                    if bitrate and video_duration:
                        estimated_bytes = (bitrate*1000/8)*video_duration; size_mb_str=f"Aprox. {estimated_bytes/(1024*1024):.2f} MB"; size_sort_priority = 1
                
                vcodec_raw = f.get('vcodec'); acodec_raw = f.get('acodec')
                vcodec = vcodec_raw.split('.')[0] if vcodec_raw else 'none'
                acodec = acodec_raw.split('.')[0] if acodec_raw else 'none'
                ext = f.get('ext', 'N/A')
                
                if format_type == 'VIDEO':
                    is_combined = acodec != 'none' and acodec is not None
                    fps = f.get('fps')
                    fps_tag = f"{fps:.0f}" if fps else ""
                    label_base = f"{f.get('height', 'Video')}p{fps_tag} ({ext}"
                    label_codecs = f", {vcodec}+{acodec}" if is_combined else f", {vcodec}"
                    label_tag = " [Combinado]" if is_combined else ""
                    note = f.get('format_note') or ''
                    note_tag = ""  
                    informative_keywords = ['hdr', 'premium', 'dv', 'hlg', 'storyboard']
                    if any(keyword in note.lower() for keyword in informative_keywords):
                        note_tag = f" [{note}]"
                    protocol = f.get('protocol', '')
                    protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                    label = f"{label_base}{label_codecs}){label_tag}{note_tag}{protocol_tag} - {size_mb_str}"

                    tags = []; compatibility_issues, unknown_issues = self._get_format_compatibility_issues(f)
                    if not compatibility_issues and not unknown_issues: tags.append("✨")
                    elif compatibility_issues or unknown_issues:
                        tags.append("⚠️")
                    if tags: label += f" {' '.join(tags)}"

                    video_entries.append({'label': label, 'format': f, 'is_combined': is_combined, 'sort_priority': size_sort_priority})
                
                elif format_type == 'AUDIO':
                    abr = f.get('abr') or f.get('tbr')
                    lang_code = f.get('language')
                    lang_name = "Idioma Desconocido"
                    if lang_code:
                        norm_code = lang_code.replace('_', '-').lower()
                        lang_name = self.app.LANG_CODE_MAP.get(norm_code, self.app.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code))
                    
                    lang_prefix = f"{lang_name} - " if lang_code else ""
                    note = f.get('format_note') or ''
                    drc_tag = " (DRC)" if 'DRC' in note else ""
                    protocol = f.get('protocol', '')
                    protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                    label = f"{lang_prefix}{abr:.0f}kbps ({acodec}, {ext}){drc_tag}{protocol_tag}" if abr else f"{lang_prefix}Audio ({acodec}, {ext}){drc_tag}{protocol_tag}"
                    
                    if acodec in self.app.EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]: label += " ✨"
                    else: label += " ⚠️"
                    audio_entries.append({'label': label, 'format': f, 'sort_priority': size_sort_priority})
            
            video_entries.sort(key=lambda e: (
                -(e['format'].get('height') or 0),      
                1 if "[Combinado]" in e['label'] else 0, 
                0 if "✨" in e['label'] else 1,         
                -(e['format'].get('tbr') or 0)          
            ))
            
            def custom_audio_sort_key(entry):
                f = entry['format']
                lang_code_raw = f.get('language') or ''
                norm_code = lang_code_raw.replace('_', '-')
                lang_priority = self.app.LANGUAGE_ORDER.get(norm_code, self.app.LANGUAGE_ORDER.get(norm_code.split('-')[0], self.app.DEFAULT_PRIORITY))
                quality = f.get('abr') or f.get('tbr') or 0
                return (lang_priority, -quality)
            
            audio_entries.sort(key=custom_audio_sort_key)
            
            self.current_video_formats = {e['label']: {k: e['format'].get(k) for k in ['format_id', 'vcodec', 'acodec', 'ext', 'width', 'height']} | {'is_combined': e.get('is_combined', False)} for e in video_entries}
            self.current_audio_formats = {e['label']: {k: e['format'].get(k) for k in ['format_id', 'acodec', 'ext']} for e in audio_entries}
            
            has_video_found = bool(video_entries)
            has_audio_found = bool(audio_entries)
            
            if not has_video_found and has_audio_found:
                self.mode_selector.configure(values=["Solo Audio"])
                self.mode_selector.set("Solo Audio")
                self._on_item_mode_change("Solo Audio")
            elif not has_video_found and not has_audio_found:
                self.mode_selector.configure(values=["Video+Audio", "Solo Audio"])
                self.mode_selector.set("Video+Audio")
                self._on_item_mode_change("Video+Audio")
            else:
                self.mode_selector.configure(values=["Video+Audio", "Solo Audio"])
                
                saved_mode = job.config.get('mode', 'Video+Audio')
                if saved_mode in ["Video+Audio", "Solo Audio"]:
                    self.mode_selector.set(saved_mode)
                    self._on_item_mode_change(saved_mode)
                else:
                    self.mode_selector.set("Video+Audio")
                    self._on_item_mode_change("Video+Audio")

            v_opts = list(self.current_video_formats.keys()) or ["-"]
            a_opts = list(self.current_audio_formats.keys()) or ["-"]

            default_video_selection = v_opts[0]
            for option in v_opts:
                if "✨" in option:
                    default_video_selection = option
                    break 
            
            default_audio_selection = a_opts[0]
            for option in a_opts:
                if "✨" in option:
                    default_audio_selection = option
                    break

            self.video_quality_menu.configure(state="normal" if v_opts[0] != "-" else "disabled", values=v_opts)
            self.audio_quality_menu.configure(state="normal" if a_opts[0] != "-" else "disabled", values=a_opts)
            
            saved_video = job.config.get('video_format_label', '-')
            saved_audio = job.config.get('audio_format_label', '-')
            
            if saved_video in v_opts:
                self.video_quality_menu.set(saved_video)
            else:
                self.video_quality_menu.set(default_video_selection)
            
            if saved_audio in a_opts:
                self.audio_quality_menu.set(saved_audio)
            else:
                self.audio_quality_menu.set(default_audio_selection)
            
            self._on_batch_video_quality_change(self.video_quality_menu.get())
            
            # Restaurar estado del checkbox de miniatura
            saved_thumbnail = job.config.get('download_thumbnail', False)
            if saved_thumbnail:
                self.auto_save_thumbnail_check.select()
            else:
                self.auto_save_thumbnail_check.deselect()
        
        finally:
            # DESACTIVAR FLAG al terminar
            self._updating_ui = False

    def load_thumbnail(self, url: str):
        """Carga una miniatura desde una URL en un hilo."""
        self.current_thumbnail_url = url
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            img_data = response.content
            
            pil_image = Image.open(BytesIO(img_data))
            display_image = pil_image.copy()
            display_image.thumbnail((160, 90), Image.Resampling.LANCZOS)
            ctk_image = ctk.CTkImage(light_image=display_image, dark_image=display_image, size=display_image.size)

            def set_new_image():
                if self.thumbnail_label: self.thumbnail_label.destroy()
                self.thumbnail_label = ctk.CTkLabel(self.thumbnail_container, text="", image=ctk_image)
                self.thumbnail_label.pack(expand=True)
                self.thumbnail_label.image = ctk_image
            
            self.app.after(0, set_new_image)
        except Exception as e:
            print(f"Error al cargar la miniatura del lote: {e}")
            self.app.after(0, self.create_placeholder_label, self.thumbnail_container, "Error")

    def get_smart_thumbnail_extension(self, image_data):
        """
        Detecta el formato óptimo para guardar la miniatura:
        - PNG si tiene transparencia
        - JPG en otros casos (más compacto)
        """
        try:
            from PIL import Image
            import io
            
            img = Image.open(io.BytesIO(image_data))
            
            # Verificar transparencia
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                return '.png'
            
            # Por defecto JPG (más compacto)
            return '.jpg'
            
        except Exception as e:
            print(f"ERROR detectando formato de miniatura: {e}")
            return '.jpg'  # Fallback seguro

    def _on_auto_save_thumbnail_toggle(self):
        """
        Callback cuando cambia el checkbox individual de miniatura.
        Deshabilita el botón de guardar manual y guarda el estado.
        """
        if self.auto_save_thumbnail_check.get():
            self.save_thumbnail_button.configure(state="disabled")
        else:
            self.save_thumbnail_button.configure(state="normal")
        
        # Guardar el estado en el job actual
        if not self._updating_ui:
            self._on_batch_config_change()

    def _on_thumbnail_mode_change(self):
        """Callback cuando cambia el modo de descarga global."""
        mode = self.thumbnail_mode_var.get()
        
        if mode == "normal":
            # Modo Manual: Habilitar el checkbox individual
            self.auto_save_thumbnail_check.configure(state="normal")
            if self.selected_job_id:
                self._set_config_panel_state("normal")
        
        elif mode == "with_thumbnail":
            # Con video/audio: Deshabilitar checkbox (se descarga siempre)
            self.auto_save_thumbnail_check.configure(state="disabled")
            if self.selected_job_id:
                self._set_config_panel_state("normal")
        
        elif mode == "only_thumbnail":
            # Solo miniaturas: Deshabilitar checkbox y panel de calidad
            self.auto_save_thumbnail_check.configure(state="disabled")
            if self.selected_job_id:
                self._set_config_panel_state("disabled")

    def _on_save_thumbnail_click(self):
        """Abre diálogo para guardar la miniatura actual con el mismo nombre del archivo."""
        if not self.current_thumbnail_url:
            print("ERROR: No hay miniatura cargada para guardar.")
            return
        
        file_name = self.title_entry.get().strip()
        if not file_name:
            file_name = "thumbnail"
        
        # Descargar la imagen para detectar su formato
        try:
            response = requests.get(self.current_thumbnail_url, timeout=10)
            response.raise_for_status()
            image_data = response.content
            
            # Detectar formato óptimo
            smart_ext = self.get_smart_thumbnail_extension(image_data)
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=smart_ext,
                filetypes=[
                    ("Imagen Óptima", f"*{smart_ext}"),
                    ("JPEG", "*.jpg"), 
                    ("PNG", "*.png"),
                    ("Todos", "*.*")
                ],
                initialfile=f"{file_name}{smart_ext}"
            )
            
            self.app.lift()  # ✅ DENTRO DEL TRY
            self.app.focus_force()
            
            if not file_path:
                return  # Usuario canceló
            
            # Guardar usando los datos ya descargados
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            print(f"INFO: Miniatura guardada en: {file_path}")
            
        except Exception as e:
            print(f"ERROR: No se pudo guardar la miniatura: {e}")

    def _classify_format(self, f):
        """Clasifica un formato de yt-dlp como 'VIDEO', 'AUDIO' o 'UNKNOWN'."""
        if f.get('height') or f.get('width'):
            return 'VIDEO'
        
        format_id_raw = f.get('format_id')
        format_note_raw = f.get('format_note')
        format_id = format_id_raw.lower() if format_id_raw else ''
        format_note = format_note_raw.lower() if format_note_raw else ''
        if 'audio' in format_id or 'audio' in format_note:
            return 'AUDIO'
            
        vcodec = f.get('vcodec')
        acodec = f.get('acodec')
        if (vcodec == 'none' or not vcodec) and (acodec and acodec != 'none'):
            return 'AUDIO'
            
        if f.get('ext') in self.app.AUDIO_EXTENSIONS:
            return 'AUDIO'
            
        if f.get('ext') in self.app.VIDEO_EXTENSIONS:
            return 'VIDEO'
            
        if vcodec == 'none':
            return 'AUDIO'
            
        return 'UNKNOWN'

    def _get_format_compatibility_issues(self, format_dict):
        """Comprueba compatibilidad."""
        if not format_dict: return [], []
        issues = []
        unknown = []
        vcodec = (format_dict.get('vcodec') or 'none').split('.')[0]
        acodec = (format_dict.get('acodec') or 'none').split('.')[0]
        ext = format_dict.get('ext') or 'none'

        if vcodec != 'none' and vcodec not in self.app.EDITOR_FRIENDLY_CRITERIA["compatible_vcodecs"]:
            issues.append(f"video ({vcodec})")
        if acodec != 'none' and acodec not in self.app.EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]:
            issues.append(f"audio ({acodec})")
        if vcodec != 'none' and ext not in self.app.EDITOR_FRIENDLY_CRITERIA["compatible_exts"]:
            issues.append(f"contenedor (.{ext})")
        return issues, unknown

    def _on_global_options_toggle(self):
        """Activa o desactiva la cadena de menús globales."""
        is_enabled = self.global_options_checkbox.get()
        state = "normal" if is_enabled else "disabled"
        self.mode_menu.configure(state=state)
        if is_enabled:
            self._on_mode_change(self.mode_menu.get())
        else:
            self.container_menu.configure(state="disabled", values=["- (Opciones Desact.) -"])
            self.quality_menu.configure(state="disabled", values=["- (Opciones Desact.) -"])
            self.container_menu.set("- (Opciones Desact.) -")
            self.quality_menu.set("- (Opciones Desact.) -")

    def _on_mode_change(self, mode: str):
        """Actualiza el menú de Contenedores global."""
        if not self.global_options_checkbox.get(): return
        containers = ["-"]
        if mode == "Video+Audio":
            containers = ["mp4", "mkv", "mov", "webm"]
        elif mode == "Solo Audio":
            containers = ["mp3", "wav", "m4a", "flac", "opus"]
        self.container_menu.configure(state="normal", values=containers)
        if containers:
            self.container_menu.set(containers[0])
            self._on_container_change(containers[0])
        else:
             self._on_container_change(None)

    def _on_container_change(self, container: str | None):
        """Actualiza el menú de Calidad global."""
        if not self.global_options_checkbox.get() or container is None:
            self.quality_menu.configure(state="disabled", values=["-"])
            self.quality_menu.set("-")
            return
        
        mode = self.mode_menu.get()
        qualities = ["-"]
        if mode == "Video+Audio":
            qualities = ["Mejor (bv+ba/b)", "4K (2160p)", "2K (1440p)", "1080p", "720p", "480p", "Peor (wv+wa/w)"]
        elif mode == "Solo Audio":
            qualities = ["Mejor Audio (ba)", "Alta (256k)", "Media (192k)", "Baja (128k)"]
        self.quality_menu.configure(state="normal", values=qualities)
        if qualities:
            self.quality_menu.set(qualities[0])

    def start_queue_processing(self):
        """Inicia (o pausa) el procesamiento de la cola."""
        
        if self.queue_manager.pause_event.is_set():
            if not hasattr(self.queue_manager, 'subfolder_created'):
                if self.create_subfolder_checkbox.get():
                    output_dir = self.output_path_entry.get()
                    subfolder_name = self.subfolder_name_entry.get().strip()
                    
                    if not subfolder_name:
                        subfolder_name = "DowP List"
                    
                    subfolder_path = os.path.join(output_dir, subfolder_name)
                    if os.path.exists(subfolder_path):
                        counter = 1
                        while True:
                            new_subfolder = f"{subfolder_name} {counter:02d}"
                            subfolder_path = os.path.join(output_dir, new_subfolder)
                            if not os.path.exists(subfolder_path):
                                break
                            counter += 1
                    
                    try:
                        os.makedirs(subfolder_path, exist_ok=True)
                        self.queue_manager.subfolder_path = subfolder_path
                        self.queue_manager.subfolder_created = True
                        print(f"INFO: Subcarpeta creada: {subfolder_path}")
                    except Exception as e:
                        print(f"ERROR: No se pudo crear la subcarpeta: {e}")
                        return
                else:
                    self.queue_manager.subfolder_created = True
            
            print("INFO: Reanudando la cola de lotes.")
            self.queue_manager.start_queue()
        else:
            print("INFO: Pausando la cola de lotes.")
            self.queue_manager.pause_queue()
    
    def select_output_folder(self):
        """Abre el diálogo para seleccionar la carpeta de salida."""
        folder_path = filedialog.askdirectory()
        self.app.lift()
        self.app.focus_force()
        if folder_path:
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, folder_path)
            self.app.default_download_path = folder_path
            self.app.single_tab.save_settings() 

    def open_last_download_folder(self):
        """Abre la carpeta del último archivo descargado por esta pestaña."""
        if not self.last_download_path or not os.path.exists(self.last_download_path):
            print("ERROR: No hay un archivo válido para mostrar o la ruta no existe.")
            return
        
        try:
            if os.name == "nt":
                import subprocess
                subprocess.Popen(['explorer', '/select,', os.path.normpath(self.last_download_path)])
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(['open', '-R', self.last_download_path])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', os.path.dirname(self.last_download_path)])
        except Exception as e:
            print(f"Error al intentar abrir la carpeta: {e}")

    def create_entry_context_menu(self, widget):
        """Crea un menú contextual simple para los Entry widgets."""
        menu = Menu(self, tearoff=0)
        
        def paste_text():
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
            try:
                widget.insert("insert", self.clipboard_get())
            except:
                pass
                
        menu.add_command(label="Copiar", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Pegar", command=paste_text)
        menu.add_separator()
        menu.add_command(label="Seleccionar todo", command=lambda: widget.select_range(0, 'end'))
        
        menu.tk_popup(widget.winfo_pointerx(), widget.winfo_pointery())

    def _on_recode_mode_change(self, mode: str):
        """Cambia entre modo rápido y manual de recodificación."""
        if mode == "Modo Rápido":
            self.recode_manual_frame.pack_forget()
            self.recode_quick_frame.pack(fill="x", padx=0, pady=0)
        else:
            self.recode_quick_frame.pack_forget()
            self.recode_manual_frame.pack(fill="x", padx=0, pady=0)
        self._on_quick_recode_toggle()
        self._toggle_recode_panels()

    def _on_quick_recode_toggle(self):
        """Toggle opciones rápidas."""
        is_checked = self.apply_quick_preset_checkbox.get() == 1
        if is_checked:
            self.quick_recode_options_frame.pack(fill="x", padx=0, pady=0)
            self.keep_original_quick_checkbox.configure(state="normal")
        else:
            self.quick_recode_options_frame.pack_forget()
            self.keep_original_quick_checkbox.configure(state="disabled")

    def _toggle_recode_panels(self):
        """Toggle paneles manuales."""
        is_video_on = self.recode_video_checkbox.get() == 1
        is_audio_on = self.recode_audio_checkbox.get() == 1
        
        if is_video_on:
            self.recode_options_frame.pack(fill="x", padx=5, pady=5, before=self.recode_audio_options_frame)
        else:
            self.recode_options_frame.pack_forget()
            
        if is_audio_on:
             self.recode_audio_options_frame.pack(fill="x", padx=5, pady=5)
        else:
            self.recode_audio_options_frame.pack_forget()
            
        if is_video_on or is_audio_on:
             self.keep_original_checkbox.configure(state="normal")
        else:
             self.keep_original_checkbox.configure(state="disabled")

    def update_codec_menu(self):
        """Actualiza menú codec."""
        proc_type = self.proc_type_var.get()
        if proc_type:
            dummy_codecs = [f"{proc_type} Codec 1", f"{proc_type} Codec 2"]
            self.recode_codec_menu.configure(state="normal", values=dummy_codecs)
            self.recode_codec_menu.set(dummy_codecs[0])
            self.update_profile_menu(dummy_codecs[0])
        else:
            self.recode_codec_menu.configure(state="disabled", values=["-"])
            self.recode_codec_menu.set("-")
            self.update_profile_menu("-")

    def update_profile_menu(self, codec: str):
        """Actualiza menú perfil."""
        if codec != "-":
             dummy_profiles = [f"{codec} Perfil A", f"{codec} Perfil B"]
             self.recode_profile_menu.configure(state="normal", values=dummy_profiles)
             self.recode_profile_menu.set(dummy_profiles[0])
        else:
            self.recode_profile_menu.configure(state="disabled", values=["-"])
            self.recode_profile_menu.set("-")
        self.on_profile_selection_change(self.recode_profile_menu.get())

    def on_profile_selection_change(self, profile: str):
        """Callback cuando cambia el perfil."""
        if "Perfil A" in profile:
             self.recode_container_label.configure(text=".mp4")
        elif "Perfil B" in profile:
             self.recode_container_label.configure(text=".mkv")
        else:
             self.recode_container_label.configure(text="-")

    def update_audio_profile_menu(self, audio_codec: str):
        """Actualiza menú perfil de audio."""
        if audio_codec != "-":
             dummy_profiles = [f"{audio_codec} Perfil X", f"{audio_codec} Perfil Y"]
             self.recode_audio_profile_menu.configure(state="normal", values=dummy_profiles)
             self.recode_audio_profile_menu.set(dummy_profiles[0])
        else:
            self.recode_audio_profile_menu.configure(state="disabled", values=["-"])
            self.recode_audio_profile_menu.set("-")

    def _on_clear_list_click(self):
        """
        Elimina todos los trabajos de la cola y resetea la sesión de lote.
        """
        print("INFO: Limpiando la lista de trabajos y reseteando la sesión de lote...")
        
        # 1. Pausar la cola (si estaba corriendo)
        self.queue_manager.pause_queue()

        # 2. Eliminar todos los trabajos de la UI y la lógica
        all_job_ids = list(self.job_widgets.keys())
        for job_id in all_job_ids:
            self._remove_job(job_id) 
            # _remove_job eventualmente llamará a self.start_queue_button.configure(state="disabled")
            # cuando la lista esté vacía.

        # 3. Resetear la subcarpeta del lote (LA CLAVE)
        # Esto asegura que el próximo "Iniciar Cola" cree una carpeta nueva.
        if hasattr(self.queue_manager, 'subfolder_path'):
            delattr(self.queue_manager, 'subfolder_path')
        if hasattr(self.queue_manager, 'subfolder_created'):
            delattr(self.queue_manager, 'subfolder_created')
        
        # 4. Forzar el reseteo visual del botón a su estado inicial
        self.start_queue_button.configure(
            text="Iniciar Cola", 
            fg_color=self.DOWNLOAD_BTN_COLOR, 
            hover_color=self.DOWNLOAD_BTN_HOVER,
            state="disabled" # Desactivado porque la lista está vacía
        )
        
        # 5. Actualizar UI
        self.progress_label.configure(text="Cola vacía. Analiza una URL para empezar.")
        print("INFO: Sesión de lote finalizada.")

    def _on_reset_status_click(self):
        """
        Resetea el estado de trabajos (COMPLETED/FAILED -> PENDING) 
        y resetea la sesión de lote para una nueva ejecución.
        """
        print("INFO: Reseteando estado de trabajos para un nuevo lote...")

        # 1. Pausar la cola (si estaba corriendo)
        self.queue_manager.pause_queue()
        
        # 2. Resetear el estado de los trabajos en la lógica
        jobs_to_reset = []
        with self.queue_manager.jobs_lock:
            for job in self.queue_manager.jobs:
                if job.status in ("COMPLETED", "FAILED", "SKIPPED"):
                    jobs_to_reset.append(job)

        if not jobs_to_reset:
            print("INFO: No hay trabajos completados/fallidos que resetear.")
            # Continuamos igualmente para resetear la sesión de lote
        else:
            # 3. Actualizar la UI para los trabajos reseteados
            for job in jobs_to_reset:
                job.status = "PENDING"
                self.app.after(0, self.update_job_ui, job.job_id, "PENDING", "Listo para descargar")
            print(f"INFO: {len(jobs_to_reset)} trabajos reseteados a PENDIENTE.")
        
        # 4. Resetear la subcarpeta del lote (LA CLAVE)
        if hasattr(self.queue_manager, 'subfolder_path'):
            delattr(self.queue_manager, 'subfolder_path')
            print("INFO: Reseteada la subcarpeta del lote anterior.")
        if hasattr(self.queue_manager, 'subfolder_created'):
            delattr(self.queue_manager, 'subfolder_created')
        
        # 5. Forzar el reseteo visual del botón
        # Comprobar si hay *algún* trabajo en la lista para decidir el estado
        jobs_exist = len(self.job_widgets) > 0
        
        self.start_queue_button.configure(
            text="Iniciar Cola", 
            fg_color=self.DOWNLOAD_BTN_COLOR, 
            hover_color=self.DOWNLOAD_BTN_HOVER,
            state="normal" if jobs_exist else "disabled" # Habilitado si hay trabajos
        )
        
        if jobs_exist:
            self.progress_label.configure(text="Estado reseteado. Listo para iniciar un nuevo lote.")
        else:
            self.progress_label.configure(text="Cola vacía. Analiza una URL para empezar.")
            
        print("INFO: Sesión de lote finalizada. Listo para un nuevo lote.")


    def _on_reset_single_job(self, job_id: str):
        """Resetea un único trabajo (COMPLETED/FAILED/SKIPPED) a PENDING."""
        job = self.queue_manager.get_job_by_id(job_id)
        
        if not job:
            print(f"ERROR: No se encontró job {job_id} para resetear.")
            return

        if job.status in ("COMPLETED", "FAILED", "SKIPPED"):
            print(f"INFO: Reseteando estado para job {job_id}.")
            job.status = "PENDING"
            
            # Actualizar la UI para este job
            self.update_job_ui(job_id, "PENDING", "Listo para descargar")
            
            # Si la cola estaba pausada (porque se completó o la pausó el usuario),
            # y el botón principal no está en modo "Pausar Cola" (rojo),
            # hay que habilitarlo para que el usuario pueda reanudar.
            if self.queue_manager.pause_event.is_set():
                current_text = self.start_queue_button.cget("text")
                if current_text != "Pausar Cola":
                    self.start_queue_button.configure(state="normal")
                    self.progress_label.configure(text="Trabajo reseteado. Listo para reanudar la cola.")
        else:
            print(f"INFO: Job {job_id} ya está PENDING o RUNNING, no se resetea.")

    def _on_analyze_click(self):
        """Inicia el análisis de la URL en un hilo separado."""
        url = self.url_entry.get().strip()
        if not url:
            return
        
        print(f"INFO: Iniciando análisis de lotes para: {url}")
        
        config = {
            "url": url,
            "title": "Analizando...",
            "mode": "Video+Audio",
            "video_format_label": "-",
            "audio_format_label": "-",
        }
        
        temp_job = Job(config=config)
        
        if self.job_widgets:
            pass
        else:
            self.queue_placeholder_label.pack_forget()
        
        self.queue_manager.add_job(temp_job)
        
        self.app.after(0, lambda: self.update_job_ui(temp_job.job_id, "RUNNING", "Analizando URL..."))
        
        threading.Thread(target=self._run_analysis, args=(url, temp_job.job_id), daemon=True).start()
        
        self.url_entry.delete(0, 'end') # <-- AÑADIR ESTO

    def _run_analysis(self, url: str, job_id: str):
        """
        Hilo de trabajo que ejecuta yt-dlp para obtener información.
        """
        try:
            single_tab = self.app.single_tab 

            ydl_opts_flat = {
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'referer': url,
                'noplaylist': False,
                'extract_flat': True,
                'listsubtitles': False,
            }

            cookie_mode = single_tab.cookie_mode_menu.get()
            browser_arg = None
            profile = None
            
            if cookie_mode == "Archivo Manual..." and single_tab.cookie_path_entry.get():
                ydl_opts_flat['cookiefile'] = single_tab.cookie_path_entry.get()
            elif cookie_mode != "No usar":
                browser_arg = single_tab.browser_var.get()
                profile = single_tab.browser_profile_entry.get()
                if profile:
                    browser_arg_with_profile = f"{browser_arg}:{profile}"
                    ydl_opts_flat['cookiesfrombrowser'] = (browser_arg_with_profile,)
                else:
                    ydl_opts_flat['cookiesfrombrowser'] = (browser_arg,)

            info_dict = None
            with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
                info_dict = ydl.extract_info(url, download=False)
            
            if not info_dict:
                raise Exception("No se pudo obtener información (Paso 1: superficial).")

            is_playlist = info_dict.get("_type") == "playlist" or (info_dict.get("entries") and len(info_dict.get("entries")) > 0)
            has_valid_title = bool(info_dict.get('title')) and info_dict.get('title') != 'Sin título'

            if not is_playlist and (not has_valid_title or info_dict.get('extractor_key') == 'Generic'):
                print("INFO: Análisis superficial incompleto. Re-intentando con análisis profundo (modo video único)...")
                
                ydl_opts_deep = {
                    'no_warnings': True,
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                    'referer': url,
                    'noplaylist': True,
                    'playlist_items': '1',
                    'listsubtitles': False,
                }
                
                if cookie_mode == "Archivo Manual..." and single_tab.cookie_path_entry.get():
                    ydl_opts_deep['cookiefile'] = single_tab.cookie_path_entry.get()
                elif cookie_mode != "No usar":
                    if browser_arg:
                        if profile:
                            browser_arg_with_profile = f"{browser_arg}:{profile}"
                            ydl_opts_deep['cookiesfrombrowser'] = (browser_arg_with_profile,)
                        else:
                            ydl_opts_deep['cookiesfrombrowser'] = (browser_arg,)

                with yt_dlp.YoutubeDL(ydl_opts_deep) as ydl:
                    info_dict = ydl.extract_info(url, download=False)

                if not info_dict:
                    raise Exception("No se pudo obtener información (Paso 2: profundo).")
                
                if info_dict.get('_type') in ('playlist', 'multi_video'):
                    if info_dict.get('entries') and len(info_dict['entries']) > 0:
                        print("INFO: Análisis profundo devolvió lista, extrayendo primer video.")
                        info_dict = info_dict['entries'][0]

            self.app.after(0, self._on_analysis_complete, info_dict, job_id)

        except Exception as e:
            error_message = f"ERROR: Falló el análisis de lotes: {e}"
            print(error_message)
            
            error_str = str(e)
            self.app.after(0, self._on_analysis_failed, job_id, error_str)

    def _on_analysis_failed(self, job_id: str, error_message: str):
        """Callback del hilo principal cuando un análisis falla."""
        self.update_job_ui(job_id, "FAILED", f"Error: {error_message[:80]}")

    def _on_analysis_complete(self, info_dict: dict, job_id: str):
        """Se ejecuta en el hilo principal cuando el análisis termina."""
        

        job = self.queue_manager.get_job_by_id(job_id)
        if not job:
            return
        
        job_widget = self.job_widgets.get(job_id)
        
        if not info_dict or not isinstance(info_dict, dict):
            print(f"ERROR: info_dict inválido para job {job_id}")
            self.update_job_ui(job_id, "FAILED", "Error: Datos de análisis inválidos")
            return
        
        is_playlist = info_dict.get("_type") == "playlist" or (info_dict.get("entries") and len(info_dict.get("entries")) > 0)
        
        if is_playlist and info_dict.get('extractor_key') != 'Generic':
            print(f"INFO: Playlist detectada con {len(info_dict.get('entries', []))} videos.")
            
            first_entry = info_dict.get('entries', [])[0] if info_dict.get('entries') else None
            if first_entry:
                title = first_entry.get('title') or 'Video sin título'
                job.config['title'] = title
                job.analysis_data = first_entry
                
                if job_widget:
                    job_widget.title_label.configure(text=title)
            
            for entry in info_dict.get('entries', [])[1:]:
                if not entry: 
                    continue
                
                video_url = entry.get('url')
                title = entry.get('title') or 'Video sin título'
                
                config = {
                    "url": video_url,
                    "title": title,
                    "mode": "Video+Audio",
                    "video_format_label": "-",
                    "audio_format_label": "-",
                }

                new_job = Job(config=config)
                new_job.analysis_data = entry
                self.queue_manager.add_job(new_job)
        else:
            print("INFO: Video único detectado.")
            title = info_dict.get('title') or 'Sin título'
            job.config['title'] = title
            job.analysis_data = info_dict
            
            if job_widget:
                job_widget.title_label.configure(text=title)

        self.update_job_ui(job_id, "PENDING", "Listo para descargar")
        
        self.start_queue_button.configure(state="normal")
        
        # DESPUÉS (La lógica correcta)
        if self.auto_download_checkbox.get():
            print("INFO: Auto-descargar activado.")
            
            # Si el usuario NO ha pausado la cola manualmente, iníciala.
            if not self.queue_manager.user_paused:
                
                # Y solo iníciala si está actualmente pausada (inactiva)
                if self.queue_manager.pause_event.is_set():
                    print("INFO: Auto-descargar iniciando/reanudando la cola...")
                    # Reseteamos subfolder_created para que use la misma carpeta
                    # si es parte del mismo lote (antes de resetear)
                    if hasattr(self.queue_manager, 'subfolder_created'):
                         delattr(self.queue_manager, 'subfolder_created')
                    
                    self.start_queue_processing()
                    self.progress_label.configure(text=f"Descargando automáticamente...")
                else:
                    # La cola ya está corriendo, no hay que hacer nada.
                    print("INFO: Auto-descargar: La cola ya estaba corriendo.")
            
            else:
                # La cola ESTÁ pausada por el usuario. No hacer nada.
                print("INFO: Auto-descargar: La cola está pausada por el usuario, no se reanudará.")
                self.progress_label.configure(text=f"Cola pausada. {len(self.job_widgets)} trabajos en espera.")

        else:
            self.progress_label.configure(text=f"Análisis completado. Presiona 'Iniciar Cola' para empezar.")

    def _on_batch_config_change(self, event=None):
        """
        MODIFICADO: Verifica el flag antes de guardar para evitar recursión.
        """
        if self._updating_ui:
            return
            
        if not self.selected_job_id:
            return
            
        job = self.queue_manager.get_job_by_id(self.selected_job_id)
        if not job:
            return
            
        # Guardar los valores de la UI en el diccionario 'config' del Job
        job.config['title'] = self.title_entry.get()
        job.config['mode'] = self.mode_selector.get()
        job.config['video_format_label'] = self.video_quality_menu.get()
        job.config['audio_format_label'] = self.audio_quality_menu.get()
        job.config['download_thumbnail'] = self.auto_save_thumbnail_check.get()  # ← NUEVO