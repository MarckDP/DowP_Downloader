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
import yt_dlp

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
        self.update_idletasks()
        win_width = 500
        win_height = 180
        master_geo = self.master.geometry()
        master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
        pos_x = master_x + (master_width // 2) - (win_width // 2)
        pos_y = master_y + (master_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
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

    VIDEO_EXTENSIONS = {'mp4', 'mkv', 'webm', 'mov', 'flv', 'avi'}
    AUDIO_EXTENSIONS = {'m4a', 'mp3', 'ogg', 'opus', 'flac', 'wav'}
    SINGLE_STREAM_AUDIO_CONTAINERS = {'.mp3', '.wav', '.flac', '.ac3'}
    FORMAT_MUXER_MAP = {
        ".m4a": "mp4",
        ".wma": "asf"
}

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
        "compatible_vcodecs": [
            "h264", "avc1",  # H.264
            "hevc", "h265",  # H.265
            "prores",        # Apple ProRes
            "dnxhd", "dnxhr", # Avid DNxHD/HR
            "cfhd",          # GoPro CineForm
            "mpeg2video",    # Común en cámaras más antiguas y DVDs
            "dvvideo"        # Formato de cámaras MiniDV
        ],
        "compatible_acodecs": ["aac", "mp4a", "pcm_s16le", "pcm_s24le", "mp3", "ac3"],
        "compatible_exts": ["mp4", "mov", "mxf", "mts", "m2ts", "avi"],
    }

    COMPATIBILITY_RULES = {
        ".mov": {
            "video": ["prores_aw", "prores_ks", "dnxhd", "cfhd", "qtrle", "hap", "h264_videotoolbox", "libx264"],
            "audio": ["pcm_s16le", "pcm_s24le", "alac"]
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
        ".ogg": { "video": [], "audio": ["libvorbis", "libopus"] },
        ".ac3": { "video": [], "audio": ["ac3"] },
        ".wma": { "video": [], "audio": ["wmav2"] },
        ".mxf": { "video": ["mpeg2video", "dnxhd"], "audio": ["pcm_s16le", "pcm_s24le"] },
        ".flac": { "video": [], "audio": ["flac"] },
        ".mp3": { "video": [], "audio": ["libmp3lame"] },
        ".m4a": { "video": [], "audio": ["aac", "alac"] },
        ".opus": { "video": [], "audio": ["libopus"] },
        ".wav": { "video": [], "audio": ["pcm_s16le", "pcm_s24le"] }
    }

    class CompromiseDialog(ctk.CTkToplevel):
        """Diálogo que pregunta al usuario si acepta una calidad de descarga alternativa."""
        def __init__(self, master, details_message):
            super().__init__(master)
            self.title("Calidad no Disponible")
            self.lift()
            self.attributes("-topmost", True)
            self.grab_set()

            self.result = "cancel"

            container = ctk.CTkFrame(self, fg_color="transparent")
            container.pack(padx=20, pady=20, fill="both", expand=True)

            main_label = ctk.CTkLabel(container, text="No se pudo obtener la calidad seleccionada.", font=ctk.CTkFont(size=15, weight="bold"), wraplength=450)
            main_label.pack(pady=(0, 10), anchor="w")
            
            details_frame = ctk.CTkFrame(container, fg_color="transparent")
            details_frame.pack(pady=5, anchor="w")
            ctk.CTkLabel(details_frame, text="La mejor alternativa disponible es:", font=ctk.CTkFont(size=12)).pack(anchor="w")
            
            details_label = ctk.CTkLabel(details_frame, text=details_message, font=ctk.CTkFont(size=13, weight="bold"), text_color="#52a2f2", wraplength=450, justify="left")
            details_label.pack(anchor="w")

            question_label = ctk.CTkLabel(container, text="¿Deseas descargar esta versión en su lugar?", font=ctk.CTkFont(size=12), wraplength=450)
            question_label.pack(pady=10, anchor="w")

            button_frame = ctk.CTkFrame(container, fg_color="transparent")
            button_frame.pack(pady=15, fill="x")
            button_frame.grid_columnconfigure((0, 1), weight=1)

            accept_btn = ctk.CTkButton(button_frame, text="Sí, Descargar", command=lambda: self.set_result("accept"))
            cancel_btn = ctk.CTkButton(button_frame, text="No, Cancelar", fg_color="red", hover_color="#990000", command=lambda: self.set_result("cancel"))
            
            accept_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
            cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")

            # Forzamos un ciclo de actualización completo antes de centrar
            self.update()
            self.update_idletasks()
            
            win_width = self.winfo_reqwidth()
            win_height = self.winfo_reqheight()
            
            master_geo = self.master.geometry()
            master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
            
            pos_x = master_x + (master_width // 2) - (win_width // 2)
            pos_y = master_y + (master_height // 2) - (win_height // 2)
            self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

        def set_result(self, result):
            self.result = result
            self.destroy()
    
    class SimpleMessageDialog(ctk.CTkToplevel):
        """Un diálogo simple para mostrar un mensaje de error o información."""
        def __init__(self, master, title, message):
            super().__init__(master)
            self.title(title)
            self.lift()
            self.attributes("-topmost", True)
            self.grab_set()
            self.resizable(False, False)

            message_label = ctk.CTkLabel(self, text=message, font=ctk.CTkFont(size=13), wraplength=450, justify="left")
            message_label.pack(padx=20, pady=20, fill="both", expand=True)
            
            ok_button = ctk.CTkButton(self, text="OK", command=self.destroy, width=100)
            ok_button.pack(padx=20, pady=(0, 20))

            self.update()
            
            win_width = self.winfo_reqwidth()
            win_height = self.winfo_reqheight()
            
            master_geo = self.master.geometry()
            master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
            
            pos_x = master_x + (master_width // 2) - (win_width // 2)
            pos_y = master_y + (master_height // 2) - (win_height // 2)
            self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

    def _get_best_available_info(self, url, options):
        """Ejecuta una simulación con yt-dlp para ver qué descargaría con 'bestvideo+bestaudio'."""
        try:
            command = [
                'yt-dlp', '-j', '--simulate', url, '--no-warnings', '--no-playlist',
                '-f', 'bv+ba' # Usamos bv+ba para video, ba para solo audio
            ]
            if options["mode"] == "Solo Audio":
                command[-1] = 'ba'

            # Añadir cookies si es necesario
            cookie_mode = options["cookie_mode"]
            if cookie_mode == "Archivo Manual..." and options["cookie_path"]:
                command.extend(['--cookies', options["cookie_path"]])
            elif cookie_mode != "No usar":
                browser_arg = options["selected_browser"]
                if options["browser_profile"]: browser_arg += f":{options['browser_profile']}"
                command.extend(['--cookies-from-browser', browser_arg])

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore', creationflags=creationflags)
            
            info = json.loads(result.stdout)
            
            if options["mode"] == "Solo Audio":
                abr = info.get('abr', 0)
                acodec = info.get('acodec', 'N/A').split('.')[0]
                return f"Audio: ~{abr:.0f} kbps ({acodec})"

            vcodec = info.get('vcodec', 'N/A').split('.')[0]
            resolution = f"{info.get('width')}x{info.get('height')}"
            abr = info.get('abr', 0)
            acodec = info.get('acodec', 'N/A').split('.')[0]
            
            return f"Video: {resolution} ({vcodec})  |  Audio: ~{abr:.0f} kbps ({acodec})"

        except (subprocess.CalledProcessError, json.JSONDecodeError, Exception) as e:
            print(f"ERROR: Falló la simulación de descarga: {e}")
            return "No se pudieron obtener los detalles."

    def __init__(self):
        super().__init__()
        self.is_shutting_down = False
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.title("DowP")
        win_width = 835
        win_height = 900
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = (screen_width // 2) - (win_width // 2)
        pos_y = (screen_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
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
        self.original_video_width = 0
        self.original_video_height = 0
        self.has_video_streams = False
        self.has_audio_streams = False

    def create_entry_context_menu(self, widget):
        """Crea y muestra un menú contextual para un widget de entrada de texto."""
        menu = tkinter.Menu(self, tearoff=0)
        def cut_text():
            widget.event_generate("<<Copy>>")
            if widget.select_present():
                widget.delete("sel.first", "sel.last")
                self.after(10, self.update_download_button_state)
        def paste_text():
            if widget.select_present():
                widget.delete("sel.first", "sel.last")
            try:
                widget.insert("insert", self.clipboard_get())
                self.after(10, self.update_download_button_state)
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
            elif request_type in ["ask_conflict", "ask_conflict_recode"]:
                filename = self.ui_request_data.get("filename", "")
                dialog = ConflictDialog(self, filename)
                self.wait_window(dialog) 
                self.lift()
                self.focus_force()
                self.ui_response_data["result"] = dialog.result
                self.ui_response_event.set()
            elif request_type == "ask_compromise":
                details = self.ui_request_data.get("details", "Detalles no disponibles.")
                dialog = self.CompromiseDialog(self, details)
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
            self.loading_window.update_progress(status_info.get("message"), -1)
            return
        if status == "warning":
            if self.loading_window and self.loading_window.winfo_exists():
                self.loading_window.error_state = False
                try:
                    default_color = self.analyze_button.cget("fg_color")
                    self.loading_window.progress_bar.configure(progress_color=default_color)
                except Exception:
                    self.loading_window.progress_bar.configure(progress_color=["#3a7ebf", "#346ead"])
            self.after(0, self.loading_window.update_progress, status_info.get("message"), 95)
            self.after(500, self.on_setup_complete)
            return
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
            snoozed = self.ffmpeg_update_snooze_until and datetime.now() < self.ffmpeg_update_snooze_until
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
                    self.ffmpeg_update_snooze_until = None
                    self.save_settings()
                else:
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
            self.after(100, self._wait_for_thread_to_finish_and_destroy)
        else:
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
        self.url_entry.bind("<<Paste>>", lambda e: self.after(50, self.update_download_button_state))
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

        ctk.CTkLabel(options_scroll_frame, text="Descargar Fragmento", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=10, pady=(5, 2))
        
        fragment_frame = ctk.CTkFrame(options_scroll_frame)
        fragment_frame.pack(fill="x", padx=5, pady=(0, 10))

        self.fragment_checkbox = ctk.CTkCheckBox(fragment_frame, text="Activar corte de fragmento", command=lambda: (self._toggle_fragment_panel(), self.update_download_button_state()))
        self.fragment_checkbox.pack(padx=10, pady=5, anchor="w")

        self.fragment_options_frame = ctk.CTkFrame(fragment_frame, fg_color="transparent")
        
        self.fragment_options_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.fragment_options_frame, text="Inicio:").grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")
        
        start_time_frame = ctk.CTkFrame(self.fragment_options_frame, fg_color="transparent")
        start_time_frame.grid(row=0, column=1, pady=5, sticky="ew")
        
        self.start_h = ctk.CTkEntry(start_time_frame, width=40, placeholder_text="00")
        self.start_m = ctk.CTkEntry(start_time_frame, width=40, placeholder_text="00")
        self.start_s = ctk.CTkEntry(start_time_frame, width=40, placeholder_text="00")
                
        self.start_h.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(start_time_frame, text=":", font=ctk.CTkFont(size=14)).pack(side="left", padx=5)
        self.start_m.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(start_time_frame, text=":", font=ctk.CTkFont(size=14)).pack(side="left", padx=5)
        self.start_s.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(self.fragment_options_frame, text="Final:").grid(row=1, column=0, padx=(0, 5), pady=5, sticky="w")

        end_time_frame = ctk.CTkFrame(self.fragment_options_frame, fg_color="transparent")
        end_time_frame.grid(row=1, column=1, pady=5, sticky="ew")

        self.end_h = ctk.CTkEntry(end_time_frame, width=40, placeholder_text="00")
        self.end_m = ctk.CTkEntry(end_time_frame, width=40, placeholder_text="00")
        self.end_s = ctk.CTkEntry(end_time_frame, width=40, placeholder_text="00")

        self.end_h.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(end_time_frame, text=":", font=ctk.CTkFont(size=14)).pack(side="left", padx=5)
        self.end_m.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(end_time_frame, text=":", font=ctk.CTkFont(size=14)).pack(side="left", padx=5)
        self.end_s.pack(side="left", fill="x", expand=True)

        self.keep_original_on_clip_check = ctk.CTkCheckBox(self.fragment_options_frame, text="Conservar completo (solo modo URL)")
        self.keep_original_on_clip_check.grid(row=3, column=0, columnspan=2, pady=(5,0), sticky="w")

        self.time_warning_label = ctk.CTkLabel(self.fragment_options_frame, text="", text_color="orange", wraplength=280, justify="left")
        # La posicionaremos en la fila 3, ocupando ambas columnas
        self.time_warning_label.grid(row=4, column=0, columnspan=2, pady=(5,0), sticky="w")

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
        self.clean_subtitle_check = ctk.CTkCheckBox(subtitle_options_frame, text="Convertir y estandarizar a formato SRT")
        self.clean_subtitle_check.pack(padx=10, pady=(0, 5), anchor="w")

        ctk.CTkLabel(options_scroll_frame, text="Cookies", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=10, pady=(5, 2))
        cookie_options_frame = ctk.CTkFrame(options_scroll_frame)
        cookie_options_frame.pack(fill="x", padx=5, pady=(0, 10))
        self.cookie_mode_menu = ctk.CTkOptionMenu(cookie_options_frame, values=["No usar", "Archivo Manual...", "Desde Navegador"], command=self.on_cookie_mode_change)
        self.cookie_mode_menu.pack(fill="x", padx=10, pady=(0, 5))
        self.manual_cookie_frame = ctk.CTkFrame(cookie_options_frame, fg_color="transparent")
        self.cookie_path_entry = ctk.CTkEntry(self.manual_cookie_frame, placeholder_text="Ruta al archivo cookies.txt...")
        self.cookie_path_entry.pack(fill="x")
        self.cookie_path_entry.bind("<KeyRelease>", self._on_cookie_detail_change)
        self.select_cookie_file_button = ctk.CTkButton(self.manual_cookie_frame, text="Elegir Archivo...", command=lambda: self.select_cookie_file())
        self.select_cookie_file_button.pack(fill="x", pady=(5,0))
        self.browser_options_frame = ctk.CTkFrame(cookie_options_frame, fg_color="transparent")
        ctk.CTkLabel(self.browser_options_frame, text="Navegador:").pack(padx=10, pady=(5,0), anchor="w")
        self.browser_var = ctk.StringVar(value=self.selected_browser_saved)
        self.browser_menu = ctk.CTkOptionMenu(self.browser_options_frame, values=["chrome", "firefox", "edge", "opera", "vivaldi", "brave"], variable=self.browser_var, command=self._on_cookie_detail_change)
        self.browser_menu.pack(fill="x", padx=10)
        ctk.CTkLabel(self.browser_options_frame, text="Perfil (Opcional):").pack(padx=10, pady=(5,0), anchor="w")
        self.browser_profile_entry = ctk.CTkEntry(self.browser_options_frame, placeholder_text="Ej: Default, Profile 1")
        self.browser_profile_entry.bind("<Button-3>", lambda e: self.create_entry_context_menu(self.browser_profile_entry))
        self.browser_profile_entry.pack(fill="x", padx=10)
        self.browser_profile_entry.bind("<KeyRelease>", self._on_cookie_detail_change)
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
        self.audio_options_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
        self.audio_quality_label = ctk.CTkLabel(self.audio_options_frame, text="Calidad de Audio:", anchor="w")
        self.audio_quality_menu = ctk.CTkOptionMenu(self.audio_options_frame, state="disabled", values=["-"], command=lambda _: (self._update_warnings(), self._validate_recode_compatibility()))
        self.use_all_audio_tracks_check = ctk.CTkCheckBox(self.audio_options_frame, text="Aplicar la recodificación a todas las pistas de audio", command=self._on_use_all_audio_tracks_change)
        self.audio_quality_label.pack(fill="x", padx=5, pady=(10,0))
        self.audio_quality_menu.pack(fill="x", padx=5, pady=(0,5))

        legend_text = (         
            "Guía de etiquetas en la lista:\n"
            "✨ Ideal: Formato óptimo para editar sin conversión.\n"
            "⚠️ Lento: El proceso de recodificación puede tardar más.\n"
            "⚠️ Recodificar: Formato no compatible con editores."
        )
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

        self.recode_toggle_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        self.recode_toggle_frame.pack(side="top", fill="x", padx=10, pady=(0, 10))
        self.recode_toggle_frame.grid_columnconfigure((0, 1), weight=1)

        self.recode_video_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Recodificar Video", command=self._toggle_recode_panels, state="disabled")
        self.recode_video_checkbox.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Recodificar Audio", command=self._toggle_recode_panels, state="disabled")
        self.recode_audio_checkbox.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.keep_original_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Mantener los archivos originales", state="disabled", command=self.save_settings)
        self.keep_original_checkbox.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        self.keep_original_checkbox.select()

        self.recode_warning_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        self.recode_warning_frame.pack(pady=0, padx=10, fill="x")
        
        self.recode_warning_label = ctk.CTkLabel(self.recode_warning_frame, text="", wraplength=400, justify="left", font=ctk.CTkFont(weight="bold"))
        self.recode_warning_label.pack(pady=5, padx=5, fill="both", expand=True)


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
        self.recode_audio_codec_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], state="disabled", command=self.update_audio_profile_menu)
        self.recode_audio_codec_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.recode_audio_options_frame, text="Perfil de Audio:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_profile_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], state="disabled", command=lambda _: self._validate_recode_compatibility())
        self.recode_audio_profile_menu.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        local_import_frame = ctk.CTkFrame(self.recode_main_frame)
        local_import_frame.pack(side="bottom", fill="x", padx=10, pady=(15, 5))
        ctk.CTkLabel(local_import_frame, text="¿Tienes un archivo existente?", font=ctk.CTkFont(weight="bold")).pack()
        self.import_button = ctk.CTkButton(local_import_frame, text="Importar Archivo Local para Recodificar", command=self.import_local_file)
        self.import_button.pack(fill="x", padx=10, pady=5)
        self.save_in_same_folder_check = ctk.CTkCheckBox(local_import_frame, text="Guardar en la misma carpeta que el original", command=self._on_save_in_same_folder_change)
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

        # Vinculamos la lógica de auto-salto para el tiempo de INICIO
        self.start_h.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.start_h, self.start_m), self.update_download_button_state()))
        self.start_m.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.start_m, self.start_s), self.update_download_button_state()))
        self.start_s.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.start_s), self.update_download_button_state()))

        # Vinculamos la lógica de auto-salto para el tiempo de FINAL
        self.end_h.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.end_h, self.end_m), self.update_download_button_state()))
        self.end_m.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.end_m, self.end_s), self.update_download_button_state()))
        self.end_s.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.end_s), self.update_download_button_state()))

        # Aseguramos que el panel inicie oculto
        self._toggle_fragment_panel()

        self._check_for_ui_requests()

    def time_str_to_seconds(self, time_str):
        """Convierte un string HH:MM:SS a segundos."""
        if not time_str: return 0
        parts = time_str.split(':')
        seconds = 0
        if len(parts) == 3:
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return seconds

    def _get_compatible_audio_codecs(self, target_container):
        """
        Devuelve una lista de nombres de códecs de audio amigables que son
        compatibles con un contenedor específico.
        """
        all_audio_codecs = self.ffmpeg_processor.available_encoders.get("CPU", {}).get("Audio", {})
        if not target_container or target_container == "-":
            return list(all_audio_codecs.keys()) or ["-"]

        rules = self.COMPATIBILITY_RULES.get(target_container, {})
        allowed_ffmpeg_codecs = rules.get("audio", [])
        
        compatible_friendly_names = []

        for friendly_name, details in all_audio_codecs.items():
            ffmpeg_codec_name = next((key for key in details if key != 'container'), None)
            if ffmpeg_codec_name in allowed_ffmpeg_codecs:
                compatible_friendly_names.append(friendly_name)
        
        # Si la lista está vacía después de filtrar, devuelve ["-"]
        return compatible_friendly_names if compatible_friendly_names else ["-"]

    def _toggle_fragment_panel(self):
        """Muestra u oculta las opciones para cortar fragmentos."""
        if self.fragment_checkbox.get() == 1:
            self.fragment_options_frame.pack(fill="x", padx=10, pady=(0,5))
        else:
            self.fragment_options_frame.pack_forget()

    def _handle_time_input(self, event, widget, next_widget=None):
        """Valida la entrada de tiempo y salta al siguiente campo."""
        text = widget.get()
        cleaned_text = "".join(filter(str.isdigit, text))
        final_text = cleaned_text[:2]
        
        if text != final_text:
            widget.delete(0, "end")
            widget.insert(0, final_text)

        if len(final_text) == 2 and next_widget:
            next_widget.focus()
            next_widget.select_range(0, 'end')

    def _get_formatted_time(self, h_widget, m_widget, s_widget):
        """Lee los campos de tiempo segmentados y los formatea como HH:MM:SS."""
        h = h_widget.get()
        m = m_widget.get()
        s = s_widget.get()

        if not h and not m and not s:
            return "" 

        h = h.zfill(2) if h else "00"
        m = m.zfill(2) if m else "00"
        s = s.zfill(2) if s else "00"

        return f"{h}:{m}:{s}"

    def _clean_ansi_codes(self, text):
        """Elimina los códigos de escape ANSI (colores) del texto."""
        if not text:
            return ""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

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
            self.auto_save_thumbnail_check.pack_forget()
            self.cancellation_event.clear()
            self.progress_label.configure(text=f"Analizando archivo local: {os.path.basename(filepath)}...")
            self.progress_bar.start()
            self.open_folder_button.configure(state="disabled")
            threading.Thread(target=self._process_local_file_info, args=(filepath,), daemon=True).start()

    def _process_local_file_info(self, filepath):
        info = self.ffmpeg_processor.get_local_media_info(filepath)

        def update_ui():
            self.keep_original_on_clip_check.configure(state="disabled")
            self.progress_bar.stop()
            if not info:
                self.progress_label.configure(text="Error: No se pudo analizar el archivo.")
                self.progress_bar.set(0)
                return
            self.reset_ui_for_local_file()
            self.local_file_path = filepath

            self.keep_original_checkbox.select()
            self.keep_original_checkbox.configure(state="disabled")
            
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
                    'index': video_stream.get('index', 0), # <-- LÍNEA AÑADIDA
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

                    # Gestionar la visibilidad de la casilla para múltiples pistas de audio
                    if hasattr(self, 'use_all_audio_tracks_check'):
                        if len(audio_labels) > 1:
                            self.use_all_audio_tracks_check.pack(padx=5, pady=(5,0), anchor="w")
                            self.use_all_audio_tracks_check.deselect()
                        else:
                            self.use_all_audio_tracks_check.pack_forget()
                        self.audio_quality_menu.configure(state="normal")

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
            self._on_save_in_same_folder_change()
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
        self.keep_original_on_clip_check.configure(state="normal")
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
        self.auto_save_thumbnail_check.pack(padx=20, pady=(0, 10), anchor="w", after=self.save_thumbnail_button)
        self.auto_save_thumbnail_check.configure(state="normal")
        self.keep_original_checkbox.configure(state="normal")
        self.update_download_button_state()
        self.save_in_same_folder_check.deselect()
        self._on_save_in_same_folder_change()
        self.use_all_audio_tracks_check.pack_forget()


    def _execute_local_recode(self, options):
        """
        Función dedicada exclusivamente a la recodificación de un archivo local.
        CORREGIDO: Reorganiza la construcción de parámetros para evitar ambigüedades.
        """
        source_path = self.local_file_path
        output_dir = self.output_path_entry.get()
        if self.save_in_same_folder_check.get() == 1:
            output_dir = os.path.dirname(source_path)
        
        final_title = self.sanitize_filename(options['title']) + "_recoded"
        final_container = options["recode_container"]
        if not options['recode_video_enabled'] and not options['recode_audio_enabled']:
            # Obtenemos la extensión (ej: .mkv) del archivo original
            _, original_extension = os.path.splitext(source_path)
            final_container = original_extension
        base_name_with_ext = f"{final_title}{final_container}"
        base_name, ext = os.path.splitext(base_name_with_ext)

        final_output_path = os.path.join(output_dir, base_name_with_ext)
        temp_output_path = os.path.join(output_dir, f"{base_name}_temp{ext}")
        backup_file_path = None

        try:
            # --- 1. Manejo de Conflicto de Archivos (Sin cambios) ---
            output_path_candidate = Path(final_output_path)
            if output_path_candidate.exists():
                self.ui_request_data = {"type": "ask_conflict_recode", "filename": output_path_candidate.name}
                self.ui_request_event.set(); self.ui_response_event.wait(); self.ui_response_event.clear()
                user_choice = self.ui_response_data.get("result", "cancel")

                if user_choice == "cancel":
                    raise UserCancelledError("Operación cancelada por el usuario.")
                elif user_choice == "rename":
                    base_title = self.sanitize_filename(options['title']) + "_recoded"
                    counter = 1
                    while Path(output_dir) / f"{base_title} ({counter}){final_container}".exists():
                        counter += 1
                    final_title = f"{base_title} ({counter})"
                    final_output_path = os.path.join(output_dir, f"{final_title}{final_container}")
                    temp_output_path = final_output_path + ".temp"
                elif user_choice == "overwrite":
                    backup_file_path = final_output_path + ".bak"
                    if os.path.exists(backup_file_path): os.remove(backup_file_path)
                    os.rename(final_output_path, backup_file_path)
            
            # --- 2. Construcción de Parámetros de FFmpeg (LÓGICA CORREGIDA) ---
            final_ffmpeg_params = []

            # Parámetros de Video
            if options['mode'] != "Solo Audio" and options["recode_video_enabled"]:
                final_ffmpeg_params.extend(["-metadata:s:v:0", "rotate=0"])
                proc = options["recode_proc"]
                codec_db = self.ffmpeg_processor.available_encoders[proc]["Video"]
                codec_data = codec_db.get(options["recode_codec_name"])
                ffmpeg_codec_name = next((k for k in codec_data if k != 'container'), None)
                profile_params = codec_data[ffmpeg_codec_name].get(options["recode_profile_name"])
                # ... (resto de la lógica de bitrate, filtros, etc. no cambia)
                if "CUSTOM_BITRATE" in profile_params:
                    bitrate_mbps = float(self.custom_bitrate_entry.get())
                    bitrate_k = int(bitrate_mbps * 1000)
                    if "nvenc" in ffmpeg_codec_name:
                        profile_params = f"-c:v {ffmpeg_codec_name} -preset p5 -rc vbr -b:v {bitrate_k}k -maxrate {bitrate_k}k"
                    else:
                        profile_params = f"-c:v {ffmpeg_codec_name} -b:v {bitrate_k}k -maxrate {bitrate_k}k -bufsize {bitrate_k*2}k -pix_fmt yuv422p"
                final_ffmpeg_params.extend(profile_params)
                
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
            elif options['mode'] != "Solo Audio":
                final_ffmpeg_params.extend(["-c:v", "copy"])

            # Parámetros de Audio (Lógica Corregida)
            is_pro_video_format = False
            if options["recode_video_enabled"]:
                codec_name = options["recode_codec_name"]
                if "ProRes" in codec_name or "DNxH" in codec_name:
                    is_pro_video_format = True
            
            # --- Parámetros de Audio (Lógica Simplificada y Corregida) ---
            recode_audio = options["recode_audio_enabled"]
            is_pro_video_format = False

            # Primero, determinamos si se está usando un códec de video profesional
            if options['mode'] != "Solo Audio" and options["recode_video_enabled"]:
                codec_name = options["recode_codec_name"]
                if "ProRes" in codec_name or "DNxH" in codec_name:
                    is_pro_video_format = True

            # Ahora, decidimos qué hacer con el audio con reglas claras
            if is_pro_video_format:
                # Regla 1: Para códecs de video Pro, SIEMPRE se recodifica el audio a PCM para máxima compatibilidad.
                final_ffmpeg_params.extend(["-c:a", "pcm_s16le"])
            elif recode_audio:
                # Regla 2: Si el usuario activó "Recodificar Audio", usamos su selección.
                audio_codec_db = self.ffmpeg_processor.available_encoders["CPU"]["Audio"]
                audio_codec_data = audio_codec_db.get(options["recode_audio_codec_name"])
                ffmpeg_audio_codec = next((k for k in audio_codec_data if k != 'container'), None)
                audio_profile_params = audio_codec_data[ffmpeg_audio_codec].get(options["recode_audio_profile_name"])
                if audio_profile_params:
                    final_ffmpeg_params.extend(audio_profile_params) # NOTA: Se cambió a .extend()
            else:
                # Regla 3: Si ninguna de las anteriores es cierta, simplemente copiamos el audio original.
                final_ffmpeg_params.extend(["-c:a", "copy"])

            # Parámetros de Fragmento (pre_params)
            pre_params = []
            if options.get("fragment_enabled"):
                if options.get("start_time"): pre_params.extend(['-ss', options.get("start_time")])
                if options.get("end_time"): pre_params.extend(['-to', options.get("end_time")])
            
            # Selección de Pista de Audio
            selected_audio_stream_index = None
            if self.use_all_audio_tracks_check.get() == 1 and len(self.audio_formats) > 1:
                selected_audio_stream_index = "all"
            else:
                selected_audio_info = self.audio_formats.get(self.audio_quality_menu.get(), {})
                if selected_audio_info.get('format_id', '').startswith('local_audio_'):
                    selected_audio_stream_index = int(selected_audio_info['format_id'].split('_')[-1])
            
            selected_video_label = self.video_quality_menu.get()
            selected_video_info = self.video_formats.get(selected_video_label, {})
            selected_video_stream_index = selected_video_info.get('index')

            recode_opts = {
                "input_file": source_path,
                "output_file": temp_output_path,
                "duration": self.video_duration,
                "ffmpeg_params": final_ffmpeg_params,
                "pre_params": pre_params,
                "selected_audio_stream_index": selected_audio_stream_index,
                "selected_video_stream_index": selected_video_stream_index, # <-- LÍNEA AÑADIDA
                "mode": options['mode']
            }
            self.ffmpeg_processor.execute_recode(recode_opts, self.update_progress, self.cancellation_event)

            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, final_output_path)
            if backup_file_path and os.path.exists(backup_file_path):
                os.remove(backup_file_path)

            self.after(0, self.on_process_finished, True, "Recodificación local completada.", final_output_path)
        except (UserCancelledError, Exception) as e:
            if os.path.exists(temp_output_path):
                try: os.remove(temp_output_path)
                except OSError as clean_e: print(f"ERROR: No se pudo eliminar el archivo temporal: {clean_e}")
            if backup_file_path and os.path.exists(backup_file_path):
                try: os.rename(backup_file_path, final_output_path)
                except OSError as restore_e: print(f"ERROR CRÍTICO: No se pudo restaurar el respaldo: {restore_e}")
            raise LocalRecodeFailedError(str(e), temp_filepath=temp_output_path)
        
    def _on_save_in_same_folder_change(self):
        """
        Actualiza el estado de la carpeta de salida según la casilla
        'Guardar en la misma carpeta'.
        """
        # Comprueba si la casilla está marcada
        if self.save_in_same_folder_check.get() == 1 and self.local_file_path:
            # Si está marcada y hay un archivo local cargado:

            # 1. Obtiene la ruta de la carpeta del archivo original
            output_dir = os.path.dirname(self.local_file_path)

            # 2. Habilita temporalmente la entrada para poder modificarla
            self.output_path_entry.configure(state="normal")

            # 3. Borra el contenido actual y muestra la nueva ruta
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, output_dir)

            # 4. Desactiva la entrada y el botón '...' para que no se puedan editar
            self.output_path_entry.configure(state="disabled")
            self.select_folder_button.configure(state="disabled")
        else:
            # Si la casilla está desmarcada o no estamos en modo local:

            # 1. Habilita la entrada y el botón '...'
            self.output_path_entry.configure(state="normal")
            self.select_folder_button.configure(state="normal")

            # 2. Restaura la última carpeta de salida que el usuario seleccionó
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, self.default_download_path)
            
        self.update_download_button_state()

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
            if self.aspect_ratio_lock.get():
                try:
                    if hasattr(self, 'original_video_width') and self.original_video_width > 0:
                        self.current_aspect_ratio = self.original_video_width / self.original_video_height
                except (ValueError, ZeroDivisionError, AttributeError):
                    self.current_aspect_ratio = None
        else:
            self.resolution_manual_frame.grid_remove()
            try:
                dims = preset.split('(')[1].split(')')[0]
                width_str, height_str = dims.split('x')
                width, height = int(width_str), int(height_str)
                self.width_entry.delete(0, 'end')
                self.width_entry.insert(0, width_str)
                self.height_entry.delete(0, 'end')
                self.height_entry.insert(0, height_str)
                if self.aspect_ratio_lock.get():
                    self.current_aspect_ratio = width / height
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
        """Puebla el menú de códecs de audio, filtrando por compatibilidad con el contenedor de video."""
        target_container = self.recode_container_label.cget("text")
        
        # Obtenemos la lista de códecs compatibles usando nuestro nuevo motor
        compatible_codecs = self._get_compatible_audio_codecs(target_container)
        
        if not compatible_codecs:
            compatible_codecs = ["-"]

        self.recode_audio_codec_menu.configure(values=compatible_codecs, state="normal" if compatible_codecs[0] != "-" else "disabled")
        
        saved_codec = self.recode_settings.get("video_audio_codec")
        if saved_codec and saved_codec in compatible_codecs:
            self.recode_audio_codec_menu.set(saved_codec)
        else:
            # Solo intenta acceder a [0] si la lista no está vacía.
            if compatible_codecs:
                self.recode_audio_codec_menu.set(compatible_codecs[0])
            
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
        self._validate_recode_compatibility()

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
        self.update_audio_codec_menu() 

    def update_download_button_state(self, *args):
        """
        Valida TODAS las condiciones necesarias y actualiza el estado del botón de descarga.
        """
        if self.url_entry.get().strip():
            self.analyze_button.configure(state="normal")
        else:
            self.analyze_button.configure(state="disabled")
        try:
            # --- Validación de Tiempo de Fragmento ---
            self.time_warning_label.configure(text="") # Oculta el mensaje por defecto
            times_are_valid = True
            if self.fragment_checkbox.get() == 1 and self.video_duration > 0:
                start_str = self._get_formatted_time(self.start_h, self.start_m, self.start_s)
                end_str = self._get_formatted_time(self.end_h, self.end_m, self.end_s)

                start_seconds = self.time_str_to_seconds(start_str)
                end_seconds = self.time_str_to_seconds(end_str)

                if start_seconds >= self.video_duration:
                    self.time_warning_label.configure(text="⚠ El tiempo de inicio no puede ser mayor a la duración.")
                    times_are_valid = False
                # Si hay un tiempo final, validarlo
                elif end_seconds > 0 and end_seconds > self.video_duration:
                    self.time_warning_label.configure(text="⚠ El tiempo final no puede ser mayor a la duración.")
                    times_are_valid = False
                elif end_seconds > 0 and start_seconds >= end_seconds:
                    self.time_warning_label.configure(text="⚠ El tiempo de inicio debe ser menor que el final.")
                    times_are_valid = False
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
                # Una acción es válida si se recodifica video, O se recodifica audio, O se corta un fragmento.
                is_fragment_clip_on = self.fragment_checkbox.get() == 1
                if not is_video_recode_on and not is_audio_recode_on and not is_fragment_clip_on:
                    action_is_selected_for_local_mode = False
            if base_conditions_met and recode_config_is_valid and action_is_selected_for_local_mode and self.recode_compatibility_status in ["valid", "warning"] and times_are_valid:
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

        if self.local_file_path:
            # En modo local, la casilla siempre está marcada y deshabilitada para proteger el archivo.
            self.keep_original_checkbox.select()
            self.keep_original_checkbox.configure(state="disabled")
        else:
            # En modo URL, la habilitación depende de si hay una recodificación activa.
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
        self.recode_warning_frame.pack_forget()
        mode = self.mode_selector.get()
        is_video_recode = self.recode_video_checkbox.get() == 1 and mode == "Video+Audio"
        is_audio_recode = self.recode_audio_checkbox.get() == 1

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
            is_pro_video_format = False
            if is_video_recode:
                codec_name = self.recode_codec_menu.get()
                if "ProRes" in codec_name or "DNxH" in codec_name:
                    is_pro_video_format = True
            
            if is_pro_video_format and not is_audio_recode and original_acodec in ['aac', 'mp3', 'opus', 'vorbis']:
                status, message = "error", f"❌ Incompatible: No se puede copiar audio {original_acodec.upper()} a un video {codec_name}. Debes recodificar el audio a un formato sin compresión (ej: WAV)."
            else:
                if is_audio_recode:
                    ffmpeg_acodec = get_ffmpeg_codec_name(self.recode_audio_codec_menu.get(), "CPU", "Audio")
                    if ffmpeg_acodec and ffmpeg_acodec not in allowed_audio:
                        status, message = "error", f"❌ El códec de audio ({self.recode_audio_codec_menu.get()}) no es compatible con {target_container}."
                elif mode == "Video+Audio":
                    if original_acodec not in allowed_audio and original_acodec != 'none':
                        status, message = "warning", f"⚠️ El audio original ({original_acodec}) no es estándar en {target_container}. Se recomienda recodificar."

        self.recode_compatibility_status = status
        
        if status == "valid":
            color = "#00A400" # Un verde más visible
            self.recode_warning_label.configure(text=message, text_color=color)
        else:
            color = "#E54B4B" if status == "error" else "#E5A04B"
            self.recode_warning_label.configure(text=message, text_color=color)

        self.recode_warning_frame.pack(after=self.recode_toggle_frame, pady=5, padx=10, fill="x")

        if hasattr(self, 'use_all_audio_tracks_check') and self.use_all_audio_tracks_check.winfo_ismapped():
            is_multi_track_available = len(self.audio_formats) > 1

            # Si el contenedor final es uno de los de pista única
            if target_container in self.SINGLE_STREAM_AUDIO_CONTAINERS:
                # Desactivamos la casilla y la deseleccionamos
                self.use_all_audio_tracks_check.configure(state="disabled")
                self.use_all_audio_tracks_check.deselect()
                self.audio_quality_menu.configure(state="normal")
            # Si el contenedor SÍ soporta múltiples pistas Y hay varias pistas disponibles
            elif is_multi_track_available:
                # La activamos
                self.use_all_audio_tracks_check.configure(state="normal")
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
        # 1. Ocultamos todos los elementos para empezar con un lienzo limpio
        self.format_warning_label.pack_forget()
        self.video_quality_label.pack_forget()
        self.video_quality_menu.pack_forget()
        if hasattr(self, 'audio_options_frame'):
            self.audio_options_frame.pack_forget()

        # 2. Reseteamos las casillas Y la selección de procesador (CPU/GPU)
        self.recode_video_checkbox.deselect()
        self.recode_audio_checkbox.deselect()
        self.proc_type_var.set("") # <-- ESTO ES CLAVE PARA EL RESETEO

        # 3. Mostramos los widgets en el orden correcto según el modo seleccionado
        if mode == "Video+Audio":
            # Orden: Video, luego Audio, luego advertencias
            self.video_quality_label.pack(fill="x", padx=5, pady=(10, 0))
            self.video_quality_menu.pack(fill="x", padx=5, pady=(0, 5))
            if hasattr(self, 'audio_options_frame'):
                self.audio_options_frame.pack(fill="x")
            self.format_warning_label.pack(fill="x", padx=5, pady=(5, 5))

            self.recode_video_checkbox.grid()
            self.recode_audio_checkbox.configure(text="Recodificar Audio")
            self.on_video_quality_change(self.video_quality_menu.get())

        elif mode == "Solo Audio":
            # Aquí solo mostramos el contenedor de audio
            if hasattr(self, 'audio_options_frame'):
                self.audio_options_frame.pack(fill="x")
            self.format_warning_label.pack(fill="x", padx=5, pady=(5, 5))

            self.recode_video_checkbox.grid_remove()
            self.recode_audio_checkbox.configure(text="Activar Recodificación para Audio")
            self._update_warnings()

        # 4. Forzamos la actualización de la UI y los menús de recodificación
        self.recode_main_frame._parent_canvas.yview_moveto(0)
        self.recode_main_frame.pack_forget()
        self.recode_main_frame.pack(pady=(10, 0), padx=5, fill="both", expand=True)
        self._toggle_recode_panels()
        self.update_codec_menu()
        self.update_audio_codec_menu()

    def _on_use_all_audio_tracks_change(self):
        """Gestiona el estado del menú de audio cuando el checkbox cambia."""
        if self.use_all_audio_tracks_check.get() == 1:
            self.audio_quality_menu.configure(state="disabled")
        else:
            self.audio_quality_menu.configure(state="normal")

    def on_video_quality_change(self, selected_label):
        # Busca la información del formato de video seleccionado
        selected_format_info = self.video_formats.get(selected_label)

        if selected_format_info:
            # Si el video seleccionado es [Combinado], deshabilita el menú de audio.
            if selected_format_info.get('is_combined'):
                self.audio_quality_menu.configure(state="disabled")
            # Si es un video-solo, habilita el menú de audio para que se pueda elegir uno.
            else:
                self.audio_quality_menu.configure(state="normal")

            # Actualiza la resolución en el panel de recodificación
            new_width = selected_format_info.get('width')
            new_height = selected_format_info.get('height')
            if new_width and new_height and hasattr(self, 'width_entry'):
                self.width_entry.delete(0, 'end')
                self.width_entry.insert(0, str(new_width))
                self.height_entry.delete(0, 'end')
                self.height_entry.insert(0, str(new_height))
                if self.aspect_ratio_lock.get():
                    self.on_aspect_lock_change()

        # Actualiza las advertencias y validaciones como siempre
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

    def create_placeholder_label(self, text="Miniatura", font_size=14):
        if self.thumbnail_label: self.thumbnail_label.destroy()
        font = ctk.CTkFont(size=font_size)
        self.thumbnail_label = ctk.CTkLabel(self.thumbnail_container, text=text, font=font)
        self.thumbnail_label.pack(expand=True, fill="both")
        self.pil_image = None
        if hasattr(self, 'save_thumbnail_button'): self.save_thumbnail_button.configure(state="disabled")
        if hasattr(self, 'auto_save_thumbnail_check'):
            self.auto_save_thumbnail_check.deselect()
            self.auto_save_thumbnail_check.configure(state="normal")

    def _on_cookie_detail_change(self, event=None):
        """Callback for when specific cookie details (path, browser, profile) change."""
        print("DEBUG: Cookie details changed. Clearing analysis cache.")
        self.analysis_cache.clear()
        self.save_settings()

    def on_cookie_mode_change(self, mode):
        """Muestra u oculta las opciones de cookies según el modo seleccionado."""
        print("DEBUG: Cookie mode changed. Clearing analysis cache.")
        self.analysis_cache.clear()

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
        """
        Se ejecuta cuando el usuario selecciona un tipo/formato de subtítulo.
        CORREGIDO: Ahora muestra la opción de conversión para CUALQUIER formato que no sea SRT.
        """
        self.selected_subtitle_info = self.current_subtitle_map.get(selected_type)
        should_show_option = False
        if self.selected_subtitle_info:
            subtitle_ext = self.selected_subtitle_info.get('ext')
            if subtitle_ext != 'srt':
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
                self.last_download_path = save_path
                self.open_folder_button.configure(state="normal")
                self.update_progress(100, f"Miniatura guardada en {os.path.basename(save_path)}")
            except Exception as e: self.update_progress(0, f"Error al guardar miniatura: {e}")

    def _execute_subtitle_download_subprocess(self, url, subtitle_info, save_path):
        """
        Descarga un subtítulo detectando el nuevo archivo creado en la carpeta.
        CORREGIDO: Se simplificó la construcción del comando para evitar errores.
        """
        try:
            output_dir = os.path.dirname(save_path)
            files_before = set(os.listdir(output_dir))
            lang_code = subtitle_info['lang']
            base_name_with_ext = os.path.basename(save_path)
            base_name = os.path.splitext(base_name_with_ext)[0]
            output_template = os.path.join(output_dir, f"{base_name}.%(ext)s")
            command = [
                'yt-dlp', '--no-warnings', '--write-sub',
                '--sub-langs', lang_code,
                '--skip-download', '--no-playlist',
                '-o', output_template 
            ]
            if self.clean_subtitle_check.winfo_ismapped() and self.clean_subtitle_check.get() == 1:
                command.extend(['--sub-format', 'best/vtt/best'])
                command.extend(['--convert-subs', 'srt'])
            else:
                command.extend(['--sub-format', subtitle_info['ext']])
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
            command.extend(['--ffmpeg-location', self.ffmpeg_processor.ffmpeg_path])    
            command.append(url)
            self.after(0, self.update_progress, 0, "Iniciando proceso de yt-dlp...")
            print(f"\n\nDEBUG: Comando final enviado a yt-dlp:\n{' '.join(command)}\n\n")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', creationflags=creationflags)
            stdout_lines = []
            stderr_lines = []
            def read_stream(stream, lines_buffer):
                for line in iter(stream.readline, ''):
                    lines_buffer.append(line.strip())
            stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
            stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines))
            stdout_thread.start()
            stderr_thread.start()
            stdout_thread.join()
            stderr_thread.join()
            process.wait()
            print("--- [yt-dlp finished] ---\n")
            if process.returncode != 0:
                full_error_output = "\n".join(stdout_lines) + "\n" + "\n".join(stderr_lines)
                raise Exception(f"El proceso de yt-dlp falló:\n{full_error_output}")
            files_after = set(os.listdir(output_dir))
            new_files = files_after - files_before
            if not new_files:
                raise FileNotFoundError("yt-dlp terminó, pero no se detectó ningún archivo de subtítulo nuevo.")
            new_filename = new_files.pop()
            final_output_path = os.path.join(output_dir, new_filename)
            if final_output_path.lower().endswith('.srt'):
                self.after(0, self.update_progress, 90, "Limpiando y estandarizando formato SRT...")
                final_output_path = clean_and_convert_vtt_to_srt(final_output_path)
            self.after(0, self.on_process_finished, True, f"Subtítulo guardado en {os.path.basename(final_output_path)}", final_output_path)
        except Exception as e:
            self.after(0, self.on_process_finished, False, f"Error al descargar subtítulo: {e}", None)

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
            "original_height": self.original_video_height,
            "fragment_enabled": self.fragment_checkbox.get() == 1,
            "start_time": self._get_formatted_time(self.start_h, self.start_m, self.start_s),
            "end_time": self._get_formatted_time(self.end_h, self.end_m, self.end_s),
            "keep_original_on_clip": self.keep_original_on_clip_check.get() == 1 # <--- AÑADE ESTA LÍNEA
        }
        self.active_operation_thread = threading.Thread(target=self._execute_download_and_recode, args=(options,), daemon=True)
        self.active_operation_thread.start()

    def _execute_download_and_recode(self, options):
        if self.local_file_path:
            try:
                self._execute_local_recode(options)
            except (LocalRecodeFailedError, UserCancelledError) as e:
                if isinstance(e, LocalRecodeFailedError) and e.temp_filepath and os.path.exists(e.temp_filepath):
                    try:
                        os.remove(e.temp_filepath)
                        print(f"DEBUG: Archivo temporal de recodificación eliminado: {e.temp_filepath}")
                    except OSError as a:
                        print(f"ERROR: No se pudo eliminar el archivo temporal '{e.temp_filepath}': {a}")
                self.after(0, self.on_process_finished, False, str(e), None)
            finally:
                self.active_operation_thread = None
            return
        process_successful = False
        downloaded_filepath = None
        recode_phase_started = False
        keep_file_on_cancel = None
        final_recoded_path = None
        cleanup_required = True
        user_facing_title = "" 
        backup_file_path = None
        audio_extraction_fallback = False
        temp_video_for_extraction = None
        try:
            if options["mode"] == "Solo Audio" and not self.audio_formats and self.video_formats:
                audio_extraction_fallback = True
                print("DEBUG: No hay pistas de audio dedicadas. Se activó el fallback de extracción desde el video.")
                best_video_label = next(iter(self.video_formats))
                options["video_format_label"] = best_video_label
            final_output_path_str = options["output_path"]
            user_facing_title = self.sanitize_filename(options['title'])
            output_path = Path(final_output_path_str)
            title_to_check = user_facing_title
            VIDEO_EXTS = ['.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv', '.mts', '.m2ts']
            AUDIO_EXTS = ['.mp3', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.aac']
            conflicting_file = None
            for f in output_path.iterdir():
                if f.is_file() and f.stem.lower() == title_to_check.lower():
                    if f.suffix.lower() in VIDEO_EXTS or f.suffix.lower() in AUDIO_EXTS:
                        conflicting_file = f
                        break
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
                    try:
                        backup_file_path = str(conflicting_file) + ".bak"
                        if os.path.exists(backup_file_path): os.remove(backup_file_path)
                        os.rename(conflicting_file, backup_file_path)
                    except OSError as e:
                        raise Exception(f"No se pudo respaldar el archivo original: {e}")
            self.after(0, self.update_progress, 0, "Iniciando descarga...")
            cleanup_required = True
            video_format_info = self.video_formats.get(options["video_format_label"], {})
            audio_format_info = self.audio_formats.get(options["audio_format_label"], {})
            mode = options["mode"]
            output_template = os.path.join(options["output_path"], f"{user_facing_title}.%(ext)s")
            precise_selector = ""
            video_format_info = self.video_formats.get(options["video_format_label"], {})
            audio_format_info = self.audio_formats.get(options["audio_format_label"], {})
            video_format_id = video_format_info.get('format_id')
            audio_format_id = audio_format_info.get('format_id')
            if audio_extraction_fallback:
                precise_selector = video_format_id
                print(f"DEBUG: Fallback activado. Selector de descarga forzado: {precise_selector}")
            elif options["mode"] == "Video+Audio":
                is_combined = video_format_info.get('is_combined', False)
                if is_combined and video_format_id:
                    precise_selector = video_format_id
                elif video_format_id and audio_format_id:
                    precise_selector = f"{video_format_id}+{audio_format_id}"
            elif options["mode"] == "Solo Audio":
                precise_selector = audio_format_id
            else:
                video_format_id = video_format_info.get('format_id')
                audio_format_id = audio_format_info.get('format_id')
                if mode == "Video+Audio":
                    is_combined = video_format_info.get('is_combined', False)
                    if is_combined and video_format_id:
                        precise_selector = video_format_id
                    elif video_format_id and audio_format_id:
                        precise_selector = f"{video_format_id}+{audio_format_id}"
                elif mode == "Solo Audio":
                    precise_selector = audio_format_id
            if getattr(sys, 'frozen', False):
                project_root = os.path.dirname(sys.executable)
            else:
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            bin_dir = os.path.join(project_root, "bin")
            ydl_opts = {
                'outtmpl': output_template,
                'postprocessors': [],
                'noplaylist': True,
                'ffmpeg_location': self.ffmpeg_processor.ffmpeg_path,
                'retries': 2,
                'fragment_retries': 2,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'referer': options["url"],
            }
            if mode == "Solo Audio" and audio_format_info.get('extract_only'):
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
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
                
            if audio_extraction_fallback:
                precise_selector = video_format_info.get('format_id')
                if not precise_selector:
                    raise Exception("No se pudo determinar un formato de video para el fallback.")
                ydl_opts['format'] = precise_selector
                print(f"DEBUG: [FALLBACK] Intentando descarga directa del video combinado: {precise_selector}")
                downloaded_filepath = download_media(options["url"], ydl_opts, self.update_progress, self.cancellation_event)
                temp_video_for_extraction = downloaded_filepath
            else:
                try:
                    try:
                        precise_selector = None
                        video_format_id = video_format_info.get('format_id')
                        audio_format_id = audio_format_info.get('format_id')
                        if mode == "Video+Audio":
                            if video_format_info.get('is_combined'):
                                precise_selector = video_format_id
                            elif video_format_id and audio_format_id:
                                precise_selector = f"{video_format_id}+{audio_format_id}"
                            elif video_format_id: 
                                precise_selector = video_format_id
                        elif mode == "Solo Audio":
                            precise_selector = audio_format_id
                        if not precise_selector:
                            raise yt_dlp.utils.DownloadError("Selector preciso no válido o no se seleccionaron formatos.")
                        ydl_opts['format'] = precise_selector
                        print(f"DEBUG: PASO 1: Intentando con selector preciso: {precise_selector}")
                        downloaded_filepath = download_media(options["url"], ydl_opts, self.update_progress, self.cancellation_event)
                        if audio_extraction_fallback:
                            temp_video_for_extraction = downloaded_filepath
                    except yt_dlp.utils.DownloadError as e:
                        print(f"DEBUG: Falló la descarga directa. Error: {e}")
                        print("DEBUG: PASO 1 FALLÓ. Pasando al Paso 2.")
                        try:
                            info_dict = self.analysis_cache.get(options["url"], {}).get('data', {})
                            selected_audio_details = next((f for f in info_dict.get('formats', []) if f.get('format_id') == audio_format_id), None)
                            language_code = selected_audio_details.get('language') if selected_audio_details else None
                            
                            strict_flexible_selector = ""
                            if self.has_audio_streams:
                                if mode == "Video+Audio":
                                    height = video_format_info.get('height')
                                    video_selector = f'bv[height={height}]' if height else 'bv' 
                                    audio_selector = f'ba[lang={language_code}]' if language_code else 'ba'
                                    strict_flexible_selector = f'{video_selector}+{audio_selector}'
                                elif mode == "Solo Audio":
                                    strict_flexible_selector = f'ba[lang={language_code}]' if language_code else 'ba'
                            else: 
                                height = video_format_info.get('height')
                                strict_flexible_selector = f'bv[height={height}]' if height else 'bv'
                            ydl_opts['format'] = strict_flexible_selector
                            print(f"DEBUG: PASO 2: Intentando con selector estricto-flexible: {strict_flexible_selector}")
                            downloaded_filepath = download_media(options["url"], ydl_opts, self.update_progress, self.cancellation_event)
                        except yt_dlp.utils.DownloadError:
                            print("DEBUG: PASO 2 FALLÓ. Pasando al Paso 3.")
                            details_ready_event = threading.Event()
                            compromise_details = {"text": "Obteniendo detalles..."}
                            def get_details_thread():
                                """Este hilo ejecuta la simulación en segundo plano."""
                                compromise_details["text"] = self._get_best_available_info(options["url"], options)
                                details_ready_event.set() 
                            self.after(0, self.update_progress, 50, "Calidad no disponible. Obteniendo detalles de alternativa...")
                            threading.Thread(target=get_details_thread, daemon=True).start()
                            details_ready_event.wait() 
                            self.ui_request_data = {"type": "ask_compromise", "details": compromise_details["text"]}
                            self.ui_response_event.clear()
                            self.ui_request_event.set()
                            self.ui_response_event.wait()
                            user_choice = self.ui_response_data.get("result", "cancel")
                            if user_choice == "accept":
                                print("DEBUG: PASO 4: El usuario aceptó. Intentando con selector final.")
                                final_selector = 'ba'
                                if mode == "Video+Audio":
                                    final_selector = 'bv+ba' if self.has_audio_streams else 'bv'
                                ydl_opts['format'] = final_selector
                                downloaded_filepath = download_media(options["url"], ydl_opts, self.update_progress, self.cancellation_event)
                            else:
                                raise UserCancelledError("Descarga cancelada por el usuario en el diálogo de compromiso.")
                except Exception as final_e:
                        raise final_e
                if not downloaded_filepath or not os.path.exists(downloaded_filepath):
                        raise Exception("La descarga falló o el archivo no se encontró.")
                is_fragment_mode = options.get("fragment_enabled") and (options.get("start_time") or options.get("end_time"))
                if is_fragment_mode:
                        self.after(0, self.update_progress, 98, "Descarga completa. Cortando fragmento con ffmpeg...")
                        original_full_video_path = downloaded_filepath
                        
                        base_name, ext = os.path.splitext(os.path.basename(original_full_video_path))
                        clipped_filename = f"{base_name}_fragmento{ext}"
                        clipped_filepath = os.path.join(os.path.dirname(original_full_video_path), clipped_filename)

                        pre_params = []
                        if options.get("start_time"): pre_params.extend(['-ss', options.get("start_time")])
                        if options.get("end_time"): pre_params.extend(['-to', options.get("end_time")])

                        clip_opts = {
                            "input_file": original_full_video_path, "output_file": clipped_filepath,
                            "ffmpeg_params": [], "pre_params": pre_params
                        }
                        self.ffmpeg_processor.execute_recode(clip_opts, lambda p, m: None, self.cancellation_event)
                        downloaded_filepath = clipped_filepath # El nuevo archivo de trabajo es el fragmento
                        try: # Limpiamos el archivo completo original
                            # Solo borra el original si el usuario NO marcó la casilla para conservarlo
                            if not options.get("keep_original_on_clip"):
                                os.remove(original_full_video_path)
                        except OSError as err:
                            print(f"ADVERTENCIA: No se pudo eliminar el archivo completo original: {err}")
                                  
            if self.cancellation_event.is_set():
                raise UserCancelledError("Proceso cancelado por el usuario.")
            self._save_thumbnail_if_enabled(downloaded_filepath)
            if options.get("download_subtitles") and self.clean_subtitle_check.get() == 1:
                self.after(0, self.update_progress, 99, "Limpiando subtítulo descargado...")
                subtitle_info = options.get("selected_subtitle_info")
                if subtitle_info:
                    try:
                        output_dir = os.path.dirname(downloaded_filepath)
                        base_name = os.path.splitext(os.path.basename(downloaded_filepath))[0]
                        expected_sub_path = os.path.join(output_dir, f"{base_name}.{subtitle_info['lang']}.{subtitle_info['ext']}")
                        if not os.path.exists(expected_sub_path):
                            expected_sub_path = os.path.join(output_dir, f"{base_name}.{subtitle_info['ext']}")
                        if os.path.exists(expected_sub_path):
                            print(f"DEBUG: Encontrado subtítulo para limpieza automática en: {expected_sub_path}")
                            clean_and_convert_vtt_to_srt(expected_sub_path)
                        else:
                            print(f"ADVERTENCIA: No se encontró el archivo de subtítulo '{expected_sub_path}' para la limpieza automática.")
                    except Exception as sub_e:
                        print(f"ADVERTENCIA: Falló la limpieza automática del subtítulo: {sub_e}")
            if audio_extraction_fallback:
                self.after(0, self.update_progress, 95, "Extrayendo pista de audio...")
                audio_ext = audio_format_info.get('ext', 'm4a')
                final_audio_path = os.path.join(final_output_path_str, f"{user_facing_title}.{audio_ext}")
                downloaded_filepath = self.ffmpeg_processor.extract_audio(
                    input_file=temp_video_for_extraction,
                    output_file=final_audio_path,
                    duration=self.video_duration,
                    progress_callback=self.update_progress,
                    cancellation_event=self.cancellation_event
                )
                try:
                    os.remove(temp_video_for_extraction)
                    print(f"DEBUG: Video temporal '{temp_video_for_extraction}' eliminado.")
                    temp_video_for_extraction = None 
                except OSError as e:
                    print(f"ADVERTENCIA: No se pudo eliminar el video temporal: {e}")
            if options.get("recode_video_enabled") or options.get("recode_audio_enabled"):
                recode_phase_started = True
                self.after(0, self.update_progress, 0, "Preparando recodificación...")
                final_title = user_facing_title + "_recoded"
                final_ffmpeg_params = []
                final_ffmpeg_params.extend(["-metadata:s:v:0", "rotate=0"])
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
                        final_ffmpeg_params.extend(profile_params)
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
                        if audio_profile_params:
                            final_ffmpeg_params.extend(audio_profile_params)
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
                self.after(0, self.on_process_finished, True, "Recodificación completada", final_path_from_recode)
                process_successful = True
            else: 
                self.after(0, self.on_process_finished, True, "Descarga completada", downloaded_filepath)
                process_successful = True
        except UserCancelledError as e:
            error_message = str(e)
            should_ask_to_keep_file = recode_phase_started and not options.get("keep_original_file", False) and not self.is_shutting_down
            if should_ask_to_keep_file:
                self.ui_request_data = {
                    "type": "ask_yes_no", "title": "Fallo en la Recodificación",
                    "message": "La descarga del archivo original se completó, pero la recodificación fue cancelada.\n\n¿Deseas conservar el archivo original descargado?"
                }
                self.ui_response_event.clear()
                self.ui_request_event.set()
                self.ui_response_event.wait()
                if self.ui_response_data.get("result", False):
                    keep_file_on_cancel = downloaded_filepath
                    self.after(0, self.on_process_finished, False, "Recodificación cancelada. Archivo original conservado.", keep_file_on_cancel, False)
                else:
                    self.after(0, self.on_process_finished, False, error_message, downloaded_filepath, False, show_dialog=False)
            else:
                self.on_process_finished(False, error_message, downloaded_filepath, show_dialog=False)
        except Exception as e:
            cleaned_message = self._clean_ansi_codes(str(e))
            self.after(0, self.on_process_finished, False, cleaned_message, downloaded_filepath, True)
            should_ask_user = recode_phase_started and not options.get("keep_original_file", False) and not self.is_shutting_down
            if should_ask_user:
                self.ui_request_data = {
                    "type": "ask_yes_no", "title": "Fallo en la Recodificación",
                    "message": "La descarga del archivo original se completó, pero la recodificación falló.\n\n¿Deseas conservar el archivo original descargado?"
                }
                self.ui_response_event.clear()
                self.ui_request_event.set()
                self.ui_response_event.wait()

                if self.ui_response_data.get("result", False):
                    keep_file_on_cancel = downloaded_filepath
        finally:
            if not process_successful and not self.local_file_path:
                if recode_phase_started and final_recoded_path and os.path.exists(final_recoded_path):
                    try:
                        gc.collect()
                        time.sleep(0.5) 
                        print(f"DEBUG: Limpiando archivo de recodificación temporal por fallo (Modo URL): {final_recoded_path}")
                        os.remove(final_recoded_path)
                    except OSError as e:
                        print(f"ERROR: No se pudo limpiar el archivo de recodificación temporal (Modo URL): {e}")
                if temp_video_for_extraction and os.path.exists(temp_video_for_extraction):
                    try:
                        print(f"DEBUG: Limpiando video temporal por fallo (Modo URL): {temp_video_for_extraction}")
                        os.remove(temp_video_for_extraction)
                    except OSError as e:
                        print(f"ERROR: No se pudo limpiar el video temporal (Modo URL): {e}")
                if backup_file_path and os.path.exists(backup_file_path):
                    print("AVISO: La descarga falló. Restaurando el archivo original desde el respaldo (Modo URL).")
                    try:
                        original_path = backup_file_path.removesuffix(".bak")
                        if os.path.exists(original_path) and os.path.normpath(original_path) != os.path.normpath(backup_file_path):
                            os.remove(original_path)
                        os.rename(backup_file_path, original_path)
                        print(f"ÉXITO: Respaldo restaurado a: {original_path}")
                    except OSError as err:
                        print(f"ERROR CRÍTICO: No se pudo restaurar el respaldo: {err}")
                elif cleanup_required:
                    print("DEBUG: Iniciando limpieza general por fallo de operación.")
                    try:
                        gc.collect()
                        time.sleep(1) 
                        base_title_for_cleanup = user_facing_title.replace("_recoded", "")
                        for filename in os.listdir(options["output_path"]):
                            if not filename.startswith(base_title_for_cleanup):
                                continue
                            file_path_to_check = os.path.join(options["output_path"], filename)
                            should_preserve = False
                            known_sidecar_exts = ('.srt', '.vtt', '.ass', '.ssa', '.json3', '.srv1', '.srv2', '.srv3', '.ttml', '.smi', '.tml', '.lrc', '.xml', '.jpg', '.jpeg', '.png')                            
                            if keep_file_on_cancel:
                                normalized_preserved_path = os.path.normpath(keep_file_on_cancel)
                                if os.path.normpath(file_path_to_check) == normalized_preserved_path:
                                    should_preserve = True
                                else:
                                    base_preserved_name = os.path.splitext(os.path.basename(keep_file_on_cancel))[0]
                                    if filename.startswith(base_preserved_name) and filename.lower().endswith(known_sidecar_exts):
                                        should_preserve = True                            
                            elif options.get("keep_original_file", False) and downloaded_filepath:
                                normalized_original_path = os.path.normpath(downloaded_filepath)
                                if os.path.normpath(file_path_to_check) == normalized_original_path:
                                    should_preserve = True
                                else:
                                    base_original_name = os.path.splitext(os.path.basename(downloaded_filepath))[0]
                                    if filename.startswith(base_original_name) and filename.lower().endswith(known_sidecar_exts):
                                        should_preserve = True
                            if should_preserve:
                                print(f"DEBUG: Conservando archivo solicitado o asociado: {file_path_to_check}")
                                continue
                            else:
                                print(f"DEBUG: Eliminando archivo no deseado: {file_path_to_check}")
                                os.remove(file_path_to_check)
                    except Exception as cleanup_e:
                        print(f"ERROR: Falló el proceso de limpieza de archivos: {cleanup_e}")
            elif process_successful and backup_file_path and os.path.exists(backup_file_path):
                try:
                    os.remove(backup_file_path)
                    print("DEBUG: Proceso exitoso, respaldo eliminado.")
                except OSError as err:
                    print(f"AVISO: No se pudo eliminar el archivo de respaldo: {err}")
            self.active_subprocess_pid = None
            self.active_operation_thread = None

    def _reset_buttons_to_original_state(self):
        """ Restablece los botones a su estado original, considerando el modo actual (URL o Local). """
        self.analyze_button.configure(
            text=self.original_analyze_text,
            fg_color=self.original_analyze_fg_color,
            command=self.original_analyze_command,
            state="normal"
        )
        button_text = "Iniciar Proceso" if self.local_file_path else self.original_download_text

        self.download_button.configure(
            text=button_text,
            fg_color=self.original_download_fg_color,
            command=self.original_download_command
        )
        self.toggle_manual_subtitle_button()
        self.update_download_button_state()

    def _save_thumbnail_if_enabled(self, base_filepath):
        """Guarda la miniatura si la opción está activada, usando la ruta del archivo base."""
        if self.auto_save_thumbnail_check.get() == 1 and self.pil_image and base_filepath:
            try:
                self.after(0, self.update_progress, 98, "Guardando miniatura...")
                output_directory = os.path.dirname(base_filepath)
                clean_title = os.path.splitext(os.path.basename(base_filepath))[0]
                if clean_title.endswith("_recoded"):
                    clean_title = clean_title.rsplit('_recoded', 1)[0]
                thumb_path = os.path.join(output_directory, f"{clean_title}.jpg")
                self.pil_image.convert("RGB").save(thumb_path, quality=95)
                print(f"DEBUG: Miniatura guardada automáticamente en {thumb_path}")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo guardar la miniatura automáticamente: {e}")

    def on_process_finished(self, success, message, final_filepath, show_dialog=True):
        """
        Callback UNIFICADO para el final de CUALQUIER proceso.
        CORREGIDO: Ahora muestra un mensaje genérico en la UI si se abre un diálogo de error.
        """
        self.last_download_path = final_filepath
        self.progress_bar.stop()
        self.progress_bar.set(1 if success else 0)
        final_message = self._clean_ansi_codes(message)
        if success:
            self.progress_label.configure(text=final_message)
            if final_filepath:
                self.open_folder_button.configure(state="normal")
        else:
            if show_dialog:
                self.progress_label.configure(text="❌ Error en la operación. Ver detalles.")
                
                lowered_message = final_message.lower()
                dialog_message = final_message 

                if "timed out" in lowered_message or "timeout" in lowered_message:
                    dialog_message = ("Falló la conexión (Timeout).\n\n"
                                    "Causas probables:\n"
                                    "• Conexión a internet lenta o inestable.\n"
                                    "• Un antivirus o firewall está bloqueando la aplicación.")
                elif "429" in lowered_message or "too many requests" in lowered_message:
                    dialog_message = (
                        "Demasiadas Peticiones (Error 429).\n\n"
                        "Has realizado demasiadas solicitudes en poco tiempo.\n\n"
                        "**Sugerencias:**\n"
                        "1. Desactiva la descarga automática de subtítulos y miniaturas.\n"
                        "2. Usa la opción de 'Cookies' si el problema persiste.\n"
                        "3. Espera unos minutos antes de volver a intentarlo."
                    )
                elif any(keyword in lowered_message for keyword in ["age-restricted", "login required", "sign in", "private video", "premium", "members only"]):
                    dialog_message = (
                        "La descarga falló. El contenido parece ser privado, tener restricción de edad o requerir una suscripción.\n\n"
                        "Por favor, intenta configurar las 'Cookies' en la aplicación y vuelve a analizar la URL."
                    )
                elif "cannot parse data" in lowered_message and "facebook" in lowered_message:
                    dialog_message = (
                        "Falló el análisis de Facebook.\n\n"
                        "Este error usualmente ocurre con videos privados o con restricción de edad. "
                        "Intenta configurar las 'Cookies' para solucionarlo."
                    )
                elif "ffmpeg not found" in lowered_message:
                    dialog_message = (
                        "Error Crítico: FFmpeg no encontrado.\n\n"
                        "yt-dlp necesita FFmpeg para realizar la conversión de subtítulos.\n\n"
                        "Asegúrate de que FFmpeg esté correctamente instalado en la carpeta 'bin' de la aplicación."
                    )

                dialog = self.SimpleMessageDialog(self, "Error en la Operación", dialog_message)
                self.wait_window(dialog)
            else:
                 self.progress_label.configure(text=final_message)
        self._reset_buttons_to_original_state()

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
        Ejecuta yt-dlp como un subproceso para analizar la URL, separando de forma
        inteligente la salida JSON de la lista de subtítulos en texto plano.
        """
        try:
            self.after(0, self.update_progress, 0, "Iniciando análisis de URL...")
            command = [
                'yt-dlp', '-j', url, '--no-warnings',
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                '--referer', url,
                '--no-playlist',
                '--playlist-items', '1',
                '--list-subs',
                '--write-auto-subs'
            ]
            
            # El resto de la construcción del comando (cookies, etc.) se mantiene igual
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

            # --- Lógica de parseo mejorada ---
            json_lines = []
            other_lines = []
            in_json_block = False
            brace_level = 0
            
            # Leemos tanto stdout como stderr para dar feedback al usuario
            # y capturar todo el output.
            stream_readers = [process.stdout, process.stderr]
            start_time = time.time()

            while process.poll() is None:
                if self.cancellation_event.is_set():
                    process.terminate()
                    raise UserCancelledError("Análisis cancelado por el usuario.")

                if time.time() - start_time > 60:
                    process.terminate()
                    raise subprocess.TimeoutExpired(cmd=command, timeout=60)
                
                # Leemos una línea de stdout o stderr
                line = process.stdout.readline() or process.stderr.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                line_stripped = line.strip()
                
                # Actualiza el feedback de la UI
                if "[youtube]" in line_stripped:
                    self.after(0, self.update_progress, 0.1, "Estableciendo conexión...")
                elif "[info]" in line_stripped:
                    self.after(0, self.update_progress, 0.3, "Extrayendo metadatos...")
                
                # Lógica para encontrar el bloque JSON
                if line_stripped.startswith('{'):
                    in_json_block = True
                
                if in_json_block:
                    json_lines.append(line)
                    brace_level += line.count('{') - line.count('}')
                    if brace_level == 0 and json_lines:
                        in_json_block = False # Fin del bloque JSON
                else:
                    other_lines.append(line_stripped)
            
            # Aseguramos leer cualquier resto en los buffers
            stdout_rem, stderr_rem = process.communicate()
            other_lines.extend(stdout_rem.strip().splitlines())
            other_lines.extend(stderr_rem.strip().splitlines())
            
            if process.returncode != 0 and not json_lines:
                error_output = "\n".join(other_lines)
                raise Exception(f"yt-dlp falló: {error_output[:500]}")

            json_string = "".join(json_lines)
            info = json.loads(json_string)

            # Ahora, parseamos las 'other_lines' para encontrar subtítulos si es necesario
            if 'subtitles' not in info and 'automatic_captions' not in info:
                info['subtitles'], info['automatic_captions'] = self._parse_subtitle_lines_from_text(other_lines)

            if info.get('is_live'):
                self.after(0, self.on_analysis_complete, None, "AVISO: La URL apunta a una transmisión en vivo.")
                return

            self.after(0, self.on_analysis_complete, info)

        except subprocess.TimeoutExpired:
            self.after(0, self.on_analysis_complete, None, "ERROR: El análisis de la URL tardó demasiado (Timeout).")
        except json.JSONDecodeError:
            error_context = "".join(other_lines)
            self.after(0, self.on_analysis_complete, None, f"ERROR: Fallo al decodificar el JSON. Contexto: {error_context[:300]}")
        except UserCancelledError:
            pass # La cancelación ya fue manejada
        except Exception as e:
            self.after(0, self.on_analysis_complete, None, f"ERROR: {e}")
        finally:
            self.active_subprocess_pid = None

    def _parse_subtitle_lines_from_text(self, lines):
        """
        Parsea una lista de líneas de texto (salida de --list-subs) y la convierte
        en diccionarios de subtítulos manuales y automáticos.
        """
        subtitles = {}
        auto_captions = {}
        current_section = None # Puede ser 'subs' o 'auto'

        for line in lines:
            if "Available subtitles for" in line:
                current_section = 'subs'
                continue
            if "Available automatic captions for" in line:
                current_section = 'auto'
                continue
            
            # Ignora las cabeceras de las tablas
            if line.startswith("Language") or line.startswith("ID") or line.startswith('---'):
                continue

            parts = re.split(r'\s+', line.strip())
            if len(parts) < 3:
                continue

            lang_code = parts[0]
            # Formatos pueden ser múltiples, ej: vtt, ttml, srv3...
            formats = [p.strip() for p in parts[1:-1] if p.strip()]

            if current_section == 'subs':
                target_dict = subtitles
            elif current_section == 'auto':
                target_dict = auto_captions
            else:
                continue

            if lang_code not in target_dict:
                target_dict[lang_code] = []
            
            # yt-dlp lista formatos en una sola línea, creamos una entrada para cada uno
            for fmt in formats:
                target_dict[lang_code].append({
                    'ext': fmt,
                    'url': None, 
                    'name': ''
                })
                
        return subtitles, auto_captions

    def on_analysis_complete(self, info, error_message=None):
        try:
            # --- NUEVA LÓGICA INTELIGENTE PARA PLAYLISTS ---
            if info and info.get('_type') in ('playlist', 'multi_video'):
                # Verifica si la playlist contiene videos (entradas)
                if info.get('entries') and len(info['entries']) > 0:
                    print("DEBUG: Playlist detectada. Extrayendo información del primer video.")
                    # Reemplaza la info de la playlist con la info del primer video
                    info = info['entries'][0]
                else:
                    # Si es una playlist pero no tiene videos, la rechaza.
                    print("DEBUG: Se detectó una playlist vacía o no válida.")
                    error_message = "La URL corresponde a una lista vacía o no válida."
                    info = None
            
            self.progress_bar.stop()
            if not info or error_message:
                self.progress_bar.set(0)
                final_error_message = error_message or "ERROR: No se pudo obtener la información."
                print(f"Error en el análisis de la URL: {final_error_message}")
                self.title_entry.delete(0, 'end')
                self.title_entry.insert(0, final_error_message)
                self.create_placeholder_label("Fallo el análisis")
                self._clear_subtitle_menus()
                return

            self.progress_bar.set(1)
            url = self.url_entry.get()
            self.analysis_cache[url] = {'data': info, 'timestamp': time.time()}
            print(f"DEBUG: Resultado para '{url}' guardado en caché.")
            if info.get('extractor_key', '').lower().startswith('twitch'):
                print("DEBUG: Detectada URL de Twitch, eliminando datos de rechat y deshabilitando menús.")
                # Eliminamos los datos del rechat para que no se procesen después.
                info['subtitles'] = {}
                info['automatic_captions'] = {}
                self._clear_subtitle_menus()
            self.title_entry.delete(0, 'end')
            self.title_entry.insert(0, info.get('title', 'Sin título'))
            self.video_duration = info.get('duration', 0)
            
            # --- CLASIFICACIÓN DEL CONTENIDO ---
            formats = info.get('formats', [])
            self.has_video_streams = any(f.get('height') for f in formats)
            self.has_audio_streams = any(f.get('acodec') != 'none' or (not f.get('height') and f.get('vcodec') == 'none') for f in formats)
            
            # --- LÓGICA DE MINIATURA ---
            thumbnail_url = info.get('thumbnail')
            if thumbnail_url:
                threading.Thread(target=self.load_thumbnail, args=(thumbnail_url,), daemon=True).start()
            elif self.has_audio_streams and not self.has_video_streams:
                self.create_placeholder_label("🎵", font_size=80) # Icono de música para audio-only
                self.save_thumbnail_button.configure(state="disabled")
                self.auto_save_thumbnail_check.deselect()
                self.auto_save_thumbnail_check.configure(state="disabled")
            else:
                self.create_placeholder_label("Miniatura")

            # Poblamos los menús con la nueva lógica consciente del contenido
            self.populate_format_menus(info, self.has_video_streams, self.has_audio_streams)

            self._update_warnings()
            self.update_download_button_state()
            self.update_estimated_size()
            self.update_progress(100, "Análisis completado. ✅ Listo para descargar.")

        finally:
            print("DEBUG: Ejecutando bloque 'finally' de on_analysis_complete para resetear la UI.")
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

    def _classify_format(self, f):
        """
        Clasifica un formato de yt-dlp como 'VIDEO', 'AUDIO' o 'UNKNOWN'
        siguiendo un estricto conjunto de reglas jerárquicas (v2.2 FINAL).
        """
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
        if f.get('ext') in self.AUDIO_EXTENSIONS:
            return 'AUDIO'
        if f.get('ext') in self.VIDEO_EXTENSIONS:
            return 'VIDEO'
        if vcodec == 'none':
            return 'AUDIO'
        return 'UNKNOWN'


    def populate_format_menus(self, info, has_video, has_audio):
        formats = info.get('formats', [])
        video_entries, audio_entries = [], []
        self.video_formats.clear()
        self.audio_formats.clear()

        for f in formats:
            format_type = self._classify_format(f)
            size_mb_str = "Tamaño desc."
            size_sort_priority = 0
            filesize = f.get('filesize') or f.get('filesize_approx')
            if filesize:
                size_mb_str = f"{filesize / (1024*1024):.2f} MB"; size_sort_priority = 2
            else:
                bitrate = f.get('tbr') or f.get('vbr') or f.get('abr')
                if bitrate and self.video_duration:
                    estimated_bytes = (bitrate*1000/8)*self.video_duration; size_mb_str=f"Aprox. {estimated_bytes/(1024*1024):.2f} MB"; size_sort_priority = 1
            
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
                if f.get('vcodec') in self.SLOW_FORMAT_CRITERIA["video_codecs"]: tags.append("⚠️")
                if not compatibility_issues and not unknown_issues: tags.append("✨")
                elif compatibility_issues or unknown_issues:
                    tags.append("⚠️")
                if tags: label += f" ({' '.join(tags)})"
                video_entries.append({'label': label, 'format': f, 'is_combined': is_combined, 'sort_priority': size_sort_priority})

            elif format_type == 'AUDIO':
                abr = f.get('abr') or f.get('tbr')
                lang_code = f.get('language')
                lang_name = "Idioma Desconocido"
                if lang_code:
                    norm_code = lang_code.replace('_', '-').lower()
                    lang_name = self.LANG_CODE_MAP.get(norm_code, self.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code))
                
                lang_prefix = f"{lang_name} - " if lang_code else ""
                
                note = f.get('format_note') or ''
                drc_tag = " (DRC)" if 'DRC' in note else ""

                protocol = f.get('protocol', '')
                protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                label = f"{lang_prefix}{abr:.0f}kbps ({acodec}, {ext}){drc_tag}{protocol_tag}" if abr else f"{lang_prefix}Audio ({acodec}, {ext}){drc_tag}{protocol_tag}"

                if acodec in self.EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]: label += " ✨"
                else: label += " ⚠️"
                audio_entries.append({'label': label, 'format': f, 'sort_priority': size_sort_priority})
        
        # --- El resto de la función no necesita cambios ---
        video_entries.sort(key=lambda e: (e['format'].get('height') or 0, e['format'].get('tbr') or 0), reverse=True)
        def custom_audio_sort_key(entry):
            f = entry['format']
            lang_code_raw = f.get('language') or ''
            norm_code = lang_code_raw.replace('_', '-')
            lang_priority = self.LANGUAGE_ORDER.get(norm_code, self.LANGUAGE_ORDER.get(norm_code.split('-')[0], self.DEFAULT_PRIORITY))
            quality = f.get('abr') or f.get('tbr') or 0
            return (lang_priority, -quality)
        audio_entries.sort(key=custom_audio_sort_key)
        
        self.video_formats = {e['label']: {k: e['format'].get(k) for k in ['format_id', 'vcodec', 'acodec', 'ext', 'width', 'height']} | {'is_combined': e.get('is_combined', False)} for e in video_entries}
        self.audio_formats = {e['label']: {k: e['format'].get(k) for k in ['format_id', 'acodec', 'ext']} for e in audio_entries}
        
        has_video_found = bool(video_entries)
        has_audio_found = bool(audio_entries)
        if not has_video_found and has_audio_found:
            self.mode_selector.set("Solo Audio")
            self.mode_selector.configure(state="disabled", values=["Solo Audio"])
        else:
            current_mode = self.mode_selector.get()
            self.mode_selector.configure(state="normal", values=["Video+Audio", "Solo Audio"])
            self.mode_selector.set(current_mode)
        
        self.on_mode_change(self.mode_selector.get())
        v_opts = list(self.video_formats.keys()) or ["- Sin Formatos de Video -"]; a_opts = list(self.audio_formats.keys()) or ["- Sin Pistas de Audio -"]
        self.video_quality_menu.configure(state="normal" if self.video_formats else "disabled", values=v_opts); self.video_quality_menu.set(v_opts[0])
        self.audio_quality_menu.configure(state="normal" if self.audio_formats else "disabled", values=a_opts); self.audio_quality_menu.set(a_opts[0])
        
        self.all_subtitles = {}
        
        def process_sub_list(sub_list, is_auto):
            lang_code_map_3_to_2 = {'spa': 'es', 'eng': 'en', 'jpn': 'ja', 'fra': 'fr', 'deu': 'de', 'por': 'pt', 'ita': 'it', 'kor': 'ko', 'rus': 'ru'}
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