import customtkinter as ctk
import threading
import os
from tkinter import StringVar, Menu
from customtkinter import filedialog
from src.core.batch_processor import QueueManager, Job
import sys
import yt_dlp
import io
import time

from tkinter import StringVar, Menu 
from customtkinter import filedialog
from contextlib import redirect_stdout

from src.core.exceptions import UserCancelledError 
from src.core.downloader import get_video_info
from src.core.batch_processor import Job
from .dialogs import Tooltip, messagebox 

import requests
from PIL import Image
from io import BytesIO

try:
    from tkinterdnd2 import DND_FILES
except ImportError:
    print("ERROR: tkinterdnd2 no encontrado en batch_tab")
    DND_FILES = None


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
    PROCESS_BTN_COLOR = "#6F42C1"        
    PROCESS_BTN_HOVER = "#59369A"
    CANCEL_BTN_COLOR = "#DC3545"
    CANCEL_BTN_HOVER = "#C82333"
    DISABLED_TEXT_COLOR = "#D3D3D3"
    DISABLED_FG_COLOR = "#565b5f"
    
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.pack(expand=True, fill="both")
        
        self.app = app
        self.is_initializing = True
        self.last_download_path = None
        self.thumbnail_label = None
        self.current_thumbnail_url = None
        self.current_raw_thumbnail = None

        self.job_widgets = {}

        self.selected_job_id: str | None = None
        self.current_video_formats: dict = {}
        self.current_audio_formats: dict = {}
        self.thumbnail_cache = {}

        self.combined_variants = {}  # Para variantes multiidioma
        self.combined_audio_map = {}  # Mapeo de idiomas seleccionados
        self.has_video_streams = False
        self.has_audio_streams = False

        # NUEVO: Flag para saber si estamos en modo recodificación local
        self.is_local_mode = False
        
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
        self._initialize_ui_settings()

    def _create_widgets(self):
        """Crea los componentes visuales de la pestaña."""
        
        # --- 1. Panel de Entrada (URL y Botones) ---
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.input_frame, text="URL:").grid(row=0, column=0, padx=(10, 5), pady=0)
        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Pega una URL de video o playlist...")
        self.url_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.url_entry)) # <-- AÑADIR ESTA LÍNEA
        self.url_entry.bind("<Return>", lambda event: self._on_analyze_click())
        self.url_entry.grid(row=0, column=1, padx=5, pady=0, sticky="ew")

        self.analyze_button = ctk.CTkButton(self.input_frame, text="Analizar", width=100, command=self._on_analyze_click)
        self.analyze_button.grid(row=0, column=2, padx=5, pady=0)
        # ✅ CAMBIO: El comando ahora abre un menú de opciones
        self.import_button = ctk.CTkButton(
            self.input_frame, 
            text="Importar ▼", # Indicador visual de menú
            width=100, 
            state="normal", 
            command=self._show_import_menu # Nueva función
        )
        self.import_button.grid(row=0, column=3, padx=(0, 10), pady=0)

        import_tooltip_text = "Activa el modo de recodificación local.\nPermite seleccionar múltiples archivos de video/audio de tu PC para añadirlos a la cola y procesarlos."
        Tooltip(self.import_button, import_tooltip_text, delay_ms=1000)

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

        # LÍNEA 1: Opciones Globales Fila 1 (Usada)
        global_line1_frame = ctk.CTkFrame(self.global_options_frame, fg_color="transparent")
        global_line1_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(3, 0))
        
        self.playlist_analysis_check = ctk.CTkCheckBox(
            global_line1_frame, 
            text="Análisis de Playlist",
            onvalue=True,
            offvalue=False,
            command=self.save_settings
        )
        self.playlist_analysis_check.pack(side="left", padx=5) 
        self.playlist_analysis_check.select() # Marcada por defecto

        playlist_tooltip_text = "Activado: Analiza la playlist/colección completa.\nDesactivado: Analiza solo el video individual de la URL."
        Tooltip(self.playlist_analysis_check, playlist_tooltip_text, delay_ms=1000)

        # Dejamos un espacio de 15px a la izq. (15 + 5 del anterior = 20px de separación)
        ctk.CTkLabel(global_line1_frame, text="Aplicar Modo Global:").pack(side="left", padx=(15, 5)) 
        
        self.global_mode_var = StringVar(value="Video+Audio")
        
        self.global_mode_menu = ctk.CTkOptionMenu(
            global_line1_frame, 
            values=["Video+Audio", "Solo Audio"],
            width=140,
            variable=self.global_mode_var,
            command=self._on_apply_global_mode # <--- Nueva función
        )
        self.global_mode_menu.pack(side="left", padx=5)

        # LÍNEA 2: Opciones Globales Fila 2 (Espacio futuro)
        global_line2_frame_placeholder = ctk.CTkFrame(self.global_options_frame, fg_color="transparent", height=10)
        global_line2_frame_placeholder.grid(row=2, column=0, sticky="ew", padx=5, pady=0)
        # (Este frame está vacío a propósito para futuros agregados)

        # LÍNEA 3: Radio buttons de miniaturas
        global_line3_frame = ctk.CTkFrame(self.global_options_frame, fg_color="transparent")
        global_line3_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=(0, 3))

        thumbnail_label = ctk.CTkLabel(global_line3_frame, text="Miniaturas:", font=ctk.CTkFont(weight="bold"))
        thumbnail_label.pack(side="left", padx=(5, 5))

        thumbnail_tooltip_text = "Controla cómo se deben descargar las miniaturas para todos los ítems de la cola."
        Tooltip(thumbnail_label, thumbnail_tooltip_text, delay_ms=1000)

        self.thumbnail_mode_var = StringVar(value="normal")

        self.radio_normal = ctk.CTkRadioButton(
            global_line3_frame, 
            text="Modo Manual", 
            variable=self.thumbnail_mode_var, 
            value="normal",
            command=self._on_thumbnail_mode_change
        )
        self.radio_normal.pack(side="left", padx=5)

        self.radio_with_thumbnail = ctk.CTkRadioButton(
            global_line3_frame, 
            text="Con video/audio", 
            variable=self.thumbnail_mode_var, 
            value="with_thumbnail",
            command=self._on_thumbnail_mode_change
        )
        self.radio_with_thumbnail.pack(side="left", padx=5)

        self.radio_only_thumbnail = ctk.CTkRadioButton(
            global_line3_frame, 
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

        # --- INICIO DE MODIFICACIÓN ---
        # Asignar peso a las columnas para que los botones se repartan
        self.queue_actions_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.clear_list_button = ctk.CTkButton(
            self.queue_actions_frame, 
            text="Limpiar Lista", 
            height=24,
            font=ctk.CTkFont(size=12),
            command=self._on_clear_list_click,
            # width=120 # Opcional: ancho fijo
        )
        self.clear_list_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.reset_status_button = ctk.CTkButton(
            self.queue_actions_frame, 
            text="Resetear Estado", 
            height=24,
            font=ctk.CTkFont(size=12),
            command=self._on_reset_status_click,
            # width=120 # Opcional: ancho fijo
        )
        self.reset_status_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # 1. Crear el nuevo frame en la columna derecha
        self.global_recode_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.global_recode_frame.grid(row=2, column=1, padx=(5, 10), pady=(0, 0), sticky="e")
        
        # 2. El Checkbox
        self.global_recode_checkbox = ctk.CTkCheckBox(
            self.global_recode_frame,
            text="Recodificación Global:",
            command=self._on_global_recode_toggle,
            state="disabled" # <-- AÑADIR ESTO
        )
        self.global_recode_checkbox.pack(side="left", padx=(0, 5))

        global_recode_tooltip = "Activa la recodificación para TODOS los ítems de la cola.\nEsto anula la configuración individual de cada ítem y aplica el mismo preset (seleccionado a la derecha) a todos."
        Tooltip(self.global_recode_checkbox, global_recode_tooltip, delay_ms=1000)
                        
        # 4. El Menú de Presets (AHORA VISIBLE Y DESHABILITADO)
        self.global_recode_preset_menu = ctk.CTkOptionMenu(
            self.global_recode_frame,
            values=["-"],
            width=200,
            state="disabled", 
            command=self._apply_global_recode_settings
        )
        self.global_recode_preset_menu.pack(side="left", padx=(0, 5))

        # --- 4. Panel de Cola (IZQUIERDA) ---
        self.queue_scroll_frame = ctk.CTkScrollableFrame(
            self, 
            fg_color="#1D1D1D", 
            border_width=1, 
            border_color="#565B5E"
        )
        self.queue_scroll_frame.grid(row=3, column=0, padx=(10, 5), pady=(0, 10), sticky="nsew")
        
        self.queue_placeholder_label = ctk.CTkLabel(
            self.queue_scroll_frame, 
            text="Arrastra videos/carpetas aquí\no pega una URL arriba", 
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.queue_placeholder_label.pack(expand=True, pady=50, padx=20)

        # ✅ SOLUCIÓN DRAG & DROP BLOQUEADO
        if DND_FILES:
            try:
                # 1. Registrar el marco principal
                self.queue_scroll_frame.drop_target_register(DND_FILES)
                self.queue_scroll_frame.dnd_bind('<<Drop>>', self._on_batch_drop)
                
                # 2. CRÍTICO: Registrar el CANVAS INTERNO (donde realmente ocurre el drop)
                # En CTk, el canvas se llama _parent_canvas
                self.queue_scroll_frame._parent_canvas.drop_target_register(DND_FILES)
                self.queue_scroll_frame._parent_canvas.dnd_bind('<<Drop>>', self._on_batch_drop)
                
                # 3. Registrar la etiqueta de texto (Empty State)
                self.queue_placeholder_label.drop_target_register(DND_FILES)
                self.queue_placeholder_label.dnd_bind('<<Drop>>', self._on_batch_drop)
                
                print("DEBUG: Drag & Drop activado en TODAS las capas de la cola")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo activar DnD en lotes: {e}")
        
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
        self.title_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.title_entry)) # <-- AÑADIR ESTA LÍNEA
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

        self.batch_use_all_audio_tracks_check = ctk.CTkCheckBox(
            self.audio_options_frame, 
            text="Recodificar todas las pistas",
            command=self._on_batch_use_all_audio_tracks_change
        )
        
        multi_track_tooltip_text = "Aplica la recodificación seleccionada a TODAS las pistas de audio por separado (no las fusiona).\n\n• Advertencia: Esta función depende del formato de salida. No todos los contenedores (ej: `.mp3`) admiten audio multipista."
        Tooltip(self.batch_use_all_audio_tracks_check, multi_track_tooltip_text, delay_ms=1000)
        # No lo empaquetamos (pack) aquí, se hará dinámicamente
        # --- FIN DE LA ADICIÓN ---

        self.audio_options_frame.pack(fill="x", pady=0, padx=0)

        # --- 5b. Panel Inferior (Recodificación) ---
        self.recode_main_scrollframe = ctk.CTkScrollableFrame(self.config_panel, label_text="Opciones de Recodificación")
        self.recode_main_scrollframe.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
                
        self.recode_main_scrollframe.grid_columnconfigure(0, weight=1)
        
        # NOTA: Usamos nombres de variables prefijados con "batch_" para evitar conflictos
        
        self.batch_apply_quick_preset_checkbox = ctk.CTkCheckBox(
            self.recode_main_scrollframe, 
            text="Activar Recodificación", 
            command=self._on_batch_quick_recode_toggle_and_save,
        )
        self.batch_apply_quick_preset_checkbox.pack(anchor="w", padx=10, pady=(5, 5))
        self.batch_apply_quick_preset_checkbox.deselect()
        
        self.batch_quick_recode_options_frame = ctk.CTkFrame(self.recode_main_scrollframe, fg_color="transparent")
        # Por defecto está oculto, _on_batch_quick_recode_toggle lo mostrará

        # 1. Checkbox "Mantener originales" (AHORA VA PRIMERO)
        self.batch_keep_original_quick_checkbox = ctk.CTkCheckBox(
            self.batch_quick_recode_options_frame, 
            text="Mantener los archivos originales",
            command=self._on_batch_config_change # Usamos la función de guardado
        )
        self.batch_keep_original_quick_checkbox.pack(anchor="w", padx=10, pady=(0, 5))
        self.batch_keep_original_quick_checkbox.select()

        # 2. Etiqueta del Preset
        preset_label = ctk.CTkLabel(self.batch_quick_recode_options_frame, text="Preset de Conversión:", font=ctk.CTkFont(weight="bold"))
        preset_label.pack(pady=10, padx=10)

        preset_tooltip_text = "Perfiles pre-configurados para tareas comunes.\n\n• Puedes crear y guardar tus propios presets desde el 'Modo Manual' de la pestaña 'Proceso Único'.\n• Tus presets guardados aparecerán aquí."
        Tooltip(preset_label, preset_tooltip_text, delay_ms=1000)

        # 3. Menú del Preset
        self.batch_recode_preset_menu = ctk.CTkOptionMenu(
            self.batch_quick_recode_options_frame, 
            values=["-"], 
            command=self._on_batch_preset_change_and_save # <-- CAMBIO DE FUNCIÓN
        )
        self.batch_recode_preset_menu.pack(pady=10, padx=10, fill="x")

        Tooltip(self.batch_recode_preset_menu, preset_tooltip_text, delay_ms=1000)

        # 4. Botones de Importar/Exportar/Eliminar (NUEVOS)
        batch_preset_actions_frame = ctk.CTkFrame(self.batch_quick_recode_options_frame, fg_color="transparent")
        batch_preset_actions_frame.pack(fill="x", padx=10, pady=(0, 10))
        batch_preset_actions_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.batch_import_preset_button = ctk.CTkButton(
            batch_preset_actions_frame,
            text="📥 Importar",
            command=self.app.single_tab.import_preset_file, # <-- Llama a la función de single_tab
            fg_color="#28A745",
            hover_color="#218838"
        )
        self.batch_import_preset_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.batch_export_preset_button = ctk.CTkButton(
            batch_preset_actions_frame,
            text="📤 Exportar",
            command=self.app.single_tab.export_preset_file, # <-- Llama a la función de single_tab
            state="disabled",
            fg_color="#007BFF",
            hover_color="#0069D9"
        )
        self.batch_export_preset_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.batch_delete_preset_button = ctk.CTkButton(
            batch_preset_actions_frame,
            text="🗑️ Eliminar",
            command=self.app.single_tab.delete_preset_file, # <-- Llama a la función de single_tab
            state="disabled",
            fg_color="#DC3545",
            hover_color="#C82333"
        )
        self.batch_delete_preset_button.grid(row=0, column=2, padx=(5, 0), sticky="ew")
        # --- FIN DE LA REORDENACIÓN Y ADICIÓN ---
                
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
        
        # Comprobar si el path por defecto es válido para habilitar el botón
        self.open_folder_button = ctk.CTkButton(
            line1_frame, text="📁", width=40, font=ctk.CTkFont(size=16), 
            command=self._open_batch_output_folder,
            state="disabled" 
        )
        self.open_folder_button.grid(row=0, column=3, padx=(0, 5), pady=5)
        
        # Asignar la etiqueta a una variable para añadirle el tooltip
        speed_label = ctk.CTkLabel(line1_frame, text="Límite (MB/s):")
        speed_label.grid(row=0, column=4, padx=(10, 5), pady=5, sticky="w")
        
        self.speed_limit_entry = ctk.CTkEntry(line1_frame, width=50)
        
        # --- AÑADIR TOOLTIP (2000ms = 2 segundos) ---
        tooltip_text = "Limita la velocidad de descarga (en MB/s).\nÚtil si las descargas fallan por 'demasiadas peticiones'."
        Tooltip(speed_label, tooltip_text, delay_ms=1000)
        Tooltip(self.speed_limit_entry, tooltip_text, delay_ms=1000)
        # --- FIN TOOLTIP ---
        
        self.speed_limit_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.speed_limit_entry))
        self.speed_limit_entry.grid(row=0, column=5, padx=(0, 10), pady=5)
        
        line2_frame = ctk.CTkFrame(self.download_frame, fg_color="transparent")
        line2_frame.pack(fill="x", padx=0, pady=0)
        line2_frame.grid_columnconfigure(5, weight=1)
        
        # --- MODIFICACIÓN: Asignar la etiqueta a una variable ---
        conflict_label = ctk.CTkLabel(line2_frame, text="Si existe:")
        conflict_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        # --- FIN DE LA MODIFICACIÓN ---

        self.conflict_policy_menu = ctk.CTkOptionMenu(
            line2_frame, 
            width=100,
            values=["Sobrescribir", "Renombrar", "Omitir"]
        )
        self.conflict_policy_menu.set("Renombrar") 
        self.conflict_policy_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")

        # --- AÑADIR ESTAS LÍNEAS (TOOLTIP 3) ---
        conflict_tooltip_text = "Determina qué hacer si un archivo con el mismo nombre ya existe:\n• Sobrescribir: Reemplaza el archivo antiguo.\n• Renombrar: Guarda como 'archivo (1).mp4'.\n• Omitir: Salta la descarga de este ítem."
        Tooltip(conflict_label, conflict_tooltip_text, delay_ms=1000)
        Tooltip(self.conflict_policy_menu, conflict_tooltip_text, delay_ms=1000)
        # --- FIN DEL TOOLTIP ---
        
        self.create_subfolder_checkbox = ctk.CTkCheckBox(
            line2_frame, 
            text="Crear carpeta", 
            command=self._toggle_subfolder_name_entry
        )

        self.create_subfolder_checkbox.grid(row=0, column=2, padx=(5, 5), pady=5, sticky="w")
        
        # --- AÑADIR ESTAS LÍNEAS (TOOLTIP 5) ---
        subfolder_tooltip_text = "Guarda todos los archivos en una subcarpeta.\nSe puede poner un nombre personalizado, pero si se deja vacío, el nombre será 'DowP List'.\nSi el nombre ya existe (ej: 'DowP List'), se creará una nueva (ej: 'DowP List 01')."
        Tooltip(self.create_subfolder_checkbox, subfolder_tooltip_text, delay_ms=1000)
        # --- FIN DEL TOOLTIP ---

        self.subfolder_name_entry = ctk.CTkEntry(line2_frame, width=100, placeholder_text="DowP List")
        self.subfolder_name_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.subfolder_name_entry))
        self.subfolder_name_entry.grid(row=0, column=3, padx=(0, 10), pady=5, sticky="w")
        self.subfolder_name_entry.configure(state="disabled")
        
        self.auto_download_checkbox = ctk.CTkCheckBox(line2_frame, text="Auto-descarga")
        self.auto_download_checkbox.grid(row=0, column=4, padx=5, pady=5, sticky="w")

        auto_tooltip_text = "Si está activo, la cola comenzará a descargarse automáticamente después de que el análisis de una URL finalice."
        Tooltip(self.auto_download_checkbox, auto_tooltip_text, delay_ms=1000)
        
        self.auto_import_checkbox = ctk.CTkCheckBox(
            line2_frame, 
            text="Import Adobe", 
            command=self.save_settings,
            text_color="#FFC792",       
            fg_color="#C17B42",         
            hover_color="#9A6336"        
        )
        self.auto_import_checkbox.grid(row=0, column=5, padx=5, pady=5, sticky="w")
        import_tooltip_text = "Habilita la importación automática de los archivos descargados a Premiere Pro y After Effects."
        Tooltip(self.auto_import_checkbox, import_tooltip_text, delay_ms=1000)
        
        self.start_queue_button = ctk.CTkButton(
            line2_frame, text="Iniciar Cola", state="disabled", command=self.start_queue_processing, 
            fg_color=self.DOWNLOAD_BTN_COLOR, hover_color=self.DOWNLOAD_BTN_HOVER, 
            text_color_disabled=self.DISABLED_TEXT_COLOR, width=120
        )
        self.start_queue_button.grid(row=0, column=6, padx=(5, 10), pady=5, sticky="e") 

        # --- 7. Panel de Progreso ---
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Esperando para iniciar la cola...")
        self.progress_label.pack(pady=(5,0))
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0,5), padx=10, fill="x")

        # --- Carga Inicial ---
        # 1. Intentar cargar la ruta específica de Lotes
        batch_path = self.app.batch_download_path
        
        # 2. Si está vacía, intentar usar la ruta de la pestaña Única (como fallback)
        if not batch_path:
            batch_path = self.app.default_download_path

        if batch_path:
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, batch_path)
        else:
            # Fallback a la carpeta de Descargas si AMBAS están vacías
            try:
                from pathlib import Path # Importar aquí para uso local
                downloads_path = Path.home() / "Downloads"
                if downloads_path.exists() and downloads_path.is_dir():
                    self.output_path_entry.delete(0, 'end')
                    self.output_path_entry.insert(0, str(downloads_path))
                    # Actualizar el path global para que se guarde al cerrar
                    self.app.batch_download_path = str(downloads_path) # <-- Guardar en la variable correcta
            except Exception as e:
                print(f"No se pudo establecer la carpeta de descargas por defecto para Lotes: {e}")

        # --- Habilitar el botón si la ruta final es válida ---
        final_path = self.output_path_entry.get()
        if final_path and os.path.isdir(final_path):
            self.open_folder_button.configure(state="normal")

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
            self.batch_apply_quick_preset_checkbox,
            self.batch_recode_preset_menu,
            self.batch_keep_original_quick_checkbox
        ]
        
        for widget in widgets_to_toggle:
            if widget: 
                widget.configure(state=state)
         
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
        Ahora maneja correctamente formatos multiidioma.
        """
        selected_format_info = self.current_video_formats.get(selected_label)
        
        if selected_format_info:
            is_combined = selected_format_info.get('is_combined', False)
            quality_key = selected_format_info.get('quality_key')
            
            # 🔧 MODIFICADO: Solo llenar el menú de audio si hay variantes REALES
            if is_combined and quality_key and quality_key in self.combined_variants:
                variants = self.combined_variants[quality_key]
                
                # 🆕 NUEVO: Verificar que realmente hay múltiples idiomas
                unique_languages = set()
                for variant in variants:
                    lang = variant.get('language', '')
                    if lang:
                        unique_languages.add(lang)
                
                # 🔧 CRÍTICO: Solo crear menú de idiomas si hay 2+ idiomas diferentes
                if len(unique_languages) >= 2:
                    # Crear opciones de idioma para el menú de audio
                    audio_language_options = []
                    self.combined_audio_map = {}
                    
                    for variant in variants:
                        lang_code = variant.get('language')
                        format_id = variant.get('format_id')
                        
                        if lang_code:
                            norm_code = lang_code.replace('_', '-').lower()
                            lang_name = self.app.LANG_CODE_MAP.get(
                                norm_code,
                                self.app.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code)
                            )
                        else:
                            continue
                        
                        abr = variant.get('abr') or variant.get('tbr')
                        acodec = variant.get('acodec', 'unknown').split('.')[0]
                        
                        label = f"{lang_name} - {abr:.0f}kbps ({acodec})" if abr else f"{lang_name} ({acodec})"
                        
                        if label not in self.combined_audio_map:
                            audio_language_options.append(label)
                            self.combined_audio_map[label] = format_id
                    
                    if not audio_language_options:
                        self.audio_quality_menu.configure(state="disabled")
                        self.combined_audio_map = {}
                    else:
                        # Ordenar por prioridad de idioma
                        def sort_by_lang_priority(label):
                            for variant in variants:
                                if self.combined_audio_map.get(label) == variant.get('format_id'):
                                    lang_code = variant.get('language', '')
                                    norm_code = lang_code.replace('_', '-').lower()
                                    return self.app.LANGUAGE_ORDER.get(
                                        norm_code,
                                        self.app.LANGUAGE_ORDER.get(norm_code.split('-')[0], self.app.DEFAULT_PRIORITY)
                                    )
                            return self.app.DEFAULT_PRIORITY
                        
                        audio_language_options.sort(key=sort_by_lang_priority)
                        
                        self.audio_quality_menu.configure(state="normal", values=audio_language_options)
                        self.audio_quality_menu.set(audio_language_options[0])
                else:
                    # 🆕 NUEVO: Solo hay un idioma o ninguno, deshabilitar el menú
                    self.audio_quality_menu.configure(state="disabled")
                    self.combined_audio_map = {}
                    print(f"DEBUG: Combinado de un solo idioma detectado (quality_key: {quality_key})")
            else:
                # 🆕 CRÍTICO: Este else faltaba - restaurar el menú de audio normal
                print(f"DEBUG: No es combinado multiidioma, restaurando menú de audio normal")
                self.combined_audio_map = {}
                
                # Restaurar las opciones de audio originales
                a_opts = list(self.current_audio_formats.keys()) or ["-"]
                
                # --- INICIO DE LA MODIFICACIÓN (FIX DEL RESETEO) ---
                
                # 1. Obtener la selección de audio ACTUAL (la que eligió el usuario)
                current_audio_selection = self.audio_quality_menu.get()
                
                # 2. Buscar la mejor opción por defecto (fallback)
                default_audio_selection = a_opts[0]
                for option in a_opts:
                    if "✨" in option:
                        default_audio_selection = option
                        break
                        
                # 3. Decidir qué selección usar
                selection_to_set = default_audio_selection # Usar el fallback por defecto
                if current_audio_selection in a_opts:
                    selection_to_set = current_audio_selection # ¡Ahá! Mantener la del usuario
                
                self.audio_quality_menu.configure(
                    state="normal" if self.current_audio_formats else "disabled",
                    values=a_opts
                )
                self.audio_quality_menu.set(selection_to_set) # <-- Usar la selección decidida
                # --- FIN DE LA MODIFICACIÓN ---

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

    def _on_batch_use_all_audio_tracks_change(self):
        """Gestiona el estado del menú de audio cuando el checkbox multipista cambia."""
        if self.batch_use_all_audio_tracks_check.get() == 1:
            self.audio_quality_menu.configure(state="disabled")
        else:
            self.audio_quality_menu.configure(state="normal")
        
        # Guardar el estado en el job actual
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

        self._populate_batch_preset_menu()

    def update_job_ui(self, job_id: str, status: str, message: str, progress_percent: float = 0.0):
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
        
        if job_id == "GLOBAL_PROGRESS":
            if status == "UPDATE":
                self.progress_label.configure(text=message)
                self.progress_bar.set(progress_percent)
            elif status == "RESET":
                self.progress_label.configure(text=message)
                self.progress_bar.set(0)
            return

        job_frame = self.job_widgets.get(job_id)

        if not job_frame:
            job_frame = ctk.CTkFrame(self.queue_scroll_frame, border_width=1, border_color="#555")
            job_frame.pack(fill="x", padx=5, pady=(0, 5))
            
            job_frame.grid_columnconfigure(0, weight=1)
            job_frame.grid_columnconfigure(1, weight=0)  # Carpeta
            job_frame.grid_columnconfigure(2, weight=0)  # Reset
            job_frame.grid_columnconfigure(3, weight=0)  # Cerrar
            
            job_frame.title_label = ctk.CTkLabel(job_frame, text=message, anchor="w", wraplength=400)


            job_frame.title_label.grid(row=0, column=0, padx=10, pady=(5,0), sticky="ew")
            
            job_frame.status_label = ctk.CTkLabel(job_frame, text="Pendiente...", anchor="w", text_color="gray", font=ctk.CTkFont(size=11))
            job_frame.status_label.grid(row=1, column=0, padx=10, pady=(0,5), sticky="ew")

            job_frame.progress_bar = ctk.CTkProgressBar(job_frame, height=4)
            job_frame.progress_bar.set(0)
            job_frame.progress_bar.grid(row=2, column=0, columnspan=4, padx=10, pady=(0, 2), sticky="ew")  # ✅ columnspan=4
            job_frame.progress_bar.grid_remove()

            # ✅ NUEVO: Botón de carpeta (oculto por defecto)
            job_frame.folder_button = ctk.CTkButton(
                job_frame, text="📂", width=28, height=28,
                font=ctk.CTkFont(size=14),
                fg_color="transparent", hover_color="#555",
                command=lambda jid=job_id: self._open_job_folder(jid)
            )
            job_frame.folder_button.grid(row=0, column=1, rowspan=2, padx=(0, 0), pady=5)
            job_frame.folder_button.grid_remove()

            job_frame.restore_button = ctk.CTkButton(
                job_frame, text="◁", width=28, height=28,
                font=ctk.CTkFont(size=16),
                fg_color="transparent", hover_color="#555",
                command=lambda jid=job_id: self._on_reset_single_job(jid)
            )
            job_frame.restore_button.grid(row=0, column=2, rowspan=2, padx=(0, 0), pady=5)
            job_frame.restore_button.grid_remove()

            job_frame.close_button = ctk.CTkButton(
                job_frame, text="⨉", width=28, height=28, 
                fg_color="transparent", hover_color="#555",
                command=lambda jid=job_id: self._remove_job(jid)
            )
            job_frame.close_button.grid(row=0, column=3, rowspan=2, padx=(0, 5), pady=5)
            
            job_frame.bind("<Button-1>", lambda e, jid=job_id: self._on_job_select(jid))

            
            job_frame.title_label.bind("<Button-1>", lambda e, jid=job_id: self._on_job_select(jid))
            job_frame.status_label.bind("<Button-1>", lambda e, jid=job_id: self._on_job_select(jid))

            self.job_widgets[job_id] = job_frame
            return

        if status == "RUNNING":
            job_frame.title_label.configure(text_color="white")
            job_frame.status_label.configure(text=message, text_color="#52a2f2") 
            job_frame.progress_bar.grid() 
            if "..." in message and "%" in message:
                try:
                    # Extraer el "XX.X" (funciona para "Descargando..." y "Recodificando...")
                    percent_str = message.split("...")[1].split("%")[0].strip()
                    percent_float = float(percent_str) / 100.0
                    job_frame.progress_bar.set(percent_float)
                except (ValueError, IndexError):
                    # Falló el parseo, pero es un mensaje de progreso
                    job_frame.progress_bar.set(0)
            else:
                 # El mensaje no es de progreso (ej: "Iniciando...", "Fusionando...")
                 job_frame.progress_bar.set(0)

        elif status == "COMPLETED":
            job_frame.title_label.configure(text_color="#90EE90")
            job_frame.status_label.configure(text=message, text_color="#28A745") 
            job_frame.progress_bar.set(1)
            job_frame.progress_bar.grid()
            job_frame.folder_button.grid()  # ✅ Mostrar botón de carpeta
            job_frame.restore_button.grid()

        elif status == "SKIPPED": # <-- BLOQUE NUEVO
            job_frame.title_label.configure(text_color="#FFA500") # Naranja
            job_frame.status_label.configure(text=message, text_color="#FF8C00") # Naranja oscuro
            job_frame.progress_bar.set(0)
            job_frame.progress_bar.grid_remove()
            job_frame.restore_button.grid()

        elif status == "NO_AUDIO":
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

    def _open_job_folder(self, job_id: str):
        """Abre la carpeta y selecciona el archivo de un job específico."""
        job = self.queue_manager.get_job_by_id(job_id)
        
        if not job or not job.final_filepath or not os.path.exists(job.final_filepath):
            print(f"ERROR: No se encontró archivo para job {job_id}")
            return
        
        file_path = os.path.normpath(job.final_filepath)
        
        try:
            import subprocess
            import platform
            
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(['explorer', '/select,', file_path])
            elif system == "Darwin":
                subprocess.Popen(['open', '-R', file_path])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(file_path)])
            
            print(f"INFO: Abriendo: {file_path}")
        except Exception as e:
            print(f"ERROR al abrir carpeta: {e}")

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
            # ✅ RESTAURAR TEXTO ORIGINAL
            self.queue_placeholder_label.configure(
                text="Arrastra videos/carpetas aquí\no pega una URL arriba"
            )
            
            self.queue_placeholder_label.pack(expand=True, pady=50, padx=20)
            self.start_queue_button.configure(state="disabled")
            self.progress_label.configure(text="Cola vacía. Analiza una URL para empezar.")

            self.global_recode_checkbox.configure(state="disabled")
            self.global_recode_preset_menu.configure(state="disabled")
            self.global_recode_checkbox.deselect()

    def _on_job_select(self, job_id: str):
        """MODIFICADO: Previene actualizaciones recursivas y CARGA LA MINIATURA."""
        if job_id == self.selected_job_id:
            return

        # Guardar el job anterior usando la función de guardado correcta
        if self.selected_job_id and not self._updating_ui:
            print(f"DEBUG: Guardando config del job anterior ({self.selected_job_id[:6]}) al deseleccionar...")
            self._on_batch_config_change()

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
        
        # 🆕 CRÍTICO: Cargar la miniatura del job seleccionado
        if job.job_type == "LOCAL_RECODE":
            local_path = job.config.get('local_file_path')
            # Solo cargar si tiene stream de video
            if job.analysis_data.get('local_info', {}).get('video_stream'):
                print(f"DEBUG: Cargando fotograma local para job {job_id}...")
                # Llamamos a load_thumbnail con la ruta local
                threading.Thread(target=self.load_thumbnail, args=(local_path, True), daemon=True).start()
            else:
                # Es un archivo de solo audio
                self.create_placeholder_label(self.thumbnail_container, "🎵", font_size=60)
                
        else: # Es un trabajo de DESCARGA (lógica original)
            thumbnail_url = job.analysis_data.get('thumbnail')
            if thumbnail_url:
                print(f"DEBUG: Cargando miniatura para job {job_id}: {thumbnail_url[:60]}...")
                # Llamamos a load_thumbnail con la URL
                threading.Thread(target=self.load_thumbnail, args=(thumbnail_url, False), daemon=True).start()
            else:
                # Si no hay miniatura, mostrar placeholder apropiado
                formats = job.analysis_data.get('formats', [])
                has_audio_only = any(
                    self._classify_format(f) == 'AUDIO' for f in formats
                ) and not any(
                    self._classify_format(f) in ['VIDEO', 'VIDEO_ONLY'] for f in formats
                )
                
                if has_audio_only:
                    self.create_placeholder_label(self.thumbnail_container, "🎵", font_size=60)
                else:
                    self.create_placeholder_label(self.thumbnail_container, "Miniatura")
        
    def _populate_config_panel(self, job: Job):
        """
        MODIFICADO: Usa el flag _updating_ui para prevenir eventos recursivos.
        """
        # ACTIVAR FLAG para prevenir actualizaciones durante la población
        self._updating_ui = True
        
        try:
            
            if job.job_type == "LOCAL_RECODE":
                print("DEBUG: Llenando panel para trabajo LOCAL_RECODE.")
                
                info = job.analysis_data
                local_info = info.get('local_info', {})
                video_stream = local_info.get('video_stream')
                audio_streams = local_info.get('audio_streams', [])
                format_info = local_info.get('format', {})
                
                # --- 1. Título ---
                self.title_entry.delete(0, 'end')
                self.title_entry.insert(0, info.get('title', 'archivo_local'))
                
                # --- 2. Thumbnail (CORREGIDO) ---
                # (Esta lógica faltaba y solo se ejecutaba en _on_job_select)
                local_path = job.config.get('local_file_path')
                if video_stream:
                    # Usamos print para ver el refresco en el log
                    print(f"DEBUG: (Re)cargando fotograma local para job {job.job_id[:6]}...")
                    # Volver a lanzar el hilo de carga de miniatura
                    threading.Thread(target=self.load_thumbnail, args=(local_path, True), daemon=True).start()
                else:
                    # Si no hay video, mostrar el ícono de música
                    self.create_placeholder_label(self.thumbnail_container, "🎵", font_size=60)
                
                # --- 3. Menús de Formato (Lógica copiada de single_tab) ---
                video_labels = ["- Sin Video -"]
                self.current_video_formats = {}
                if video_stream:
                    v_codec = video_stream.get('codec_name', 'N/A').upper()
                    v_profile = video_stream.get('profile', 'N/A')
                    v_level = video_stream.get('level')
                    full_profile = f"{v_profile}@L{float(v_level) / 10.0:.1f}" if v_level else v_profile
                    v_resolution = f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}"
                    v_fps = self._format_fps(video_stream.get('r_frame_rate'))
                    v_bitrate = self._format_bitrate(video_stream.get('bit_rate') or format_info.get('bit_rate'))
                    v_pix_fmt = video_stream.get('pix_fmt', 'N/A')
                    bit_depth = "10-bit" if any(x in v_pix_fmt for x in ['p10', '10le']) else "8-bit"
                    color_range = video_stream.get('color_range', '').capitalize()
                    
                    v_label = f"{v_resolution} | {v_codec} ({full_profile}) @ {v_fps} fps | {v_bitrate} | {v_pix_fmt} ({bit_depth}, {color_range})"
                    video_labels = [v_label]
                    # Guardamos el stream de ffprobe. El procesador de recodificación lo leerá.
                    self.current_video_formats[v_label] = video_stream 
                
                audio_labels = ["- Sin Audio -"]
                self.current_audio_formats = {}
                if audio_streams:
                    audio_labels = []
                    for stream in audio_streams:
                        idx = stream.get('index', '?')
                        title = stream.get('tags', {}).get('title', f"Pista {idx}")
                        is_default = stream.get('disposition', {}).get('default', 0) == 1
                        default_str = " (Default)" if is_default else ""
                        a_codec = stream.get('codec_name', 'N/A').upper()
                        a_profile = stream.get('profile', 'N/A')
                        a_channels_num = stream.get('channels', '?')
                        a_channel_layout = stream.get('channel_layout', 'N/A')
                        a_channels = f"{a_channels_num} Canales ({a_channel_layout})"
                        a_sample_rate = f"{int(stream.get('sample_rate', 0)) / 1000:.1f} kHz"
                        a_bitrate = self._format_bitrate(stream.get('bit_rate'))
                        
                        a_label = f"{title}{default_str}: {a_codec} ({a_profile}) | {a_sample_rate} | {a_channels} | {a_bitrate}"
                        audio_labels.append(a_label)
                        self.current_audio_formats[a_label] = stream
                
                # --- 4. Poblar Menús ---
                self.video_quality_menu.configure(state="normal" if video_stream else "disabled", values=video_labels)
                self.video_quality_menu.set(video_labels[0])
                
                self.audio_quality_menu.configure(state="normal" if audio_streams else "disabled", values=audio_labels)
                default_audio = next((l for l in audio_labels if "(Default)" in l), audio_labels[0])
                self.audio_quality_menu.set(default_audio)

                if len(audio_streams) > 1:
                    # Mostrar el checkbox
                    self.batch_use_all_audio_tracks_check.pack(padx=5, pady=(5,0), anchor="w")
                    
                    # Restaurar estado guardado
                    use_all_tracks = job.config.get('recode_all_audio_tracks', False)
                    if use_all_tracks:
                        self.batch_use_all_audio_tracks_check.select()
                        self.audio_quality_menu.configure(state="disabled")
                    else:
                        self.batch_use_all_audio_tracks_check.deselect()
                        self.audio_quality_menu.configure(state="normal")
                else:
                    # Ocultar el checkbox si solo hay 0 o 1 pista
                    self.batch_use_all_audio_tracks_check.pack_forget()
                    self.batch_use_all_audio_tracks_check.deselect()
                
                # --- 5. Modo Selector (CORREGIDO) ---
                
                # 1. Leer el modo guardado en el job (que fue establecido por la config global)
                saved_mode = job.config.get('mode', 'Video+Audio')
                
                # 2. Establecer el modo guardado PRIMERO
                self.mode_selector.set(saved_mode)
                
                # 3. Restringir la UI basado en el contenido real del archivo
                if not video_stream and audio_streams:
                    # Es un archivo de solo audio, forzar modo "Solo Audio"
                    self.mode_selector.set("Solo Audio")
                    self.mode_selector.configure(state="disabled", values=["Solo Audio"])
                elif video_stream:
                    # Tiene video, ambos modos son posibles, habilitar el selector
                    self.mode_selector.configure(state="normal", values=["Video+Audio", "Solo Audio"])
                else:
                    # No tiene ni video ni audio (¿archivo corrupto?)
                    self.mode_selector.set("Video+Audio")
                    self.mode_selector.configure(state="disabled", values=["Video+Audio"])
                
                # 4. Llamar a _on_item_mode_change CON EL VALOR FINAL
                self._on_item_mode_change(self.mode_selector.get())

                # --- 6. Opciones de Miniatura (Deshabilitadas para locales) ---
                self.auto_save_thumbnail_check.deselect()
                self.auto_save_thumbnail_check.configure(state="disabled")
                self.save_thumbnail_button.configure(state="normal" if video_stream else "disabled")

                # --- INICIO DE MODIFICACIÓN (Problemas 2 y 3) ---
                # (Lógica copiada de la sección "DOWNLOAD")
                
                # Restaurar estado de Recodificación Rápida del JOB
                is_recode_enabled = job.config.get('recode_enabled', False)
                is_keep_original = job.config.get('recode_keep_original', True)
    
                if is_recode_enabled:
                    self.batch_apply_quick_preset_checkbox.select()
                else:
                    self.batch_apply_quick_preset_checkbox.deselect()
    
                if is_keep_original:
                    self.batch_keep_original_quick_checkbox.select()
                else:
                    self.batch_keep_original_quick_checkbox.deselect()
    
                # Poblar el menú (esto también restaurará la selección)
                self._populate_batch_preset_menu()
                
                # Mostrar u ocultar el frame de opciones DIRECTAMENTE
                # Mostrar u ocultar el frame de opciones DIRECTAMENTE
                if is_recode_enabled:
                    self.batch_quick_recode_options_frame.pack(fill="x", padx=0, pady=0)
                    # Para modo local, la casilla siempre debe estar deshabilitada y seleccionada
                    self.batch_keep_original_quick_checkbox.select()
                    self.batch_keep_original_quick_checkbox.configure(state="disabled")
                else:
                    self.batch_quick_recode_options_frame.pack_forget()
                    self.batch_keep_original_quick_checkbox.configure(state="disabled")
                
                # Validar compatibilidad del preset con multipista
                self._validate_batch_recode_compatibility()
            
            # La lógica original para "DOWNLOAD" (yt-dlp) continúa aquí abajo
            else:
                info = job.analysis_data
            
                # Ocultar checkbox multipista (solo es para modo local)
                self.batch_use_all_audio_tracks_check.pack_forget()
            
                self.title_entry.delete(0, 'end')
                self.create_placeholder_label(self.thumbnail_container, "Cargando...")
                self.current_video_formats.clear()
                self.current_audio_formats.clear()
                
                # 🔧 LÓGICA SIMPLIFICADA Y ROBUSTA DE TÍTULO
                title = job.config.get('title', '').strip()
                
                # Solo buscar en info si el título está vacío o es un placeholder
                if not title or title in ['Analizando...', 'Sin título', '-']:
                    title = (info.get('title') or '').strip()
                
                # Fallback final solo si realmente no hay título
                if not title:
                    title = f"video_{job.job_id[:6]}"

                # ✅ Actualizar el config del job con el título correcto
                job.config['title'] = title

                # Insertar título
                self.title_entry.insert(0, title)
                print(f"DEBUG: Título establecido para job {job.job_id[:8]}: '{title}'")
                
                # ============================================
                # 🆕 SECCIÓN DE MINIATURA (TAMBIÉN FALTABA)
                # ============================================
                
                # Si no hay miniatura, mostrar placeholder apropiado
                formats = info.get('formats', [])
                has_audio_only = any(
                    self._classify_format(f) == 'AUDIO' for f in formats
                ) and not any(
                    self._classify_format(f) in ['VIDEO', 'VIDEO_ONLY'] for f in formats
                )
                
                if has_audio_only:
                    self.create_placeholder_label(self.thumbnail_container, "🎵", font_size=60)
                else:
                    self.create_placeholder_label(self.thumbnail_container, "Miniatura")
                
                # ============================================
                # RESTO DEL CÓDIGO (sin cambios)
                # ============================================
                
                formats = info.get('formats', [])
                video_entries, audio_entries = [], []
                
                video_duration = info.get('duration', 0)
                
                # 🆕 PASADA PREVIA: Detectar si hay ALGUNA fuente de audio disponible
                has_any_audio_source = False
                for f in formats:
                    format_type = self._classify_format(f)
                    if format_type == 'AUDIO':
                        has_any_audio_source = True
                        break
                    if format_type == 'VIDEO':  # Combinado con audio
                        acodec = f.get('acodec')
                        if acodec and acodec != 'none':
                            has_any_audio_source = True
                            break
                
                print(f"DEBUG: 🔊 has_any_audio_source = {has_any_audio_source}")
                
                # 🔧 PASO 1: Pre-análisis MEJORADO para agrupar variantes
                self.combined_variants = {}
                
                for f in formats:
                    format_type = self._classify_format(f)
                    
                    # 🆕 CRÍTICO: Manejar VIDEO, VIDEO_ONLY y AUDIO
                    if format_type in ['VIDEO', 'VIDEO_ONLY']:
                        vcodec_raw = f.get('vcodec')
                        acodec_raw = f.get('acodec')
                        vcodec = vcodec_raw.split('.')[0] if vcodec_raw else 'none'
                        acodec = acodec_raw.split('.')[0] if acodec_raw else 'none'
                        is_combined = acodec != 'none' and acodec is not None
                        
                        if is_combined:
                            fps = f.get('fps')
                            height = f.get('height', 0)
                            fps_val = int(fps) if fps else 0
                            ext = f.get('ext', 'N/A')
                            
                            tbr = f.get('tbr', 0)
                            tbr_rounded = round(tbr / 100) * 100 if tbr else 0
                            
                            quality_key = f"{height}p{fps_val}_{ext}_{vcodec}_{acodec}_tbr{tbr_rounded}"
                            
                            if quality_key not in self.combined_variants:
                                self.combined_variants[quality_key] = []
                            self.combined_variants[quality_key].append(f)
                
                # 🔧 PASO 1.5: Filtrar grupos que NO son realmente multiidioma
                real_multilang_keys = set()
                for quality_key, variants in self.combined_variants.items():
                    unique_languages = set()
                    for variant in variants:
                        lang = variant.get('language', '')
                        if lang:
                            unique_languages.add(lang)
                    
                    if len(unique_languages) >= 2:
                        real_multilang_keys.add(quality_key)
                        print(f"DEBUG: Grupo multiidioma detectado: {quality_key} con idiomas {unique_languages}")
                
                # 🔧 PASO 2: Crear las entradas con la información correcta
                combined_keys_seen = set()
                
                for f in formats:
                    format_type = self._classify_format(f)
                    
                    size_mb_str = "Tamaño desc."
                    size_sort_priority = 0
                    filesize = f.get('filesize') or f.get('filesize_approx')
                    if filesize:
                        size_mb_str = f"{filesize / (1024*1024):.2f} MB"
                        size_sort_priority = 2
                    else:
                        bitrate = f.get('tbr') or f.get('vbr') or f.get('abr')
                        if bitrate and video_duration:
                            estimated_bytes = (bitrate*1000/8)*video_duration
                            size_mb_str = f"Aprox. {estimated_bytes/(1024*1024):.2f} MB"
                            size_sort_priority = 1
                    
                    vcodec_raw = f.get('vcodec')
                    acodec_raw = f.get('acodec')
                    vcodec = vcodec_raw.split('.')[0] if vcodec_raw else 'none'
                    acodec = acodec_raw.split('.')[0] if acodec_raw else 'none'
                    ext = f.get('ext', 'N/A')
                    
                    # 🆕 CRÍTICO: Procesar VIDEO y VIDEO_ONLY
                    if format_type in ['VIDEO', 'VIDEO_ONLY']:
                        is_combined = acodec != 'none' and acodec is not None
                        fps = f.get('fps')
                        fps_tag = f"{fps:.0f}" if fps else ""
                        
                        quality_key = None
                        if is_combined:
                            height = f.get('height', 0)
                            fps_val = int(fps) if fps else 0
                            tbr = f.get('tbr', 0)
                            tbr_rounded = round(tbr / 100) * 100 if tbr else 0
                            quality_key = f"{height}p{fps_val}_{ext}_{vcodec}_{acodec}_tbr{tbr_rounded}"
                            
                            # 🔧 MODIFICADO: Solo deduplicar si es REALMENTE multiidioma
                            if quality_key in real_multilang_keys:
                                if quality_key in combined_keys_seen:
                                    continue
                                combined_keys_seen.add(quality_key)
                        
                        label_base = f"{f.get('height', 'Video')}p{fps_tag} ({ext}"
                        label_codecs = f", {vcodec}+{acodec}" if is_combined else f", {vcodec}"
                        
                        # 🔧 MODIFICADO: Solo mostrar [Sin Audio] si NO hay audio disponible en el sitio
                        no_audio_tag = ""
                        if format_type == 'VIDEO_ONLY' and not has_any_audio_source:
                            no_audio_tag = " [Sin Audio]"
                        
                        # 🔧 MODIFICADO: Solo mostrar "Multiidioma" si está en real_multilang_keys
                        audio_lang_tag = ""
                        if is_combined and quality_key:
                            if quality_key in real_multilang_keys:
                                audio_lang_tag = f" [Multiidioma]"
                            else:
                                lang_code = f.get('language')
                                if lang_code:
                                    norm_code = lang_code.replace('_', '-').lower()
                                    lang_name = self.app.LANG_CODE_MAP.get(
                                        norm_code, 
                                        self.app.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code)
                                    )
                                    audio_lang_tag = f" | Audio: {lang_name}"
                        
                        label_tag = " [Combinado]" if is_combined else ""
                        note = f.get('format_note') or ''
                        note_tag = ""
                        informative_keywords = ['hdr', 'premium', 'dv', 'hlg', 'storyboard']
                        if any(keyword in note.lower() for keyword in informative_keywords):
                            note_tag = f" [{note}]"
                        protocol = f.get('protocol', '')
                        protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                        
                        # 🔧 CORREGIDO: Agregar el tag de sin audio
                        label = f"{label_base}{label_codecs}){label_tag}{audio_lang_tag}{no_audio_tag}{note_tag}{protocol_tag} - {size_mb_str}"

                        tags = []
                        compatibility_issues, unknown_issues = self._get_format_compatibility_issues(f)
                        if not compatibility_issues and not unknown_issues:
                            tags.append("✨")
                        elif compatibility_issues or unknown_issues:
                            tags.append("⚠️")
                        if tags:
                            label += f" {' '.join(tags)}"

                        video_entries.append({
                            'label': label,
                            'format': f,
                            'is_combined': is_combined,
                            'sort_priority': size_sort_priority,
                            'quality_key': quality_key
                        })

                    elif format_type == 'AUDIO':
                        abr = f.get('abr') or f.get('tbr')
                        lang_code = f.get('language')
                        
                        lang_name = "Idioma Desconocido"
                        if lang_code:
                            norm_code = lang_code.replace('_', '-').lower()
                            lang_name = self.app.LANG_CODE_MAP.get(
                                norm_code,
                                self.app.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code)
                            )
                        
                        lang_prefix = f"{lang_name} - " if lang_code else ""
                        note = f.get('format_note') or ''
                        drc_tag = " (DRC)" if 'DRC' in note else ""
                        protocol = f.get('protocol', '')
                        protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                        label = f"{lang_prefix}{abr:.0f}kbps ({acodec}, {ext}){drc_tag}{protocol_tag}" if abr else f"{lang_prefix}Audio ({acodec}, {ext}){drc_tag}{protocol_tag}"
                        
                        if acodec in self.app.EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]:
                            label += " ✨"
                        else:
                            label += " ⚠️"
                        audio_entries.append({
                            'label': label,
                            'format': f,
                            'sort_priority': size_sort_priority
                        })
                
                # 🔧 Ordenamiento mejorado (igual que single_download_tab.py)
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
                    lang_priority = self.app.LANGUAGE_ORDER.get(
                        norm_code,
                        self.app.LANGUAGE_ORDER.get(norm_code.split('-')[0], self.app.DEFAULT_PRIORITY)
                    )
                    quality = f.get('abr') or f.get('tbr') or 0
                    return (lang_priority, -quality)
                
                audio_entries.sort(key=custom_audio_sort_key)
                
                # 🔧 MODIFICADO: Guardar también quality_key en video_formats
                self.current_video_formats = {
                    e['label']: {
                        k: e['format'].get(k) for k in ['format_id', 'vcodec', 'acodec', 'ext', 'width', 'height']
                    } | {
                        'is_combined': e.get('is_combined', False),
                        'quality_key': e.get('quality_key')
                    }
                    for e in video_entries
                }
                
                self.current_audio_formats = {
                    e['label']: {
                        k: e['format'].get(k) for k in ['format_id', 'acodec', 'ext']
                    }
                    for e in audio_entries
                }
                
                # 🔧 Verificar disponibilidad de audio (DESPUÉS de llenar los diccionarios)
                has_any_audio = bool(audio_entries) or any(
                    v.get('is_combined', False) for v in self.current_video_formats.values()
                )
                
                print(f"DEBUG: audio_entries={len(audio_entries)}, has_any_audio={has_any_audio}")
                
                # 🆕 Deshabilitar modo "Solo Audio" si no hay audio
                if not has_any_audio:
                    self.mode_selector.set("Video+Audio")
                    self.mode_selector.configure(state="disabled", values=["Video+Audio"])
                    print("⚠️ ADVERTENCIA: No hay pistas de audio disponibles. Modo Solo Audio deshabilitado.")
                elif not video_entries and audio_entries:
                    self.mode_selector.set("Solo Audio")
                    self.mode_selector.configure(state="disabled", values=["Solo Audio"])
                    print("✅ Solo hay audio. Modo Solo Audio activado.")
                else:
                    saved_mode = job.config.get('mode', 'Video+Audio')
                    self.mode_selector.configure(state="normal", values=["Video+Audio", "Solo Audio"])
                    if saved_mode in ["Video+Audio", "Solo Audio"]:
                        self.mode_selector.set(saved_mode)
                    else:
                        self.mode_selector.set("Video+Audio")
                    print(f"✅ Ambos modos disponibles. Modo actual: {self.mode_selector.get()}")
                
                self._on_item_mode_change(self.mode_selector.get())

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
                
                # 1. Determinar y establecer la SELECCIÓN DE VIDEO (guardada o default)
                video_selection_to_set = default_video_selection
                if saved_video in v_opts:
                    video_selection_to_set = saved_video
                self.video_quality_menu.set(video_selection_to_set)

                # 2. LLAMAR A LA FUNCIÓN DE VIDEO AHORA
                # Esto actualiza la lista de audios (corrigiendo el mapa de idiomas)
                # y resetea temporalmente el audio al valor por defecto (lo cual está bien).
                self._on_batch_video_quality_change(video_selection_to_set)
                
                # 3. AHORA SÍ, establecer la SELECCIÓN DE AUDIO (guardada o default)
                
                # (Volvemos a leer la lista de opciones de audio, por si cambió en el paso 2)
                current_audio_opts = self.audio_quality_menu.cget("values")

                audio_selection_to_set = default_audio_selection # Fallback
                
                # Comprobar si la selección guardada sigue siendo válida en la lista actual
                if saved_audio in current_audio_opts:
                    audio_selection_to_set = saved_audio
                elif saved_audio in a_opts: # Fallback por si la lista no se actualizó
                    audio_selection_to_set = saved_audio
                
                # Establecer la selección de audio final
                self.audio_quality_menu.set(audio_selection_to_set)
                
                # Restaurar estado del checkbox de miniatura
                saved_thumbnail = job.config.get('download_thumbnail', False)
                if saved_thumbnail:
                    self.auto_save_thumbnail_check.select()
                else:
                    self.auto_save_thumbnail_check.deselect()
                
                self.auto_save_thumbnail_check.configure(state="normal")

                # Restaurar estado de Recodificación Rápida
                is_recode_enabled = job.config.get('recode_enabled', False)
                is_keep_original = job.config.get('recode_keep_original', True)

                if is_recode_enabled:
                    self.batch_apply_quick_preset_checkbox.select()
                else:
                    self.batch_apply_quick_preset_checkbox.deselect()

                if is_keep_original:
                    self.batch_keep_original_quick_checkbox.select()
                else:
                    self.batch_keep_original_quick_checkbox.deselect()

                # Poblar el menú (esto también restaurará la selección)
                self._populate_batch_preset_menu()
                
                # Mostrar u ocultar el frame de opciones DIRECTAMENTE
                # (sin llamar a la función que usa .get())
                if is_recode_enabled:
                    self.batch_quick_recode_options_frame.pack(fill="x", padx=0, pady=0)
                    self.batch_keep_original_quick_checkbox.configure(state="normal")
                else:
                    self.batch_quick_recode_options_frame.pack_forget()
                    self.batch_keep_original_quick_checkbox.configure(state="disabled")

                # (Recarga la miniatura, ya que este panel se refresca)
                thumbnail_url = job.analysis_data.get('thumbnail')
                if thumbnail_url:
                    threading.Thread(target=self.load_thumbnail, args=(thumbnail_url,), daemon=True).start()
            

        finally:
            # DESACTIVAR FLAG al terminar
            self._updating_ui = False

    def load_thumbnail(self, path_or_url: str, is_local: bool = False):
        """Carga una miniatura (desde URL o archivo local)."""
        
        # --- INICIO DE MODIFICACIÓN: Manejo de 'is_local' ---
        
        # Para archivos locales, usamos la ruta como clave de caché
        cache_key = path_or_url
        self.current_thumbnail_url = path_or_url if not is_local else None
        
        # 1. Verificar caché (AHORA A PRUEBA DE RACE CONDITIONS)
        try:
            # Intenta obtener la 'cache_key' del caché en una sola operación
            cached_item = self.thumbnail_cache[cache_key]
            
            # Si lo encuentra, imprime el log
            print(f"DEBUG: Miniatura encontrada en caché: {cache_key[:60]}...")
            
            # Verificar si es el NUEVO formato (diccionario)
            if isinstance(cached_item, dict) and 'ctk' in cached_item and 'raw' in cached_item:
                cached_image = cached_item['ctk']
                self.current_raw_thumbnail = cached_item['raw']
                
                # Si es el formato nuevo y válido, usarlo
                def set_cached_image():
                    if self.thumbnail_label:
                        self.thumbnail_label.destroy()
                    self.thumbnail_label = ctk.CTkLabel(self.thumbnail_container, text="", image=cached_image)
                    self.thumbnail_label.pack(expand=True)
                    self.thumbnail_label.image = cached_image
                    self.save_thumbnail_button.configure(state="normal")
                
                self.app.after(0, set_cached_image)
                return # <- Importante: Salir si usamos el caché
                
            else:
                # Si es el formato VIEJO o inválido, eliminarlo y seguir para descargar de nuevo
                print("DEBUG: Formato de caché viejo o inválido detectado. Re-descargando...")

        except KeyError:
            # Si 'cache_key' no estaba en el caché (o fue borrada por otro hilo), sigue adelante.
            print(f"DEBUG: Miniatura no en caché. Descargando: {cache_key[:60]}...")
            pass # Pasa al bloque de descarga
            
        # Si no está en caché O el caché era inválido, descargar/generar
        self.app.after(0, self.create_placeholder_label, self.thumbnail_container, "Cargando...")
        
        try:
            img_data = None
            if is_local:
                # --- LÓGICA NUEVA: Generar fotograma desde archivo local ---
                print(f"DEBUG: Generando fotograma para: {path_or_url}")
                # Asumimos que la info ya está en analysis_data del job seleccionado
                job = self.queue_manager.get_job_by_id(self.selected_job_id)
                duration = job.analysis_data.get('duration', 0)
                
                # Usamos el procesador de ffmpeg para obtener el fotograma
                frame_path = self.app.ffmpeg_processor.get_frame_from_video(path_or_url, duration)
                
                if frame_path and os.path.exists(frame_path):
                    with open(frame_path, 'rb') as f:
                        img_data = f.read()
                    # (Opcional: eliminar el .jpg temporal)
                    try: os.remove(frame_path)
                    except Exception as e: print(f"ADVERTENCIA: No se pudo eliminar fotograma temporal: {e}")
                else:
                    raise Exception("No se pudo generar el fotograma desde el video local.")
                
            else:
                # --- LÓGICA ANTIGUA (AHORA CORREGIDA) ---
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://imgur.com/',
                }
                
                max_retries = 2
                timeout = 15
                
                for attempt in range(max_retries):
                    try:
                        response = requests.get(
                            path_or_url,  # <--- ¡ESTA ES LA CORRECCIÓN! (url -> path_or_url)
                            headers=headers, 
                            timeout=timeout,
                            allow_redirects=True
                        )
                        response.raise_for_status()
                        img_data = response.content
                        break
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 429:
                            if attempt < max_retries - 1:
                                wait_time = 2 ** attempt
                                print(f"⚠️ Rate limit en miniatura. Reintentando en {wait_time}s...")
                                time.sleep(wait_time)
                                continue
                            else:
                                raise Exception(f"Rate limit (429). La miniatura no está disponible temporalmente.")
                        else:
                            raise
                    except requests.exceptions.Timeout:
                        if attempt < max_retries - 1:
                            print(f"⚠️ Timeout descargando miniatura. Reintentando...")
                            continue
                        else:
                            raise Exception("Timeout al descargar la miniatura")
            
            # Validar que img_data no esté vacío
            if not img_data or len(img_data) < 100:
                raise Exception("La miniatura descargada está vacía o corrupta")
            
            # --- FIN DE LA LÓGICA DE OBTENCIÓN DE DATOS ---

            pil_image = Image.open(BytesIO(img_data))
            display_image = pil_image.copy()
            display_image.thumbnail((160, 90), Image.Resampling.LANCZOS) 
            ctk_image = ctk.CTkImage(light_image=display_image, dark_image=display_image, size=display_image.size)
            
            # Guardar en caché (NUEVO FORMATO: diccionario)
            self.thumbnail_cache[cache_key] = {
                'ctk': ctk_image,
                'raw': img_data
            }
            self.current_raw_thumbnail = img_data
            print(f"DEBUG: Miniatura guardada en caché ({len(self.thumbnail_cache)} total)")

            def set_new_image():
                if self.thumbnail_label:
                    self.thumbnail_label.destroy()
                self.thumbnail_label = ctk.CTkLabel(self.thumbnail_container, text="", image=ctk_image)
                self.thumbnail_label.pack(expand=True)
                self.thumbnail_label.image = ctk_image
                self.save_thumbnail_button.configure(state="normal")
            
            self.app.after(0, set_new_image)
        
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') else 'unknown'
            error_msg = f"Error HTTP {status_code}"
            
            if status_code == 429:
                error_msg = "Rate limit (429)"
                placeholder_text = "⏳"
            elif status_code == 404:
                error_msg = "No encontrada (404)"
                placeholder_text = "❌"
            elif status_code in [403, 401]:
                error_msg = f"Acceso denegado ({status_code})"
                placeholder_text = "🔒"
            else:
                placeholder_text = "❌"
            
            print(f"⚠️ Error al cargar miniatura: {error_msg} - URL: {path_or_url}")
            self.current_raw_thumbnail = None
            self.app.after(0, lambda p=placeholder_text: self.create_placeholder_label(self.thumbnail_container, p, font_size=60))
            
        except requests.exceptions.Timeout:
            print(f"⚠️ Timeout al cargar miniatura: {path_or_url}")
            self.app.after(0, lambda: self.create_placeholder_label(self.thumbnail_container, "⏱️", font_size=60))
            
        except Exception as e:
            print(f"⚠️ Error al cargar miniatura: {e}")
            self.current_raw_thumbnail = None
            self.app.after(0, lambda: self.create_placeholder_label(self.thumbnail_container, "❌", font_size=60))

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


    def _on_apply_global_mode(self, selected_mode: str):
        """
        Aplica el modo (Video+Audio o Solo Audio) a TODOS los trabajos 
        actuales en la cola.
        """
        print(f"INFO: Aplicando modo global '{selected_mode}' a todos los trabajos...")
        
        # 1. Obtener una copia de la lista de trabajos
        with self.queue_manager.jobs_lock:
            all_jobs = list(self.queue_manager.jobs)
        
        if not all_jobs:
            print("INFO: No hay trabajos en la cola para aplicar el modo.")
            return

        # 2. Iterar y actualizar la configuración de CADA trabajo
        for job in all_jobs:
            job.config['mode'] = selected_mode

        # 3. [CRÍTICO] Refrescar el panel de configuración si hay un trabajo seleccionado
        # Esto hace que el usuario vea el cambio reflejado inmediatamente en la UI.
        if self.selected_job_id:
            current_job = self.queue_manager.get_job_by_id(self.selected_job_id)
            if current_job:
                print(f"DEBUG: Refrescando panel de configuración para {self.selected_job_id[:6]}...")
                
                # Usamos _populate_config_panel para recargar la UI del job
                # de forma segura, respetando el flag _updating_ui.
                self._populate_config_panel(current_job)
        
        print(f"INFO: Modo global aplicado a {len(all_jobs)} trabajos.")


    def _on_save_thumbnail_click(self):
        """
        Abre diálogo para guardar la miniatura actual, la re-codifica con PIL
        (preservando transparencia) y la importa a Adobe si está marcado.
        """
                
        if not self.current_raw_thumbnail: 
            print("ERROR: No hay miniatura cargada (datos raw) para guardar.")
            return
        
        file_name = self.title_entry.get().strip()
        if not file_name:
            file_name = "thumbnail"
        
        try:
            image_data = self.current_raw_thumbnail
            
            # 1. Detectar formato óptimo (PNG o JPG)
            smart_ext = self.get_smart_thumbnail_extension(image_data)
            
            # 2. Pedir al usuario dónde guardar
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
            
            self.app.lift()
            self.app.focus_force()
            
            if not file_path:
                return  # Usuario canceló
            
            # 3. Re-codificar con PIL (LA SOLUCIÓN A LA TRANSPARENCIA Y CABECERA)
            pil_image = Image.open(BytesIO(image_data))
            
            # Forzar la extensión final basada en lo que el usuario eligió
            final_ext_chosen = os.path.splitext(file_path)[1].lower()

            if final_ext_chosen == '.png':
                pil_image.save(file_path, "PNG")
                print(f"INFO: Miniatura guardada como PNG (con transparencia): {file_path}")
            else:
                # Por defecto (si es .jpg o cualquier otra cosa), guardar como JPG
                pil_image.convert("RGB").save(file_path, "JPEG", quality=95)
                print(f"INFO: Miniatura guardada como JPG (sin transparencia): {file_path}")

            
            # 4. Comprobar si se debe importar
            if self.auto_import_checkbox.get():
                active_target = self.app.ACTIVE_TARGET_SID_accessor()
                if active_target:
                    # 5. Armar el paquete (solo miniatura, sin bin de lote)
                    file_package = {
                        "video": None,
                        "thumbnail": file_path.replace('\\', '/'),
                        "subtitle": None,
                        "targetBin": None # Importa a la raíz "DowP Imports"
                    }
                    
                    print(f"INFO: [Manual] Enviando miniatura a CEP: {file_package}")
                    
                    # 6. Enviar
                    self.app.socketio.emit('new_file', {'filePackage': file_package}, to=active_target)

        except Exception as e:
            print(f"ERROR: No se pudo guardar o importar la miniatura manualmente: {e}")

    def _classify_format(self, f):
        """
        Clasifica un formato (v3.2 - Manejo de codecs 'unknown')
        """
        ext = f.get('ext', '')
        vcodec = f.get('vcodec', '')
        acodec = f.get('acodec', '')
        format_id = (f.get('format_id') or '').lower()
        format_note = (f.get('format_note') or '').lower()
        protocol = f.get('protocol', '')
        
        # 🆕 REGLA -1: Formato sintético
        if 'audio directo' in format_note or 'livestream' in format_note:
            if 'audio' in format_note:
                return 'AUDIO'
            return 'VIDEO'
        
        # 🆕 REGLA 0: Casos especiales de vcodec literal
        vcodec_special_cases = {
            'audio only': 'AUDIO',
            'images': 'VIDEO',
            'slideshow': 'VIDEO',
        }
        
        if vcodec in vcodec_special_cases:
            return vcodec_special_cases[vcodec]
        
        # 🔧 REGLA 1: GIF explícito
        if ext == 'gif' or vcodec == 'gif':
            return 'VIDEO'
        
        # 🔧 REGLA 2: Tiene dimensiones → VIDEO (con o sin audio)
        if f.get('height') or f.get('width'):
            # 🆕 CRÍTICO: Si ambos codecs son 'unknown' o faltan → ASUMIR COMBINADO
            vcodec_is_unknown = not vcodec or vcodec in ['unknown', 'N/A', '']
            acodec_is_unknown = not acodec or acodec in ['unknown', 'N/A', '']
            
            # Si AMBOS son desconocidos → probablemente es combinado
            if vcodec_is_unknown and acodec_is_unknown:
                print(f"DEBUG: Formato {f.get('format_id')} con codecs desconocidos → asumiendo VIDEO combinado")
                return 'VIDEO'
            
            # Si solo audio es 'none' explícitamente → VIDEO_ONLY
            if acodec in ['none']:
                return 'VIDEO_ONLY'
            
            # Si tiene audio conocido → VIDEO combinado
            return 'VIDEO'
        
        # 🆕 REGLA 2.5: Livestreams
        if f.get('is_live') or 'live' in format_id:
            return 'VIDEO'
        
        # 🔧 REGLA 3: Resolución en format_note
        resolution_patterns = ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p', '4320p']
        if any(res in format_note for res in resolution_patterns):
            if acodec in ['none']:
                return 'VIDEO_ONLY'
            return 'VIDEO'
        
        # 🔧 REGLA 4: "audio" explícito en IDs
        if 'audio' in format_id or 'audio' in format_note:
            return 'AUDIO'
        
        # 🆕 REGLA 4.5: "video" explícito en IDs
        if 'video' in format_id or 'video' in format_note:
            # Si tiene dimensiones o codecs desconocidos → asumir combinado
            if f.get('height') or (vcodec == 'unknown' and acodec == 'unknown'):
                return 'VIDEO'
            return 'VIDEO_ONLY' if acodec in ['none'] else 'VIDEO'
        
        # 🔧 REGLA 5: Extensión tiene MÁXIMA PRIORIDAD
        if ext in self.app.AUDIO_EXTENSIONS:
            return 'AUDIO'
        
        # 🆕 REGLA 6: Audio sin video (codec EXPLÍCITAMENTE 'none')
        # IMPORTANTE: 'unknown' NO es lo mismo que 'none'
        if vcodec == 'none' and acodec and acodec not in ['none', '', 'N/A', 'unknown']:
            return 'AUDIO'
        
        # 🆕 REGLA 7: Video sin audio (codec EXPLÍCITAMENTE 'none')
        if acodec == 'none' and vcodec and vcodec not in ['none', '', 'N/A', 'unknown']:
            return 'VIDEO_ONLY'
        
        # 🔧 REGLA 8: Extensión de video + codecs válidos o desconocidos
        if ext in self.app.VIDEO_EXTENSIONS:
            # 🆕 Si ambos codecs son desconocidos → asumir combinado
            if vcodec in ['unknown', ''] and acodec in ['unknown', '']:
                return 'VIDEO'
            return 'VIDEO'
        
        # 🔧 REGLA 9: Ambos codecs explícitamente válidos
        valid_vcodecs = ['h264', 'h265', 'vp8', 'vp9', 'av1', 'hevc', 'mpeg4', 'xvid', 'theora']
        valid_acodecs = ['aac', 'mp3', 'opus', 'vorbis', 'flac', 'ac3', 'eac3', 'pcm']
        
        vcodec_lower = (vcodec or '').lower()
        acodec_lower = (acodec or '').lower()
        
        if vcodec_lower in valid_vcodecs:
            if acodec_lower in valid_acodecs:
                return 'VIDEO'
            else:
                return 'VIDEO_ONLY'
        
        # 🔧 REGLA 10: Protocolo m3u8/dash
        if 'm3u8' in protocol or 'dash' in protocol:
            return 'VIDEO'
        
        # 🆕 REGLA 11: Casos de formatos sin codecs claros pero con metadata
        if f.get('tbr') and not f.get('abr'):
            return 'VIDEO'
        elif f.get('abr') and not f.get('vbr'):
            return 'AUDIO'
        
        # 🆕 REGLA 12: Fallback para casos ambiguos con extensión de video
        if ext in self.app.VIDEO_EXTENSIONS:
            print(f"⚠️ ADVERTENCIA: Formato {f.get('format_id')} ambiguo → asumiendo VIDEO combinado por extensión")
            return 'VIDEO'
        
        # 🔧 REGLA 13: Si llegamos aquí → UNKNOWN
        print(f"⚠️ ADVERTENCIA: Formato sin clasificación clara: {f.get('format_id')} (vcodec={vcodec}, acodec={acodec}, ext={ext})")
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
                        self.open_folder_button.configure(state="normal")
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
            self.save_settings()
            self.open_folder_button.configure(state="normal")

    def _open_batch_output_folder(self):
        """
        Abre la carpeta de salida principal del lote.
        Prioritiza la subcarpeta del lote si fue creada.
        """
        path_to_open = None
        
        # 1. Prioridad: La subcarpeta del lote (ej: "DowP List 01")
        if hasattr(self.queue_manager, 'subfolder_path') and self.queue_manager.subfolder_path:
            if os.path.isdir(self.queue_manager.subfolder_path):
                path_to_open = self.queue_manager.subfolder_path
            else:
                # Si la subcarpeta fue borrada, intentar abrir la carpeta padre
                path_to_open = os.path.dirname(self.queue_manager.subfolder_path)
        
        # 2. Fallback: La carpeta de salida principal
        if not path_to_open:
            path_to_open = self.output_path_entry.get()

        if not path_to_open or not os.path.isdir(path_to_open):
            print(f"ERROR: La carpeta de salida '{path_to_open}' no es válida o no existe.")
            return

        # 3. Abrir la carpeta
        try:
            print(f"INFO: Abriendo carpeta de salida del lote: {path_to_open}")
            if os.name == "nt":
                import subprocess
                # Abrir la carpeta en el explorador (sin seleccionar un archivo)
                subprocess.Popen(['explorer', os.path.normpath(path_to_open)])
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(['open', path_to_open])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', path_to_open])
        except Exception as e:
            print(f"Error al intentar abrir la carpeta: {e}")

    def create_entry_context_menu(self, widget):
        """Crea un menú contextual simple para los Entry widgets."""
        menu = Menu(self, tearoff=0)
        
        def copy_text():
            """Copia el texto seleccionado al portapapeles."""
            try:
                selected_text = widget.selection_get()
                if selected_text:
                    widget.clipboard_clear()
                    widget.clipboard_append(selected_text)
            except Exception:
                pass # No había nada seleccionado
        
        def cut_text():
            """Corta el texto seleccionado (copia y borra)."""
            try:
                selected_text = widget.selection_get()
                if selected_text:
                    # 1. Copiar al portapapeles
                    widget.clipboard_clear()
                    widget.clipboard_append(selected_text)
                    # 2. Borrar selección
                    widget.delete("sel.first", "sel.last")
            except Exception:
                pass # No había nada seleccionado

        def paste_text():
            """Pega el texto del portapapeles."""
            try:
                # 1. Borrar selección actual (si existe)
                if widget.selection_get():
                    widget.delete("sel.first", "sel.last")
            except Exception:
                pass # No había nada seleccionado

            try:
                # 2. Pegar desde el portapapeles
                widget.insert("insert", self.clipboard_get())
            except:
                pass # Portapapeles vacío
                
        menu.add_command(label="Cortar", command=cut_text)
        menu.add_command(label="Copiar", command=copy_text)
        menu.add_command(label="Pegar", command=paste_text)
        menu.add_separator()
        menu.add_command(label="Seleccionar todo", command=lambda: widget.select_range(0, 'end'))
        
        menu.tk_popup(widget.winfo_pointerx(), widget.winfo_pointery())

    def _on_clear_list_click(self):
        """
        Elimina todos los trabajos de la cola y resetea la sesión de lote.
        """
        print("INFO: Limpiando la lista de trabajos y reseteando la sesión de lote...")
        
        # 1. Pausar la cola (si estaba corriendo)
        self.queue_manager.pause_queue()
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

        self.global_recode_checkbox.configure(state="disabled")
        self.global_recode_preset_menu.configure(state="disabled")
        self.global_recode_checkbox.deselect()

        # 5. Actualizar UI
        self.progress_label.configure(text="Cola vacía. Analiza una URL para empezar.")
        self._set_local_batch_mode(False)
        print("INFO: Sesión de lote finalizada.")

    def _on_reset_status_click(self):
        """
        Resetea el estado de trabajos (COMPLETED/FAILED -> PENDING) 
        y resetea la sesión de lote para una nueva ejecución.
        """
        print("INFO: Reseteando estado de trabajos para un nuevo lote...")

        # 1. Pausar la cola (si estaba corriendo)
        self.queue_manager.pause_queue()
        self.queue_manager.reset_progress()
        
        # 2. Resetear el estado de los trabajos en la lógica
        jobs_to_reset = []
        with self.queue_manager.jobs_lock:
            for job in self.queue_manager.jobs:
                if job.status in ("COMPLETED", "FAILED", "SKIPPED", "NO_AUDIO"):
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
        
        # --- INICIO DE MODIFICACIÓN ---
        if self.is_local_mode:
            # Mantener el modo Proceso (morado)
            self.start_queue_button.configure(
                text="Iniciar Proceso", 
                fg_color=self.PROCESS_BTN_COLOR, 
                hover_color=self.PROCESS_BTN_HOVER,
                state="normal" if jobs_exist else "disabled"
            )
        else:
            # Mantener el modo Cola (verde)
            self.start_queue_button.configure(
                text="Iniciar Cola", 
                fg_color=self.DOWNLOAD_BTN_COLOR, 
                hover_color=self.DOWNLOAD_BTN_HOVER,
                state="normal" if jobs_exist else "disabled"
            )
        # --- FIN DE MODIFICACIÓN ---
        self.global_recode_checkbox.configure(state="normal" if jobs_exist else "disabled")
        if not jobs_exist:
            self.global_recode_preset_menu.configure(state="disabled")
            self.global_recode_checkbox.deselect()

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

        if job.status in ("COMPLETED", "FAILED", "SKIPPED", "NO_AUDIO"):
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
        if self.is_local_mode:
            print("INFO: Saliendo del modo local. Limpiando cola de recodificación.")
            # 1. Limpiar la lista de trabajos locales
            self._on_clear_list_click() 
            # 2. Reactivar la UI para el modo de descarga
            self._set_local_batch_mode(False)
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
        self.url_entry.delete(0, 'end')
        

    def _run_analysis(self, url: str, job_id: str):
        """
        Hilo de trabajo que ejecuta yt-dlp para obtener información.
        MODIFICADO: Lee la casilla "Análisis de Playlist" para decidir
        si usa `noplaylist: True` (video único) o `noplaylist: False` (playlist).
        Ya no usa 'extract_flat'.
        """
        try:
            single_tab = self.app.single_tab 

            # --- INICIO DE LA MODIFICACIÓN ---
            
            # 1. Leer el estado de la nueva casilla (lectura directa)
            try:
                analizar_playlist = self.playlist_analysis_check.get()
            except Exception as e:
                # Fallback si la UI no está lista (aunque debería)
                print(f"ADVERTENCIA: No se pudo leer la casilla de playlist, se asume 'True': {e}")
                analizar_playlist = True
            
            print(f"DEBUG: Iniciando análisis. Modo Playlist: {analizar_playlist}")

            # 2. Configurar ydl_opts basado en la casilla
            ydl_opts = {
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.0 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'referer': url,
                'noplaylist': not analizar_playlist, # <-- ¡LA LÓGICA CLAVE!
                # 'extract_flat' se elimina para un análisis profundo
                'listsubtitles': False,
                'ignoreerrors': True, # Para que un video malo no arruine toda la playlist
            }
            # --- FIN DE LA MODIFICACIÓN ---

            cookie_mode = single_tab.cookie_mode_menu.get()
            browser_arg = None
            profile = None
            
            if cookie_mode == "Archivo Manual..." and single_tab.cookie_path_entry.get():
                ydl_opts['cookiefile'] = single_tab.cookie_path_entry.get()
            elif cookie_mode != "No usar":
                browser_arg = single_tab.browser_var.get()
                profile = single_tab.browser_profile_entry.get()
                if profile:
                    browser_arg_with_profile = f"{browser_arg}:{profile}"
                    ydl_opts['cookiesfrombrowser'] = (browser_arg_with_profile,)
                else:
                    ydl_opts['cookiesfrombrowser'] = (browser_arg,)

            info_dict = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
            
            if not info_dict:
                raise Exception("No se pudo obtener información.")
            
            # La lógica de ydl_opts_deep (análisis profundo) ya no es necesaria,
            # porque este análisis ES profundo por defecto (sin extract_flat).
            
            # Normalizar el resultado final
            if info_dict:
                info_dict = self._normalize_info_dict(info_dict)

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
        
        # --- INICIO DE MODIFICACIÓN (BUG 3) ---
        # 1. Leer la configuración global de recodificación PRIMERO
        global_recode_enabled = self.global_recode_checkbox.get() == 1
        global_preset_name = self.global_recode_preset_menu.get()
        global_preset_params = self._find_preset_params(global_preset_name)
        
        # Si el preset no es válido (ej: "---" o no encontrado), desactivar
        if not global_preset_params or global_preset_name.startswith("---"):
            global_recode_enabled = False

        global_preset_mode = global_preset_params.get("mode_compatibility", "Video+Audio")
        global_keep_original = global_preset_params.get("keep_original_file", True)
        
        if global_recode_enabled:
                print(f"DEBUG: Aplicando config global a nuevos jobs (Preset: {global_preset_name})")
        # --- FIN DE MODIFICACIÓN (BUG 3) ---

        is_playlist = info_dict.get("_type") == "playlist" or (info_dict.get("entries") and len(info_dict.get("entries")) > 0)
        
        if is_playlist and info_dict.get('extractor_key') != 'Generic':
            entries = info_dict.get('entries', [])
            if not entries:
                self.update_job_ui(job_id, "FAILED", "Error: Playlist/Colección está vacía.")
                return

            print(f"INFO: Playlist detectada con {len(entries)} videos.")
            
            all_jobs = [job] 
            for i in range(1, len(entries)):
                all_jobs.append(Job(config={})) 

            for i, (entry, current_job) in enumerate(zip(entries, all_jobs)):
                if not entry: continue

                video_url = entry.get('webpage_url') or job.config.get('url')
                title = entry.get('title') or f'Video {i+1}'
                
                playlist_index = entry.get('playlist_index', i + 1) 

                # --- INICIO DE MODIFICACIÓN (BUG 3) ---
                # Aplicar la configuración global al crear el job
                current_job.config['url'] = video_url
                current_job.config['title'] = title
                current_job.config['playlist_index'] = playlist_index
                current_job.analysis_data = entry

                if global_recode_enabled:
                    current_job.config['mode'] = global_preset_mode
                    current_job.config['recode_enabled'] = True
                    current_job.config['recode_preset_name'] = global_preset_name
                    current_job.config['recode_keep_original'] = global_keep_original
                else:
                    # Usar el modo global (Video/Audio), no el del preset
                    current_job.config['mode'] = self.global_mode_var.get()
                    current_job.config['recode_enabled'] = False
                    current_job.config['recode_preset_name'] = "-"
                    current_job.config['recode_keep_original'] = True
                # --- FIN DE MODIFICACIÓN (BUG 3) ---
                
                if current_job == job:
                    if job_widget:
                        job_widget.title_label.configure(text=title)
                else:
                    self.queue_manager.add_job(current_job)

        else:
            # Es un video único
            print("INFO: Video único detectado.")
            title = (info_dict.get('title') or '').strip()
            if not title:
                title = f"video_{job.job_id[:8]}"
            job.config['title'] = title
            job.analysis_data = info_dict
            job.config['playlist_index'] = None
            
            # --- INICIO DE MODIFICACIÓN (BUG 3) ---
            # Aplicar la configuración global al job único
            if global_recode_enabled:
                job.config['mode'] = global_preset_mode
                job.config['recode_enabled'] = True
                job.config['recode_preset_name'] = global_preset_name
                job.config['recode_keep_original'] = global_keep_original
            else:
                job.config['mode'] = self.global_mode_var.get()
                job.config['recode_enabled'] = False
                job.config['recode_preset_name'] = "-"
                job.config['recode_keep_original'] = True
            # --- FIN DE MODIFICACIÓN (BUG 3) ---

            if job_widget:
                job_widget.title_label.configure(text=title)
        
        self.update_job_ui(job_id, "PENDING", "Listo para descargar")
        self.start_queue_button.configure(state="normal")
        # Habilitar controles globales si estaban deshabilitados
        self.global_recode_checkbox.configure(state="normal")
        if self.global_recode_checkbox.get() == 1:
             self._populate_global_preset_menu()
             self.global_recode_preset_menu.configure(state="normal")

        self._on_job_select(job_id)
        
        if self.auto_download_checkbox.get():
            print("INFO: Auto-descargar activado.")
            
            if not self.queue_manager.user_paused:
                if self.queue_manager.pause_event.is_set():
                    print("INFO: Auto-descargar iniciando/reanudando la cola...")
                    if hasattr(self.queue_manager, 'subfolder_created'):
                         delattr(self.queue_manager, 'subfolder_created')
                    
                    self.start_queue_processing()
                    self.progress_label.configure(text=f"Descargando automáticamente...")
                else:
                    print("INFO: Auto-descargar: La cola ya estaba corriendo.")
            
            else:
                print("INFO: Auto-descargar: La cola está pausada por el usuario, no se reanudará.")
                self.progress_label.configure(text=f"Cola pausada. {len(self.job_widgets)} trabajos en espera.")

        else:
            self.progress_label.configure(text=f"Análisis completado. Presiona 'Iniciar Cola' para empezar.")

    def _on_batch_config_change(self, event=None):
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
        job.config['download_thumbnail'] = self.auto_save_thumbnail_check.get()

        is_recode_enabled = self.batch_apply_quick_preset_checkbox.get() == 1
        is_keep_original = self.batch_keep_original_quick_checkbox.get() == 1
        
        job.config['recode_enabled'] = is_recode_enabled
        job.config['recode_preset_name'] = self.batch_recode_preset_menu.get()
        job.config['recode_keep_original'] = is_keep_original
        
        job.config['recode_all_audio_tracks'] = self.batch_use_all_audio_tracks_check.get() == 1

        print(f"DEBUG: [Guardando Job {job.job_id[:6]}] Recodificación: {is_recode_enabled}, Mantener Original: {is_keep_original}")
        
        # ✅ NUEVO: Guardar los format_id REALES (incluyendo multiidioma)
        v_label = self.video_quality_menu.get()
        a_label = self.audio_quality_menu.get()
        
        v_info = self.current_video_formats.get(v_label, {})
        a_info = self.current_audio_formats.get(a_label, {})
        
        # Determinar el format_id de video correcto
        v_id = v_info.get('format_id')
        
        # Si es combinado multiidioma, usar el ID del idioma seleccionado
        if v_info.get('is_combined') and hasattr(self, 'combined_audio_map') and self.combined_audio_map:
            if a_label in self.combined_audio_map:
                v_id = self.combined_audio_map[a_label]
                print(f"DEBUG: Guardando format_id multiidioma: {v_id}")
        
        # Guardar los IDs reales en el config
        job.config['resolved_video_format_id'] = v_id
        
        # --- INICIO DE CORRECCIÓN (Soporte Multipista Local) ---
        if job.job_type == "LOCAL_RECODE":
            # Para locales, a_info es el stream. Guardamos el 'index'
            job.config['resolved_audio_stream_index'] = a_info.get('index')
            print(f"DEBUG: [Guardando Job Local] Índice de audio resuelto: {a_info.get('index')}")
        else:
            # Para descargas, guardamos el 'format_id'
            job.config['resolved_audio_format_id'] = a_info.get('format_id')
        # --- FIN DE CORRECCIÓN ---

    def _normalize_info_dict(self, info):
        """
        Normaliza el diccionario de info para casos donde yt-dlp no devuelve 'formats'.
        Maneja contenido de audio directo, GIF, directos, etc.
        """
        if not info:
            return info
        
        formats = info.get('formats', [])
        
        # Si ya tiene formatos, no tocar
        if formats:
            return info
        
        print(f"DEBUG: ℹ️ Info sin formatos detectada. Extractor: {info.get('extractor_key')}")
        
        # ===== CASO 1: Audio directo =====
        url = info.get('url')
        ext = info.get('ext')
        vcodec = info.get('vcodec', 'none')
        acodec = info.get('acodec')
        
        is_audio_content = False
        
        if url and ext and (vcodec == 'none' or not vcodec) and acodec and acodec != 'none':
            is_audio_content = True
            print(f"DEBUG: 🎵 Audio directo detectado por codecs")
        elif ext in self.app.AUDIO_EXTENSIONS:
            is_audio_content = True
            print(f"DEBUG: 🎵 Audio directo detectado por extensión (.{ext})")
            if not acodec or acodec == 'none':
                acodec = {'mp3': 'mp3', 'opus': 'opus', 'aac': 'aac', 'm4a': 'aac'}.get(ext, ext)
        elif info.get('extractor_key', '').lower() in ['applepodcasts', 'soundcloud', 'audioboom', 'spreaker', 'libsyn']:
            is_audio_content = True
            print(f"DEBUG: 🎵 Audio directo detectado por extractor")
            if not acodec:
                acodec = 'mp3'
        
        if is_audio_content:
            synthetic_format = {
                'format_id': '0',
                'url': url or info.get('manifest_url') or '',
                'ext': ext or 'mp3',
                'vcodec': 'none',
                'acodec': acodec or 'unknown',
                'abr': info.get('abr'),
                'tbr': info.get('tbr'),
                'filesize': info.get('filesize'),
                'filesize_approx': info.get('filesize_approx'),
                'protocol': info.get('protocol', 'https'),
                'format_note': 'Audio directo',
            }
            
            info['formats'] = [synthetic_format]
            print(f"DEBUG: ✅ Formato sintético creado (audio)")
            return info
        
        # ===== CASO 2: Video directo (Imgur, etc) =====
        if url and ext and ext in self.app.VIDEO_EXTENSIONS:
            is_video_content = False
            
            # Detectar por metadata
            if vcodec and vcodec != 'none':
                is_video_content = True
                print(f"DEBUG: 🎬 Video directo detectado por vcodec")
            
            # Detectar por extensión
            if ext in ['gif', 'mp4', 'webm', 'mov', 'avi']:
                is_video_content = True
                print(f"DEBUG: 🎬 Video directo detectado por extensión (.{ext})")
            
            # Detectar por extractor
            extractor = info.get('extractor_key', '').lower()
            if any(x in extractor for x in ['imgur', 'gfycat', 'giphy', 'tenor']):
                is_video_content = True
                print(f"DEBUG: 🎬 Video directo detectado por extractor: {extractor}")
            
            if is_video_content:
                synthetic_format = {
                    'format_id': '0',
                    'url': url or info.get('manifest_url') or '',
                    'ext': ext or 'mp4',
                    'vcodec': vcodec or 'h264',
                    'acodec': acodec or 'none',
                    'abr': info.get('abr'),
                    'tbr': info.get('tbr'),
                    'width': info.get('width'),
                    'height': info.get('height'),
                    'filesize': info.get('filesize'),
                    'filesize_approx': info.get('filesize_approx'),
                    'protocol': info.get('protocol', 'https'),
                    'format_note': 'Video directo',
                }
                
                info['formats'] = [synthetic_format]
                print(f"DEBUG: ✅ Formato sintético creado (video directo)")
                return info
        
        # ===== CASO 3: Livestream sin formatos =====
        if info.get('is_live') and info.get('manifest_url'):
            print(f"DEBUG: 📡 Livestream detectado sin formatos")
            
            synthetic_format = {
                'format_id': 'live',
                'url': info.get('manifest_url'),
                'ext': info.get('ext', 'mp4'),
                'protocol': 'm3u8_native',
                'format_note': 'Livestream',
                'vcodec': info.get('vcodec', 'h264'),
                'acodec': info.get('acodec', 'aac'),
            }
            
            info['formats'] = [synthetic_format]
            print(f"DEBUG: ✅ Formato sintético creado (livestream)")
            return info
        
        # ===== CASO 4: Sin información disponible =====
        print(f"DEBUG: ⚠️ No se pudo determinar tipo de contenido")
        print(f"     ext={ext}, vcodec={vcodec}, acodec={acodec}")
        print(f"     extractor={info.get('extractor_key')}")
        
        # Fallback: crear formato genérico
        synthetic_format = {
            'format_id': 'best',
            'url': url or info.get('manifest_url') or '',
            'ext': ext or 'mp4',
            'vcodec': vcodec or 'unknown',
            'acodec': acodec or 'unknown',
            'format_note': 'Contenido genérico',
        }
        
        info['formats'] = [synthetic_format]
        print(f"DEBUG: ✅ Formato genérico fallback creado")
        
        return info
    
    def _initialize_ui_settings(self):
        """Carga la configuración guardada en la UI al iniciar."""
        if self.app.batch_playlist_analysis_saved:
            self.playlist_analysis_check.select()
        else:
            self.playlist_analysis_check.deselect()

        if self.app.batch_auto_import_saved:
            self.auto_import_checkbox.select()
        else:
            self.auto_import_checkbox.deselect()
        self.is_initializing = False

    def save_settings(self):
        """
        Guarda la configuración de la pestaña de lotes en la app principal.
        La app principal se encargará de escribir el archivo JSON.
        """
        if not hasattr(self, 'app') or self.is_initializing: # Prevenir error si se llama antes de tiempo
            return
            
        self.app.batch_download_path = self.output_path_entry.get() 
        self.app.batch_playlist_analysis_saved = self.playlist_analysis_check.get() == 1
        self.app.batch_auto_import_saved = self.auto_import_checkbox.get() == 1

    def _on_batch_quick_recode_toggle(self):
        """
        Muestra/oculta las opciones de recodificación en la pestaña de Lotes.
        Adaptado de single_download_tab.py.
        """
        if self.batch_apply_quick_preset_checkbox.get() == 1:
            self.batch_quick_recode_options_frame.pack(fill="x", padx=0, pady=0)

            # --- INICIO DE CORRECCIÓN ---
            # Comprobar si estamos en modo local ANTES de habilitar
            job = self.queue_manager.get_job_by_id(self.selected_job_id)
            if job and job.job_type == "LOCAL_RECODE":
                self.batch_keep_original_quick_checkbox.select()
                self.batch_keep_original_quick_checkbox.configure(state="disabled")
            else:
                self.batch_keep_original_quick_checkbox.configure(state="normal")
            # --- FIN DE CORRECCIÓN ---
            
        else:
            self.batch_quick_recode_options_frame.pack_forget()
            self.batch_keep_original_quick_checkbox.configure(state="disabled")
        
    def _on_batch_quick_recode_toggle_and_save(self):
        """
        Llamado solo por el CLIC del usuario.
        Actualiza la UI Y guarda el estado.
        """
        # 1. Actualizar la UI (mostrar/ocultar)
        self._on_batch_quick_recode_toggle()
        
        # 2. Guardar el estado en el config del job
        self._on_batch_config_change()

    def _populate_batch_preset_menu(self):
        """
        Lee los presets disponibles (de la app principal) y los añade al menú,
        filtrando por el modo (Video+Audio o Solo Audio) DEL ITEM SELECCIONADO.
        Adaptado de single_download_tab.py.
        """
        
        # 1. Obtener el modo del item actual (no el global)
        current_item_mode = self.mode_selector.get()
        compatible_presets = []

        # 2. Leer presets integrados
        for name, data in self.app.single_tab.built_in_presets.items():
            if data.get("mode_compatibility") == current_item_mode:
                compatible_presets.append(name)
        
        # 3. Leer presets personalizados
        custom_presets_found = False
        for preset in getattr(self.app.single_tab, "custom_presets", []):
            if preset.get("data", {}).get("mode_compatibility") == current_item_mode:
                if not custom_presets_found:
                    if compatible_presets:
                        compatible_presets.append("--- Mis Presets ---")
                    custom_presets_found = True
                compatible_presets.append(preset.get("name"))

        # 4. Actualizar el menú
        if compatible_presets:
            self.batch_recode_preset_menu.configure(values=compatible_presets, state="normal")
            
            # Intentar restaurar la selección guardada del job
            job = self.queue_manager.get_job_by_id(self.selected_job_id)
            if job:
                saved_preset = job.config.get("recode_preset_name")
                if saved_preset and saved_preset in compatible_presets:
                    self.batch_recode_preset_menu.set(saved_preset)
                else:
                    self.batch_recode_preset_menu.set(compatible_presets[0])
            else:
                 self.batch_recode_preset_menu.set(compatible_presets[0])
        else:
            self.batch_recode_preset_menu.configure(values=["- No hay presets para este modo -"], state="disabled")
            self.batch_recode_preset_menu.set("- No hay presets para este modo -")

        self._update_batch_export_button_state()

    def _find_preset_params(self, preset_name):
        """
        Busca un preset por su nombre (personalizados y luego integrados).
        Adaptado de single_download_tab.py.
        """
        # Buscar en personalizados
        for preset in getattr(self.app.single_tab, 'custom_presets', []):
            if preset.get("name") == preset_name:
                return preset.get("data", {})
        
        # Buscar en integrados
        if preset_name in self.app.single_tab.built_in_presets:  
            return self.app.single_tab.built_in_presets[preset_name]
            
        return {}
    
    def _on_batch_preset_change_and_save(self, selection):
        """Llamado cuando el menú de preset cambia."""
        # 1. Guardar la selección en el job
        self._on_batch_config_change()
        # 2. Actualizar el estado de los botones Exportar/Eliminar
        self._update_batch_export_button_state()
        # 3. Validar compatibilidad del nuevo preset con multipista
        self._validate_batch_recode_compatibility()

    def _update_batch_export_button_state(self):
        """
        Habilita/desahabilita los botones de exportar y eliminar
        basado en si el preset es personalizado.
        Copiado de single_download_tab.py
        """
        selected_preset = self.batch_recode_preset_menu.get()

        # Busca en la lista de presets de la pestaña ÚNICA
        is_custom = any(p["name"] == selected_preset for p in self.app.single_tab.custom_presets)

        if is_custom:
            self.batch_export_preset_button.configure(state="normal")
            self.batch_delete_preset_button.configure(state="normal")
        else:
            self.batch_export_preset_button.configure(state="disabled")
            self.batch_delete_preset_button.configure(state="disabled")

    def _validate_batch_recode_compatibility(self):
        """
        (NUEVA FUNCIÓN)
        Valida si el preset de recodificación seleccionado es compatible con multipista.
        Deshabilita la casilla 'Recodificar todas las pistas' si no lo es.
        """
        if not hasattr(self, 'batch_use_all_audio_tracks_check'):
            return # Aún no se ha creado

        # 1. Obtener el preset y el contenedor
        target_container = None
        selected_preset_name = self.batch_recode_preset_menu.get()
        
        if selected_preset_name and not selected_preset_name.startswith("-"):
            preset_params = self._find_preset_params(selected_preset_name)
            if preset_params:
                target_container = preset_params.get("recode_container")

        # 2. Comprobar si la casilla 'multipista' está visible
        if self.batch_use_all_audio_tracks_check.winfo_ismapped():
            job = self.queue_manager.get_job_by_id(self.selected_job_id)
            is_multi_track_available = False
            if job and job.job_type == "LOCAL_RECODE":
                audio_streams = job.analysis_data.get('local_info', {}).get('audio_streams', [])
                is_multi_track_available = len(audio_streams) > 1

            # 3. Aplicar la lógica de deshabilitación
            # Leemos la constante global de la app
            if target_container in self.app.SINGLE_STREAM_AUDIO_CONTAINERS:
                print(f"DEBUG: Preset usa {target_container}, incompatible con multipista. Deshabilitando casilla.")
                self.batch_use_all_audio_tracks_check.configure(state="disabled")
                self.batch_use_all_audio_tracks_check.deselect()
                self.audio_quality_menu.configure(state="normal")
            elif is_multi_track_available:
                # Es compatible (o desconocido) Y el archivo es multipista, habilitarla
                self.batch_use_all_audio_tracks_check.configure(state="normal")
            else:
                # No es multipista, deshabilitar (aunque ya debería estar oculta)
                self.batch_use_all_audio_tracks_check.configure(state="disabled")

    def _populate_global_preset_menu(self):
        """
        Puebla el menú de presets GLOBALES, listando TODOS los presets
        (Video+Audio Y Solo Audio) para que el usuario elija.
        """
        print("\n--- DEBUG: Ejecutando _populate_global_preset_menu ---")

        all_presets = []

        # --- DEBUG LOG 2: ¿QUÉ DATOS ESTAMOS RECIBIENDO? ---
        try:
            built_in_count = len(self.app.single_tab.built_in_presets)
            custom_count = len(getattr(self.app.single_tab, "custom_presets", []))
            print(f"DEBUG: Fuente de datos: {built_in_count} presets integrados, {custom_count} presets personalizados.")
        except Exception as e:
            print(f"--- ERROR CRÍTICO: No se pudo acceder a los presets de single_tab: {e} ---")
            self.global_recode_preset_menu.configure(values=["- Error de carga -"], state="disabled")
            self.global_recode_preset_menu.set("- Error de carga -")
            return
        
        # 1. Leer presets integrados
        all_presets.append("--- Presets de Video ---")
        for name, data in self.app.single_tab.built_in_presets.items():
            if data.get("mode_compatibility") == "Video+Audio":
                all_presets.append(name)
        
        all_presets.append("--- Presets de Audio ---")
        for name, data in self.app.single_tab.built_in_presets.items():
            if data.get("mode_compatibility") == "Solo Audio":
                all_presets.append(name)
        
        # 2. Leer presets personalizados
        custom_video_presets = []
        custom_audio_presets = []
        for preset in getattr(self.app.single_tab, "custom_presets", []):
            if preset.get("data", {}).get("mode_compatibility") == "Video+Audio":
                custom_video_presets.append(preset.get("name"))
            else:
                custom_audio_presets.append(preset.get("name"))

        if custom_video_presets:
            all_presets.append("--- Mis Presets de Video ---")
            all_presets.extend(custom_video_presets)
            
        if custom_audio_presets:
            all_presets.append("--- Mis Presets de Audio ---")
            all_presets.extend(custom_audio_presets)

        # Contar presets reales, no separadores
        real_presets_count = sum(1 for p in all_presets if not p.startswith("---"))
        print(f"DEBUG: Total de presets y separadores encontrados: {len(all_presets)}")
        print(f"DEBUG: Total de presets REALES encontrados: {real_presets_count}")

        # 4. Actualizar el menú
        if all_presets:
            print(f"INFO: Configurando menú global con {real_presets_count} presets.")
            self.global_recode_preset_menu.configure(values=all_presets)
            # Intentar seleccionar el primer preset real (no un separador)
            first_valid_preset = next((p for p in all_presets if not p.startswith("---")), all_presets[0])
            self.global_recode_preset_menu.set(first_valid_preset)
        else:
            print("ADVERTENCIA: No se encontraron presets reales. Configurando menú a 'No hay presets'.")
            self.global_recode_preset_menu.configure(values=["- No hay presets -"], state="disabled")
            self.global_recode_preset_menu.set("- No hay presets -")
        
        print("--- DEBUG: Fin de _populate_global_preset_menu ---\n")

    def _on_global_recode_toggle(self):
        """Habilita/deshabilita el menú de preset global y aplica los cambios."""
        if self.global_recode_checkbox.get() == 1:
            self._populate_global_preset_menu()
            self.global_recode_preset_menu.configure(state="normal")
        else:
            self.global_recode_preset_menu.configure(state="disabled")
        
        # Aplicar la configuración a todos los jobs
        self._apply_global_recode_settings()

    def _apply_global_recode_settings(self, event=None):
        """
        Aplica la configuración de recodificación global a TODOS los jobs
        en la cola y actualiza la UI del job seleccionado.
        """
        is_enabled = self.global_recode_checkbox.get() == 1
        selected_preset_name = self.global_recode_preset_menu.get()
        
        if not selected_preset_name or selected_preset_name.startswith("---"):
            # Si no es un preset válido, desactiva la recodificación
            is_enabled = False

        preset_params = self._find_preset_params(selected_preset_name)
        if not preset_params:
             is_enabled = False # No se encontró el preset
             
        preset_mode = preset_params.get("mode_compatibility", "Video+Audio")
        preset_keep_original = preset_params.get("keep_original_file", True)

        print(f"--- APLICANDO CONFIGURACIÓN GLOBAL ---")
        print(f"Activado: {is_enabled}")
        print(f"Preset: {selected_preset_name}")
        print(f"Modo del Preset: {preset_mode}")
        
        # 1. Aplicar a todos los jobs en la lógica
        with self.queue_manager.jobs_lock:
            jobs_list = self.queue_manager.jobs 
            for job in jobs_list:
                job.config['recode_enabled'] = is_enabled
                job.config['recode_preset_name'] = selected_preset_name
                job.config['recode_keep_original'] = preset_keep_original
                
                # Forzar el modo del job para que coincida con el preset
                job.config['mode'] = preset_mode

        print(f"Configuración aplicada a {len(jobs_list)} jobs.")

        # 2. Refrescar la UI del job actualmente seleccionado (si hay uno)
        if self.selected_job_id:
            current_job = self.queue_manager.get_job_by_id(self.selected_job_id)
            if current_job:
                print(f"Refrescando UI para el job seleccionado: {self.selected_job_id[:6]}")
                # Usamos _populate_config_panel para recargar la UI del job
                # de forma segura, respetando el flag _updating_ui.
                self._populate_config_panel(current_job)

    def _set_local_batch_mode(self, is_local: bool):
        """Activa o desactiva la UI para el modo de recodificación local por lotes."""
        self.is_local_mode = is_local
        
        if is_local:
            print("INFO: Entrando en modo de Recodificación Local por Lotes.")
            
            # --- MODIFICADO ---
            # NO deshabilitar la URL entry
            # self.url_entry.configure(state="disabled") <--- LÍNEA ELIMINADA
            
            # Deshabilitar controles irrelevantes
            self.playlist_analysis_check.configure(state="disabled")
            self.auto_download_checkbox.configure(state="disabled")
            self.radio_normal.configure(state="disabled")
            self.radio_with_thumbnail.configure(state="disabled")
            self.radio_only_thumbnail.configure(state="disabled")
            
            # --- NUEVO: HABILITAR Recodificación Global ---
            self._populate_global_preset_menu() # Cargar presets
            self.global_recode_checkbox.configure(state="normal")
            if self.global_recode_checkbox.get() == 1:
                self.global_recode_preset_menu.configure(state="normal")

            # --- NUEVO: Cambiar color de botón ---
            self.start_queue_button.configure(
                text="Iniciar Proceso",
                fg_color=self.PROCESS_BTN_COLOR,
                hover_color=self.PROCESS_BTN_HOVER
            )
            
            # Forzar reseteo de la cola
            self.queue_manager.reset_progress()
            self.progress_label.configure(text="Modo Local. Listo para procesar.")
            
        else: # Volviendo a modo URL/Descarga
            print("INFO: Saliendo del modo local. Volviendo a modo Descarga.")
            
            # Habilitar todos los controles de URL
            self.url_entry.configure(state="normal") # <-- Asegurarse de que esté normal
            self.playlist_analysis_check.configure(state="normal")
            self.auto_download_checkbox.configure(state="normal")
            self.radio_normal.configure(state="normal")
            self.radio_with_thumbnail.configure(state="normal")
            self.radio_only_thumbnail.configure(state="normal")
            
            # --- NUEVO: Restablecer botón ---
            self.start_queue_button.configure(
                text="Iniciar Cola",
                fg_color=self.DOWNLOAD_BTN_COLOR,
                hover_color=self.DOWNLOAD_BTN_HOVER
            )

            self.progress_label.configure(text="Cola vacía. Analiza una URL para empezar.")

    def _show_import_menu(self):
        """Despliega un menú para elegir entre archivos o carpeta."""
        menu = Menu(self, tearoff=0)
        menu.add_command(label="Seleccionar Archivos...", command=self._on_import_local_files_click)
        menu.add_command(label="Escanear Carpeta Completa...", command=self._import_folder_action)
        
        # Mostrar debajo del botón
        try:
            x = self.import_button.winfo_rootx()
            y = self.import_button.winfo_rooty() + self.import_button.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _import_folder_action(self):
        """Pide una carpeta y lanza el escaneo en segundo plano."""
        folder_path = filedialog.askdirectory(title="Seleccionar carpeta para analizar")
        
        # Recuperar foco
        self.app.lift()
        self.app.focus_force()
        
        if not folder_path:
            return

        # Preparar UI
        if not self.is_local_mode:
            self._on_clear_list_click()
            self._set_local_batch_mode(True)
            
        if self.queue_placeholder_label.winfo_ismapped():
            self.queue_placeholder_label.pack_forget()

        print(f"INFO: Escaneando carpeta seleccionada: {folder_path}")
        
        # Reutilizar el hilo de escaneo que ya creamos para el Drop
        # pero envolviendo la ruta en una lista
        threading.Thread(
            target=self._scan_batch_drop_thread, # Reutilizamos la lógica de escaneo
            args=([folder_path],), # Pasamos la carpeta como una lista de 1 elemento
            daemon=True
        ).start()

    def _on_import_local_files_click(self):
        """
        Abre el diálogo para seleccionar múltiples archivos locales
        y los añade a la cola como trabajos de recodificación.
        """
        filetypes = [
            ("Archivos de Video", "*.mp4 *.mkv *.mov *.avi *.webm *.mts *.m2ts *.mxf"),
            ("Archivos de Audio", "*.mp3 *.wav *.m4a *.flac *.opus"),
            ("Todos los archivos", "*.*")
        ]
        
        # 1. Pedir al usuario los archivos
        filepaths = filedialog.askopenfilenames(
            title="Importar archivos locales para Recodificar en Lote",
            filetypes=filetypes
        )
        self.app.lift()
        self.app.focus_force()
        
        if not filepaths:
            print("INFO: Importación local cancelada por el usuario.")
            return

        # --- INICIO DE MODIFICACIÓN ---
        # 2. Comprobar si ya estamos en modo local. Si no, entrar.
        if not self.is_local_mode:
            # Si venimos del modo URL, SÍ limpiamos la cola.
            self._on_clear_list_click()
            self._set_local_batch_mode(True)
        # Si ya estábamos en modo local, simplemente añadimos trabajos.
        
        # 4. Olvidar el placeholder de "cola vacía"
        if self.queue_placeholder_label.winfo_ismapped():
            self.queue_placeholder_label.pack_forget()
            
        # 5. Lanzar el análisis de fondo
        print(f"INFO: Importando {len(filepaths)} archivos locales...")
        threading.Thread(
            target=self._run_local_file_analysis, 
            args=(filepaths,), 
            daemon=True
        ).start()

    def _run_local_file_analysis(self, filepaths: tuple[str]):
        """
        (Hilo de trabajo) Analiza cada archivo local con ffprobe y lo añade a la cola.
        """
        
        # --- OBTENER CONFIGURACIÓN GLOBAL DE RECODIFICACIÓN ---
        # (La copiamos de _on_analysis_complete)
        global_recode_enabled = self.global_recode_checkbox.get() == 1
        global_preset_name = self.global_recode_preset_menu.get()
        global_preset_params = self._find_preset_params(global_preset_name)
        
        if not global_preset_params or global_preset_name.startswith("---"):
            global_recode_enabled = False

        global_preset_mode = global_preset_params.get("mode_compatibility", "Video+Audio")
        global_keep_original = global_preset_params.get("keep_original_file", True)
        
        if global_recode_enabled:
            print(f"DEBUG: [Modo Local] Aplicando config global (Preset: {global_preset_name})")
        # --- FIN DE OBTENER CONFIGURACIÓN ---
            
        first_job_id = None
        
        for i, filepath in enumerate(filepaths):
            if not os.path.exists(filepath):
                print(f"ADVERTENCIA: El archivo {filepath} no existe. Omitiendo.")
                continue

            base_name = os.path.basename(filepath)
            
            # Crear un job temporal de "Analizando..."
            temp_config = {"title": f"Analizando: {base_name}", "local_file_path": filepath}
            temp_job = Job(config=temp_config, job_type="LOCAL_RECODE")
            self.queue_manager.add_job(temp_job)
            self.app.after(0, self.update_job_ui, temp_job.job_id, "RUNNING", f"Analizando {base_name}...")
            
            if i == 0:
                first_job_id = temp_job.job_id
            
            try:
                # 1. Analizar con ffprobe
                info_dict = self.app.ffmpeg_processor.get_local_media_info(filepath)
                
                # 2. Traducir la info
                analysis_data = self._translate_ffprobe_to_analysis_data(info_dict, filepath)
                
                # 3. Actualizar el job con la info real
                temp_job.analysis_data = analysis_data
                temp_job.config['title'] = analysis_data.get('title', base_name)
                
                # 4. Aplicar configuración de recodificación (global o por defecto)
                if global_recode_enabled:
                    temp_job.config['mode'] = global_preset_mode
                    temp_job.config['recode_enabled'] = True
                    temp_job.config['recode_preset_name'] = global_preset_name
                    temp_job.config['recode_keep_original'] = global_keep_original
                else:
                    # Por defecto, activamos la recodificación con el primer preset
                    # (Esto se puede cambiar, pero es un buen punto de partida)
                    temp_job.config['mode'] = "Video+Audio" # Asumir Video+Audio
                    temp_job.config['recode_enabled'] = False # <-- O False si prefieres
                    temp_job.config['recode_preset_name'] = "-"
                    temp_job.config['recode_keep_original'] = True

                # 5. Marcar como listo
                self.app.after(0, self.update_job_ui, temp_job.job_id, "PENDING", f"Listo para procesar: {base_name}")

            except Exception as e:
                print(f"ERROR: Falló el análisis local de {base_name}: {e}")
                self.app.after(0, self.update_job_ui, temp_job.job_id, "FAILED", f"Error al analizar: {e}")
        
        # Seleccionar el primer job importado
        if first_job_id:
            self.app.after(100, self._on_job_select, first_job_id)
            
        # Habilitar el botón de Iniciar Cola si hay trabajos
        if len(self.queue_manager.jobs) > 0:
            
            def _activate_buttons():
                self.start_queue_button.configure(
                    state="normal",
                    text="Iniciar Proceso",
                    fg_color=self.PROCESS_BTN_COLOR,
                    hover_color=self.PROCESS_BTN_HOVER
                )
                self.global_recode_checkbox.configure(state="normal")
                if self.global_recode_checkbox.get() == 1:
                    self.global_recode_preset_menu.configure(state="normal")

            # Usamos self.app.after para garantizar que se ejecute en el hilo principal
            self.app.after(0, _activate_buttons)
            if global_recode_enabled:
                self.app.after(0, self.global_recode_preset_menu.configure, {"state": "normal"})

    def _translate_ffprobe_to_analysis_data(self, ffprobe_info: dict, filepath: str) -> dict:
        """
        Convierte la salida de ffprobe (get_local_media_info) en un
        diccionario 'analysis_data' que imita la estructura de yt-dlp.
        """
        if not ffprobe_info:
            raise Exception("No se recibió información de ffprobe.")
            
        streams = ffprobe_info.get('streams', [])
        format_info = ffprobe_info.get('format', {})
        
        video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
        audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
        
        title = os.path.splitext(os.path.basename(filepath))[0]
        duration = float(format_info.get('duration', 0))
        
        # Crear la estructura de analysis_data
        analysis_data = {
            'title': title,
            'duration': duration,
            'formats': [],
            # Añadir info local para la recodificación
            'local_info': {
                'video_stream': video_stream,
                'audio_streams': audio_streams,
                'format': format_info
            }
        }
        
        # --- Lógica de 'single_download_tab' adaptada ---
        
        # 1. Añadir streams de video (si existen)
        if video_stream:
            v_codec = video_stream.get('codec_name', 'N/A')
            v_profile = video_stream.get('profile', 'N/A')
            v_width = video_stream.get('width', 0)
            v_height = video_stream.get('height', 0)
            v_fps_str = video_stream.get('r_frame_rate', '0/1')
            try:
                num, den = map(int, v_fps_str.split('/'))
                v_fps = float(num / den) if den > 0 else 0.0
            except Exception:
                v_fps = 0.0
                
            _, ext_with_dot = os.path.splitext(filepath)
            ext = ext_with_dot.lstrip('.')
            
            video_format_entry = {
                'format_id': f"local_video_{video_stream.get('index', 0)}",
                'vcodec': v_codec,
                'acodec': 'none', # Asumimos 'none' para video_only
                'ext': ext,
                'width': v_width,
                'height': v_height,
                'fps': v_fps,
                'is_combined': False,
                # Guardar el índice real de ffprobe
                'stream_index': video_stream.get('index') 
            }
            analysis_data['formats'].append(video_format_entry)

        # 2. Añadir streams de audio (si existen)
        for audio_stream in audio_streams:
            a_codec = audio_stream.get('codec_name', 'N/A')
            a_bitrate = int(audio_stream.get('bit_rate', 0)) // 1000 # Convertir a kbps
            
            audio_format_entry = {
                'format_id': f"local_audio_{audio_stream.get('index', 0)}",
                'vcodec': 'none',
                'acodec': a_codec,
                'abr': a_bitrate if a_bitrate > 0 else None,
                'tbr': a_bitrate if a_bitrate > 0 else None,
                'ext': a_codec, # Extensión simple
                'language': audio_stream.get('tags', {}).get('language'),
                # Guardar el índice real de ffprobe
                'stream_index': audio_stream.get('index')
            }
            analysis_data['formats'].append(audio_format_entry)

        return analysis_data
    
    def _format_bitrate(self, bitrate_str):
        """Convierte un bitrate en string a un formato legible (kbps o Mbps)."""
        if not bitrate_str: return "Bitrate N/A"
        try:
            bitrate = int(bitrate_str)
            if bitrate > 1_000_000:
                return f"{bitrate / 1_000_000:.2f} Mbps"
            elif bitrate > 1_000:
                return f"{bitrate / 1_000:.0f} kbps"
            return f"{bitrate} bps"
        except (ValueError, TypeError):
            return "Bitrate N/A"

    def _format_fps(self, fps_str):
        """Convierte una fracción de FPS (ej: '30000/1001') a un número decimal."""
        if not fps_str or '/' not in fps_str: return fps_str or "FPS N/A"
        try:
            num, den = map(int, fps_str.split('/'))
            if den == 0: return "FPS N/A"
            return f"{num / den:.2f}"
        except (ValueError, TypeError):
            return "FPS N/A"
        
    def _on_batch_drop(self, event):
        """
        Maneja archivos/carpetas soltados en la cola de lotes.
        """
        try:
            paths = self.tk.splitlist(event.data)
            if not paths: return

            print(f"INFO: Drop en Lotes detectado ({len(paths)} elementos). Escaneando...")
            
            # Feedback visual
            if self.queue_placeholder_label.winfo_ismapped():
                self.queue_placeholder_label.configure(text="Escaneando archivos...")

            # Lanzar hilo de escaneo
            threading.Thread(
                target=self._scan_batch_drop_thread,
                args=(paths,),
                daemon=True
            ).start()
            
        except Exception as e:
            print(f"ERROR en Batch Drag & Drop: {e}")

    def _scan_batch_drop_thread(self, paths):
        """
        (HILO) Escanea rutas buscando videos/audios válidos.
        Funciona para Drops y para Importar Carpeta.
        """
        valid_files = []
        # Extensiones permitidas
        valid_exts = self.app.VIDEO_EXTENSIONS.union(self.app.AUDIO_EXTENSIONS)
        
        try:
            for path in paths:
                path = path.strip('"')
                
                if os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower().lstrip('.')
                    if ext in valid_exts:
                        valid_files.append(path)
                
                elif os.path.isdir(path):
                    print(f"DEBUG: Escaneando carpeta: {path}")
                    for root, _, filenames in os.walk(path):
                        for f in filenames:
                            ext = os.path.splitext(f)[1].lower().lstrip('.')
                            if ext in valid_exts:
                                full_path = os.path.join(root, f)
                                valid_files.append(full_path)
            
            if valid_files:
                print(f"INFO: Se encontraron {len(valid_files)} archivos multimedia válidos.")
                self.app.after(0, self._handle_dropped_batch_files, valid_files)
            else:
                print("INFO: No se encontraron archivos multimedia válidos.")
                self.app.after(0, lambda: messagebox.showinfo("Sin resultados", "No se encontraron archivos de video/audio compatibles en la selección."))
                # Restaurar label si estaba vacío
                if not self.job_widgets:
                     self.app.after(0, lambda: self.queue_placeholder_label.pack(expand=True, pady=50, padx=20))

        except Exception as e:
            print(f"ERROR escaneando: {e}")

    def _handle_dropped_batch_files(self, filepaths):
        """
        (UI PRINCIPAL) Configura el modo local y lanza el análisis.
        """
        # 1. Si NO estamos en modo local, cambiar y limpiar la cola anterior
        if not self.is_local_mode:
            print("INFO: Drop detectado -> Cambiando a Modo Local automáticamente.")
            self._on_clear_list_click() # Limpiar residuos
            self._set_local_batch_mode(True) # Activar UI local
            
        # 2. Ocultar el placeholder
        if self.queue_placeholder_label.winfo_ismapped():
            self.queue_placeholder_label.pack_forget()
            
        # 3. Lanzar el análisis (reutilizamos tu función existente)
        threading.Thread(
            target=self._run_local_file_analysis, 
            args=(filepaths,), 
            daemon=True
        ).start()

    
