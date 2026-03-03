import customtkinter as ctk
import os
import threading
import requests

class ConfigTab(ctk.CTkFrame):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app
        
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
        self.sidebar_frame.grid_rowconfigure(5, weight=1) # Empujar elementos hacia arriba
        
        self.sidebar_title = ctk.CTkLabel(self.sidebar_frame, text="Opciones", font=ctk.CTkFont(size=16, weight="bold"))
        self.sidebar_title.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Botones del menú lateral
        self.btn_general = ctk.CTkButton(self.sidebar_frame, text="General", fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", command=lambda: self.select_section("general"))
        self.btn_general.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_cookies = ctk.CTkButton(self.sidebar_frame, text="Cookies", fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", command=lambda: self.select_section("cookies"))
        self.btn_cookies.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_deps = ctk.CTkButton(self.sidebar_frame, text="Dependencias", fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", command=lambda: self.select_section("deps"))
        self.btn_deps.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_models = ctk.CTkButton(self.sidebar_frame, text="Modelos", fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", command=lambda: self.select_section("models"))
        self.btn_models.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        
        # Guardamos los botones en un dict para cambiarles el color al seleccionarlos
        self.menu_buttons = {
            "general": self.btn_general,
            "cookies": self.btn_cookies,
            "deps": self.btn_deps,
            "models": self.btn_models
        }
        
        # ==================== ÁREA DE CONTENIDO (Derecha) ====================
        self.content_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)
        
        # Diccionario para guardar los frames de cada sección
        self.sections = {}
        
        self._setup_sections()
        
        # ==================== BARRA INFERIOR (Abajo) ====================
        self.bottom_frame = ctk.CTkFrame(self, height=40, corner_radius=0)
        self.bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.bottom_frame.pack_propagate(False) # Prevenir que cambie de altura por el contenido
        
        # Contenido de la barra inferior
        self.about_label = ctk.CTkLabel(self.bottom_frame, text="DowP by MarckDBM |", font=ctk.CTkFont(size=12, weight="bold"))
        self.about_label.pack(side="left", padx=(15, 5), pady=10)
        
        import webbrowser
        
        self.link_yt = ctk.CTkButton(self.bottom_frame, text="YouTube", width=60, height=20, fg_color=("#FFB6B6", "#8C3A3A"), text_color=("gray10", "gray90"), hover_color=("#FF9999", "#A64D4D"), command=lambda: webbrowser.open("https://www.youtube.com/@MarckDBM"))
        self.link_yt.pack(side="left", padx=5)

        self.link_github = ctk.CTkButton(self.bottom_frame, text="GitHub", width=50, height=20, fg_color=("#E0E0E0", "#4D4D4D"), text_color=("gray10", "gray90"), hover_color=("#CCCCCC", "#666666"), command=lambda: webbrowser.open("https://github.com/MarckDP/DowP_Downloader"))
        self.link_github.pack(side="left", padx=5)
        
        self.link_donate = ctk.CTkButton(self.bottom_frame, text="Ko-fi ☕", width=80, height=20, fg_color=("#BAE1FF", "#3A628C"), text_color=("gray10", "gray90"), hover_color=("#99CCFF", "#4D7CB3"), command=lambda: webbrowser.open("https://ko-fi.com/marckdbm"))
        self.link_donate.pack(side="left", padx=5)

        self.version_label = ctk.CTkLabel(self.bottom_frame, text=f"Versión {getattr(self.app, 'APP_VERSION', 'Desconocida')}", font=ctk.CTkFont(size=12), text_color="gray50")
        self.version_label.pack(side="right", padx=15, pady=10)

        # Seleccionar la primera sección por defecto
        self.select_section("general")

    def _setup_sections(self):
        """Inicializa los frames para cada sección pero los oculta por defecto."""
        
        # ===== Sección: General =====
        frame_general = ctk.CTkFrame(self.content_container, fg_color="transparent")
        ctk.CTkLabel(frame_general, text="Configuraciones Generales", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 20))
        ctk.CTkLabel(frame_general, text="Aquí irán opciones de comportamiento por defecto del programa, como:\n- Ubicaciones de descargas.\n- Temas visuales.\n- Otras opciones de la app.", justify="left").pack(anchor="w")
        self.sections["general"] = frame_general
        
        # ===== Sección: Cookies =====
        frame_cookies = ctk.CTkFrame(self.content_container, fg_color="transparent")
        ctk.CTkLabel(frame_cookies, text="Gestión de Cookies", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        cookie_desc = "Configura las cookies para acceder a contenido protegido por edad, videos privados, o contenido restringido que requiera haber iniciado sesión en el servicio."
        ctk.CTkLabel(frame_cookies, text=cookie_desc, justify="left", wraplength=600, text_color="gray60").pack(anchor="w", pady=(0, 20))
        
        # Selector de Modo
        ctk.CTkLabel(frame_cookies, text="Modo de Cookies:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.cookie_mode_menu = ctk.CTkOptionMenu(
            frame_cookies, 
            values=["No usar", "Archivo Manual...", "Desde Navegador"], 
            command=self.on_cookie_mode_change
        )
        self.cookie_mode_menu.pack(anchor="w", fill="x", pady=(5, 15))

        # Contenedor Dinámico
        self.cookie_dynamic_frame = ctk.CTkFrame(frame_cookies, fg_color="transparent")
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
        
        cookie_advice_label = ctk.CTkLabel(self.browser_options_frame, text=" ⓘ Si falla, cierre el navegador por completo. \n ⓘ Para Chrome/Edge/Brave, se recomienda usar la opción 'Archivo Manual'", font=ctk.CTkFont(size=11), text_color="orange", justify="left")
        cookie_advice_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        
        # --- Sección de Ayuda ---
        help_frame = ctk.CTkFrame(frame_cookies, fg_color=("gray85", "gray20"))
        help_frame.pack(fill="x", pady=(30, 0), ipadx=10, ipady=10)
        ctk.CTkLabel(help_frame, text="¿Cómo obtener cookies de forma segura?", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(10, 5))
        ctk.CTkLabel(help_frame, text="La forma más infalible de evitar bloqueos de descarga por falta de autorizaciones en YouTube u otras plataformas es extrayendo tu sesión actual con el complemento de navegador Open Source 'Get cookies.txt LOCALLY'.", justify="left", text_color="gray50", wraplength=550).pack(anchor="w", padx=20, pady=(0, 10))
        
        import webbrowser
        ctk.CTkButton(help_frame, text="Descargar Extensión (GitHub)", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"), command=lambda: webbrowser.open_new_tab("https://github.com/kairi003/Get-cookies.txt-LOCALLY")).pack(anchor="w", padx=20, pady=(0, 10))
        
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
        frame_deps = ctk.CTkFrame(self.content_container, fg_color="transparent")
        
        # Título principal
        ctk.CTkLabel(frame_deps, text="Dependencias y Herramientas Externas", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 20))
        
        # --- SUB-SECCIÓN: ACTUALIZABLES ---
        ctk.CTkLabel(frame_deps, text="Componentes Actualizables", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        # Frame contenedor para las actualizables
        self.updatable_frame = ctk.CTkFrame(frame_deps, fg_color=("gray85", "gray20"))
        self.updatable_frame.pack(fill="x", pady=(0, 20), padx=5)
        
        # Diccionarios para guardar referencias a las etiquetas y botones
        self.dep_labels = {}
        self.dep_progress = {}
        self.dep_buttons = {}
        
        # Crear filas (FFmpeg, Deno, Poppler)
        self._create_dependency_row(self.updatable_frame, "FFmpeg", "Motor de procesamiento multimedia", "ffmpeg")
        self._create_dependency_row(self.updatable_frame, "Deno", "Entorno de ejecución interno", "deno")
        self._create_dependency_row(self.updatable_frame, "Poppler", "Herramienta de extracción de PDF", "poppler")
        
        # --- SEPARADOR VISUAL ---
        separator = ctk.CTkFrame(frame_deps, height=2, fg_color=("gray75", "gray30"))
        separator.pack(fill="x", pady=(10, 20), padx=20)
        
        # --- SUB-SECCIÓN: FIJAS ---
        ctk.CTkLabel(frame_deps, text="Dependencias Fijas (Integridad del Sistema)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(0, 5))
        ctk.CTkLabel(frame_deps, text="Estas herramientas vienen incluidas por defecto en la versión Full del programa. Si alguna aparece como no detectada, te recomendamos descargar el último instalador 'DowP_vx.x.x_Full_setup.exe' desde nuestro repositorio oficial, o bien descargarlas gratis desde sus sitios web y extraerlas en la carpeta 'bin'.", font=ctk.CTkFont(size=12), text_color="gray50", justify="left", wraplength=600).pack(anchor="w", padx=20, pady=(0, 10))
        
        import webbrowser
        ctk.CTkButton(frame_deps, text="Descargar DowP Full (GitHub)", command=lambda: webbrowser.open("https://github.com/MarckDP/DowP/releases")).pack(anchor="w", padx=20, pady=(0, 15))
        
        # Frame contenedor para las fijas
        self.fixed_frame = ctk.CTkFrame(frame_deps, fg_color=("gray85", "gray20"))
        self.fixed_frame.pack(fill="x", padx=5)
        
        # Crear filas (Ghostscript, Inkscape)
        self._create_fixed_dependency_row(self.fixed_frame, "Ghostscript", "Motor de renderizado de vectores", "ghostscript", "https://ghostscript.com/releases/gsdnld.html")
        self._create_fixed_dependency_row(self.fixed_frame, "Inkscape", "Editor de gráficos vectoriales", "inkscape", "https://inkscape.org/release/1.4/windows/")

        self.sections["deps"] = frame_deps

        # ===== Sección: Modelos =====
        frame_models = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        ctk.CTkLabel(frame_models, text="Modelos de Inteligencia Artificial", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(frame_models, text="Gestiona los modelos de IA usados por las herramientas de imagen. Puedes descargar los que necesites, ver cuánto ocupan o eliminarlos para liberar espacio.", justify="left", wraplength=600, text_color="gray60").pack(anchor="w", pady=(0, 20))

        # -- Grupo: Eliminación de Fondo (Rembg) --
        ctk.CTkLabel(frame_models, text="Eliminación de Fondo (Rembg)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 8))
        self.rembg_models_frame = ctk.CTkFrame(frame_models, fg_color=("gray85", "gray20"))
        self.rembg_models_frame.pack(fill="x", pady=(0, 20), padx=5)
        self.model_rows = {}
        self._populate_rembg_model_rows()

        # -- Grupo: Motores de Reescalado (Upscaling) --
        ctk.CTkLabel(frame_models, text="Motores de Reescalado (Upscaling)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 8))
        self.upscaling_models_frame = ctk.CTkFrame(frame_models, fg_color=("gray85", "gray20"))
        self.upscaling_models_frame.pack(fill="x", pady=(0, 20), padx=5)
        self._populate_upscaling_model_rows()

        self.sections["models"] = frame_models
        # Mitigar glitch visual al hacer scroll: refrescar la ventana durante el scroll
        frame_models._scrollbar.bind("<B1-Motion>", lambda e: self.app.update_idletasks())
        frame_models.bind("<MouseWheel>", lambda e: self.app.after(10, self.app.update_idletasks))

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
            # Encabezado de familia
            header = ctk.CTkLabel(
                self.rembg_models_frame,
                text=family_name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="gray50"
            )
            header.pack(anchor="w", padx=15, pady=(12, 2))

            # Aviso especial para la familia RMBG 2.0
            if family_name == RMBG2_FAMILY:
                notice = (
                    "Los modelos de esta familia están sujetos a los términos de uso de BriaAI y "
                    "requieren descarga manual desde Hugging Face. Únicamente el modelo marcado como "
                    "'Automático' puede descargarse directamente desde DowP. Los demás abrirán la "
                    "página de descarga en el navegador; coloca el archivo .onnx descargado en la "
                    "carpeta mostrada al pulsar 'Carpeta'."
                )
                notice_frame = ctk.CTkFrame(self.rembg_models_frame, fg_color=("gray75", "gray30"))
                notice_frame.pack(fill="x", padx=15, pady=(0, 6), ipadx=8, ipady=6)
                ctk.CTkLabel(
                    notice_frame,
                    text=notice,
                    font=ctk.CTkFont(size=11),
                    text_color=("gray20", "gray80"),
                    justify="left",
                    wraplength=520
                ).pack(anchor="w", padx=8, pady=4)

            for model_name, model_info in models.items():
                row_key = f"rembg_{model_info['file']}"
                # Para RMBG 2.0 los modelos de HuggingFace usan 'Abrir Web' en lugar de 'Descargar'
                is_hf_manual = (
                    family_name == RMBG2_FAMILY and
                    model_name != RMBG2_AUTO_KEY
                )
                self._create_model_row(
                    parent=self.rembg_models_frame,
                    row_key=row_key,
                    display_name=model_name,
                    description=f"Archivo: {model_info['file']}",
                    model_info=model_info,
                    kind="rembg",
                    manual_web=is_hf_manual
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
                kind="upscaling"
            )

    def _create_model_row(self, parent, row_key, display_name, description, model_info, kind, manual_web=False):
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

        pct_lbl = ctk.CTkLabel(status_frame, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#1f6aa5")
        pct_lbl.pack(anchor="center")

        # -- Columna Derecha: Botones --
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=2, sticky="e", padx=(10, 0))

        dl_label = "Abrir Web" if manual_web else "Descargar"
        dl_btn = ctk.CTkButton(btn_frame, text=dl_label, width=100)
        dl_btn.pack(side="left", padx=2)

        folder_btn = ctk.CTkButton(btn_frame, text="Carpeta", width=80, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        folder_btn.pack(side="left", padx=2)

        del_btn = ctk.CTkButton(btn_frame, text="Eliminar", width=80, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
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
            size = os.path.getsize(path)
            row["status_lbl"].configure(text=self._format_size(size), text_color=("#2e7d32", "#66bb6a"))
            row["pct_lbl"].configure(text="")
            row["dl_btn"].configure(state="disabled", text="Instalado")
            row["del_btn"].configure(state="normal", fg_color="#c0392b", hover_color="#922b21", text_color="white", border_width=0)
        else:
            row["status_lbl"].configure(text="No descargado", text_color="gray50")
            row["pct_lbl"].configure(text="")
            row["dl_btn"].configure(state="normal", text="Descargar")
            row["del_btn"].configure(state="disabled", fg_color="transparent", hover_color=("gray70", "gray30"), text_color=("gray10", "gray90"), border_width=1)

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
        """Descarga y extrae un motor de upscaling (ZIP) en un hilo."""
        row = self.model_rows[row_key]
        row["dl_btn"].configure(state="disabled", text="Instalado")
        row["status_lbl"].configure(text="0%", text_color="#1f6aa5")
        row["pct_lbl"].configure(text="")

        def do_download():
            import zipfile, tempfile, time
            try:
                from main import UPSCALING_DIR
                tool_dir = os.path.join(UPSCALING_DIR, tool_info["folder"])
                os.makedirs(tool_dir, exist_ok=True)

                with requests.get(url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    last_ui_update = 0.0
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            tmp.write(chunk)
                            downloaded += len(chunk)
                            now = time.monotonic()
                            if total > 0 and now - last_ui_update >= 0.3:
                                last_ui_update = now
                                pct = int(downloaded / total * 100)
                                self.app.after(0, lambda p=pct: row["status_lbl"].configure(text=f"{p}%"))
                                size_lbl = f"{self._format_size(downloaded)} / {self._format_size(total)}"
                                self.app.after(0, lambda t=size_lbl: row["pct_lbl"].configure(text=t))
                    tmp.close()

                self.app.after(0, lambda: row["status_lbl"].configure(text="Extrayendo..."))
                with zipfile.ZipFile(tmp.name, "r") as zf:
                    members = zf.namelist()
                    root = members[0].split("/")[0] + "/" if "/" in members[0] else ""
                    for member in members:
                        target = member[len(root):] if root and member.startswith(root) else member
                        if not target:
                            continue
                        target_path = os.path.join(tool_dir, target)
                        if member.endswith("/"):
                            os.makedirs(target_path, exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            with zf.open(member) as src, open(target_path, "wb") as dst:
                                dst.write(src.read())
                os.unlink(tmp.name)
                self.app.after(0, lambda: self._refresh_model_row(row_key))
            except Exception as e:
                self.app.after(0, lambda: row["status_lbl"].configure(text=f"Error: {str(e)[:60]}", text_color="red"))
                self.app.after(0, lambda: row["dl_btn"].configure(state="normal", text="Reintentar"))

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

    def _create_dependency_row(self, parent, name, description, key):
        """Crea una fila para una dependencia actualizable."""
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=15, pady=10)
        
        # Configurar columnas: Info (peso 1), Progreso (peso 1), Botón (peso 0)
        row_frame.grid_columnconfigure(0, weight=2)
        row_frame.grid_columnconfigure(1, weight=2)
        row_frame.grid_columnconfigure(2, weight=0)
        
        # 1. Información (Izquierda)
        info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="w")
        
        name_label = ctk.CTkLabel(info_frame, text=name, font=ctk.CTkFont(size=14, weight="bold"))
        name_label.pack(anchor="w")
        
        version_label = ctk.CTkLabel(info_frame, text="Versión: Desconocida", font=ctk.CTkFont(size=11), text_color="gray50", wraplength=230, justify="left")
        version_label.pack(anchor="w")
        self.dep_labels[key] = version_label
        
        # 2. Progreso (Centro - Oculto por defecto)
        progress_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        
        status_label = ctk.CTkLabel(progress_frame, text="...", font=ctk.CTkFont(size=11), wraplength=180, justify="left")
        status_label.pack(anchor="w", pady=(0, 2))
        
        pbar = ctk.CTkProgressBar(progress_frame, width=150)
        pbar.set(0)
        pbar.pack(anchor="w")
        
        self.dep_progress[key] = {"frame": progress_frame, "label": status_label, "bar": pbar}
        # Nota: no usamos .grid() aún para que esté oculto
        
        # 3. Botón de Acción (Derecha)
        btn = ctk.CTkButton(row_frame, text="Buscar Actualización", width=140)
        btn.grid(row=0, column=2, sticky="e", padx=(10, 0))
        
        # Conectar acción según la dependencia
        if key == "ffmpeg":
            btn.configure(command=self.manual_ffmpeg_update_check)
        elif key == "deno":
            btn.configure(command=self.manual_deno_update_check)
        elif key == "poppler":
            btn.configure(command=self.manual_poppler_update_check)
            
        self.dep_buttons[key] = btn

    def _create_fixed_dependency_row(self, parent, name, description, key, url):
        """Crea una fila para una dependencia fija (comprobación de integridad)."""
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=15, pady=10)
        
        # Configurar columnas: Nombre (peso 2), Estado (peso 2), Botón (peso 0)
        row_frame.grid_columnconfigure(0, weight=2)
        row_frame.grid_columnconfigure(1, weight=2)
        row_frame.grid_columnconfigure(2, weight=0)
        
        # 1. Nombre y descripción (Izquierda)
        info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="w")
        
        name_label = ctk.CTkLabel(info_frame, text=name, font=ctk.CTkFont(size=14, weight="bold"))
        name_label.pack(anchor="w")
        
        desc_label = ctk.CTkLabel(info_frame, text=description, font=ctk.CTkFont(size=11), text_color="gray50", wraplength=180, justify="left")
        desc_label.pack(anchor="w")
        
        # 2. Estado (Centro)
        # Simulamos estado provisional. Luego se conectará a la lógica real.
        status_label = ctk.CTkLabel(row_frame, text="Estado: Calculando...", font=ctk.CTkFont(size=12, weight="bold"), wraplength=180, justify="left")
        status_label.grid(row=0, column=1, sticky="w", padx=10)
        self.dep_labels[key] = status_label
        
        # 3. Botón Manual (Derecha)
        import webbrowser
        btn = ctk.CTkButton(
            row_frame, 
            text="Sitio Web Oficial", 
            width=140, 
            fg_color="transparent", 
            border_width=1, 
            text_color=("gray10", "gray90"),
            command=lambda u=url: webbrowser.open(u)
        )
        btn.grid(row=0, column=2, sticky="e", padx=(10, 0))
            
        self.dep_buttons[key] = btn

    def select_section(self, section_name):
        """Muestra el frame de la sección elegida y oculta los demás. Resalta el botón."""
        
        # Ocultar todos los frames
        for frame in self.sections.values():
            frame.grid_forget()
            
        # Resaltar el botón seleccionado (efecto visual)
        for name, btn in self.menu_buttons.items():
            if name == section_name:
                # Color para el botón seleccionado
                btn.configure(fg_color=("gray75", "gray25")) 
            else:
                # Fondo transparente para los no seleccionados
                btn.configure(fg_color="transparent") 
        
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
                self.dep_progress[key]["frame"].grid(row=0, column=1, sticky="w", padx=10)
                self.dep_progress[key]["label"].configure(text=text)
                # Escalar valor de 0-100 a 0.0-1.0 para el widget
                normalized_value = max(0.0, min(1.0, value / 100.0))
                self.dep_progress[key]["bar"].set(normalized_value)

    def main_window_callback(self, method_name, *args):
        """Ejecuta de forma segura un método de la app principal si existe."""
        if hasattr(self.app, method_name):
            method = getattr(self.app, method_name)
            self.app.after(0, method, *args)
        else:
            print(f"ADVERTENCIA: La ventana principal no tiene el método {method_name}")

    def manual_ffmpeg_update_check(self):
        """Inicia una comprobación manual de la actualización de FFmpeg."""
        self.dep_buttons["ffmpeg"].configure(state="disabled", text="Buscando...")
        self.dep_labels["ffmpeg"].configure(text="Versión: Verificando...")
        
        import threading
        from src.core.setup import check_ffmpeg_status

        def check_task():
            status_info = check_ffmpeg_status(
                lambda text, val: self.update_setup_download_progress('ffmpeg', text, val)
            )
            self.main_window_callback('on_ffmpeg_check_complete', status_info)

        threading.Thread(target=check_task, daemon=True).start()

    def manual_deno_update_check(self):
        """Inicia una comprobación manual de la actualización de Deno."""
        self.dep_buttons["deno"].configure(state="disabled", text="Buscando...")
        self.dep_labels["deno"].configure(text="Versión: Verificando...")

        import threading
        from src.core.setup import check_deno_status

        def check_task():
            status_info = check_deno_status(
                lambda text, val: self.update_setup_download_progress('deno', text, val)
            )
            self.main_window_callback('on_deno_check_complete', status_info)

        threading.Thread(target=check_task, daemon=True).start()

    def manual_poppler_update_check(self):
        """Inicia una comprobación manual de la actualización de Poppler."""
        self.dep_buttons["poppler"].configure(state="disabled", text="Buscando...")
        self.dep_labels["poppler"].configure(text="Versión: Verificando...")

        import threading
        from src.core.setup import check_poppler_status

        def check_task():
            status_info = check_poppler_status(
                lambda text, val: self.update_setup_download_progress('poppler', text, val)
            )
            self.main_window_callback('on_poppler_check_complete', status_info)

        threading.Thread(target=check_task, daemon=True).start()

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
        if mode == "Archivo Manual...":
            self.manual_cookie_frame.pack(fill="x", pady=(5,0))
            self.browser_options_frame.pack_forget()
        elif mode == "Desde Navegador":
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack(fill="x", pady=(5,0))
        else:  # "No usar"
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack_forget()
            
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
