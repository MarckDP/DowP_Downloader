from tkinter import messagebox
import tkinter
import customtkinter as ctk
from customtkinter import filedialog
from PIL import Image
import requests
from io import BytesIO
import gc
import threading
import os
import re
import sys
from pathlib import Path
import subprocess
import json
import time
import shutil
import platform

from datetime import datetime, timedelta
from src.core.downloader import get_video_info, download_media
from src.core.processor import FFmpegProcessor, CODEC_PROFILES
from src.core.exceptions import UserCancelledError, LocalRecodeFailedError
from src.core.processor import clean_and_convert_vtt_to_srt

SETTINGS_FILE = "app_settings.json"

class ConflictDialog(ctk.CTkToplevel):

    def __init__(self, master, filename):
        super().__init__(master)
        self.title("Conflicto de Archivo")
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()
        self.geometry("500x180")
        self.resizable(False, False)
        self.result = "cancel"
        main_label = ctk.CTkLabel(self, text=f"El archivo '{filename}' ya existe en la carpeta de destino.", font=ctk.CTkFont(size=14), wraplength=460)
        main_label.pack(pady=(20, 10), padx=20)
        question_label = ctk.CTkLabel(self, text="¿Qué deseas hacer?")
        question_label.pack(pady=5, padx=20)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=15, fill="x", expand=True)
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        overwrite_btn = ctk.CTkButton(button_frame, text="Sobrescribir", command=lambda: self.set_result("overwrite"))
        rename_btn = ctk.CTkButton(button_frame, text="Conservar Ambos", command=lambda: self.set_result("rename"))
        cancel_btn = ctk.CTkButton(button_frame, text="Cancelar", fg_color="red", hover_color="#990000", command=lambda: self.set_result("cancel"))
        overwrite_btn.grid(row=0, column=0, padx=10, sticky="ew")
        rename_btn.grid(row=0, column=1, padx=10, sticky="ew")
        cancel_btn.grid(row=0, column=2, padx=10, sticky="ew")

    def set_result(self, result):
        self.result = result
        self.destroy()

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

    LANG_CODE_MAP = {
        # --- Orden de Popularidad Original (Mantenido) ---
        "es": "Español",
        "es-419": "Español (Latinoamérica)",
        "es-es": "Español (España)",
        "es_la": "Español (Latinoamérica)", 
        "en": "Inglés",
        "en-us": "Inglés (EE.UU.)",
        "en-gb": "Inglés (Reino Unido)",
        "en-orig": "Inglés (Original)",
        "ja": "Japonés",
        "fr": "Francés",
        "de": "Alemán",
        "it": "Italiano",
        "pt": "Portugués",
        "pt-br": "Portugués (Brasil)",
        "pt-pt": "Portugués (Portugal)",
        "ru": "Ruso",
        "zh": "Chino",
        "zh-cn": "Chino (Simplificado)",
        "zh-tw": "Chino (Tradicional)",
        "zh-hans": "Chino (Simplificado)", 
        "zh-hant": "Chino (Tradicional)", 
        "ko": "Coreano",
        "ar": "Árabe",
        "hi": "Hindi",
        "iw": "Hebreo (código antiguo)", 
        "he": "Hebreo",
        "fil": "Filipino", 
        "aa": "Afar",
        "ab": "Abjasio",
        "ae": "Avéstico",
        "af": "Afrikáans",
        "ak": "Akán",
        "am": "Amárico",
        "an": "Aragonés",
        "as": "Asamés",
        "av": "Avar",
        "ay": "Aimara",
        "az": "Azerí",
        "ba": "Baskir",
        "be": "Bielorruso",
        "bg": "Búlgaro",
        "bh": "Bhojpuri",
        "bho": "Bhojpuri", 
        "bi": "Bislama",
        "bm": "Bambara",
        "bn": "Bengalí",
        "bo": "Tibetano",
        "br": "Bretón",
        "bs": "Bosnio",
        "ca": "Catalán",
        "ce": "Checheno",
        "ceb": "Cebuano", 
        "ch": "Chamorro",
        "co": "Corso",
        "cr": "Cree",
        "cs": "Checo",
        "cu": "Eslavo eclesiástico",
        "cv": "Chuvash",
        "cy": "Galés",
        "da": "Danés",
        "dv": "Divehi",
        "dz": "Dzongkha",
        "ee": "Ewe",
        "el": "Griego",
        "eo": "Esperanto",
        "et": "Estonio",
        "eu": "Euskera",
        "fa": "Persa",
        "ff": "Fula",
        "fi": "Finlandés",
        "fj": "Fiyiano",
        "fo": "Feroés",
        "fy": "Frisón occidental",
        "ga": "Irlandés",
        "gd": "Gaélico escocés",
        "gl": "Gallego",
        "gn": "Guaraní",
        "gu": "Guyaratí",
        "gv": "Manés",
        "ha": "Hausa",
        "ht": "Haitiano",
        "hu": "Húngaro",
        "hy": "Armenio",
        "hz": "Herero",
        "ia": "Interlingua",
        "id": "Indonesio",
        "ie": "Interlingue",
        "ig": "Igbo",
        "ii": "Yi de Sichuán",
        "ik": "Inupiaq",
        "io": "Ido",
        "is": "Islandés",
        "iu": "Inuktitut",
        "jv": "Javanés",
        "ka": "Georgiano",
        "kg": "Kongo",
        "ki": "Kikuyu",
        "kj": "Kuanyama",
        "kk": "Kazajo",
        "kl": "Groenlandés",
        "km": "Jemer",
        "kn": "Canarés",
        "kr": "Kanuri",
        "ks": "Cachemiro",
        "ku": "Kurdo",
        "kv": "Komi",
        "kw": "Córnico",
        "ky": "Kirguís",
        "la": "Latín",
        "lb": "Luxemburgués",
        "lg": "Ganda",
        "li": "Limburgués",
        "ln": "Lingala",
        "lo": "Lao",
        "lt": "Lituano",
        "lu": "Luba-katanga",
        "lv": "Letón",
        "mg": "Malgache",
        "mh": "Marshalés",
        "mi": "Maorí",
        "mk": "Macedonio",
        "ml": "Malayalam",
        "mn": "Mongol",
        "mr": "Maratí",
        "ms": "Malayo",
        "mt": "Maltés",
        "my": "Birmano",
        "na": "Nauruano",
        "nb": "Noruego bokmål",
        "nd": "Ndebele del norte",
        "ne": "Nepalí",
        "ng": "Ndonga",
        "nl": "Neerlandés",
        "nn": "Noruego nynorsk",
        "no": "Noruego",
        "nr": "Ndebele del sur",
        "nv": "Navajo",
        "ny": "Chichewa",
        "oc": "Occitano",
        "oj": "Ojibwa",
        "om": "Oromo",
        "or": "Oriya",
        "os": "Osético",
        "pa": "Panyabí",
        "pi": "Pali",
        "pl": "Polaco",
        "ps": "Pastún",
        "qu": "Quechua",
        "rm": "Romanche",
        "rn": "Kirundi",
        "ro": "Rumano",
        "rw": "Kinyarwanda",
        "sa": "Sánscrito",
        "sc": "Sardo",
        "sd": "Sindhi",
        "se": "Sami septentrional",
        "sg": "Sango",
        "si": "Cingalés",
        "sk": "Eslovaco",
        "sl": "Esloveno",
        "sm": "Samoano",
        "sn": "Shona",
        "so": "Somalí",
        "sq": "Albanés",
        "sr": "Serbio",
        "ss": "Suazi",
        "st": "Sesotho",
        "su": "Sundanés",
        "sv": "Sueco",
        "sw": "Suajili",
        "ta": "Tamil",
        "te": "Telugu",
        "tg": "Tayiko",
        "th": "Tailandés",
        "ti": "Tigriña",
        "tk": "Turcomano",
        "tl": "Tagalo",
        "tn": "Setsuana",
        "to": "Tongano",
        "tr": "Turco",
        "ts": "Tsonga",
        "tt": "Tártaro",
        "tw": "Twi",
        "ty": "Tahitiano",
        "ug": "Uigur",
        "uk": "Ucraniano",
        "ur": "Urdu",
        "uz": "Uzbeko",
        "ve": "Venda",
        "vi": "Vietnamita",
        "vo": "Volapük",
        "wa": "Valón",
        "wo": "Wolof",
        "xh": "Xhosa",
        "yi": "Yidis",
        "yo": "Yoruba",
        "za": "Zhuang",
        "zu": "Zulú",
        "und": "No especificado",
        "alb-al": "Albanés (Albania)",
        "ara-sa": "Árabe (Arabia Saudita)",
        "aze-az": "Azerí (Azerbaiyán)",
        "ben-bd": "Bengalí (Bangladesh)",
        "bul-bg": "Búlgaro (Bulgaria)",
        "cat-es": "Catalán (España)",
        "ces-cz": "Checo (República Checa)",
        "cmn-hans-cn": "Chino Mandarín (Simplificado, China)",
        "cmn-hant-cn": "Chino Mandarín (Tradicional, China)",
        "crs": "Francés criollo seselwa",
        "dan-dk": "Danés (Dinamarca)",
        "deu-de": "Alemán (Alemania)",
        "ell-gr": "Griego (Grecia)",
        "est-ee": "Estonio (Estonia)",
        "fil-ph": "Filipino (Filipinas)",
        "fin-fi": "Finlandés (Finlandia)",
        "fra-fr": "Francés (Francia)",
        "gaa": "Ga",
        "gle-ie": "Irlandés (Irlanda)",
        "haw": "Hawaiano",
        "heb-il": "Hebreo (Israel)",
        "hin-in": "Hindi (India)",
        "hmn": "Hmong",
        "hrv-hr": "Croata (Croacia)",
        "hun-hu": "Húngaro (Hungría)",
        "ind-id": "Indonesio (Indonesia)",
        "isl-is": "Islandés (Islandia)",
        "ita-it": "Italiano (Italia)",
        "jav-id": "Javanés (Indonesia)",
        "jpn-jp": "Japonés (Japón)",
        "kaz-kz": "Kazajo (Kazajistán)",
        "kha": "Khasi",
        "khm-kh": "Jemer (Camboya)",
        "kor-kr": "Coreano (Corea del Sur)",
        "kri": "Krio",
        "lav-lv": "Letón (Letonia)",
        "lit-lt": "Lituano (Lituania)",
        "lua": "Luba-Lulua",
        "luo": "Luo",
        "mfe": "Morisyen",
        "msa-my": "Malayo (Malasia)",
        "mya-mm": "Birmano (Myanmar)",
        "new": "Newari",
        "nld-nl": "Neerlandés (Países Bajos)",
        "nob-no": "Noruego Bokmål (Noruega)",
        "nso": "Sotho del norte",
        "pam": "Pampanga",
        "pol-pl": "Polaco (Polonia)",
        "por-pt": "Portugués (Portugal)",
        "ron-ro": "Rumano (Rumania)",
        "rus-ru": "Ruso (Rusia)",
        "slk-sk": "Eslovaco (Eslovaquia)",
        "slv-si": "Esloveno (Eslovenia)",
        "spa-es": "Español (España)",
        "swa-sw": "Suajili", 
        "swe-se": "Sueco (Suecia)",
        "tha-th": "Tailandés (Tailandia)",
        "tum": "Tumbuka",
        "tur-tr": "Turco (Turquía)",
        "ukr-ua": "Ucraniano (Ucrania)",
        "urd-pk": "Urdu (Pakistán)",
        "uzb-uz": "Uzbeko (Uzbekistán)",
        "vie-vn": "Vietnamita (Vietnam)",
        "war": "Waray",
        # --- Alias de 3 letras de TikTok añadidos para compatibilidad ---
        "alb": "Albanés",
        "ara": "Árabe",
        "aze": "Azerí",
        "ben": "Bengalí",
        "bul": "Búlgaro",
        "cat": "Catalán",
        "ces": "Checo",
        "cmn": "Chino Mandarín",
        "dan": "Danés",
        "deu": "Alemán",
        "ell": "Griego",
        "est": "Estonio",
        "fin": "Finlandés",
        "fra": "Francés",
        "gle": "Irlandés",
        "heb": "Hebreo",
        "hin": "Hindi",
        "hrv": "Croata",
        "hun": "Húngaro",
        "ind": "Indonesio",
        "isl": "Islandés",
        "ita": "Italiano",
        "jav": "Javanés",
        "jpn": "Japonés",
        "kaz": "Kazajo",
        "khm": "Jemer",
        "kor": "Coreano",
        "lav": "Letón",
        "lit": "Lituano",
        "msa": "Malayo",
        "mya": "Birmano",
        "nld": "Neerlandés",
        "nob": "Noruego Bokmål",
        "pol": "Polaco",
        "por": "Portugués",
        "ron": "Rumano",
        "rus": "Ruso",
        "slk": "Eslovaco",
        "slv": "Esloveno",
        "spa": "Español",
        "swe": "Sueco",
        "swa": "Suajili",
        "tha": "Tailandés",
        "tur": "Turco",
        "ukr": "Ucraniano",
        "urd": "Urdu",
        "uzb": "Uzbeko",
        "vie": "Vietnamita",
    }

    LANGUAGE_ORDER = {
    'es-419': 0,   # Español LATAM
    'es-es': 1,    # Español España
    'es': 2,       # Español general
    'en': 3,       # Inglés
    'ja': 4,       # Japonés 
    'fr': 5,       # Francés 
    'de': 6,       # Alemán 
    'pt': 7,       # Portugués
    'it': 8,       # Italiano
    'zh': 9,       # Chino
    'ko': 10,      # Coreano
    'ru': 11,      # Ruso
    'ar': 12,      # Árabe
    'hi': 13,      # Hindi
    'vi': 14,      # Vietnamita
    'th': 15,      # Tailandés
    'pl': 16,      # Polaco
    'id': 17,      # Indonesio
    'tr': 18,      # Turco
    'bn': 19,      # Bengalí
    'ta': 20,      # Tamil
    'te': 21,      # Telugu
    'pa': 22,      # Punjabi
    'mr': 23,      # Marathi
    'ca': 24,      # Catalán
    'gl': 25,      # Gallego
    'eu': 26,      # Euskera
    'und': 27,     # Indefinido
}

    DEFAULT_PRIORITY = 99 
    SLOW_FORMAT_CRITERIA = {
        "video_codecs": ["av01", "vp9", "hevc"], 
        "min_height_for_slow": 2160,             
        "min_fps_for_slow": 50                   
    }

    EDITOR_FRIENDLY_CRITERIA = {
        "compatible_vcodecs": ["avc1", "h264", "prores", "dnxhd", "cfhd"],
        "compatible_acodecs": ["aac", "mp4a", "pcm_s16le", "pcm_s24le", "mp3"],
        "compatible_exts": ["mp4", "mov"],
    }

    COMPATIBILITY_RULES = {
        ".mov": {
            "video": ["prores_aw", "prores_ks", "dnxhd", "cfhd", "qtrle", "hap", "h264_videotoolbox", "libx264"],
            "audio": ["pcm_s16le", "pcm_s24le", "aac", "alac"]
        },
        ".mp4": {
            "video": ["libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_amf", "hevc_amf", "av1_nvenc", "av1_amf", "h264_qsv", "hevc_qsv", "av1_qsv", "vp9_qsv"],
            "audio": ["aac", "mp3", "ac3", "opus"]
        },
        ".mkv": {
            "video": ["libx264", "libx265", "libvpx", "libvpx-vp9", "libaom-av1", "h264_nvenc", "hevc_nvenc", "av1_nvenc"],
            "audio": ["aac", "mp3", "opus", "flac", "libvorbis", "ac3", "pcm_s16le"]
        },
        ".webm": { "video": ["libvpx", "libvpx-vp9", "libaom-av1"], "audio": ["libopus", "libvorbis"] },
        ".mxf": { "video": ["mpeg2video", "dnxhd"], "audio": ["pcm_s16le", "pcm_s24le"] },
        ".flac": { "video": [], "audio": ["flac"] },
        ".mp3": { "video": [], "audio": ["libmp3lame"] },
        ".m4a": { "video": [], "audio": ["aac", "alac"] },
        ".opus": { "video": [], "audio": ["libopus"] },
        ".wav": { "video": [], "audio": ["pcm_s16le", "pcm_s24le"] }
    }

    def __init__(self):

        super().__init__()
        self.is_shutting_down = False
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.title("DowP")
        self.geometry("835x900")
        self.is_updating_dimension = False
        self.current_aspect_ratio = None
        self.minsize(835, 900)
        ctk.set_appearance_mode("Dark")
        self.video_formats = {}
        self.audio_formats = {}
        self.subtitle_formats = {} 
        self.local_file_path = None
        self.thumbnail_label = None
        self.pil_image = None
        self.last_download_path = None
        self.video_duration = 0
        self.video_id = None
        self.analysis_cache = {} 
        self.CACHE_TTL = 300
        self.active_subprocess_pid = None 
        self.cancellation_event = threading.Event()
        self.active_operation_thread = None
        self.recode_settings = {}
        self.all_subtitles = {}
        self.current_subtitle_map = {}
        self.ui_request_event = threading.Event()
        self.ui_request_data = {}
        self.ui_response_event = threading.Event()
        self.ui_response_data = {}
        self.recode_compatibility_status = "valid"
        self.original_analyze_text = "Analizar"
        self.original_analyze_command = self.start_analysis_thread
        self.original_analyze_fg_color = None
        self.original_download_text = "Iniciar Descarga"
        self.original_download_command = self.start_download_thread
        self.original_download_fg_color = None
        self.default_download_path = ""
        self.cookies_path = ""
        self.cookies_mode_saved = "No usar"
        self.selected_browser_saved = "chrome"
        self.browser_profile_saved = ""
        self.auto_download_subtitle_saved = False
        self.ffmpeg_update_snooze_until = None
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
                    self.auto_download_subtitle_saved = settings.get("auto_download_subtitle", False)
                    snooze_str = settings.get("ffmpeg_update_snooze_until")
                    if snooze_str:
                        self.ffmpeg_update_snooze_until = datetime.fromisoformat(snooze_str)
                    self.recode_settings = settings.get("recode_settings", {})
                print(f"DEBUG: Configuración cargada exitosamente.")
            else:
                print("DEBUG: Archivo de configuración no encontrado. Usando valores por defecto.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: Fallo al cargar configuración: {e}")
            pass
        self.ffmpeg_processor = FFmpegProcessor()
        self.create_widgets()
        self.run_initial_setup()

    def create_entry_context_menu(self, widget):
        """Crea y muestra un menú contextual para un widget de entrada de texto."""
        menu = tkinter.Menu(self, tearoff=0)
        def cut_text():
            widget.event_generate("<<Copy>>")
            if widget.select_present():
                widget.delete("sel.first", "sel.last")
        def paste_text():
            if widget.select_present():
                widget.delete("sel.first", "sel.last")
            try:
                widget.insert("insert", self.clipboard_get())
            except tkinter.TclError:
                pass
        menu.add_command(label="Cortar", command=cut_text)
        menu.add_command(label="Copiar", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Pegar", command=paste_text)
        menu.add_separator()
        menu.add_command(label="Seleccionar todo", command=lambda: widget.select_range(0, 'end'))
        menu.tk_popup(widget.winfo_pointerx(), widget.winfo_pointery())
        
    def paste_into_widget(self, widget):
        """Obtiene el contenido del portapapeles y lo inserta en un widget."""
        try:
            clipboard_text = self.clipboard_get()
            widget.insert('insert', clipboard_text)
        except tkinter.TclError:
            pass
        
    def _check_for_ui_requests(self):
        """
        Verifica si un hilo secundario ha solicitado una acción de UI.
        Este método se ejecuta en el bucle principal de la aplicación.
        """
        if self.ui_request_event.is_set():
            self.ui_request_event.clear()
            request_type = self.ui_request_data.get("type")

            if request_type == "ask_yes_no":
                if self.loading_window and self.loading_window.winfo_exists():
                    self.loading_window.withdraw()
                title = self.ui_request_data.get("title", "Confirmar")
                message = self.ui_request_data.get("message", "¿Estás seguro?")
                result = messagebox.askyesno(title, message)
                self.ui_response_data["result"] = result
                if self.loading_window and self.loading_window.winfo_exists():
                    self.loading_window.deiconify()
                self.lift() 
                self.ui_response_event.set()

            # --- LA CORRECCIÓN CLAVE ESTÁ AQUÍ ---
            # Ahora reconoce tanto la petición del modo URL ("ask_conflict")
            # como la del modo local ("ask_conflict_recode").
            elif request_type in ["ask_conflict", "ask_conflict_recode"]:
                filename = self.ui_request_data.get("filename", "")
                dialog = ConflictDialog(self, filename)
                self.wait_window(dialog) 
                self.lift()
                self.focus_force()
                self.ui_response_data["result"] = dialog.result
                self.ui_response_event.set()

        self.after(100, self._check_for_ui_requests)

    def run_initial_setup(self):
        """Lanza la ventana de carga y el proceso de verificación en un hilo."""
        self.loading_window = LoadingWindow(self)
        self.attributes('-disabled', True)
        from src.core.setup import check_environment_status
        self.setup_thread = threading.Thread(
            target=lambda: self.on_status_check_complete(check_environment_status(self.update_setup_progress)),
            daemon=True
        )
        self.setup_thread.start()

    def on_status_check_complete(self, status_info, force_check=False):
        """Callback que se ejecuta cuando la verificación del entorno termina."""
        local_version = status_info.get("local_version", "No encontrado")
        self.ffmpeg_status_label.configure(text=f"FFmpeg: Versión local {local_version}")
        self.update_ffmpeg_button.configure(state="normal", text="Buscar Actualizaciones de FFmpeg")
        status = status_info.get("status")

        if status == "error":
            # Si el error es realmente crítico (ej: no hay FFmpeg y no se puede descargar)
            self.loading_window.update_progress(status_info.get("message"), -1)
            # La aplicación se detiene aquí a propósito.
            return

        if status == "warning":
            # --- ESTA ES LA CORRECCIÓN CLAVE ---
            # El programa encontró un problema (no pudo verificar la versión), pero no es crítico.
            # Le decimos a la ventana de carga que ignore el estado de error y que continúe.
            if self.loading_window and self.loading_window.winfo_exists():
                self.loading_window.error_state = False
                # Restablecemos el color de la barra de progreso a su color por defecto
                try:
                    # Intenta obtener el color azul por defecto de otro botón
                    default_color = self.analyze_button.cget("fg_color")
                    self.loading_window.progress_bar.configure(progress_color=default_color)
                except Exception:
                    # Si falla, usa un color de respaldo
                    self.loading_window.progress_bar.configure(progress_color=["#3a7ebf", "#346ead"])

            self.after(0, self.loading_window.update_progress, status_info.get("message"), 95)
            self.after(500, self.on_setup_complete) # Se le indica que finalice la configuración.
            return

        # --- El resto de la función para el caso de éxito continúa igual ---
        local_version = status_info.get("local_version")
        latest_version = status_info.get("latest_version")
        download_url = status_info.get("download_url")
        ffmpeg_exists = status_info.get("ffmpeg_path_exists")
        should_download = False
        update_available = ffmpeg_exists and local_version != latest_version

        if not ffmpeg_exists:
            self.after(0, self.loading_window.update_progress, "FFmpeg no encontrado. Se instalará automáticamente.", 40)
            should_download = True
        elif update_available:
            # Comprobar si el usuario ha pospuesto la notificación
            snoozed = self.ffmpeg_update_snooze_until and datetime.now() < self.ffmpeg_update_snooze_until

            # Si no está pospuesto O si es una comprobación manual forzada
            if not snoozed or force_check:
                if self.loading_window and self.loading_window.winfo_exists():
                    self.loading_window.withdraw()

                user_response = messagebox.askyesno(
                    "Actualización Disponible",
                    f"Hay una nueva versión de FFmpeg disponible.\n\n"
                    f"Versión Actual: {local_version or 'Desconocida'}\n"
                    f"Versión Nueva: {latest_version}\n\n"
                    "¿Deseas actualizar ahora?"
                )
                if self.loading_window and self.loading_window.winfo_exists():
                    self.loading_window.deiconify()

                self.lift() 
                if user_response:
                    self.after(0, self.loading_window.update_progress, "Actualizando FFmpeg...", 40)
                    should_download = True
                    # Si el usuario actualiza, eliminamos el snooze
                    self.ffmpeg_update_snooze_until = None
                    self.save_settings()
                else:
                    # El usuario dijo NO, establecemos el snooze para 15 días
                    self.ffmpeg_update_snooze_until = datetime.now() + timedelta(days=15)
                    self.save_settings()
                    print(f"DEBUG: Actualización de FFmpeg pospuesta hasta {self.ffmpeg_update_snooze_until.isoformat()}")
            else:
                print(f"DEBUG: Comprobación de actualización de FFmpeg omitida debido al snooze.")
        if should_download:
            from src.core.setup import download_and_install_ffmpeg
            download_thread = threading.Thread(
                target=download_and_install_ffmpeg,
                args=(latest_version, download_url, self.update_setup_progress),
                daemon=True
            )
            download_thread.start()
        else:
            if update_available:
                self.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} (Actualización a {latest_version} disponible)")
            else:
                self.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} (Actualizado)")

            self.after(0, self.loading_window.update_progress, f"FFmpeg está actualizado ({local_version}).", 95)
            self.after(500, self.on_setup_complete)

    def update_setup_progress(self, text, value):
        """Callback para actualizar la ventana de carga desde el hilo de configuración."""
        if value >= 95:
            self.after(500, self.on_setup_complete)
        self.after(0, self.loading_window.update_progress, text, value / 100.0)

    def on_setup_complete(self):
        """Se ejecuta cuando la configuración inicial ha terminado."""
        if not self.loading_window.error_state:
            self.loading_window.update_progress("Configuración completada.", 100)
            self.after(800, self.loading_window.destroy) 
            self.attributes('-disabled', False)
            self.lift()
            self.focus_force()
            self.ffmpeg_processor.run_detection_async(self.on_ffmpeg_detection_complete)
            self.output_path_entry.insert(0, self.default_download_path)
            self.cookie_mode_menu.set(self.cookies_mode_saved)
            if self.cookies_path:
                self.cookie_path_entry.insert(0, self.cookies_path)
            self.browser_var.set(self.selected_browser_saved)
            self.browser_profile_entry.insert(0, self.browser_profile_saved)
            self.on_cookie_mode_change(self.cookies_mode_saved)
            if self.auto_download_subtitle_saved:
                self.auto_download_subtitle_check.select()
            else:
                self.auto_download_subtitle_check.deselect()
            self.toggle_manual_subtitle_button()
            if self.recode_settings.get("keep_original", True):
                self.keep_original_checkbox.select()
            else:
                self.keep_original_checkbox.deselect()

            self.recode_video_checkbox.deselect()
            self.recode_audio_checkbox.deselect()
            self._toggle_recode_panels()
        else:
            self.loading_window.title("Error Crítico")

    def on_closing(self):
        """
        Se ejecuta cuando el usuario intenta cerrar la ventana.
        Gestiona la cancelación, limpieza y confirmación de forma robusta.
        """
        if self.active_operation_thread and self.active_operation_thread.is_alive():
            if messagebox.askokcancel("Confirmar Salida", "Hay una operación en curso. ¿Estás seguro de que quieres salir?"):
                self.is_shutting_down = True 
                self.attributes("-disabled", True)
                self.progress_label.configure(text="Cancelando y limpiando, por favor espera...")
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
        if self.active_operation_thread and self.active_operation_thread.is_alive():
            # El hilo todavía está ocupado (probablemente limpiando), esperamos un poco más
            self.after(100, self._wait_for_thread_to_finish_and_destroy)
        else:
            # El hilo ha terminado, ahora es seguro cerrar
            self.save_settings()
            self.destroy()

    def create_widgets(self):
        url_frame = ctk.CTkFrame(self)
        url_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(url_frame, text="URL del Video:").pack(side="left", padx=(10, 5))
        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="Pega la URL aquí...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.url_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.url_entry))
        self.url_entry.bind("<Return>", self.start_analysis_thread)
        self.url_entry.bind("<KeyRelease>", self.update_download_button_state)
        self.analyze_button = ctk.CTkButton(url_frame, text=self.original_analyze_text, command=self.original_analyze_command)
        self.analyze_button.pack(side="left", padx=(5, 10))
        self.original_analyze_fg_color = self.analyze_button.cget("fg_color")
        info_frame = ctk.CTkFrame(self)
        info_frame.pack(pady=10, padx=10, fill="both", expand=True)
        left_column_container = ctk.CTkFrame(info_frame, fg_color="transparent")
        left_column_container.pack(side="left", padx=10, pady=10, fill="y", anchor="n")
        self.thumbnail_container = ctk.CTkFrame(left_column_container, width=320, height=180)
        self.thumbnail_container.pack(pady=(0, 5))
        self.thumbnail_container.pack_propagate(False)
        self.create_placeholder_label()
        thumbnail_actions_frame = ctk.CTkFrame(left_column_container)
        thumbnail_actions_frame.pack(fill="x")
        self.save_thumbnail_button = ctk.CTkButton(thumbnail_actions_frame, text="Descargar Miniatura...", state="disabled", command=self.save_thumbnail)
        self.save_thumbnail_button.pack(fill="x", padx=10, pady=5)
        self.auto_save_thumbnail_check = ctk.CTkCheckBox(thumbnail_actions_frame, text="Descargar miniatura con el video", command=self.toggle_manual_thumbnail_button)
        self.auto_save_thumbnail_check.pack(padx=10, pady=5, anchor="w")
        options_scroll_frame = ctk.CTkScrollableFrame(left_column_container)
        options_scroll_frame.pack(pady=10, fill="both", expand=True)
        ctk.CTkLabel(options_scroll_frame, text="Subtítulos", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=10, pady=(5, 2))
        subtitle_options_frame = ctk.CTkFrame(options_scroll_frame)
        subtitle_options_frame.pack(fill="x", padx=5, pady=(0, 10))
        subtitle_selection_frame = ctk.CTkFrame(subtitle_options_frame, fg_color="transparent")
        subtitle_selection_frame.pack(fill="x", padx=10, pady=(0, 5))
        subtitle_selection_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(subtitle_selection_frame, text="Idioma:").grid(row=0, column=0, padx=(0, 10), pady=5, sticky="w")
        self.subtitle_lang_menu = ctk.CTkOptionMenu(subtitle_selection_frame, values=["-"], state="disabled", command=self.on_language_change)
        self.subtitle_lang_menu.grid(row=0, column=1, pady=5, sticky="ew")
        ctk.CTkLabel(subtitle_selection_frame, text="Formato:").grid(row=1, column=0, padx=(0, 10), pady=5, sticky="w")
        self.subtitle_type_menu = ctk.CTkOptionMenu(subtitle_selection_frame, values=["-"], state="disabled", command=self.on_subtitle_selection_change)
        self.subtitle_type_menu.grid(row=1, column=1, pady=5, sticky="ew")
        self.save_subtitle_button = ctk.CTkButton(subtitle_options_frame, text="Descargar Subtítulos", state="disabled", command=self.save_subtitle)
        self.save_subtitle_button.pack(fill="x", padx=10, pady=5)
        self.auto_download_subtitle_check = ctk.CTkCheckBox(subtitle_options_frame, text="Descargar subtítulos con el video", command=self.toggle_manual_subtitle_button)
        self.auto_download_subtitle_check.pack(padx=10, pady=5, anchor="w")
        self.clean_subtitle_check = ctk.CTkCheckBox(subtitle_options_frame, text="Simplificar a formato estándar (SRT)")
        self.clean_subtitle_check.pack(padx=10, pady=(0, 5), anchor="w")

        ctk.CTkLabel(options_scroll_frame, text="Cookies", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=10, pady=(5, 2))
        cookie_options_frame = ctk.CTkFrame(options_scroll_frame)
        cookie_options_frame.pack(fill="x", padx=5, pady=(0, 10))
        self.cookie_mode_menu = ctk.CTkOptionMenu(cookie_options_frame, values=["No usar", "Archivo Manual...", "Desde Navegador"], command=self.on_cookie_mode_change)
        self.cookie_mode_menu.pack(fill="x", padx=10, pady=(0, 5))
        self.manual_cookie_frame = ctk.CTkFrame(cookie_options_frame, fg_color="transparent")
        self.cookie_path_entry = ctk.CTkEntry(self.manual_cookie_frame, placeholder_text="Ruta al archivo cookies.txt...")
        self.cookie_path_entry.pack(fill="x")
        self.cookie_path_entry.bind("<KeyRelease>", lambda event: self.save_settings())
        self.select_cookie_file_button = ctk.CTkButton(self.manual_cookie_frame, text="Elegir Archivo...", command=lambda: self.select_cookie_file())
        self.select_cookie_file_button.pack(fill="x", pady=(5,0))
        self.browser_options_frame = ctk.CTkFrame(cookie_options_frame, fg_color="transparent")
        ctk.CTkLabel(self.browser_options_frame, text="Navegador:").pack(padx=10, pady=(5,0), anchor="w")
        self.browser_var = ctk.StringVar(value=self.selected_browser_saved)
        self.browser_menu = ctk.CTkOptionMenu(self.browser_options_frame, values=["chrome", "firefox", "edge", "opera", "vivaldi", "brave"], variable=self.browser_var, command=self.save_settings)
        self.browser_menu.pack(fill="x", padx=10)
        ctk.CTkLabel(self.browser_options_frame, text="Perfil (Opcional):").pack(padx=10, pady=(5,0), anchor="w")
        self.browser_profile_entry = ctk.CTkEntry(self.browser_options_frame, placeholder_text="Ej: Default, Profile 1")
        self.browser_profile_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.browser_profile_entry))
        self.browser_profile_entry.pack(fill="x", padx=10)
        self.browser_profile_entry.bind("<KeyRelease>", lambda event: self.save_settings())
        cookie_advice_label = ctk.CTkLabel(self.browser_options_frame, text=" ⓘ Si falla, cierre el navegador por completo. \n ⓘ Para Chrome/Edge/Brave,\n se recomienda usar la opción 'Archivo Manual'", font=ctk.CTkFont(size=11), text_color="orange", justify="left")
        cookie_advice_label.pack(pady=(10, 5), padx=10, fill="x", anchor="w")

        ctk.CTkLabel(options_scroll_frame, text="Mantenimiento", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=10, pady=(5, 2))
        maintenance_frame = ctk.CTkFrame(options_scroll_frame)
        maintenance_frame.pack(fill="x", padx=5, pady=(0, 10))
        maintenance_frame.grid_columnconfigure(0, weight=1)
        self.ffmpeg_status_label = ctk.CTkLabel(maintenance_frame, text="FFmpeg: Verificando...", wraplength=280, justify="left")
        self.ffmpeg_status_label.grid(row=0, column=0, padx=10, pady=(5,5), sticky="ew")
        self.update_ffmpeg_button = ctk.CTkButton(maintenance_frame, text="Buscar Actualizaciones de FFmpeg", command=self.manual_ffmpeg_update_check)
        self.update_ffmpeg_button.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        details_frame = ctk.CTkFrame(info_frame)
        details_frame.pack(side="left", fill="both", expand=True, padx=(0,10), pady=10)
        ctk.CTkLabel(details_frame, text="Título:", anchor="w").pack(fill="x", padx=5, pady=(5,0))
        self.title_entry = ctk.CTkEntry(details_frame, font=("", 14))
        self.title_entry.pack(fill="x", padx=5, pady=(0,10))
        self.title_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.title_entry))
        options_frame = ctk.CTkFrame(details_frame)
        options_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(options_frame, text="Modo:").pack(side="left", padx=(0, 10))
        self.mode_selector = ctk.CTkSegmentedButton(options_frame, values=["Video+Audio", "Solo Audio"], command=self.on_mode_change)
        self.mode_selector.set("Video+Audio")
        self.mode_selector.pack(side="left", expand=True, fill="x")
        self.video_quality_label = ctk.CTkLabel(details_frame, text="Calidad de Video:", anchor="w")
        self.video_quality_menu = ctk.CTkOptionMenu(details_frame, state="disabled", values=["-"], command=self.on_video_quality_change)
        self.audio_quality_label = ctk.CTkLabel(details_frame, text="Calidad de Audio:", anchor="w")
        self.audio_quality_menu = ctk.CTkOptionMenu(details_frame, state="disabled", values=["-"], command=lambda _: (self._update_warnings(), self._validate_recode_compatibility()))


        legend_text = (
            "Guía de etiquetas en la lista:\n"
            "✨ Ideal: Formato óptimo para editar sin conversión.\n"
            "⚠️ Lento: El proceso de recodificación puede tardar más.\n"
            "⚠️ Recodificar: Formato no compatible con editores."
        )
        # Crea la etiqueta usando el texto de la guía
        self.format_warning_label = ctk.CTkLabel(
            details_frame, 
            text=legend_text, 
            text_color="gray", 
            font=ctk.CTkFont(size=12, weight="normal"), 
            wraplength=400, 
            justify="left"
        )

        self.recode_main_frame = ctk.CTkScrollableFrame(details_frame)
        ctk.CTkLabel(self.recode_main_frame, text="Opciones de Recodificación", font=ctk.CTkFont(weight="bold")).pack(pady=(5,10))

        recode_toggle_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        recode_toggle_frame.pack(side="top", fill="x", padx=10, pady=(0, 10))
        recode_toggle_frame.grid_columnconfigure((0, 1), weight=1)

        self.recode_video_checkbox = ctk.CTkCheckBox(recode_toggle_frame, text="Recodificar Video", command=self._toggle_recode_panels, state="disabled")
        self.recode_video_checkbox.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_checkbox = ctk.CTkCheckBox(recode_toggle_frame, text="Recodificar Audio", command=self._toggle_recode_panels, state="disabled")
        self.recode_audio_checkbox.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.keep_original_checkbox = ctk.CTkCheckBox(recode_toggle_frame, text="Mantener los archivos originales", state="disabled", command=self.save_settings)
        self.keep_original_checkbox.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        self.keep_original_checkbox.select()

        self.recode_warning_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent", height=40)
        self.recode_warning_frame.pack(pady=0, padx=10, fill="x")
        self.recode_warning_frame.pack_propagate(False)
        
        self.recode_warning_label = ctk.CTkLabel(self.recode_warning_frame, text="", wraplength=400, justify="left", font=ctk.CTkFont(weight="bold"))

        self.recode_options_frame = ctk.CTkFrame(self.recode_main_frame)
        ctk.CTkLabel(self.recode_options_frame, text="Opciones de Video", font=ctk.CTkFont(weight="bold")).pack(pady=(5, 10), padx=10)

        self.proc_type_var = ctk.StringVar(value="")
        proc_frame = ctk.CTkFrame(self.recode_options_frame, fg_color="transparent")
        proc_frame.pack(fill="x", padx=10, pady=5)
        self.cpu_radio = ctk.CTkRadioButton(proc_frame, text="CPU", variable=self.proc_type_var, value="CPU", command=self.update_codec_menu)
        self.cpu_radio.pack(side="left", padx=10)
        self.gpu_radio = ctk.CTkRadioButton(proc_frame, text="GPU", variable=self.proc_type_var, value="GPU", state="disabled", command=self.update_codec_menu)
        self.gpu_radio.pack(side="left", padx=20)

        codec_options_frame = ctk.CTkFrame(self.recode_options_frame)
        codec_options_frame.pack(fill="x", padx=10, pady=5)
        codec_options_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(codec_options_frame, text="Codec:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.recode_codec_menu = ctk.CTkOptionMenu(codec_options_frame, values=["-"], state="disabled", command=self.update_profile_menu)
        self.recode_codec_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(codec_options_frame, text="Perfil/Calidad:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.recode_profile_menu = ctk.CTkOptionMenu(codec_options_frame, values=["-"], state="disabled", command=self.on_profile_selection_change) 
        self.recode_profile_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.custom_bitrate_frame = ctk.CTkFrame(codec_options_frame, fg_color="transparent")
        ctk.CTkLabel(self.custom_bitrate_frame, text="Bitrate (Mbps):").pack(side="left", padx=(0, 5))
        self.custom_bitrate_entry = ctk.CTkEntry(self.custom_bitrate_frame, placeholder_text="Ej: 8", width=100)
        self.custom_bitrate_entry.bind("<KeyRelease>", self.update_download_button_state)
        self.custom_bitrate_entry.pack(side="left")

        self.estimated_size_label = ctk.CTkLabel(self.custom_bitrate_frame, text="N/A", font=ctk.CTkFont(weight="bold"))
        self.estimated_size_label.pack(side="right", padx=(10, 0))
        ctk.CTkLabel(self.custom_bitrate_frame, text="Tamaño Estimado:").pack(side="right")

        ctk.CTkLabel(codec_options_frame, text="Contenedor:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        container_value_frame = ctk.CTkFrame(codec_options_frame, fg_color="transparent")
        container_value_frame.grid(row=3, column=1, padx=5, pady=0, sticky="ew")
        self.recode_container_label = ctk.CTkLabel(container_value_frame, text="-", font=ctk.CTkFont(weight="bold"))
        self.recode_container_label.pack(side="left", padx=5, pady=5)

        self.fps_frame = ctk.CTkFrame(self.recode_options_frame)
        self.fps_frame.pack(fill="x", padx=10, pady=(10, 5))
        self.fps_frame.grid_columnconfigure(1, weight=1)
        self.fps_checkbox = ctk.CTkCheckBox(self.fps_frame, text="Forzar FPS Constantes (CFR)", command=self.toggle_fps_entry_panel)
        self.fps_checkbox.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        self.fps_value_label = ctk.CTkLabel(self.fps_frame, text="Valor FPS:")
        self.fps_entry = ctk.CTkEntry(self.fps_frame, placeholder_text="Ej: 23.976, 25, 29.97, 30, 60")
        self.toggle_fps_entry_panel()

        self.resolution_frame = ctk.CTkFrame(self.recode_options_frame)
        self.resolution_frame.pack(fill="x", padx=10, pady=5)
        self.resolution_frame.grid_columnconfigure(1, weight=1)
        self.resolution_checkbox = ctk.CTkCheckBox(self.resolution_frame, text="Cambiar Resolución", command=self.toggle_resolution_panel)
        self.resolution_checkbox.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        self.resolution_options_frame = ctk.CTkFrame(self.resolution_frame, fg_color="transparent")
        self.resolution_options_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.resolution_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.resolution_options_frame, text="Preset:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.resolution_preset_menu = ctk.CTkOptionMenu(self.resolution_options_frame, values=["Personalizado", "4K UHD (3840x2160)", "2K QHD (2560x1440)", "1080p Full HD (1920x1080)", "720p HD (1280x720)", "480p SD (854x480)", "Vertical 9:16 (1080x1920)", "Cuadrado 1:1 (1080x1080)"], command=self.on_resolution_preset_change)
        self.resolution_preset_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.resolution_manual_frame = ctk.CTkFrame(self.resolution_options_frame, fg_color="transparent")
        self.resolution_manual_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.resolution_manual_frame.grid_columnconfigure((0, 2), weight=1)
        ctk.CTkLabel(self.resolution_manual_frame, text="Ancho:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.width_entry = ctk.CTkEntry(self.resolution_manual_frame, width=80)
        self.width_entry.grid(row=0, column=1, padx=5, pady=5)
        self.width_entry.bind("<KeyRelease>", lambda event: self.on_dimension_change("width"))
        self.aspect_ratio_lock = ctk.CTkCheckBox(self.resolution_manual_frame, text="🔗", font=ctk.CTkFont(size=16), command=self.on_aspect_lock_change)
        self.aspect_ratio_lock.grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(self.resolution_manual_frame, text="Alto:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.height_entry = ctk.CTkEntry(self.resolution_manual_frame, width=80)
        self.height_entry.grid(row=1, column=1, padx=5, pady=5)
        self.height_entry.bind("<KeyRelease>", lambda event: self.on_dimension_change("height"))
        self.no_upscaling_checkbox = ctk.CTkCheckBox(self.resolution_manual_frame, text="No ampliar resolución")
        self.no_upscaling_checkbox.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        self.toggle_resolution_panel()

        self.recode_audio_options_frame = ctk.CTkFrame(self.recode_main_frame)
        self.recode_audio_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.recode_audio_options_frame, text="Opciones de Audio", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, pady=(5, 10), padx=10)
        ctk.CTkLabel(self.recode_audio_options_frame, text="Codec de Audio:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_codec_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], state="disabled", command=lambda _: self._validate_recode_compatibility())
        self.recode_audio_codec_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.recode_audio_options_frame, text="Perfil de Audio:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_profile_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], state="disabled", command=lambda _: self._validate_recode_compatibility())
        self.recode_audio_profile_menu.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        local_import_frame = ctk.CTkFrame(self.recode_main_frame)
        local_import_frame.pack(side="bottom", fill="x", padx=10, pady=(15, 5))
        ctk.CTkLabel(local_import_frame, text="¿Tienes un archivo existente?", font=ctk.CTkFont(weight="bold")).pack()
        self.import_button = ctk.CTkButton(local_import_frame, text="Importar Archivo Local para Recodificar", command=self.import_local_file)
        self.import_button.pack(fill="x", padx=10, pady=5)
        self.save_in_same_folder_check = ctk.CTkCheckBox(local_import_frame, text="Guardar en la misma carpeta que el original")
        self.clear_local_file_button = ctk.CTkButton(local_import_frame, text="Limpiar y Volver a Modo URL", fg_color="gray", hover_color="#555555", command=self.reset_to_url_mode)

        download_frame = ctk.CTkFrame(self)
        download_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(download_frame, text="Carpeta de Salida:").pack(side="left", padx=(10, 5))
        self.output_path_entry = ctk.CTkEntry(download_frame, placeholder_text="Selecciona una carpeta...")
        self.output_path_entry.bind("<KeyRelease>", self.update_download_button_state)
        self.output_path_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.output_path_entry))
        self.output_path_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.select_folder_button = ctk.CTkButton(download_frame, text="...", width=40, command=lambda: self.select_output_folder())
        self.select_folder_button.pack(side="left", padx=(0, 5))
        self.open_folder_button = ctk.CTkButton(download_frame, text="📂", width=40, font=ctk.CTkFont(size=16), command=self.open_last_download_folder, state="disabled")
        self.open_folder_button.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(download_frame, text="Límite (MB/s):").pack(side="left", padx=(10, 5))
        self.speed_limit_entry = ctk.CTkEntry(download_frame, width=50)
        self.speed_limit_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.speed_limit_entry))
        self.speed_limit_entry.pack(side="left", padx=(0, 10))
        self.download_button = ctk.CTkButton(download_frame, text=self.original_download_text, state="disabled", command=self.original_download_command)
        self.download_button.pack(side="left", padx=(5, 10))
        self.original_download_fg_color = self.download_button.cget("fg_color")
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
        self.on_profile_selection_change(self.recode_profile_menu.get())
        self._check_for_ui_requests()

    def import_local_file(self):
        filetypes = [
            ("Archivos de Video", "*.mp4 *.mkv *.mov *.avi *.webm"),
            ("Archivos de Audio", "*.mp3 *.wav *.m4a *.flac *.opus"),
            ("Todos los archivos", "*.*")
        ]
        filepath = filedialog.askopenfilename(title="Selecciona un archivo para recodificar", filetypes=filetypes)
        self.lift()
        self.focus_force()
        if filepath:
            self.cancellation_event.clear()
            self.progress_label.configure(text=f"Analizando archivo local: {os.path.basename(filepath)}...")
            self.progress_bar.start()
            self.open_folder_button.configure(state="disabled")
            threading.Thread(target=self._process_local_file_info, args=(filepath,), daemon=True).start()

    def _process_local_file_info(self, filepath):
        info = self.ffmpeg_processor.get_local_media_info(filepath)

        def update_ui():
            self.progress_bar.stop()
            if not info:
                self.progress_label.configure(text="Error: No se pudo analizar el archivo.")
                self.progress_bar.set(0)
                return
            self.reset_ui_for_local_file()
            self.local_file_path = filepath
            self.auto_save_thumbnail_check.configure(state="disabled")
            self.auto_save_thumbnail_check.deselect()
            self.recode_main_frame._parent_canvas.yview_moveto(0)
            self.save_in_same_folder_check.pack(padx=10, pady=(5,0), anchor="w")
            self.save_in_same_folder_check.select()

            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            audio_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)

            if video_stream:
                self.original_video_width = video_stream.get('width', 0)
                self.original_video_height = video_stream.get('height', 0)
            else:
                self.original_video_width = 0
                self.original_video_height = 0

            self.title_entry.insert(0, os.path.splitext(os.path.basename(filepath))[0])
            self.video_duration = float(info.get('format', {}).get('duration', 0))

            if video_stream:
                self.mode_selector.set("Video+Audio")
                self.on_mode_change("Video+Audio")

                frame_path = self.ffmpeg_processor.get_frame_from_video(filepath)
                if frame_path:
                    self.load_thumbnail(frame_path, is_local=True)
                v_codec = video_stream.get('codec_name', 'N/A').upper()
                v_profile = video_stream.get('profile', 'N/A')
                v_level = video_stream.get('level')
                full_profile = f"{v_profile}@L{v_level / 10.0}" if v_level else v_profile
                v_resolution = f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}"
                v_fps = self._format_fps(video_stream.get('r_frame_rate'))
                v_bitrate = self._format_bitrate(video_stream.get('bit_rate'))
                v_pix_fmt = video_stream.get('pix_fmt', 'N/A')
                bit_depth = "10-bit" if any(x in v_pix_fmt for x in ['p10', '10le']) else "8-bit"
                color_range = video_stream.get('color_range', '').capitalize()
                v_label = f"{v_resolution} | {v_codec} ({full_profile}) @ {v_fps} fps | {v_bitrate} | {v_pix_fmt} ({bit_depth}, {color_range})"
                _, ext_with_dot = os.path.splitext(filepath)
                ext = ext_with_dot.lstrip('.')
                self.video_formats = {v_label: {
                    'format_id': 'local_video', 
                    'width': self.original_video_width, 
                    'height': self.original_video_height, 
                    'vcodec': v_codec, 
                    'ext': ext
                }}
                self.video_quality_menu.configure(values=[v_label], state="normal")
                self.video_quality_menu.set(v_label)
                self.on_video_quality_change(v_label)

                audio_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
                audio_labels = []
                self.audio_formats = {} # Limpia los formatos de audio anteriores

                if not audio_streams:
                    self.audio_formats = {"-": {}}
                    self.audio_quality_menu.configure(values=["-"], state="disabled")
                else:
                    for stream in audio_streams:
                        idx = stream.get('index', '?')
                        # Busca el título de la pista en las etiquetas
                        title = stream.get('tags', {}).get('title', f"Pista de Audio {idx}")
                        # Comprueba si es la pista por defecto
                        is_default = stream.get('disposition', {}).get('default', 0) == 1
                        default_str = " (Default)" if is_default else ""

                        # Extrae y formatea todos los detalles del stream actual
                        a_codec = stream.get('codec_name', 'N/A').upper()
                        a_profile = stream.get('profile', 'N/A')
                        a_channels_num = stream.get('channels', '?')
                        a_channel_layout = stream.get('channel_layout', 'N/A')
                        a_channels = f"{a_channels_num} Canales ({a_channel_layout})"
                        a_sample_rate = f"{int(stream.get('sample_rate', 0)) / 1000:.1f} kHz"
                        a_bitrate = self._format_bitrate(stream.get('bit_rate'))

                        # Construye la etiqueta final y la añade a la lista
                        a_label = f"{title}{default_str}: {a_codec} ({a_profile}) | {a_sample_rate} | {a_channels} | {a_bitrate}"
                        audio_labels.append(a_label)
                        
                        # Guarda la información del stream para uso interno
                        self.audio_formats[a_label] = {'format_id': f'local_audio_{idx}', 'acodec': stream.get('codec_name', 'N/A')}
                    
                    self.audio_quality_menu.configure(values=audio_labels, state="normal")
                    # Intenta seleccionar la pista "Default" automáticamente
                    default_selection = next((label for label in audio_labels if "(Default)" in label), audio_labels[0])
                    self.audio_quality_menu.set(default_selection)

                self._update_warnings()

            elif audio_stream:
                self.mode_selector.set("Solo Audio")
                self.on_mode_change("Solo Audio")
                self.create_placeholder_label("🎵")

                a_codec = audio_stream.get('codec_name', 'N/A')
                a_label = f"Audio Original ({a_codec})"
                self.audio_formats = {a_label: {'format_id': 'local_audio', 'acodec': a_codec}}
                self.audio_quality_menu.configure(values=[a_label], state="normal")
                self.audio_quality_menu.set(a_label)
                self._update_warnings()
            if self.cpu_radio.cget('state') == 'normal':
                self.proc_type_var.set("CPU")
                self.update_codec_menu() 
            self.progress_label.configure(text=f"Listo para recodificar: {os.path.basename(filepath)}")
            self.progress_bar.set(1)
            self.update_download_button_state()
            self.download_button.configure(text="Iniciar Proceso")
            self.update_estimated_size()
            self._validate_recode_compatibility()
        self.after(0, update_ui)

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

    def reset_ui_for_local_file(self):
        self.title_entry.delete(0, 'end')
        self.video_formats, self.audio_formats = {}, {}
        self.video_quality_menu.configure(values=["-"], state="disabled")
        self.audio_quality_menu.configure(values=["-"], state="disabled")
        self._clear_subtitle_menus()
        self.clear_local_file_button.pack(fill="x", padx=10, pady=(0, 10))

    def reset_to_url_mode(self):
        self.local_file_path = None
        self.url_entry.configure(state="normal")
        self.analyze_button.configure(state="normal")
        self.url_entry.delete(0, 'end')
        self.title_entry.delete(0, 'end')
        self.create_placeholder_label("Miniatura")
        self.auto_save_thumbnail_check.configure(state="normal")
        self.video_formats, self.audio_formats = {}, {}
        self.video_quality_menu.configure(values=["-"], state="disabled")
        self.audio_quality_menu.configure(values=["-"], state="disabled")
        self.progress_label.configure(text="Esperando...")
        self.progress_bar.set(0)
        self._clear_subtitle_menus()
        self.save_in_same_folder_check.pack_forget()
        self.download_button.configure(text=self.original_download_text)
        self.clear_local_file_button.pack_forget()
        self.update_download_button_state()

    def _execute_local_recode(self, options):
        """
        Función dedicada exclusivamente a la recodificación de un archivo local.
        Maneja su propia lógica de conflictos y errores.
        """
        source_path = self.local_file_path
        output_dir = self.output_path_entry.get()
        if self.save_in_same_folder_check.get() == 1:
            output_dir = os.path.dirname(source_path)
        final_title = self.sanitize_filename(options['title']) + "_recoded"
        final_container = options["recode_container"]
        final_recoded_path = None
        try:
            output_path_candidate = Path(output_dir) / f"{final_title}{final_container}"
            if output_path_candidate.exists():
                self.ui_request_data = {"type": "ask_conflict_recode", "filename": output_path_candidate.name}
                self.ui_request_event.set()
                self.ui_response_event.wait()
                self.ui_response_event.clear()
                user_choice = self.ui_response_data.get("result", "cancel")
                if user_choice == "cancel":
                    raise UserCancelledError("Operación cancelada por el usuario en conflicto de archivo.")
                elif user_choice == "rename":
                    base_title = self.sanitize_filename(options['title']) + "_recoded"
                    counter = 1
                    while True:
                        new_title_candidate = f"{base_title} ({counter})"
                        new_path_candidate = Path(output_dir) / f"{new_title_candidate}{final_container}"
                        if not new_path_candidate.exists():
                            final_title = new_title_candidate
                            break
                        counter += 1
            final_recoded_path = os.path.join(output_dir, f"{final_title}{final_container}")
            final_ffmpeg_params = []
            if options["recode_video_enabled"]:
                proc = options["recode_proc"]; codec_db = self.ffmpeg_processor.available_encoders[proc]["Video"]; codec_data = codec_db.get(options["recode_codec_name"])
                ffmpeg_codec_name = list(filter(lambda k: k != 'container', codec_data.keys()))[0]; profile_params = codec_data[ffmpeg_codec_name].get(options["recode_profile_name"])
                if "CUSTOM_BITRATE" in profile_params:
                    bitrate_mbps = float(self.custom_bitrate_entry.get()); bitrate_k = int(bitrate_mbps * 1000)
                    if "nvenc" in ffmpeg_codec_name: profile_params = f"-c:v {ffmpeg_codec_name} -preset p5 -rc vbr -b:v {bitrate_k}k -maxrate {bitrate_k}k"
                    else: profile_params = f"-c:v {ffmpeg_codec_name} -b:v {bitrate_k}k -maxrate {bitrate_k}k -bufsize {bitrate_k*2}k -pix_fmt yuv420p"
                final_ffmpeg_params.extend(profile_params.split())
            else:
                final_ffmpeg_params.extend(["-c:v", "copy"])
            if options["recode_audio_enabled"]:
                audio_codec_db = self.ffmpeg_processor.available_encoders["CPU"]["Audio"]; audio_codec_data = audio_codec_db.get(options["recode_audio_codec_name"])
                ffmpeg_audio_codec = list(filter(lambda k: k != 'container', audio_codec_data.keys()))[0]; audio_profile_params = audio_codec_data[ffmpeg_audio_codec].get(options["recode_audio_profile_name"])
                if audio_profile_params: final_ffmpeg_params.extend(audio_profile_params.split())
            else:
                final_ffmpeg_params.extend(["-c:a", "copy"])
            recode_opts = { "input_file": source_path, "output_file": final_recoded_path, "duration": self.video_duration, "ffmpeg_params": final_ffmpeg_params }
            self.ffmpeg_processor.execute_recode(recode_opts, self.update_progress, self.cancellation_event)
            self.on_process_finished(True, "Recodificación local completada.", final_recoded_path)
        except (UserCancelledError, Exception) as e:
            raise LocalRecodeFailedError(str(e), temp_filepath=final_recoded_path)

    def toggle_resolution_panel(self):
        if self.resolution_checkbox.get() == 1:
            self.resolution_options_frame.grid()
            self.on_resolution_preset_change(self.resolution_preset_menu.get())
        else:
            self.resolution_options_frame.grid_remove()

    def on_dimension_change(self, source):
        if not self.aspect_ratio_lock.get() or self.is_updating_dimension or not self.current_aspect_ratio:
            return
        try:
            self.is_updating_dimension = True
            if source == "width":
                current_width_str = self.width_entry.get()
                if current_width_str:
                    new_width = int(current_width_str)
                    new_height = int(new_width / self.current_aspect_ratio)
                    self.height_entry.delete(0, 'end')
                    self.height_entry.insert(0, str(new_height))
            elif source == "height":
                current_height_str = self.height_entry.get()
                if current_height_str:
                    new_height = int(current_height_str)
                    new_width = int(new_height * self.current_aspect_ratio)
                    self.width_entry.delete(0, 'end')
                    self.width_entry.insert(0, str(new_width))
        except (ValueError, ZeroDivisionError):
            pass
        finally:
            self.is_updating_dimension = False

    def on_aspect_lock_change(self):
        if self.aspect_ratio_lock.get():
            try:
                if hasattr(self, 'original_video_width') and self.original_video_width > 0:
                    self.current_aspect_ratio = self.original_video_width / self.original_video_height
                else:
                    width = int(self.width_entry.get())
                    height = int(self.height_entry.get())
                    self.current_aspect_ratio = width / height
            except (ValueError, ZeroDivisionError, AttributeError):
                self.current_aspect_ratio = None
        else:
            self.current_aspect_ratio = None

    def on_resolution_preset_change(self, preset):
        if preset == "Personalizado":
            self.resolution_manual_frame.grid()
        else:
            self.resolution_manual_frame.grid_remove()
            try:
                dims = preset.split('(')[1].split(')')[0]
                width, height = dims.split('x')
                self.width_entry.delete(0, 'end')
                self.width_entry.insert(0, width)
                self.height_entry.delete(0, 'end')
                self.height_entry.insert(0, height)
            except Exception as e:
                print(f"Error al parsear el preset de resolución: {e}")

    def toggle_audio_recode_panel(self):
        """Muestra u oculta el panel de opciones de recodificación de audio."""
        if self.recode_audio_checkbox.get() == 1:
            self.recode_audio_options_frame.pack(fill="x", padx=5, pady=5)
            self.update_audio_codec_menu()
        else:
            self.recode_audio_options_frame.pack_forget()
        self.update_recode_container_label()

    def update_audio_codec_menu(self):
        """Puebla el menú de códecs de audio disponibles."""
        audio_codecs = list(self.ffmpeg_processor.available_encoders.get("CPU", {}).get("Audio", {}).keys())
        if not audio_codecs:
            audio_codecs = ["-"]
        
        self.recode_audio_codec_menu.configure(values=audio_codecs, state="normal" if audio_codecs[0] != "-" else "disabled")
        saved_codec = self.recode_settings.get("video_audio_codec")
        if saved_codec and saved_codec in audio_codecs:
            self.recode_audio_codec_menu.set(saved_codec)
        else:
            self.recode_audio_codec_menu.set(audio_codecs[0])
        self.update_audio_profile_menu(self.recode_audio_codec_menu.get())

    def update_audio_profile_menu(self, selected_codec_name):
        """Puebla el menú de perfiles basado en el códec de audio seleccionado."""
        profiles = ["-"]
        if selected_codec_name != "-":
            audio_codecs = self.ffmpeg_processor.available_encoders.get("CPU", {}).get("Audio", {})
            codec_data = audio_codecs.get(selected_codec_name)
            if codec_data:
                ffmpeg_codec_name = list(filter(lambda k: k != 'container', codec_data.keys()))[0]
                profiles = list(codec_data.get(ffmpeg_codec_name, {}).keys())
        self.recode_audio_profile_menu.configure(values=profiles, state="normal" if profiles[0] != "-" else "disabled")
        saved_profile = self.recode_settings.get("video_audio_profile")
        if saved_profile and saved_profile in profiles:
            self.recode_audio_profile_menu.set(saved_profile)
        else:
            self.recode_audio_profile_menu.set(profiles[0])
        self.update_recode_container_label()

    def on_audio_selection_change(self, selection):
        """Se ejecuta al cambiar el códec o perfil de audio para verificar la compatibilidad."""
        # Primero, actualiza la etiqueta del contenedor como antes
        self.update_audio_profile_menu(selection)
        self.update_recode_container_label()

        # Lógica de advertencia
        is_video_mode = self.mode_selector.get() == "Video+Audio"
        video_codec = self.recode_codec_menu.get()
        audio_codec = self.recode_audio_codec_menu.get()

        # Combinaciones conocidas como problemáticas
        incompatible = False
        if is_video_mode and "ProRes" in video_codec or "DNxH" in video_codec:
            if "FLAC" in audio_codec or "Opus" in audio_codec or "Vorbis" in audio_codec:
                incompatible = True

        if incompatible:
            self.audio_compatibility_warning.grid() # Muestra la advertencia
        else:
            self.audio_compatibility_warning.grid_remove() # Oculta la advertencia

    def update_recode_container_label(self, *args):
        """
        Determina y muestra el contenedor final, asegurando que en modo
        Video+Audio siempre se use un contenedor de video.
        """
        container = "-"
        mode = self.mode_selector.get()
        is_video_recode_on = self.recode_video_checkbox.get() == 1
        is_audio_recode_on = self.recode_audio_checkbox.get() == 1
        if mode == "Video+Audio":
            if is_video_recode_on:
                proc_type = self.proc_type_var.get()
                if proc_type:
                    codec_name = self.recode_codec_menu.get()
                    available = self.ffmpeg_processor.available_encoders.get(proc_type, {}).get("Video", {})
                    if codec_name in available:
                        container = available[codec_name].get("container", "-")
            elif is_audio_recode_on:
                container = ".mp4"
        elif mode == "Solo Audio":
            if is_audio_recode_on:
                codec_name = self.recode_audio_codec_menu.get()
                available = self.ffmpeg_processor.available_encoders.get("CPU", {}).get("Audio", {})
                if codec_name in available:
                    container = available[codec_name].get("container", "-")
        self.recode_container_label.configure(text=container)

    def manual_ffmpeg_update_check(self):
        """Inicia una comprobación manual de la actualización de FFmpeg, ignorando el snooze."""
        self.update_ffmpeg_button.configure(state="disabled", text="Buscando...")
        self.ffmpeg_status_label.configure(text="FFmpeg: Verificando...")

        from src.core.setup import check_environment_status
        # Forzamos la comprobación pasando un callback que ignora el snooze
        self.setup_thread = threading.Thread(
            target=lambda: self.on_status_check_complete(
                check_environment_status(self.update_setup_progress),
                force_check=True  # Argumento para ignorar el snooze
            ),
            daemon=True
        )
        self.setup_thread.start()

    def _clear_subtitle_menus(self):
        """Restablece TODOS los controles de subtítulos a su estado inicial e inactivo."""
        self.subtitle_lang_menu.configure(state="disabled", values=["-"])
        self.subtitle_lang_menu.set("-")
        self.subtitle_type_menu.configure(state="disabled", values=["-"])
        self.subtitle_type_menu.set("-")
        self.save_subtitle_button.configure(state="disabled")
        self.auto_download_subtitle_check.configure(state="disabled")
        self.auto_download_subtitle_check.deselect()
        if hasattr(self, 'clean_subtitle_check'):
            if self.clean_subtitle_check.winfo_ismapped():
                self.clean_subtitle_check.pack_forget()
            self.clean_subtitle_check.deselect()
        self.all_subtitles = {}
        self.current_subtitle_map = {}
        self.selected_subtitle_info = None

    def on_profile_selection_change(self, profile):
        if "Bitrate Personalizado" in profile:
            self.custom_bitrate_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5)
            if not self.custom_bitrate_entry.get():
                self.custom_bitrate_entry.insert(0, "8")
        else:
            self.custom_bitrate_frame.grid_forget()
        self.update_estimated_size()
        self.save_settings()
        self._validate_recode_compatibility()

    def update_download_button_state(self, *args):
        """
        Valida TODAS las condiciones necesarias y actualiza el estado del botón de descarga.
        """
        if self.url_entry.get().strip():
            self.analyze_button.configure(state="normal")
        else:
            self.analyze_button.configure(state="disabled")
        try:
            url_is_present = bool(self.url_entry.get())
            local_file_is_present = self.local_file_path is not None
            output_path_is_present = bool(self.output_path_entry.get())
            if local_file_is_present and self.save_in_same_folder_check.get() == 1:
                output_path_is_present = True
            base_conditions_met = output_path_is_present and (url_is_present or local_file_is_present)
            is_video_recode_on = self.recode_video_checkbox.get() == 1
            is_audio_recode_on = self.recode_audio_checkbox.get() == 1
            recode_config_is_valid = True
            if is_video_recode_on:
                processor_selected = bool(self.proc_type_var.get())
                bitrate_ok = True
                if "Bitrate Personalizado" in self.recode_profile_menu.get():
                    try:
                        value = float(self.custom_bitrate_entry.get())
                        if not (0 < value <= 200): bitrate_ok = False
                    except (ValueError, TypeError):
                        bitrate_ok = False
                if not processor_selected or not bitrate_ok:
                    recode_config_is_valid = False
            action_is_selected_for_local_mode = True 
            if local_file_is_present:
                if not is_video_recode_on and not is_audio_recode_on:
                    action_is_selected_for_local_mode = False
            if base_conditions_met and recode_config_is_valid and action_is_selected_for_local_mode and self.recode_compatibility_status in ["valid", "warning"]:
                self.download_button.configure(state="normal")
            else:
                self.download_button.configure(state="disabled")
        except Exception as e:
            print(f"Error inesperado al actualizar estado del botón: {e}")
            self.download_button.configure(state="disabled")
        self.update_estimated_size()

    def update_estimated_size(self):
        try:
            duration_s = float(self.video_duration)
            bitrate_mbps = float(self.custom_bitrate_entry.get())
            if duration_s > 0 and bitrate_mbps > 0:
                estimated_mb = (bitrate_mbps * duration_s) / 8
                size_str = f"~ {estimated_mb / 1024:.2f} GB" if estimated_mb >= 1024 else f"~ {estimated_mb:.1f} MB"
                self.estimated_size_label.configure(text=size_str)
            else:
                self.estimated_size_label.configure(text="N/A")
        except (ValueError, TypeError, AttributeError):
            if hasattr(self, 'estimated_size_label'):
                self.estimated_size_label.configure(text="N/A")

    def save_settings(self, event=None):
        """ Guarda la configuración actual de la aplicación en un archivo JSON. """
        mode = self.mode_selector.get()
        codec = self.recode_codec_menu.get()
        profile = self.recode_profile_menu.get()
        proc_type = self.proc_type_var.get()
        if proc_type: self.recode_settings["proc_type"] = proc_type
        if codec != "-":
            if mode == "Video+Audio": self.recode_settings["video_codec"] = codec
            else: self.recode_settings["audio_codec"] = codec
        if profile != "-":
            if mode == "Video+Audio": self.recode_settings["video_profile"] = profile
            else: self.recode_settings["audio_profile"] = profile
            if self.recode_audio_codec_menu.get() != "-":
                self.recode_settings["video_audio_codec"] = self.recode_audio_codec_menu.get()
            if self.recode_audio_profile_menu.get() != "-":
                self.recode_settings["video_audio_profile"] = self.recode_audio_profile_menu.get()
        self.recode_settings["keep_original"] = self.keep_original_checkbox.get() == 1
        self.recode_settings["recode_video_enabled"] = self.recode_video_checkbox.get() == 1
        self.recode_settings["recode_audio_enabled"] = self.recode_audio_checkbox.get() == 1
        
        snooze_save_val = self.ffmpeg_update_snooze_until.isoformat() if self.ffmpeg_update_snooze_until else None
        
        settings_to_save = {
            "default_download_path": self.default_download_path,
            "cookies_path": self.cookies_path,
            "cookies_mode": self.cookie_mode_menu.get(),
            "selected_browser": self.browser_var.get(),
            "browser_profile": self.browser_profile_entry.get(),
            "auto_download_subtitle": self.auto_download_subtitle_check.get() == 1,
            "ffmpeg_update_snooze_until": snooze_save_val,
            "recode_settings": self.recode_settings 
        }
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_file_path = os.path.join(script_dir, SETTINGS_FILE)
        try:
            with open(settings_file_path, 'w') as f:
                json.dump(settings_to_save, f, indent=4)
        except IOError as e:
            print(f"ERROR: Fallo al guardar configuración: {e}")

    def on_ffmpeg_detection_complete(self, success, message):
        if success:
            if self.ffmpeg_processor.gpu_vendor:
                self.gpu_radio.configure(text="GPU", state="normal")
                self.cpu_radio.pack_forget()
                self.gpu_radio.pack_forget()
                self.gpu_radio.pack(side="left", padx=10)
                self.cpu_radio.pack(side="left", padx=20)
            else:
                self.gpu_radio.configure(text="GPU (No detectada)")
                self.proc_type_var.set("CPU")
                self.gpu_radio.configure(state="disabled")
            self.recode_video_checkbox.configure(state="normal")
            self.recode_audio_checkbox.configure(state="normal")
            self.update_codec_menu()
        else:
            print(f"FFmpeg detection error: {message}")
            self.recode_video_checkbox.configure(text="Recodificación no disponible", state="disabled")
            self.recode_audio_checkbox.configure(text="(Error FFmpeg)", state="disabled")

    def _toggle_recode_panels(self):
        is_video_recode = self.recode_video_checkbox.get() == 1
        is_audio_recode = self.recode_audio_checkbox.get() == 1
        is_audio_only_mode = self.mode_selector.get() == "Solo Audio"
        if is_video_recode or is_audio_recode:
            self.keep_original_checkbox.configure(state="normal")
        else:
            self.keep_original_checkbox.configure(state="disabled")
        if is_video_recode and not is_audio_only_mode:
            if not self.recode_options_frame.winfo_ismapped():
                self.proc_type_var.set("")
                self.update_codec_menu()
        else:
            self.recode_options_frame.pack_forget()

        # Gestiona el panel de audio
        if is_audio_recode:
            if not self.recode_audio_options_frame.winfo_ismapped():
                self.update_audio_codec_menu()
        else:
            self.recode_audio_options_frame.pack_forget()

        # Re-apila los widgets en el orden correcto
        self.recode_options_frame.pack_forget()
        self.recode_audio_options_frame.pack_forget()

        if is_video_recode and not is_audio_only_mode:
            self.recode_options_frame.pack(side="top", fill="x", padx=5, pady=5)
        if is_audio_recode:
            self.recode_audio_options_frame.pack(side="top", fill="x", padx=5, pady=5)

        # Llama a la validación central
        self._validate_recode_compatibility()

    def _validate_recode_compatibility(self):
        """Valida la compatibilidad de las opciones de recodificación y actualiza la UI."""
        mode = self.mode_selector.get()
        is_video_recode = self.recode_video_checkbox.get() == 1 and mode == "Video+Audio"
        is_audio_recode = self.recode_audio_checkbox.get() == 1

        # Limpiar y salir si no hay nada que validar
        self.recode_warning_label.pack_forget()
        if not is_video_recode and not is_audio_recode:
            self.recode_compatibility_status = "valid"
            self.update_download_button_state()
            return

        def get_ffmpeg_codec_name(friendly_name, proc_type, category):
            if not friendly_name or friendly_name == "-": return None
            db = self.ffmpeg_processor.available_encoders.get(proc_type, {}).get(category, {})
            codec_data = db.get(friendly_name)
            if codec_data: return next((key for key in codec_data if key != 'container'), None)
            return None

        # --- LÓGICA DE CONTENEDOR CORREGIDA ---
        target_container = None
        if is_video_recode:
            proc_type = self.proc_type_var.get()
            if proc_type:
                available = self.ffmpeg_processor.available_encoders.get(proc_type, {}).get("Video", {})
                target_container = available.get(self.recode_codec_menu.get(), {}).get("container")
        elif is_audio_recode:
            if mode == "Video+Audio": # Si se copia video y se recodifica audio
                target_container = ".mp4"  # Forzamos un contenedor de video seguro
            else: # Modo Solo Audio
                available = self.ffmpeg_processor.available_encoders.get("CPU", {}).get("Audio", {})
                target_container = available.get(self.recode_audio_codec_menu.get(), {}).get("container")
        
        if not target_container:
            self.recode_compatibility_status = "error"
            self.update_download_button_state()
            return
        self.recode_container_label.configure(text=target_container) 

        
        status, message = "valid", f"✅ Combinación Válida. Contenedor final: {target_container}"
        rules = self.COMPATIBILITY_RULES.get(target_container, {})
        allowed_video = rules.get("video", [])
        allowed_audio = rules.get("audio", [])

        video_info = self.video_formats.get(self.video_quality_menu.get()) or {}
        original_vcodec = (video_info.get('vcodec') or 'none').split('.')[0]
        audio_info = self.audio_formats.get(self.audio_quality_menu.get()) or {}
        original_acodec = (audio_info.get('acodec') or 'none').split('.')[0]

        if mode == "Video+Audio":
            if is_video_recode:
                proc_type = self.proc_type_var.get()
                ffmpeg_vcodec = get_ffmpeg_codec_name(self.recode_codec_menu.get(), proc_type, "Video")
                if ffmpeg_vcodec and ffmpeg_vcodec not in allowed_video:
                    status, message = "error", f"❌ El códec de video ({self.recode_codec_menu.get()}) no es compatible con {target_container}."
            else: # Copiando video
                if not allowed_video:
                    status, message = "error", f"❌ No se puede copiar video a un contenedor de solo audio ({target_container})."
                elif original_vcodec not in allowed_video and original_vcodec != 'none':
                    status, message = "warning", f"⚠️ El video original ({original_vcodec}) no es estándar en {target_container}. Se recomienda recodificar."

        if status in ["valid", "warning"]:
            if is_audio_recode:
                ffmpeg_acodec = get_ffmpeg_codec_name(self.recode_audio_codec_menu.get(), "CPU", "Audio")
                if ffmpeg_acodec and ffmpeg_acodec not in allowed_audio:
                    status, message = "error", f"❌ El códec de audio ({self.recode_audio_codec_menu.get()}) no es compatible con {target_container}."
            elif mode == "Video+Audio":
                if original_acodec not in allowed_audio and original_acodec != 'none':
                    status, message = "warning", f"⚠️ El audio original ({original_acodec}) no es compatible con {target_container}. Se recomienda recodificar."

        # --- LÓGICA DE VISUALIZACIÓN CORREGIDA ---
        self.recode_compatibility_status = status
        
        if status == "valid":
            color = "#00A400" # Un verde más visible
            self.recode_warning_label.configure(text=message, text_color=color)
        else:
            color = "#E54B4B" if status == "error" else "#E5A04B"
            self.recode_warning_label.configure(text=message, text_color=color)
        
        self.recode_warning_label.pack(pady=5, padx=5) # Siempre mostramos la etiqueta
        self.update_download_button_state()

    def toggle_fps_panel(self):
        """Muestra u oculta el panel de opciones de FPS."""
        if self.fps_checkbox.get() == 1:
            self.fps_options_frame.grid()
            # Por defecto, selecciona CFR y muestra el campo de entrada
            self.fps_mode_var.set("CFR") 
            self.toggle_fps_entry()
        else:
            self.fps_options_frame.grid_remove()

    def toggle_fps_entry_panel(self):
        if self.fps_checkbox.get() == 1:
            self.fps_value_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
            self.fps_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        else:
            self.fps_value_label.grid_remove()
            self.fps_entry.grid_remove()

    def update_codec_menu(self, *args):
        proc_type = self.proc_type_var.get()
        mode = self.mode_selector.get()
        codecs = ["-"]
        is_recode_panel_visible = self.recode_options_frame.winfo_ismapped()
        if self.ffmpeg_processor.is_detection_complete and is_recode_panel_visible and proc_type:
            category = "Audio" if mode == "Solo Audio" else "Video"
            effective_proc = "CPU" if category == "Audio" else proc_type
            available = self.ffmpeg_processor.available_encoders.get(effective_proc, {}).get(category, {})
            if available:
                codecs = list(available.keys())
        self.recode_codec_menu.configure(values=codecs, state="normal" if codecs and codecs[0] != "-" else "disabled")
        key = "video_codec" if mode == "Video+Audio" else "audio_codec"
        saved_codec = self.recode_settings.get(key)
        if saved_codec and saved_codec in codecs:
            self.recode_codec_menu.set(saved_codec)
        else:
            self.recode_codec_menu.set(codecs[0])
        self.update_profile_menu(self.recode_codec_menu.get())
        self.update_download_button_state()
        self.save_settings()  

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
        self.recode_profile_menu.configure(values=profiles, state="normal" if profiles and profiles[0] != "-" else "disabled", command=self.on_profile_selection_change)
        key = "video_profile" if mode == "Video+Audio" else "audio_profile"
        saved_profile = self.recode_settings.get(key)
        if saved_profile and saved_profile in profiles:
            self.recode_profile_menu.set(saved_profile)
        else:
            self.recode_profile_menu.set(profiles[0])
        self.on_profile_selection_change(self.recode_profile_menu.get())
        self.recode_container_label.configure(text=container)
        self.update_download_button_state()
        self.save_settings()

    def on_mode_change(self, mode):
        self.format_warning_label.pack_forget()
        self.video_quality_label.pack_forget()
        self.video_quality_menu.pack_forget()
        self.audio_quality_label.pack_forget()
        self.audio_quality_menu.pack_forget()
        self.recode_video_checkbox.deselect()
        self.recode_audio_checkbox.deselect()
        if mode == "Video+Audio":
            self.video_quality_label.pack(fill="x", padx=5, pady=(10,0))
            self.video_quality_menu.pack(fill="x", padx=5, pady=(0,5))
            self.audio_quality_label.pack(fill="x", padx=5, pady=(10,0))
            self.audio_quality_menu.pack(fill="x", padx=5, pady=(0,5))
            self.format_warning_label.pack(fill="x", padx=5, pady=(5,5))
            self.recode_video_checkbox.grid()
            self.recode_audio_checkbox.configure(text="Recodificar Audio")
            self.on_video_quality_change(self.video_quality_menu.get())
        elif mode == "Solo Audio":
            self.audio_quality_label.pack(fill="x", padx=5, pady=(10,0))
            self.audio_quality_menu.pack(fill="x", padx=5, pady=(0,5))
            self.format_warning_label.pack(fill="x", padx=5, pady=(5,5))
            self.recode_video_checkbox.grid_remove()
            self.recode_audio_checkbox.configure(text="Activar Recodificación para Audio")
            self._update_warnings()
        self.recode_main_frame._parent_canvas.yview_moveto(0)
        self.recode_main_frame.pack_forget()
        self.recode_main_frame.pack(pady=(10, 0), padx=5, fill="both", expand=True)
        self._toggle_recode_panels()

    def on_video_quality_change(self, selected_label):
        selected_format_info = self.video_formats.get(selected_label)
        if selected_format_info:
            new_width = selected_format_info.get('width')
            new_height = selected_format_info.get('height')
            if new_width and new_height and hasattr(self, 'width_entry'):
                self.width_entry.delete(0, 'end')
                self.width_entry.insert(0, str(new_width))
                self.height_entry.delete(0, 'end')
                self.height_entry.insert(0, str(new_height))
                if self.aspect_ratio_lock.get():
                    self.on_aspect_lock_change()
        self._update_warnings()
        self._validate_recode_compatibility()

    def _update_warnings(self):
        mode = self.mode_selector.get()
        warnings = []
        compatibility_issues = []
        unknown_issues = []
        if mode == "Video+Audio":
            video_info = self.video_formats.get(self.video_quality_menu.get())
            audio_info = self.audio_formats.get(self.audio_quality_menu.get())
            if not video_info or not audio_info: return
            virtual_format = {'vcodec': video_info.get('vcodec'), 'acodec': audio_info.get('acodec'), 'ext': video_info.get('ext')}
            compatibility_issues, unknown_issues = self._get_format_compatibility_issues(virtual_format)
            if "Lento" in self.video_quality_menu.get():
                warnings.append("• Formato de video lento para recodificar.")
        elif mode == "Solo Audio":
            audio_info = self.audio_formats.get(self.audio_quality_menu.get())
            if not audio_info: return
            virtual_format = {'acodec': audio_info.get('acodec')}
            compatibility_issues, unknown_issues = self._get_format_compatibility_issues(virtual_format)
            if audio_info.get('acodec') == 'none':
                unknown_issues.append("audio")
        if compatibility_issues:
            issues_str = ", ".join(compatibility_issues)
            warnings.append(f"• Requiere recodificación por códec de {issues_str}.")
        if unknown_issues:
            issues_str = ", ".join(unknown_issues)
            warnings.append(f"• Compatibilidad desconocida para el códec de {issues_str}.")
        if warnings:
            self.format_warning_label.configure(text="\n".join(warnings), text_color="#FFA500")
        else:
            legend_text = ("Guía de etiquetas en la lista:\n" "✨ Ideal: Formato óptimo para editar sin conversión.\n" "⚠️ Lento: El proceso de recodificación puede tardar más.\n" "⚠️ Recodificar: Formato no compatible con editores.")
            self.format_warning_label.configure(text=legend_text, text_color="gray")

    def _get_format_compatibility_issues(self, format_dict):
        if not format_dict: return [], []
        compatibility_issues = []
        unknown_issues = []
        raw_vcodec = format_dict.get('vcodec')
        vcodec = raw_vcodec.split('.')[0] if raw_vcodec else 'none'
        raw_acodec = format_dict.get('acodec')
        acodec = raw_acodec.split('.')[0] if raw_acodec else 'none'
        ext = format_dict.get('ext') or 'none'
        if vcodec == 'none' and 'vcodec' in format_dict:
            unknown_issues.append("video")
        elif vcodec != 'none' and vcodec not in self.EDITOR_FRIENDLY_CRITERIA["compatible_vcodecs"]:
            compatibility_issues.append(f"video ({vcodec})")
        if acodec != 'none' and acodec not in self.EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]:
            compatibility_issues.append(f"audio ({acodec})")
        if vcodec != 'none' and ext not in self.EDITOR_FRIENDLY_CRITERIA["compatible_exts"]:
            compatibility_issues.append(f"contenedor (.{ext})")
        return compatibility_issues, unknown_issues

    def sanitize_filename(self, filename):
        import unicodedata
        filename = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
        filename = re.sub(r'[^\w\s\.-]', '', filename).strip()
        filename = re.sub(r'[-\s]+', ' ', filename)
        filename = re.sub(r'[\\/:\*\?"<>|]', '', filename)
        return filename

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
        elif mode == "Desde Navegador":
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack(fill="x", padx=10, pady=(0, 10))
        else: 
            self.manual_cookie_frame.pack_forget()
            self.browser_options_frame.pack_forget()
        self.save_settings()

    def toggle_manual_thumbnail_button(self):
        is_checked = self.auto_save_thumbnail_check.get() == 1
        has_image = self.pil_image is not None
        if is_checked or not has_image: self.save_thumbnail_button.configure(state="disabled")
        else: self.save_thumbnail_button.configure(state="normal")

    def toggle_manual_subtitle_button(self):
        """Activa/desactiva el botón 'Descargar Subtítulos'."""
        is_auto_download = self.auto_download_subtitle_check.get() == 1
        has_valid_subtitle_selected = hasattr(self, 'selected_subtitle_info') and self.selected_subtitle_info is not None
        if is_auto_download or not has_valid_subtitle_selected:
            self.save_subtitle_button.configure(state="disabled")
        else:
            self.save_subtitle_button.configure(state="normal")

    def on_language_change(self, selected_language_name):
        """Se ejecuta cuando el usuario selecciona un idioma. Pobla el segundo menú."""
        possible_codes = [code for code, name in self.LANG_CODE_MAP.items() if name == selected_language_name]
        actual_lang_code = None
        for code in possible_codes:
            primary_part = code.split('-')[0].lower()
            if primary_part in self.all_subtitles:
                actual_lang_code = primary_part
                break
        if not actual_lang_code:
            actual_lang_code = possible_codes[0].split('-')[0].lower() if possible_codes else selected_language_name
        sub_list = self.all_subtitles.get(actual_lang_code, [])
        filtered_subs = []
        added_types = set()
        for sub_info in sub_list:
            ext = sub_info.get('ext')
            is_auto = sub_info.get('automatic', False)
            sub_type_key = (is_auto, ext)
            if sub_type_key in added_types:
                continue
            filtered_subs.append(sub_info)
            added_types.add(sub_type_key)

        def custom_type_sort_key(sub_info):
            is_auto = 1 if sub_info.get('automatic', False) else 0
            is_srt = 0 if sub_info.get('ext') == 'srt' else 1
            return (is_auto, is_srt)
        sorted_subs = sorted(filtered_subs, key=custom_type_sort_key)
        type_display_names = []
        self.current_subtitle_map = {}
        for sub_info in sorted_subs:
            origin = "Automático" if sub_info.get('automatic') else "Manual"
            ext = sub_info.get('ext', 'N/A')
            full_lang_code = sub_info.get('lang', '')
            display_name = self._get_subtitle_display_name(full_lang_code)
            label = f"{origin} (.{ext}) - {display_name}"
            type_display_names.append(label)
            self.current_subtitle_map[label] = sub_info 
        if type_display_names:
            self.subtitle_type_menu.configure(state="normal", values=type_display_names)
            self.subtitle_type_menu.set(type_display_names[0])
            self.on_subtitle_selection_change(type_display_names[0]) 
        else:
            self.subtitle_type_menu.configure(state="disabled", values=["-"])
            self.subtitle_type_menu.set("-")
        self.toggle_manual_subtitle_button()

    def _get_subtitle_display_name(self, lang_code):
        """Obtiene un nombre legible para un código de idioma de subtítulo, simple o compuesto."""
        parts = lang_code.split('-')
        if len(parts) == 1:
            return self.LANG_CODE_MAP.get(lang_code, lang_code)
        elif self.LANG_CODE_MAP.get(lang_code):
            return self.LANG_CODE_MAP.get(lang_code)
        else:
            original_lang = self.LANG_CODE_MAP.get(parts[0], parts[0])
            translated_part = '-'.join(parts[1:])
            translated_lang = self.LANG_CODE_MAP.get(translated_part, translated_part)
            return f"{original_lang} (Trad. a {translated_lang})"

    def on_subtitle_selection_change(self, selected_type):
        """Se ejecuta cuando el usuario selecciona un tipo/formato de subtítulo."""
        self.selected_subtitle_info = self.current_subtitle_map.get(selected_type)
        karaoke_capable_formats = ['vtt', 'ass']
        should_show_option = False
        if self.selected_subtitle_info:
            subtitle_ext = self.selected_subtitle_info.get('ext')
            if subtitle_ext in karaoke_capable_formats:
                should_show_option = True
        is_visible = self.clean_subtitle_check.winfo_ismapped()
        if should_show_option:
            if not is_visible:
                self.clean_subtitle_check.pack(padx=10, pady=(0, 5), anchor="w")
        else:
            if is_visible:
                self.clean_subtitle_check.pack_forget()
            self.clean_subtitle_check.deselect()
        print(f"Subtítulo seleccionado final: {self.selected_subtitle_info}")
        self.toggle_manual_subtitle_button()
        self.save_settings()

    def select_output_folder(self):
        folder_path = filedialog.askdirectory()
        self.lift()
        self.focus_force()
        if folder_path:
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, folder_path)
            self.default_download_path = folder_path
            self.save_settings()
            self.update_download_button_state()

    def open_last_download_folder(self):
        """Abre la carpeta de la última descarga y selecciona el archivo si es posible."""
        if not self.last_download_path or not os.path.exists(self.last_download_path):
            print("ERROR: No hay un archivo válido para mostrar o la ruta no existe.")
            return
        file_path = os.path.normpath(self.last_download_path)
        
        try:
            print(f"DEBUG: Intentando mostrar el archivo en la carpeta: {file_path}")
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(['explorer', '/select,', file_path])
            elif system == "Darwin": # macOS
                subprocess.Popen(['open', '-R', file_path])
            else: 
                subprocess.Popen(['xdg-open', os.path.dirname(file_path)])
        except Exception as e:
            print(f"Error al intentar seleccionar el archivo en la carpeta: {e}")
            messagebox.showerror("Error", f"No se pudo mostrar el archivo en la carpeta:\n{file_path}\n\nError: {e}")

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

    def _execute_subtitle_download_subprocess(self, url, subtitle_info, save_path):
        """
        Descarga un subtítulo detectando el nuevo archivo creado en la carpeta,
        evitando así todos los problemas de nombres y codificación.
        """
        try:
            output_dir = os.path.dirname(save_path)
            files_before = set(os.listdir(output_dir))
            lang_code = subtitle_info['lang']
            sub_format = subtitle_info['ext']
            output_template = os.path.join(output_dir, f"{self.sanitize_filename(self.title_entry.get())}.%(ext)s")
            command = [
                'yt-dlp', '--no-warnings', '--write-sub',
                '--sub-format', sub_format,
                '--sub-langs', lang_code,
                '--skip-download', '--no-playlist',
                '-o', output_template 
            ]
            if subtitle_info.get('automatic', False):
                command.append('--write-auto-sub')
            cookie_mode = self.cookie_mode_menu.get()
            if cookie_mode == "Archivo Manual..." and self.cookie_path_entry.get():
                command.extend(['--cookies', self.cookie_path_entry.get()])
            elif cookie_mode != "No usar":
                browser_arg = self.browser_var.get()
                profile = self.browser_profile_entry.get()
                if profile: browser_arg += f":{profile}"
                command.extend(['--cookies-from-browser', browser_arg])
            command.append(url)
            self.after(0, self.update_progress, 0, "Iniciando proceso de yt-dlp...")
            print(f"\n\nDEBUG: Comando final enviado a yt-dlp:\n{' '.join(command)}\n\n")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', creationflags=creationflags)
            for line in iter(process.stdout.readline, ''): print(line.strip())
            process.wait()
            print("--- [yt-dlp finished] ---\n")
            if process.returncode != 0:
                raise Exception("El proceso de yt-dlp falló (ver consola para detalles).")
            files_after = set(os.listdir(output_dir))
            new_files = files_after - files_before
            if not new_files:
                raise FileNotFoundError("yt-dlp terminó, pero no se detectó ningún archivo nuevo en la carpeta.")
            new_filename = new_files.pop()
            final_output_path = os.path.join(output_dir, new_filename)
            if self.clean_subtitle_check.winfo_ismapped() and self.clean_subtitle_check.get() == 1:
                self.after(0, self.update_progress, 90, "Revisando y convirtiendo formato...")
                final_output_path = clean_and_convert_vtt_to_srt(final_output_path)
            self.after(0, self.update_progress, 100, f"Subtítulo guardado en {os.path.basename(final_output_path)}")
        except Exception as e:
            self.after(0, self.update_progress, 0, f"Error: {e}")
        finally:
            self.after(0, self._reset_buttons_to_original_state)

    def save_subtitle(self):
        """
        Guarda el subtítulo seleccionado invocando a yt-dlp en un subproceso.
        """
        subtitle_info = self.selected_subtitle_info
        if not subtitle_info:
            self.update_progress(0, "Error: No hay subtítulo seleccionado.")
            return
        subtitle_ext = subtitle_info.get('ext', 'txt')
        clean_title = self.sanitize_filename(self.title_entry.get() or "subtitle")
        initial_filename = f"{clean_title}.{subtitle_ext}"
        save_path = filedialog.asksaveasfilename(
            defaultextension=f".{subtitle_ext}",
            filetypes=[(f"{subtitle_ext.upper()} Subtitle", f"*.{subtitle_ext}"), ("All files", "*.*")],
            initialfile=initial_filename
        )
        if save_path:
            video_url = self.url_entry.get()
            self.download_button.configure(state="disabled")
            self.analyze_button.configure(state="disabled")
            threading.Thread(
                target=self._execute_subtitle_download_subprocess, 
                args=(video_url, subtitle_info, save_path), 
                daemon=True
            ).start()

    def cancel_operation(self):
        """
        Maneja la cancelación de cualquier operación activa, ya sea análisis o descarga.
        Ahora termina forzosamente el proceso para liberar los bloqueos de archivo.
        """
        print("DEBUG: Botón de Cancelar presionado.")
        self.cancellation_event.set()
        self.ffmpeg_processor.cancel_current_process()
        if self.active_subprocess_pid:
            print(f"DEBUG: Intentando terminar el árbol de procesos para el PID: {self.active_subprocess_pid}")
            try:
                subprocess.run(
                    ['taskkill', '/PID', str(self.active_subprocess_pid), '/T', '/F'],
                    check=True,
                    capture_output=True, text=True
                )
                print(f"DEBUG: Proceso {self.active_subprocess_pid} y sus hijos terminados exitosamente.")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"ADVERTENCIA: No se pudo terminar el proceso {self.active_subprocess_pid} con taskkill (puede que ya haya terminado): {e}")
            self.active_subprocess_pid = None

    def start_download_thread(self):
        url = self.url_entry.get()
        output_path = self.output_path_entry.get()
        has_input = url or self.local_file_path
        has_output = output_path
        if not has_input or not has_output:
            error_msg = "Error: Falta la carpeta de salida."
            if not has_input:
                error_msg = "Error: No se ha proporcionado una URL ni se ha importado un archivo."
            self.progress_label.configure(text=error_msg)
            return
        self.download_button.configure(text="Cancelar", fg_color="red", command=self.cancel_operation)
        self.analyze_button.configure(state="disabled") 
        self.save_subtitle_button.configure(state="disabled") 
        self.cancellation_event.clear()
        self.progress_bar.set(0)
        self.update_progress(0, "Preparando proceso...")
        options = {
            "url": url, "output_path": output_path,
            "title": self.title_entry.get() or "video_descargado",
            "mode": self.mode_selector.get(),
            "video_format_label": self.video_quality_menu.get(),
            "audio_format_label": self.audio_quality_menu.get(),
            "recode_video_enabled": self.recode_video_checkbox.get() == 1,
            "recode_audio_enabled": self.recode_audio_checkbox.get() == 1,
            "keep_original_file": self.keep_original_checkbox.get() == 1,
            "recode_proc": self.proc_type_var.get(),
            "recode_codec_name": self.recode_codec_menu.get(),
            "recode_profile_name": self.recode_profile_menu.get(),
            "recode_container": self.recode_container_label.cget("text"),
            "recode_audio_enabled": self.recode_audio_checkbox.get() == 1,
            "recode_audio_codec_name": self.recode_audio_codec_menu.get(),
            "recode_audio_profile_name": self.recode_audio_profile_menu.get(),
            "speed_limit": self.speed_limit_entry.get(),
            "cookie_mode": self.cookie_mode_menu.get(),
            "cookie_path": self.cookie_path_entry.get(),
            "selected_browser": self.browser_var.get(),
            "browser_profile": self.browser_profile_entry.get(),
            "download_subtitles": self.auto_download_subtitle_check.get() == 1,
            "selected_subtitle_info": self.selected_subtitle_info,
            "fps_force_enabled": self.fps_checkbox.get() == 1,
            "fps_value": self.fps_entry.get(),
            "resolution_change_enabled": self.resolution_checkbox.get() == 1,
            "res_width": self.width_entry.get(),
            "res_height": self.height_entry.get(),
            "no_upscaling_enabled": self.no_upscaling_checkbox.get() == 1,
            "original_width": self.original_video_width,
            "original_height": self.original_video_height
        }
        self.active_operation_thread = threading.Thread(target=self._execute_download_and_recode, args=(options,), daemon=True)
        self.active_operation_thread.start()

    def _execute_download_and_recode(self, options):
        if self.local_file_path:
        # Si estamos en modo local, llamamos a la función especialista
            try:
                self._execute_local_recode(options)
            except (LocalRecodeFailedError, UserCancelledError) as e:
                # Si la función especialista falla, limpiamos los archivos temporales
                if isinstance(e, LocalRecodeFailedError) and e.temp_filepath and os.path.exists(e.temp_filepath):
                    try:
                        os.remove(e.temp_filepath)
                        print(f"DEBUG: Archivo temporal de recodificación eliminado: {e.temp_filepath}")
                    except OSError as a:
                        print(f"ERROR: No se pudo eliminar el archivo temporal '{e.temp_filepath}': {a}")
                self.on_process_finished(False, str(e), None)
            finally:
                self.active_operation_thread = None
            return # Terminamos aquí para el modo local
        process_successful = False
        downloaded_filepath = None
        recode_phase_started = False
        keep_file_on_cancel = None
        final_recoded_path = None
        cleanup_required = True
        user_facing_title = "" 

        try:
            final_output_path_str = options["output_path"]
            user_facing_title = self.sanitize_filename(options['title'])
            output_path = Path(final_output_path_str)
            title_to_check = user_facing_title

            VIDEO_EXTS = ['.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv', '.mts', '.m2ts']
            AUDIO_EXTS = ['.mp3', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.aac']
            conflicting_file = None
            for f in output_path.iterdir():
                # Comparamos el nombre del archivo sin la extensión
                if f.is_file() and f.stem.lower() == title_to_check.lower():
                    # Verificamos si la extensión corresponde a un video o audio
                    if f.suffix.lower() in VIDEO_EXTS or f.suffix.lower() in AUDIO_EXTS:
                        conflicting_file = f
                        break
            
            overwrite_allowed = False
            if conflicting_file:
                self.ui_request_data = {"type": "ask_conflict", "filename": conflicting_file.name}
                self.ui_response_event.clear()
                self.ui_request_event.set()
                self.ui_response_event.wait()
                user_choice = self.ui_response_data.get("result", "cancel")

                if user_choice == "cancel":
                    cleanup_required = False
                    raise UserCancelledError("Operación cancelada por el usuario en conflicto de archivo.")
                elif user_choice == "rename":
                    base_title = title_to_check
                    counter = 1
                    while True:
                        new_title_candidate = f"{base_title} ({counter})"
                        if not any(f.stem.lower() == new_title_candidate.lower() for f in output_path.iterdir()):
                            user_facing_title = new_title_candidate
                            break
                        counter += 1
                elif user_choice == "overwrite":
                    overwrite_allowed = True

            if self.local_file_path:
                self.after(0, self.update_progress, 0, "Usando archivo local como fuente...")
                downloaded_filepath = self.local_file_path
                cleanup_required = False
                if self.save_in_same_folder_check.get() == 1:
                    final_output_path_str = os.path.dirname(self.local_file_path)
            else:
                self.after(0, self.update_progress, 0, "Iniciando descarga...")
                cleanup_required = True

                video_format_id = self.video_formats.get(options["video_format_label"], {}).get('format_id')
                audio_format_id = self.audio_formats.get(options["audio_format_label"], {}).get('format_id')
                format_selector = ""
                postprocessors = []
                mode = options["mode"]
                output_template = os.path.join(str(output_path), f"{user_facing_title}.%(ext)s")

                if mode == "Video+Audio":
                    format_selector = f"{video_format_id}+{audio_format_id}" if video_format_id and audio_format_id else video_format_id or audio_format_id
                elif mode == "Solo Audio":
                    format_selector = audio_format_id

                if getattr(sys, 'frozen', False):
                    project_root = os.path.dirname(sys.executable)
                else:
                    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                bin_dir = os.path.join(project_root, "bin")

                ydl_opts = {
                    'format': format_selector, 
                    'outtmpl': output_template,
                    'postprocessors': postprocessors, 
                    'noplaylist': True,
                    'ffmpeg_location': bin_dir,
                    'retries': 5,
                    'fragment_retries': 5,
                }

                if overwrite_allowed:
                    ydl_opts['overwrites'] = True
                if options["download_subtitles"] and options.get("selected_subtitle_info"):
                    subtitle_info = options["selected_subtitle_info"]
                    if subtitle_info:
                        ydl_opts.update({
                            'writesubtitles': True,
                            'subtitleslangs': [subtitle_info['lang']],
                            'subtitlesformat': subtitle_info.get('ext', 'best'),
                            'writeautomaticsub': subtitle_info.get('automatic', False),
                            'embedsubtitles': mode == "Video+Audio"
                        })
                if options["speed_limit"]:
                    try: ydl_opts['ratelimit'] = float(options["speed_limit"]) * 1024 * 1024
                    except ValueError: pass

                cookie_mode = options["cookie_mode"]
                if cookie_mode == "Archivo Manual..." and options["cookie_path"]: ydl_opts['cookiefile'] = options["cookie_path"]
                elif cookie_mode != "No usar":
                    browser_arg = options["selected_browser"]
                    if options["browser_profile"]: browser_arg += f":{options['browser_profile']}"
                    ydl_opts['cookiesfrombrowser'] = (browser_arg,)

                downloaded_filepath = download_media(options["url"], ydl_opts, self.update_progress, self.cancellation_event)

            if self.clean_subtitle_check.get() and ydl_opts.get('writesubtitles'):
                base_name = os.path.splitext(downloaded_filepath)[0]
                lang_code = ydl_opts['subtitleslangs'][0]
                vtt_path = f"{base_name}.{lang_code}.vtt" 
                if os.path.exists(vtt_path):
                    self.after(0, self.update_progress, 95, "Simplificando subtítulo...")
                    clean_and_convert_vtt_to_srt(vtt_path)

            if not downloaded_filepath or not os.path.exists(downloaded_filepath):
                raise Exception("La descarga falló o el archivo no se encontró.")
            if self.cancellation_event.is_set():
                raise UserCancelledError("Proceso cancelado por el usuario.")
            
            self._save_thumbnail_if_enabled(downloaded_filepath)

            if options.get("recode_video_enabled") or options.get("recode_audio_enabled"):
                recode_phase_started = True
                self.after(0, self.update_progress, 0, "Preparando recodificación...")
                final_title = user_facing_title + "_recoded"
                final_ffmpeg_params = []

                mode = options["mode"]
                if mode == "Video+Audio":
                    if options["recode_video_enabled"]:
                        proc = options["recode_proc"]
                        codec_db = self.ffmpeg_processor.available_encoders[proc]["Video"]
                        codec_data = codec_db.get(options["recode_codec_name"])
                        if not codec_data: raise Exception("Codec de video no encontrado.")

                        ffmpeg_codec_name = list(filter(lambda k: k != 'container', codec_data.keys()))[0]
                        profile_params = codec_data[ffmpeg_codec_name].get(options["recode_profile_name"])
                        if not profile_params: raise Exception("Perfil de recodificación de video no válido.")

                        if "CUSTOM_BITRATE" in profile_params:
                            try:
                                bitrate_mbps = float(self.custom_bitrate_entry.get())
                                bitrate_k = int(bitrate_mbps * 1000)
                            except (ValueError, TypeError):
                                raise Exception("El valor del bitrate personalizado no es válido.")

                            if "nvenc" in ffmpeg_codec_name:
                                rc_mode = "vbr" if "VBR" in profile_params else "cbr"
                                profile_params = f"-c:v {ffmpeg_codec_name} -preset p5 -rc {rc_mode} -b:v {bitrate_k}k -maxrate {bitrate_k}k"
                            elif "amf" in ffmpeg_codec_name:
                                rc_mode = "vbr_peak" if "VBR" in profile_params else "cbr"
                                profile_params = f"-c:v {ffmpeg_codec_name} -quality balanced -rc {rc_mode} -b:v {bitrate_k}k -maxrate {bitrate_k}k"
                            else:
                                profile_params = f"-c:v {ffmpeg_codec_name} -b:v {bitrate_k}k -maxrate {bitrate_k}k -bufsize {bitrate_k*2}k -pix_fmt yuv420p"

                        final_ffmpeg_params.extend(profile_params.split())

                        video_filters = []
                        if options.get("fps_force_enabled") and options.get("fps_value"):
                            video_filters.append(f'fps={options["fps_value"]}')

                        if options.get("resolution_change_enabled"):
                            try:
                                width, height = int(options["res_width"]), int(options["res_height"])
                                if options.get("no_upscaling_enabled"):
                                    original_width, original_height = options.get("original_width", 0), options.get("original_height", 0)
                                    if original_width > 0 and width > original_width: width = original_width
                                    if original_height > 0 and height > original_height: height = original_height
                                video_filters.append(f'scale={width}:{height}')
                            except (ValueError, TypeError): pass

                        if video_filters:
                            final_ffmpeg_params.extend(['-vf', ",".join(video_filters)])
                    else:
                        final_ffmpeg_params.extend(["-c:v", "copy"])

                if options["recode_audio_enabled"]:
                    audio_codec_db = self.ffmpeg_processor.available_encoders["CPU"]["Audio"]
                    audio_codec_data = audio_codec_db.get(options["recode_audio_codec_name"])
                    if audio_codec_data:
                        ffmpeg_audio_codec = list(filter(lambda k: k != 'container', audio_codec_data.keys()))[0]
                        audio_profile_params = audio_codec_data[ffmpeg_audio_codec].get(options["recode_audio_profile_name"])
                        if audio_profile_params: final_ffmpeg_params.extend(audio_profile_params.split())
                elif mode == "Video+Audio":
                    final_ffmpeg_params.extend(["-c:a", "copy"])

                final_container = options["recode_container"]
                final_recoded_path = os.path.join(final_output_path_str, f"{final_title}{final_container}")

                recode_opts = {
                    "input_file": downloaded_filepath,
                    "output_file": final_recoded_path,
                    "duration": self.video_duration,
                    "ffmpeg_params": final_ffmpeg_params
                }

                final_path_from_recode = self.ffmpeg_processor.execute_recode(recode_opts, self.update_progress, self.cancellation_event)

                if not options.get("keep_original_file", False):
                    if os.path.exists(downloaded_filepath):
                        os.remove(downloaded_filepath)

                self.on_process_finished(True, "Recodificación completada", final_path_from_recode)
                process_successful = True
            else: 
                self.on_process_finished(True, "Descarga completada", downloaded_filepath)
                process_successful = True

        except (UserCancelledError, Exception) as e:
            is_cancel = isinstance(e, UserCancelledError)
            error_message = str(e) if is_cancel else f"Ocurrió un error inesperado: {e}"
            should_ask_user = recode_phase_started and not options.get("keep_original_file", False) and not self.is_shutting_down

            if should_ask_user:
                self.ui_request_data = {
                    "type": "ask_yes_no", "title": "Fallo en la Recodificación",
                    "message": "La descarga del archivo original se completó, pero la recodificación falló o fue cancelada.\n\n¿Deseas conservar el archivo original descargado?"
                }
                self.ui_response_event.clear()
                self.ui_request_event.set()
                self.ui_response_event.wait()
                
                if self.ui_response_data.get("result", False):
                    keep_file_on_cancel = downloaded_filepath
                    self.on_process_finished(False, "Recodificación cancelada. Archivo original conservado.", None)
                else:
                    self.on_process_finished(False, error_message, None)
            else:
                if recode_phase_started and options.get("keep_original_file", False):
                    keep_file_on_cancel = downloaded_filepath
                    self.on_process_finished(False, "Recodificación cancelada. Archivo original conservado.", None)
                else:
                    self.on_process_finished(False, error_message, None)
        finally:
            self.active_subprocess_pid = None
            if not process_successful and cleanup_required:
                try:
                    gc.collect()
                    time.sleep(1) 
                    base_title_for_cleanup = user_facing_title.replace("_recoded", "")
                    for filename in os.listdir(options["output_path"]):
                        if not filename.startswith(base_title_for_cleanup):
                            continue
                        file_path_to_check = os.path.join(options["output_path"], filename)
                        should_preserve = False
                        if keep_file_on_cancel:
                            normalized_preserved_path = os.path.normpath(keep_file_on_cancel)
                            normalized_path_to_check = os.path.normpath(file_path_to_check)
                            if normalized_path_to_check == normalized_preserved_path:
                                should_preserve = True
                            else:
                                base_preserved_name = os.path.splitext(os.path.basename(keep_file_on_cancel))[0]
                                known_sidecar_exts = ('.srt', '.vtt', '.ass', '.ssa', '.json3', '.srv1', '.srv2', '.srv3', '.ttml', '.smi', '.tml', '.lrc', '.xml', '.jpg', '.jpeg', '.png')
                                if filename.startswith(base_preserved_name) and filename.lower().endswith(known_sidecar_exts):
                                    should_preserve = True
                        if should_preserve:
                            print(f"DEBUG: Conservando archivo solicitado o asociado: {file_path_to_check}")
                            continue
                        else:
                            print(f"DEBUG: Eliminando archivo temporal, parcial o no deseado: {file_path_to_check}")
                            os.remove(file_path_to_check)
                except Exception as cleanup_e:
                    print(f"ERROR: Falló el proceso de limpieza de archivos: {cleanup_e}")
            self.active_operation_thread = None

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
            command=self.original_download_command
        )
        self.toggle_manual_subtitle_button()
        self.update_download_button_state()

    def _save_thumbnail_if_enabled(self, base_filepath):
        """Guarda la miniatura si la opción está activada, usando la ruta del archivo base."""
        if self.auto_save_thumbnail_check.get() == 1 and self.pil_image and base_filepath:
            try:
                # Actualiza la UI desde el hilo de trabajo
                self.after(0, self.update_progress, 98, "Guardando miniatura...")
                
                output_directory = os.path.dirname(base_filepath)
                # Usa el nombre del archivo descargado para mayor consistencia
                clean_title = os.path.splitext(os.path.basename(base_filepath))[0]
                
                # Si es un archivo recodificado, quita el sufijo para que coincida con el original
                if clean_title.endswith("_recoded"):
                    clean_title = clean_title.rsplit('_recoded', 1)[0]

                thumb_path = os.path.join(output_directory, f"{clean_title}.jpg")
                self.pil_image.convert("RGB").save(thumb_path, quality=95)
                print(f"DEBUG: Miniatura guardada automáticamente en {thumb_path}")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo guardar la miniatura automáticamente: {e}")

    def on_process_finished(self, success, message, filepath):
        """Callback unificado para el final del proceso. Se ejecuta en el hilo principal."""
        def _update_ui():
            self.last_download_path = filepath
            self.progress_label.configure(text=message)

            if self.local_file_path:
                self.download_button.configure(text="Iniciar Proceso", state="normal", command=self.original_download_command, fg_color=self.original_download_fg_color)
                self.analyze_button.configure(state="disabled")
            else:
                self._reset_buttons_to_original_state()

            self.ui_request_event.clear()
            self.ui_response_event.clear()

            if success:
                self.progress_bar.set(1)
                self.open_folder_button.configure(state="normal")
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

    def start_analysis_thread(self, event=None):
        url = self.url_entry.get()
        if url and self.local_file_path:
            self.reset_to_url_mode()
            self.url_entry.insert(0, url)
        if self.analyze_button.cget("text") == "Cancelar":
            return
        if not url:
            return
        if url in self.analysis_cache:
            cached_entry = self.analysis_cache[url]
            if (time.time() - cached_entry['timestamp']) < self.CACHE_TTL:
                print("DEBUG: Resultado encontrado en caché. Cargando...")
                self.update_progress(100, "Resultado encontrado en caché. Cargando...")
                self.on_analysis_complete(cached_entry['data'])
                return
        self.analyze_button.configure(text="Cancelar", fg_color="red", command=self.cancel_operation)
        self.download_button.configure(state="disabled") 
        self.open_folder_button.configure(state="disabled")
        self.save_subtitle_button.configure(state="disabled") 
        self.cancellation_event.clear()
        self.progress_label.configure(text="Analizando...") 
        self.progress_bar.start() 
        self.create_placeholder_label("Analizando...")
        self.title_entry.delete(0, 'end')
        self.title_entry.insert(0, "Analizando...")
        self.video_quality_menu.configure(state="disabled", values=["-"])
        self.audio_quality_menu.configure(state="disabled", values=["-"])
        self.subtitle_lang_menu.configure(state="disabled", values=["-"])
        self.subtitle_lang_menu.set("-")
        self.subtitle_type_menu.configure(state="disabled", values=["-"])
        self.subtitle_type_menu.set("-") 
        self.toggle_manual_subtitle_button() 
        threading.Thread(target=self._run_analysis_subprocess, args=(url,), daemon=True).start()

    def _run_analysis_subprocess(self, url):
        """
        Ejecuta yt-dlp como un subproceso con un timeout para analizar la URL,
        proporcionando feedback más granular al usuario.
        """
        full_stdout = ""
        try:
            self.after(0, self.update_progress, 0, "Analizando URL...")
            command = [
                'yt-dlp', '-j', url, '--no-warnings',
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                '--referer', url,
                '--no-playlist',
                '--list-subs',
                '--write-auto-subs' 
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
            self.active_subprocess_pid = process.pid 
            json_output_lines = []
            info_received = False

            start_time = time.time()
            while True:
                if self.cancellation_event.is_set():
                    print("DEBUG: Análisis detectó señal de cancelación. Terminando proceso.")
                    process.terminate()
                    raise UserCancelledError("Análisis cancelado por el usuario.")
                if time.time() - start_time > 60:
                    process.terminate()
                    raise subprocess.TimeoutExpired(cmd=command, timeout=60)
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
        self.progress_bar.stop() 
        if info and not error_message:
            self.progress_bar.set(1) 
        else:
            self.progress_bar.set(0) 
        if info and not error_message:
            url = self.url_entry.get()
            self.analysis_cache[url] = {
                'data': info,
                'timestamp': time.time()
            }
            print(f"DEBUG: Resultado para '{url}' guardado en caché.")
        self.create_placeholder_label("Miniatura")
        self.title_entry.delete(0, 'end') 
        if info:
            self.title_entry.insert(0, info.get('title', 'Sin título'))
            self.video_duration = info.get('duration', 0)
            self.video_id = info.get('id', None)
            self.original_video_width = info.get('width', 0)
            self.original_video_height = info.get('height', 0)
            if hasattr(self, 'width_entry'):
                self.width_entry.delete(0, 'end')
                self.width_entry.insert(0, str(self.original_video_width))
            if hasattr(self, 'height_entry'):
                self.height_entry.delete(0, 'end')
                self.height_entry.insert(0, str(self.original_video_height))
            self.populate_format_menus(info)
            self._update_warnings()
            self.update_download_button_state()
            if thumbnail_url := info.get('thumbnail'):
                threading.Thread(target=self.load_thumbnail, args=(thumbnail_url,), daemon=True).start()
            self.update_estimated_size()
        else:
            self.title_entry.insert(0, error_message or "ERROR: No se pudo obtener la información.")
            self.create_placeholder_label("Fallo el análisis")
            self._clear_subtitle_menus()
        self._reset_buttons_to_original_state()
        self.toggle_manual_subtitle_button() 
        self._validate_recode_compatibility()

    def load_thumbnail(self, path_or_url, is_local=False):
        try:
            self.after(0, self.create_placeholder_label, "Cargando miniatura...")
            if is_local:
                with open(path_or_url, 'rb') as f:
                    img_data = f.read()
            else:
                response = requests.get(path_or_url, timeout=10)
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
                self.thumbnail_label.image = ctk_image # Guarda una referencia para evitar que se borre
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

                # Lógica para determinar si es lento (sin cambios)
                is_slow = False
                if vcodec in self.SLOW_FORMAT_CRITERIA["video_codecs"] and height >= self.SLOW_FORMAT_CRITERIA["min_height_for_slow"]:
                    is_slow = True
                elif height >= self.SLOW_FORMAT_CRITERIA["min_height_for_slow"] and fps >= self.SLOW_FORMAT_CRITERIA["min_fps_for_slow"]:
                    is_slow = True
                elif height >= 3840:
                    is_slow = True

                # Construcción de la etiqueta con la lógica corregida
                if acodec != 'none':
                    label = f"{f.get('height', 0)}p ({ext}, {vcodec}+{acodec}) - {size_mb}"
                else:
                    label = f"{f.get('height', 0)}p ({ext}, {vcodec}) - {size_mb}"

                compatibility_issues, unknown_issues = self._get_format_compatibility_issues(f)

                tags = []
                if is_slow:
                    tags.append("⚠️ Lento")

                # La lógica ahora considera ambas listas de problemas
                if not compatibility_issues and not unknown_issues and not is_slow:
                    tags.append("✨ Ideal")
                elif compatibility_issues or unknown_issues:
                    tags.append("⚠️ Recodificar")

                if tags:
                    label += f" ({' y '.join(tags)})"

                video_entries.append({'label': label, 'format': f, 'has_audio': acodec != 'none'})
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                abr = f.get('abr')
                acodec = f.get('acodec', 'N/A').split('.')[0]
                language_code = f.get('language')
                format_note = f.get('format_note', '').lower()
                lang_name = "Idioma Desconocido"
                if language_code:
                    normalized_lang_code = language_code.replace('_', '-')
                    full_code_match = self.LANG_CODE_MAP.get(normalized_lang_code.lower())
                    if full_code_match:
                        lang_name = full_code_match
                    else:
                        primary_code = normalized_lang_code.split('-')[0].lower()
                        lang_name = self.LANG_CODE_MAP.get(primary_code, language_code)
                if lang_name == 'Español':
                    if 'latino' in format_note or 'latin' in format_note:
                        lang_name = 'Español (Latinoamérica)'
                    elif 'castellano' in format_note or 'españa' in format_note or 'spain' in format_note:
                        lang_name = 'Español (España)'
                lang_prefix = f"{lang_name} - "
                if abr and abr > 0:
                    label = f"{lang_prefix}{abr:.0f}kbps ({acodec}, {ext}) - {size_mb}"
                else:
                    label = f"{lang_prefix}Audio ({acodec}, {ext}) - {size_mb}"

                # Añadir etiqueta de compatibilidad
                if acodec in self.EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]:
                    label += " ✨"
                else:
                    label += " ⚠️"

                audio_entries.append({'label': label, 'format': f})

        def custom_video_sort_key(entry):
            f = entry['format']
            size_is_known = 0 if "Tamaño desc." in entry['label'] else 1
            height = f.get('height') or 0
            fps = f.get('fps') or 0
            return (size_is_known, height, fps)

        def custom_audio_sort_key(entry):
            f = entry['format']
            lang_code_raw = f.get('language') or ''
            normalized_lang_code = lang_code_raw.replace('_', '-')
            lang_priority = self.LANGUAGE_ORDER.get(normalized_lang_code, -1) 
            if lang_priority == -1:
                primary_lang_code = normalized_lang_code.split('-')[0]
                lang_priority = self.LANGUAGE_ORDER.get(primary_lang_code, self.DEFAULT_PRIORITY)
            quality = f.get('abr') or 0
            return (lang_priority, -quality)
        video_entries.sort(key=custom_video_sort_key, reverse=True)
        audio_entries.sort(key=custom_audio_sort_key)
        self.video_formats = {entry['label']: {
            'format_id': entry['format'].get('format_id'), 
            'has_audio': entry.get('has_audio', False), 
            'vcodec': entry['format'].get('vcodec'), 
            'ext': entry['format'].get('ext'),
            'width': entry['format'].get('width'),    
            'height': entry['format'].get('height')  
        } for entry in video_entries}
        self.audio_formats = {
            entry['label']: {
                'format_id': entry['format'].get('format_id'),
                'acodec': (acodec_val.split('.')[0] if (acodec_val := entry['format'].get('acodec')) else 'none'),
                'ext': entry['format'].get('ext')
            } for entry in audio_entries
        }
        v_opts = list(self.video_formats.keys()) or ["-"]
        a_opts = list(self.audio_formats.keys()) or ["-"]
        self.video_quality_menu.configure(state="normal" if v_opts[0] != "-" else "disabled", values=v_opts)
        self.video_quality_menu.set(v_opts[0])
        self.on_video_quality_change(v_opts[0])
        self.audio_quality_menu.configure(state="normal" if a_opts[0] != "-" else "disabled", values=a_opts)
        self.audio_quality_menu.set(a_opts[0])

        self.all_subtitles = {}
        
        def process_sub_list(sub_list, is_auto):
            lang_code_map_3_to_2 = {
                'spa': 'es', 'eng': 'en', 'jpn': 'ja', 
                'fra': 'fr', 'deu': 'de', 'por': 'pt',
                'ita': 'it', 'kor': 'ko', 'rus': 'ru'
            }
            for lang_code, subs in sub_list.items():
                primary_part = lang_code.replace('_', '-').split('-')[0].lower()
                grouped_lang_code = lang_code_map_3_to_2.get(primary_part, primary_part)
                for sub_info in subs:
                    sub_info['lang'] = lang_code 
                    sub_info['automatic'] = is_auto
                    self.all_subtitles.setdefault(grouped_lang_code, []).append(sub_info)
        process_sub_list(info.get('subtitles', {}), is_auto=False)
        process_sub_list(info.get('automatic_captions', {}), is_auto=True)
        
        def custom_language_sort_key(lang_code):
            """
            Función de ordenamiento que prioriza los idiomas en LANGUAGE_ORDER
            y luego ordena el resto alfabéticamente.
            """
            priority = self.LANGUAGE_ORDER.get(lang_code, self.DEFAULT_PRIORITY)
            return (priority, lang_code)
        available_languages = sorted(self.all_subtitles.keys(), key=custom_language_sort_key)
        if available_languages:
            self.auto_download_subtitle_check.configure(state="normal")
            lang_display_names = [self.LANG_CODE_MAP.get(lang, lang) for lang in available_languages]
            self.subtitle_lang_menu.configure(state="normal", values=lang_display_names)
            self.subtitle_lang_menu.set(lang_display_names[0])
            self.on_language_change(lang_display_names[0])
        else:
            self._clear_subtitle_menus()
        self.toggle_manual_subtitle_button()