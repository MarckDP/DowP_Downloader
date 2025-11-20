import customtkinter as ctk
import queue
import os
import sys
import threading
import tkinter
import tempfile         
import requests         
import time  
import yt_dlp    
import time      
import gc
import uuid

from urllib.parse import urlparse 
from PIL import ImageGrab, Image   
from tkinter import Menu, messagebox
from tkinter import Menu
from customtkinter import filedialog
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.core.exceptions import UserCancelledError
from .dialogs import Tooltip, MultiPageDialog
from src.core.image_converter import ImageConverter
from src.core.image_processor import ImageProcessor
from src.core.constants import REMBG_MODEL_FAMILIES 
from main import REMBG_MODELS_DIR, MODELS_DIR

try:
    from tkinterdnd2 import DND_FILES
except ImportError:
    print("ERROR: tkinterdnd2 no encontrado en image_tools_tab")
    DND_FILES = None

class ImageToolsTab(ctk.CTkFrame):
    """
    Pestaña de Herramientas de Imagen, diseñada para la conversión
    y procesamiento de lotes grandes de archivos.
    """

    # Extensiones de entrada compatibles (¡puedes añadir más aquí!)
    # Combinamos raster, vector y otros formatos comunes
    COMPATIBLE_EXTENSIONS = (
        # Raster (Pillow)
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".avif",
        # Vectoriales (Ghostscript/Cairo)
        ".pdf", ".svg", ".eps", ".ai", ".ps",
        # Otros formatos (Pillow)
        ".psd", ".tga", ".jp2", ".ico",
        # Formatos de cámara (requieren plugins, pero Pillow intenta)
        ".cr2", ".nef", ".orf", ".dng"
    )
    
    # Colores de botones (copiados de tus otras pestañas para consistencia)
    PROCESS_BTN_COLOR = "#6F42C1"        
    PROCESS_BTN_HOVER = "#59369A"        
    DISABLED_TEXT_COLOR = "#D3D3D3"
    DISABLED_FG_COLOR = "#565b5f" 

    def __init__(self, master, app, poppler_path=None, inkscape_path=None): 
        super().__init__(master, fg_color="transparent")
        self.pack(expand=True, fill="both")
        
        self.app = app
        self.file_list_data = []

        # 🔧 NUEVO: Flag para sincronización con importación
        self.conversion_complete_event = threading.Event()

        # Crear la instancia del motor de procesamiento
        self.image_processor = ImageProcessor(poppler_path=poppler_path, 
                                            inkscape_path=inkscape_path)
        
        # Crear la instancia del conversor
        self.image_converter = ImageConverter(poppler_path=poppler_path,
                                            inkscape_path=inkscape_path,
                                            ffmpeg_processor=self.app.ffmpeg_processor)
        
        # Variable para rastrear la última miniatura solicitada
        self.last_preview_path = None
        
        # ⭐ Sistema de caché de miniaturas
        self.thumbnail_cache = {}
        self.thumbnail_queue = queue.Queue()
        self.active_thumbnail_thread = None
        self.thumbnail_lock = threading.Lock()

        self.temp_image_dir = self._get_temp_dir()
        self.is_analyzing_url = False
        self.last_processed_output_dir = None

        # --- 1. Diseño de la Rejilla Principal (3 Zonas) ---
        
        # Fila 0: Contenido principal (Izquierda 40%, Derecha 60%)
        self.grid_rowconfigure(0, weight=1)
        # Fila 1: Panel de Salida (Altura fija)
        self.grid_rowconfigure(1, weight=0)
        # Fila 2: Panel de Progreso (Altura fija)
        self.grid_rowconfigure(2, weight=0) 
        
        # ✅ CAMBIO: Pesos iguales (1 y 1) para dividir la pantalla al 50%
        # También aumenté un poco el minsize para que no se aplaste mucho.
        self.grid_columnconfigure(0, weight=1, minsize=350)
        self.grid_columnconfigure(1, weight=1, minsize=350)
        
        # --- 2. Crear los Paneles ---
        self._create_left_panel()
        self._create_right_panel()
        self._create_bottom_panel()
        self._create_progress_panel()

        # --- 3. Cargar Configuración Inicial ---
        self._initialize_ui_settings()

    # ==================================================================
    # --- CREACIÓN DE PANELES DE UI ---
    # ==================================================================

    def _create_left_panel(self):
        """Crea el panel izquierdo (40%) para la URL, botones y lista de archivos."""
        
        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.grid(row=0, column=0, padx=(10, 5), pady=(10, 5), sticky="nsew")
        
        # Expandir la fila 2 (donde va la lista) para que ocupe el espacio vertical
        self.left_panel.grid_rowconfigure(2, weight=1) 
        self.left_panel.grid_columnconfigure(0, weight=1)

        # --- 1. Zona de URL (Fila 0) ---
        self.url_frame = ctk.CTkFrame(self.left_panel)
        self.url_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)
        
        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="Pegar URL de imagen o PDF...")
        self.url_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.url_entry))
        self.url_entry.grid(row=0, column=0, padx=(0, 5), pady=0, sticky="ew")

        self.analyze_button = ctk.CTkButton(
            self.url_frame, text="Añadir", width=80, 
            command=self._on_analyze_url
        )
        self.analyze_button.grid(row=0, column=1, padx=(0, 0), pady=0)

        # --- 2. Barra de Herramientas Unificada (Fila 1) ---
        self.buttons_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.buttons_frame.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        
        # Configurar 4 columnas con peso igual
        self.buttons_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Botón 1: Importar (Con Menú)
        self.import_button = ctk.CTkButton(
            self.buttons_frame, 
            text="Importar ▼", 
            width=80,
            command=self._show_import_menu
        )
        self.import_button.grid(row=0, column=0, padx=(0, 3), sticky="ew")

        # Botón 2: Pegar
        self.paste_button = ctk.CTkButton(
            self.buttons_frame, 
            text="Pegar", 
            width=60,
            command=self._on_paste_list
        )
        self.paste_button.grid(row=0, column=1, padx=3, sticky="ew")
        
        # Botón 3: Limpiar
        self.clear_button = ctk.CTkButton(
            self.buttons_frame, 
            text="Limpiar", 
            width=60,
            command=self._on_clear_list
        )
        self.clear_button.grid(row=0, column=2, padx=3, sticky="ew")

        # Botón 4: Borrar (Rojo)
        self.delete_button = ctk.CTkButton(
            self.buttons_frame, 
            text="Borrar", 
            width=60,
            fg_color="#DC3545", 
            hover_color="#C82333",
            command=self._on_delete_selected, 
            state="disabled"
        )
        self.delete_button.grid(row=0, column=3, padx=(3, 0), sticky="ew")

        # --- 3. Zona de Lista de Archivos (Fila 2) ---
        # Frame contenedor que se expande
        self.list_frame = ctk.CTkFrame(self.left_panel)
        self.list_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.grid_rowconfigure(0, weight=1)

        # Scrollbar Vertical
        self.file_list_scrollbar_y = ctk.CTkScrollbar(self.list_frame)
        self.file_list_scrollbar_y.grid(row=0, column=1, sticky="ns")
        
        # Scrollbar Horizontal
        self.file_list_scrollbar_x = ctk.CTkScrollbar(self.list_frame, orientation="horizontal")
        self.file_list_scrollbar_x.grid(row=1, column=0, sticky="ew")

        # Listbox Nativo
        self.file_list_box = tkinter.Listbox(
            self.list_frame,
            font=ctk.CTkFont(size=12),
            bg="#1D1D1D",
            fg="#FFFFFF",
            selectbackground="#1F6AA5",
            selectforeground="#FFFFFF",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#565B5E",
            activestyle="none",
            selectmode="extended",
            exportselection=False,
            yscrollcommand=self.file_list_scrollbar_y.set,
            xscrollcommand=self.file_list_scrollbar_x.set,
        )
        self.file_list_box.grid(row=0, column=0, sticky="nsew")

        # Conectar scrollbars
        self.file_list_scrollbar_y.configure(command=self.file_list_box.yview)
        self.file_list_scrollbar_x.configure(command=self.file_list_box.xview)

        # Etiqueta de "Arrastra aquí" (Empty State)
        self.drag_hint_label = ctk.CTkLabel(
            self.list_frame,
            text="Arrastra archivos o carpetas aquí\no usa 'Importar Archivos'",
            text_color="gray",
            bg_color="#1D1D1D",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.drag_hint_label.place(relx=0.5, rely=0.5, anchor="center")

        # Configurar Drag & Drop
        if DND_FILES:
            try:
                # Registrar lista y etiqueta
                self.file_list_box.drop_target_register(DND_FILES)
                self.file_list_box.dnd_bind('<<Drop>>', self._on_image_list_drop)
                
                self.drag_hint_label.drop_target_register(DND_FILES)
                self.drag_hint_label.dnd_bind('<<Drop>>', self._on_image_list_drop)
                
                print("DEBUG: Drag & Drop activado en la lista de imágenes")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo activar DnD en la lista: {e}")

        # Bindings
        self.file_list_box.bind("<ButtonRelease-1>", self._on_file_select)
        self.file_list_box.bind("<Up>", self._on_file_select)
        self.file_list_box.bind("<Down>", self._on_file_select)
        self.file_list_box.bind("<Prior>", self._on_file_select)
        self.file_list_box.bind("<Next>", self._on_file_select)
        self.file_list_box.bind("<Home>", self._on_file_select)
        self.file_list_box.bind("<End>", self._on_file_select)
        self.file_list_box.bind("<Button-3>", self._create_list_context_menu)
        self.file_list_box.bind("<Delete>", self._on_delete_selected)
        self.file_list_box.bind("<BackSpace>", self._on_delete_selected)

        # --- 4. Etiqueta de Conteo (Fila 3) ---
        self.list_status_label = ctk.CTkLabel(self.left_panel, text="0 archivos", font=ctk.CTkFont(size=11), text_color="gray")
        self.list_status_label.grid(row=3, column=0, padx=10, pady=(0, 5), sticky="w")

    def _create_right_panel(self):
        """Crea el panel derecho (60%) para el visor y las opciones."""
        
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=0, column=1, padx=(5, 10), pady=(10, 5), sticky="nsew")

        self.right_panel.grid_rowconfigure(0, weight=40) # Visor (40% alto)
        self.right_panel.grid_rowconfigure(1, weight=0)  # Título (fijo)
        self.right_panel.grid_rowconfigure(2, weight=60) # Opciones (60% alto)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # --- 1. Zona de Visor (Fila 0) ---
        self.viewer_frame = ctk.CTkFrame(self.right_panel, fg_color="#1D1D1D")
        self.viewer_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="nsew")
        self.viewer_frame.grid_columnconfigure(0, weight=1)
        self.viewer_frame.grid_rowconfigure(0, weight=1)
        self.viewer_frame.grid_propagate(False) 

        self.viewer_placeholder = ctk.CTkLabel(
            self.viewer_frame, 
            text="Selecciona un archivo de la lista para previsualizarlo",
            text_color="gray"
        )
        self.viewer_placeholder.grid(row=0, column=0, sticky="nsew")

        # --- 2. Zona de Título (Fila 1) ---
        self.title_frame = ctk.CTkFrame(self.right_panel)
        self.title_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.title_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.title_frame, text="Título:").grid(row=0, column=0, padx=(10, 5))
        self.title_entry = ctk.CTkEntry(self.title_frame, placeholder_text="Nombre del archivo de salida...")
        self.title_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.title_entry))
        self.title_entry.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        # --- 3. Zona de Opciones (Fila 2) ---
        self.options_frame = ctk.CTkScrollableFrame(
            self.right_panel, 
            label_text="Opciones de Procesamiento"
        )
        self.options_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.options_frame.grid_columnconfigure(0, weight=1)
        
        
        # --- (INICIO DE LA CORRECCIÓN DE JERARQUÍA) ---
        
        # 3.1: Módulo "Cuadrito" Maestro de Formato
        # Usamos el color de fondo de las opciones para que se vea integrado
        self.format_master_frame = ctk.CTkFrame(self.options_frame, fg_color="#2B2B2B")
        self.format_master_frame.pack(fill="x", padx=5, pady=(5, 0))
        
        # 3.1a: Frame para el Menú (DENTRO del "cuadrito" maestro)
        self.format_menu_frame = ctk.CTkFrame(self.format_master_frame, fg_color="transparent")
        self.format_menu_frame.pack(fill="x", padx=5, pady=(5, 0)) # Padding interno
        self.format_menu_frame.grid_columnconfigure(1, weight=1) 

        self.format_label = ctk.CTkLabel(self.format_menu_frame, text="Formato de Salida:", width=120, anchor="w")
        self.format_label.grid(row=0, column=0, padx=(5, 5), pady=5, sticky="w") # Padding interno
        
        self.export_formats = [
            "No Convertir", 
            "PNG", "JPG", "WEBP", "AVIF", "PDF", "TIFF", "ICO", "BMP"
            "--- Video ---",
            ".mp4 (H.264)",
            ".mov (ProRes)",
            ".webm (VP9)",
            ".gif (Animado)"
        ]
        
        self.format_menu = ctk.CTkOptionMenu(
            self.format_menu_frame, 
            values=self.export_formats, 
            command=self._on_format_changed
        )
        self.format_menu.grid(row=0, column=1, padx=(0, 5), pady=5, sticky="ew") # Padding interno

        # --- NUEVO TOOLTIP ---
        Tooltip(self.format_menu, "Selecciona el formato de archivo final.\n• Nota: Formatos como JPG no soportan transparencia (se pondrá fondo blanco o el que elijas).", delay_ms=1000)

        # 3.1b: Contenedor de Opciones (DENTRO del "cuadrito" maestro)
        self.options_container = ctk.CTkFrame(self.format_master_frame, fg_color="transparent")
        self.options_container.pack(fill="x", expand=True, padx=5, pady=0, after=self.format_menu_frame)

        # 3.2: Separador (Sigue igual, entre los dos "cuadritos")
        ctk.CTkFrame(self.options_frame, height=2, fg_color="#333333").pack(fill="x", padx=10, pady=5)

        # 3.3: Módulo "Cuadrito" Maestro de Escalado (Sigue igual)
        self.resize_master_frame = ctk.CTkFrame(self.options_frame)
        self.resize_master_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.resize_master_frame.grid_columnconfigure(0, weight=1)

        self.resize_checkbox = ctk.CTkCheckBox(
            self.resize_master_frame,
            text="Cambiar Tamaño (Escalar)",
            command=self._on_toggle_resize_frame
        )
        self.resize_checkbox.pack(fill="x", padx=10, pady=5)

        # --- NUEVO TOOLTIP ---
        Tooltip(self.resize_checkbox, "Redimensiona la imagen a una resolución específica (ej: 1920x1080).\nÚtil para aumentar el tamaño de archivos vectoriales antes de convertirlos.", delay_ms=1000)

        self.resize_options_frame = ctk.CTkFrame(self.resize_master_frame, fg_color="transparent")
        self.resize_options_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.resize_options_frame, text="Preset de Escalado:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        self.resize_preset_menu = ctk.CTkOptionMenu(
            self.resize_options_frame,
            values=[
                "No escalar (Original)",
                "4K UHD (Máx: 3840×2160)",
                "2K QHD (Máx: 2560×1440)",
                "1080p FHD (Máx: 1920×1080)",
                "720p HD (Máx: 1280×720)",
                "480p SD (Máx: 854×480)",
                "Personalizado..."
            ],
            command=self._on_resize_preset_changed
        )
        self.resize_preset_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")

        # Menú de interpolación (solo para raster)
        self.interpolation_frame = ctk.CTkFrame(self.resize_options_frame, fg_color="transparent")
        self.interpolation_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.interpolation_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.interpolation_frame, text="Interpolación (Solo Rasters):").grid(row=0, column=0, padx=(10, 5), sticky="w")
        
        from src.core.constants import INTERPOLATION_METHODS
        self.interpolation_menu = ctk.CTkOptionMenu(
            self.interpolation_frame,
            values=list(INTERPOLATION_METHODS.keys())
        )
        self.interpolation_menu.set("Lanczos (Mejor Calidad)")
        self.interpolation_menu.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        Tooltip(self.interpolation_menu, "Método para reescalar imágenes raster (PNG, JPG). No afecta vectoriales.", delay_ms=500)
        
        # Ajustar la row del custom frame
        self.resize_custom_frame = ctk.CTkFrame(self.resize_options_frame, fg_color="transparent")
        self.resize_custom_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="ew")  # Cambiar de row=1 a row=2
        self.resize_custom_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(self.resize_custom_frame, text="Ancho:").grid(row=0, column=0, padx=(0, 5), sticky="e")
        self.resize_width_entry = ctk.CTkEntry(self.resize_custom_frame, width=80, placeholder_text="1920")
        self.resize_width_entry.grid(row=0, column=1, sticky="w")
        
        self.resize_aspect_lock = ctk.CTkCheckBox(
            self.resize_custom_frame, 
            text="",    
            width=28    
        )
        self.resize_aspect_lock.grid(row=0, column=2, padx=10, pady=5)
        self.resize_aspect_lock.select() 

        Tooltip(
            self.resize_aspect_lock, 
            text="Mantener Proporción", 
            delay_ms=100
        )
        
        ctk.CTkLabel(self.resize_custom_frame, text="Alto:").grid(row=0, column=3, padx=(0, 5), sticky="e")
        self.resize_height_entry = ctk.CTkEntry(self.resize_custom_frame, width=80, placeholder_text="1080")
        self.resize_height_entry.grid(row=0, column=4, sticky="w")

        # 3.4: Módulo "Cuadrito" Maestro de Canvas (después del de Resize)
        self.canvas_master_frame = ctk.CTkFrame(self.options_frame)
        self.canvas_master_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.canvas_master_frame.grid_columnconfigure(0, weight=1)

        self.canvas_checkbox = ctk.CTkCheckBox(
            self.canvas_master_frame,
            text="Ajustar Canvas (Lienzo)",
            command=self._on_toggle_canvas_frame
        )
        self.canvas_checkbox.pack(fill="x", padx=10, pady=5)

        # --- NUEVO TOOLTIP ---
        Tooltip(self.canvas_checkbox, "Cambia el tamaño del área de trabajo sin deformar la imagen.\nPermite añadir márgenes, bordes o centrar la imagen en un tamaño fijo (ej: Post de Instagram).", delay_ms=1000)

        self.canvas_options_frame = ctk.CTkFrame(self.canvas_master_frame, fg_color="transparent")
        self.canvas_options_frame.grid_columnconfigure(1, weight=1)

        # Opciones de Canvas
        ctk.CTkLabel(self.canvas_options_frame, text="Opciones de Canvas:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        
        from src.core.constants import CANVAS_OPTIONS
        self.canvas_option_menu = ctk.CTkOptionMenu(
            self.canvas_options_frame,
            values=CANVAS_OPTIONS,
            command=self._on_canvas_option_changed
        )
        self.canvas_option_menu.set("Sin ajuste")
        self.canvas_option_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")

        # Frame para margen (aparece con "Añadir Margen...")
        self.canvas_margin_frame = ctk.CTkFrame(self.canvas_options_frame, fg_color="transparent")
        self.canvas_margin_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(self.canvas_margin_frame, text="Margen:", width=80, anchor="w").grid(row=0, column=0, padx=(10, 5), sticky="w")
        self.canvas_margin_entry = ctk.CTkEntry(self.canvas_margin_frame, width=80, placeholder_text="100")
        self.canvas_margin_entry.insert(0, "100")
        self.canvas_margin_entry.grid(row=0, column=1, sticky="w", padx=(0, 5))
        ctk.CTkLabel(self.canvas_margin_frame, text="px").grid(row=0, column=2, sticky="w")

        # Tooltip explicativo
        Tooltip(
            self.canvas_margin_entry, 
            text="Espacio que se añadirá en cada lado de la imagen.\n"
                 "Ejemplo: 100px = 100px arriba + 100px abajo + 100px izquierda + 100px derecha.\n\n"
                 "• Margen Externo: El canvas crece (imagen + margen).\n"
                 "• Margen Interno: La imagen se reduce (canvas - margen).",
            delay_ms=1000
        )

        # Frame para dimensiones personalizadas (aparece con "Personalizado...")
        self.canvas_custom_frame = ctk.CTkFrame(self.canvas_options_frame, fg_color="transparent")
        self.canvas_custom_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.canvas_custom_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(self.canvas_custom_frame, text="Ancho:").grid(row=0, column=0, padx=(10, 5), sticky="e")
        self.canvas_width_entry = ctk.CTkEntry(self.canvas_custom_frame, width=80, placeholder_text="1080")
        self.canvas_width_entry.grid(row=0, column=1, sticky="w")
        
        ctk.CTkLabel(self.canvas_custom_frame, text="Alto:").grid(row=0, column=2, padx=(10, 5), sticky="e")
        self.canvas_height_entry = ctk.CTkEntry(self.canvas_custom_frame, width=80, placeholder_text="1080")
        self.canvas_height_entry.grid(row=0, column=3, sticky="w")

        # Posición del contenido
        ctk.CTkLabel(self.canvas_options_frame, text="Posición del contenido:").grid(row=2, column=0, padx=(10, 5), pady=5, sticky="w")
        
        from src.core.constants import CANVAS_POSITIONS
        self.canvas_position_menu = ctk.CTkOptionMenu(
            self.canvas_options_frame,
            values=CANVAS_POSITIONS
        )
        self.canvas_position_menu.set("Centro")
        self.canvas_position_menu.grid(row=2, column=1, padx=(0, 10), pady=5, sticky="ew")

        # Modo de overflow (solo visible para presets fijos y personalizado)
        self.canvas_overflow_frame = ctk.CTkFrame(self.canvas_options_frame, fg_color="transparent")
        self.canvas_overflow_frame.grid(row=3, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        self.canvas_overflow_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.canvas_overflow_frame, text="Si imagen excede espacio:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        
        from src.core.constants import CANVAS_OVERFLOW_MODES
        self.canvas_overflow_menu = ctk.CTkOptionMenu(
            self.canvas_overflow_frame,
            values=CANVAS_OVERFLOW_MODES
        )
        self.canvas_overflow_menu.set("Centrar (puede recortar)")
        self.canvas_overflow_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")

        # Ocultar todo por defecto
        self.canvas_options_frame.pack_forget()
        self.canvas_margin_frame.grid_forget()
        self.canvas_custom_frame.grid_forget()
        self.canvas_overflow_frame.grid_forget()
        
        self.option_frames = {}

        # 3.4.5: Módulo "Cuadrito" Maestro de Eliminar Fondo (IA)
        self.rembg_master_frame = ctk.CTkFrame(self.options_frame)
        self.rembg_master_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.rembg_master_frame.grid_columnconfigure(0, weight=1)

        self.rembg_checkbox = ctk.CTkCheckBox(
            self.rembg_master_frame,
            text="Eliminar Fondo (IA)",
            command=self._on_toggle_rembg_frame,
            fg_color="#E04F5F", hover_color="#C03949"
        )
        self.rembg_checkbox.pack(fill="x", padx=10, pady=5)

        Tooltip(self.rembg_checkbox, "Usa Inteligencia Artificial para eliminar el fondo automáticamente.\nRequiere descargar modelos adicionales.", delay_ms=1000)

        self.rembg_options_frame = ctk.CTkFrame(self.rembg_master_frame, fg_color="transparent")
        self.rembg_options_frame.grid_columnconfigure(1, weight=1)

        # --- MENÚ 1: FAMILIA ---
        ctk.CTkLabel(self.rembg_options_frame, text="Motor:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        
        self.rembg_family_menu = ctk.CTkOptionMenu(
            self.rembg_options_frame,
            values=list(REMBG_MODEL_FAMILIES.keys()),
            command=self._on_rembg_family_change
        )
        self.rembg_family_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")
        
        # --- MENÚ 2: MODELO ---
        ctk.CTkLabel(self.rembg_options_frame, text="Modelo:").grid(row=1, column=0, padx=(10, 5), pady=5, sticky="w")
        
        self.rembg_model_menu = ctk.CTkOptionMenu(
            self.rembg_options_frame,
            values=["-"], # Se llena dinámicamente
            command=self._on_rembg_model_change
        )
        self.rembg_model_menu.grid(row=1, column=1, padx=(0, 10), pady=5, sticky="ew")
        
        self.rembg_status_label = ctk.CTkLabel(self.rembg_options_frame, text="", font=ctk.CTkFont(size=10))
        self.rembg_status_label.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew")

        self.rembg_options_frame.pack_forget()
        
        # Inicializar menús con el default
        default_family = "Rembg Standard (U2Net)"
        self.rembg_family_menu.set(default_family)

        # 3.5: Módulo "Cuadrito" Maestro de Cambio de Fondo
        self.background_master_frame = ctk.CTkFrame(self.options_frame)
        self.background_master_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.background_master_frame.grid_columnconfigure(0, weight=1)

        self.background_checkbox = ctk.CTkCheckBox(
            self.background_master_frame,
            text="Cambiar Fondo (Transparente)",
            command=self._on_toggle_background_frame
        )
        self.background_checkbox.pack(fill="x", padx=10, pady=5)

        # --- NUEVO TOOLTIP ---
        Tooltip(self.background_checkbox, "Reemplaza las áreas transparentes de la imagen con un color sólido, un degradado o una imagen personalizada.", delay_ms=1000)

        self.background_options_frame = ctk.CTkFrame(self.background_master_frame, fg_color="transparent")
        self.background_options_frame.grid_columnconfigure(1, weight=1)

        # Tipo de fondo
        ctk.CTkLabel(self.background_options_frame, text="Tipo de Fondo:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        
        from src.core.constants import BACKGROUND_TYPES
        self.background_type_menu = ctk.CTkOptionMenu(
            self.background_options_frame,
            values=BACKGROUND_TYPES,
            command=self._on_background_type_changed
        )
        self.background_type_menu.set("Color Sólido")
        self.background_type_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")

        # Frame para Color Sólido
        self.bg_solid_frame = ctk.CTkFrame(self.background_options_frame, fg_color="transparent")
        self.bg_solid_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(self.bg_solid_frame, text="Color:", width=80, anchor="w").grid(row=0, column=0, padx=(10, 5), sticky="w")
        
        self.bg_color_button = ctk.CTkButton(
            self.bg_solid_frame, text="🎨", width=40,
            command=self._pick_solid_color
        )
        self.bg_color_button.grid(row=0, column=1, sticky="w", padx=(0, 5))
        
        self.bg_color_entry = ctk.CTkEntry(self.bg_solid_frame, width=100, placeholder_text="#FFFFFF")
        self.bg_color_entry.insert(0, "#FFFFFF")
        self.bg_color_entry.grid(row=0, column=2, sticky="w")
        
        Tooltip(self.bg_color_entry, "Color de fondo en formato hexadecimal (#RRGGBB)", delay_ms=1000)

        # Frame para Degradado
        self.bg_gradient_frame = ctk.CTkFrame(self.background_options_frame, fg_color="transparent")
        self.bg_gradient_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        # Color 1
        ctk.CTkLabel(self.bg_gradient_frame, text="Color 1:", width=80, anchor="w").grid(row=0, column=0, padx=(10, 5), sticky="w")
        self.bg_gradient_color1_button = ctk.CTkButton(
            self.bg_gradient_frame, text="🎨", width=40,
            command=lambda: self._pick_gradient_color(1)
        )
        self.bg_gradient_color1_button.grid(row=0, column=1, sticky="w", padx=(0, 5))
        self.bg_gradient_color1_entry = ctk.CTkEntry(self.bg_gradient_frame, width=100, placeholder_text="#FF0000")
        self.bg_gradient_color1_entry.insert(0, "#FF0000")
        self.bg_gradient_color1_entry.grid(row=0, column=2, sticky="w")
        
        # Color 2
        ctk.CTkLabel(self.bg_gradient_frame, text="Color 2:", width=80, anchor="w").grid(row=1, column=0, padx=(10, 5), pady=(5, 0), sticky="w")
        self.bg_gradient_color2_button = ctk.CTkButton(
            self.bg_gradient_frame, text="🎨", width=40,
            command=lambda: self._pick_gradient_color(2)
        )
        self.bg_gradient_color2_button.grid(row=1, column=1, sticky="w", padx=(0, 5), pady=(5, 0))
        self.bg_gradient_color2_entry = ctk.CTkEntry(self.bg_gradient_frame, width=100, placeholder_text="#0000FF")
        self.bg_gradient_color2_entry.insert(0, "#0000FF")
        self.bg_gradient_color2_entry.grid(row=1, column=2, sticky="w", pady=(5, 0))
        
        # Dirección
        ctk.CTkLabel(self.bg_gradient_frame, text="Dirección:", width=80, anchor="w").grid(row=2, column=0, padx=(10, 5), pady=(5, 0), sticky="w")
        
        from src.core.constants import GRADIENT_DIRECTIONS
        self.bg_gradient_direction_menu = ctk.CTkOptionMenu(
            self.bg_gradient_frame,
            values=GRADIENT_DIRECTIONS,
            width=200
        )
        self.bg_gradient_direction_menu.set("Horizontal (Izq → Der)")
        self.bg_gradient_direction_menu.grid(row=2, column=1, columnspan=2, sticky="w", pady=(5, 0))

        # Frame para Imagen de Fondo
        self.bg_image_frame = ctk.CTkFrame(self.background_options_frame, fg_color="transparent")
        self.bg_image_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.bg_image_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.bg_image_frame, text="Imagen:", width=80, anchor="w").grid(row=0, column=0, padx=(10, 5), sticky="w")
        self.bg_image_entry = ctk.CTkEntry(self.bg_image_frame, placeholder_text="Selecciona una imagen...")
        self.bg_image_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        self.bg_image_button = ctk.CTkButton(
            self.bg_image_frame, text="📁", width=40,
            command=self._select_background_image
        )
        self.bg_image_button.grid(row=0, column=2, sticky="w")

        # Ocultar todo por defecto
        self.background_master_frame.pack_forget()  # El módulo completo se oculta
        self.background_options_frame.pack_forget()
        self.bg_solid_frame.grid_forget()
        self.bg_gradient_frame.grid_forget()
        self.bg_image_frame.grid_forget()

        self._create_png_options()
        self._create_jpg_options()
        self._create_webp_options()
        self._create_avif_options()
        self._create_pdf_options()
        self._create_tiff_options()
        self._create_ico_options()
        self._create_bmp_options()
        
        # --- NUEVO: Crear el frame de opciones de Video ---
        self._create_video_options()
        
        # Mapear los formatos de video al mismo frame de opciones
        video_frame = self.option_frames.get("VIDEO")
        if video_frame:
            self.option_frames[".mp4 (H.264)"] = video_frame
            self.option_frames[".mov (ProRes)"] = video_frame
            self.option_frames[".webm (VP9)"] = video_frame
            self.option_frames[".gif (Animado)"] = video_frame

        self.resize_options_frame.pack_forget()
        self.resize_custom_frame.grid_forget()
        self.interpolation_frame.grid_forget()
        
        self._on_format_changed(self.format_menu.get())
        
    def _create_bottom_panel(self):
        """
        Crea el panel de salida inferior, copiando la estructura de 
        batch_download_tab.py (sin límite de velocidad).
        """
        self.bottom_panel = ctk.CTkFrame(self)
        self.bottom_panel.grid(row=1, column=0, columnspan=2, padx=10, pady=(5, 5), sticky="ew")
        
        # --- Fila 1 del panel (Ruta de salida) ---
        line1_frame = ctk.CTkFrame(self.bottom_panel, fg_color="transparent")
        line1_frame.pack(fill="x", padx=0, pady=(0, 5))
        line1_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(line1_frame, text="Carpeta de Salida:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        
        self.output_path_entry = ctk.CTkEntry(line1_frame, placeholder_text="Selecciona una carpeta...")
        self.output_path_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.output_path_entry))
        self.output_path_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.select_folder_button = ctk.CTkButton(
            line1_frame, text="...", width=40, 
            command=self.select_output_folder
        )
        self.select_folder_button.grid(row=0, column=2, padx=(0, 5), pady=5)
        
        self.open_folder_button = ctk.CTkButton(
            line1_frame, text="📁", width=40, font=ctk.CTkFont(size=16), 
            command=self._open_batch_output_folder, state="disabled"
        )
        self.open_folder_button.grid(row=0, column=3, padx=(0, 10), pady=5)
        
        # (Se omite el límite de velocidad, como se solicitó)

        # --- Fila 2 del panel (Opciones y Botón de Inicio) ---
        line2_frame = ctk.CTkFrame(self.bottom_panel, fg_color="transparent")
        line2_frame.pack(fill="x", padx=0, pady=0)
        line2_frame.grid_columnconfigure(5, weight=1) # Columna de espacio flexible
        
        conflict_label = ctk.CTkLabel(line2_frame, text="Si existe:")
        conflict_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")

        self.conflict_policy_menu = ctk.CTkOptionMenu(
            line2_frame, width=120,
            values=["Sobrescribir", "Renombrar", "Omitir"]
        )
        self.conflict_policy_menu.set("Renombrar")
        self.conflict_policy_menu.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")
        
        Tooltip(conflict_label, "Determina qué hacer si un archivo con el mismo nombre ya existe.", delay_ms=1000)
        Tooltip(self.conflict_policy_menu, "Determina qué hacer si un archivo con el mismo nombre ya existe.", delay_ms=1000)
        
        self.create_subfolder_checkbox = ctk.CTkCheckBox(
            line2_frame, text="Crear carpeta", 
            command=self._toggle_subfolder_name_entry
        )
        self.create_subfolder_checkbox.grid(row=0, column=2, padx=(5, 5), pady=5, sticky="w")
        Tooltip(self.create_subfolder_checkbox, "Guarda todos los archivos en una subcarpeta dedicada.", delay_ms=1000)

        self.subfolder_name_entry = ctk.CTkEntry(line2_frame, width=120, placeholder_text="DowP Imágenes")
        self.subfolder_name_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.subfolder_name_entry))
        self.subfolder_name_entry.grid(row=0, column=3, padx=(0, 10), pady=5, sticky="w")
        self.subfolder_name_entry.configure(state="disabled")
        
        # (Se omite Auto-descarga)
        
        self.auto_import_checkbox = ctk.CTkCheckBox(
            line2_frame, text="Import Adobe", 
            command=self.save_settings,
            text_color="#FFC792", fg_color="#C17B42", hover_color="#9A6336"
        )
        self.auto_import_checkbox.grid(row=0, column=4, padx=5, pady=5, sticky="w")
        Tooltip(self.auto_import_checkbox, "Importa automáticamente los archivos procesados a Premiere o After Effects.", delay_ms=1000)
        
        self.start_process_button = ctk.CTkButton(
            line2_frame, text="Iniciar Proceso", 
            state="disabled", command=self._on_start_process, 
            fg_color=self.PROCESS_BTN_COLOR, hover_color=self.PROCESS_BTN_HOVER, 
            text_color_disabled=self.DISABLED_TEXT_COLOR, width=140
        )
        self.start_process_button.grid(row=0, column=6, padx=(5, 10), pady=5, sticky="e") 

    def _create_progress_panel(self):
        """Crea el panel de progreso inferior."""
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Listo. Añade archivos para empezar.")
        self.progress_label.pack(pady=(5,0))
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0,5), padx=10, fill="x")


    # ==================================================================
    # --- LÓGICA DE OPCIONES DINÁMICAS (PANEL DERECHO) ---
    # ==================================================================

    def _on_format_changed(self, selected_format):
        """Oculta todos los frames de opciones y muestra solo el relevante."""
        
        # 1. Ocultar todos los frames de opciones específicas
        for frame in self.option_frames.values():
            if frame: frame.pack_forget()
        
        is_video_format = selected_format.startswith(".") or selected_format == "--- Video ---"
        
        if is_video_format:
            # Si es VIDEO: Deshabilitar Escalado y Canvas
            self.resize_checkbox.configure(state="disabled")
            self.canvas_checkbox.configure(state="disabled")
            self.background_checkbox.configure(state="normal")
        else: 
            # Si es IMAGEN ("PNG", "JPG", etc.) o "No Convertir": Habilitar todo
            self.resize_checkbox.configure(state="normal")
            self.canvas_checkbox.configure(state="normal")
            self.background_checkbox.configure(state="normal")


        # 2. Mostrar/Ocultar el contenedor de opciones y el frame correcto
        if selected_format == "No Convertir" or selected_format == "--- Video ---":
            self.options_container.pack_forget()
        else:
            self.options_container.pack(fill="x", expand=True, padx=5, pady=0, after=self.format_menu_frame)
            
            frame_to_show = self.option_frames.get(selected_format)
            if frame_to_show:
                frame_to_show.pack(fill="x", expand=True, padx=5, pady=5)
        
        # 3. Mostrar/ocultar el módulo de cambio de fondo
        from src.core.constants import FORMATS_WITH_TRANSPARENCY, IMAGE_INPUT_FORMATS

        show_background_module = False
        
        # Mostrar si es "No Convertir", video, o un formato de imagen transparente
        if selected_format == "No Convertir" or is_video_format:
            show_background_module = True
        elif selected_format in FORMATS_WITH_TRANSPARENCY:
            show_background_module = True
        
        if selected_format == "WEBP" and hasattr(self, 'webp_transparency') and self.webp_transparency.get() == 0:
            show_background_module = False
        if selected_format == "TIFF" and hasattr(self, 'tiff_transparency') and self.tiff_transparency.get() == 0:
            show_background_module = False
            
        if selected_format == "AVIF" and hasattr(self, 'avif_transparency') and self.avif_transparency.get() == 0:
            show_background_module = False

        if show_background_module:
            self.background_master_frame.pack(fill="x", padx=5, pady=(0, 5), after=self.canvas_master_frame)
        else:
            self.background_master_frame.pack_forget()

    def _create_slider_with_label(self, parent, text, min_val, max_val, default_val, step=1):
        """
        Helper para crear un slider con un label de valor numérico a la derecha.
        Cumple con tu requisito de UI.
        """
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=5, anchor="w")
        
        label = ctk.CTkLabel(frame, text=text, width=120, anchor="w") # Label a la izquierda
        label.pack(side="left")
        
        # Entry a la derecha (para mostrar el valor)
        value_entry = ctk.CTkEntry(frame, width=45, justify="center")
        value_entry.pack(side="right", padx=(10, 0))
        
        # Callback para actualizar el Entry en vivo
        def slider_callback(value):
            int_value = int(value / step) * step
            value_entry.configure(state="normal")
            value_entry.delete(0, "end")
            value_entry.insert(0, f"{int_value}")
            value_entry.configure(state="disabled") # Deshabilitado para que actúe como label
        
        slider = ctk.CTkSlider(
            frame, 
            from_=min_val, 
            to=max_val,
            number_of_steps=(max_val - min_val) // step if step != 0 else 100,
            command=slider_callback
        )
        slider.set(default_val)
        
        slider_callback(default_val) # Llamada inicial
        
        slider.pack(side="left", fill="x", expand=True) # Slider en el medio
        
        return slider, value_entry # Devolvemos los widgets por si los necesitamos

    def _create_png_options(self):
        """Crea el frame de opciones para PNG."""
        png_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        self.png_transparency = ctk.CTkCheckBox(png_frame, text="Mantener Transparencia")
        self.png_transparency.pack(fill="x", padx=10, pady=5)
        self.png_transparency.select() # Por defecto, mantener transparencia

        self.png_compression_slider, self.png_compression_label = self._create_slider_with_label(
            parent=png_frame,
            text="Compresión (0-9):",
            min_val=0, max_val=9, default_val=6, step=1
        )
        
        self.option_frames["PNG"] = png_frame

    def _create_jpg_options(self):
        """Crea el frame de opciones para JPG/JPEG."""
        jpg_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        self.jpg_quality_slider, self.jpg_quality_label = self._create_slider_with_label(
            parent=jpg_frame,
            text="Calidad (1-100):",
            min_val=1, max_val=100, default_val=90, step=1
        )
        
        sub_frame = ctk.CTkFrame(jpg_frame, fg_color="transparent")
        sub_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        ctk.CTkLabel(sub_frame, text="Subsampling Croma:", width=120, anchor="w").pack(side="left")
        self.jpg_subsampling = ctk.CTkOptionMenu(
            sub_frame, 
            values=["4:2:0 (Estándar)", "4:2:2 (Alta)", "4:4:4 (Máxima)"],
            width=200
        )
        self.jpg_subsampling.pack(side="left", fill="x", expand=True)

        self.jpg_progressive = ctk.CTkCheckBox(jpg_frame, text="Escaneo Progresivo (Web)")
        self.jpg_progressive.pack(fill="x", padx=10, pady=5)
        
        self.option_frames["JPG"] = jpg_frame
        self.option_frames["JPEG"] = jpg_frame # Ambos apuntan al mismo frame

    def _create_webp_options(self):
        """Crea el frame de opciones para WEBP."""
        webp_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        self.webp_lossless = ctk.CTkCheckBox(
            webp_frame, 
            text="Compresión sin Pérdida (Lossless)",
            command=self._toggle_webp_quality # Llama a la función de UI
        )
        self.webp_lossless.pack(fill="x", padx=10, pady=5)

        # Guardamos el frame del slider para poder ocultarlo/mostrarlo
        self.webp_quality_frame = ctk.CTkFrame(webp_frame, fg_color="transparent")
        self.webp_quality_frame.pack(fill="x", expand=True)
        
        self.webp_quality_slider, self.webp_quality_label = self._create_slider_with_label(
            parent=self.webp_quality_frame,
            text="Calidad (1-100):",
            min_val=1, max_val=100, default_val=90, step=1
        )

        self.webp_transparency = ctk.CTkCheckBox(
            webp_frame, 
            text="Mantener Transparencia",
            command=lambda: self._on_format_changed(self.format_menu.get())
        )
        self.webp_transparency.pack(fill="x", padx=10, pady=5)
        self.webp_transparency.select()

        self.webp_metadata = ctk.CTkCheckBox(webp_frame, text="Guardar Metadatos (EXIF, XMP)")
        self.webp_metadata.pack(fill="x", padx=10, pady=5)
        
        self.option_frames["WEBP"] = webp_frame

    def _create_avif_options(self):
        """Crea el frame de opciones para AVIF."""
        avif_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        self.avif_lossless = ctk.CTkCheckBox(
            avif_frame, 
            text="Sin Pérdida (Lossless)",
            command=self._toggle_avif_quality
        )
        self.avif_lossless.pack(fill="x", padx=10, pady=5)

        # Frame de Calidad (se oculta si es Lossless)
        self.avif_quality_frame = ctk.CTkFrame(avif_frame, fg_color="transparent")
        self.avif_quality_frame.pack(fill="x", expand=True)
        
        self.avif_quality_slider, _ = self._create_slider_with_label(
            parent=self.avif_quality_frame,
            text="Calidad (1-100):",
            min_val=1, max_val=100, default_val=80, step=1
        )

        # Slider de Velocidad (0-10)
        self.avif_speed_slider, _ = self._create_slider_with_label(
            parent=avif_frame,
            text="Velocidad (0-10):",
            min_val=0, max_val=10, default_val=6, step=1
        )
        Tooltip(self.avif_speed_slider, "Compresión: 0=Lento/Mejor, 10=Rápido/Peor. Default: 6", delay_ms=1000)

        self.avif_transparency = ctk.CTkCheckBox(
            avif_frame, 
            text="Mantener Transparencia",
            command=lambda: self._on_format_changed(self.format_menu.get())
        )
        self.avif_transparency.pack(fill="x", padx=10, pady=5)
        self.avif_transparency.select()
        
        self.option_frames["AVIF"] = avif_frame

    def _toggle_avif_quality(self):
        """Muestra u oculta slider calidad según lossless."""
        if self.avif_lossless.get() == 1:
            self.avif_quality_frame.pack_forget()
        else:
            self.avif_quality_frame.pack(fill="x", expand=True, after=self.avif_lossless)

    def _toggle_webp_quality(self):
        """Muestra u oculta el slider de calidad de WEBP."""
        if self.webp_lossless.get() == 1:
            # Si es Lossless, ocultar calidad
            self.webp_quality_frame.pack_forget()
        else:
            # Si NO es Lossless, mostrar calidad
            self.webp_quality_frame.pack(fill="x", expand=True, after=self.webp_lossless)
        # Actualizar visibilidad del módulo de fondo
        self._on_format_changed(self.format_menu.get())

    def _toggle_pdf_title_entry(self):
        """Muestra u oculta el entry de título del PDF combinado."""
        if self.pdf_combine.get() == 1:
            # Mostrar el campo de título
            self.pdf_title_frame.pack(fill="x", padx=10, pady=5, after=self.pdf_combine)
        else:
            # Ocultar el campo de título
            self.pdf_title_frame.pack_forget()

    def _on_toggle_canvas_frame(self):
        """Muestra u oculta el frame de opciones de canvas."""
        if self.canvas_checkbox.get() == 1:
            # Mostrar el frame de opciones
            self.canvas_options_frame.pack(fill="x", padx=5, pady=0, after=self.canvas_checkbox)
            # Aplicar la opción seleccionada actualmente
            self._on_canvas_option_changed(self.canvas_option_menu.get())
        else:
            # Ocultar todos los frames
            self.canvas_options_frame.pack_forget()
            self.canvas_margin_frame.grid_forget()
            self.canvas_custom_frame.grid_forget()
            self.canvas_overflow_frame.grid_forget()

    def _on_canvas_option_changed(self, selection):
        """Maneja el cambio de opción de canvas."""
        from src.core.constants import CANVAS_PRESET_SIZES
        
        # Ocultar todos los frames opcionales primero
        self.canvas_margin_frame.grid_forget()
        self.canvas_custom_frame.grid_forget()
        self.canvas_overflow_frame.grid_forget()
        
        if selection == "Sin ajuste":
            # No mostrar nada adicional
            pass
        
        elif selection in ["Añadir Margen Externo", "Añadir Margen Interno"]:
            # Mostrar campo de margen
            self.canvas_margin_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        elif selection == "Personalizado...":
            # Mostrar campos de dimensiones y overflow
            self.canvas_custom_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
            self.canvas_overflow_frame.grid(row=3, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        
        elif selection in CANVAS_PRESET_SIZES:
            # Preset fijo: llenar dimensiones y mostrar overflow
            width, height = CANVAS_PRESET_SIZES[selection]
            self.canvas_width_entry.delete(0, "end")
            self.canvas_width_entry.insert(0, str(width))
            self.canvas_height_entry.delete(0, "end")
            self.canvas_height_entry.insert(0, str(height))
            self.canvas_overflow_frame.grid(row=3, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
            print(f"Preset de canvas aplicado: {width}×{height}")

    def _on_toggle_background_frame(self):
        """Muestra u oculta el frame de opciones de fondo."""
        if self.background_checkbox.get() == 1:
            self.background_options_frame.pack(fill="x", padx=5, pady=0, after=self.background_checkbox)
            self._on_background_type_changed(self.background_type_menu.get())
        else:
            self.background_options_frame.pack_forget()
            self.bg_solid_frame.grid_forget()
            self.bg_gradient_frame.grid_forget()
            self.bg_image_frame.grid_forget()

    def _on_background_type_changed(self, selection):
        """Muestra el frame correspondiente al tipo de fondo seleccionado."""
        # Ocultar todos
        self.bg_solid_frame.grid_forget()
        self.bg_gradient_frame.grid_forget()
        self.bg_image_frame.grid_forget()
        
        # Mostrar el correcto
        if selection == "Color Sólido":
            self.bg_solid_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        elif selection == "Degradado":
            self.bg_gradient_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        elif selection == "Imagen de Fondo":
            self.bg_image_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

    def _pick_solid_color(self):
        """Abre un color picker para el fondo sólido."""
        try:
            from tkinter import colorchooser
            color = colorchooser.askcolor(title="Seleccionar Color de Fondo", initialcolor=self.bg_color_entry.get())
            if color[1]:  # color[1] es el valor hexadecimal
                self.bg_color_entry.delete(0, "end")
                self.bg_color_entry.insert(0, color[1].upper())
        except Exception as e:
            print(f"Error al abrir el color picker: {e}")

    def _pick_gradient_color(self, color_num):
        """Abre un color picker para el degradado."""
        try:
            from tkinter import colorchooser
            entry = self.bg_gradient_color1_entry if color_num == 1 else self.bg_gradient_color2_entry
            color = colorchooser.askcolor(title=f"Seleccionar Color {color_num}", initialcolor=entry.get())
            if color[1]:
                entry.delete(0, "end")
                entry.insert(0, color[1].upper())
        except Exception as e:
            print(f"Error al abrir el color picker: {e}")

    def _select_background_image(self):
        """Abre un diálogo para seleccionar una imagen de fondo."""
        from customtkinter import filedialog
        filepath = filedialog.askopenfilename(
            title="Seleccionar Imagen de Fondo",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("Todos los archivos", "*.*")
            ]
        )
        self.app.lift()
        self.app.focus_force()
        
        if filepath:
            self.bg_image_entry.delete(0, "end")
            self.bg_image_entry.insert(0, filepath)

    def _create_pdf_options(self):
        """Crea el frame de opciones para PDF."""
        pdf_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        self.pdf_combine = ctk.CTkCheckBox(
            pdf_frame, 
            text="Combinar todos en un solo PDF",
            command=self._toggle_pdf_title_entry
        )
        self.pdf_combine.pack(fill="x", padx=10, pady=5)
        
        # Frame para el título del PDF combinado
        self.pdf_title_frame = ctk.CTkFrame(pdf_frame, fg_color="transparent")
        self.pdf_title_frame.pack(fill="x", padx=10, pady=5)
        self.pdf_title_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.pdf_title_frame, text="Nombre del PDF:", width=120, anchor="w").grid(row=0, column=0, padx=(0, 5), sticky="w")
        
        self.pdf_combined_title_entry = ctk.CTkEntry(
            self.pdf_title_frame, 
            placeholder_text="combined_output"
        )
        self.pdf_combined_title_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.pdf_combined_title_entry))
        self.pdf_combined_title_entry.grid(row=0, column=1, sticky="ew")
        
        # Ocultar por defecto
        self.pdf_title_frame.pack_forget()
        
        self.option_frames["PDF"] = pdf_frame

    def _create_tiff_options(self):
        """Crea el frame de opciones para TIFF."""
        tiff_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        comp_frame = ctk.CTkFrame(tiff_frame, fg_color="transparent")
        comp_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        ctk.CTkLabel(comp_frame, text="Compresión:", width=120, anchor="w").pack(side="left")
        self.tiff_compression = ctk.CTkOptionMenu(
            comp_frame, 
            values=["Ninguna", "LZW (Recomendada)", "Deflate (ZIP)", "PackBits"],
            width=200
        )
        self.tiff_compression.set("LZW (Recomendada)")
        self.tiff_compression.pack(side="left", fill="x", expand=True)
        
        self.tiff_multipago = ctk.CTkCheckBox(tiff_frame, text="Guardar Multipágina (unir cola)")
        self.tiff_multipago.pack(fill="x", padx=10, pady=5)

        self.tiff_transparency = ctk.CTkCheckBox(
            tiff_frame, 
            text="Mantener Transparencia",
            command=lambda: self._on_format_changed(self.format_menu.get())
        )
        self.tiff_transparency.pack(fill="x", padx=10, pady=5)
        self.tiff_transparency.select()
        
        self.option_frames["TIFF"] = tiff_frame

    def _create_ico_options(self):
        """Crea el frame de opciones para ICO."""
        ico_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        ctk.CTkLabel(ico_frame, text="Tamaños a incluir en el .ico:").pack(fill="x", padx=10, pady=5)
        
        self.ico_sizes = {}
        sizes_frame = ctk.CTkFrame(ico_frame, fg_color="transparent")
        sizes_frame.pack(fill="x", padx=10, pady=5)
        sizes = [16, 32, 48, 64, 128, 256]
        
        # Configurar las columnas para que tengan un 'pad' (espaciado)
        # y peso para que se distribuyan uniformemente.
        sizes_frame.grid_columnconfigure((0, 1, 2), weight=1, pad=5)
        # --- FIN DE CORRECCIÓN ---

        for i, size in enumerate(sizes):
            # Colocar en 2 filas y 3 columnas
            row = i // 3
            col = i % 3
            
            chk = ctk.CTkCheckBox(sizes_frame, text=f"{size}x{size}")
            # Marcar 32 y 256 por defecto
            if size in [32, 256]:
                chk.select()
            
            # --- CORRECCIÓN ---
            # Quitar el 'padx' y 'pady' de aquí para que
            # el 'grid_columnconfigure' controle el espaciado.
            chk.grid(row=row, column=col, sticky="w")
            self.ico_sizes[size] = chk # Guardar el widget
            
        self.option_frames["ICO"] = ico_frame

    def _create_bmp_options(self):
        """Crea el frame de opciones para BMP."""
        bmp_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        self.bmp_rle = ctk.CTkCheckBox(bmp_frame, text="Comprimir (RLE)")
        self.bmp_rle.pack(fill="x", padx=10, pady=5)
        
        self.option_frames["BMP"] = bmp_frame

    # ==================================================================
    # --- NUEVA LÓGICA DE UI DE ESCALADO ---
    # ==================================================================

    def _on_toggle_resize_frame(self):
        """Muestra u oculta el frame de opciones de escalado."""
        if self.resize_checkbox.get() == 1:
            # Mostrar el frame de opciones
            self.resize_options_frame.pack(fill="x", padx=5, pady=0, after=self.resize_checkbox)
            # Asegurarse de que el frame "Personalizado" se muestre (o no)
            self._on_resize_preset_changed(self.resize_preset_menu.get())
            # Mostrar interpolación DESPUÉS de llamar al preset (para que siempre esté visible)
            if hasattr(self, 'interpolation_frame'):
                self.interpolation_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        else:
            # Ocultar todos los frames
            self.resize_options_frame.pack_forget()
            self.resize_custom_frame.grid_forget()
            if hasattr(self, 'interpolation_frame'):
                self.interpolation_frame.grid_forget()

    def _on_resize_preset_changed(self, selection):
        """Aplica el preset seleccionado o muestra el frame personalizado."""
        # Mapeo de presets a dimensiones (basado en el lado más largo)
        # Esto respeta la proporción de la imagen original
        preset_map = {
            "4K UHD (Máx: 3840×2160)": (3840, 2160),
            "2K QHD (Máx: 2560×1440)": (2560, 1440),
            "1080p FHD (Máx: 1920×1080)": (1920, 1080),
            "720p HD (Máx: 1280×720)": (1280, 720),
            "480p SD (Máx: 854×480)": (854, 480),
            "No escalar (Original)": None
        }
        
        if selection == "Personalizado...":
            # Mostrar campos personalizados
            self.resize_custom_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        else:
            # Ocultar campos personalizados
            self.resize_custom_frame.grid_forget()
            
            # Aplicar preset automáticamente
            if selection in preset_map:
                dimensions = preset_map[selection]
                if dimensions:
                    width, height = dimensions
                    # Llenar los campos (aunque estén ocultos, se usarán internamente)
                    self.resize_width_entry.delete(0, "end")
                    self.resize_width_entry.insert(0, str(width))
                    self.resize_height_entry.delete(0, "end")
                    self.resize_height_entry.insert(0, str(height))
                    
                    print(f"Preset aplicado: {width}×{height}")
                else:
                    # "No escalar" - limpiar campos
                    self.resize_width_entry.delete(0, "end")
                    self.resize_height_entry.delete(0, "end")

    # ==================================================================
    # --- FUNCIONES DE CONVERTIR A VIDEO ---
    # ==================================================================

    def _create_video_options(self):
        """Crea el frame de opciones para 'Convertir a Video'."""
        video_frame = ctk.CTkFrame(self.options_container, fg_color="#2B2B2B")
        
        # --- 0. NUEVO: Nombre del Video ---
        self.video_name_frame = ctk.CTkFrame(video_frame, fg_color="transparent")
        self.video_name_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        self.video_name_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.video_name_frame, text="Nombre Video:", width=120, anchor="w").grid(row=0, column=0, sticky="w")
        
        self.video_filename_entry = ctk.CTkEntry(
            self.video_name_frame, 
            placeholder_text="Opcional (Auto: Primera Imagen)"
        )
        self.video_filename_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.video_filename_entry))
        self.video_filename_entry.grid(row=0, column=1, sticky="ew")

        Tooltip(self.video_filename_entry, "Nombre del archivo de video final.\nSi lo dejas vacío, se usará el nombre de la primera imagen de la lista.", delay_ms=1000)
        
        # --- 1. Resolución ---
        self.res_frame = ctk.CTkFrame(video_frame, fg_color="transparent")
        self.res_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        self.res_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.res_frame, text="Resolución:", width=120, anchor="w").grid(row=0, column=0, sticky="w")
        
        # Inicializamos con valores temporales, se actualizará inmediatamente
        self.video_resolution_menu = ctk.CTkOptionMenu(
            self.res_frame,
            values=["Usar la primera (Auto)", "1920x1080 (1080p)"],
            command=self._on_video_resolution_changed
        )
        self.video_resolution_menu.grid(row=0, column=1, sticky="ew")

        # Frame para resolución personalizada
        self.video_custom_res_frame = ctk.CTkFrame(video_frame, fg_color="transparent")
        # Aquí le decimos que se empaquete DESPUÉS del frame de resolución
        self.video_custom_res_frame.pack(fill="x", padx=10, pady=0, anchor="w", after=self.res_frame)
        self.video_custom_res_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(self.video_custom_res_frame, text="Ancho:").grid(row=0, column=0, padx=(10, 5), sticky="e")
        self.video_custom_width_entry = ctk.CTkEntry(self.video_custom_res_frame, width=80, placeholder_text="1920")
        self.video_custom_width_entry.grid(row=0, column=1, sticky="w")
        
        ctk.CTkLabel(self.video_custom_res_frame, text="Alto:").grid(row=0, column=2, padx=(10, 5), sticky="e")
        self.video_custom_height_entry = ctk.CTkEntry(self.video_custom_res_frame, width=80, placeholder_text="1080")
        self.video_custom_height_entry.grid(row=0, column=3, sticky="w")
        
        # Ocultar frame personalizado por defecto
        self.video_custom_res_frame.pack_forget()
        
        # --- 2. FPS y Duración ---
        fps_frame = ctk.CTkFrame(video_frame, fg_color="transparent")
        fps_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        fps_frame.grid_columnconfigure((1, 3), weight=1)
        
        ctk.CTkLabel(fps_frame, text="FPS del Video:").grid(row=0, column=0, padx=(0, 5), sticky="e")
        self.video_fps_entry = ctk.CTkEntry(fps_frame, width=80, placeholder_text="30")
        self.video_fps_entry.insert(0, "30")
        self.video_fps_entry.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(fps_frame, text="Duración (frames):").grid(row=0, column=2, padx=(10, 5), sticky="e")
        self.video_frame_duration_entry = ctk.CTkEntry(fps_frame, width=80, placeholder_text="3")
        self.video_frame_duration_entry.insert(0, "3")
        self.video_frame_duration_entry.grid(row=0, column=3, sticky="w")
        Tooltip(self.video_frame_duration_entry, "Cuántos fotogramas durará cada imagen en pantalla.", delay_ms=1000)

        # --- 3. Modo de Ajuste ---
        fit_frame = ctk.CTkFrame(video_frame, fg_color="transparent")
        fit_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        fit_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(fit_frame, text="Modo de Ajuste:", width=120, anchor="w").grid(row=0, column=0, sticky="w")
        self.video_fit_mode_menu = ctk.CTkOptionMenu(
            fit_frame,
            values=[
                "Mantener Tamaño Original",
                "Ajustar al Fotograma (Barras)",
                "Ajustar al Marco (Recortar)",
            ]
        )
        self.video_fit_mode_menu.grid(row=0, column=1, sticky="ew")

        # Guardar el frame principal
        self.option_frames["VIDEO"] = video_frame

    def _on_video_resolution_changed(self, selection):
        """Muestra u oculta los campos de resolución de video personalizada."""
        # Si seleccionamos "Usar la primera...", ocultamos el personalizado
        if selection == "Personalizado...":
            self.video_custom_res_frame.pack(fill="x", padx=10, pady=0, anchor="w", after=self.res_frame)
        else:
            self.video_custom_res_frame.pack_forget()

    def _process_batch_as_video(self, output_dir, options):
        """
        Prepara la UI e inicia el hilo para la conversión a video.
        """
        # Validaciones específicas de video
        try:
            fps = int(options.get("video_fps", "30"))
            duration = int(options.get("video_frame_duration", "3"))
            if fps <= 0 or duration <= 0:
                raise ValueError("FPS y Duración deben ser positivos")
        except ValueError:
            messagebox.showerror("Valores Inválidos", "FPS y Duración (frames) deben ser números enteros positivos.")
            return

        if options["video_resolution"] == "Personalizado...":
            try:
                width = int(options.get("video_custom_width", "1920"))
                height = int(options.get("video_custom_height", "1080"))
                if width <= 0 or height <= 0:
                    raise ValueError("Dimensiones inválidas")
            except ValueError:
                messagebox.showerror("Resolución Inválida", "El Ancho y Alto personalizados deben ser números enteros positivos.")
                return

        # Preparar UI para procesamiento
        self.is_processing = True
        self.cancel_processing = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        
        self.start_process_button.configure(state="normal", text="Cancelar", 
                                        fg_color="#DC3545", hover_color="#C82333")
        self.import_button.configure(state="disabled")
        
        
        # Iniciar el hilo de video
        threading.Thread(
            target=self._video_thread_target,
            args=(output_dir, options),
            daemon=True
        ).start()

    def _video_thread_target(self, output_dir, options, cancel_event): # <-- ACEPTAR EVENTO
        """
        (HILO DE TRABAJO) Llama al conversor para crear el video
        y maneja los callbacks de la UI.
        """
        # 1. Definir el callback de progreso que el conversor usará
        def progress_callback(phase, progress_pct, message):
            if cancel_event.is_set(): # Chequeo rápido en el callback
                raise UserCancelledError("Proceso cancelado por el usuario.")

            if phase == "Standardizing":
                # Fase A: Estandarizando imágenes
                self.app.after(0, lambda: self.progress_label.configure(text=f"[Fase 1/2] Estandarizando: {message}"))
                self.app.after(0, lambda: self.progress_bar.set(progress_pct / 100.0 * 0.5)) # 0% a 50%
            
            elif phase == "Encoding":
                # Fase B: Codificando video
                self.app.after(0, lambda: self.progress_label.configure(text=f"[Fase 2/2] Codificando: {message}"))
                self.app.after(0, lambda: self.progress_bar.set(0.5 + (progress_pct / 100.0 * 0.5))) # 50% a 100%

        final_video_path = None
        try:
            
            # 1. Obtener el nombre personalizado
            custom_title = options.get("video_custom_title", "")
            
            if custom_title:
                # Si el usuario escribió algo, usarlo
                base_name = custom_title
            else:
                # Si está vacío, usar el nombre de la primera imagen
                if self.file_list_data:
                    first_file_path, _ = self.file_list_data[0]
                    base_name = os.path.splitext(os.path.basename(first_file_path))[0]
                    base_name += "_video" # Añadir sufijo para diferenciar
                else:
                    base_name = "video_output" # Fallback extremo (lista vacía)

            # 2. Sanitizar el nombre (quitar caracteres prohibidos)
            import re
            base_name = re.sub(r'[<>:"/\\|?*]', '_', base_name)
            
            # 3. Obtener extensión
            video_format_str = options.get("format")
            # Extraer extensión del string ".mp4 (H.264)" -> ".mp4"
            video_format_ext = video_format_str.split(" ")[0].lower() if video_format_str else ".mp4"
            
            output_filename = f"{base_name}{video_format_ext}"
            output_path = os.path.join(output_dir, output_filename)
            
            # 3. Manejar conflicto (El resto del código sigue igual)
            conflict_policy = self.conflict_policy_menu.get()
            if os.path.exists(output_path):
                action = self._handle_conflict(output_path, conflict_policy)
                if action == "skip":
                    raise Exception("Omitido: El archivo de video ya existe.")
                elif action == "rename":
                    output_path = self._get_unique_filename(output_path)
            
            # 4. Iniciar el proceso (esto es bloqueante)
            final_video_path = self.image_converter.create_video_from_images(
                file_data_list=self.file_list_data,
                output_path=output_path,
                options=options,
                progress_callback=progress_callback,
                cancellation_event=cancel_event # <-- PASAR EVENTO REAL
            )
            
            # 5. Importar a Adobe si está activado
            if not cancel_event.is_set() and self.auto_import_checkbox.get():
                self.app.after(500, self._import_to_adobe, [final_video_path])

            # 6. Mostrar resumen
            if not cancel_event.is_set():
                summary = f"✅ Video Creado: {os.path.basename(final_video_path)}"
                self.app.after(0, lambda s=summary: self.progress_label.configure(text=s))
                self.app.after(0, lambda: self.progress_bar.set(1.0))
                self.app.after(0, lambda: messagebox.showinfo("Proceso Completado", summary))
            else:
                self.app.after(0, lambda: self.progress_label.configure(text="⚠️ Proceso de video cancelado."))

        except UserCancelledError:
             self.app.after(0, lambda: self.progress_label.configure(text="⚠️ Proceso de video cancelado."))
        except Exception as e:
            error_msg = f"Error al crear video: {e}"
            print(f"ERROR: {error_msg}")
            self.app.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.app.after(0, lambda: self.progress_bar.set(0))
            
        finally:
            # REACTIVAR BOTONES Y RESTAURAR TEXTO
            self.is_processing = False
            
            # Restaurar botón de inicio
            self.app.after(0, lambda: self.start_process_button.configure(
                state="normal", text="Iniciar Proceso", 
                fg_color=self.PROCESS_BTN_COLOR, hover_color=self.PROCESS_BTN_HOVER))
            
            # ✅ CORRECCIÓN: Reactivar el botón único de importar
            if hasattr(self, 'import_button'):
                self.app.after(0, lambda: self.import_button.configure(state="normal"))

    # ==================================================================
    # --- FUNCIONES DE INICIALIZACIÓN Y LÓGICA (STUBS) ---
    # ==================================================================

    def _initialize_ui_settings(self):
        """Carga la configuración guardada en la UI al iniciar."""
        
        # 1. Rutas y Auto-Import (Código existente)
        image_path = self.app.image_output_path
        if image_path:
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, image_path)
            self.last_processed_output_dir = image_path 
            self.open_folder_button.configure(state="normal")
        else:
            try:
                from pathlib import Path
                downloads_path = str(Path.home() / "Downloads")
                self.output_path_entry.insert(0, downloads_path)
                self.app.image_output_path = downloads_path
                self.open_folder_button.configure(state="normal")
            except: pass
        
        if self.app.image_auto_import_saved:
            self.auto_import_checkbox.select()
        else:
            self.auto_import_checkbox.deselect()

        # 2. Cargar Herramientas de Imagen
        settings = getattr(self.app, 'image_settings', {})
        
        # --- CORRECCIÓN CRÍTICA: NO RETORNAR SI ESTÁ VACÍO ---
        # Antes había un "if not settings: return" aquí. Lo quitamos.
        # Si settings está vacío, usaremos diccionarios vacíos {} para cargar los defaults.
        # -----------------------------------------------------
        
        try:
            # -- Formato --
            saved_format = settings.get("format", "PNG") # Default PNG
            self.format_menu.set(saved_format)
            self._on_format_changed(saved_format)

            # -- Resize --
            res = settings.get("resize", {})
            if res.get("enabled"): self.resize_checkbox.select()
            else: self.resize_checkbox.deselect()
            
            if res.get("preset"): self.resize_preset_menu.set(res["preset"])
            if res.get("width"): 
                self.resize_width_entry.delete(0, 'end')
                self.resize_width_entry.insert(0, res["width"])
            if res.get("height"):
                self.resize_height_entry.delete(0, 'end')
                self.resize_height_entry.insert(0, res["height"])
            if res.get("lock"): self.resize_aspect_lock.select()
            else: self.resize_aspect_lock.deselect()
            if res.get("interpolation"): self.interpolation_menu.set(res["interpolation"])
            
            self._on_toggle_resize_frame()
            # Solo aplicar preset si hay uno guardado, si no, dejar default
            if res.get("preset"):
                self._on_resize_preset_changed(res.get("preset"))

            # -- Canvas --
            can = settings.get("canvas", {})
            if can.get("enabled"): self.canvas_checkbox.select()
            else: self.canvas_checkbox.deselect()
            
            if can.get("option"): self.canvas_option_menu.set(can["option"])
            if can.get("margin"):
                self.canvas_margin_entry.delete(0, 'end')
                self.canvas_margin_entry.insert(0, can["margin"])
            if can.get("width"):
                self.canvas_width_entry.delete(0, 'end')
                self.canvas_width_entry.insert(0, can["width"])
            if can.get("height"):
                self.canvas_height_entry.delete(0, 'end')
                self.canvas_height_entry.insert(0, can["height"])
            if can.get("position"): self.canvas_position_menu.set(can["position"])
            if can.get("overflow"): self.canvas_overflow_menu.set(can["overflow"])
            
            self._on_toggle_canvas_frame()

            # -- Background --
            bg = settings.get("background", {})
            if bg.get("enabled"): self.background_checkbox.select()
            else: self.background_checkbox.deselect()
            
            if bg.get("type"): self.background_type_menu.set(bg["type"])
            if bg.get("color"):
                self.bg_color_entry.delete(0, 'end')
                self.bg_color_entry.insert(0, bg["color"])
            if bg.get("grad_c1"):
                self.bg_gradient_color1_entry.delete(0, 'end')
                self.bg_gradient_color1_entry.insert(0, bg["grad_c1"])
            if bg.get("grad_c2"):
                self.bg_gradient_color2_entry.delete(0, 'end')
                self.bg_gradient_color2_entry.insert(0, bg["grad_c2"])
            if bg.get("direction"): self.bg_gradient_direction_menu.set(bg["direction"])
            
            self._on_toggle_background_frame()

            # -- Rembg (IA) --
            # CORRECCIÓN: Asegurar inicialización incluso sin settings
            rem = settings.get("rembg", {})
            if rem.get("enabled"): self.rembg_checkbox.select()
            else: self.rembg_checkbox.deselect()
            
            # 1. Obtener familia (guardada o default)
            saved_family = rem.get("family", "Rembg Standard (U2Net)")
            self.rembg_family_menu.set(saved_family)
            
            # 2. CRÍTICO: Forzar la población del menú de modelos AHORA
            # Esto llenará el segundo menú con los valores correctos
            self._on_rembg_family_change(saved_family) 
            
            # 3. Establecer el modelo específico (si existe)
            saved_model = rem.get("model")
            if saved_model:
                # Verificar que el modelo existe en la lista recién poblada
                current_values = self.rembg_model_menu.cget("values")
                if current_values and saved_model in current_values:
                    self.rembg_model_menu.set(saved_model)
                    
                    # CORRECCIÓN: Usar modo silencioso para no molestar al iniciar
                    self._on_rembg_model_change(saved_model, silent=True)
            
            self._on_toggle_rembg_frame()
            
        except Exception as e:
            print(f"ERROR al restaurar configuración de imágenes: {e}")

    def save_settings(self):
        """Guarda la configuración de esta pestaña en la app principal."""
        if not hasattr(self, 'app'):
            return
            
        # Guardar ruta y auto-import (ya existían)
        self.app.image_output_path = self.output_path_entry.get()
        if hasattr(self, 'auto_import_checkbox'):
             self.app.image_auto_import_saved = self.auto_import_checkbox.get() == 1
        
        # --- NUEVO: Guardar estado de herramientas ---
        current_settings = {
            "format": self.format_menu.get(),
            
            "resize": {
                "enabled": self.resize_checkbox.get(),
                "preset": self.resize_preset_menu.get(),
                "width": self.resize_width_entry.get(),
                "height": self.resize_height_entry.get(),
                "lock": self.resize_aspect_lock.get(),
                "interpolation": self.interpolation_menu.get()
            },
            
            "canvas": {
                "enabled": self.canvas_checkbox.get(),
                "option": self.canvas_option_menu.get(),
                "margin": self.canvas_margin_entry.get(),
                "width": self.canvas_width_entry.get(),
                "height": self.canvas_height_entry.get(),
                "position": self.canvas_position_menu.get(),
                "overflow": self.canvas_overflow_menu.get()
            },
            
            "background": {
                "enabled": self.background_checkbox.get(),
                "type": self.background_type_menu.get(),
                "color": self.bg_color_entry.get(),
                "grad_c1": self.bg_gradient_color1_entry.get(),
                "grad_c2": self.bg_gradient_color2_entry.get(),
                "direction": self.bg_gradient_direction_menu.get()
                # No guardamos la ruta de imagen de fondo porque puede cambiar/borrarse
            },
            
            "rembg": {
                "enabled": self.rembg_checkbox.get(),
                "family": self.rembg_family_menu.get(),
                "model": self.rembg_model_menu.get()
            }
        }
        
        # Enviar a la app principal
        self.app.image_settings = current_settings

    # ==================================================================
    # --- LÓGICA DE LA LISTA DE ARCHIVOS (PANEL IZQUIERDO) ---
    # ==================================================================

    def _get_temp_dir(self):
        """Crea y devuelve un directorio temporal dedicado para imágenes web."""
        try:
            path = os.path.join(tempfile.gettempdir(), "dowp_images")
            os.makedirs(path, exist_ok=True)
            print(f"INFO: Carpeta temporal de imágenes en: {path}")
            return path
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo crear la carpeta temporal, usando 'temp': {e}")
            return tempfile.gettempdir()

    def _on_analyze_url(self):
        """Inicia el hilo de análisis de URL."""
        url = self.url_entry.get().strip()
        if not url or self.is_analyzing_url:
            return

        self.is_analyzing_url = True
        self.analyze_button.configure(state="disabled", text="...")
        self.progress_label.configure(text=f"Analizando URL: {url[:50]}...")
        
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()

        # Iniciar el análisis en un hilo para no congelar la UI
        threading.Thread(
            target=self._analyze_url_thread,
            args=(url,),
            daemon=True
        ).start()

    def _get_thumbnail_from_url(self, url):
        """
        (HILO DE TRABAJO) Llama a yt-dlp con opciones GENÉRICAS
        para extraer solo la miniatura.
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'noplaylist': True,
            'ignoreerrors': True,
            'timeout': 20, # 20 segundos de tiempo límite
        }
        
        # Re-usar la lógica de cookies de la pestaña de descarga única
        # (Esto es crucial para videos privados o con restricción de edad)
        try:
            single_tab = self.app.single_tab
            cookie_mode = single_tab.cookie_mode_menu.get()
            
            if cookie_mode == "Archivo Manual..." and single_tab.cookie_path_entry.get():
                ydl_opts['cookiefile'] = single_tab.cookie_path_entry.get()
            elif cookie_mode != "No usar":
                browser_arg = single_tab.browser_var.get()
                profile = single_tab.browser_profile_entry.get()
                if profile:
                    browser_arg += f":{profile}"
                ydl_opts['cookiesfrombrowser'] = (browser_arg,)
        except Exception as e:
            print(f"ADVERTENCIA: No se pudieron cargar las cookies: {e}")

        try:
            # Extraer información
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info or not info.get('thumbnail'):
                return None, "No se encontró miniatura (info dict vacío)."
                
            # Éxito: retorna la URL de la miniatura
            return info.get('thumbnail'), None 

        except Exception as e:
            print(f"DEBUG: _get_thumbnail_from_url falló: {e}")
            return None, str(e)

    def _analyze_url_thread(self, url):
        """
        (Hilo de trabajo) Implementa la lógica híbrida:
        1. Intenta descargar como imagen directa.
        2. Si falla, usa yt-dlp para obtener la miniatura.
        """
        try:
            # --- Opción 1: Intentar como imagen directa ---
            direct_image_exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg', '.pdf')
            parsed_path = urlparse(url).path
            
            # --- CORRECCIÓN: Generar nombre ÚNICO ---
            original_name = os.path.basename(parsed_path)
            name, ext = os.path.splitext(original_name)
            if not ext: ext = ".jpg" # Fallback si no hay extensión
            
            # Crear nombre único: nombre_uuid.ext
            unique_suffix = str(uuid.uuid4())[:8]
            filename = f"{name}_{unique_suffix}{ext}"
            # ----------------------------------------
            
            if url.lower().endswith(direct_image_exts):
                print(f"INFO: Detectada URL de imagen directa: {filename}")
                temp_filepath = os.path.join(self.temp_image_dir, filename)
                
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                with open(temp_filepath, 'wb') as f:
                    f.write(response.content)
                
                self.app.after(0, self._process_imported_files, [temp_filepath])
                self.app.after(0, lambda fn=filename: self.progress_label.configure(text=f"Añadido: {fn}"))
                self.app.after(0, lambda: self.progress_bar.set(1.0))
            
            else:
                # --- Opción 2: Es una página multimedia (usar yt-dlp) ---
                print(f"INFO: URL no directa. Usando yt-dlp para buscar miniatura...")
                self.app.after(0, lambda: self.progress_label.configure(text="Buscando miniatura con yt-dlp..."))
                
                thumbnail_url, error_msg = self._get_thumbnail_from_url(url)
                
                if error_msg or not thumbnail_url:
                    if error_msg and "is not a valid URL" in error_msg:
                         raise Exception(f"La URL no es válida: {url[:50]}...")
                    raise Exception(error_msg or "No se encontró una miniatura en esta URL.")

                # --- CORRECCIÓN: Generar nombre ÚNICO para la miniatura ---
                original_thumb_name = os.path.basename(urlparse(thumbnail_url).path)
                if '?' in original_thumb_name:
                    original_thumb_name = original_thumb_name.split('?')[0]
                
                name, ext = os.path.splitext(original_thumb_name)
                if not ext: ext = ".jpg"
                
                # Crear nombre único: thumbnail_timestamp_uuid.ext
                # Esto evita que 'maxresdefault.jpg' se repita
                unique_id = f"{int(time.time())}_{str(uuid.uuid4())[:6]}"
                thumb_filename = f"{name}_{unique_id}{ext}"
                # ----------------------------------------------------------

                print(f"INFO: Miniatura encontrada. Descargando como: {thumb_filename}")
                temp_filepath = os.path.join(self.temp_image_dir, thumb_filename)
                
                response = requests.get(thumbnail_url, timeout=10)
                response.raise_for_status()
                
                with open(temp_filepath, 'wb') as f:
                    f.write(response.content)
                
                self.app.after(0, self._process_imported_files, [temp_filepath])
                self.app.after(0, lambda tfn=thumb_filename: self.progress_label.configure(text=f"Añadida miniatura: {tfn}"))
                self.app.after(0, lambda: self.progress_bar.set(1.0))

        except Exception as e:
            print(f"ERROR: No se pudo añadir desde URL: {e}")
            error_msg = str(e) 
            self.app.after(0, lambda: self.progress_label.configure(text=f"Error: {error_msg}"))
            self.app.after(0, lambda: self.progress_bar.set(0))
        
        finally:
            self.is_analyzing_url = False
            self.app.after(0, lambda: self.analyze_button.configure(state="normal", text="Añadir"))
            self.app.after(0, lambda: self.url_entry.delete(0, "end"))
            
            self.app.after(0, self.progress_bar.stop)
            self.app.after(0, lambda: self.progress_bar.configure(mode="determinate"))

    def _on_image_list_drop(self, event):
        """
        Maneja archivos Y carpetas soltados.
        Lanza un hilo para no congelar la UI si la carpeta es grande.
        """
        try:
            # Obtener las rutas crudas
            paths = self.tk.splitlist(event.data)
            
            if not paths:
                return

            print(f"INFO: Drop detectado con {len(paths)} elementos. Iniciando escaneo...")
            
            # Mostrar feedback visual inmediato
            if hasattr(self, 'list_status_label'):
                self.list_status_label.configure(text="⏳ Escaneando carpeta(s)...")
            
            # IMPORTANTE: Lanzar el escaneo en un hilo aparte
            # para no congelar la ventana si la carpeta es gigante
            threading.Thread(
                target=self._scan_and_import_dropped_paths,
                args=(paths,),
                daemon=True
            ).start()
            
        except Exception as e:
            print(f"ERROR en Drag & Drop: {e}")
            import traceback
            traceback.print_exc()

    def _on_import_files(self):
        """Abre el diálogo para seleccionar MÚLTIPLES ARCHIVOS."""
        filetypes = [
            ("Archivos de Imagen Compatibles", " ".join(self.COMPATIBLE_EXTENSIONS)),
            ("Todos los archivos", "*.*")
        ]
        
        filepaths = filedialog.askopenfilenames(
            title="Importar Archivos de Imagen",
            filetypes=filetypes
        )
        self.app.lift()
        self.app.focus_force()
        
        if filepaths:
            print(f"INFO: Importando {len(filepaths)} archivos...")
            self._process_imported_files(filepaths)

    def _on_import_folder(self):
        """Abre el diálogo para seleccionar UNA CARPETA y la escanea recursivamente."""
        folder_path = filedialog.askdirectory(
            title="Importar Carpeta (se escaneará recursivamente)"
        )
        self.app.lift()
        self.app.focus_force()
        
        if not folder_path:
            return

        print(f"INFO: Escaneando carpeta: {folder_path}")
        self._toggle_import_buttons("disabled") # Deshabilitar botones
        self.list_status_label.configure(text="Escaneando carpeta...")
        
        # Iniciar el escaneo en un hilo separado para no congelar la UI
        threading.Thread(
            target=self._search_folder_thread, 
            args=(folder_path,), 
            daemon=True
        ).start()

    def _show_import_menu(self):
        """Despliega el menú de opciones de importación."""
        menu = Menu(self, tearoff=0)
        menu.add_command(label="Seleccionar Archivos...", command=self._on_import_files)
        menu.add_command(label="Escanear Carpeta...", command=self._on_import_folder)
        
        # Calcular posición debajo del botón
        try:
            x = self.import_button.winfo_rootx()
            y = self.import_button.winfo_rooty() + self.import_button.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _process_imported_files(self, filepaths):
        """
        Procesa una lista de archivos. Muestra el diálogo de multi-página
        si es necesario antes de añadirlos a la lista.
        """
        files_to_add = [] # Esta será la lista de (filepath, page_num)
        
        for path in filepaths:
            # 1. Usar el "Radar" para contar páginas
            page_count = self.image_processor.get_document_page_count(path)
            
            if page_count == 1:
                # 2a. Si solo tiene 1 página, añadirlo como antes
                files_to_add.append( (path, 1) )
                
            else:
                # 2b. Si tiene múltiples páginas, mostrar el diálogo
                filename = os.path.basename(path)
                dialog = MultiPageDialog(self, filename, page_count)
                range_string = dialog.get_result() # Esto PAUSA la función
                
                if range_string:
                    # 3. El usuario aceptó. Parsear el rango.
                    page_numbers = self._parse_page_range(range_string, page_count)
                    
                    if not page_numbers:
                        messagebox.showerror("Rango Inválido", f"El rango '{range_string}' no es válido.", parent=self)
                        continue # Saltar este archivo

                    # 4. Añadir cada página como un item separado
                    for page_num in page_numbers:
                        files_to_add.append( (path, page_num) )
        
        # 5. Añadir todos los items recopilados a la lista de la UI
        if files_to_add:
            self._add_files_to_list(files_to_add)

    def _parse_page_range(self, range_string, max_pages):
        """
        Convierte un string como "1-3, 5, 8-10" en una lista [1, 2, 3, 5, 8, 9, 10].
        """
        pages = set()
        try:
            parts = range_string.split(',')
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                if '-' in part:
                    # Es un rango (ej: "5-10")
                    start_str, end_str = part.split('-')
                    start = int(start_str.strip())
                    end = int(end_str.strip())
                    
                    if start <= 0 or end > max_pages or start > end:
                        raise ValueError(f"Rango inválido {start}-{end}")
                        
                    for i in range(start, end + 1):
                        pages.add(i)
                else:
                    # Es un número único (ej: "8")
                    page = int(part)
                    if page <= 0 or page > max_pages:
                         raise ValueError(f"Página inválida {page}")
                    pages.add(page)
                    
            return sorted(list(pages))
        except Exception as e:
            print(f"Error parseando el rango '{range_string}': {e}")
            return None # Devuelve None si hay un error

    def _search_folder_thread(self, folder_path):
        """(Hilo de trabajo) Recorre recursivamente la carpeta y encuentra archivos."""
        found_files = []
        try:
            for root, _, files in os.walk(folder_path, topdown=True):
                for file in files:
                    # Comprobar si la extensión es compatible
                    if file.lower().endswith(self.COMPATIBLE_EXTENSIONS):
                        full_path = os.path.join(root, file)
                        found_files.append(full_path)
        except Exception as e:
            print(f"ERROR: Falló el escaneo de carpeta: {e}")
            
        print(f"INFO: Escaneo completo. Se encontraron {len(found_files)} archivos.")
        
        # Enviar los archivos encontrados de vuelta al hilo principal (UI)
        if found_files:
            # En lugar de llamar a _add_files_to_list, el hilo
            # llama al nuevo procesador en la UI principal
            self.app.after(0, self._process_imported_files, found_files)
        
        # Reactivar botones en el hilo principal
        self.app.after(0, self._toggle_import_buttons, "normal")

    def _toggle_import_buttons(self, state):
        """Habilita o deshabilita el botón de menú de importación."""
        if hasattr(self, 'import_button'):
            self.import_button.configure(state=state)

    def _on_paste_list(self):
        """
        Pega el contenido del portapapeles.
        Prioridad 1: Datos de imagen (pixeles).
        Prioridad 2: Texto (rutas de archivo).
        """
        try:
            # --- Prioridad 1: Intentar obtener DATOS DE IMAGEN ---
            img = ImageGrab.grabclipboard()
            
            if img:
                print("INFO: Detectada imagen en el portapapeles.")
                # Generar un nombre de archivo único
                filename = f"clipboard_{int(time.time())}.png"
                temp_filepath = os.path.join(self.temp_image_dir, filename)
                
                # Guardar como PNG para preservar transparencia
                img.save(temp_filepath, "PNG")
                print(f"INFO: Imagen de portapapeles guardada en: {temp_filepath}")
                
                self._process_imported_files([temp_filepath])
                return # ¡Éxito! Terminar aquí.

        except Exception as e:
            # Esto puede fallar si el clipboard no contiene una imagen
            print(f"DEBUG: No se pudo obtener imagen de clipboard ({e}). Probando texto...")
        
        # --- Prioridad 2: Fallback a TEXTO (Rutas de archivo) ---
        try:
            content = self.clipboard_get()
            filepaths = [path.strip() for path in content.splitlines() if path.strip()]
            
            valid_files = [path for path in filepaths if os.path.exists(path) and path.lower().endswith(self.COMPATIBLE_EXTENSIONS)]
            
            if valid_files:
                print(f"INFO: Pegando {len(valid_files)} rutas de archivo válidas desde el portapapeles.")
                self._process_imported_files(valid_files)
            else:
                print("INFO: No se encontraron rutas de archivo válidas en el portapapeles.")
                
        except Exception as e:
            print(f"ERROR: No se pudo pegar desde el portapapeles: {e}")

    def _on_clear_list(self):
        """Limpia la lista de archivos y los datos internos."""
        print("Lógica para limpiar la lista...")
        self.file_list_data.clear()
        self.file_list_box.delete(0, "end")
        
        # Limpiar caché de miniaturas
        with self.thumbnail_lock:
            self.thumbnail_cache.clear()
        
        # Limpiar el visor (recrear el placeholder)
        for widget in self.viewer_frame.winfo_children():
            widget.destroy()
        
        self.viewer_placeholder = ctk.CTkLabel(
            self.viewer_frame, 
            text="Selecciona un archivo de la lista para previsualizarlo",
            text_color="gray"
        )
        self.viewer_placeholder.grid(row=0, column=0, sticky="nsew")
        
        # Limpiar el título
        self.title_entry.delete(0, "end")
        
        # Actualizar estado
        self._update_list_status()
        self._update_video_resolution_menu_options()

    def _on_delete_selected(self, event=None):
        """Elimina los ítems seleccionados de la lista (optimizado)."""
        
        selected_indices = self.file_list_box.curselection()  # ⭐ CORREGIDO
        
        if not selected_indices:
            print("INFO: No hay nada seleccionado para borrar.")
            return

        print(f"INFO: Borrando {len(selected_indices)} ítems seleccionados.")

        # ⭐ NUEVO: Borrar del caché también
        with self.thumbnail_lock:
            for index in selected_indices:
                if index < len(self.file_list_data):
                    filepath = self.file_list_data[index]
                    self.thumbnail_cache.pop(filepath, None)  # Eliminar del caché
        
        # CRÍTICO: Debemos iterar en reversa para no arruinar los índices
        for index in reversed(selected_indices):
            self.file_list_box.delete(index)  # ⭐ CORREGIDO
            self.file_list_data.pop(index)
        
        # Llamar a la función de estado centralizada
        self._update_list_status()
        self._update_video_resolution_menu_options()
    
    def _on_file_select(self, event=None):
        """
        Se activa al hacer clic o usar las flechas.
        Carga la vista previa/título y actualiza el estado de los botones.
        """
        # 1. Actualizar estado de botones
        self._update_list_status()
        
        selected_indices = self.file_list_box.curselection()  # ⭐ CORREGIDO
        
        if not selected_indices:
            self.title_entry.delete(0, "end")
            self._display_thumbnail_in_viewer(None, None)
            return
            
        # 2. Lógica para el Visor y Título
        first_index = selected_indices[0]
        try:
            # 1. AHORA OBTENEMOS LA TUPLA
            (filepath, page_num) = self.file_list_data[first_index]
            
            # 2. Quitar la extensión (.pdf) para el título
            title_no_ext = os.path.splitext(os.path.basename(filepath))[0]
            
            # 3. Crear un título de salida sugerido
            if page_num and self.image_processor.get_document_page_count(filepath) > 1:
                 title_with_page = f"{title_no_ext}_p{page_num}"
            else:
                 title_with_page = title_no_ext

            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, title_with_page) # Título sugerido
            
            # 4. La clave de caché AHORA debe incluir la página
            cache_key = f"{filepath}::{page_num}"
            
            # 5. Guardar esta CLAVE ÚNICA como la "última solicitada"
            self.last_preview_path = cache_key

            # 6. Verificar si ya está en caché
            with self.thumbnail_lock:
                if cache_key in self.thumbnail_cache:
                    # ✅ Está en caché, mostrar inmediatamente
                    cached_image = self.thumbnail_cache[cache_key]
                    self._display_cached_thumbnail(cached_image, cache_key)
                    return

            # ⭐ NUEVO: Vaciar la cola antes de agregar (cancelar solicitudes obsoletas)
            # Esto permite que funcione con teclas mantenidas
            try:
                while True:
                    self.thumbnail_queue.get_nowait()  # Vaciar todo
            except queue.Empty:
                pass  # La cola ya está vacía

            # ❌ No está en caché, agregar a la cola
            self.thumbnail_queue.put( (filepath, page_num) )

            # Mostrar "Cargando..." mientras se procesa
            self._display_thumbnail_in_viewer(None, None, is_loading=True)

            # Iniciar el worker si no está activo
            self._start_thumbnail_worker()
            
        except Exception as e:
            print(f"ERROR: No se pudo seleccionar el ítem en el índice {first_index}: {e}")
            self._display_thumbnail_in_viewer(None, None)

    def _on_start_process(self):
        """Inicia o cancela el procesamiento de archivos."""
        
        # --- LÓGICA DE CANCELACIÓN (COMO SINGLE_TAB) ---
        if hasattr(self, 'is_processing') and self.is_processing:
            if hasattr(self, 'cancel_event') and self.cancel_event:
                self.cancel_event.set()
            
            self.start_process_button.configure(state="disabled", text="Cancelando...")
            self.progress_label.configure(text="Cancelando proceso...")
            return

        if self.image_converter.gs_exe:
            existe = os.path.exists(self.image_converter.gs_exe)

            if existe:
                import stat

        else:
            print("   ⚠️ gs_exe es None o vacío")
        print("="*60)
        
        # --- ADVERTENCIA DE RASTERIZACIÓN ---
        try:
            if self.format_menu.get() == "No Convertir":
                is_raster_op = (self.resize_checkbox.get() == 1 or
                                self.canvas_checkbox.get() == 1 or
                                self.background_checkbox.get() == 1)
                if is_raster_op:
                    from src.core.constants import IMAGE_INPUT_FORMATS
                    has_vectors = False
                    # CORREGIDO: Iterar sobre las tuplas (path, page)
                    for f_path, page in self.file_list_data:
                        ext = os.path.splitext(f_path)[1].lower()
                        if ext in IMAGE_INPUT_FORMATS:
                            has_vectors = True
                            break
                    if has_vectors:
                        response = messagebox.askyesno(
                            "Advertencia de Conversión",
                            "Tu lista contiene archivos vectoriales (SVG, PDF, AI, etc.) y has seleccionado 'No Convertir', pero también has activado una operación de píxeles (Escalado, Canvas o Fondo).\n\n"
                            "Para aplicar estos efectos, los vectores DEBEN ser convertidos a PNG.\n\n"
                            "¿Deseas continuar?"
                        )
                        if not response:
                            print("INFO: Proceso cancelado por el usuario.")
                            return
        except Exception as e:
            print(f"Error durante la comprobación de advertencia: {e}")
            
        # --- VALIDACIONES ---
        if not self.file_list_data:
            messagebox.showwarning("Sin archivos", "No hay archivos para procesar.")
            return
        
        output_dir = self.output_path_entry.get()
        if not output_dir:
            messagebox.showwarning("Sin carpeta de salida", "Selecciona una carpeta de salida.")
            return
        
        if not os.path.exists(output_dir):
            try: os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear la carpeta de salida:\n{e}")
                return
        
        if self.create_subfolder_checkbox.get():
            subfolder_name = self.subfolder_name_entry.get() or "DowP Imágenes"
            output_dir = os.path.join(output_dir, subfolder_name)
            try: os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear la subcarpeta:\n{e}")
                return
        
        self.last_processed_output_dir = output_dir
        self.open_folder_button.configure(state="normal")

        # Validar tamaño objetivo si el escalado está activado
        if self.resize_checkbox.get():
            try:
                width = int(self.resize_width_entry.get())
                height = int(self.resize_height_entry.get())
                
                if width <= 0 or height <= 0:
                    messagebox.showwarning("Dimensiones inválidas", 
                                         "El ancho y alto deben ser mayores a 0.")
                    return
                
                # Validar con el conversor
                is_safe, warning_msg = self.image_converter.validate_target_size((width, height))
                
                if warning_msg:
                    if not is_safe:
                        # Crítico: mostrar error y no continuar
                        messagebox.showerror("Resolución Crítica", warning_msg)
                        return
                    else:
                        # Alto: pedir confirmación
                        response = messagebox.askyesno("Advertencia de Resolución", warning_msg)
                        if not response:
                            return
            
            except ValueError:
                messagebox.showwarning("Dimensiones inválidas", 
                                     "Ingresa valores numéricos válidos para ancho y alto.")
                return
            
        # Validar canvas si está activado
        if self.canvas_checkbox.get():
            canvas_option = self.canvas_option_menu.get()
            
            if canvas_option == "Personalizado...":
                try:
                    canvas_width = int(self.canvas_width_entry.get())
                    canvas_height = int(self.canvas_height_entry.get())
                    
                    if canvas_width <= 0 or canvas_height <= 0:
                        messagebox.showwarning("Dimensiones inválidas", 
                                             "El ancho y alto del canvas deben ser mayores a 0.")
                        return
                    
                    # Validar con el conversor
                    is_safe, warning_msg = self.image_converter.validate_target_size((canvas_width, canvas_height))
                    
                    if warning_msg:
                        if not is_safe:
                            messagebox.showerror("Resolución de Canvas Crítica", warning_msg)
                            return
                        else:
                            response = messagebox.askyesno("Advertencia de Canvas", warning_msg)
                            if not response:
                                return
                
                except ValueError:
                    messagebox.showwarning("Dimensiones inválidas", 
                                         "Ingresa valores numéricos válidos para el canvas.")
                    return
            
            elif canvas_option in ["Añadir Margen Externo", "Añadir Margen Interno"]:
                # Validar margen
                margin_str = self.canvas_margin_entry.get()
                if not margin_str or not margin_str.strip():
                    messagebox.showwarning("Margen inválido", "Ingresa un valor para el margen.")
                    return
                
                try:
                    margin = int(margin_str)
                    if margin <= 0:
                        messagebox.showwarning("Margen inválido", "El margen debe ser mayor a 0.")
                        return
                except ValueError:
                    messagebox.showwarning("Margen inválido", "Ingresa un valor numérico válido para el margen.")
                    return
        
        options = self._gather_conversion_options()
        is_video_export = options.get("format", "").startswith(".")
        
        if is_video_export:
            try:
                fps = int(options.get("video_fps", "30"))
                duration = int(options.get("video_frame_duration", "3"))
                if fps <= 0 or duration <= 0: raise ValueError("FPS/Duración debe ser > 0")
            except ValueError:
                messagebox.showerror("Valores Inválidos", "FPS y Duración (frames) deben ser números enteros positivos.")
                return

            if options["video_resolution"] == "Personalizado...":
                try:
                    width = int(options.get("video_custom_width", "1920"))
                    height = int(options.get("video_custom_height", "1080"))
                    if width <= 0 or height <= 0: raise ValueError("Dimensiones inválidas")
                except ValueError:
                    messagebox.showerror("Resolución Inválida", "El Ancho y Alto personalizados deben ser números enteros positivos.")
                    return

        # --- PREPARAR E INICIAR PROCESO ---
        self.is_processing = True
        self.cancel_event = threading.Event() # <-- EVENTO DE CANCELACIÓN REAL
        self.cancel_event.clear() # No está cancelado
        
        self.start_process_button.configure(state="normal", text="Cancelar", 
                                        fg_color="#DC3545", hover_color="#C82333")
        
        # ✅ CORRECCIÓN: Deshabilitar el nuevo botón único
        self.import_button.configure(state="disabled")
        
        # Iniciar procesamiento en hilo separado...
        threading.Thread(
            target=self._process_files_thread,
            args=(output_dir, self.cancel_event), # <-- PASAR EL EVENTO REAL
            daemon=True
        ).start()

    def _process_files_thread(self, output_dir, cancel_event):
        """Hilo de trabajo que procesa todos los archivos."""
        
        total_files = len(self.file_list_data)
        processed = 0
        skipped = 0
        errors = 0
        
        # 🔧 NUEVO: Lista detallada de errores
        error_details = []
        
        # 🔧 NUEVO: Resetear el flag al inicio
        self.conversion_complete_event.clear()
        
        # Obtener opciones de conversión
        options = self._gather_conversion_options()

        # --- NUEVO ROUTER: VIDEO vs IMÁGENES ---
        is_video_export = options.get("format", "").startswith(".")
        
        if is_video_export:
            # Llamar a la nueva lógica de video
            self._video_thread_target(output_dir, options, cancel_event)
            return
        # --- FIN DEL ROUTER ---

        # Política de conflictos
        conflict_policy = self.conflict_policy_menu.get()
        
        # Lista de PDFs generados (para combinar al final)
        generated_pdfs = []
        
        # Lista de archivos exitosos
        successfully_processed_paths = []
        
        try:
            for i, input_path in enumerate(self.file_list_data):
                
                if cancel_event.is_set():
                    print("INFO: Proceso cancelado por el usuario")
                    self.app.after(0, lambda p=processed: self.progress_label.configure(
                        text=f"Cancelado: {p} archivos procesados antes de cancelar"))
                    break
                
                (input_path, page_num) = self.file_list_data[i]
                filename = os.path.basename(input_path)
                
                # --- CALLBACK DE PROGRESO FINO ---
                def internal_callback(file_pct, message=None):
                    # file_pct: 0 a 100 (puede ser None si solo es mensaje)
                    
                    # Solo actualizar la barra si hay un porcentaje numérico
                    if file_pct is not None:
                        weight_per_file = 100 / total_files
                        base_progress = i * weight_per_file
                        current_contribution = (file_pct / 100.0) * weight_per_file
                        total_global = base_progress + current_contribution
                        
                        self.app.after(0, lambda p=total_global: self.progress_bar.set(p / 100.0))
                    
                    # Actualizar el texto si se proporciona
                    if message:
                        self.app.after(0, lambda t=message: self.progress_label.configure(text=t))
                
                # Actualizar texto inicial del archivo
                self.app.after(0, lambda t=f"Procesando ({i+1}/{total_files}): {filename}": 
                            self.progress_label.configure(text=t))
                
                # 2. Generar el nombre de salida
                output_filename = self._get_output_filename(input_path, options, page_num)
                output_path = os.path.join(output_dir, output_filename)
                
                # Manejar conflictos
                if os.path.exists(output_path):
                    action = self._handle_conflict(output_path, conflict_policy)
                    if action == "skip":
                        print(f"INFO: Omitiendo {filename} (ya existe)")
                        skipped += 1
                        continue
                    elif action == "rename":
                        output_path = self._get_unique_filename(output_path)

                # Convertir archivo CON CALLBACK
                try:
                    success = self.image_converter.convert_file(
                        input_path, 
                        output_path, 
                        options,
                        page_number=page_num,
                        progress_callback=internal_callback  # <--- AQUÍ ESTÁ LA MAGIA
                    )
                    
                    if success:
                        processed += 1
                        print(f"✅ Convertido: {filename} → {os.path.basename(output_path)}")

                        successfully_processed_paths.append(output_path)

                        # Si es PDF y se va a combinar, guardar ruta
                        if options["format"] == "PDF" and options.get("pdf_combine", False):
                            generated_pdfs.append(output_path)
                    else:
                        errors += 1
                        error_details.append((filename, "Error desconocido durante la conversión"))
                        print(f"❌ Error al convertir: {filename}")
                
                except Exception as e:
                    errors += 1
                    error_message = str(e)
                    
                    # 🔧 NUEVO: Categorizar errores comunes
                    if "decompression bomb" in error_message.lower():
                        error_type = "Archivo demasiado grande (posible ataque de descompresión)"
                    elif "could not convert string to float" in error_message.lower():
                        error_type = "SVG corrupto (atributos inválidos)"
                    elif "MAX_TEXT_CHUNK" in error_message:
                        error_type = "Metadatos demasiado grandes (límite de seguridad)"
                    elif "timeout" in error_message.lower():
                        error_type = "Tiempo de espera agotado (archivo muy complejo)"
                    else:
                        error_type = error_message[:100]  # Primeros 100 caracteres
                    
                    error_details.append((filename, error_type))
                    print(f"❌ Error al procesar {filename}: {e}")
            
            # Combinar PDFs si está activado
            if not cancel_event.is_set() and options["format"] == "PDF" and options.get("pdf_combine", False) and len(generated_pdfs) > 1:
                self.app.after(0, lambda: self.progress_label.configure(
                    text=f"Combinando {len(generated_pdfs)} PDFs..."))
                
                # Obtener el nombre personalizado del PDF combinado
                pdf_title = options.get("pdf_combined_title", "combined_output")
                if not pdf_title or pdf_title.strip() == "":
                    pdf_title = "combined_output"

                # Eliminar caracteres inválidos para nombres de archivo
                import re
                pdf_title = re.sub(r'[<>:"/\\|?*]', '_', pdf_title)

                # Asegurar que no tenga extensión .pdf (la añadimos nosotros)
                if pdf_title.lower().endswith(".pdf"):
                    pdf_title = pdf_title[:-4]

                combined_pdf_path = os.path.join(output_dir, f"{pdf_title}.pdf")
                
                # Manejar conflicto del PDF combinado
                if os.path.exists(combined_pdf_path):
                    combined_pdf_path = self._get_unique_filename(combined_pdf_path)
                
                if self.image_converter.combine_pdfs(generated_pdfs, combined_pdf_path):
                    print(f"✅ PDF combinado creado: {os.path.basename(combined_pdf_path)}")
                    
                    # Actualizar nuestra lista de archivos exitosos:
                    for pdf_path in generated_pdfs:
                        if pdf_path in successfully_processed_paths:
                            successfully_processed_paths.remove(pdf_path)
                        
                        try:
                            os.remove(pdf_path)
                        except Exception as e:
                            print(f"ADVERTENCIA: No se pudo eliminar {pdf_path}: {e}")
                    
                    # Añadir el nuevo PDF combinado a la lista
                    successfully_processed_paths.append(combined_pdf_path)
            
            # 🔧 NUEVO: Señalizar que la conversión terminó COMPLETAMENTE
            self.conversion_complete_event.set()
            print("DEBUG: ✅ Todas las conversiones completadas. Señal enviada.")
            
            # Importar a Adobe
            if not cancel_event.is_set() and self.auto_import_checkbox.get():
                print(f"DEBUG: Proceso finalizado. Programando importación a Adobe.")
                self.app.after(0, self._import_to_adobe, successfully_processed_paths)

            # 🔧 NUEVO: Mostrar resumen mejorado
            if not cancel_event.is_set():
                summary = f"✅ Completado: {processed} archivos"
                if skipped > 0:
                    summary += f" ({skipped} omitidos)"
                if errors > 0:
                    summary += f" ({errors} errores)"
                
                self.app.after(0, lambda s=summary: self.progress_label.configure(text=s))
                self.app.after(0, lambda: self.progress_bar.set(1.0))
                
                # 🔧 NUEVO: Diálogo de resumen con detalles de errores
                self.app.after(0, lambda: self._show_process_summary(processed, skipped, errors, error_details))
        
        except Exception as e:
            error_msg = f"Error crítico durante el procesamiento: {e}"
            print(f"ERROR: {error_msg}")
            self.app.after(0, lambda: messagebox.showerror("Error", error_msg))
        
        finally:
            # REACTIVAR BOTONES Y RESTAURAR TEXTO
            self.is_processing = False
            
            # Restaurar botón de inicio
            self.app.after(0, lambda: self.start_process_button.configure(
                state="normal", text="Iniciar Proceso", 
                fg_color=self.PROCESS_BTN_COLOR, hover_color=self.PROCESS_BTN_HOVER))
            
            # ✅ CORRECCIÓN: Reactivar el botón único de importar
            if hasattr(self, 'import_button'):
                self.app.after(0, lambda: self.import_button.configure(state="normal"))

    def _show_process_summary(self, processed, skipped, errors, error_details):
        """
        Muestra un diálogo de resumen del proceso (Texto plano, sin sugerencias).
        """
        # Construir mensaje base
        detail_msg = f"Convertidos exitosamente: {processed}"
        
        if skipped > 0:
            detail_msg += f"\nOmitidos (ya existían): {skipped}"
        
        if errors > 0:
            detail_msg += f"\n\nErrores encontrados: {errors}"
            
            if error_details:
                detail_msg += "\n\nDetalles de los errores:\n"
                detail_msg += "-" * 50 + "\n"
                
                # Agrupar errores por tipo
                error_groups = {}
                for filename, error_type in error_details:
                    if error_type not in error_groups:
                        error_groups[error_type] = []
                    error_groups[error_type].append(filename)
                
                # Mostrar errores agrupados (Solo descripción y archivos)
                for error_type, files in error_groups.items():
                    detail_msg += f"\n{error_type}\n"
                    for file in files[:3]:  # Mostrar máximo 3 archivos por tipo
                        detail_msg += f"  - {file}\n"
                    if len(files) > 3:
                        detail_msg += f"  ... y {len(files) - 3} más\n"
        
        # Mostrar el diálogo
        messagebox.showinfo("Resumen del Proceso", detail_msg)

    def _wait_for_file_ready(self, filepath, timeout=2.0):
        """
        Espera hasta que un archivo esté completamente escrito y accesible.
        Crítico para importación inmediata en Adobe Premiere.
        """
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Intentar abrir y leer el archivo
                with open(filepath, 'rb') as f:
                    f.read(1)  # Leer el primer byte
                
                # Si llegamos aquí, el archivo está listo
                return True
                
            except (IOError, OSError, PermissionError):
                # Archivo aún no está listo, esperar
                time.sleep(0.05)  # 50ms entre reintentos
        
        # Timeout alcanzado
        print(f"⚠️ ADVERTENCIA: Timeout esperando que esté listo: {os.path.basename(filepath)}")
        return False

    def _gather_conversion_options(self):
        format_selected = self.format_menu.get()
        
        vid_res_selection = self.video_resolution_menu.get() if hasattr(self, 'video_resolution_menu') else "1920x1080 (1080p)"
        
        # Valores por defecto
        vid_width = "1920"
        vid_height = "1080"
        
        if vid_res_selection == "Personalizado...":
            if hasattr(self, 'video_custom_width_entry'):
                vid_width = self.video_custom_width_entry.get()
                vid_height = self.video_custom_height_entry.get()
        
        elif vid_res_selection.startswith("Usar la primera"):
            # Intentar extraer (WxH) del paréntesis
            import re
            match = re.search(r'\((\d+)x(\d+)\)', vid_res_selection)
            if match:
                vid_width = match.group(1)
                vid_height = match.group(2)
            else:
                # Si dice (Auto) o falla, intentamos leerlo en caliente
                dims = self._get_first_image_dimensions()
                if dims:
                    vid_width, vid_height = map(str, dims)
                else:
                    # Fallback extremo si no hay imágenes
                    vid_width, vid_height = "1920", "1080"
        
        else:
            # Es un preset fijo como "1280x720 (720p)"
            try:
                # Tomamos la primera parte antes del espacio "1280x720"
                res_part = vid_res_selection.split(" ")[0]
                vid_width, vid_height = res_part.split("x")
            except:
                pass # Mantener default 1920x1080
        
        # Lógica para obtener el nombre real del archivo para rembg
        selected_family = self.rembg_family_menu.get() if hasattr(self, 'rembg_family_menu') else None
        selected_model_label = self.rembg_model_menu.get() if hasattr(self, 'rembg_model_menu') else None
        
        real_model_name = "u2netp" # Fallback
        
        if selected_family and selected_model_label:
            model_data = REMBG_MODEL_FAMILIES.get(selected_family, {}).get(selected_model_label)
            if model_data:
                # Rembg usa el nombre del archivo SIN extensión como ID de sesión
                # OJO: Para BiRefNet hay que tener cuidado, pero por ahora pasamos el nombre base.
                real_model_name = model_data["file"] 
        
        options = {
            "format": format_selected,
            # Opciones de escalado
            "resize_enabled": self.resize_checkbox.get() == 1,
            "resize_width": self.resize_width_entry.get() if hasattr(self, 'resize_width_entry') and self.resize_width_entry.get() else None,
            "resize_height": self.resize_height_entry.get() if hasattr(self, 'resize_height_entry') and self.resize_height_entry.get() else None,
            "resize_maintain_aspect": self.resize_aspect_lock.get() == 1,
            "interpolation_method": self.interpolation_menu.get() if hasattr(self, 'interpolation_menu') else "Lanczos (Mejor Calidad)",
            # Opciones de canvas
            "canvas_enabled": self.canvas_checkbox.get() == 1 if hasattr(self, 'canvas_checkbox') else False,
            "canvas_option": self.canvas_option_menu.get() if hasattr(self, 'canvas_option_menu') else "Sin ajuste",
            "canvas_width": self.canvas_width_entry.get() if hasattr(self, 'canvas_width_entry') and self.canvas_width_entry.get() else None,
            "canvas_height": self.canvas_height_entry.get() if hasattr(self, 'canvas_height_entry') and self.canvas_height_entry.get() else None,
            "canvas_margin": int(self.canvas_margin_entry.get()) if hasattr(self, 'canvas_margin_entry') and self.canvas_margin_entry.get() and self.canvas_margin_entry.get().isdigit() else 100,
            "canvas_position": self.canvas_position_menu.get() if hasattr(self, 'canvas_position_menu') else "Centro",
            "canvas_overflow_mode": self.canvas_overflow_menu.get() if hasattr(self, 'canvas_overflow_menu') else "Centrar (puede recortar)",
            # Opciones de fondo
            "background_enabled": self.background_checkbox.get() == 1 if hasattr(self, 'background_checkbox') else False,
            "background_type": self.background_type_menu.get() if hasattr(self, 'background_type_menu') else "Color Sólido",
            "background_color": self.bg_color_entry.get() if hasattr(self, 'bg_color_entry') and self.bg_color_entry.get() else "#FFFFFF",
            "background_gradient_color1": self.bg_gradient_color1_entry.get() if hasattr(self, 'bg_gradient_color1_entry') and self.bg_gradient_color1_entry.get() else "#FF0000",
            "background_gradient_color2": self.bg_gradient_color2_entry.get() if hasattr(self, 'bg_gradient_color2_entry') and self.bg_gradient_color2_entry.get() else "#0000FF",
            "background_gradient_direction": self.bg_gradient_direction_menu.get() if hasattr(self, 'bg_gradient_direction_menu') else "Horizontal (Izq → Der)",
            "background_image_path": self.bg_image_entry.get() if hasattr(self, 'bg_image_entry') and self.bg_image_entry.get() else None,
            # PNG
            "png_transparency": self.png_transparency.get() if hasattr(self, 'png_transparency') else True,
            "png_compression": int(self.png_compression_slider.get()) if hasattr(self, 'png_compression_slider') else 6,
            # JPG
            "jpg_quality": int(self.jpg_quality_slider.get()) if hasattr(self, 'jpg_quality_slider') else 90,
            "jpg_subsampling": self.jpg_subsampling.get() if hasattr(self, 'jpg_subsampling') else "4:2:0 (Estándar)",
            "jpg_progressive": self.jpg_progressive.get() if hasattr(self, 'jpg_progressive') else False,
            # WEBP
            "webp_lossless": self.webp_lossless.get() if hasattr(self, 'webp_lossless') else False,
            "webp_quality": int(self.webp_quality_slider.get()) if hasattr(self, 'webp_quality_slider') else 90,
            "webp_transparency": self.webp_transparency.get() if hasattr(self, 'webp_transparency') else True,
            "webp_metadata": self.webp_metadata.get() if hasattr(self, 'webp_metadata') else False,
            # AVIF
            "avif_lossless": self.avif_lossless.get() if hasattr(self, 'avif_lossless') else False,
            "avif_quality": int(self.avif_quality_slider.get()) if hasattr(self, 'avif_quality_slider') else 80,
            "avif_speed": int(self.avif_speed_slider.get()) if hasattr(self, 'avif_speed_slider') else 6,
            "avif_transparency": self.avif_transparency.get() if hasattr(self, 'avif_transparency') else True,
            # PDF
            "pdf_combine": self.pdf_combine.get() if hasattr(self, 'pdf_combine') else False,
            "pdf_combined_title": self.pdf_combined_title_entry.get() if hasattr(self, 'pdf_combined_title_entry') else "combined_output",
            # TIFF
            "tiff_compression": self.tiff_compression.get() if hasattr(self, 'tiff_compression') else "LZW (Recomendada)",
            "tiff_transparency": self.tiff_transparency.get() if hasattr(self, 'tiff_transparency') else True,
            # ICO
            "ico_sizes": {size: checkbox.get() for size, checkbox in self.ico_sizes.items()} if hasattr(self, 'ico_sizes') else {},
            # BMP
            "bmp_rle": self.bmp_rle.get() if hasattr(self, 'bmp_rle') else False,
            
            # --- NUEVAS OPCIONES DE VIDEO ---
            "video_custom_title": self.video_filename_entry.get().strip() if hasattr(self, 'video_filename_entry') else "",
            "video_resolution": "Personalizado...", 
            "video_custom_width": vid_width, 
            "video_custom_height": vid_height,
            "video_fps": self.video_fps_entry.get() if hasattr(self, 'video_fps_entry') else "30",
            "video_frame_duration": self.video_frame_duration_entry.get() if hasattr(self, 'video_frame_duration_entry') else "3",
            "video_fit_mode": self.video_fit_mode_menu.get() if hasattr(self, 'video_fit_mode_menu') else "Mantener Tamaño Original",
            # Opciones de rembg
            "rembg_enabled": self.rembg_checkbox.get() == 1,
            "rembg_model": real_model_name,
        }
        
        return options
    
    def _get_first_image_dimensions(self):
        """Obtiene (ancho, alto) del primer ítem de la lista. Retorna None si falla."""
        if not self.file_list_data:
            return None
        
        filepath, page_num = self.file_list_data[0]
        
        try:
            # Usamos Pillow en modo 'lazy' (solo lee cabeceras)
            with Image.open(filepath) as img:
                return img.size # (width, height)
        except Exception:
            # Si es un PDF/Vectorial o falla Pillow, intentamos usar valores por defecto
            # o podríamos usar poppler, pero por velocidad retornamos None (Auto)
            return None
        
    def _update_video_resolution_menu_options(self):
        """Actualiza las opciones del menú de resolución con el valor de la primera imagen."""
        
        # 1. Obtener dimensiones actuales
        dims = self._get_first_image_dimensions()
        
        # 2. Crear el texto dinámico
        if dims:
            w, h = dims
            first_option = f"Usar la primera ({w}x{h})"
        else:
            first_option = "Usar la primera (Auto)"
            
        # 3. Lista base de opciones
        base_options = [
            "1920x1080 (1080p)",
            "1280x720 (720p)",
            "3840x2160 (4K UHD)",
            "Personalizado..."
        ]
        
        # 4. Combinar
        new_values = [first_option] + base_options
        
        # 5. Actualizar el menú
        # Guardamos la selección actual para intentar restaurarla si no era la dinámica
        current_selection = self.video_resolution_menu.get()
        
        self.video_resolution_menu.configure(values=new_values)
        
        # Si la selección actual ya no existe (porque cambiaron las dimensiones),
        # o si era la opción "Usar la primera...", actualizamos a la nueva cadena.
        if current_selection.startswith("Usar la primera") or current_selection not in base_options:
            self.video_resolution_menu.set(first_option)
        else:
            # Si estaba en 1080p o Personalizado, lo mantenemos
            self.video_resolution_menu.set(current_selection)

    def _get_output_filename(self, input_path, options, page_num=None):
        """Genera el nombre del archivo de salida."""
        from src.core.constants import IMAGE_INPUT_FORMATS
        from urllib.parse import unquote  # 🔧 NUEVO
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        # 🔧 NUEVO: Decodificar caracteres URL-encoded (%20, %C3%B1, etc.)
        base_name = unquote(base_name)
        
        # 🔧 NUEVO: Limpiar caracteres problemáticos para Windows/Premiere
        import re
        base_name = re.sub(r'[<>:"/\\|?*]', '_', base_name)
        
        # Añadir el sufijo de página SI existe y si el original tenía varias páginas
        if page_num and self.image_processor.get_document_page_count(input_path) > 1:
            base_name = f"{base_name}_p{page_num}"
            
        output_format_str = options["format"]

        # --- INICIO DE MODIFICACIÓN ---
        if output_format_str == "No Convertir":
            input_ext = os.path.splitext(input_path)[1].lower()
            
            # Si el original era un vector, se rasterizará a PNG
            if input_ext in IMAGE_INPUT_FORMATS: # .svg, .pdf, .ai, .eps
                extension = "png"
            else:
                # Mantener la extensión original para rasters
                extension = input_ext.lstrip('.')
        
        else:
            extension = output_format_str.lower()
            # Casos especiales
            if extension in ["jpg", "jpeg"]:
                extension = "jpg"
        # --- FIN DE MODIFICACIÓN ---
        
        return f"{base_name}.{extension}"

    def _handle_conflict(self, output_path, policy):
        """
        Maneja conflictos de archivos existentes.
        Returns: "overwrite", "rename", "skip"
        """
        if policy == "Sobrescribir":
            return "overwrite"
        elif policy == "Renombrar":
            return "rename"
        elif policy == "Omitir":
            return "skip"
        else:
            return "overwrite"  # Por defecto

    def _get_unique_filename(self, filepath):
        """Genera un nombre único para evitar sobrescribir."""
        directory = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        name, ext = os.path.splitext(filename)
        
        counter = 1
        while True:
            new_name = f"{name} ({counter}){ext}"
            new_path = os.path.join(directory, new_name)
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def _import_to_adobe(self, processed_filepaths: list):
        """
        Importa los archivos procesados a Adobe (Premiere/After Effects).
        CORREGIDO: Ahora recibe una lista de archivos para no re-escanear.
        """
        try:
            # 1. Obtener el objetivo activo
            active_target_sid = self.app.ACTIVE_TARGET_SID_accessor()
            
            if not active_target_sid:
                print("INFO: No hay aplicación Adobe vinculada para importación automática")
                return
            
            # 2. Determinar la papelera (bin) de destino
            target_bin_name = None
            if self.create_subfolder_checkbox.get():
                # Usar el nombre de la subcarpeta como nombre del bin
                target_bin_name = self.subfolder_name_entry.get() or "DowP Imágenes"

            # 3. Lista de formatos compatibles (excluyendo WEBP)
            compatible_formats = {".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".tif", ".ico", ".bmp"}
            
            files_to_import = []

            # 4. Iterar sobre la LISTA RECIBIDA (esta es la corrección)
            print(f"DEBUG: Preparando {len(processed_filepaths)} archivos para importar.")
            
            for filepath in processed_filepaths:
                file_ext = os.path.splitext(filepath)[1].lower()
                
                # Validar que el archivo exista y sea compatible
                if os.path.isfile(filepath) and file_ext in compatible_formats:
                    files_to_import.append(filepath.replace('\\', '/'))
                elif file_ext not in compatible_formats:
                    # Omitir silenciosamente formatos no compatibles (como .webp)
                    print(f"INFO: [ImgTools] Omitiendo importación de {os.path.basename(filepath)} (no compatible).")
            
            if not files_to_import:
                print("ADVERTENCIA: No se encontraron archivos compatibles en la lista procesada para importar.")
                return
            
            # 5. Verificar que TODOS los archivos sean accesibles
            print(f"DEBUG: Verificando accesibilidad de {len(files_to_import)} archivos...")
            verified_files = []
            for filepath in files_to_import:
                try:
                    # Verificar que existe y es accesible
                    if not os.path.exists(filepath):
                        print(f"  ❌ {os.path.basename(filepath)} - No existe")
                        continue
                    
                    size = os.path.getsize(filepath)
                    with open(filepath, 'rb') as f:
                        f.read(1)  # Leer primer byte
                    
                    verified_files.append(filepath)
                    print(f"  ✅ {os.path.basename(filepath)} ({size} bytes)")
                except Exception as e:
                    print(f"  ❌ {os.path.basename(filepath)} - ERROR: {e}")
            
            if not verified_files:
                print("ERROR: Ningún archivo pasó la verificación de accesibilidad")
                return
            
            # 6. Armar el PAQUETE ÚNICO (con archivos verificados)
            import_package = {
                "files": verified_files,
                "targetBin": target_bin_name
            }
            
            # 7. Enviar el paquete en UN SOLO MENSAJE
            print(f"INFO: [ImgTools] Enviando paquete de lote a CEP: {len(verified_files)} archivos a la papelera '{target_bin_name}'")
            self.app.socketio.emit('import_files', 
                                   import_package,
                                   to=active_target_sid)
        
        except Exception as e:
            print(f"ERROR: Falló la importación automática a Adobe: {e}")
        
    def _toggle_subfolder_name_entry(self):
        """Habilita/deshabilita el entry de nombre de carpeta."""
        if self.create_subfolder_checkbox.get():
            self.subfolder_name_entry.configure(state="normal")
        else:
            self.subfolder_name_entry.configure(state="disabled")

    def _update_list_status(self):
        """
        Helper para actualizar la etiqueta de conteo y el estado de los botones.
        Esta es ahora la ÚNICA fuente de verdad para el estado de los botones.
        """
        count = len(self.file_list_data)
        self.list_status_label.configure(text=f"{count} archivos")
        
        # ✅ NUEVO: Controlar visibilidad de la etiqueta de ayuda
        if hasattr(self, 'drag_hint_label'):
            if count == 0:
                self.drag_hint_label.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self.drag_hint_label.place_forget()
        
        # 1. Estado del botón "Iniciar Proceso"
        if count == 0:
            self.start_process_button.configure(state="disabled")
            self.title_entry.delete(0, "end")
        else:
            self.start_process_button.configure(state="normal")

        # 2. Estado del botón "Borrar" (basado en la selección actual)
        if self.file_list_box.curselection():
            self.delete_button.configure(state="normal")
        else:
            self.delete_button.configure(state="disabled")

    def _create_list_context_menu(self, event):
        """Crea el menú de clic derecho para la lista de archivos."""
        menu = Menu(self, tearoff=0)
        
        # ✅ NUEVA OPCIÓN
        menu.add_command(label="Abrir ubicación del archivo", command=self._open_selected_file_location)
        menu.add_separator() # Separador visual
        
        menu.add_command(label="Copiar nombre de archivo", command=self._copy_selected_filename)
        menu.add_command(label="Copiar ruta completa", command=self._copy_selected_filepath)
        menu.add_separator()
        menu.add_command(label="Borrar selección", command=self._on_delete_selected)
        
        # Habilitar opciones solo si hay una selección válida
        if self.file_list_box.curselection():
            menu.entryconfigure("Abrir ubicación del archivo", state="normal") # ✅
            menu.entryconfigure("Copiar nombre de archivo", state="normal")
            menu.entryconfigure("Copiar ruta completa", state="normal")
            menu.entryconfigure("Borrar selección", state="normal")
        else:
            # Auto-seleccionar bajo el cursor (Lógica existente)
            self.file_list_box.selection_clear(0, "end")
            nearest_index = self.file_list_box.nearest(event.y)
            self.file_list_box.selection_set(nearest_index)
            self.file_list_box.activate(nearest_index)
            self.app.after(10, self._on_file_select)

        menu.tk_popup(event.x_root, event.y_root)

    def _get_selected_list_items(self, get_all=False):
        """
        Helper para obtener las rutas y nombres de los archivos seleccionados.
        CORREGIDO: Maneja la estructura de tuplas (filepath, page_num).
        """
        filepaths = []
        filenames = []
        
        # Índices a procesar
        if get_all:
            indices = range(len(self.file_list_data))
        else:
            indices = self.file_list_box.curselection()
            if not indices:
                return [], []
            
        for index in indices:
            # 1. Obtener la tupla de datos
            item_data = self.file_list_data[index]
            
            # 2. Extraer SOLO la ruta (primer elemento de la tupla)
            if isinstance(item_data, tuple):
                file_path = item_data[0]
            else:
                file_path = item_data # Fallback por seguridad
                
            filepaths.append(file_path)
            
            # 3. Obtener el nombre visual de la lista
            filenames.append(self.file_list_box.get(index))
                
        return filepaths, filenames

    def _copy_selected_filename(self):
        filepaths, filenames = self._get_selected_list_items()
        if filenames:
            self.clipboard_clear()
            self.clipboard_append("\n".join(filenames))

    def _copy_selected_filepath(self):
        filepaths, filenames = self._get_selected_list_items()
        if filepaths:
            self.clipboard_clear()
            self.clipboard_append("\n".join(filepaths))

    def _open_selected_file_location(self):
        """Abre el explorador de archivos seleccionando el ítem."""
        filepaths, _ = self._get_selected_list_items()
        
        if not filepaths:
            return
            
        # Abrir solo el primero de la selección para no abrir 50 ventanas
        path = os.path.normpath(filepaths[0])
        
        if not os.path.exists(path):
            print(f"ERROR: El archivo no existe: {path}")
            return
            
        try:
            import subprocess
            import platform
            
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(['explorer', '/select,', path])
            elif system == "Darwin": # Mac
                subprocess.Popen(['open', '-R', path])
            else: # Linux
                subprocess.Popen(['xdg-open', os.path.dirname(path)])
                
        except Exception as e:
            print(f"ERROR al abrir ubicación: {e}")

    def _add_files_to_list(self, file_tuples: list):
        """Helper para añadir archivos a la lista. AHORA ACEPTA TUPLAS (filepath, page_num)."""
        
        new_files_added = 0
        for (file_path, page_num) in file_tuples:
            
            # La clave de datos ahora debe incluir la página para ser única
            data_key = (file_path, page_num)
            
            if data_key not in self.file_list_data:
                self.file_list_data.append(data_key) # Guardar la tupla
                
                # El nombre en la UI debe ser descriptivo
                file_name = os.path.basename(file_path)
                if page_num and self.image_processor.get_document_page_count(file_path) > 1:
                    display_name = f"{file_name} (pág. {page_num})"
                else:
                    display_name = file_name # Mostrar nombre simple si es 1 pág
                    
                self.file_list_box.insert("end", display_name) # Mostrar nombre con página
                new_files_added += 1
        
        if new_files_added > 0:
            print(f"INFO: Añadidos {new_files_added} archivos nuevos a la lista.")
        
        # Llamar a la función de estado centralizada
        self._update_list_status()
        self._update_video_resolution_menu_options()
        
    def _toggle_subfolder_name_entry(self):
        """Habilita/deshabilita el entry de nombre de carpeta."""
        if self.create_subfolder_checkbox.get():
            self.subfolder_name_entry.configure(state="normal")
        else:
            self.subfolder_name_entry.configure(state="disabled")

    def select_output_folder(self):
        """Abre el diálogo para seleccionar la carpeta de salida."""
        folder_path = filedialog.askdirectory()
        self.app.lift()
        self.app.focus_force()
        if folder_path:
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, folder_path)
            self.save_settings() # Guardar la ruta
            self.last_processed_output_dir = folder_path
            self.open_folder_button.configure(state="normal")

    def _open_batch_output_folder(self):
        """
        Abre la carpeta de salida del ÚLTIMO proceso ejecutado,
        que puede ser la principal o la subcarpeta creada.
        """
        
        path_to_open = self.last_processed_output_dir
        
        # Fallback a la carpeta de salida principal si no se ha procesado nada
        if not path_to_open:
            path_to_open = self.output_path_entry.get()

        if not path_to_open or not os.path.isdir(path_to_open):
            print(f"ERROR: La carpeta de salida '{path_to_open}' no es válida.")
            return

        try:
            if os.name == "nt":
                os.startfile(os.path.normpath(path_to_open))
            elif sys.platform == "darwin":
                subprocess.Popen(['open', path_to_open])
            else:
                subprocess.Popen(['xdg-open', path_to_open])
        except Exception as e:
            print(f"Error al intentar abrir la carpeta: {e}")

    def create_entry_context_menu(self, widget):
        """Crea un menú contextual simple para los Entry widgets."""
        menu = Menu(self, tearoff=0)
        
        def copy_text():
            try:
                selected_text = widget.selection_get()
                if selected_text:
                    widget.clipboard_clear()
                    widget.clipboard_append(selected_text)
            except Exception: pass
        
        def cut_text():
            try:
                selected_text = widget.selection_get()
                if selected_text:
                    widget.clipboard_clear()
                    widget.clipboard_append(selected_text)
                    widget.delete("sel.first", "sel.last")
            except Exception: pass

        def paste_text():
            try:
                if widget.selection_get():
                    widget.delete("sel.first", "sel.last")
            except Exception: pass
            try:
                widget.insert("insert", self.clipboard_get())
            except Exception: pass
                
        menu.add_command(label="Cortar", command=cut_text)
        menu.add_command(label="Copiar", command=copy_text)
        menu.add_command(label="Pegar", command=paste_text)
        menu.add_separator()
        menu.add_command(label="Seleccionar todo", command=lambda: widget.select_range(0, 'end'))
        
        menu.tk_popup(widget.winfo_pointerx(), widget.winfo_pointery())

    def _load_thumbnail_thread(self, filepath):
        """
        (Hilo de trabajo) Llama al procesador para generar la miniatura.
        """
        # Obtener el tamaño del contenedor del visor
        # Lo hacemos aquí para que el hilo tenga el tamaño más actual
        try:
            # Damos un pequeño margen de 10px
            width = self.viewer_frame.winfo_width() - 10
            height = self.viewer_frame.winfo_height() - 10
            if width < 50 or height < 50: # Fallback si el frame está colapsado
                width, height = 400, 400
        except Exception:
            width, height = 400, 400 # Fallback
            
        # Llamar al "motor" de procesamiento
        pil_image = self.image_processor.generate_thumbnail(filepath, size=(width, height))
        
        # Enviar la imagen (o None) de vuelta al hilo principal (UI)
        self.app.after(0, self._display_thumbnail_in_viewer, pil_image, filepath)

    def _display_thumbnail_in_viewer(self, pil_image, original_filepath, is_loading=False):
        """
        (Hilo de UI) Muestra la miniatura generada en el visor.
        """
        # 1. Limpiar el visor anterior
        for widget in self.viewer_frame.winfo_children():
            widget.destroy()

        # 2. Comprobar si esta miniatura es obsoleta
        if original_filepath is not None and original_filepath != self.last_preview_path:
            print(f"DEBUG: Miniatura obsoleta de '{os.path.basename(original_filepath)}' descartada.")
            # No hacemos nada, dejamos el visor "Cargando..." para la nueva imagen
            return

        if is_loading:
            # 3. Mostrar "Cargando..."
            self.viewer_placeholder = ctk.CTkLabel(
                self.viewer_frame, text="Cargando...", text_color="gray"
            )
            self.viewer_placeholder.grid(row=0, column=0, sticky="nsew")
        
        elif pil_image:
            # 4. Mostrar la imagen generada
            try:
                # Calcular el tamaño máximo disponible en el visor
                max_width = self.viewer_frame.winfo_width() - 20  # Padding
                max_height = self.viewer_frame.winfo_height() - 20
                
                # Si el frame aún no tiene tamaño (primera carga), usar valores por defecto
                if max_width < 50 or max_height < 50:
                    max_width = 400
                    max_height = 300
                
                # Calcular el tamaño manteniendo la relación de aspecto
                img_width, img_height = pil_image.size
                aspect_ratio = img_width / img_height
                
                # Ajustar al contenedor manteniendo la relación de aspecto
                if img_width > max_width or img_height > max_height:
                    if aspect_ratio > (max_width / max_height):
                        # La imagen es más ancha
                        display_width = max_width
                        display_height = int(max_width / aspect_ratio)
                    else:
                        # La imagen es más alta
                        display_height = max_height
                        display_width = int(max_height * aspect_ratio)
                else:
                    # La imagen cabe sin redimensionar
                    display_width = img_width
                    display_height = img_height
                
                ctk_image = ctk.CTkImage(
                    light_image=pil_image, 
                    dark_image=pil_image, 
                    size=(display_width, display_height)
                )
                
                self.viewer_placeholder = ctk.CTkLabel(
                    self.viewer_frame, 
                    text="", 
                    image=ctk_image
                )
                self.viewer_placeholder.grid(row=0, column=0)
            except Exception as e:
                print(f"ERROR: No se pudo mostrar la CTkImage: {e}")
                self.viewer_placeholder = ctk.CTkLabel(
                    self.viewer_frame, text="Error al mostrar imagen", text_color="orange"
                )
                self.viewer_placeholder.grid(row=0, column=0, sticky="nsew")
        
        else:
            # 5. Mostrar el placeholder por defecto
            self.viewer_placeholder = ctk.CTkLabel(
                self.viewer_frame, 
                text="Selecciona un archivo de la lista para previsualizarlo",
                text_color="gray"
            )
            self.viewer_placeholder.grid(row=0, column=0, sticky="nsew")

    def _start_thumbnail_worker(self):
        """Inicia el hilo worker de miniaturas si no está activo"""
        if self.active_thumbnail_thread and self.active_thumbnail_thread.is_alive():
            return  # Ya hay un worker activo
        
        self.active_thumbnail_thread = threading.Thread(
            target=self._thumbnail_worker_loop,
            daemon=True
        )
        self.active_thumbnail_thread.start()

    def _thumbnail_worker_loop(self):
        """
        Worker que procesa la cola de miniaturas una a la vez.
        Solo genera la miniatura si sigue siendo la última solicitada.
        """
        while True:
            try:
                # 1. Obtener la tupla (filepath, page_num) de la cola
                (filepath, page_num) = self.thumbnail_queue.get(timeout=3.0)
                
                # 2. Crear la clave única
                cache_key = f"{filepath}::{page_num}"
                
            except queue.Empty:
                # Si la cola está vacía por 3 segundos, terminar el worker
                break
            
            # 3. Verificar si esta miniatura sigue siendo relevante
            if cache_key != self.last_preview_path:
                print(f"DEBUG: Miniatura de '{os.path.basename(filepath)}' (pág. {page_num}) saltada (obsoleta)")
                continue
            
            # Generar la miniatura
            try:
                # Obtener el tamaño del contenedor del visor
                try:
                    width = self.viewer_frame.winfo_width() - 20
                    height = self.viewer_frame.winfo_height() - 20
                    if width < 50 or height < 50:
                        width, height = 400, 300
                except Exception:
                    width, height = 400, 300
                
                # 4. Llamar al procesador CON el número de página
                pil_image = self.image_processor.generate_thumbnail(
                    filepath, 
                    size=(width, height),
                    page_number=page_num # <-- ¡EL NUEVO ARGUMENTO!
                )
                
                # 5. Verificar de nuevo si sigue siendo relevante
                if cache_key != self.last_preview_path:
                    print(f"DEBUG: Miniatura de '{os.path.basename(filepath)}' (pág. {page_num}) descartada después de generar")
                    continue
                
                if pil_image:
                    # Crear CTkImage
                    ctk_image = ctk.CTkImage(
                        light_image=pil_image,
                        dark_image=pil_image,
                        size=(pil_image.width, pil_image.height)
                    )
                    
                    # 6. Guardar en caché con la clave única
                    with self.thumbnail_lock:
                        self.thumbnail_cache[cache_key] = ctk_image
                    
                    # 7. Mostrar en la UI (desde el hilo principal)
                    self.app.after(0, self._display_cached_thumbnail, ctk_image, cache_key)
                
            except Exception as e:
                print(f"ERROR: No se pudo generar miniatura para {filepath} (pág {page_num}): {e}")
                # 8. Mostrar error en la UI
                self.app.after(0, self._display_thumbnail_in_viewer, None, cache_key)

    def _display_cached_thumbnail(self, ctk_image, original_filepath):
        """
        Muestra una miniatura que ya está en formato CTkImage.
        Más rápido que _display_thumbnail_in_viewer porque no convierte PIL->CTk.
        """
        # Verificar si esta miniatura es obsoleta
        if original_filepath != self.last_preview_path:
            return
        
        # Limpiar el visor anterior
        for widget in self.viewer_frame.winfo_children():
            widget.destroy()
        
        # Calcular dimensiones con aspecto
        max_width = self.viewer_frame.winfo_width() - 20
        max_height = self.viewer_frame.winfo_height() - 20
        
        if max_width < 50 or max_height < 50:
            max_width = 400
            max_height = 300
        
        img_width = ctk_image.cget("size")[0]
        img_height = ctk_image.cget("size")[1]
        aspect_ratio = img_width / img_height
        
        # Ajustar al contenedor manteniendo la relación de aspecto
        if img_width > max_width or img_height > max_height:
            if aspect_ratio > (max_width / max_height):
                display_width = max_width
                display_height = int(max_width / aspect_ratio)
            else:
                display_height = max_height
                display_width = int(max_height * aspect_ratio)
        else:
            display_width = img_width
            display_height = img_height
        
        # Crear una nueva imagen redimensionada
        display_image = ctk.CTkImage(
            light_image=ctk_image._light_image,
            dark_image=ctk_image._dark_image,
            size=(display_width, display_height)
        )
        
        label = ctk.CTkLabel(
            self.viewer_frame,
            text="",
            image=display_image
        )
        label.image = display_image  # Mantener referencia
        label.grid(row=0, column=0)

    def import_folder_from_path(self, folder_path):
        """
        (API PÚBLICA)
        Inicia un escaneo de carpeta desde una llamada externa (ej. SingleDownloadTab).
        """
        if not os.path.isdir(folder_path):
            print(f"ERROR: [ImageTools] La ruta {folder_path} no es una carpeta válida.")
            return
            
        print(f"INFO: [ImageTools] Importando programáticamente desde: {folder_path}")
        
        # 1. Cambiar a esta pestaña
        self.app.tab_view.set("Herramientas de Imagen")
        
        # 2. Bloquear botones y mostrar estado
        self._toggle_import_buttons("disabled")
        self.list_status_label.configure(text=f"Importando desde {os.path.basename(folder_path)}...")
        
        # 3. Reutilizar tu lógica de escaneo de carpeta existente
        threading.Thread(
            target=self._search_folder_thread, 
            args=(folder_path,), 
            daemon=True
        ).start()

    def _scan_and_import_dropped_paths(self, paths):
        """
        (HILO DE TRABAJO) Recorre los items arrastrados.
        Si es archivo: lo valida.
        Si es carpeta: la escanea recursivamente (os.walk).
        """
        files_to_process = []
        
        try:
            for path in paths:
                # Limpiar comillas si las hubiera
                path = path.strip('"')
                
                if os.path.isfile(path):
                    # CASO 1: Es un archivo
                    if path.lower().endswith(self.COMPATIBLE_EXTENSIONS):
                        files_to_process.append(path)
                
                elif os.path.isdir(path):
                    # CASO 2: Es una carpeta -> Escaneo Recursivo
                    print(f"DEBUG: Escaneando carpeta arrastrada: {path}")
                    for root, _, filenames in os.walk(path):
                        for f in filenames:
                            if f.lower().endswith(self.COMPATIBLE_EXTENSIONS):
                                full_path = os.path.join(root, f)
                                files_to_process.append(full_path)
            
            # Volver al hilo principal para procesar la lista final
            if files_to_process:
                print(f"INFO: Escaneo de drop finalizado. {len(files_to_process)} archivos encontrados.")
                self.app.after(0, self._process_imported_files, files_to_process)
            else:
                print("INFO: No se encontraron archivos compatibles en lo arrastrado.")
                self.app.after(0, lambda: self.list_status_label.configure(text="No se encontraron archivos compatibles."))

        except Exception as e:
            print(f"ERROR escaneando drop: {e}")
            self.app.after(0, lambda: messagebox.showerror("Error", f"Fallo al leer archivos arrastrados:\n{e}"))

    # ==================================================================
    # --- LÓGICA DE ELIMINAR FONDO (REMBG) ---
    # ==================================================================

    def _on_toggle_rembg_frame(self):
        """Muestra u oculta las opciones de rembg."""
        if self.rembg_checkbox.get() == 1:
            self.rembg_options_frame.pack(fill="x", padx=5, pady=0, after=self.rembg_checkbox)
            # Verificar el modelo seleccionado actualmente
            self._on_rembg_model_change(self.rembg_model_menu.get())
        else:
            self.rembg_options_frame.pack_forget()

    def _on_rembg_family_change(self, selected_family):
        """Actualiza el menú de modelos basado en la familia seleccionada."""
        models_dict = REMBG_MODEL_FAMILIES.get(selected_family, {})
        model_names = list(models_dict.keys())
        
        if model_names:
            self.rembg_model_menu.configure(values=model_names)
            # Intentar seleccionar el "general" o "recomendado" por defecto
            default_model = next((m for m in model_names if "General" in m or "Recomendado" in m), model_names[0])
            self.rembg_model_menu.set(default_model)
            self._on_rembg_model_change(default_model)
        else:
            self.rembg_model_menu.configure(values=["-"])
            self.rembg_model_menu.set("-")

    def _on_rembg_model_change(self, selected_model, silent=False):
        """
        Verifica si el modelo está descargado.
        CORRECCIÓN: Si la herramienta (checkbox) está apagada, no hace nada.
        """
        # --- NUEVA GUARDIA DE SEGURIDAD ---
        # Si el usuario no ha activado la casilla "Eliminar Fondo", 
        # no tiene sentido verificar ni pedir descargas. Salimos inmediatamente.
        if self.rembg_checkbox.get() != 1:
            return
        # ----------------------------------

        if selected_model == "-" or not selected_model: return

        family = self.rembg_family_menu.get()
        
        # Buscar el modelo en la estructura anidada
        model_info = REMBG_MODEL_FAMILIES.get(family, {}).get(selected_model)
        
        if not model_info: return

        filename = model_info["file"]
        folder = model_info.get("folder", "rembg")
        
        # Construir ruta: bin/models/{folder}/{filename}
        target_dir = os.path.join(MODELS_DIR, folder)
        file_path = os.path.join(target_dir, filename)
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            self.rembg_status_label.configure(text="✅ Modelo listo", text_color="gray")
            self.start_process_button.configure(state="normal")
        else:
            self.rembg_status_label.configure(text="⚠️ No instalado", text_color="orange")
            
            if silent:
                return

            # Preguntar al usuario si quiere descargar
            response = messagebox.askyesno(
                "Descargar Modelo IA", 
                f"El modelo '{selected_model}' no está instalado.\n\n"
                f"Se descargará en: bin/models/{folder}/\n"
                "¿Deseas descargarlo ahora?"
            )
            
            if response:
                self.rembg_model_menu.configure(state="disabled")
                self.rembg_family_menu.configure(state="disabled")
                self.start_process_button.configure(state="disabled")
                
                threading.Thread(
                    target=self._download_rembg_model_thread, 
                    args=(model_info, file_path), 
                    daemon=True
                ).start()
            else:
                 self.rembg_status_label.configure(text="❌ Descarga cancelada", text_color="red")

    def _download_rembg_model_thread(self, model_info, file_path):
        """
        Descarga el modelo con estrategia ROBUSTA (Reintentos + Timeouts largos).
        Diseñado para conexiones lentas o inestables.
        """
        url = model_info["url"]
        
        # Asegurar que la carpeta existe
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # --- CONFIGURACIÓN DE ROBUSTEZ ---
        # Configurar una sesión con reintentos automáticos
        session = requests.Session()
        
        # Estrategia de reintentos:
        # total=5: Intentará 5 veces si falla.
        # backoff_factor=1: Esperará 1s, 2s, 4s entre intentos (para dar tiempo al internet de volver).
        # status_forcelist: Reintentar si el servidor da errores temporales (500, 502, etc).
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        # ----------------------------------

        try:
            self.app.after(0, lambda: self.rembg_status_label.configure(text="⏳ Conectando...", text_color="#52a2f2"))
            
            # Timeout elevado (30s para conectar, 60s para leer datos)
            response = session.get(url, stream=True, timeout=(30, 60))
            response.raise_for_status()
            
            total_length = response.headers.get('content-length')
            
            with open(file_path, 'wb') as f:
                if total_length is None:
                    f.write(response.content)
                else:
                    dl = 0
                    total_length = int(total_length)
                    last_percent = -1
                    
                    # Chunk size aumentado ligeramente para buffer
                    for chunk in response.iter_content(chunk_size=16384): 
                        if chunk:
                            dl += len(chunk)
                            f.write(chunk)
                            
                            # Calcular porcentaje
                            percent = int(100 * dl / total_length)
                            
                            # Actualizar UI solo si cambió el porcentaje (para no saturar el hilo)
                            if percent > last_percent:
                                last_percent = percent
                                # Mostrar progreso y tamaño descargado
                                downloaded_mb = dl / (1024 * 1024)
                                total_mb = total_length / (1024 * 1024)
                                status_text = f"⏳ {percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
                                self.app.after(0, lambda t=status_text: self.rembg_status_label.configure(text=t, text_color="#52a2f2"))

            # Verificación final de tamaño (si el servidor envió content-length)
            if total_length is not None and os.path.getsize(file_path) != total_length:
                raise Exception("El archivo descargado está incompleto.")

            self.app.after(0, lambda: self.rembg_status_label.configure(text="✅ Descarga completada", text_color="green"))
            
            # Habilitar botón de proceso inmediatamente
            self.app.after(0, lambda: self.start_process_button.configure(state="normal"))
            
        except Exception as e:
            print(f"ERROR ROBUSO descargando modelo: {e}")
            
            # Mensaje de error amigable para el usuario
            error_msg = "❌ Error de red"
            if "timeout" in str(e).lower():
                error_msg = "❌ Internet muy lento (Timeout)"
            elif "connection" in str(e).lower():
                error_msg = "❌ Fallo de conexión"
                
            self.app.after(0, lambda m=error_msg: self.rembg_status_label.configure(text=m, text_color="red"))
            
            # Limpiar archivo corrupto/incompleto para evitar errores futuros
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
        
        finally:
            session.close()
            # Reactivar controles
            self.app.after(0, lambda: self.rembg_model_menu.configure(state="normal"))
            self.app.after(0, lambda: self.rembg_family_menu.configure(state="normal"))