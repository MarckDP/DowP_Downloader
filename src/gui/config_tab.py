import customtkinter as ctk
import os
import sys
import json
import threading
import requests
import time
from tkinter import filedialog, messagebox
from .dialogs import Tooltip, URLInputDialog

class ConfigTab(ctk.CTkFrame):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app
        
        # Listas para rastreo de widgets temáticos
        self.config_cards = []
        self.config_subtitles = []
        self.model_family_icons = []
        
        # Cargar colores iniciales
        self._load_theme_colors()
        
        # Ocupar todo el espacio de la pestaña
        self.pack(expand=True, fill="both")
        
        # Configurar grid principal (1 fila principal que se expande, 1 fila inferior fija, 2 columnas)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0) # Barra inferior
        self.grid_columnconfigure(0, weight=0) # Menú lateral fijo
        self.grid_columnconfigure(1, weight=1) # Área de contenido expandible
        
        # ==================== MENÚ LATERAL (Izquierda) ====================
        self.sidebar_frame = ctk.CTkFrame(self, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1) # Empujar elementos hacia arriba
        
        self.sidebar_title = ctk.CTkLabel(self.sidebar_frame, text="Opciones", font=ctk.CTkFont(size=16, weight="bold"))
        self.sidebar_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Botones del menú lateral
        self.btn_general = ctk.CTkButton(self.sidebar_frame, text="General", fg_color="transparent", text_color=self.MENU_NORMAL_TEXT, hover_color=self.MENU_SELECTED_BG, anchor="w", command=lambda: self.select_section("general"))
        self.btn_general.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_cookies = ctk.CTkButton(self.sidebar_frame, text="Cookies", fg_color="transparent", text_color=self.MENU_NORMAL_TEXT, hover_color=self.MENU_SELECTED_BG, anchor="w", command=lambda: self.select_section("cookies"))
        self.btn_cookies.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_deps = ctk.CTkButton(self.sidebar_frame, text="Dependencias", fg_color="transparent", text_color=self.MENU_NORMAL_TEXT, hover_color=self.MENU_SELECTED_BG, anchor="w", command=lambda: self.select_section("deps"))
        self.btn_deps.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_models = ctk.CTkButton(self.sidebar_frame, text="Modelos", fg_color="transparent", text_color=self.MENU_NORMAL_TEXT, hover_color=self.MENU_SELECTED_BG, anchor="w", command=lambda: self.select_section("models"))
        self.btn_models.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

        self.btn_console = ctk.CTkButton(self.sidebar_frame, text="Consola", fg_color="transparent", text_color=self.MENU_NORMAL_TEXT, hover_color=self.MENU_SELECTED_BG, anchor="w", command=lambda: self.select_section("console"))
        self.btn_console.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        
        # Guardamos los botones en un dict para cambiarles el color al seleccionarlos
        self.menu_buttons = {
            "general": self.btn_general,
            "cookies": self.btn_cookies,
            "deps": self.btn_deps,
            "models": self.btn_models,
            "console": self.btn_console,
        }
        
        # Cache de actualizaciones (Persistencia de sesión)
        self.update_cache = {}
        
        # ==================== ÁREA DE CONTENIDO (Derecha) ====================
        self.content_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)
        
        # Diccionario para guardar los frames de cada sección
        self.sections = {}

        # --- Estado de la Consola ---
        self._console_at_start = True
        self._console_wrap_var = ctk.BooleanVar(value=getattr(self.app, 'console_wrap', False))
        
        self._setup_sections()
        self._setup_console_section()
        
        # ==================== BARRA INFERIOR (Abajo) ====================
        self.bottom_frame = ctk.CTkFrame(self, height=40, corner_radius=0)
        self.bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.bottom_frame.pack_propagate(False) # Prevenir que cambie de altura por el contenido
        
        # Contenido de la barra inferior
        self.about_label = ctk.CTkLabel(self.bottom_frame, text="DowP by MarckDBM |", font=ctk.CTkFont(size=12, weight="bold"))
        self.about_label.pack(side="left", padx=(15, 5), pady=10)
        
        import webbrowser
        
        self.link_yt = ctk.CTkButton(self.bottom_frame, text="YouTube", width=60, height=20, fg_color=self.DOWNLOAD_BTN, text_color=self.DOWNLOAD_TEXT, hover_color=self.DOWNLOAD_HOVER, command=lambda: webbrowser.open("https://www.youtube.com/@MarckDBM"))
        self.link_yt.pack(side="left", padx=5)

        self.link_github = ctk.CTkButton(self.bottom_frame, text="GitHub", width=50, height=20, fg_color=self.SECONDARY_BTN, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER, command=lambda: webbrowser.open("https://github.com/MarckDP/DowP_Downloader"))
        self.link_github.pack(side="left", padx=5)
        
        self.link_donate = ctk.CTkButton(self.bottom_frame, text="Ko-fi ☕", width=80, height=20, fg_color=self.TERTIARY_BTN, text_color=self.TERTIARY_TEXT, hover_color=self.TERTIARY_HOVER, command=lambda: webbrowser.open("https://ko-fi.com/marckdbm"))
        self.link_donate.pack(side="left", padx=5)

        self.version_label = ctk.CTkLabel(self.bottom_frame, text=f"Versión {getattr(self.app, 'APP_VERSION', 'Desconocida')}", font=ctk.CTkFont(size=12), text_color=self.MENU_NORMAL_TEXT)
        self.version_label.pack(side="right", padx=15, pady=10)


        # Seleccionar la primera sección por defecto
        self.select_section("general")

    def _setup_sections(self):
        """Inicializa los frames para cada sección pero los oculta por defecto."""
        
        # ===== Sección: General =====
        frame_general = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        
        # --- BLOQUE: APARIENCIA (NUEVO) ---
        ctk.CTkLabel(frame_general, text="Apariencia", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(10, 2), padx=10)
        
        self.appearance_frame = ctk.CTkFrame(frame_general, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.appearance_frame.pack(fill="x", pady=5, padx=5)
        self.config_cards.append(self.appearance_frame)
        
        # --- FILA 1: TEMA Y MODO (Agrupados) ---
        top_row = ctk.CTkFrame(self.appearance_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=15, pady=(15, 10))
        
        # Contenedor para mantenerlos juntos a la izquierda
        selection_group = ctk.CTkFrame(top_row, fg_color="transparent")
        selection_group.pack(side="left")

        accent_lbl = ctk.CTkLabel(selection_group, text="Tema:", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.SECTION_SUBTITLE)
        accent_lbl.pack(side="left")
        self.config_subtitles.append(accent_lbl)
        
        # Mapeo de nombres para el menú (Temas Base de CustomTkinter)
        self.theme_display_names = {
            "blue": "Azul (Estándar)",
            "dark-blue": "Azul Profundo",
            "green": "Verde (Estándar)"
        }
        self.theme_internal_names = {v: k for k, v in self.theme_display_names.items()}
        
        self.theme_menu = ctk.CTkOptionMenu(
            selection_group, 
            values=["Azul (Estándar)", "Azul Profundo"], 
            command=self._on_theme_change,
            width=160
        )
        self.theme_menu.pack(side="left", padx=(10, 40)) # Espacio de 40px entre menús

        mode_lbl = ctk.CTkLabel(selection_group, text="Modo:", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.SECTION_SUBTITLE)
        mode_lbl.pack(side="left")
        self.config_subtitles.append(mode_lbl)
        
        self.appearance_mode_menu = ctk.CTkOptionMenu(
            selection_group,
            values=["Sistema", "Claro", "Oscuro"],
            command=self._on_appearance_mode_change,
            width=120
        )
        self.appearance_mode_menu.pack(side="left", padx=10)
        
        # Cargar valor guardado
        current_mode = getattr(self.app, 'appearance_mode', 'System')
        mode_map = {"System": "Sistema", "Light": "Claro", "Dark": "Oscuro"}
        self.appearance_mode_menu.set(mode_map.get(current_mode, "Sistema"))
        
        # --- FILA 2: BOTONES DE ACCIÓN (Reordenados) ---
        buttons_row = ctk.CTkFrame(self.appearance_frame, fg_color="transparent")
        buttons_row.pack(fill="x", padx=15, pady=(0, 15))
        
        # 1. Importar
        self.import_theme_btn = ctk.CTkButton(
            buttons_row, 
            text="Importar Tema", 
            width=100,
            fg_color=self.TERTIARY_BTN,
            hover_color=self.TERTIARY_HOVER,
            text_color=self.TERTIARY_TEXT,
            command=self._import_theme
        )
        self.import_theme_btn.pack(side="left", padx=5)

        # 2. Instalar URL (Movido aquí)
        self.install_url_btn = ctk.CTkButton(
            buttons_row, 
            text="Instalar URL", 
            width=100,
            fg_color=self.TERTIARY_BTN,
            hover_color=self.TERTIARY_HOVER,
            text_color=self.TERTIARY_TEXT,
            command=self._install_theme_from_url
        )
        self.install_url_btn.pack(side="left", padx=5)

        # 3. Ver Plantilla
        self.view_template_btn = ctk.CTkButton(
            buttons_row, 
            text="Ver Plantilla", 
            width=100,
            fg_color=self.TERTIARY_BTN,
            hover_color=self.TERTIARY_HOVER,
            text_color=self.TERTIARY_TEXT,
            command=self._on_view_template
        )
        self.view_template_btn.pack(side="left", padx=5)

        # 4. Abrir Carpeta (Emoji y movido)
        self.open_themes_btn = ctk.CTkButton(
            buttons_row, 
            text="📁", 
            width=40,
            fg_color=self.TERTIARY_BTN,
            hover_color=self.TERTIARY_HOVER,
            text_color=self.TERTIARY_TEXT,
            command=self._open_themes_folder
        )
        self.open_themes_btn.pack(side="left", padx=5)

        # 5. Borrar Tema (Nombre corto)
        self.delete_theme_btn = ctk.CTkButton(
            buttons_row, 
            text="Borrar Tema", 
            width=100,
            fg_color=self.CANCEL_BTN,
            hover_color=self.CANCEL_HOVER,
            text_color=self.CANCEL_TEXT,
            command=self._delete_theme
        )
        self.delete_theme_btn.pack(side="left", padx=5)

        self._refresh_theme_list()

        # --- TÍTULO SECCIÓN ---
        ctk.CTkLabel(frame_general, text="Herramientas de Imagen", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(10, 2), padx=10)
        ctk.CTkLabel(frame_general, text="Ajustes de procesamiento, modelos de IA y motores vectoriales.", font=ctk.CTkFont(size=11), text_color="gray60").pack(anchor="w", pady=(0, 10), padx=10)

        # CUADRO MAESTRO
        self.master_frame = ctk.CTkFrame(frame_general, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.master_frame.pack(fill="x", pady=5, padx=5)
        self.config_cards.append(self.master_frame)
        
        # 1. GESTIÓN DE IA (VRAM)
        vram_group = ctk.CTkFrame(self.master_frame, fg_color="transparent")
        vram_group.pack(fill="x", padx=15, pady=15)
        
        vram_header = ctk.CTkLabel(vram_group, text="Motor de Inteligencia Artificial (ONNX)", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.SECTION_SUBTITLE)
        vram_header.pack(anchor="w", pady=(0, 5))
        self.config_subtitles.append(vram_header)
        
        vram_controls = ctk.CTkFrame(vram_group, fg_color="transparent")
        vram_controls.pack(fill="x")
        
        self.keep_vram_var = ctk.BooleanVar(value=getattr(self.app, 'keep_ai_models_in_memory', False))
        self.keep_vram_switch = ctk.CTkSwitch(vram_controls, text="Mantener modelos cargados en memoria (VRAM)", variable=self.keep_vram_var, command=self._on_vram_persistence_toggle)
        self.keep_vram_switch.pack(side="left")
        
        self.clear_vram_btn = ctk.CTkButton(
            vram_controls, 
            text="Liberar VRAM Ahora", 
            width=160, height=26, 
            font=ctk.CTkFont(size=11, weight="bold"), 
            fg_color=self.CANCEL_BTN, 
            hover_color=self.CANCEL_HOVER, 
            text_color=self.CANCEL_TEXT, 
            command=self._manual_vram_clear
        )
        self.clear_vram_btn.pack(side="right")
        
        # SEPARADOR
        ctk.CTkFrame(self.master_frame, height=2, fg_color=("gray80", "gray25")).pack(fill="x", padx=15)
        
        # 2. RESOLUCIÓN Y DPI (LADO A LADO)
        dpi_group = ctk.CTkFrame(self.master_frame, fg_color="transparent")
        dpi_group.pack(fill="x", padx=15, pady=15)
        
        dpi_header = ctk.CTkLabel(dpi_group, text="Calidad de Renderizado y Previsualización", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.SECTION_SUBTITLE)
        dpi_header.pack(anchor="w", pady=(0, 10))
        self.config_subtitles.append(dpi_header)
        
        dpi_row = ctk.CTkFrame(dpi_group, fg_color="transparent")
        dpi_row.pack(fill="x")
        dpi_row.grid_columnconfigure(0, weight=1)
        dpi_row.grid_columnconfigure(1, weight=1)
        
        # --- LADO IZQUIERDO: RENDER DPI ---
        render_frame = ctk.CTkFrame(dpi_row, fg_color="transparent")
        render_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        ctk.CTkLabel(render_frame, text="Calidad Final (DPI):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        
        render_controls = ctk.CTkFrame(render_frame, fg_color="transparent")
        render_controls.pack(fill="x", pady=5)
        
        self.vector_dpi_var = ctk.IntVar(value=self.app.vector_dpi)
        self.dpi_slider = ctk.CTkSlider(render_controls, from_=70, to=1200, variable=self.vector_dpi_var, command=self._on_vector_dpi_change)
        self.dpi_slider.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.dpi_entry = ctk.CTkEntry(render_controls, width=55, height=24)
        self.dpi_entry.insert(0, str(self.app.vector_dpi))
        self.dpi_entry.pack(side="right")
        self.dpi_entry.bind("<KeyRelease>", self._on_dpi_entry_change)
        
        # --- LADO DERECHO: PREVIEW DPI ---
        preview_frame = ctk.CTkFrame(dpi_row, fg_color="transparent")
        preview_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        ctk.CTkLabel(preview_frame, text="Nitidez Visor (DPI):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        
        preview_controls = ctk.CTkFrame(preview_frame, fg_color="transparent")
        preview_controls.pack(fill="x", pady=5)
        
        self.preview_dpi_var = ctk.IntVar(value=self.app.preview_vector_dpi)
        self.preview_slider = ctk.CTkSlider(preview_controls, from_=72, to=150, variable=self.preview_dpi_var, command=self._on_preview_dpi_change)
        self.preview_slider.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.preview_dpi_label = ctk.CTkLabel(preview_controls, text=f"{self.app.preview_vector_dpi} DPI", font=ctk.CTkFont(size=12, weight="bold"), width=55)
        self.preview_dpi_label.pack(side="right")
        
        # EXPLICACIÓN DPI
        dpi_desc = "El DPI de renderizado define la calidad del archivo exportado (estándar: 300), mientras que el de previsualización controla la nitidez y velocidad de las miniaturas en el visor."
        ctk.CTkLabel(dpi_group, text=dpi_desc, font=ctk.CTkFont(size=11), text_color="gray60", justify="left", wraplength=550).pack(anchor="w", pady=(5, 0))
        
        # ADVERTENCIA DPI ALTO (Ahora es un atributo de clase para manejarlo bien)
        self.dpi_warning_label = ctk.CTkLabel(
            dpi_group, 
            text="⚠️ Valores > 1200 DPI pueden agotar la RAM. Usar con precaución.", 
            font=ctk.CTkFont(size=11, weight="bold"), 
            text_color="#FF8C00",
            wraplength=550,
            justify="left"
        )
        if self.app.vector_dpi > 1200:
            self.dpi_warning_label.pack(anchor="w", pady=(5, 0))

        # SEPARADOR
        ctk.CTkFrame(self.master_frame, height=2, fg_color=("gray80", "gray25")).pack(fill="x", padx=15)
        
        # 3. AVANZADO (INKSCAPE Y FONDO)
        adv_group = ctk.CTkFrame(self.master_frame, fg_color="transparent")
        adv_group.pack(fill="x", padx=15, pady=15)
        
        adv_header = ctk.CTkLabel(adv_group, text="Opciones Avanzadas y Compatibilidad", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.SECTION_SUBTITLE)
        adv_header.pack(anchor="w", pady=(0, 10))
        self.config_subtitles.append(adv_header)
        
        # --- FILA 1: FONDO SÓLIDO ---
        self.vector_bg_var = ctk.BooleanVar(value=self.app.vector_force_background)
        self.vector_bg_switch = ctk.CTkSwitch(adv_group, text="Forzar fondo sólido (Aplanado) en vectores", variable=self.vector_bg_var, command=self._on_vector_bg_toggle)
        self.vector_bg_switch.pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(adv_group, text="Añade un fondo blanco a archivos AI, EPS y PS (como en los PDF) para evitar transparencias no deseadas.", font=ctk.CTkFont(size=11), text_color="gray60").pack(anchor="w", padx=25, pady=(0, 15))

        # --- FILA 2: INKSCAPE ---
        ink_header_row = ctk.CTkFrame(adv_group, fg_color="transparent")
        ink_header_row.pack(fill="x")
        
        self.inkscape_enabled_var = ctk.BooleanVar(value=self.app.inkscape_enabled)
        self.inkscape_switch = ctk.CTkSwitch(ink_header_row, text="Usar Inkscape para conversiones profesionales", variable=self.inkscape_enabled_var, command=self._on_inkscape_toggle)
        self.inkscape_switch.pack(side="left")
        
        # Ruta de Inkscape
        ink_path_frame = ctk.CTkFrame(adv_group, fg_color="transparent")
        ink_path_frame.pack(fill="x", pady=(10, 5))
        
        self.inkscape_path_entry = ctk.CTkEntry(ink_path_frame, placeholder_text=r"C:\Program Files\Inkscape")
        self.inkscape_path_entry.insert(0, self.app.inkscape_path)
        self.inkscape_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.inkscape_path_entry.bind("<KeyRelease>", self._on_inkscape_path_change)
        
        self.ink_browse_btn = ctk.CTkButton(ink_path_frame, text="Examinar...", width=90, height=28, command=self._browse_inkscape_path)
        self.ink_browse_btn.pack(side="right")
        
        # Fila de Estado y Acciones de Inkscape
        ink_status_row = ctk.CTkFrame(adv_group, fg_color="transparent")
        ink_status_row.pack(fill="x", pady=(5, 0))
        
        # Botón de descarga (A la izquierda del de verificar)
        import webbrowser
        INKSCAPE_URL = "https://inkscape.org/release/1.4/windows/"
        self.ink_download_btn = ctk.CTkButton(
            ink_status_row, 
            text="Descargar Inkscape", 
            width=130, height=26, 
            fg_color=self.SECONDARY_BTN,
            hover_color=self.SECONDARY_HOVER,
            text_color=self.SECONDARY_TEXT,
            command=lambda: webbrowser.open(INKSCAPE_URL)
        )
        self.ink_download_btn.pack(side="left", padx=(0, 10))
        
        self.ink_verify_btn = ctk.CTkButton(
            ink_status_row, 
            text="Verificar Instalación", 
            width=130, height=26, 
            fg_color=self.DOWNLOAD_BTN,
            hover_color=self.DOWNLOAD_HOVER,
            text_color=self.DOWNLOAD_TEXT,
            command=self._check_inkscape_status
        )
        self.ink_verify_btn.pack(side="left", padx=(0, 10))
        
        # Estado Inkscape
        initial_status = "Inkscape desactivado."
        initial_color = "gray50"
        if self.app.inkscape_enabled:
             if self.app.inkscape_version:
                 initial_status = f"✅ Detectado: {self.app.inkscape_version}"
                 initial_color = "#28A745"
             else:
                 initial_status = "⚠️ Pendiente de verificación."
                 initial_color = "#FFC107"

        self.ink_status_label = ctk.CTkLabel(ink_status_row, text=initial_status, font=ctk.CTkFont(size=11, weight="bold"), text_color=initial_color)
        self.ink_status_label.pack(side="left")

        # --- BLOQUE: INTEGRACIONES (NUEVO) ---
        ctk.CTkLabel(frame_general, text="Integraciones", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(10, 2), padx=10)
        ctk.CTkLabel(frame_general, text="Conecta DowP con aplicaciones de edición externas.", font=ctk.CTkFont(size=11), text_color="gray60").pack(anchor="w", pady=(0, 10), padx=10)

        self.integrations_frame = ctk.CTkFrame(frame_general, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.integrations_frame.pack(fill="x", pady=5, padx=5)
        self.config_cards.append(self.integrations_frame)

        # --- ADOBE ---
        adobe_group = ctk.CTkFrame(self.integrations_frame, fg_color="transparent")
        adobe_group.pack(fill="x", padx=15, pady=15)
        
        adobe_header_frame = ctk.CTkFrame(adobe_group, fg_color="transparent")
        adobe_header_frame.pack(fill="x", pady=(0, 10))

        adobe_header = ctk.CTkLabel(adobe_header_frame, text="Adobe (Premiere Pro / After Effects)", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.SECTION_SUBTITLE)
        adobe_header.pack(side="left")
        self.config_subtitles.append(adobe_header)

        self.adobe_master_var = ctk.BooleanVar(value=getattr(self.app, 'adobe_enabled', True))
        self.adobe_master_switch = ctk.CTkSwitch(adobe_header_frame, text="Activar integración", variable=self.adobe_master_var, command=self._on_integration_toggle, progress_color="#C17B42")
        self.adobe_master_switch.pack(side="right")

        adobe_switches = ctk.CTkFrame(adobe_group, fg_color="transparent")
        adobe_switches.pack(fill="x")

        self.adobe_single_var = ctk.BooleanVar(value=getattr(self.app, 'adobe_import_single', True))
        self.adobe_single_switch = ctk.CTkSwitch(adobe_switches, text="Proceso único", variable=self.adobe_single_var, command=self._on_integration_toggle)
        self.adobe_single_switch.pack(side="left", padx=(0, 20))

        self.adobe_batch_var = ctk.BooleanVar(value=getattr(self.app, 'adobe_import_batch', True))
        self.adobe_batch_switch = ctk.CTkSwitch(adobe_switches, text="Proceso por lotes", variable=self.adobe_batch_var, command=self._on_integration_toggle)
        self.adobe_batch_switch.pack(side="left", padx=(0, 20))

        self.adobe_image_var = ctk.BooleanVar(value=getattr(self.app, 'adobe_import_image', True))
        self.adobe_image_switch = ctk.CTkSwitch(adobe_switches, text="Herramientas de imagen", variable=self.adobe_image_var, command=self._on_integration_toggle)
        self.adobe_image_switch.pack(side="left")

        # SEPARADOR
        ctk.CTkFrame(self.integrations_frame, height=2, fg_color=("gray80", "gray25")).pack(fill="x", padx=15)

        # --- DAVINCI ---
        davinci_group = ctk.CTkFrame(self.integrations_frame, fg_color="transparent")
        davinci_group.pack(fill="x", padx=15, pady=15)
        
        davinci_header_frame = ctk.CTkFrame(davinci_group, fg_color="transparent")
        davinci_header_frame.pack(fill="x", pady=(0, 10))

        davinci_header = ctk.CTkLabel(davinci_header_frame, text="DaVinci Resolve (Solo versión Studio)", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.SECTION_SUBTITLE)
        davinci_header.pack(side="left")
        self.config_subtitles.append(davinci_header)

        self.davinci_master_var = ctk.BooleanVar(value=getattr(self.app, 'davinci_enabled', True))
        self.davinci_master_switch = ctk.CTkSwitch(davinci_header_frame, text="Activar integración", variable=self.davinci_master_var, command=self._on_integration_toggle, progress_color="#C17B42")
        self.davinci_master_switch.pack(side="right")

        davinci_switches_top = ctk.CTkFrame(davinci_group, fg_color="transparent")
        davinci_switches_top.pack(fill="x", pady=(0, 10))

        self.davinci_single_var = ctk.BooleanVar(value=getattr(self.app, 'davinci_import_single', True))
        self.davinci_single_switch = ctk.CTkSwitch(davinci_switches_top, text="Proceso único", variable=self.davinci_single_var, command=self._on_integration_toggle)
        self.davinci_single_switch.pack(side="left", padx=(0, 20))

        self.davinci_batch_var = ctk.BooleanVar(value=getattr(self.app, 'davinci_import_batch', True))
        self.davinci_batch_switch = ctk.CTkSwitch(davinci_switches_top, text="Proceso por lotes", variable=self.davinci_batch_var, command=self._on_integration_toggle)
        self.davinci_batch_switch.pack(side="left", padx=(0, 20))

        self.davinci_image_var = ctk.BooleanVar(value=getattr(self.app, 'davinci_import_image', True))
        self.davinci_image_switch = ctk.CTkSwitch(davinci_switches_top, text="Herramientas de imagen", variable=self.davinci_image_var, command=self._on_integration_toggle)
        self.davinci_image_switch.pack(side="left")

        davinci_extra_row = ctk.CTkFrame(davinci_group, fg_color="transparent")
        davinci_extra_row.pack(fill="x")

        self.davinci_everything_var = ctk.BooleanVar(value=getattr(self.app, 'davinci_import_everything', False))
        self.davinci_everything_switch = ctk.CTkSwitch(davinci_extra_row, text="Importar originales y procesados", variable=self.davinci_everything_var, command=self._on_integration_toggle)
        self.davinci_everything_switch.pack(side="left", padx=(0, 20))

        self.davinci_timeline_var = ctk.BooleanVar(value=getattr(self.app, 'davinci_import_to_timeline', False))
        self.davinci_timeline_switch = ctk.CTkSwitch(davinci_extra_row, text="Importar a línea de tiempo", variable=self.davinci_timeline_var, command=self._on_integration_toggle)
        self.davinci_timeline_switch.pack(side="left")

        self.sections["general"] = frame_general
        
        # Sincronización inicial de estados de switches
        self._update_integration_switches_state()
        
        # ===== Sección: Cookies =====
        frame_cookies = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        ctk.CTkLabel(frame_cookies, text="Gestión de Cookies", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        cookie_desc = "Configura las cookies para acceder a contenido protegido por edad, videos privados, o contenido restringido que requiera haber iniciado sesión en el servicio."
        ctk.CTkLabel(frame_cookies, text=cookie_desc, justify="left", wraplength=600, text_color="gray60").pack(anchor="w", pady=(0, 20))
        
        # Selector de Modo
        ctk.CTkLabel(frame_cookies, text="Modo de Cookies:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        mode_frame = ctk.CTkFrame(frame_cookies, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(5, 15))
        
        self.cookie_mode_menu = ctk.CTkOptionMenu(
            mode_frame, 
            values=["No usar", "Archivo Manual...", "Desde Navegador"], 
            command=self.on_cookie_mode_change
        )
        self.cookie_mode_menu.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.test_cookies_btn = ctk.CTkButton(
            mode_frame,
            text="Probar Cookies",
            width=120,
            fg_color=self.DOWNLOAD_BTN,
            hover_color=self.DOWNLOAD_HOVER,
            text_color=self.DOWNLOAD_TEXT,
            state="disabled",
            command=self._test_cookies
        )
        self.test_cookies_btn.pack(side="right")

        # Contenedor Dinámico
        self.cookie_dynamic_frame = ctk.CTkFrame(frame_cookies, fg_color="transparent", height=0)
        self.cookie_dynamic_frame.pack(fill="x")
        
        # ---- Modo Archivo Manual ----
        self.manual_cookie_frame = ctk.CTkFrame(self.cookie_dynamic_frame, fg_color="transparent")
        self.cookie_path_entry = ctk.CTkEntry(self.manual_cookie_frame, placeholder_text="Ruta al archivo cookies.txt...")
        self.cookie_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.cookie_path_entry.bind("<KeyRelease>", self._on_cookie_detail_change)
        
        self.select_cookie_file_button = ctk.CTkButton(self.manual_cookie_frame, text="Examinar...", width=100, command=self.select_cookie_file)
        self.select_cookie_file_button.pack(side="right")
        
        # ---- Modo Navegador ----
        self.browser_options_frame = ctk.CTkFrame(self.cookie_dynamic_frame, fg_color="transparent")
        ctk.CTkLabel(self.browser_options_frame, text="Navegador:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        
        self.browser_var = ctk.StringVar(value=self.app.selected_browser_saved)
        self.browser_menu = ctk.CTkOptionMenu(self.browser_options_frame, values=["chrome", "firefox", "edge", "opera", "vivaldi", "brave"], variable=self.browser_var, command=self._on_cookie_detail_change)
        self.browser_menu.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(self.browser_options_frame, text="Perfil (Opcional):").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.browser_profile_entry = ctk.CTkEntry(self.browser_options_frame, placeholder_text="Ej: Default, Profile 1")
        self.browser_profile_entry.grid(row=1, column=1, sticky="ew", pady=5)
        self.browser_profile_entry.bind("<KeyRelease>", self._on_cookie_detail_change)
        
        notice_frame = ctk.CTkFrame(self.browser_options_frame, fg_color=("#FCF2CE", "#3D3725"), corner_radius=self.CONFIG_CARD_RADIUS)
        notice_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(15, 0))
        self.config_cards.append(notice_frame)
        
        notice_text = (
            "⚠️ Los navegadores Chromium (Chrome, Edge, Brave, Opera, Vivaldi) han "
            "implementado bloqueos de cifrado muy estrictos que impiden extraer sus cookies directamente.\n\n"
            "✅ Se recomienda usar Firefox (o sus variantes) ya que permiten una extracción directa de sesión más estable, "
            "o en su lugar optar por usar el modo superior: 'Archivo Manual'. \n(Si igualmente ocurre un fallo durante la extracción, asegúrate de haber cerrado el navegador por completo primero)."
        )
        ctk.CTkLabel(
            notice_frame, 
            text=notice_text, 
            font=ctk.CTkFont(size=11), 
            text_color=("gray10", "white"), 
            justify="left", 
            wraplength=520
        ).pack(padx=15, pady=10, anchor="w")
        
        # --- Sección de Ayuda ---
        self.help_frame = ctk.CTkFrame(frame_cookies, fg_color=("#E3F2FD", "#162E40"), corner_radius=self.CONFIG_CARD_RADIUS)
        self.help_frame.pack(fill="x", pady=(30, 0), ipadx=10, ipady=10)
        self.config_cards.append(self.help_frame)
        
        ctk.CTkLabel(self.help_frame, text="¿Cómo obtener cookies locales de forma segura?", font=ctk.CTkFont(weight="bold"), text_color=("gray10", "white")).pack(anchor="w", padx=20, pady=(10, 5))
        
        ctk.CTkLabel(self.help_frame, text="Se recomienda exportar tu sesión actual usando la extensión de navegador Get cookies.txt LOCALLY en formato NetScape y luego cargar ese archivo .txt usando la opción 'Archivo Manual'. Es el método más seguro y confiable.", justify="left", text_color=("gray20", "gray90"), wraplength=550).pack(anchor="w", padx=20, pady=(0, 10))
        
        import webbrowser
        ctk.CTkButton(
            self.help_frame, 
            text="Descargar 'Get cookies.txt LOCALLY' (GitHub)", 
            fg_color=("#3B8ED0", "#1F6AA5"), 
            border_width=0, 
            text_color="white", 
            font=ctk.CTkFont(weight="bold"),
            command=lambda: webbrowser.open_new_tab("https://github.com/kairi003/Get-cookies.txt-LOCALLY")
        ).pack(anchor="w", padx=20, pady=(0, 10))
        
        self.sections["cookies"] = frame_cookies
        
        # --- Inyectores Iniciales ---
        self.cookie_mode_menu.set(self.app.cookies_mode_saved)
        if self.app.cookies_path: 
            self.cookie_path_entry.insert(0, self.app.cookies_path) 
        if self.app.browser_profile_saved:
            self.browser_profile_entry.insert(0, self.app.browser_profile_saved)
        # Mostrar el panel correcto según lo guardado
        self.on_cookie_mode_change(self.app.cookies_mode_saved, save=False)

        # ===== Sección: Dependencias =====
        frame_deps = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        
        # Título principal
        ctk.CTkLabel(frame_deps, text="Dependencias y Herramientas Externas", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 20))
        
        # --- SUB-SECCIÓN: ACTUALIZABLES ---
        updatable_header_frame = ctk.CTkFrame(frame_deps, fg_color="transparent")
        updatable_header_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(updatable_header_frame, text="Componentes Actualizables", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        
        self.btn_check_all_updates = ctk.CTkButton(
            updatable_header_frame, 
            text="Buscar Actualizaciones", 
            width=150, 
            fg_color=self.ANALYZE_BTN, 
            hover_color=self.ANALYZE_HOVER, 
            text_color=self.ANALYZE_TEXT,
            command=self.check_all_updates
        )
        self.btn_check_all_updates.pack(side="right", padx=5)
        
        # Frame contenedor para las actualizables
        self.updatable_frame = ctk.CTkFrame(frame_deps, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.updatable_frame.pack(fill="x", pady=(0, 20), padx=5)
        self.config_cards.append(self.updatable_frame)
        
        # Diccionarios para guardar referencias a las etiquetas y botones
        self.dep_labels = {}
        self.dep_progress = {}
        self.dep_buttons = {}
        
        # Crear filas (FFmpeg, Deno, Poppler, yt-dlp)
        self._create_dependency_row(self.updatable_frame, "FFmpeg", "Motor de procesamiento multimedia", "ffmpeg")
        self._create_dependency_row(self.updatable_frame, "Deno", "Entorno de ejecución interno", "deno")
        self._create_dependency_row(self.updatable_frame, "Poppler", "Herramienta de extracción de PDF", "poppler")
        self._create_dependency_row(self.updatable_frame, "yt-dlp", "Motor principal de descargas", "ytdlp")
        
        # --- SEPARADOR VISUAL ---
        separator = ctk.CTkFrame(frame_deps, height=2, fg_color=self.SEPARATOR_COLOR)
        separator.pack(fill="x", pady=(10, 20), padx=20)
        
        # --- SUB-SECCIÓN: FIJAS ---
        ctk.CTkLabel(frame_deps, text="Dependencias Fijas (Integridad del Sistema)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(0, 5))
        
        ctk.CTkLabel(frame_deps, text="Para actualizar estas herramientas debes hacer una instalación manual descargando los binarios correspondientes y reemplazando sus archivos dentro de la carpeta 'bin' del programa.", font=ctk.CTkFont(size=12), text_color="gray60", justify="left", wraplength=550).pack(anchor="w", padx=20, pady=(0, 10))
        
        # Frame contenedor para las fijas
        self.fixed_frame = ctk.CTkFrame(frame_deps, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.fixed_frame.pack(fill="x", padx=5)
        self.config_cards.append(self.fixed_frame)
        
        # Crear filas (Ghostscript)
        self._create_fixed_dependency_row(self.fixed_frame, "Ghostscript", "Motor de renderizado de vectores", "ghostscript", "https://ghostscript.com/releases/gsdnld.html")
        
        # --- Aviso Final de Recuperación ---
        recovery_frame = ctk.CTkFrame(frame_deps, fg_color=("#FCF2CE", "#3D3725"), corner_radius=self.CONFIG_CARD_RADIUS)
        recovery_frame.pack(fill="x", pady=(20, 0), padx=5)
        self.config_cards.append(recovery_frame)
        
        # Usamos un label con mejores márgenes para evitar que se corte la primera letra
        self.recovery_label = ctk.CTkLabel(
            recovery_frame, 
            text="Estas dependencias son necesarias para las Herramientas de Imagen y ya vienen pre-instaladas. Si notas que te faltan, fallan o se han corrompido, la opción recomendada es reinstalar el programa directamente desde la página oficial.", 
            justify="left", 
            text_color=("gray10", "#DCE4EE"), 
            wraplength=550
        )
        self.recovery_label.pack(anchor="w", padx=(25, 20), pady=(15, 5))
        
        import webbrowser
        ctk.CTkButton(recovery_frame, text="Página Oficial de DowP", fg_color=self.DOWNLOAD_BTN, hover_color=self.DOWNLOAD_HOVER, text_color=self.DOWNLOAD_TEXT, command=lambda: webbrowser.open("https://marckdp.github.io/DowP/")).pack(anchor="w", padx=20, pady=(5, 15))

        self.sections["deps"] = frame_deps
        # Mitigar glitch visual al hacer scroll
        frame_deps._scrollbar.bind("<B1-Motion>", lambda e: self.app.update_idletasks())
        frame_deps.bind("<MouseWheel>", lambda e: self.app.after(10, self.app.update_idletasks))
        
        # Cargar versiones locales inmediatamente (Offline-First)
        self.app.after(100, self._load_local_versions)

        # ===== Sección: Modelos =====
        frame_models = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        self.models_content_frame = frame_models
        ctk.CTkLabel(frame_models, text="Modelos de Inteligencia Artificial", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(frame_models, text="Gestiona los modelos de IA usados por las herramientas de imagen. Puedes descargar los que necesites, ver cuánto ocupan o eliminarlos para liberar espacio.", justify="left", wraplength=600, text_color="gray60").pack(anchor="w", pady=(0, 20))

        # -- Grupo: Eliminación de Fondo (Rembg) --
        ctk.CTkLabel(frame_models, text="Eliminación de Fondo (Rembg)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 8))
        self.rembg_models_frame = ctk.CTkFrame(frame_models, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.rembg_models_frame.pack(fill="x", pady=(0, 20), padx=5)
        self.config_cards.append(self.rembg_models_frame)
        self.model_rows = {}

        self._populate_rembg_model_rows()

        # -- Grupo: Motores de Reescalado (Upscaling) --
        ctk.CTkLabel(frame_models, text="Motores de Reescalado (Upscaling)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 8))
        self.upscaling_models_frame = ctk.CTkFrame(frame_models, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.upscaling_models_frame.pack(fill="x", pady=(0, 10), padx=5)
        self.config_cards.append(self.upscaling_models_frame)
        self._populate_upscaling_model_rows()

        # -- Grupo: Modelos Personalizados (Gestión) --
        # No ponemos cabecera nueva para que se sienta parte de la misma sección
        self.custom_models_mgr_frame = ctk.CTkFrame(frame_models, fg_color=self.CONFIG_CARD_BG, corner_radius=self.CONFIG_CARD_RADIUS, border_width=1, border_color=self.CONFIG_CARD_BORDER)
        self.custom_models_mgr_frame.pack(fill="x", pady=(0, 20), padx=5)
        self.config_cards.append(self.custom_models_mgr_frame)
        
        # Barra de acciones
        custom_actions_bar = ctk.CTkFrame(self.custom_models_mgr_frame, fg_color="transparent")
        custom_actions_bar.pack(fill="x", padx=10, pady=10)
        
        # Botón Añadir a la izquierda de Borrar
        self.btn_add_custom = ctk.CTkButton(
            custom_actions_bar, 
            text="Añadir Modelo", 
            fg_color=self.DOWNLOAD_BTN, 
            hover_color=self.DOWNLOAD_HOVER,
            text_color=self.DOWNLOAD_TEXT,
            height=28,
            command=self._on_add_custom_model_config
        )
        self.btn_add_custom.pack(side="left", padx=(0, 10))
        
        self.btn_delete_custom = ctk.CTkButton(
            custom_actions_bar, 
            text="Borrar Seleccionados", 
            fg_color=self.SECONDARY_BTN, 
            hover_color=self.SECONDARY_HOVER,
            text_color=self.SECONDARY_TEXT,
            height=28,
            state="disabled",
            command=self._delete_selected_custom_models
        )
        self.btn_delete_custom.pack(side="left")
        
        # Lista de modelos
        list_container = ctk.CTkFrame(self.custom_models_mgr_frame, fg_color="transparent")
        list_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        from tkinter import Listbox, EXTENDED
        _lb_bg = self.app.get_theme_color("LISTBOX_BG", ["#F9F9FA", "#18181A"])
        _lb_text = self.app.get_theme_color("LISTBOX_TEXT", ["gray10", "#DCE4EE"])
        
        self.custom_models_listbox = Listbox(
            list_container,
            bg=self._resolve_color(_lb_bg),
            fg=self._resolve_color(_lb_text),
            font=("Segoe UI", 10),
            selectmode=EXTENDED,
            borderwidth=1,
            highlightthickness=0,
            height=8  # Más altura para evitar que parezca solo un elemento
        )
        self.custom_models_listbox.pack(side="left", fill="both", expand=True)
        self.custom_models_listbox.bind("<<ListboxSelect>>", self._on_custom_model_select)
        
        scrollbar = ctk.CTkScrollbar(list_container, command=self.custom_models_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.custom_models_listbox.config(yscrollcommand=scrollbar.set)
        
        # Cargar lista inicial
        self.app.after(500, self._refresh_custom_models_list)

        self.sections["models"] = frame_models
        # Mitigar glitch visual al hacer scroll: refrescar la ventana durante el scroll
        frame_models._scrollbar.bind("<B1-Motion>", lambda e: self.app.update_idletasks())
        frame_models.bind("<MouseWheel>", lambda e: self.app.after(10, self.app.update_idletasks))

    def _setup_console_section(self):
        """Crea la sección de Consola de Diagnóstico."""

        frame_console = ctk.CTkFrame(self.content_container, fg_color="transparent")
        frame_console.grid_rowconfigure(1, weight=1)
        frame_console.grid_columnconfigure(0, weight=1)

        # ── Encabezado ──────────────────────────────────────────────────────────
        # Grid de 2 columnas:
        #   Col 0 (expande): título + descripción apilados
        #   Col 1 (fijo):    fila 0 = switch  |  fila 1 = [Copiar][Exportar][Limpiar]
        header = ctk.CTkFrame(frame_console, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)   # lado izquierdo se expande
        header.grid_columnconfigure(1, weight=0)   # lado derecho fijo

        # ── Columna izquierda: título + controles ──
        left_frame = ctk.CTkFrame(header, fg_color="transparent")
        left_frame.grid(row=0, column=0, rowspan=2, sticky="w")

        ctk.CTkLabel(
            left_frame,
            text="Consola de Diagnóstico",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")

        # ── Fila de Controles (Debajo del título) ──
        controls_row = ctk.CTkFrame(left_frame, fg_color="transparent")
        controls_row.pack(anchor="w", pady=(5, 0))

        # Switch 1: Activar Consola
        self._console_switch_var = ctk.BooleanVar(value=getattr(self.app, 'console_enabled', False))
        self._console_switch = ctk.CTkSwitch(
            controls_row,
            text="Activar Consola",
            font=ctk.CTkFont(size=12),
            variable=self._console_switch_var,
            onvalue=True,
            offvalue=False,
            command=self._on_console_switch_toggle
        )
        self._console_switch.pack(side="left", padx=(0, 20))

        # Switch 2: Ajuste de línea (Word Wrap)
        self._console_wrap_switch = ctk.CTkSwitch(
            controls_row,
            text="Ajuste de línea",
            font=ctk.CTkFont(size=12),
            variable=self._console_wrap_var,
            onvalue=True,
            offvalue=False,
            command=self._on_console_wrap_toggle
        )
        self._console_wrap_switch.pack(side="left")

        # ── Columna derecha, fila 1: botones de log ──
        log_btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        log_btn_frame.grid(row=1, column=1, sticky="e", padx=(10, 0))

        self._btn_copy = ctk.CTkButton(
            log_btn_frame,
            text="Copiar",
            width=90, height=28,
            fg_color=("#1565C0", "#1565C0"),
            hover_color=("#0D47A1", "#0D47A1"),
            text_color="white",
            command=self._console_copy
        )
        self._btn_copy.pack(side="left", padx=3)

        self._btn_export = ctk.CTkButton(
            log_btn_frame,
            text="Exportar",
            width=90, height=28,
            fg_color=self.SECONDARY_BTN,
            hover_color=self.SECONDARY_HOVER,
            text_color=self.SECONDARY_TEXT,
            command=self._console_export
        )
        self._btn_export.pack(side="left", padx=3)

        self._btn_clear = ctk.CTkButton(
            log_btn_frame,
            text="Limpiar",
            width=90, height=28,
            fg_color=self.CANCEL_BTN,
            hover_color=self.CANCEL_HOVER,
            text_color=self.CANCEL_TEXT,
            command=self._console_clear
        )
        self._btn_clear.pack(side="left", padx=(3, 0))


        # ── Textbox (siempre visible, row=1) ────────────────────────────────────
        self._console_textbox = ctk.CTkTextbox(
            frame_console,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.CONSOLE_BG,
            text_color=self.CONSOLE_TEXT,
            wrap="word" if self._console_wrap_var.get() else "none",
            state="disabled",
        )
        self._console_textbox.grid(row=1, column=0, sticky="nsew")
        
        # Configurar colores para tags de la consola
        self._console_textbox.tag_config("user_command", foreground="#52A2F2") # Celeste brillante
        self._console_textbox.tag_config("error", foreground="#e74c3c") # Rojo
        self._console_textbox.tag_config("warning", foreground="#f39c12") # Naranja

        if not self._console_switch_var.get():
            self._console_set_placeholder(True)

        self._console_auto_scroll = True
        self._console_textbox.bind("<MouseWheel>", self._on_console_scroll)
        self._console_textbox.bind("<Button-4>", self._on_console_scroll)
        self._console_textbox.bind("<Button-5>", self._on_console_scroll)

        # ── Barra inferior: [entrada ──────────────────────────] [Ejecutar] [Cancelar] ──
        bottom_bar = ctk.CTkFrame(frame_console, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        bottom_bar.grid_columnconfigure(0, weight=1)  # entrada ocupa todo el ancho libre

        self._cmd_process = None

        self._console_cmd_entry = ctk.CTkEntry(
            bottom_bar,
            placeholder_text="ffmpeg -version  ·  yt-dlp --help  ·  yt-dlp -f best URL",
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
        )
        self._console_cmd_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        
        # Historial de comandos
        self._console_history = []
        self._console_history_index = -1
        
        self._console_cmd_entry.bind("<Return>", lambda e: self._execute_console_command())
        self._console_cmd_entry.bind("<Up>", self._on_console_history_nav)
        self._console_cmd_entry.bind("<Down>", self._on_console_history_nav)

        cmd_btn_frame = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        cmd_btn_frame.grid(row=0, column=1)

        self._btn_execute = ctk.CTkButton(
            cmd_btn_frame,
            text="Ejecutar",
            width=90, height=28,
            fg_color=self.DOWNLOAD_BTN,
            hover_color=self.DOWNLOAD_HOVER,
            text_color=self.DOWNLOAD_TEXT,
            state="disabled",
            command=self._execute_console_command
        )
        self._btn_execute.pack(side="left", padx=(0, 3))

        self._btn_cancel_cmd = ctk.CTkButton(
            cmd_btn_frame,
            text="Cancelar",
            width=90, height=28,
            fg_color="transparent",
            border_width=1,
            border_color=self.CANCEL_BTN,
            text_color=self.CANCEL_TEXT,
            hover_color=self.CANCEL_HOVER,
            state="disabled",
            command=self._cancel_console_command
        )
        self._btn_cancel_cmd.pack(side="left")

        self.sections["console"] = frame_console

        # Setup del ConsoleHandler
        from main import BIN_DIR, FFMPEG_BIN_DIR
        from src.core.console_handler import ConsoleHandler
        self._console_handler = ConsoleHandler(BIN_DIR, FFMPEG_BIN_DIR)
        self._console_handler.connect_callbacks(self.append_to_console, self._on_cmd_finished)

        # Si la consola viene activa desde los ajustes guardados,
        # habilitar el campo de entrada y el botón Ejecutar inmediatamente
        if self._console_switch_var.get():
            self._console_cmd_entry.configure(state="normal")
            self._btn_execute.configure(state="normal")



    # ================= LÓGICA DE CONSOLA =================

    def _on_console_switch_toggle(self):
        """Activa o desactiva la captura de logs al cambiar el switch."""
        enabled = self._console_switch_var.get()
        self.app.console_enabled = enabled
        self.app.save_settings()

        if enabled:
            self._console_set_placeholder(False)
            self._console_cmd_entry.configure(state="normal")
            self._btn_execute.configure(state="normal")
            if hasattr(self.app, 'console_logger'):
                self.app.console_logger.enable()
        else:
            if hasattr(self.app, 'console_logger'):
                self.app.console_logger.disable()
            self._console_cmd_entry.configure(state="disabled")
            self._btn_execute.configure(state="disabled")
            # Solo mostrar placeholder si la caja está vacía
            content = self._console_textbox.get("1.0", "end-1c")
            if not content.strip():
                self._console_set_placeholder(True)

    def _on_console_wrap_toggle(self):
        """Alterna entre ajuste de línea (word wrap) y scroll horizontal (none)."""
        wrapped = self._console_wrap_var.get()
        self.app.console_wrap = wrapped
        self.app.save_settings()
        
        if wrapped:
            self._console_textbox.configure(wrap="word")
        else:
            self._console_textbox.configure(wrap="none")

    def _console_set_placeholder(self, show: bool):
        """Muestra u oculta el texto de placeholder en la consola."""
        self._console_textbox.configure(state="normal")
        self._console_textbox.delete("1.0", "end")
        if show:
            self._console_textbox.insert("end",
                "\n\n          Consola inactiva — activa el interruptor para comenzar a capturar registros."
            )
            self._console_textbox.configure(text_color="gray50")
            self._console_at_start = True
        else:
            # Recuperar el color del tema activo
            self._console_textbox.configure(text_color=self.CONSOLE_TEXT)
            self._console_at_start = True
        self._console_textbox.configure(state="disabled")

    def append_to_console(self, text: str, tag: str = "normal"):
        """
        Callback llamado por ConsoleLogger o ConsoleHandler.
        Añade texto al textbox con timestamp si falta y maneja el límite de líneas.
        """
        if not self.winfo_exists() or not text:
            return
            
        try:
            self._console_textbox.configure(state="normal")
            
            import re
            import time
            from datetime import datetime
            
            # Procesar el texto para insertar timestamps en cada inicio de línea si faltan
            # y manejar retornos de carro (\r) para progreso
            
            # Si el bloque de texto contiene \r, es probable que sea spam de progreso.
            # Lo procesamos para que solo quede la última versión de la línea.
            if "\r" in text:
                parts = text.split("\r")
                text = parts[-1] if parts[-1] else parts[-2] if len(parts) > 1 else text
                self._console_last_was_r = True
            else:
                self._console_last_was_r = False

            lines = text.splitlines(keepends=True)
            for line in lines:
                # Si el bloque anterior terminó en \r, borramos la línea actual antes de escribir
                if getattr(self, "_console_at_r_pos", False):
                    self._console_textbox.delete("insert linestart", "insert lineend")
                    self._console_at_r_pos = False

                # Si estamos al inicio de una línea física en el widget
                if self._console_at_start and line.strip():
                    # Comprobar si ya tiene un timestamp [HH:MM:SS]
                    if not bool(re.match(r'^\s*\[\d{2}:\d{2}:\d{2}\]', line)):
                        timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] "
                        self._console_textbox.insert("end", timestamp, tag)
                
                self._console_textbox.insert("end", line, tag)
                self._console_at_start = line.endswith('\n')
                
            if self._console_last_was_r:
                self._console_at_r_pos = True

            # Optimización: Solo verificar el límite de líneas cada cierto tiempo
            current_time = time.time()
            if not hasattr(self, "_last_console_cleanup"):
                self._last_console_cleanup = 0
                
            if current_time - self._last_console_cleanup > 3.0: # Cada 3 segundos
                self._last_console_cleanup = current_time
                MAX_LINES = 2500
                line_count = int(self._console_textbox.index("end-1c").split(".")[0])
                if line_count > MAX_LINES:
                    excess = line_count - MAX_LINES
                    self._console_textbox.delete("1.0", f"{excess + 1}.0")

            self._console_textbox.configure(state="disabled")

            # Auto-scroll
            if self._console_auto_scroll:
                self._console_textbox.see("end")
        except Exception:
            pass

    def _on_console_scroll(self, event):
        """Pausa el auto-scroll cuando el usuario hace scroll hacia arriba."""
        # Reactivar auto-scroll si el usuario llega al final
        self.app.after(50, self._check_console_at_bottom)

    def _check_console_at_bottom(self):
        """Reactiva auto-scroll si el textbox está cerca del final."""
        try:
            yview = self._console_textbox.yview()
            # yview()[1] == 1.0 significa que el final del texto es visible.
            # Bajamos el umbral a 0.95 para que sea más permisivo con el scroll rápido.
            self._console_auto_scroll = (yview[1] >= 0.95)
        except Exception:
            pass

    def _console_copy(self):
        """Copia todo el contenido de la consola al portapapeles y da feedback visual."""
        try:
            text = self._console_textbox.get("1.0", "end-1c")
            self.app.clipboard_clear()
            self.app.clipboard_append(text)
            # Feedback visual: verde + texto por 1.5 s
            self._btn_copy.configure(
                text="¡Copiado!",
                fg_color=self.STATUS_SUCCESS,
                hover_color=self.STATUS_SUCCESS,
                text_color="white"
            )
            self.app.after(1500, self._reset_copy_button)
        except Exception as e:
            print(f"ADVERTENCIA [Consola]: No se pudo copiar: {e}")

    def _reset_copy_button(self):
        """Restaura el botón Copiar a su estado original (azul)."""
        try:
            self._btn_copy.configure(
                text="Copiar",
                fg_color=self.SECONDARY_BTN,
                hover_color=self.SECONDARY_HOVER,
                text_color=self.SECONDARY_TEXT
            )
        except Exception:
            pass

    # ================= RUNNER DE COMANDOS =================

    def _execute_console_command(self):
        """
        Parsea el comando escrito por el usuario y lo delega al ConsoleHandler.
        """
        raw = self._console_cmd_entry.get().strip()
        if not raw:
            return

        # Guardar en historial si es distinto al último
        if not self._console_history or self._console_history[-1] != raw:
            self._console_history.append(raw)
        self._console_history_index = -1

        # Limpiar primero, luego deshabilitar entrada mientras corre
        self._console_cmd_entry.delete(0, "end")
        self._console_cmd_entry.configure(state="disabled")
        self._btn_execute.configure(state="disabled")
        self._btn_cancel_cmd.configure(state="normal")

        # El _console_handler se encargará de ejecutar el comando y llamar a los callbacks
        self._console_handler.execute_command(raw)

    def _cancel_console_command(self):
        """Termina el subproceso en ejecución a través del handler."""
        if hasattr(self, '_console_handler'):
            self._console_handler.cancel_process()

    def _on_cmd_finished(self):
        """Restaura el estado de los botones al terminar un comando."""
        try:
            self._btn_cancel_cmd.configure(state="disabled")
            if self._console_switch_var.get():
                self._console_cmd_entry.configure(state="normal")
                self._btn_execute.configure(state="normal")
                # Devolver el foco a la entrada al terminar para poder seguir escribiendo
                self._console_cmd_entry.focus_set()
        except Exception:
            pass

    def _on_console_history_nav(self, event):
        """Maneja la navegación por el historial de comandos (Flechas arriba/abajo)."""
        if not self._console_history:
            return
        
        if event.keysym == "Up":
            if self._console_history_index == -1:
                # Si estamos al final, el primer Arriba nos lleva al último comando
                self._console_history_index = len(self._console_history) - 1
            elif self._console_history_index > 0:
                self._console_history_index -= 1
        elif event.keysym == "Down":
            if self._console_history_index != -1:
                if self._console_history_index < len(self._console_history) - 1:
                    self._console_history_index += 1
                else:
                    # Si bajamos del último, limpiamos el campo
                    self._console_history_index = -1

        # Actualizar el Entry
        self._console_cmd_entry.delete(0, "end")
        if self._console_history_index != -1:
            self._console_cmd_entry.insert(0, self._console_history[self._console_history_index])
        
        # Mover el cursor al final
        self._console_cmd_entry.icursor("end")
        return "break" # Evita que el cursor se mueva al inicio/fin (comportamiento por defecto)

    def _console_export(self):
        """Exporta el contenido de la consola a un archivo .txt."""
        from tkinter import filedialog as tkfd
        import datetime
        text = self._console_textbox.get("1.0", "end-1c")
        if not text.strip():
            return
        default_name = f"dowp_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path = tkfd.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Archivo de texto", "*.txt")],
            initialfile=default_name,
            title="Exportar log de consola"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(text)
            except Exception as e:
                print(f"ERROR [Consola]: No se pudo exportar: {e}")

    def _console_clear(self):
        """Limpia el contenido del textbox de la consola."""
        try:
            self._console_textbox.configure(state="normal")
            self._console_textbox.delete("1.0", "end")
            self._console_textbox.configure(state="disabled")
            self._console_auto_scroll = True
        except Exception:
            pass

    # ================= LÓGICA DE VRAM =================

    def _on_vector_dpi_change(self, value):
        """Actualiza el DPI vectorial desde el slider y sincroniza la entrada."""
        val = int(value)
        self.app.vector_dpi = val
        
        # Sincronizar entry (borrar y escribir para evitar bucles de eventos si fuera StringVar)
        self.dpi_entry.delete(0, "end")
        self.dpi_entry.insert(0, str(val))
        
        self._update_dpi_warning(val)
        self.app.save_settings()

    def _on_dpi_entry_change(self, event):
        """Valida y sincroniza el DPI cuando el usuario escribe manualmente."""
        text = self.dpi_entry.get()
        if not text: return
        
        try:
            val = int(text)
            # Límite máximo avanzado: 2400
            if val > 2400:
                val = 2400
                self.dpi_entry.delete(0, "end")
                self.dpi_entry.insert(0, "2400")
            elif val < 70:
                # No forzamos el mínimo mientras escribe para no molestar, 
                # pero el slider se quedará en el mínimo.
                pass
                
            self.app.vector_dpi = val
            self.vector_dpi_var.set(min(val, 1200)) # El slider solo llega a 1200 visualmente
            
            self._update_dpi_warning(val)
            self.app.save_settings()
        except ValueError:
            pass # Ignorar si no es número mientras escribe

    def _on_theme_change(self, display_name):
        """Maneja el cambio de tema de color con actualización dinámica."""
        internal_name = self.theme_internal_names.get(display_name)
        if not internal_name or internal_name == getattr(self.app, 'selected_theme_accent', 'blue'):
            return
            
        self.app.selected_theme_accent = internal_name
        self.app.save_settings()
        
        # 🎨 ACTUALIZACIÓN DINÁMICA (NUEVO)
        # Esto actualizará los colores personalizados al instante
        self.app.refresh_theme()
        
        # Diálogo de reinicio (Opcional, para un cambio 100% completo)
        from tkinter import messagebox
        import sys
        if messagebox.askyesno("Tema Actualizado", 
                               "Se han actualizado los colores personalizados de forma dinámica.\n\n"
                               "¿Deseas reiniciar DowP ahora para aplicar el cambio de acento de forma completa en toda la interfaz (marcos, barras, etc)?"):
            # Cerrar limpiamente
            self.app.on_closing()
            
            # Lanzar nueva instancia
            import subprocess
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable] + sys.argv)
            
            # Salir de la actual
            sys.exit(0)

    def _on_appearance_mode_change(self, mode_display):
        """Maneja el cambio entre Claro, Oscuro y Sistema."""
        mode_map = {"Sistema": "System", "Claro": "Light", "Oscuro": "Dark"}
        internal_mode = mode_map.get(mode_display, "System")
        
        ctk.set_appearance_mode(internal_mode)
        self.app.appearance_mode = internal_mode
        self.app.save_settings()
        
        print(f"DEBUG: Modo de apariencia cambiado a: {internal_mode}")
        
        # Propagar el cambio de modo a los widgets nativos (tkinter Listbox, Canvas)
        # CTk actualiza sus propios widgets automáticamente, pero los nativos necesitan
        # un refresh manual para leer el nuevo color según el modo Light/Dark.
        self.app.after(100, self.app.refresh_theme)

    def _refresh_theme_list(self):
        """Escanea las carpetas de temas y actualiza el menú desplegable."""
        # Temas base de CTK
        self.theme_display_names = {
            "blue": "Azul (Estándar)",
            "dark-blue": "Azul Profundo",
            "green": "Verde (Estándar)"
        }
        
        # 1. Escaneo de Temas Internos
        base_path = getattr(sys, '_MEIPASS', self.app.APP_BASE_PATH)
        internal_dir = os.path.join(base_path, "src", "gui", "themes")
        
        # 2. Escaneo de Temas de Usuario
        user_dir = getattr(self.app, 'USER_THEMES_DIR', None)
        
        for directory in [internal_dir, user_dir]:
            if directory and os.path.exists(directory):
                import json
                for file in os.listdir(directory):
                    if file.endswith(".json"):
                        name = file[:-5] # Quitar .json
                        
                        # 🚫 EXCLUIR: Plantilla y archivos temporales/ocultos
                        if name == "plantilla_tema" or name.startswith("."):
                            continue
                            
                        # Intentar leer el nombre interno del JSON
                        full_path = os.path.join(directory, file)
                        display = None
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                # Buscar ThemeName en raíz o en instrucciones
                                display = data.get("ThemeName") or data.get("_INSTRUCCIONES_DOWP", {}).get("ThemeName")
                        except:
                            pass
                            
                        if not display:
                            # Fallback: Formatear nombre para mostrar (ej: verde_bosque -> Verde Bosque)
                            display = name.replace("_", " ").replace("-", " ").title()
                        
                        self.theme_display_names[name] = display
        
        self.theme_internal_names = {v: k for k, v in self.theme_display_names.items()}
        
        # Actualizar Menu
        sorted_display = sorted(self.theme_display_names.values())
        self.theme_menu.configure(values=sorted_display)
        
        current_internal = getattr(self.app, 'selected_theme_accent', 'blue')
        current_display = self.theme_display_names.get(current_internal, "Azul (Estándar)")
        self.theme_menu.set(current_display)

    def _import_theme(self):
        """Abre un diálogo para copiar un archivo JSON a la carpeta de temas."""
        from customtkinter import filedialog
        from tkinter import messagebox
        import shutil
        
        file_path = filedialog.askopenfilename(
            title="Seleccionar Tema de CustomTkinter",
            filetypes=[("Archivos JSON", "*.json")]
        )
        
        if not file_path:
            return
            
        try:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(self.app.USER_THEMES_DIR, filename)
            
            if os.path.exists(dest_path):
                if not messagebox.askyesno("Sobrescribir", f"El tema '{filename}' ya existe. ¿Quieres sobrescribirlo?"):
                    return
            
            shutil.copy(file_path, dest_path)
            messagebox.showinfo("Éxito", f"Tema '{filename}' importado correctamente.")
            self._refresh_theme_list()
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo importar el tema: {e}")

    def _install_theme_from_url(self):
        """Descarga un tema desde una URL y lo guarda en la carpeta de temas."""
        from tkinter import messagebox
        import requests
        import json
        
        # Ocultar tooltips antes de abrir el diálogo de entrada
        Tooltip.hide_all()
        
        dialog = URLInputDialog(master=self.app, text="Pega el link directo (JSON Raw) del tema:", title="Instalar Tema por URL")
        url = dialog.get_input()
        
        if not url:
            return
            
        try:
            # 1. Descargar
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            # 2. Validar que sea JSON
            try:
                theme_data = response.json()
            except:
                messagebox.showerror("Error de Formato", "El link no contiene un JSON válido.")
                return
            
            # 3. Determinar nombre del archivo
            # Prioridad: ThemeName interno > Nombre en URL > "tema_descargado"
            internal_name = theme_data.get("ThemeName") or theme_data.get("_INSTRUCCIONES_DOWP", {}).get("ThemeName")
            if internal_name:
                filename = internal_name.lower().replace(" ", "_") + ".json"
            else:
                filename = url.split("/")[-1]
                if "?" in filename: filename = filename.split("?")[0] # Limpiar query params
                if not filename.endswith(".json"):
                    filename = "tema_descargado.json"
            
            dest_path = os.path.join(self.app.USER_THEMES_DIR, filename)
            
            # 4. Preguntar si ya existe
            if os.path.exists(dest_path):
                if not messagebox.askyesno("Sobrescribir", f"El tema '{filename}' ya existe. ¿Quieres sobrescribirlo?"):
                    return
            
            # 5. Guardar
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=2, ensure_ascii=False)
            
            # 6. Refrescar
            self._refresh_theme_list()
            messagebox.showinfo("Instalación Exitosa", f"El tema '{filename}' se ha instalado correctamente.")
            
        except Exception as e:
            messagebox.showerror("Error de Descarga", f"No se pudo descargar el tema:\n\n{e}")

    def _delete_theme(self):
        """Elimina el tema seleccionado actualmente (si es un tema de usuario)."""
        from tkinter import messagebox
        import os
        
        display_name = self.theme_menu.get()
        internal_name = self.theme_internal_names.get(display_name)
        
        if not internal_name:
            return
            
        # No permitir borrar temas internos básicos (Sistema y Curados)
        system_themes = [
            "blue", "dark-blue", "green", "green_shrek", "dorado", "tokyo", 
            "coffee_noir", "cyberpunk_neon", "forest_moss", "midnight_ocean", "sunset_lavender", "shrek"
        ]
        if internal_name in system_themes:
            messagebox.showwarning("Acción no permitida", "No puedes eliminar los temas preinstalados del sistema.")
            return
            
        theme_path = os.path.join(self.app.USER_THEMES_DIR, f"{internal_name}.json")
        
        if not os.path.exists(theme_path):
            messagebox.showerror("Error", f"No se encontró el archivo del tema: {internal_name}.json")
            return
            
        if messagebox.askyesno("Confirmar eliminación", f"¿Estás seguro de que quieres eliminar el tema '{display_name}'?\n\nEsta acción no se puede deshacer."):
            try:
                os.remove(theme_path)
                messagebox.showinfo("Tema eliminado", "El tema ha sido eliminado correctamente.\n\nEs necesario reiniciar la aplicación para aplicar los cambios.")
                
                # Volver al tema por defecto para evitar errores
                self.app.selected_theme_accent = "blue"
                self.app.save_config()
                
                # Opcional: preguntar si quiere reiniciar ahora
                if messagebox.askyesno("Reiniciar ahora", "¿Quieres reiniciar DowP ahora para aplicar los cambios?"):
                    self.app._on_restart_app()
                else:
                    self._refresh_theme_list()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar el tema: {e}")

    def _open_themes_folder(self):
        """Abre la carpeta de temas del usuario en el explorador de archivos."""
        import subprocess
        import os
        
        path = self.app.USER_THEMES_DIR
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta: {e}")

    def _update_dpi_warning(self, val):
        """Muestra u oculta la advertencia según el valor de DPI."""
        if val > 1200:
            if not self.dpi_warning_label.winfo_ismapped():
                self.dpi_warning_label.pack(anchor="w", padx=15, pady=(0, 10))
        else:
            if self.dpi_warning_label.winfo_ismapped():
                self.dpi_warning_label.pack_forget()

    def _on_preview_dpi_change(self, value):
        """Actualiza el DPI de previsualización y guarda la configuración."""
        val = int(value)
        self.preview_dpi_label.configure(text=f"{val} DPI")
        self.app.preview_vector_dpi = val
        self.app.save_settings()

    def _on_vram_persistence_toggle(self):
        """Guarda la preferencia de persistencia de modelos IA."""
        self.app.keep_ai_models_in_memory = self.keep_vram_var.get()
        self.app.save_settings()

    def _manual_vram_clear(self):
        """Llama a la limpieza de sesiones de IA de forma manual."""
        if hasattr(self.app, 'image_tab') and hasattr(self.app.image_tab, 'image_converter'):
            self.app.image_tab.image_converter.clear_ai_sessions()
            
            # Feedback visual en el botón
            original_text = self.clear_vram_btn.cget("text")
            self.clear_vram_btn.configure(text="¡VRAM Liberada!", fg_color="#28a745")
            self.app.after(2000, lambda: self.clear_vram_btn.configure(text=original_text, fg_color=("#DC3545", "#c0392b")))

    # ================= LOGICA DE MODELOS =================

    def _get_model_path(self, model_info):
        """Devuelve la ruta absoluta esperada del archivo de un modelo."""
        from main import MODELS_DIR
        return os.path.join(MODELS_DIR, model_info["folder"], model_info["file"])

    def _get_upscaling_tool_path(self, tool_info):
        """Devuelve la ruta absoluta del ejecutable de un motor de upscaling."""
        from main import UPSCALING_DIR
        return os.path.join(UPSCALING_DIR, tool_info["folder"], tool_info["exe"])

    def _format_size(self, size_bytes):
        """Convierte bytes a una cadena legible (KB, MB, GB)."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / 1024**2:.1f} MB"
        else:
            return f"{size_bytes / 1024**3:.2f} GB"

    def _populate_rembg_model_rows(self):
        """Crea las filas de modelos Rembg a partir de constants.py."""
        from src.core.constants import REMBG_MODEL_FAMILIES
        RMBG2_FAMILY = "RMBG 2.0 (BriaAI)"
        # Solo este modelo de RMBG 2.0 permite descarga directa desde DowP
        RMBG2_AUTO_KEY = "Standard (Automático - 977 MB)"

        for family_name, models in REMBG_MODEL_FAMILIES.items():
            # Encabezado de familia con el botón acoplado
            header_frame = ctk.CTkFrame(self.rembg_models_frame, fg_color="transparent")
            header_frame.pack(fill="x", padx=15, pady=(12, 2))
            
            header = ctk.CTkLabel(
                header_frame,
                text=family_name,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.SECTION_SUBTITLE
            )
            header.pack(side="left")
            self.config_subtitles.append(header)
            
            # Botón unificado de Carpeta
            folder_icon = ctk.CTkButton(
                header_frame, 
                text="Abrir Carpeta", 
                width=100,
                height=24,
                fg_color=self.TERTIARY_BTN, 
                hover_color=self.TERTIARY_HOVER,
                text_color=self.TERTIARY_TEXT,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda f=family_name: self._open_family_folder(f)
            )
            folder_icon.pack(side="right")
            self.model_family_icons.append(folder_icon)

            # Aviso especial para la familia RMBG 2.0
            if family_name == RMBG2_FAMILY:
                notice = (
                    "Únicamente el modelo 'Automático' puede descargarse directamente desde DowP. "
                    "Para descargar los demás formatos especializados es requisito obligatorio tener una cuenta conectada en Hugging Face. "
                    "Una vez descargados manualmente desde su web, colócalos en la carpeta que se muestra al pulsar 'Abrir Carpeta'."
                )
                notice_frame = ctk.CTkFrame(self.rembg_models_frame, fg_color=("#FCF2CE", "#3D3725"), corner_radius=6)
                notice_frame.pack(fill="x", padx=15, pady=(0, 6))
                
                text_lbl = ctk.CTkLabel(
                    notice_frame,
                    text=notice,
                    font=ctk.CTkFont(size=11),
                    text_color=("gray10", "white"),
                    justify="left",
                    wraplength=520
                )
                text_lbl.pack(anchor="w", padx=15, pady=(10, 3))
                
                self.huggingface_btn = ctk.CTkButton(
                    notice_frame, 
                    text="Explorar Repositorio Web (HuggingFace)", 
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color=self.TERTIARY_BTN,
                    hover_color=self.TERTIARY_HOVER,
                    text_color=self.TERTIARY_TEXT,
                    width=250,
                    command=lambda: __import__('webbrowser').open("https://huggingface.co/briaai/RMBG-2.0/tree/main/onnx")
                )
                self.huggingface_btn.pack(anchor="w", padx=15, pady=(0, 12))

            for model_name, model_info in models.items():
                if family_name == RMBG2_FAMILY and model_name != RMBG2_AUTO_KEY:
                    continue  # Saltar modelos inútiles en interfaz
                    
                row_key = f"rembg_{model_info['file']}"
                is_hf_manual = (family_name == RMBG2_FAMILY and model_name != RMBG2_AUTO_KEY)
                
                self._create_model_row(
                    parent=self.rembg_models_frame,
                    row_key=row_key,
                    display_name=model_name,
                    description=f"Archivo: {model_info['file']}",
                    model_info=model_info,
                    kind="rembg",
                    manual_web=is_hf_manual,
                    show_folder_btn=False
                )

    def _populate_upscaling_model_rows(self):
        """Crea las filas de motores de upscaling a partir de constants.py."""
        from src.core.constants import UPSCALING_TOOLS
        for tool_name, tool_info in UPSCALING_TOOLS.items():
            row_key = f"upscale_{tool_info['folder']}"
            self._create_model_row(
                parent=self.upscaling_models_frame,
                row_key=row_key,
                display_name=tool_name,
                description=f"Ejecutable: {tool_info['exe']}",
                model_info=tool_info,
                kind="upscaling",
                show_folder_btn=True
            )

    def _create_model_row(self, parent, row_key, display_name, description, model_info, kind, manual_web=False, show_folder_btn=True):
        """Crea una fila visual para un modelo o motor de IA."""
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=15, pady=6)
        row_frame.grid_columnconfigure(0, weight=3)  # Nombre
        row_frame.grid_columnconfigure(1, weight=1)  # Tamaño/Estado
        row_frame.grid_columnconfigure(2, weight=0)  # Botones

        # -- Columna Izquierda: Nombre y descripción --
        info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(info_frame, text=display_name, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(info_frame, text=description, font=ctk.CTkFont(size=11), text_color="gray50").pack(anchor="w")

        # -- Columna Centro: Estado + progreso --
        status_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        status_frame.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        status_lbl = ctk.CTkLabel(status_frame, text="Calculando...", font=ctk.CTkFont(size=11), text_color="gray50")
        status_lbl.pack(anchor="center")

        pct_lbl = ctk.CTkLabel(status_frame, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.SECTION_SUBTITLE)
        pct_lbl.pack(anchor="center")
        self.config_subtitles.append(pct_lbl)

        # -- Columna Derecha: Botones --
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=2, sticky="e", padx=(10, 0))

        dl_label = "Abrir Web" if manual_web else "Descargar"
        dl_btn = ctk.CTkButton(
            btn_frame, 
            text=dl_label, 
            width=100,
            fg_color=self.DOWNLOAD_BTN,
            hover_color=self.DOWNLOAD_HOVER,
            text_color=self.DOWNLOAD_TEXT
        )
        dl_btn.pack(side="left", padx=2)

        folder_btn = None
        if show_folder_btn:
            folder_btn = ctk.CTkButton(
                btn_frame, 
                text="Carpeta", 
                width=80, 
                fg_color=self.SECONDARY_BTN,
                hover_color=self.SECONDARY_HOVER,
                text_color=self.SECONDARY_TEXT,
                font=ctk.CTkFont(size=11, weight="bold")
            )
            folder_btn.pack(side="left", padx=2)

        del_btn = ctk.CTkButton(
            btn_frame, 
            text="Eliminar", 
            width=80, 
            fg_color=self.CANCEL_BTN,
            hover_color=self.CANCEL_HOVER,
            text_color=self.CANCEL_TEXT
        )
        del_btn.pack(side="left", padx=2)

        # Guardar referencias
        self.model_rows[row_key] = {
            "status_lbl": status_lbl,
            "pct_lbl": pct_lbl,
            "dl_btn": dl_btn,
            "del_btn": del_btn,
            "folder_btn": folder_btn,
            "model_info": model_info,
            "kind": kind,
            "manual_web": manual_web
        }

        # Conectar acciones
        dl_btn.configure(command=lambda k=row_key: self._download_model(k))
        del_btn.configure(command=lambda k=row_key: self._delete_model(k))
        if show_folder_btn:
            folder_btn.configure(command=lambda k=row_key: self._open_model_folder(k))

        # Actualizar estado inicial
        self.app.after(50, lambda k=row_key: self._refresh_model_row(k))

    def _refresh_model_row(self, row_key):
        """Actualiza el estado visual (descargado / no descargado) de una fila."""
        if row_key not in self.model_rows:
            return
        row = self.model_rows[row_key]
        model_info = row["model_info"]
        kind = row["kind"]

        if kind == "upscaling":
            path = self._get_upscaling_tool_path(model_info)
        else:
            path = self._get_model_path(model_info)

        if os.path.exists(path):
            if kind == "upscaling":
                engine_dir = os.path.dirname(path)
                size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fn in os.walk(engine_dir) for f in fn)
            else:
                size = os.path.getsize(path)
            row["status_lbl"].configure(text=self._format_size(size), text_color=("#2e7d32", "#66bb6a"))
            row["pct_lbl"].configure(text="")
            # El botón "Instalado" ahora es gris (secundario) para no distraer
            row["dl_btn"].configure(
                state="disabled", 
                text="Instalado", 
                fg_color=self.SECONDARY_BTN, 
                text_color=self.SECONDARY_TEXT
            )
            # El botón "Eliminar" es rojo solo si está activo
            row["del_btn"].configure(
                state="normal", 
                fg_color=self.CANCEL_BTN, 
                hover_color=self.CANCEL_HOVER, 
                text_color=self.CANCEL_TEXT, 
                border_width=0
            )
        else:
            row["status_lbl"].configure(text="No descargado", text_color="gray50")
            row["pct_lbl"].configure(text="")
            # El botón "Descargar" es el principal
            row["dl_btn"].configure(
                state="normal", 
                text="Descargar", 
                fg_color=self.DOWNLOAD_BTN, 
                hover_color=self.DOWNLOAD_HOVER, 
                text_color=self.DOWNLOAD_TEXT
            )
            # El botón "Eliminar" es inactivo/transparente si no hay nada que borrar
            row["del_btn"].configure(
                state="disabled", 
                fg_color="transparent", 
                border_width=1, 
                text_color=("gray10", "gray90")
            )
            
        # Actualizar botón de carpeta si existe (Usa estilo TERCIARIO)
        if row.get("folder_btn"):
            row["folder_btn"].configure(
                fg_color=self.TERTIARY_BTN, 
                hover_color=self.TERTIARY_HOVER, 
                text_color=self.TERTIARY_TEXT
            )

    def _download_model(self, row_key):
        """Inicia la descarga de un modelo en un hilo separado."""
        if row_key not in self.model_rows:
            return
        row = self.model_rows[row_key]
        model_info = row["model_info"]
        kind = row["kind"]

        # Determinar ruta de destino
        if kind == "upscaling":
            dest_path = self._get_upscaling_tool_path(model_info)
        else:
            dest_path = self._get_model_path(model_info)

        url = model_info.get("url", "")
        if not url or "huggingface.co" in url:
            # Modelos que requieren descarga manual (Hugging Face exige login)
            import webbrowser
            webbrowser.open(url)
            return

        # Si es un ZIP de upscaling, delegamos en la lógica existente
        if kind == "upscaling":
            self._download_upscaling_tool(row_key, model_info, dest_path, url)
            return

        # Descarga directa del .onnx
        row["dl_btn"].configure(state="disabled", text="Instalado")
        row["status_lbl"].configure(text="0%", text_color="#1f6aa5")
        row["pct_lbl"].configure(text="")

        def do_download():
            import time
            try:
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with requests.get(url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    last_ui_update = 0.0
                    with open(dest_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):  # 64 KB
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.monotonic()
                                if total > 0 and now - last_ui_update >= 0.3:
                                    last_ui_update = now
                                    pct = int(downloaded / total * 100)
                                    self.app.after(0, lambda p=pct: row["status_lbl"].configure(text=f"{p}%"))
                                    size_lbl = f"{self._format_size(downloaded)} / {self._format_size(total)}"
                                    self.app.after(0, lambda t=size_lbl: row["pct_lbl"].configure(text=t))
                self.app.after(0, lambda: self._refresh_model_row(row_key))
            except Exception as e:
                self.app.after(0, lambda: row["status_lbl"].configure(text=f"Error: {str(e)[:60]}", text_color="red"))
                self.app.after(0, lambda: row["dl_btn"].configure(state="normal", text="Reintentar"))

        threading.Thread(target=do_download, daemon=True).start()

    def _download_upscaling_tool(self, row_key, tool_info, dest_exe_path, url):
        """Descarga un motor llamando a check_and_download_upscaling_tools para integrarlo correctamente."""
        row = self.model_rows[row_key]
        row["dl_btn"].configure(state="disabled", text="Instalado")
        row["status_lbl"].configure(text="0%", text_color="#1f6aa5")
        row["pct_lbl"].configure(text="")

        def do_download():
            try:
                from src.core.setup import check_and_download_upscaling_tools

                # Encontrar el nombre interno del motor (engine_key)
                engine_key = None
                from src.core.constants import UPSCALING_TOOLS
                for k, v in UPSCALING_TOOLS.items():
                    if v.get("folder") == tool_info.get("folder"):
                        engine_key = k
                        break
                
                if not engine_key:
                    raise Exception("Motor no reconocido en las variables locales.")

                def progress_cb(text, val):
                    # val can be -1 if size is unknown
                    if val >= 0:
                        self.app.after(0, lambda: row["status_lbl"].configure(text=f"{val}%"))
                    else:
                        self.app.after(0, lambda: row["status_lbl"].configure(text="Descargando..."))
                    self.app.after(0, lambda: row["pct_lbl"].configure(text=text))

                success = check_and_download_upscaling_tools(progress_cb, target_tool=engine_key)

                if success:
                    self.app.after(0, lambda: self._refresh_model_row(row_key))
                else:
                    raise Exception("Fallo en la descarga o extracción.")

            except Exception as e:
                self.app.after(0, lambda: row["status_lbl"].configure(text=f"Error", text_color="red"))
                self.app.after(0, lambda: row["pct_lbl"].configure(text=str(e)[:60]))
                self.app.after(0, lambda: row["dl_btn"].configure(state="normal", text="Reintentar"))

        import threading
        threading.Thread(target=do_download, daemon=True).start()

    def _delete_model(self, row_key):
        """Elimina el archivo del modelo del disco."""
        if row_key not in self.model_rows:
            return
        row = self.model_rows[row_key]
        model_info = row["model_info"]
        kind = row["kind"]

        if kind == "upscaling":
            path = self._get_upscaling_tool_path(model_info)
            # Para upscaling eliminamos la carpeta del motor completo
            import shutil
            tool_dir = os.path.dirname(path)
            if os.path.isdir(tool_dir):
                try:
                    shutil.rmtree(tool_dir)
                except Exception as e:
                    print(f"ERROR eliminando carpeta de motor: {e}")
        else:
            path = self._get_model_path(model_info)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"ERROR eliminando modelo: {e}")

        self._refresh_model_row(row_key)

    def _open_model_folder(self, row_key):
        """Abre la carpeta que contiene el modelo en el explorador de archivos."""
        if row_key not in self.model_rows:
            return
        row = self.model_rows[row_key]
        model_info = row["model_info"]
        kind = row["kind"]

        if kind == "upscaling":
            path = self._get_upscaling_tool_path(model_info)
        else:
            path = self._get_model_path(model_info)

        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        import subprocess
        subprocess.Popen(["explorer", os.path.normpath(folder)])

    def _open_family_folder(self, family_name):
        from main import MODELS_DIR
        import subprocess
        
        # Determinar carpeta según familia
        if "RMBG 2.0" in family_name:
            folder_name = "rmbg2"
        elif "InSPyReNet" in family_name:
            folder_name = "inspyrenet"
        else:
            folder_name = "rembg"
            
        target_dir = os.path.join(MODELS_DIR, folder_name)
        os.makedirs(target_dir, exist_ok=True)
        try:
            if os.name == 'nt': os.startfile(target_dir)
            elif sys.platform == 'darwin': subprocess.Popen(['open', target_dir])
            else: subprocess.Popen(['xdg-open', target_dir])
        except Exception as e:
            print(f"Error abriendo carpeta global {target_dir}: {e}")

    def _create_dependency_row(self, parent, name, description, key):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=15, pady=8)
        
        # Configurar columnas con pesos fijos para que no colapsen
        # Col 0: Info (Ancho mínimo reducido para dar espacio central)
        # Col 1: Progreso (Flexible, máxima prioridad)
        # Col 2: Botones (Fijo, apilados verticalmente)
        row_frame.grid_columnconfigure(0, weight=0, minsize=180)
        row_frame.grid_columnconfigure(1, weight=1)
        row_frame.grid_columnconfigure(2, weight=0, minsize=150)
        
        # 1. Información (Izquierda)
        info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="nsw")
        
        name_label = ctk.CTkLabel(info_frame, text=name, font=ctk.CTkFont(size=14, weight="bold"))
        name_label.pack(anchor="w")
        
        version_label = ctk.CTkLabel(info_frame, text="Versión: Desconocida", font=ctk.CTkFont(size=11), text_color="gray50", wraplength=180, justify="left")
        version_label.pack(anchor="w")
        self.dep_labels[key] = version_label
        
        # 2. Progreso (Centro - Pre-posicionado pero oculto)
        progress_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        # No usamos pack aquí, se griddeará en la función update_setup_download_progress
        
        status_label = ctk.CTkLabel(progress_frame, text="...", font=ctk.CTkFont(size=11), wraplength=250, justify="left")
        status_label.pack(anchor="w", pady=(0, 2))
        
        pbar = ctk.CTkProgressBar(progress_frame, width=200)
        pbar.set(0)
        pbar.pack(anchor="w", fill="x", expand=True)
        
        self.dep_progress[key] = {"frame": progress_frame, "label": status_label, "bar": pbar}
        
        # 3. Botón de Acción (Derecha)
        btn_container = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_container.grid(row=0, column=2, sticky="nse", padx=(10, 0))
        
        btn = ctk.CTkButton(btn_container, text="Actualizado", width=140, state="disabled", fg_color=self.SECONDARY_BTN, text_color=self.SECONDARY_TEXT)
        btn.pack(side="top", pady=2, fill="x")
        
        if key == "ffmpeg":
            safe_btn = ctk.CTkButton(btn_container, text="Restaurar (8.0.1)", width=140, 
                                     fg_color=self.STATUS_SUCCESS,
                                     command=self.manual_ffmpeg_safe_update_check)
            safe_btn.pack(side="top", pady=2, fill="x")
            self.dep_buttons["ffmpeg_safe"] = safe_btn

        # Conectar acción de descarga/instalación para cuando se habilita el botón
        if key == "ffmpeg":
            btn.configure(command=self.download_ffmpeg_update)
        elif key == "deno":
            btn.configure(command=self.download_deno_update)
        elif key == "poppler":
            btn.configure(command=self.download_poppler_update)
        elif key == "ytdlp":
            btn.configure(command=self.download_ytdlp_update)
            
        self.dep_buttons[key] = btn


    def _create_fixed_dependency_row(self, parent, name, description, key, url):
        """Crea una fila para una dependencia fija (comprobación de integridad)."""
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=15, pady=8)
        
        # Mantener consistencia con _create_dependency_row
        row_frame.grid_columnconfigure(0, weight=0, minsize=180)
        row_frame.grid_columnconfigure(1, weight=1)
        row_frame.grid_columnconfigure(2, weight=0, minsize=150)
        
        # 1. Nombre y descripción (Izquierda)
        info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="nsw")
        
        name_label = ctk.CTkLabel(info_frame, text=name, font=ctk.CTkFont(size=14, weight="bold"))
        name_label.pack(anchor="w")
        
        desc_label = ctk.CTkLabel(info_frame, text=description, font=ctk.CTkFont(size=11), text_color="gray50", wraplength=180, justify="left")
        desc_label.pack(anchor="w")
        
        # 2. Estado (Centro)
        status_label = ctk.CTkLabel(row_frame, text="Estado: Calculando...", font=ctk.CTkFont(size=12, weight="bold"), wraplength=250, justify="left")
        status_label.grid(row=0, column=1, sticky="w", padx=10)
        self.dep_labels[key] = status_label
        
        # 3. Botón Manual (Derecha)
        btn_container = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_container.grid(row=0, column=2, sticky="nse", padx=(10, 0))

        import webbrowser
        btn = ctk.CTkButton(
            btn_container, 
            text="Sitio Web Oficial", 
            width=140, 
            fg_color="transparent", 
            border_width=1, 
            text_color=("gray10", "gray90"),
            command=lambda u=url: webbrowser.open(u)
        )
        btn.pack(side="top", pady=2, fill="x")
            
        self.dep_buttons[key] = btn

    def select_section(self, section_name):
        """Muestra el frame de la sección elegida y oculta los demás. Resalta el botón."""
        
        # Ocultar todos los frames
        for frame in self.sections.values():
            frame.grid_forget()
            
        # Resaltar el botón seleccionado (efecto visual)
        for name, btn in self.menu_buttons.items():
            if name == section_name:
                # Color para el botón seleccionado (usar acento del tema)
                btn.configure(fg_color=self.MENU_SELECTED_BG, text_color=self.MENU_SELECTED_TEXT) 
            else:
                # Fondo transparente para los no seleccionados
                btn.configure(fg_color="transparent", text_color=self.MENU_NORMAL_TEXT) 
        
        # Mostrar el frame correspondiente en el contenedor
        if section_name in self.sections:
            self.sections[section_name].grid(row=0, column=0, sticky="nsew")

    # ================= LOGICA DE DEPENDENCIAS =================

    def update_setup_download_progress(self, key, text, value):
        """Actualiza la barra de progreso de una dependencia específica."""
        if not self.winfo_exists(): return
        
        # Si 'value' es <= 0 no mostrar barra
        if value < 0:
            if key in self.dep_progress:
                self.dep_progress[key]["frame"].grid_forget()
        else:
            if key in self.dep_progress:
                p_frame = self.dep_progress[key]["frame"]
                # Asegurar que esté griddéado correctamente en la columna 1
                if not p_frame.winfo_manager():
                    p_frame.grid(row=0, column=1, sticky="ew", padx=20)
                
                self.dep_progress[key]["label"].configure(text=text)
                # Escalar valor de 0-100 a 0.0-1.0 para el widget
                normalized_value = max(0.0, min(1.0, value / 100.0))
                self.dep_progress[key]["bar"].set(normalized_value)

    def _load_theme_colors(self):
        """Carga los colores del tema actual."""
        # Colores de Botones
        self.DOWNLOAD_BTN = self.app.get_theme_color("DOWNLOAD_BTN", ["#3B8ED0", "#1F6AA5"])
        self.DOWNLOAD_HOVER = self.app.get_theme_color("DOWNLOAD_BTN_HOVER", ["#367fb8", "#1a5a8a"])
        self.DOWNLOAD_TEXT = self.app.get_theme_color("DOWNLOAD_BTN_TEXT", ["white", "white"])
        
        self.CANCEL_BTN = self.app.get_theme_color("CANCEL_BTN", ["#dc3545", "#c82333"])
        self.CANCEL_HOVER = self.app.get_theme_color("CANCEL_BTN_HOVER", ["#c82333", "#bd2130"])
        self.CANCEL_TEXT = self.app.get_theme_color("CANCEL_BTN_TEXT", ["white", "white"])
        
        self.ANALYZE_BTN = self.app.get_theme_color("ANALYZE_BTN", ["#FF8C00", "#E67E22"])
        self.ANALYZE_HOVER = self.app.get_theme_color("ANALYZE_BTN_HOVER", ["#E67E22", "#D35400"])
        self.ANALYZE_TEXT = self.app.get_theme_color("ANALYZE_BTN_TEXT", ["white", "white"])
        
        self.SECONDARY_BTN = self.app.get_theme_color("SECONDARY_BTN", ["gray50", "gray30"])
        self.SECONDARY_HOVER = self.app.get_theme_color("SECONDARY_BTN_HOVER", ["gray60", "gray40"])
        self.SECONDARY_TEXT = self.app.get_theme_color("SECONDARY_BTN_TEXT", ["white", "white"])
        
        self.TERTIARY_BTN = self.app.get_theme_color("TERTIARY_BTN", ["#A0522D", "#8B4513"])
        self.TERTIARY_HOVER = self.app.get_theme_color("TERTIARY_BTN_HOVER", ["#8B4513", "#5D2E0B"])
        self.TERTIARY_TEXT = self.app.get_theme_color("TERTIARY_BTN_TEXT", ["white", "white"])
        
        self.QUATERNARY_BTN = self.app.get_theme_color("QUATERNARY_BTN", ["#E5DCC5", "#3F3F46"])
        self.QUATERNARY_HOVER = self.app.get_theme_color("QUATERNARY_BTN_HOVER", ["#D9CCB0", "#323238"])
        self.QUATERNARY_TEXT = self.app.get_theme_color("QUATERNARY_BTN_TEXT", ["gray10", "#DCE4EE"])

        # Colores de Consola
        self.CONSOLE_BG = self.app.get_theme_color("CONSOLE_BG", ["#F9F9FA", "#1D1E1E"])
        self.CONSOLE_TEXT = self.app.get_theme_color("CONSOLE_TEXT", ["gray10", "#DCE4EE"])

        # Colores de Estructura
        self.SECTION_SUBTITLE = self.app.get_theme_color("SECTION_SUBTITLE", ["#1F6AA5", "#52A2F2"])
        self.CONFIG_CARD_BG = self.app.get_theme_color("CONFIG_CARD_BG", ["gray85", "gray20"])
        self.CONFIG_CARD_BORDER = self.app.get_theme_color("CONFIG_CARD_BORDER", ["gray75", "gray30"])
        
        # Colores de Estado (Para feedback de botones y labels)
        self.STATUS_SUCCESS = self.app.get_theme_color("STATUS_SUCCESS", ["#28A745", "#218838"])
        self.STATUS_ERROR = self.app.get_theme_color("STATUS_ERROR", ["#DC3545", "#C82333"])
        self.STATUS_WARNING = self.app.get_theme_color("STATUS_WARNING", ["#FFA500", "#FF8C00"])
        self.STATUS_PENDING = self.app.get_theme_color("STATUS_PENDING", ["#565B5E", "#565B5E"])
        self.UPDATE_ALERT = self.app.get_theme_color("UPDATE_ALERT", self.STATUS_WARNING)
        self.SEPARATOR_COLOR = self.app.get_theme_color("SEPARATOR_COLOR", ["gray65", "#3F3F46"])
        
        # Colores de Menú Lateral (NUEVO)
        self.MENU_SELECTED_BG = self.app.get_theme_color("LISTBOX_SELECTED_BG", ["#3B8ED0", "#1F6AA5"])
        self.MENU_SELECTED_TEXT = self.app.get_theme_color("LISTBOX_SELECTED_TEXT", ["white", "white"])
        self.MENU_NORMAL_TEXT = self.app.get_theme_color("CTkLabel", ["gray10", "#DCE4EE"], is_ctk_widget=True)
        
        # Corner radius global del tema (o el de CTkFrame si no hay)
        _theme_frame = self.app.theme_data.get("CTkFrame", {})
        self.CONFIG_CARD_RADIUS = _theme_frame.get("corner_radius", 10)

    def refresh_theme(self):
        """Actualiza los colores de la pestaña de configuración dinámicamente."""
        # 1. Recargar colores
        self._load_theme_colors()
        
        # 2. Aplicar a estructuras (Cartas/Cuadritos)
        for card in self.config_cards:
            if card.winfo_exists():
                # Algunos frames especiales (notice, help, recovery) tienen colores de fondo propios
                # pero deben seguir el radio de borde del tema.
                card.configure(corner_radius=self.CONFIG_CARD_RADIUS)
                # Si es un frame de contenido general, aplicar colores de carta
                if card in [self.appearance_frame, self.master_frame, self.updatable_frame, self.fixed_frame, 
                           self.rembg_models_frame, self.upscaling_models_frame, self.custom_models_mgr_frame]:
                    card.configure(fg_color=self.CONFIG_CARD_BG, border_color=self.CONFIG_CARD_BORDER)

        # 3. Aplicar a subtítulos
        for sub in self.config_subtitles:
            if sub.winfo_exists():
                sub.configure(text_color=self.SECTION_SUBTITLE)

        # 4. Aplicar a botones específicos
        # Botones Principales (Dorado/Verde)
        main_btns = [
            'ink_verify_btn', 'test_cookies_btn', 
            'btn_check_all_updates', 'btn_add_custom', '_btn_execute'
        ]
        for btn_name in main_btns:
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                if btn.winfo_exists():
                    btn.configure(fg_color=self.DOWNLOAD_BTN, hover_color=self.DOWNLOAD_HOVER, text_color=self.DOWNLOAD_TEXT)
        
        # Botones Terciarios (Acento secundario/Temas)
        theme_btns = ['import_theme_btn', 'view_template_btn', 'install_url_btn', 'open_themes_btn']
        for btn_name in theme_btns:
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                if btn.winfo_exists():
                    btn.configure(fg_color=self.TERTIARY_BTN, hover_color=self.TERTIARY_HOVER, text_color=self.TERTIARY_TEXT)

        # Botones Secundarios (Bronce/Gris)
        sec_btns = [
            'ink_download_btn', 'btn_delete_custom', '_btn_copy', '_btn_export'
        ]
        for btn_name in sec_btns:
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                if btn.winfo_exists():
                    btn.configure(fg_color=self.SECONDARY_BTN, hover_color=self.SECONDARY_HOVER, text_color=self.SECONDARY_TEXT)

        # Botones Terciarios (Acento/HuggingFace)
        ter_btns = ['huggingface_btn']
        for btn_name in ter_btns:
            if hasattr(self, btn_name):
                btn = getattr(self, btn_name)
                if btn.winfo_exists():
                    btn.configure(fg_color=self.TERTIARY_BTN, hover_color=self.TERTIARY_HOVER, text_color=self.TERTIARY_TEXT)

        # Botón de liberar VRAM / Cancelar / Limpiar (Rojo/Peligro)
        if hasattr(self, 'clear_vram_btn'):
            self.clear_vram_btn.configure(fg_color=self.CANCEL_BTN, hover_color=self.CANCEL_HOVER, text_color=self.CANCEL_TEXT)
        if hasattr(self, '_btn_cancel_cmd'):
            self._btn_cancel_cmd.configure(border_color=self.CANCEL_BTN, text_color=self.CANCEL_TEXT, hover_color=self.CANCEL_HOVER)
        if hasattr(self, '_btn_clear'):
            self._btn_clear.configure(fg_color=self.CANCEL_BTN, hover_color=self.CANCEL_HOVER, text_color=self.CANCEL_TEXT)
        
        # 4b. Refrescar colores del menú lateral
        if hasattr(self, 'menu_buttons'):
            # Detectar cuál está seleccionado actualmente para reaplicar colores
            current_section = "general"
            for name, frame in self.sections.items():
                if frame.winfo_ismapped():
                    current_section = name
                    break
            self.select_section(current_section)
            
            # Sincronizar hover color de botones laterales
            for btn in self.menu_buttons.values():
                btn.configure(hover_color=self.MENU_SELECTED_BG)

        # 5. Botones de modelos e IA (Refrescar según estado para evitar pintado erróneo)
        if hasattr(self, 'model_rows'):
            for row_key in self.model_rows.keys():
                self._refresh_model_row(row_key)
        
        # Iconos de familia y Listbox
        for icon in self.model_family_icons:
            if icon.winfo_exists():
                icon.configure(fg_color=self.TERTIARY_BTN, hover_color=self.TERTIARY_HOVER, text_color=self.TERTIARY_TEXT)
        
        if hasattr(self, 'custom_models_listbox') and self.custom_models_listbox.winfo_exists():
            self.custom_models_listbox.configure(
                bg=self._resolve_color(self.app.get_theme_color("LISTBOX_BG", ["#F9F9FA", "#18181A"])),
                fg=self._resolve_color(self.app.get_theme_color("LISTBOX_TEXT", ["gray10", "#DCE4EE"]))
            )

        # 6. Colores de la Consola (Texto y Tags)
        if hasattr(self, '_console_textbox'):
            self._console_textbox.configure(fg_color=self.CONSOLE_BG, text_color=self.CONSOLE_TEXT)
            self._console_textbox.tag_config("user_command", foreground=self._resolve_color(self.SECTION_SUBTITLE))
            self._console_textbox.tag_config("error", foreground=self._resolve_color(self.STATUS_ERROR))
            self._console_textbox.tag_config("warning", foreground=self._resolve_color(self.STATUS_WARNING))
            self._console_textbox.tag_config("success", foreground=self._resolve_color(self.STATUS_SUCCESS))

        # Botones de dependencias (Filas individuales)
        if hasattr(self, 'dep_buttons'):
            for key, btn in self.dep_buttons.items():
                if not btn.winfo_exists(): continue
                
                # Sincronizar colores según el tipo de botón
                btn_text = btn.cget("text").lower()
                if "actualizar" in btn_text:
                    btn.configure(fg_color=self.DOWNLOAD_BTN, hover_color=self.DOWNLOAD_HOVER, text_color=self.DOWNLOAD_TEXT)
                elif "restaurar" in btn_text:
                    btn.configure(fg_color=self.STATUS_SUCCESS, hover_color=self.STATUS_SUCCESS, text_color="white")
                elif "actualizado" in btn_text:
                    # El botón ya está deshabilitado, pero podemos asegurar el color de fondo neutro
                    btn.configure(fg_color=self.app.get_theme_color("DISABLED_FG", ["#A0A0A0", "#404040"]))

        # 5. Lista de modelos personalizados (Misma lógica que ImageToolsTab)
        if hasattr(self, 'custom_models_listbox'):
            _lb_bg = self.app.get_theme_color("LISTBOX_BG", ["#F9F9FA", "#18181A"])
            _lb_text = self.app.get_theme_color("LISTBOX_TEXT", ["gray10", "#DCE4EE"])
            _lb_sel_bg = self.app.get_theme_color("LISTBOX_SELECTED_BG", ["#3B8ED0", "#1F6AA5"])
            _lb_sel_text = self.app.get_theme_color("LISTBOX_SELECTED_TEXT", ["white", "white"])
            _lb_bdr = self.app.get_theme_color("DND_BORDER", ["#565B5E", "#565B5E"])
            
            _bg = self._resolve_color(_lb_bg)
            _fg = self._resolve_color(_lb_text)
            _sbg = self._resolve_color(_lb_sel_bg)
            _sfg = self._resolve_color(_lb_sel_text)
            _bdc = self._resolve_color(_lb_bdr)
            
            self.custom_models_listbox.configure(
                bg=_bg, fg=_fg, 
                selectbackground=_sbg, selectforeground=_sfg,
                highlightbackground=_bdc, highlightthickness=1, borderwidth=0
            )

        # 6. Forzar refresco de consola
        if hasattr(self, '_console_textbox'):
            _lb_bg = self.app.get_theme_color("LISTBOX_BG", ["#F9F9FA", "#18181A"])
            _lb_text = self.app.get_theme_color("LISTBOX_TEXT", ["gray10", "#DCE4EE"])
            _status_success = self.app.get_theme_color("STATUS_SUCCESS", ["#28A745", "#218838"])
            _status_error = self.app.get_theme_color("STATUS_ERROR", ["#DC3545", "#C82333"])
            _status_warning = self.app.get_theme_color("STATUS_WARNING", ["#FFA500", "#FF8C00"])
            _accent = self.app.get_theme_color("DOWNLOAD_BTN", ["#3B8ED0", "#1F6AA5"])

            self._console_textbox.configure(
                fg_color=self._resolve_color(_lb_bg),
                text_color=self._resolve_color(_lb_text)
            )
            # Actualizar tags de colores
            self._console_textbox.tag_config("user_command", foreground=self._resolve_color(_accent))
            self._console_textbox.tag_config("error", foreground=self._resolve_color(_status_error))
            self._console_textbox.tag_config("warning", foreground=self._resolve_color(_status_warning))
            self._console_textbox.tag_config("success", foreground=self._resolve_color(_status_success))

        print("[REFRESH-THEME] OK ConfigTab actualizada dinámicamente.")

    def _resolve_color(self, color_pair):
        """Resuelve un par [claro, oscuro] según el modo de apariencia actual."""
        if not isinstance(color_pair, (list, tuple)) or len(color_pair) < 2:
            return color_pair
        return color_pair[1] if ctk.get_appearance_mode() == "Dark" else color_pair[0]

    def _load_local_versions(self):
        """Carga las versiones locales instantáneamente."""
        from src.core.setup import check_environment_status
        # Llamar con check_updates=False es súper rápido y no toca internet
        env_status = check_environment_status(lambda t, v: None, check_updates=False)
        
        # Mapeo de prefijos:
        # ffmpeg: local_version
        # deno: local_deno_version
        # poppler: local_poppler_version
        # ytdlp: local_ytdlp_version
        
        versions = {
            "ffmpeg": env_status.get("local_version") or "No encontrado",
            "deno": env_status.get("local_deno_version") or "No encontrado",
            "poppler": env_status.get("local_poppler_version") or "No encontrado",
            "ytdlp": env_status.get("local_ytdlp_version") or "No encontrado"
        }
        
        for key, ver in versions.items():
            if key in self.dep_labels:
                status_text = "No encontrado" if ver == "No encontrado" else f"Versión: {ver}"
                color = self.MENU_NORMAL_TEXT
                
                # REVISIÓN DE CACHE: Si ya buscamos actualizaciones antes en esta sesión, recuperamos el aviso
                cache = self.update_cache.get(key)
                
                # VALIDACIÓN DINÁMICA: Si la versión actual ya es igual a la última detectada, limpiar aviso
                if cache and cache.get("latest_version"):
                    latest = cache.get("latest_version").lstrip('v')
                    current = str(ver).lstrip('v')
                    if latest == current:
                        cache["update_available"] = False

                if cache and cache.get("update_available") and ver != "No encontrado":
                    status_text = f"Versión: {ver} \n(Actualización disponible: {cache.get('latest_version')})"
                    color = self.UPDATE_ALERT
                
                if ver == "No encontrado":
                    color = self.STATUS_ERROR
                
                self.dep_labels[key].configure(text=status_text, text_color=color)
                
            if key in self.dep_buttons:
                # Si hay una actualización en cache, habilitamos el botón correspondiente
                cache = self.update_cache.get(key)
                if cache and cache.get("update_available") and ver != "No encontrado":
                    self.dep_buttons[key].configure(state="normal", text="Actualizar", fg_color=self.DOWNLOAD_BTN, text_color=self.DOWNLOAD_TEXT, hover_color=self.DOWNLOAD_HOVER)
                    continue

                if ver == "No encontrado":
                    self.dep_buttons[key].configure(state="disabled", text="Usa Buscar", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
                else:
                    self.dep_buttons[key].configure(state="disabled", text="Actualizado", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
                
        # Si ya estamos en la versión segura de FFmpeg, deshabilita el botón de restaurar
        if versions["ffmpeg"] == "8.0.1" and "ffmpeg_safe" in self.dep_buttons:
            self.dep_buttons["ffmpeg_safe"].configure(state="disabled")

    def refresh_all_models(self):
        """Refresca visualmente el estado de todos los modelos basándose en si existen en disco."""
        if hasattr(self, 'model_rows'):
            for row_key in self.model_rows:
                self._refresh_model_row(row_key)

    def check_all_updates(self):
        """Busca actualizaciones consultando las APIs de GitHub en segundo plano."""
        self.btn_check_all_updates.configure(
            state="disabled", 
            text="Buscando...",
            fg_color=self.STATUS_PENDING # Color neutro mientras busca
        )
        
        # Ponemos los botones en estado de búsqueda
        for key in ["ffmpeg", "deno", "poppler", "ytdlp"]:
            self.dep_buttons[key].configure(state="disabled", text="Buscando...", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
            current_text = self.dep_labels[key].cget("text")
            self.dep_labels[key].configure(text=f"{current_text} - Buscando...", text_color="gray50")
            
        import threading
        from src.core.setup import check_environment_status
        def check_task():
            env_status = check_environment_status(lambda t, v: None, check_updates=True)
            self.app.after(0, lambda: self._on_all_updates_check_complete(env_status))
            
        threading.Thread(target=check_task, daemon=True).start()

    def _on_all_updates_check_complete(self, env_status):
        """Procesa los resultados de la búsqueda global y habilita botones si hay update."""
        self.btn_check_all_updates.configure(
            state="normal", 
            text="Buscar Actualizaciones", 
            fg_color=self.ANALYZE_BTN, 
            hover_color=self.ANALYZE_HOVER,
            text_color=self.ANALYZE_TEXT
        )
        import re
        from packaging import version
        
        # 1. FFmpeg
        local_ffmpeg = env_status.get("local_version") or "No encontrado"
        latest_ffmpeg = env_status.get("latest_version")
        self.latest_ffmpeg_url = env_status.get("download_url")
        self.latest_ffmpeg_version = latest_ffmpeg
        
        update_available_ffmpeg = False
        if local_ffmpeg != "No encontrado" and latest_ffmpeg:
             try:
                 local_v = version.parse(re.search(r'v?(\d+\.\d+(\.\d+)?)', local_ffmpeg).group(1))
                 latest_v = version.parse(re.search(r'v?(\d+\.\d+(\.\d+)?)', latest_ffmpeg).group(1))
                 if latest_v > local_v: update_available_ffmpeg = True
             except:
                 update_available_ffmpeg = local_ffmpeg != latest_ffmpeg
        elif local_ffmpeg == "No encontrado" and latest_ffmpeg:
             update_available_ffmpeg = True
             
        if update_available_ffmpeg:
            self.dep_labels["ffmpeg"].configure(text=f"Versión: {local_ffmpeg} \n(Actualización disponible: {latest_ffmpeg})", text_color=self.UPDATE_ALERT)
            self.dep_buttons["ffmpeg"].configure(state="normal", text=f"Actualizar", fg_color=self.DOWNLOAD_BTN, text_color=self.DOWNLOAD_TEXT, hover_color=self.DOWNLOAD_HOVER)
        else:
            self.dep_labels["ffmpeg"].configure(text=f"Versión: {local_ffmpeg} \n(Actualizado)", text_color=self.MENU_NORMAL_TEXT)
            self.dep_buttons["ffmpeg"].configure(state="disabled", text="Actualizado", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
            
        # Guardar en cache para persistencia de sesión
        self.update_cache["ffmpeg"] = {"latest_version": latest_ffmpeg, "update_available": update_available_ffmpeg}
            
        # 2. Deno
        local_deno = env_status.get("local_deno_version") or "No encontrado"
        latest_deno = env_status.get("latest_deno_version")
        self.latest_deno_url = env_status.get("deno_download_url")
        self.latest_deno_version = latest_deno
        
        update_available_deno = False
        if local_deno != "No encontrado" and latest_deno:
             try:
                 local_v = version.parse(local_deno.lstrip('v'))
                 latest_v = version.parse(latest_deno.lstrip('v'))
                 if latest_v > local_v: update_available_deno = True
             except:
                 update_available_deno = local_deno != latest_deno
        elif local_deno == "No encontrado" and latest_deno:
             update_available_deno = True
             
        if update_available_deno:
            self.dep_labels["deno"].configure(text=f"Versión: {local_deno} \n(Actualización disponible: {latest_deno})", text_color=self.UPDATE_ALERT)
            self.dep_buttons["deno"].configure(state="normal", text=f"Actualizar", fg_color=self.DOWNLOAD_BTN, text_color=self.DOWNLOAD_TEXT, hover_color=self.DOWNLOAD_HOVER)
        else:
            self.dep_labels["deno"].configure(text=f"Versión: {local_deno} \n(Actualizado)", text_color=self.MENU_NORMAL_TEXT)
            self.dep_buttons["deno"].configure(state="disabled", text="Actualizado", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
            
        # Guardar en cache para persistencia de sesión
        self.update_cache["deno"] = {"latest_version": latest_deno, "update_available": update_available_deno}
            
        # 3. Poppler
        local_poppler = env_status.get("local_poppler_version") or "No encontrado"
        latest_poppler = env_status.get("latest_poppler_version")
        self.latest_poppler_url = env_status.get("poppler_download_url")
        self.latest_poppler_version = latest_poppler
        
        update_available_poppler = False
        if local_poppler != "No encontrado" and latest_poppler:
            update_available_poppler = local_poppler != latest_poppler
        elif local_poppler == "No encontrado" and latest_poppler:
            update_available_poppler = True
            
        if update_available_poppler:
            self.dep_labels["poppler"].configure(text=f"Versión: {local_poppler} \n(Actualización disponible: {latest_poppler})", text_color=self.UPDATE_ALERT)
            self.dep_buttons["poppler"].configure(state="normal", text=f"Actualizar", fg_color=self.DOWNLOAD_BTN, text_color=self.DOWNLOAD_TEXT, hover_color=self.DOWNLOAD_HOVER)
        else:
            self.dep_labels["poppler"].configure(text=f"Versión: {local_poppler} \n(Actualizado)", text_color=self.MENU_NORMAL_TEXT)
            self.dep_buttons["poppler"].configure(state="disabled", text="Actualizado", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
            
        # Guardar en cache para persistencia de sesión
        self.update_cache["poppler"] = {"latest_version": latest_poppler, "update_available": update_available_poppler}
            
        # 4. yt-dlp
        local_ytdlp = env_status.get("local_ytdlp_version") or "No encontrado"
        latest_ytdlp = env_status.get("latest_ytdlp_version")
        self.latest_ytdlp_url = env_status.get("ytdlp_download_url")
        self.latest_ytdlp_version = latest_ytdlp
        
        update_available_ytdlp = False
        if local_ytdlp != "No encontrado" and latest_ytdlp:
             try:
                 local_v = version.parse(local_ytdlp)
                 latest_v = version.parse(latest_ytdlp)
                 if latest_v > local_v: update_available_ytdlp = True
             except:
                 update_available_ytdlp = local_ytdlp != latest_ytdlp
        elif local_ytdlp == "No encontrado" and latest_ytdlp:
             update_available_ytdlp = True

        if update_available_ytdlp:
            self.dep_labels["ytdlp"].configure(text=f"Versión: {local_ytdlp} \n(Actualización disponible: {latest_ytdlp})", text_color=self.UPDATE_ALERT)
            self.dep_buttons["ytdlp"].configure(state="normal", text=f"Actualizar", fg_color=self.DOWNLOAD_BTN, text_color=self.DOWNLOAD_TEXT, hover_color=self.DOWNLOAD_HOVER)
        else:
            self.dep_labels["ytdlp"].configure(text=f"Versión: {local_ytdlp} \n(Actualizado)", text_color=self.MENU_NORMAL_TEXT)
            self.dep_buttons["ytdlp"].configure(state="disabled", text="Actualizado", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
            
        # Guardar en cache para persistencia de sesión
        self.update_cache["ytdlp"] = {"latest_version": latest_ytdlp, "update_available": update_available_ytdlp}


    def download_ffmpeg_update(self):
        from tkinter import messagebox
        Tooltip.hide_all()
        response = messagebox.askyesno(
            "Aviso de Actualización",
            "Estás a punto de instalar la última versión pública de FFmpeg.\n\n"
            "Nota: En algunas ocasiones puntuales, las compilaciones muy nuevas de FFmpeg pueden presentar cierta inestabilidad al descargar videos o audios fragmentados de YouTube.\n\n"
            "Si llegas a experimentar que las descargas se atascan y no inician, siempre puedes usar el botón verde 'Restaurar (8.0.1)' para regresar a nuestra versión estable probada.\n\n"
            "¿Deseas continuar e instalar la nueva actualización?"
        )
        if not response:
            return
            
        self.dep_buttons["ffmpeg"].configure(state="disabled", text="Instalando...")
        import threading
        from src.core.setup import download_and_install_ffmpeg
        def download_task():
            success = download_and_install_ffmpeg(
                self.latest_ffmpeg_version, 
                self.latest_ffmpeg_url, 
                lambda text, val, c_mb=0, t_mb=0: self.app.after(0, lambda: self.update_setup_download_progress('ffmpeg', text, val))
            )
            self.app.after(0, lambda: self._on_download_complete("ffmpeg", success))
        threading.Thread(target=download_task, daemon=True).start()
        
    def download_deno_update(self):
        self.dep_buttons["deno"].configure(state="disabled", text="Instalando...")
        import threading
        from src.core.setup import download_and_install_deno
        def download_task():
            success = download_and_install_deno(
                self.latest_deno_version, 
                self.latest_deno_url, 
                lambda text, val, c_mb=0, t_mb=0: self.app.after(0, lambda: self.update_setup_download_progress('deno', text, val))
            )
            self.app.after(0, lambda: self._on_download_complete("deno", success))
        threading.Thread(target=download_task, daemon=True).start()
        
    def download_poppler_update(self):
        self.dep_buttons["poppler"].configure(state="disabled", text="Instalando...")
        import threading
        from src.core.setup import download_and_install_poppler
        def download_task():
            success = download_and_install_poppler(
                self.latest_poppler_version, 
                self.latest_poppler_url, 
                lambda text, val, c_mb=0, t_mb=0: self.app.after(0, lambda: self.update_setup_download_progress('poppler', text, val))
            )
            self.app.after(0, lambda: self._on_download_complete("poppler", success))
        threading.Thread(target=download_task, daemon=True).start()
        
    def download_ytdlp_update(self):
        self.dep_buttons["ytdlp"].configure(state="disabled", text="Instalando...")
        import threading
        from src.core.setup import download_and_install_ytdlp
        def download_task():
            success = download_and_install_ytdlp(
                self.latest_ytdlp_version, 
                self.latest_ytdlp_url, 
                lambda text, val, c_mb=0, t_mb=0: self.app.after(0, lambda: self.update_setup_download_progress('ytdlp', text, val))
            )
            self.app.after(0, lambda: self._on_download_complete("ytdlp", success))
        threading.Thread(target=download_task, daemon=True).start()

    def manual_ffmpeg_safe_update_check(self):
        """Instala forzadamente la versión segura de FFmpeg (8.0.1)."""
        from tkinter import messagebox
        Tooltip.hide_all()
        confirm = messagebox.askyesno(
            "Restaurar Versión Default",
            "¿Deseas restaurar la versión Default de FFmpeg (8.0.1)?\n\n"
            "Esta versión es recomendada para solucionar problemas con fragmentos de YouTube.\n"
            "Se sobrescribirá tu versión actual."
        )
        if not confirm:
            return

        self.dep_buttons["ffmpeg"].configure(state="disabled")
        self.dep_buttons["ffmpeg_safe"].configure(state="disabled", text="Instalando...")
        
        import threading
        from src.core.setup import download_and_install_ffmpeg, get_safe_ffmpeg_info
        def download_task():
            tag, url = get_safe_ffmpeg_info(
                lambda text, val, c_mb=0, t_mb=0: self.app.after(0, lambda: self.update_setup_download_progress('ffmpeg', text, val))
            )
            success = download_and_install_ffmpeg(
                tag, url, 
                lambda text, val, c_mb=0, t_mb=0: self.app.after(0, lambda: self.update_setup_download_progress('ffmpeg', text, val))
            )
            self.app.after(0, lambda: self._on_download_complete("ffmpeg", success))
        threading.Thread(target=download_task, daemon=True).start()

    def _on_download_complete(self, key, success):
        """Finaliza el ciclo de descarga de un componente individual."""
        self.update_setup_download_progress(key, "", -1) # Ocultar barra
        
        if success:
            # Solo recargamos la versión local exacta de la dependencia que se actualizó
            from src.core.setup import check_environment_status
            env_status = check_environment_status(lambda t, v: None, check_updates=False)
            mapping = {
                "ffmpeg": "local_version",
                "deno": "local_deno_version",
                "poppler": "local_poppler_version",
                "ytdlp": "local_ytdlp_version"
            }
            new_ver = env_status.get(mapping[key]) or "Desconocida"
            self.dep_labels[key].configure(text=f"Versión: {new_ver} \n(Actualizado)", text_color="gray50")
            self.dep_buttons[key].configure(state="disabled", text="Actualizado", fg_color=self.STATUS_PENDING, text_color=self.MENU_NORMAL_TEXT)
            
            # Limpiar caché de actualización para que no vuelva a salir el aviso al cambiar de pestaña
            if key in self.update_cache:
                self.update_cache[key]["update_available"] = False
            
            if key == "ffmpeg" and "ffmpeg_safe" in self.dep_buttons:
                self.dep_buttons["ffmpeg_safe"].configure(state="normal", text="Restaurar (8.0.1)")
                if new_ver == "8.0.1":
                    self.dep_buttons["ffmpeg_safe"].configure(state="disabled")
                    
            if key == "ytdlp":
                from tkinter import messagebox
                Tooltip.hide_all()
                if messagebox.askyesno("Reinicio Necesario", "Se actualizó yt-dlp exitosamente.\n\nEs OBLIGATORIO reiniciar DowP para evitar fallos. ¿Reiniciar ahora?"):
                    import sys, os, subprocess, tempfile
                    try:
                        # Limpiar el cerrojo de la ventana manualmente antes de invocar la otra
                        lockfile = os.path.join(tempfile.gettempdir(), 'dowp.lock')
                        if os.path.exists(lockfile):
                            try: os.remove(lockfile)
                            except: pass
                            
                        subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "main.py")])
                        self.app.destroy()
                        sys.exit(0)
                    except Exception as e:
                        print(f"ERROR reiniciando: {e}")
        else:
            if key == "ffmpeg" and "ffmpeg_safe" in self.dep_buttons:
                self.dep_buttons["ffmpeg_safe"].configure(state="normal", text="Restaurar (8.0.1)")
            from tkinter import messagebox
            Tooltip.hide_all()
            messagebox.showerror("Error", f"La actualizaci\xf3n de {key} fall\xf3. Revisa la consola o tu conexi\xf3n.")


    # ================= LOGICA DE COOKIES =================

    def _on_cookie_detail_change(self, event=None):
        """Disparado cuando rutas, nombres de perfil o el navegador cambian."""
        # Se envía al global
        self.app.cookies_path = self.cookie_path_entry.get()
        self.app.selected_browser_saved = self.browser_var.get()
        self.app.browser_profile_saved = self.browser_profile_entry.get()
        
        # Limpiamos la caché de análisis del menú de descarga único
        if hasattr(self.app, 'single_tab'):
            self.app.single_tab.analysis_cache.clear()
            
        print("DEBUG: Cookies detail changed by Settings tab.")

    def on_cookie_mode_change(self, mode, save=True):
        """Muestra/Oculta los paneles dinámicos de las cookies según el selector."""
        if mode == "No usar":
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack_forget()
            self.cookie_dynamic_frame.pack_forget()
            self.test_cookies_btn.configure(state="disabled")
        elif mode == "Archivo Manual...":
            if hasattr(self, 'help_frame'):
                self.cookie_dynamic_frame.pack(fill="x", before=self.help_frame)
            else:
                self.cookie_dynamic_frame.pack(fill="x")
            self.manual_cookie_frame.pack(fill="x", pady=(5,0))
            self.browser_options_frame.pack_forget()
            self.test_cookies_btn.configure(state="normal")
        elif mode == "Desde Navegador":
            if hasattr(self, 'help_frame'):
                self.cookie_dynamic_frame.pack(fill="x", before=self.help_frame)
            else:
                self.cookie_dynamic_frame.pack(fill="x")
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack(fill="x", pady=(5,0))
            self.test_cookies_btn.configure(state="normal")
            
        if save:
            self.app.cookies_mode_saved = mode
            if hasattr(self.app, 'single_tab'):
                self.app.single_tab.analysis_cache.clear()
            print(f"DEBUG: Cookie mode changed to {mode}")

    def select_cookie_file(self):
        """Abre un gestor de archivos para que el usuario navegue su cookies.txt"""
        import customtkinter as ctk
        filepath = ctk.filedialog.askopenfilename(title="Selecciona tu archivo de cookies (.txt)", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if filepath:
            self.cookie_path_entry.delete(0, 'end')
            self.cookie_path_entry.insert(0, filepath)
            # Propaga el trigger manual
            self._on_cookie_detail_change()

    # ========================== VALIDACIÓN DE COOKIES ==========================

    def _test_cookies(self):
        mode = self.app.cookies_mode_saved
        if mode == "No usar":
            return
            
        args = {}
        if mode == "Archivo Manual...":
            path = self.cookie_path_entry.get().strip()
            if not path:
                from tkinter import messagebox
                Tooltip.hide_all()
                messagebox.showwarning("Prueba Inválida", "La ruta del archivo está vacía.\n\nUsa el botón 'Examinar...' para localizar tu archivo de cookies.")
                return
            args['cookiefile'] = path
            
        elif mode == "Desde Navegador":
            browser = self.browser_var.get()
            profile = self.browser_profile_entry.get().strip()
            if profile:
                args['cookiesfrombrowser'] = (f"{browser}:{profile}",)
            else:
                args['cookiesfrombrowser'] = (browser,)

        self.test_cookies_btn.configure(state="disabled", text="Probando...")
        
        import threading
        t = threading.Thread(target=self._run_cookie_test_thread, args=(args,), daemon=True)
        t.start()

    def _run_cookie_test_thread(self, ydl_opts):
        import traceback
        try:
            import yt_dlp
            # Al invocar el constructor y apelar a 'cookiejar', yt-dlp iniciará forzosamente el desencriptado de la DB.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                cookies = ydl.cookiejar
                num_cookies = len(cookies)
                
            self.app.after(0, lambda: self._on_test_cookies_success(num_cookies))
        except Exception as e:
            err_msg = str(e)
            full_trace = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            suggestion = ""
            if "database is locked" in err_msg.lower() or "database is locked" in full_trace.lower() or "permission" in err_msg.lower() or "file is locked" in full_trace.lower():
                suggestion = "\n\n⚠️ SUGERENCIA: Existe un bloqueo de lectura en los archivos. \nAsegúrate de que el navegador esté TOTALMENTE CERRADO e intenta de nuevo."
            elif "could not find" in err_msg.lower():
                suggestion = "\n\n⚠️ SUGERENCIA: yt-dlp no pudo localizar la base de datos.\nAsegúrate de tener el perfil correcto o cambia al modo superior 'Archivo Manual'."
            else:
                suggestion = "\n\n⚠️ SUGERENCIA: Si seleccionaste un navegador basado en Chromium (Edge, Brave, Chrome, etc.) la extracción suele fallar por su nivel de encriptación extrema. Prueba cambiando a Firefox o usando la alternativa segura 'Archivo Manual'."
            
            import re
            # Limpiamos los códigos de colores ANSI que yt-dlp incrusta en los mensajes de consola
            clean_err = re.sub(r'\x1b\[[0-9;]*m', '', err_msg)
            clean_err = clean_err.replace("yt_dlp.utils.DownloadError: ", "")
            
            self.app.after(0, lambda: self._on_test_cookies_error(clean_err, suggestion))

    def _on_test_cookies_success(self, count):
        self.test_cookies_btn.configure(state="normal", text="Probar Cookies")
        from tkinter import messagebox
        Tooltip.hide_all()
        messagebox.showinfo("Prueba Exitosa", f"✅ yt-dlp logró conectarse y leer el archivo de sesión sin bloqueos.\n\nSe identificaron de forma limpia {count} cookies en memoria listas para descargar.")

    def _on_test_cookies_error(self, err_msg, suggestion):
        self.test_cookies_btn.configure(state="normal", text="Probar Cookies")
        from tkinter import messagebox
        Tooltip.hide_all()
        messagebox.showerror("Error Severo de Cookies", f"Falló el intento de extracción yt-dlp:\n\n{err_msg}{suggestion}")
    # ================= GESTIÓN DE MODELOS PERSONALIZADOS =================

    def _on_add_custom_model_config(self):
        """Callback para el botón 'Añadir' en la pestaña de ajustes."""
        from src.core.setup import install_custom_upscayl_model
        if install_custom_upscayl_model(self.app):
            self.app.refresh_custom_models_across_tabs()

    def _refresh_custom_models_list(self):
        """Actualiza la Listbox con los modelos personalizados y sus pesos."""
        if not hasattr(self, 'custom_models_listbox'):
            return
            
        self.custom_models_listbox.delete(0, 'end')
        custom_models = getattr(self.app, 'upscayl_custom_models', {})
        
        from main import UPSCALING_DIR
        models_dir = os.path.join(UPSCALING_DIR, "upscayl", "models")
        
        for real_name, nickname in custom_models.items():
            # Calcular peso
            total_size = 0
            bin_p = os.path.join(models_dir, real_name + ".bin")
            param_p = os.path.join(models_dir, real_name + ".param")
            
            if os.path.exists(bin_p): total_size += os.path.getsize(bin_p)
            if os.path.exists(param_p): total_size += os.path.getsize(param_p)
            
            size_str = self._format_size(total_size)
            self.custom_models_listbox.insert('end', f" {nickname}  ({size_str})  [{real_name}]")
        
        # Forzar actualización de altura para el scrollable frame
        self.update_idletasks()
        
        # Resetear estado del botón de borrado
        self._on_custom_model_select()

    def _on_custom_model_select(self, event=None):
        """Actualiza el estado del botón de borrado según la selección."""
        if not hasattr(self, 'custom_models_listbox') or not hasattr(self, 'btn_delete_custom'):
            return
            
        selection = self.custom_models_listbox.curselection()
        if selection:
            self.btn_delete_custom.configure(state="normal", fg_color="#DC3545", hover_color="#C82333")
        else:
            self.btn_delete_custom.configure(state="disabled", fg_color="#6c757d")

    def _delete_selected_custom_models(self):
        """Borra los modelos seleccionados físicamente y de los ajustes."""
        selected_indices = self.custom_models_listbox.curselection()
        if not selected_indices:
            from tkinter import messagebox
            Tooltip.hide_all()
            messagebox.showwarning("Atención", "No has seleccionado ningún modelo de la lista.")
            return
            
        from tkinter import messagebox
        Tooltip.hide_all()
        if not messagebox.askyesno("Confirmar Borrado", f"¿Estás seguro de que deseas eliminar los {len(selected_indices)} modelos seleccionados?\n\nEsta acción no se puede deshacer."):
            return
            
        from src.core.setup import delete_custom_upscayl_model
        
        # Obtener los nombres reales (están entre corchetes al final de cada string)
        to_delete = []
        for i in selected_indices:
            text = self.custom_models_listbox.get(i)
            import re
            match = re.search(r'\[(.*?)\]$', text)
            if match:
                to_delete.append(match.group(1))
        
        success_count = 0
        for real_name in to_delete:
            if delete_custom_upscayl_model(real_name, self.app):
                success_count += 1
                
        # Refrescar todas las pestañas de forma sincronizada
        self.app.refresh_custom_models_across_tabs()
            
        Tooltip.hide_all()
        messagebox.showinfo("Limpieza Completada", f"Se han eliminado {success_count} modelos correctamente.")

    def _on_integration_toggle(self):
        """Actualiza los ajustes de integración en la app."""
        self.app.adobe_enabled = self.adobe_master_var.get()
        self.app.adobe_import_single = self.adobe_single_var.get()
        self.app.adobe_import_batch = self.adobe_batch_var.get()
        self.app.adobe_import_image = self.adobe_image_var.get()

        self.app.davinci_enabled = self.davinci_master_var.get()
        self.app.davinci_import_single = self.davinci_single_var.get()
        self.app.davinci_import_batch = self.davinci_batch_var.get()
        self.app.davinci_import_image = self.davinci_image_var.get()
        self.app.davinci_import_everything = self.davinci_everything_var.get()
        self.app.davinci_import_to_timeline = self.davinci_timeline_var.get()
        
        # Sincronizar estado visual de los sub-switches
        self._update_integration_switches_state()
        
        self.app.save_settings()

    def _update_integration_switches_state(self):
        """Habilita o deshabilita los sub-switches según el master switch."""
        adobe_state = "normal" if self.adobe_master_var.get() else "disabled"
        self.adobe_single_switch.configure(state=adobe_state)
        self.adobe_batch_switch.configure(state=adobe_state)
        self.adobe_image_switch.configure(state=adobe_state)

        davinci_state = "normal" if self.davinci_master_var.get() else "disabled"
        self.davinci_single_switch.configure(state=davinci_state)
        self.davinci_batch_switch.configure(state=davinci_state)
        self.davinci_image_switch.configure(state=davinci_state)
        self.davinci_everything_switch.configure(state=davinci_state)
        self.davinci_timeline_switch.configure(state=davinci_state)

    def _on_vector_bg_toggle(self):
        self.app.vector_force_background = self.vector_bg_var.get()
        self.app.save_settings()

    def _on_inkscape_toggle(self):
        self.app.inkscape_enabled = self.inkscape_enabled_var.get()
        self._check_inkscape_status()
        self.app.save_settings()

    def _on_inkscape_path_change(self, event=None):
        self.app.inkscape_path = self.inkscape_path_entry.get()
        # Resetear versión guardada si la ruta cambia
        self.app.inkscape_version = ""
        self.ink_status_label.configure(text="⚠️ La ruta cambió. Por favor, vuelve a comprobar.", text_color="#FFC107")
        self.app.save_settings()

    def _browse_inkscape_path(self):
        path = filedialog.askdirectory(title="Selecciona la carpeta de instalación de Inkscape")
        if path:
            self.inkscape_path_entry.delete(0, "end")
            self.inkscape_path_entry.insert(0, path)
            self._on_inkscape_path_change()

    def _check_inkscape_status(self):
        """Valida si la ruta de Inkscape es correcta y actualiza el estado visual."""
        self.ink_status_label.configure(text="⏳ Verificando...", text_color="gray50")
        self.update_idletasks() # Forzar actualización visual
        
        from src.core.inkscape_service import InkscapeService
        service = InkscapeService(self.app.inkscape_path)
        
        if service.is_available():
            v_text = service.version_info.split("(")[0].strip() if service.version_info else "Disponible"
            self.ink_status_label.configure(text=f"✅ Inkscape detectado: {v_text}", text_color="#28A745")
            self.app.inkscape_version = v_text
            self.app.inkscape_service = service
        else:
            self.app.inkscape_version = ""
            if self.app.inkscape_enabled:
                self.ink_status_label.configure(text="❌ No se encontró Inkscape en la ruta especificada.", text_color="#DC3545")
            else:
                self.ink_status_label.configure(text="Inkscape desactivado. Se usarán motores nativos.", text_color="gray50")
            self.app.inkscape_service = None
        
        # 🔄 PROPAGAR CAMBIO DINÁMICAMENTE (Sin reiniciar app)
        if hasattr(self.app, 'image_tab'):
            if hasattr(self.app.image_tab, 'image_processor'):
                self.app.image_tab.image_processor.inkscape_service = self.app.inkscape_service
            if hasattr(self.app.image_tab, 'image_converter'):
                self.app.image_tab.image_converter.inkscape_service = self.app.inkscape_service
            print("DEBUG: Referencias de Inkscape actualizadas en ImageToolsTab.")
        
        self.app.save_settings()
    def _on_view_template(self):
        """Muestra el diálogo con la plantilla del tema (dorado.json)."""
        import json
        from src.gui.dialogs import ThemeTemplateDialog
        
        # Intentar cargar dorado.json (que es nuestra base)
        base_path = getattr(sys, '_MEIPASS', self.app.APP_BASE_PATH)
        dorado_path = os.path.join(base_path, "src", "gui", "themes", "dorado.json")
        
        template_content = ""
        if os.path.exists(dorado_path):
            try:
                with open(dorado_path, 'r', encoding='utf-8') as f:
                    # Lo cargamos y volvemos a volcar para asegurar indentación bonita
                    data = json.load(f)
                    template_content = json.dumps(data, indent=2, ensure_ascii=False)
            except Exception as e:
                template_content = f"Error cargando dorado.json: {e}"
        else:
            template_content = "Error: No se encontró dorado.json en la ruta especificada."
            
        if not template_content:
             template_content = "// No se pudo cargar la plantilla."

        ThemeTemplateDialog(self.app, template_content)
