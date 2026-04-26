import sys
import os
import subprocess
import multiprocessing
import tempfile  
import atexit   
import tkinter as tk 
import pillow_avif

from tkinter import messagebox
from PIL import Image, ImageTk

APP_VERSION = "1.4.1"

# ==============================================================================
# 🔕 PARCHE GLOBAL: OCULTAR CONSOLAS (WINDOWS)
# ==============================================================================
# Este parche intercepta todas las llamadas a subprocesos (Ghostscript, Poppler, etc.)
# y les inyecta la bandera CREATE_NO_WINDOW. Esto evita que salten ventanas de CMD
# negras en la versión compilada (.exe), incluso desde librerías externas.
if sys.platform == "win32":
    import subprocess
    # Evitar aplicar el parche múltiples veces si se importa main.py de nuevo
    if not hasattr(subprocess.Popen, "_is_patched"):
        _original_popen = subprocess.Popen
        class _PatchedPopen(_original_popen):
            _is_patched = True
            def __init__(self, *args, **kwargs):
                # 🔍 INSPECCIÓN DE COMANDO:
                # Obtenemos el comando (ya sea por args posicionales o por keyword)
                cmd = args[0] if args else kwargs.get('args', "")
                cmd_str = ""
                if isinstance(cmd, (list, tuple)):
                    cmd_str = " ".join(map(str, cmd)).lower()
                elif isinstance(cmd, str):
                    cmd_str = cmd.lower()

                # 🚫 Herramientas que SÍ queremos ver (excluidas del parche de ocultación)
                # Esto permite que ffmpeg y yt-dlp muestren su progreso en consola si es necesario.
                exclude_list = ["ffmpeg", "yt-dlp", "ffprobe"]
                is_excluded = any(tool in cmd_str for tool in exclude_list)

                # Inyectar bandera de ocultación SOLO si no está excluido y no tiene flags
                if not is_excluded and 'creationflags' not in kwargs:
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                
                super().__init__(*args, **kwargs)
        
        subprocess.Popen = _PatchedPopen
        print("INFO: Parche de ocultación selectiva aplicado (FFmpeg/yt-dlp visibles).")
# ==============================================================================

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
FFMPEG_BIN_DIR = os.path.join(BIN_DIR, "ffmpeg")
DENO_BIN_DIR = os.path.join(BIN_DIR, "deno")
POPPLER_BIN_DIR = os.path.join(BIN_DIR, "poppler")
INKSCAPE_BIN_DIR = os.path.join(BIN_DIR, "inkscape")
GHOSTSCRIPT_BIN_DIR = os.path.join(BIN_DIR, "ghostscript")

# --- NUEVO: Rutas para Modelos de IA ---
MODELS_DIR = os.path.join(BIN_DIR, "models")
REMBG_MODELS_DIR = os.path.join(MODELS_DIR, "rembg")
UPSCALING_DIR = os.path.join(MODELS_DIR, "upscaling")

# Configurar variable de entorno para que rembg use nuestra carpeta
os.environ["U2NET_HOME"] = REMBG_MODELS_DIR

class SplashScreen:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True) # Quita bordes
        
        # Configuración visual
        bg_color = "#2B2B2B"
        text_color = "#FFFFFF"
        self.root.configure(bg=bg_color)
        
        # Dimensiones
        width = 350  # Un poco más ancha para que quepa el icono y la versión
        height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # --- CARGAR ICONO ---
        self.tk_image = None
        try:
            # Buscar la ruta del icono (funciona en dev y exe)
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "DowP-icon.ico")
            
            if os.path.exists(icon_path):
                # Cargar y redimensionar con Pillow (Alta calidad)
                pil_img = Image.open(icon_path).resize((40, 40), Image.Resampling.LANCZOS)
                self.tk_image = ImageTk.PhotoImage(pil_img)
                
                # También ponerlo en la barra de tareas (aunque no tenga borde)
                self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"No se pudo cargar el icono en Splash: {e}")

        # --- ETIQUETA PRINCIPAL (Icono + Texto) ---
        main_label = tk.Label(
            self.root, 
            text=f"Iniciando DowP v{APP_VERSION}", # <--- Texto con versión
            image=self.tk_image,                   # <--- Imagen
            compound="left",                       # <--- Imagen a la IZQUIERDA del texto
            padx=15,                               # Espacio extra
            font=("Segoe UI", 14, "bold"),
            bg=bg_color, 
            fg=text_color
        )
        main_label.pack(expand=True, fill="both", pady=(15, 0))
        
        # Etiqueta de Estado
        self.status_label = tk.Label(
            self.root, 
            text="Cargando...", 
            font=("Segoe UI", 9),
            bg=bg_color, 
            fg="#AAAAAA"
        )
        self.status_label.pack(side="bottom", pady=(0, 15))
        
        self.root.update()

    def update_status(self, text):
        if self.root:
            self.status_label.config(text=text)
            self.root.update()

    def destroy(self):
        if self.root:
            self.root.destroy()
            self.root = None
class SingleInstance:
    def __init__(self):
        self.lockfile = os.path.join(tempfile.gettempdir(), 'dowp.lock')
        if os.path.exists(self.lockfile):
            try:
                with open(self.lockfile, 'r') as f:
                    pid = int(f.read())
                if self._is_pid_running(pid):
                    messagebox.showwarning("DowP ya está abierto",
                                           f"Ya hay una instancia de DowP en ejecución (Proceso ID: {pid}).\n\n"
                                           "Por favor, busca la ventana existente.")
                    sys.exit(1)
                else:
                    print("INFO: Se encontró un archivo de cerrojo obsoleto. Eliminándolo.")
                    os.remove(self.lockfile)
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo verificar el archivo de cerrojo. Eliminándolo. ({e})")
                try:
                    os.remove(self.lockfile)
                except OSError:
                    pass
        with open(self.lockfile, 'w') as f:
            f.write(str(os.getpid()))
        atexit.register(self.cleanup)

    def _is_pid_running(self, pid):
        """
        Comprueba si un proceso con un PID dado está corriendo Y si
        coincide con el nombre de este ejecutable.
        """
        try:
            if sys.platform == "win32":
                # Obtenemos el nombre del ejecutable actual (ej: "dowp.exe" o "python.exe")
                image_name = os.path.basename(sys.executable)
                
                # Comando de tasklist MEJORADO:
                # Filtra por PID Y por nombre de imagen.
                command = ['tasklist', '/fi', f'PID eq {pid}', '/fi', f'IMAGENAME eq {image_name}']
                
                # Usamos creationflags=0x08000000 para (CREATE_NO_WINDOW) y evitar que aparezca una consola
                output = subprocess.check_output(command, 
                                                 stderr=subprocess.STDOUT, 
                                                 text=True, 
                                                 creationflags=0x08000000)
                
                # Si el proceso (PID + Nombre) se encuentra, el PID estará en la salida.
                return str(pid) in output
            else: 
                try:
                    # 1. Comprobación rápida de existencia del PID
                    os.kill(pid, 0)
                    
                    # 2. Si existe, comprobar la identidad del proceso
                    expected_name = os.path.basename(sys.executable)
                    command = ['ps', '-p', str(pid), '-o', 'comm=']
                    
                    output = subprocess.check_output(command, 
                                                     stderr=subprocess.STDOUT, 
                                                     text=True)
                    
                    process_name = output.strip()
                    
                    # Compara el nombre del proceso (ej: 'python3' o 'dowp')
                    return process_name == expected_name
                    
                except (OSError, subprocess.CalledProcessError):
                    # OSError: "No such process" (el PID no existe)
                    # CalledProcessError: 'ps' falló
                    return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            # CalledProcessError: Ocurre si el PID no existe (en Windows)
            # FileNotFoundError: tasklist/ps no encontrado (muy raro)
            return False
        except Exception as e:
            # Captura cualquier otro error inesperado
            print(f"Error inesperado en _is_pid_running: {e}")
            return False
        
    def cleanup(self):
        """Borra el archivo de cerrojo al cerrar."""
        try:
            if os.path.exists(self.lockfile):
                os.remove(self.lockfile)
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo limpiar el archivo de cerrojo: {e}")

if __name__ == "__main__":
    multiprocessing.freeze_support()

    # --- MANEJADOR DE CLI PARA YT-DLP (EVITA DOBLE INSTANCIA AL USAR CONSOLA) ---
    if len(sys.argv) > 1 and sys.argv[1].endswith("yt-dlp.zip"):
        yt_dlp_zip = sys.argv[1]
        if os.path.exists(yt_dlp_zip):
            if yt_dlp_zip not in sys.path:
                sys.path.insert(0, yt_dlp_zip)
            try:
                import yt_dlp
                yt_dlp.main(sys.argv[2:])
                sys.exit(0)
            except Exception as e:
                print(f"ERROR: Falló la ejecución directa de yt-dlp: {e}")
                sys.exit(1)

    # 1. Mostrar Splash INMEDIATAMENTE
    splash = SplashScreen()
    splash.update_status("Verificando instancia única...")

    SingleInstance()

    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    # --- INYECTAR YT-DLP DESDE EL ZIP EXTERNO (SI EXISTE) ---
    yt_dlp_zip = os.path.join(BIN_DIR, "ytdlp", "yt-dlp.zip")
    
    if os.path.exists(yt_dlp_zip) and yt_dlp_zip not in sys.path:
        # Lo insertamos primero para que Python le dé prioridad sobre la librería instalada
        sys.path.insert(0, yt_dlp_zip)
        print(f"INFO: Cargando yt-dlp desde el archivo ZIP externo: {yt_dlp_zip}")
    else:
        print("INFO: No se encontró yt-dlp.zip en bin/. Usando librería compilada (o del entorno virtual).")

    # 2. Actualizar estado mientras configuras el entorno
    splash.update_status("Configurando entorno y rutas...")

    # Añadir el directorio 'bin' principal
    if os.path.isdir(BIN_DIR) and BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = BIN_DIR + os.pathsep + os.environ['PATH']
    
    # Añadir el subdirectorio de FFmpeg
    if os.path.isdir(FFMPEG_BIN_DIR) and FFMPEG_BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = FFMPEG_BIN_DIR + os.pathsep + os.environ['PATH']

    # Añadir el subdirectorio de Deno 
    if os.path.isdir(DENO_BIN_DIR) and DENO_BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = DENO_BIN_DIR + os.pathsep + os.environ['PATH']

    # Añadir el subdirectorio de Poppler
    if os.path.isdir(POPPLER_BIN_DIR) and POPPLER_BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = POPPLER_BIN_DIR + os.pathsep + os.environ['PATH']

    # Añadir Inkscape al PATH (para tu instalación manual)
    if os.path.isdir(INKSCAPE_BIN_DIR) and INKSCAPE_BIN_DIR not in os.environ['PATH']:
        print(f"INFO: Añadiendo Inkscape al PATH: {INKSCAPE_BIN_DIR}")
        os.environ['PATH'] = INKSCAPE_BIN_DIR + os.pathsep + os.environ['PATH']

    # Añadir el subdirectorio de Ghostscript (para .eps y .ai)
    if os.path.isdir(GHOSTSCRIPT_BIN_DIR) and GHOSTSCRIPT_BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = GHOSTSCRIPT_BIN_DIR + os.pathsep + os.environ['PATH']

    print("Iniciando la aplicación...")
    launch_target = sys.argv[1] if len(sys.argv) > 1 else None
    
    # 3. Actualizar justo antes de la carga pesada
    splash.update_status("Cargando módulos e interfaz...")

    # --- NUEVO: CARGAR TEMA (Acento) ANTES DE LA UI ---
    _theme_data = {} # 🎨 Almacena los datos crudos del tema para colores personalizados
    _theme_warnings = [] # ⚠️ Lista de advertencias sobre el tema cargado
    try:
        import json
        import customtkinter as ctk
        _appdata = os.getenv('APPDATA') or os.path.expanduser('~\\AppData\\Roaming')
        _settings_path = os.path.join(_appdata, 'DowP', "app_settings.json")
        _theme = "blue"
        _appearance = "System"
        if os.path.exists(_settings_path):
            with open(_settings_path, 'r') as f:
                _settings = json.load(f)
                _theme = _settings.get("selected_theme_accent", "blue")
                _appearance = _settings.get("appearance_mode", "System")
        
        ctk.set_appearance_mode(_appearance)
        
        # ✅ SOPORTE PARA TEMAS PERSONALIZADOS DINÁMICOS
        # 1. Rutas de búsqueda (Usuario e Internas)
        _base_path = getattr(sys, '_MEIPASS', PROJECT_ROOT)
        _user_themes_dir = os.path.join(_appdata, 'DowP', "themes")
        _internal_themes_dir = os.path.join(_base_path, "src", "gui", "themes")
        
        # 2. Buscar si el tema seleccionado corresponde a un archivo JSON
        # Prioridad: Usuario > Interno
        _found_path = None
        for _dir in [_user_themes_dir, _internal_themes_dir]:
            _json_path = os.path.join(_dir, f"{_theme}.json")
            if os.path.exists(_json_path):
                _found_path = _json_path
                break
        
        if _found_path:
            # --- NUEVO: COMPLETADOR Y SANITIZADOR DE TEMAS ---
            try:
                # 1. Cargar tema base (Green) como red de seguridad para completar claves faltantes
                _base_theme_path = os.path.join(_internal_themes_dir, "shrek.json")
                _final_theme_data = {}
                if os.path.exists(_base_theme_path):
                    with open(_base_theme_path, 'r', encoding='utf-8') as f:
                        _final_theme_data = json.load(f)
                
                # 2. Cargar el tema del usuario/seleccionado
                with open(_found_path, 'r', encoding='utf-8') as f:
                    _user_theme_data = json.load(f)
                
                # 3. Mezclar profundamente (Deep Update) para evitar KeyError en CTK
                def _deep_update(base, over):
                    for k, v in over.items():
                        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                            _deep_update(base[k], v)
                        else:
                            base[k] = v
                
                # Detectar claves faltantes antes de mezclar para informar al usuario
                _missing = [k for k in _final_theme_data if k not in _user_theme_data and not k.startswith("_") and k != "CustomColors"]
                if _missing:
                    print(f"⚠️ ADVERTENCIA: El tema '{_theme}' está incompleto.")
                    print(f"   Claves faltantes: {', '.join(_missing)}")
                    _theme_warnings.append(f"El tema '{_theme}' está incompleto. Faltan {len(_missing)} secciones técnicas (ej: {', '.join(_missing[:3])}). Se usaron valores por defecto.")

                _deep_update(_final_theme_data, _user_theme_data)
                _theme_data = _final_theme_data

                # 4. Función recursiva para limpiar "transparent" de lugares prohibidos
                def _sanitize_node(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if "border_color" in k:
                                if isinstance(v, list):
                                    obj[k] = [c if c != "transparent" else "gray65" for c in v]
                                elif v == "transparent":
                                    obj[k] = "gray65"
                            else:
                                _sanitize_node(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _sanitize_node(item)

                _sanitize_node(_theme_data)
                
                # 5. Aplanar CTkFont por plataforma (CTk espera family/size/weight directo)
                # Nuestros temas usan: CTkFont → {Windows: {family, size, weight}, macOS: {...}}
                if "CTkFont" in _theme_data:
                    _font_data = _theme_data["CTkFont"]
                    import platform
                    _os_name = platform.system()  # "Windows", "Darwin", "Linux"
                    _os_key_map = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
                    _os_key = _os_key_map.get(_os_name, "Windows")
                    
                    # Si tiene la estructura anidada por SO, aplanarla
                    if _os_key in _font_data and isinstance(_font_data[_os_key], dict):
                        _theme_data["CTkFont"] = _font_data[_os_key]
                    elif "family" not in _font_data:
                        # Intentar con cualquier clave de SO disponible
                        for _try_key in ["Windows", "macOS", "Linux"]:
                            if _try_key in _font_data and isinstance(_font_data[_try_key], dict):
                                _theme_data["CTkFont"] = _font_data[_try_key]
                                break
                
                # 6. Guardar en un archivo temporal seguro para cargar
                _temp_theme_path = os.path.join(_user_themes_dir, ".active_theme_sanitized.json")
                with open(_temp_theme_path, 'w', encoding='utf-8') as f:
                    json.dump(_theme_data, f)
                
                _theme = _temp_theme_path
                print(f"INFO: Tema visual completado y sanitizado desde: {_found_path}")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo procesar el tema, intentando carga normal: {e}")
                _theme = _found_path
        
        # Si no se encontró el archivo del tema personalizado, volvemos al azul por defecto
        # para evitar errores de pre-carga en CustomTkinter.
        if not _found_path and _theme not in ["blue", "dark-blue", "green"]:
            _theme = "blue"

        ctk.set_default_color_theme(_theme)
        print(f"INFO: Tema de acento pre-cargado.")
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo pre-cargar el tema: {e}")
        import customtkinter as ctk
        ctk.set_default_color_theme("blue")
    
    # Aquí ocurre la "pausa" de carga, pero el usuario verá la ventana flotante
    from src.gui.main_window import MainWindow 
    
    # 4. Pasar la referencia 'splash' a la ventana principal
    app = MainWindow(launch_target=launch_target, 
                     project_root=PROJECT_ROOT, 
                     poppler_path=POPPLER_BIN_DIR,
                     inkscape_path=INKSCAPE_BIN_DIR,
                     splash_screen=splash,
                     app_version=APP_VERSION,
                     theme_data=_theme_data,
                     theme_warnings=_theme_warnings)
    
    app.mainloop()