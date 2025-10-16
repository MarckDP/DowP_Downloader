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
    APP_VERSION = "1.2.0"


    DOWNLOAD_BTN_COLOR = "#28A745"       
    DOWNLOAD_BTN_HOVER = "#218838"       
    PROCESS_BTN_COLOR = "#6F42C1"        
    PROCESS_BTN_HOVER = "#59369A"        

    ANALYZE_BTN_COLOR = "#007BFF"        
    ANALYZE_BTN_HOVER = "#0069D9"        

    
    CANCEL_BTN_COLOR = "#DC3545"         
    CANCEL_BTN_HOVER = "#C82333"         
    
    DISABLED_TEXT_COLOR = "#D3D3D3"
    DISABLED_FG_COLOR = "#565b5f" 

    VIDEO_EXTENSIONS = {'mp4', 'mkv', 'webm', 'mov', 'flv', 'avi', 'gif'}
    AUDIO_EXTENSIONS = {'m4a', 'mp3', 'ogg', 'opus', 'flac', 'wav'}
    SINGLE_STREAM_AUDIO_CONTAINERS = {'.mp3', '.wav', '.flac', '.ac3'}
    FORMAT_MUXER_MAP = {
        ".m4a": "mp4",
        ".wma": "asf"
}

    LANG_CODE_MAP = {
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

    EDITOR_FRIENDLY_CRITERIA = {
        "compatible_vcodecs": [
            "h264", "avc1",  # H.264
            "hevc", "h265",  # H.265
            "prores",        # Apple ProRes
            "dnxhd", "dnxhr", # Avid DNxHD/HR
            "cfhd",          # GoPro CineForm
            "mpeg2video",    
            "dvvideo"        # Formato de cámaras MiniDV
        ],
        "compatible_acodecs": ["aac", "mp4a", "pcm_s16le", "pcm_s24le", "mp3", "ac3"],
        "compatible_exts": ["mp4", "mov", "mxf", "mts", "m2ts", "avi"],
    }

    COMPATIBILITY_RULES = {
        ".gif": {
            "video": ["gif"],  
            "audio": []       
        },
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
        
    class SavePresetDialog(ctk.CTkToplevel):
        """Diálogo para guardar un preset con nombre personalizado."""
        def __init__(self, master):
            super().__init__(master)
            self.title("Guardar ajuste prestablecido")
            self.lift()
            self.attributes("-topmost", True)
            self.grab_set()
            self.result = None
            
            self.geometry("450x200")
            self.resizable(False, False)
            
            self.update_idletasks()
            win_width = 450
            win_height = 200
            master_geo = self.master.geometry()
            master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
            pos_x = master_x + (master_width // 2) - (win_width // 2)
            pos_y = master_y + (master_height // 2) - (win_height // 2)
            self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
            
            label = ctk.CTkLabel(
                self, 
                text="Nombre del ajuste prestablecido:",
                font=ctk.CTkFont(size=13)
            )
            label.pack(pady=(20, 10), padx=20)
            
            self.name_entry = ctk.CTkEntry(
                self,
                placeholder_text="Ej: Mi ProRes Personal"
            )
            self.name_entry.pack(pady=10, padx=20, fill="x")
            self.name_entry.focus()
            
            self.name_entry.bind("<Return>", lambda e: self.save())
            
            button_frame = ctk.CTkFrame(self, fg_color="transparent")
            button_frame.pack(pady=15, padx=20, fill="x")
            button_frame.grid_columnconfigure((0, 1), weight=1)
            
            save_btn = ctk.CTkButton(
                button_frame, 
                text="Guardar",
                command=self.save
            )
            save_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
            
            cancel_btn = ctk.CTkButton(
                button_frame,
                text="Cancelar",
                fg_color="gray",
                hover_color="#555555",
                command=self.cancel
            )
            cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        def save(self):
            preset_name = self.name_entry.get().strip()
            if preset_name:
                self.result = preset_name
                self.destroy()
            else:
                messagebox.showwarning("Nombre vacío", "Por favor, ingresa un nombre para el ajuste.")
        
        def cancel(self):
            self.result = None
            self.destroy()

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
        global main_app_instance
        main_app_instance = self
        self.launch_target = launch_target
        self.is_shutting_down = False
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.title("DowP")
        win_width = 835
        win_height = 900
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = (screen_width // 2) - (win_width // 2)
        pos_y = (screen_height // 2) - (win_height // 2)

        self.original_video_width = 0
        self.original_video_height = 0
        self.has_video_streams = False
        self.has_audio_streams = False
        self.analysis_is_complete = False

        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        self.is_updating_dimension = False
        self.current_aspect_ratio = None
        self.minsize(835, 900)
        ctk.set_appearance_mode("Dark")
        server_thread = threading.Thread(target=run_flask_app, daemon=True)
        server_thread.start()
        print("INFO: Servidor de integración iniciado en el puerto 7788.")
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
        self.release_page_url = None
        self.recode_settings = {}
        self.all_subtitles = {}
        self.current_subtitle_map = {}
        self.apply_quick_preset_checkbox_state = False
        self.keep_original_quick_saved = True
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
        self.selected_browser_saved = "firefox"
        self.browser_profile_saved = ""
        self.auto_download_subtitle_saved = False
        self.ffmpeg_update_snooze_until = None
        self.custom_presets = []
        try:
            print(f"DEBUG: Intentando cargar configuración desde: {SETTINGS_FILE}")
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    self.default_download_path = settings.get("default_download_path", "")
                    self.cookies_path = settings.get("cookies_path", "")
                    self.cookies_mode_saved = settings.get("cookies_mode", "No usar")
                    self.selected_browser_saved = settings.get("selected_browser", "firefox")
                    self.browser_profile_saved = settings.get("browser_profile", "")
                    self.auto_download_subtitle_saved = settings.get("auto_download_subtitle", False)
                    snooze_str = settings.get("ffmpeg_update_snooze_until")
                    if snooze_str:
                        self.ffmpeg_update_snooze_until = datetime.fromisoformat(snooze_str)
                    self.recode_settings = settings.get("recode_settings", {})
                    self.custom_presets = settings.get("custom_presets", [])
                    self.apply_quick_preset_checkbox_state = settings.get("apply_quick_preset_enabled", False)
                    self.keep_original_quick_saved = settings.get("keep_original_quick_enabled", True) 
                print(f"DEBUG: Configuración cargada exitosamente.")
            else:
                print("DEBUG: Archivo de configuración no encontrado. Usando valores por defecto.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: Fallo al cargar configuración: {e}")
            pass

        self._initialize_presets_file()
        presets_data = self._load_presets()
        self.built_in_presets = presets_data.get("built_in_presets", {})
        self.custom_presets = presets_data.get("custom_presets", [])

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
        CORREGIDO: Se eliminaron las referencias a la obsoleta 'loading_window'.
        """
        if self.ui_request_event.is_set():
            self.ui_request_event.clear()
            request_type = self.ui_request_data.get("type")

            if request_type == "ask_yes_no":
                title = self.ui_request_data.get("title", "Confirmar")
                message = self.ui_request_data.get("message", "¿Estás seguro?")
                
                result = messagebox.askyesno(title, message)
                
                self.ui_response_data["result"] = result
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
        """
        Inicia la aplicación, configura la UI y lanza una comprobación de
        FFmpeg en segundo plano.
        """
        print("INFO: Configurando UI y lanzando comprobación de FFmpeg en segundo plano...")

        from src.core.setup import check_app_update
        threading.Thread(
            target=lambda: self.on_update_check_complete(check_app_update(self.APP_VERSION)),
            daemon=True
        ).start()
        
        from src.core.setup import check_environment_status
        threading.Thread(
            target=lambda: self.on_status_check_complete(check_environment_status(lambda text, val: None)),
            daemon=True
        ).start()

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
        
        if self.apply_quick_preset_checkbox_state:
            self.apply_quick_preset_checkbox.select()
        else:
            self.apply_quick_preset_checkbox.deselect()
        
        self.apply_quick_preset_checkbox.deselect()
        
        self._on_quick_recode_toggle()
        
        if self.keep_original_quick_saved:
            self.keep_original_quick_checkbox.select()
        else:
            self.keep_original_quick_checkbox.deselect()
        self.toggle_manual_subtitle_button()
        if self.recode_settings.get("keep_original", True):
            self.keep_original_checkbox.select()
        else:
            self.keep_original_checkbox.deselect()
        self.recode_video_checkbox.deselect()
        self.recode_audio_checkbox.deselect()
        self._toggle_recode_panels()
        self._populate_preset_menu()
        self.after(100, self._update_save_preset_visibility)

    def on_update_check_complete(self, update_info):
        """Callback que se ejecuta cuando la comprobación de versión termina."""
        if update_info.get("update_available"):
            latest_version = update_info.get("latest_version")
            self.release_page_url = update_info.get("release_url")
            
            is_prerelease = update_info.get("is_prerelease", False)
            if is_prerelease:
                status_text = f"¡Nueva Pre-release {latest_version} disponible!"
            else:
                status_text = f"¡Nueva versión {latest_version} disponible!"
            
            self.app_status_label.configure(text=status_text, text_color="#52a2f2")
            
            self.update_app_button.configure(text=f"Descargar v{latest_version}", state="normal", fg_color=self.DOWNLOAD_BTN_COLOR)

        elif "error" in update_info:
            self.app_status_label.configure(text=f"DowP v{self.APP_VERSION} - Error al verificar", text_color="orange")
            self.update_app_button.configure(text="Reintentar", state="normal", fg_color="gray")

        else: 
            self.app_status_label.configure(text=f"DowP v{self.APP_VERSION} - Estás al día ✅")
            self.update_app_button.configure(text="Sin actualizaciones", state="disabled")

    def _open_release_page(self):
        """Abre la página de la release en el navegador."""
        if self.release_page_url:
            webbrowser.open_new_tab(self.release_page_url)
        else:
            from src.core.setup import check_app_update
            self.app_status_label.configure(text=f"DowP v{self.APP_VERSION} - Verificando de nuevo...")
            self.update_app_button.configure(state="disabled")
            threading.Thread(
                target=lambda: self.on_update_check_complete(check_app_update(self.APP_VERSION)),
                daemon=True
            ).start()

    def _handle_download_progress(self, text, value):
        """
        Una función de callback segura para actualizar el progreso en la UI principal,
        sin depender de la ventana de carga.
        """

        percentage = value / 100.0
        
        self.update_progress(percentage, text)


    def on_status_check_complete(self, status_info, force_check=False):
        """
        Callback FINAL que gestiona el estado de FFmpeg.
        - Si FFmpeg no existe, lo descarga AUTOMÁTICAMENTE.
        - Si existe y hay una actualización, PREGUNTA al usuario y respeta el SNOOZE.
        """
        status = status_info.get("status")
        
        self.update_ffmpeg_button.configure(state="normal", text="Buscar Actualizaciones de FFmpeg")

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
            self.update_progress(0, "FFmpeg no encontrado. Iniciando descarga automática...")
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
                self.lift()
                if user_response:
                    should_download = True
                    self.ffmpeg_update_snooze_until = None 
                else:
                    self.ffmpeg_update_snooze_until = datetime.now() + timedelta(days=15)
                    self.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualización pospuesta)")
                self.save_settings() 
                
            elif update_available and snoozed:
                print(f"DEBUG: Actualización de FFmpeg omitida. Snooze activo hasta {self.ffmpeg_update_snooze_until}.")
                self.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualización pospuesta)")
            else:
                self.ffmpeg_status_label.configure(text=f"FFmpeg: {local_version} \n(Actualizado)")

        if should_download:
            if not download_url:
                messagebox.showerror("Error", "No se pudo obtener la URL de descarga para FFmpeg.")
                return

            self.update_progress(0, f"Iniciando descarga de FFmpeg {latest_version}...")
            from src.core.setup import download_and_install_ffmpeg
            
            def download_task():
                success = download_and_install_ffmpeg(latest_version, download_url, self._handle_download_progress)
                if success:
                    self.after(0, self.ffmpeg_processor.run_detection_async, 
                            lambda s, m: self.on_ffmpeg_detection_complete(s, m, show_ready_message=True))
                    self.after(0, lambda: self.ffmpeg_status_label.configure(text=f"FFmpeg: {latest_version} \n(Instalado)"))
                else:
                    self.after(0, self.update_progress, 0, "Falló la descarga de FFmpeg.")

            threading.Thread(target=download_task, daemon=True).start()

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
        self.analyze_button = ctk.CTkButton(url_frame, text=self.original_analyze_text, command=self.original_analyze_command, 
                                     fg_color=self.ANALYZE_BTN_COLOR, hover_color=self.ANALYZE_BTN_HOVER)
        self.analyze_button.pack(side="left", padx=(5, 10))
        self.original_analyze_fg_color = self.ANALYZE_BTN_COLOR
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

        self.app_status_label = ctk.CTkLabel(maintenance_frame, text=f"DowP v{self.APP_VERSION} - Verificando...", justify="left")
        self.app_status_label.grid(row=0, column=0, padx=10, pady=(5, 5), sticky="ew")

        self.update_app_button = ctk.CTkButton(maintenance_frame, text="Buscar Actualización", state="disabled", command=self._open_release_page)
        self.update_app_button.grid(row=1, column=0, padx=10, pady=(0, 15), sticky="ew")

        self.ffmpeg_status_label = ctk.CTkLabel(maintenance_frame, text="FFmpeg: Verificando...", wraplength=280, justify="left")
        self.ffmpeg_status_label.grid(row=2, column=0, padx=10, pady=(5,5), sticky="ew") 
        self.update_ffmpeg_button = ctk.CTkButton(maintenance_frame, text="Buscar Actualizaciones de FFmpeg", command=self.manual_ffmpeg_update_check)
        self.update_ffmpeg_button.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")

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

        recode_mode_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        recode_mode_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(recode_mode_frame, text="Modo:").pack(side="left", padx=(0, 10))
        self.recode_mode_selector = ctk.CTkSegmentedButton(recode_mode_frame, values=["Modo Rápido", "Modo Manual"], command=self._on_recode_mode_change)
        self.recode_mode_selector.pack(side="left", expand=True, fill="x")

        self.recode_quick_frame = ctk.CTkFrame(self.recode_main_frame)

        self.apply_quick_preset_checkbox = ctk.CTkCheckBox(
            self.recode_quick_frame, 
            text="Recodificación no disponible (Detectando FFmpeg...)", 
            command=self._on_quick_recode_toggle,
            state="disabled" 
        )
        self.apply_quick_preset_checkbox.pack(anchor="w", padx=10, pady=(5, 5))
        self.apply_quick_preset_checkbox.deselect()
        
        self.quick_recode_options_frame = ctk.CTkFrame(self.recode_quick_frame, fg_color="transparent")
        
        ctk.CTkLabel(self.quick_recode_options_frame, text="Preset de Conversión:", font=ctk.CTkFont(weight="bold")).pack(pady=10, padx=10)
        
        def on_preset_change(selection):
            self.update_download_button_state()
            self._update_export_button_state()
        
        self.recode_preset_menu = ctk.CTkOptionMenu(self.quick_recode_options_frame, values=["- Aún no disponible -"], command=on_preset_change)
        self.recode_preset_menu.pack(pady=10, padx=10, fill="x")
        
        preset_actions_frame = ctk.CTkFrame(self.quick_recode_options_frame, fg_color="transparent")
        preset_actions_frame.pack(fill="x", padx=10, pady=(0, 10))
        preset_actions_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.import_preset_button = ctk.CTkButton(
            preset_actions_frame,
            text="📥 Importar",
            command=self.import_preset_file,
            fg_color="#28A745",
            hover_color="#218838"
        )
        self.import_preset_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.export_preset_button = ctk.CTkButton(
            preset_actions_frame,
            text="📤 Exportar",
            command=self.export_preset_file,
            state="disabled",
            fg_color="#007BFF",
            hover_color="#0069D9"
        )
        self.export_preset_button.grid(row=0, column=1, padx=5, sticky="ew")
        
        self.delete_preset_button = ctk.CTkButton(
            preset_actions_frame,
            text="🗑️ Eliminar",
            command=self.delete_preset_file,
            state="disabled",
            fg_color="#DC3545",
            hover_color="#C82333"
        )
        self.delete_preset_button.grid(row=0, column=2, padx=(5, 0), sticky="ew")
        
        self.keep_original_quick_checkbox = ctk.CTkCheckBox(
            self.recode_quick_frame, 
            text="Mantener los archivos originales",
            command=self.save_settings,
            state="disabled"
        )
        self.keep_original_quick_checkbox.pack(anchor="w", padx=10, pady=(0, 5))
        self.keep_original_quick_checkbox.select()
        

        self.recode_manual_frame = ctk.CTkFrame(self.recode_main_frame, fg_color="transparent")
        
        self.recode_toggle_frame = ctk.CTkFrame(self.recode_manual_frame, fg_color="transparent")
        self.recode_toggle_frame.pack(side="top", fill="x", padx=10, pady=(0, 10)) 
        self.recode_toggle_frame.grid_columnconfigure((0, 1), weight=1)

        self.recode_video_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Recodificar Video", command=self._toggle_recode_panels, state="disabled")
        self.recode_video_checkbox.grid(row=0, column=0, padx=10, pady=(5, 5), sticky="w")
        self.recode_audio_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Recodificar Audio", command=self._toggle_recode_panels, state="disabled")
        self.recode_audio_checkbox.grid(row=0, column=1, padx=10, pady=(5, 5), sticky="w")
        self.keep_original_checkbox = ctk.CTkCheckBox(self.recode_toggle_frame, text="Mantener los archivos originales", state="disabled", command=self.save_settings)
        self.keep_original_checkbox.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="w")

        self.keep_original_checkbox.select()
        
        self.recode_warning_frame = ctk.CTkFrame(self.recode_manual_frame, fg_color="transparent")
        self.recode_warning_frame.pack(pady=0, padx=0, fill="x")
        self.recode_warning_label = ctk.CTkLabel(self.recode_warning_frame, text="", wraplength=400, justify="left", font=ctk.CTkFont(weight="bold"))
        self.recode_warning_label.pack(pady=5, padx=5, fill="both", expand=True)
        
        self.recode_options_frame = ctk.CTkFrame(self.recode_manual_frame)
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
        self.custom_gif_frame = ctk.CTkFrame(codec_options_frame, fg_color="transparent")
        self.custom_gif_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5)
        self.custom_gif_frame.grid_remove() 
        ctk.CTkLabel(self.custom_gif_frame, text="FPS:").pack(side="left", padx=(0, 5))
        self.custom_gif_fps_entry = ctk.CTkEntry(self.custom_gif_frame, placeholder_text="15", width=60)
        self.custom_gif_fps_entry.pack(side="left")
        ctk.CTkLabel(self.custom_gif_frame, text="Ancho:").pack(side="left", padx=(15, 5))
        self.custom_gif_width_entry = ctk.CTkEntry(self.custom_gif_frame, placeholder_text="480", width=60)
        self.custom_gif_width_entry.pack(side="left")
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
        self.resolution_preset_menu = ctk.CTkOptionMenu(self.resolution_options_frame, values=["Personalizado", "4K UHD", "2K QHD", "1080p Full HD", "720p HD", "480p SD"], command=self.on_resolution_preset_change)
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
        
        self.recode_audio_options_frame = ctk.CTkFrame(self.recode_manual_frame)
        self.recode_audio_options_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.recode_audio_options_frame, text="Opciones de Audio", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, pady=(5, 10), padx=10)
        ctk.CTkLabel(self.recode_audio_options_frame, text="Codec de Audio:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_codec_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], state="disabled", command=self.update_audio_profile_menu)
        self.recode_audio_codec_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(self.recode_audio_options_frame, text="Perfil de Audio:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.recode_audio_profile_menu = ctk.CTkOptionMenu(self.recode_audio_options_frame, values=["-"], state="disabled", command=lambda _: self._validate_recode_compatibility())
        self.recode_audio_profile_menu.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.save_preset_frame = ctk.CTkFrame(self.recode_manual_frame)
        self.save_preset_frame.pack(side="bottom", fill="x", padx=0, pady=(10, 0))
        
        self.save_preset_button = ctk.CTkButton(
            self.save_preset_frame, 
            text="Guardar como ajuste prestablecido",
            command=self.open_save_preset_dialog
        )
        self.save_preset_button.pack(fill="x", padx=10, pady=(10, 5))



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
        self.download_button = ctk.CTkButton(download_frame, text=self.original_download_text, state="disabled", command=self.original_download_command, 
                                     fg_color=self.DOWNLOAD_BTN_COLOR, hover_color=self.DOWNLOAD_BTN_HOVER,
                                     text_color_disabled=self.DISABLED_TEXT_COLOR)
        self.download_button.pack(side="left", padx=(5, 10))
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
        self.start_h.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.start_h, self.start_m), self.update_download_button_state()))
        self.start_m.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.start_m, self.start_s), self.update_download_button_state()))
        self.start_s.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.start_s), self.update_download_button_state()))
        self.end_h.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.end_h, self.end_m), self.update_download_button_state()))
        self.end_m.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.end_m, self.end_s), self.update_download_button_state()))
        self.end_s.bind("<KeyRelease>", lambda e: (self._handle_time_input(e, self.end_s), self.update_download_button_state()))
        self._toggle_fragment_panel()
        self.recode_mode_selector.set("Modo Rápido")
        self._on_recode_mode_change("Modo Rápido")
        self._check_for_ui_requests()

    def _on_recode_mode_change(self, mode):
        """Muestra el panel de recodificación apropiado."""
        if mode == "Modo Rápido":
            self.recode_quick_frame.pack(side="top", fill="x", padx=10, pady=0)
            self.recode_manual_frame.pack_forget()
            self.save_preset_frame.pack_forget()
        else:
            self.recode_manual_frame.pack(side="top", fill="x", padx=0, pady=0)
            self.recode_quick_frame.pack_forget()
        
        self._validate_recode_compatibility()
        self._update_save_preset_visibility()

    def _on_quick_recode_toggle(self):
        """
        Muestra/oculta las opciones de recodificación en Modo Rápido
        según si el checkbox está marcado
        """
        if self.apply_quick_preset_checkbox.get() == 1:
            
            self.quick_recode_options_frame.pack(fill="x", padx=0, pady=0)
            self.keep_original_quick_checkbox.configure(state="normal") 
        else:
            
            self.quick_recode_options_frame.pack_forget()
            self.keep_original_quick_checkbox.configure(state="disabled")
        
        self.update_download_button_state()
        self.save_settings()

    def _populate_preset_menu(self):
        """
        Lee los presets disponibles y los añade al menú desplegable del Modo Rápido,
        filtrando por el modo principal seleccionado (Video+Audio vs Solo Audio).
        """
        current_main_mode = self.mode_selector.get()
        compatible_presets = []

        for name, data in self.built_in_presets.items():
            if data.get("mode_compatibility") == current_main_mode:
                compatible_presets.append(name)
        
        custom_presets_found = False
        for preset in getattr(self, "custom_presets", []):
            if preset.get("data", {}).get("mode_compatibility") == current_main_mode:
                if not custom_presets_found:
                    if compatible_presets:
                        compatible_presets.append("--- Mis Presets ---")
                    custom_presets_found = True
                compatible_presets.append(preset.get("name"))

        if compatible_presets:
            self.recode_preset_menu.configure(values=compatible_presets, state="normal")
            self.recode_preset_menu.set(compatible_presets[0])
            self._update_export_button_state()
        else:
            self.recode_preset_menu.configure(values=["- No hay presets para este modo -"], state="disabled")
            self.recode_preset_menu.set("- No hay presets para este modo -")
            self.export_preset_button.configure(state="disabled")

    def _update_export_button_state(self):
        """
        Habilita/desahabilita los botones de exportar y eliminar según si el preset es personalizado
        """
        selected_preset = self.recode_preset_menu.get()
        
        is_custom = any(p["name"] == selected_preset for p in self.custom_presets)
        
        if is_custom:
            self.export_preset_button.configure(state="normal")
            self.delete_preset_button.configure(state="normal")
        else:
            self.export_preset_button.configure(state="disabled")
            self.delete_preset_button.configure(state="disabled")

    def _find_preset_params(self, preset_name):
        """
        Busca un preset por su nombre, primero en los personalizados y luego en los integrados.
        Devuelve el diccionario de parámetros si lo encuentra.
        """
        for preset in getattr(self, 'custom_presets', []):
            if preset.get("name") == preset_name:
                return preset.get("data", {})
        
        if preset_name in self.built_in_presets:  
            return self.built_in_presets[preset_name]
            
        return {}

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
        self.reset_to_url_mode()
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

            self.keep_original_quick_checkbox.select()
            self.keep_original_quick_checkbox.configure(state="disabled")

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
                    'index': video_stream.get('index', 0),
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
                self.audio_formats = {} 
                if not audio_streams:
                    self.audio_formats = {"-": {}}
                    self.audio_quality_menu.configure(values=["-"], state="disabled")
                else:
                    for stream in audio_streams:
                        idx = stream.get('index', '?')
                        title = stream.get('tags', {}).get('title', f"Pista de Audio {idx}")
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
                        self.audio_formats[a_label] = {'format_id': f'local_audio_{idx}', 'acodec': stream.get('codec_name', 'N/A')}
                    self.audio_quality_menu.configure(values=audio_labels, state="normal")
                    default_selection = next((label for label in audio_labels if "(Default)" in label), audio_labels[0])
                    self.audio_quality_menu.set(default_selection)
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
            self.download_button.configure(text="Iniciar Proceso", fg_color=self.PROCESS_BTN_COLOR, hover_color=self.PROCESS_BTN_HOVER)
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
        self.download_button.configure(text=self.original_download_text, fg_color=self.DOWNLOAD_BTN_COLOR)
        self.clear_local_file_button.pack_forget()
        self.auto_save_thumbnail_check.pack(padx=20, pady=(0, 10), anchor="w", after=self.save_thumbnail_button)
        self.auto_save_thumbnail_check.configure(state="normal")
        self.keep_original_checkbox.configure(state="normal")
        self.keep_original_quick_checkbox.configure(state="normal")
        self.update_download_button_state()
        self.save_in_same_folder_check.deselect()
        self._on_save_in_same_folder_change()
        self.use_all_audio_tracks_check.pack_forget()

    def _execute_local_recode(self, options):
        """
        Función simplificada que recolecta datos para la recodificación local
        y llama a la función maestra.
        """
        try:
            source_path = self.local_file_path
            output_dir = self.output_path_entry.get()
            if self.save_in_same_folder_check.get() == 1:
                output_dir = os.path.dirname(source_path)

            base_filename = self.sanitize_filename(options['title']) + "_recoded"

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
            
            options['selected_audio_stream_index'] = selected_audio_stream_index
            options['selected_video_stream_index'] = selected_video_stream_index
            options['duration'] = self.video_duration

            final_output_path = self._execute_recode_master(
                input_file=source_path,
                output_dir=output_dir,
                base_filename=base_filename,
                recode_options=options
            )

            self.after(0, self.on_process_finished, True, "Recodificación local completada.", final_output_path)

        except (UserCancelledError, Exception) as e:
            raise LocalRecodeFailedError(str(e))
        
    def _on_save_in_same_folder_change(self):
        """
        Actualiza el estado de la carpeta de salida según la casilla
        'Guardar en la misma carpeta'.
        """
        if self.save_in_same_folder_check.get() == 1 and self.local_file_path:
            output_dir = os.path.dirname(self.local_file_path)
            self.output_path_entry.configure(state="normal")
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, output_dir)
            self.output_path_entry.configure(state="disabled")
            self.select_folder_button.configure(state="disabled")
        else:
            self.output_path_entry.configure(state="normal")
            self.select_folder_button.configure(state="normal")
            self.output_path_entry.delete(0, 'end')
            self.output_path_entry.insert(0, self.default_download_path)
        self.update_download_button_state()

    def toggle_resolution_panel(self):
        if self.resolution_checkbox.get() == 1:
            self.resolution_options_frame.grid()
            
            if hasattr(self, 'original_video_width') and self.original_video_width > 0:
                if not self.width_entry.get() and not self.height_entry.get():
                    self.width_entry.delete(0, 'end')
                    self.width_entry.insert(0, str(self.original_video_width))
                    self.height_entry.delete(0, 'end')
                    self.height_entry.insert(0, str(self.original_video_height))
                    
                    if not self.aspect_ratio_lock.get():
                        self.aspect_ratio_lock.select()
                    try:
                        self.current_aspect_ratio = self.original_video_width / self.original_video_height
                    except (ValueError, ZeroDivisionError):
                        self.current_aspect_ratio = None
            
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
                width_str = self.width_entry.get()
                height_str = self.height_entry.get()
                
                if width_str and height_str:
                    width = int(width_str)
                    height = int(height_str)
                    self.current_aspect_ratio = width / height
                elif hasattr(self, 'original_video_width') and self.original_video_width > 0:
                    self.current_aspect_ratio = self.original_video_width / self.original_video_height
                else:
                    self.current_aspect_ratio = None
                    
            except (ValueError, ZeroDivisionError, AttributeError):
                self.current_aspect_ratio = None
        else:
            self.current_aspect_ratio = None

    def on_resolution_preset_change(self, preset):
        if preset == "Personalizado":
            self.resolution_manual_frame.grid()
            if hasattr(self, 'original_video_width') and self.original_video_width > 0:
                if not self.width_entry.get():  
                    self.width_entry.delete(0, 'end')
                    self.width_entry.insert(0, str(self.original_video_width))
                    self.height_entry.delete(0, 'end')
                    self.height_entry.insert(0, str(self.original_video_height))
                if self.aspect_ratio_lock.get():
                    try:
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
                
                try:
                    self.current_aspect_ratio = width / height
                except ZeroDivisionError:
                    self.current_aspect_ratio = None
                    
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
        compatible_codecs = self._get_compatible_audio_codecs(target_container)
        if not compatible_codecs:
            compatible_codecs = ["-"]
        self.recode_audio_codec_menu.configure(values=compatible_codecs, state="normal" if compatible_codecs[0] != "-" else "disabled")
        saved_codec = self.recode_settings.get("video_audio_codec")
        if saved_codec and saved_codec in compatible_codecs:
            self.recode_audio_codec_menu.set(saved_codec)
        else:
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
        self.update_audio_profile_menu(selection)
        self.update_recode_container_label()
        is_video_mode = self.mode_selector.get() == "Video+Audio"
        video_codec = self.recode_codec_menu.get()
        audio_codec = self.recode_audio_codec_menu.get()
        incompatible = False
        if is_video_mode and "ProRes" in video_codec or "DNxH" in video_codec:
            if "FLAC" in audio_codec or "Opus" in audio_codec or "Vorbis" in audio_codec:
                incompatible = True
        if incompatible:
            self.audio_compatibility_warning.grid()
        else:
            self.audio_compatibility_warning.grid_remove() 

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
        """Inicia una comprobación manual de la actualización de FFmpeg, usando el callback de progreso seguro."""
        self.update_ffmpeg_button.configure(state="disabled", text="Buscando...")
        self.ffmpeg_status_label.configure(text="FFmpeg: Verificando...")
        from src.core.setup import check_environment_status
        
        def check_task():
            status_info = check_environment_status(self._handle_download_progress)
            self.after(0, self.on_status_check_complete, status_info, True)

        self.setup_thread = threading.Thread(target=check_task, daemon=True)
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
        self.custom_bitrate_frame.grid_forget()
        self.custom_gif_frame.grid_remove()
        if "Bitrate Personalizado" in profile:
            self.custom_bitrate_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5)
            if not self.custom_bitrate_entry.get():
                self.custom_bitrate_entry.insert(0, "8")
        
        elif profile == "Personalizado" and self.recode_codec_menu.get() == "GIF (animado)":
            self.custom_gif_frame.grid()

        self.update_estimated_size()
        self.save_settings()
        self._validate_recode_compatibility()
        self.update_audio_codec_menu() 

    def update_download_button_state(self, *args):
        """
        Valida TODAS las condiciones necesarias y actualiza el estado del botón de descarga.
        Ahora es consciente del modo de recodificación (Rápido vs Manual).
        """
        if self.url_entry.get().strip():
            self.analyze_button.configure(state="normal")
        else:
            self.analyze_button.configure(state="disabled")

        try:
            current_recode_mode = self.recode_mode_selector.get()
            
            url_mode_ready = self.analysis_is_complete and bool(self.url_entry.get().strip())
            local_mode_ready = self.local_file_path is not None
            app_is_ready_for_action = url_mode_ready or local_mode_ready

            output_path_is_valid = bool(self.output_path_entry.get())
            if local_mode_ready and self.save_in_same_folder_check.get() == 1:
                output_path_is_valid = True

            times_are_valid = True
            self.time_warning_label.configure(text="")
            if self.fragment_checkbox.get() == 1 and self.video_duration > 0:
                start_str = self._get_formatted_time(self.start_h, self.start_m, self.start_s)
                end_str = self._get_formatted_time(self.end_h, self.end_m, self.end_s)
                start_seconds = self.time_str_to_seconds(start_str)
                end_seconds = self.time_str_to_seconds(end_str)
                if start_seconds >= self.video_duration or (end_seconds > 0 and end_seconds > self.video_duration) or (end_seconds > 0 and start_seconds >= end_seconds):
                    times_are_valid = False

            recode_config_is_valid = True
            
            if current_recode_mode == "Modo Rápido":
                if self.apply_quick_preset_checkbox.get() == 1:
                    selected_preset = self.recode_preset_menu.get()
                    if selected_preset.startswith("- ") or not selected_preset:
                        recode_config_is_valid = False
            else:  
                if self.recode_video_checkbox.get() == 1:
                    bitrate_ok = True
                    if "Bitrate Personalizado" in self.recode_profile_menu.get():
                        try:
                            value = float(self.custom_bitrate_entry.get())
                            if not (0 < value <= 200):
                                bitrate_ok = False
                        except (ValueError, TypeError):
                            bitrate_ok = False
                    if not self.proc_type_var.get() or not bitrate_ok:
                        recode_config_is_valid = False

            action_is_selected_for_local_mode = True
            if local_mode_ready:
                if current_recode_mode == "Modo Rápido":
                    is_recode_on = self.apply_quick_preset_checkbox.get() == 1
                else:  
                    is_recode_on = self.recode_video_checkbox.get() == 1 or self.recode_audio_checkbox.get() == 1
                
                is_clip_on = self.fragment_checkbox.get() == 1
                if not is_recode_on and not is_clip_on:
                    action_is_selected_for_local_mode = False

            recode_is_compatible = self.recode_compatibility_status in ["valid", "warning"]

            if (app_is_ready_for_action and
                output_path_is_valid and
                times_are_valid and
                recode_config_is_valid and
                action_is_selected_for_local_mode and
                recode_is_compatible):
                
                button_color = self.PROCESS_BTN_COLOR if self.local_file_path else self.DOWNLOAD_BTN_COLOR
                hover_color = self.PROCESS_BTN_HOVER if self.local_file_path else self.DOWNLOAD_BTN_HOVER
                self.download_button.configure(state="normal", 
                                            fg_color=button_color, 
                                            hover_color=hover_color)
            else:
                self.download_button.configure(state="disabled", 
                                            fg_color=self.DISABLED_FG_COLOR)

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
            "recode_settings": self.recode_settings,
            "custom_presets": getattr(self, 'custom_presets', []),
            "apply_quick_preset_enabled": self.apply_quick_preset_checkbox.get() == 1,
            "keep_original_quick_enabled": self.keep_original_quick_checkbox.get() == 1
        }
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings_to_save, f, indent=4)
        except IOError as e:
            print(f"ERROR: Fallo al guardar configuración: {e}")

    def on_ffmpeg_detection_complete(self, success, message, show_ready_message=False):
        if success:
            self.recode_video_checkbox.configure(text="Recodificar Video", state="normal")
            self.recode_audio_checkbox.configure(text="Recodificar Audio", state="normal")
            
            self.apply_quick_preset_checkbox.configure(text="Activar recodificación Rápida", state="normal")
            
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
            
            self.update_codec_menu()
            
            if show_ready_message:
                self.update_progress(100, "✅ FFmpeg instalado correctamente. Listo para usar.")
        else:
            print(f"FFmpeg detection error: {message}")
            self.recode_video_checkbox.configure(text="Recodificación no disponible", state="disabled")
            self.recode_audio_checkbox.configure(text="(Error FFmpeg)", state="disabled")
            
            self.apply_quick_preset_checkbox.configure(text="Recodificación no disponible (Error FFmpeg)", state="disabled")
            self.apply_quick_preset_checkbox.deselect() 

    def _toggle_recode_panels(self):
        is_video_recode = self.recode_video_checkbox.get() == 1
        is_audio_recode = self.recode_audio_checkbox.get() == 1
        is_audio_only_mode = self.mode_selector.get() == "Solo Audio"
        if self.local_file_path:
            self.keep_original_checkbox.select()
            self.keep_original_checkbox.configure(state="disabled")
        else:
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
        if is_audio_recode:
            if not self.recode_audio_options_frame.winfo_ismapped():
                self.update_audio_codec_menu()
        else:
            self.recode_audio_options_frame.pack_forget()
        self.recode_options_frame.pack_forget()
        self.recode_audio_options_frame.pack_forget()
        if is_video_recode and not is_audio_only_mode:
            self.recode_options_frame.pack(side="top", fill="x", padx=5, pady=5)
        if is_audio_recode:
            self.recode_audio_options_frame.pack(side="top", fill="x", padx=5, pady=5)
        self._validate_recode_compatibility()
        self._update_save_preset_visibility()
    
    def _update_save_preset_visibility(self):
        """
        Muestra/oculta el botón 'Guardar como ajuste' según si hay opciones de recodificación activas
        """
        is_video_recode = self.recode_video_checkbox.get() == 1
        is_audio_recode = self.recode_audio_checkbox.get() == 1
        mode = self.mode_selector.get()
        
        should_show = False
        
        if mode == "Video+Audio":
            should_show = is_video_recode or is_audio_recode
        elif mode == "Solo Audio":
            should_show = is_audio_recode
        
        if should_show:
            self.save_preset_frame.pack(side="bottom", fill="x", padx=0, pady=(10, 0))
        else:
            self.save_preset_frame.pack_forget()

    def _validate_recode_compatibility(self):
        """Valida la compatibilidad de las opciones de recodificación y actualiza la UI."""
        self.recode_warning_frame.pack_forget()
        
        current_recode_mode = self.recode_mode_selector.get()
        if current_recode_mode == "Modo Rápido":
            self.recode_compatibility_status = "valid"
            self.update_download_button_state()
            return
        
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
        target_container = None
        if is_video_recode:
            proc_type = self.proc_type_var.get()
            if proc_type:
                available = self.ffmpeg_processor.available_encoders.get(proc_type, {}).get("Video", {})
                target_container = available.get(self.recode_codec_menu.get(), {}).get("container")
        elif is_audio_recode:
            if mode == "Video+Audio": 
                target_container = ".mp4"  
            else: 
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
            else:
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
            color = "#00A400"
            self.recode_warning_label.configure(text=message, text_color=color)
        else:
            color = "#E54B4B" if status == "error" else "#E5A04B"
            self.recode_warning_label.configure(text=message, text_color=color)
        self.recode_warning_frame.pack(after=self.recode_toggle_frame, pady=5, padx=10, fill="x")
        if hasattr(self, 'use_all_audio_tracks_check') and self.use_all_audio_tracks_check.winfo_ismapped():
            is_multi_track_available = len(self.audio_formats) > 1
            if target_container in self.SINGLE_STREAM_AUDIO_CONTAINERS:
                self.use_all_audio_tracks_check.configure(state="disabled")
                self.use_all_audio_tracks_check.deselect()
                self.audio_quality_menu.configure(state="normal")
            elif is_multi_track_available:
                self.use_all_audio_tracks_check.configure(state="normal")
        self.update_download_button_state()

    def toggle_fps_panel(self):
        """Muestra u oculta el panel de opciones de FPS."""
        if self.fps_checkbox.get() == 1:
            self.fps_options_frame.grid()
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

        if "GIF (animado)" in selected_codec_name:
            # Si es GIF, desactiva la recodificación de audio.
            self.recode_audio_checkbox.deselect()
            self.recode_audio_checkbox.configure(state="disabled")

            # Y también desactiva las opciones generales de FPS y resolución.
            self.fps_checkbox.configure(state="disabled")
            self.fps_checkbox.deselect()
            self.resolution_checkbox.configure(state="disabled")
            self.resolution_checkbox.deselect()
            
        else:
            # Si NO es GIF, reactiva las opciones (si hay audio disponible).
            if self.has_audio_streams or self.local_file_path:
                self.recode_audio_checkbox.configure(state="normal")
            self.fps_checkbox.configure(state="normal")
            self.resolution_checkbox.configure(state="normal")

        # Estas dos llamadas son seguras y se mantienen
        self.toggle_fps_entry_panel()
        self.toggle_resolution_panel()

        self.update_download_button_state()
        self.save_settings()

    def on_mode_change(self, mode):
        self.format_warning_label.pack_forget()
        self.video_quality_label.pack_forget()
        self.video_quality_menu.pack_forget()
        if hasattr(self, 'audio_options_frame'):
            self.audio_options_frame.pack_forget()
        self.recode_video_checkbox.deselect()
        self.recode_audio_checkbox.deselect()
        self.proc_type_var.set("") 
        if mode == "Video+Audio":
            self.video_quality_label.pack(fill="x", padx=5, pady=(10, 0))
            self.video_quality_menu.pack(fill="x", padx=5, pady=(0, 5))
            if hasattr(self, 'audio_options_frame'):
                self.audio_options_frame.pack(fill="x")
            self.format_warning_label.pack(fill="x", padx=5, pady=(5, 5))
            self.recode_video_checkbox.grid()
            self.recode_audio_checkbox.configure(text="Recodificar Audio")
            self.on_video_quality_change(self.video_quality_menu.get())
        elif mode == "Solo Audio":
            if hasattr(self, 'audio_options_frame'):
                self.audio_options_frame.pack(fill="x")
            self.format_warning_label.pack(fill="x", padx=5, pady=(5, 5))
            self.recode_video_checkbox.grid_remove()
            self.recode_audio_checkbox.configure(text="Activar Recodificación para Audio")
            self._update_warnings()
        self.recode_main_frame._parent_canvas.yview_moveto(0)
        self.recode_main_frame.pack_forget()
        self.recode_main_frame.pack(pady=(10, 0), padx=5, fill="both", expand=True)
        self._toggle_recode_panels()
        self.update_codec_menu()
        self.update_audio_codec_menu()
        self._populate_preset_menu()
        self._update_save_preset_visibility()

    def _on_use_all_audio_tracks_change(self):
        """Gestiona el estado del menú de audio cuando el checkbox cambia."""
        if self.use_all_audio_tracks_check.get() == 1:
            self.audio_quality_menu.configure(state="disabled")
        else:
            self.audio_quality_menu.configure(state="normal")

    def on_video_quality_change(self, selected_label):
        selected_format_info = self.video_formats.get(selected_label)
        if selected_format_info:
            if selected_format_info.get('is_combined'):
                self.audio_quality_menu.configure(state="disabled")
            else:
                self.audio_quality_menu.configure(state="normal")
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
            legend_text = ("Guía de etiquetas en la lista:\n" "✨ Ideal: Formato óptimo para editar sin conversión.\n" "⚠️ Recodificar: Formato no compatible con editores.")
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
    
    def _initialize_presets_file(self):
        """
        Inicializa el archivo presets.json si no existe.
        Si ya existe, lo deja como está.
        """
        if not os.path.exists(PRESETS_FILE):
            print(f"DEBUG: Archivo presets.json no encontrado. Creando con presets por defecto...")
            
            default_presets = {
                "built_in_presets": {
                    "Archivo - H.265 Normal": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "H.265 (x265)",
                        "recode_profile_name": "Calidad Media (CRF 24)",
                        "recode_audio_codec_name": "AAC",
                        "recode_audio_profile_name": "Buena Calidad (~192kbps)",
                        "recode_container": ".mp4"
                    },
                    "Archivo - H.265 Máxima": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "H.265 (x265)",
                        "recode_profile_name": "Calidad Alta (CRF 20)",
                        "recode_audio_codec_name": "AAC",
                        "recode_audio_profile_name": "Máxima Calidad (~320kbps)",
                        "recode_container": ".mp4"
                    },
                    "Web/Móvil - H.264 Liviano": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "H.264 (x264)",
                        "recode_profile_name": "Calidad Rápida (CRF 28)",
                        "recode_audio_codec_name": "AAC",
                        "recode_audio_profile_name": "Calidad Baja (~128kbps)",
                        "recode_container": ".mp4"
                    },
                    "Web/Móvil - H.264 Normal": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "H.264 (x264)",
                        "recode_profile_name": "Calidad Media (CRF 23)",
                        "recode_audio_codec_name": "AAC",
                        "recode_audio_profile_name": "Alta Calidad (~256kbps)",
                        "recode_container": ".mp4"
                    },
                    "Web/Móvil - H.264 Máxima": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "H.264 (x264)",
                        "recode_profile_name": "Alta Calidad (CRF 18)",
                        "recode_audio_codec_name": "AAC",
                        "recode_audio_profile_name": "Máxima Calidad (~320kbps)",
                        "recode_container": ".mp4"
                    },
                    "Edición - ProRes 422 Proxy": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "Apple ProRes (prores_aw) (Velocidad)",
                        "recode_profile_name": "422 Proxy",
                        "recode_audio_codec_name": "WAV (Sin Comprimir)",
                        "recode_audio_profile_name": "PCM 16-bit",
                        "recode_container": ".mov"
                    },
                    "Edición - ProRes 422": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "Apple ProRes (prores_ks) (Precisión)",
                        "recode_profile_name": "422 HQ",
                        "recode_audio_codec_name": "WAV (Sin Comprimir)",
                        "recode_audio_profile_name": "PCM 16-bit",
                        "recode_container": ".mov"
                    },
                    "Edición - ProRes 422 LT": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "Apple ProRes (prores_aw) (Velocidad)",
                        "recode_profile_name": "422 LT",
                        "recode_audio_codec_name": "WAV (Sin Comprimir)",
                        "recode_audio_profile_name": "PCM 16-bit",
                        "recode_container": ".mov"
                    },
                    "GIF R\u00e1pido (Baja Calidad)": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": False,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "GIF (animado)",
                        "recode_profile_name": "Baja Calidad (R\u00e1pido)",
                        "custom_bitrate_value": "8",
                        "custom_gif_fps": "",
                        "custom_gif_width": "",
                        "recode_container": ".gif",
                        "recode_audio_codec_name": "-",
                        "recode_audio_profile_name": "-",
                        "fps_force_enabled": False,
                        "fps_value": "",
                        "resolution_change_enabled": False,
                        "res_width": "",
                        "res_height": "",
                        "no_upscaling_enabled": False
                    },
                    "GIF (Media Calidad)": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": False,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "GIF (animado)",
                        "recode_profile_name": "Calidad Media (540p, 24fps)",
                        "custom_bitrate_value": "8",
                        "custom_gif_fps": "",
                        "custom_gif_width": "",
                        "recode_container": ".gif",
                        "recode_audio_codec_name": "-",
                        "recode_audio_profile_name": "-",
                        "fps_force_enabled": False,
                        "fps_value": "",
                        "resolution_change_enabled": False,
                        "res_width": "",
                        "res_height": "",
                        "no_upscaling_enabled": False
                    },
                    "GIF (Alta Calidad)": {
                        "mode_compatibility": "Video+Audio",
                        "recode_video_enabled": True,
                        "recode_audio_enabled": False,
                        "keep_original_file": True,
                        "recode_proc": "CPU",
                        "recode_codec_name": "GIF (animado)",
                        "recode_profile_name": "Calidad Alta (720p, 30fps)",
                        "custom_bitrate_value": "8",
                        "custom_gif_fps": "",
                        "custom_gif_width": "",
                        "recode_container": ".gif",
                        "recode_audio_codec_name": "-",
                        "recode_audio_profile_name": "-",
                        "fps_force_enabled": False,
                        "fps_value": "",
                        "resolution_change_enabled": False,
                        "res_width": "",
                        "res_height": "",
                        "no_upscaling_enabled": False
                    },
                    "Audio - MP3 128kbps": {
                        "mode_compatibility": "Solo Audio",
                        "recode_video_enabled": False,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_audio_codec_name": "MP3 (libmp3lame)",
                        "recode_audio_profile_name": "128kbps (CBR)",
                        "recode_container": ".mp3"
                    },
                    "Audio - MP3 192kbps": {
                        "mode_compatibility": "Solo Audio",
                        "recode_video_enabled": False,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_audio_codec_name": "MP3 (libmp3lame)",
                        "recode_audio_profile_name": "192kbps (CBR)",
                        "recode_container": ".mp3"
                    },
                    "Audio - MP3 320kbps": {
                        "mode_compatibility": "Solo Audio",
                        "recode_video_enabled": False,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_audio_codec_name": "MP3 (libmp3lame)",
                        "recode_audio_profile_name": "320kbps (CBR)",
                        "recode_container": ".mp3"
                    },
                    "Audio - AAC 192kbps": {
                        "mode_compatibility": "Solo Audio",
                        "recode_video_enabled": False,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_audio_codec_name": "AAC",
                        "recode_audio_profile_name": "Buena Calidad (~192kbps)",
                        "recode_container": ".m4a"
                    },
                    "Audio - WAV 16-bit (Sin pérdida)": {
                        "mode_compatibility": "Solo Audio",
                        "recode_video_enabled": False,
                        "recode_audio_enabled": True,
                        "keep_original_file": True,
                        "recode_audio_codec_name": "WAV (Sin Comprimir)",
                        "recode_audio_profile_name": "PCM 16-bit",
                        "recode_container": ".wav"
                    }
                },
                "custom_presets": []
            }
        
            try:
                with open(PRESETS_FILE, 'w') as f:
                    json.dump(default_presets, f, indent=4)
                print(f"DEBUG: presets.json creado exitosamente en {PRESETS_FILE}")
            except IOError as e:
                print(f"ERROR: No se pudo crear presets.json: {e}")
        else:
            print(f"DEBUG: presets.json ya existe. Cargando...")

    def _load_presets(self):
        """
        Carga los presets desde presets.json.
        Retorna un diccionario con built_in_presets y custom_presets.
        """
        try:
            if os.path.exists(PRESETS_FILE):
                with open(PRESETS_FILE, 'r') as f:
                    presets_data = json.load(f)
                    return presets_data
            else:
                print("ERROR: presets.json no encontrado")
                return {"built_in_presets": {}, "custom_presets": []}
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: No se pudo cargar presets.json: {e}")
            return {"built_in_presets": {}, "custom_presets": []}
        
    def open_save_preset_dialog(self):
        """Abre el diálogo para guardar un preset personalizado."""
        dialog = self.SavePresetDialog(self)
        self.wait_window(dialog)
        
        if dialog.result:
            self._save_custom_preset(dialog.result)

    def export_preset_file(self):
        """
        Exporta el preset seleccionado como archivo .dowp_preset
        """
        selected_preset_name = self.recode_preset_menu.get()
        
        if selected_preset_name.startswith("- ") or not selected_preset_name:
            messagebox.showwarning("Selecciona un preset", "Por favor, selecciona un preset para exportar.")
            return
        
        preset_data = None
        for custom_preset in self.custom_presets:
            if custom_preset["name"] == selected_preset_name:
                preset_data = custom_preset["data"]
                break
        
        if preset_data is None:
            messagebox.showwarning(
                "No se puede exportar",
                "Solo puedes exportar presets personalizados.\nLos presets integrados no se pueden exportar."
            )
            return
        
        preset_content = self._create_preset_file_content(preset_data, selected_preset_name)
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".dowp_preset",
            filetypes=[("DowP Preset", "*.dowp_preset"), ("JSON", "*.json"), ("All Files", "*.*")],
            initialfile=f"{selected_preset_name}.dowp_preset"
        )
        
        self.lift()
        self.focus_force()
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(preset_content, f, indent=4)
                
                messagebox.showinfo(
                    "Exportado",
                    f"El preset '{selected_preset_name}' ha sido exportado exitosamente.\n\nUbicación: {file_path}"
                )
                print(f"DEBUG: Preset exportado: {file_path}")
            except Exception as e:
                messagebox.showerror("Error al exportar", f"No se pudo exportar el preset:\n{e}")
                print(f"ERROR al exportar preset: {e}")

    def import_preset_file(self):
        """
        Importa un archivo .dowp_preset y lo agrega a presets personalizados
        """
        file_path = filedialog.askopenfilename(
            filetypes=[("DowP Preset", "*.dowp_preset"), ("JSON", "*.json"), ("All Files", "*.*")],
            title="Selecciona un archivo .dowp_preset para importar"
        )
        
        self.lift()
        self.focus_force()
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r') as f:
                preset_content = json.load(f)
            
            if not self._validate_preset_file(preset_content):
                messagebox.showerror(
                    "Archivo inválido",
                    "El archivo no es un preset válido o está corrupto."
                )
                return
            
            preset_name = preset_content.get("preset_name", "Sin nombre")
            preset_data = preset_content.get("data")
            
            existing_preset = next((p for p in self.custom_presets if p["name"] == preset_name), None)
            if existing_preset:
                result = messagebox.askyesno(
                    "Preset duplicado",
                    f"El preset '{preset_name}' ya existe.\n¿Deseas sobrescribirlo?"
                )
                if not result:
                    return
                
                self.custom_presets = [p for p in self.custom_presets if p["name"] != preset_name]
            
            self.custom_presets.append({
                "name": preset_name,
                "data": preset_data
            })
            
            presets_data = self._load_presets()
            presets_data["custom_presets"] = self.custom_presets
            
            with open(PRESETS_FILE, 'w') as f:
                json.dump(presets_data, f, indent=4)
            
            self._populate_preset_menu()
            
            messagebox.showinfo(
                "Importado",
                f"El preset '{preset_name}' ha sido importado exitosamente.\nAhora está disponible en Modo Rápido."
            )
            print(f"DEBUG: Preset importado: {preset_name}")
            
        except json.JSONDecodeError:
            messagebox.showerror(
                "Error",
                "El archivo no es un JSON válido."
            )
        except Exception as e:
            messagebox.showerror(
                "Error al importar",
                f"No se pudo importar el preset:\n{e}"
            )
            print(f"ERROR al importar preset: {e}")

    def delete_preset_file(self):
        """
        Elimina el preset personalizado seleccionado
        """
        selected_preset_name = self.recode_preset_menu.get()
        
        if selected_preset_name.startswith("- ") or not selected_preset_name:
            messagebox.showwarning("Selecciona un preset", "Por favor, selecciona un preset para eliminar.")
            return
        
        is_custom = any(p["name"] == selected_preset_name for p in self.custom_presets)
        if not is_custom:
            messagebox.showwarning(
                "No se puede eliminar",
                "Solo puedes eliminar presets personalizados.\nLos presets integrados no se pueden eliminar."
            )
            return
        
        result = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Estás seguro de que deseas eliminar el preset '{selected_preset_name}'?\n\nEsta acción no se puede deshacer."
        )
        
        if not result:
            return
        
        try:
            self.custom_presets = [p for p in self.custom_presets if p["name"] != selected_preset_name]
            
            presets_data = self._load_presets()
            presets_data["custom_presets"] = self.custom_presets
            
            with open(PRESETS_FILE, 'w') as f:
                json.dump(presets_data, f, indent=4)
            
            self._populate_preset_menu()
            
            messagebox.showinfo(
                "Eliminado",
                f"El preset '{selected_preset_name}' ha sido eliminado exitosamente."
            )
            print(f"DEBUG: Preset eliminado: {selected_preset_name}")
            
        except Exception as e:
            messagebox.showerror(
                "Error al eliminar",
                f"No se pudo eliminar el preset:\n{e}"
            )
            print(f"ERROR al eliminar preset: {e}")
    
    def _save_custom_preset(self, preset_name):
        """
        Guarda la configuración actual como un preset personalizado en presets.json
        """
        try:
            current_preset_data = {
                "mode_compatibility": self.mode_selector.get(),
                "recode_video_enabled": self.recode_video_checkbox.get() == 1,
                "recode_audio_enabled": self.recode_audio_checkbox.get() == 1,
                "keep_original_file": self.keep_original_checkbox.get() == 1,
                "recode_proc": self.proc_type_var.get(),
                "recode_codec_name": self.recode_codec_menu.get(),
                "recode_profile_name": self.recode_profile_menu.get(),
                "custom_bitrate_value": self.custom_bitrate_entry.get(),
                "custom_gif_fps": self.custom_gif_fps_entry.get(),
                "custom_gif_width": self.custom_gif_width_entry.get(),
                "recode_container": self.recode_container_label.cget("text"),
                "recode_audio_codec_name": self.recode_audio_codec_menu.get(),
                "recode_audio_profile_name": self.recode_audio_profile_menu.get(),
                "fps_force_enabled": self.fps_checkbox.get() == 1,
                "fps_value": self.fps_entry.get(),
                "resolution_change_enabled": self.resolution_checkbox.get() == 1,
                "res_width": self.width_entry.get(),
                "res_height": self.height_entry.get(),
                "no_upscaling_enabled": self.no_upscaling_checkbox.get() == 1,
            }
            
            presets_data = self._load_presets()
            
            if preset_name in presets_data["built_in_presets"]:
                messagebox.showerror(
                    "Nombre duplicado",
                    f"El nombre '{preset_name}' ya existe en los presets integrados.\nPor favor, usa otro nombre."
                )
                return
            
            existing_preset = next((p for p in presets_data["custom_presets"] if p["name"] == preset_name), None)
            if existing_preset:
                result = messagebox.askyesno(
                    "Preset ya existe",
                    f"El preset '{preset_name}' ya existe.\n¿Deseas sobrescribirlo?"
                )
                if result:
                    presets_data["custom_presets"] = [p for p in presets_data["custom_presets"] if p["name"] != preset_name]
                else:
                    return
            
            presets_data["custom_presets"].append({
                "name": preset_name,
                "data": current_preset_data
            })
            
            with open(PRESETS_FILE, 'w') as f:
                json.dump(presets_data, f, indent=4)
            
            print(f"DEBUG: Preset personalizado '{preset_name}' guardado exitosamente.")
            
            self.built_in_presets = presets_data.get("built_in_presets", {})
            self.custom_presets = presets_data.get("custom_presets", [])
            
            self._populate_preset_menu()
            
            messagebox.showinfo(
                "Éxito",
                f"El ajuste '{preset_name}' ha sido guardado.\nAhora está disponible en Modo Rápido."
            )
            
        except Exception as e:
            print(f"ERROR al guardar preset: {e}")
            messagebox.showerror(
                "Error al guardar",
                f"No se pudo guardar el ajuste:\n{e}"
            )

    def _create_preset_file_content(self, preset_data, preset_name):
        """
        Crea el contenido de un archivo .dowp_preset con validación.
        Retorna un diccionario que será guardado como JSON.
        """
        import hashlib
        
        preset_content = {
            "preset_name": preset_name,
            "preset_version": "1.0",
            "data": preset_data
        }
        
        content_string = json.dumps(preset_data, sort_keys=True)
        checksum = hashlib.sha256(content_string.encode()).hexdigest()
        preset_content["checksum"] = checksum
        
        return preset_content
    
    def _validate_preset_file(self, preset_content):
        """
        Valida la integridad de un archivo .dowp_preset.
        Retorna True si es válido, False si no.
        """
        import hashlib
        
        if not isinstance(preset_content, dict):
            print("ERROR: El archivo no es un preset válido (no es diccionario)")
            return False
        
        if "checksum" not in preset_content or "data" not in preset_content:
            print("ERROR: El preset no tiene estructura válida")
            return False
        
        stored_checksum = preset_content.get("checksum")
        preset_data = preset_content.get("data")
        
        content_string = json.dumps(preset_data, sort_keys=True)
        calculated_checksum = hashlib.sha256(content_string.encode()).hexdigest()
        
        if stored_checksum != calculated_checksum:
            print("ERROR: El checksum no coincide (archivo corrupto o modificado)")
            return False
        
        return True

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
            elif system == "Darwin":
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
        initial_dir = self.output_path_entry.get()
        if not os.path.isdir(initial_dir):
            initial_dir = self.default_download_path or str(Path.home() / "Downloads")
        save_path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile=f"{clean_title}.jpg",
            defaultextension=".jpg", 
            filetypes=[("JPEG Image", "*.jpg"), ("PNG Image", "*.png")]
        )
        if save_path:
            try:
                if save_path.lower().endswith((".jpg", ".jpeg")): self.pil_image.convert("RGB").save(save_path, quality=95)
                else: self.pil_image.save(save_path)
                self.on_process_finished(True, f"Miniatura guardada en {os.path.basename(save_path)}", save_path)
            except Exception as e: self.on_process_finished(False, f"Error al guardar miniatura: {e}", None)

    def _execute_subtitle_download_subprocess(self, url, subtitle_info, save_path):
        """
        Descarga un subtítulo usando la API de yt-dlp, preservando la lógica de cookies
        y detección de archivos.
        """
        try:
            self.after(0, self.update_progress, 0, "Iniciando proceso de yt-dlp...")
            
            output_dir = os.path.dirname(save_path)
            files_before = set(os.listdir(output_dir)) 
            lang_code = subtitle_info['lang']
            base_name = os.path.splitext(os.path.basename(save_path))[0]
            output_template = os.path.join(output_dir, f"{base_name}.%(ext)s")

            ydl_opts = {
                'no_warnings': True,
                'skip_download': True,
                'noplaylist': True,
                'outtmpl': output_template,
                'writesubtitles': True,
                'subtitleslangs': [lang_code],
                'writeautomaticsub': subtitle_info.get('automatic', False),
                'ffmpeg_location': self.ffmpeg_processor.ffmpeg_path
            }

            if self.clean_subtitle_check.winfo_ismapped() and self.clean_subtitle_check.get() == 1:
                ydl_opts['subtitlesformat'] = 'best/vtt/best'
                ydl_opts['convertsubtitles'] = 'srt'
            else:
                ydl_opts['subtitlesformat'] = subtitle_info['ext']

            cookie_mode = self.cookie_mode_menu.get()
            if cookie_mode == "Archivo Manual..." and self.cookie_path_entry.get():
                ydl_opts['cookiefile'] = self.cookie_path_entry.get()
            elif cookie_mode != "No usar":
                browser_arg = self.browser_var.get()
                profile = self.browser_profile_entry.get()
                if profile: browser_arg += f":{profile}"
                ydl_opts['cookiesfrombrowser'] = (browser_arg,)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            files_after = set(os.listdir(output_dir))
            new_files = files_after - files_before
            
            if not new_files:
                raise FileNotFoundError("yt-dlp terminó, pero no se detectó ningún archivo de subtítulo nuevo.")
            
            new_filename = new_files.pop()
            final_output_path = os.path.join(output_dir, new_filename)

            if final_output_path.lower().endswith('.srt'):
                self.after(0, self.update_progress, 90, "Estandarizando formato SRT...")
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
        self.download_button.configure(text="Cancelar", fg_color=self.CANCEL_BTN_COLOR, hover_color=self.CANCEL_BTN_HOVER, command=self.cancel_operation)
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
            "custom_bitrate_value": self.custom_bitrate_entry.get(),
            "custom_gif_fps": self.custom_gif_fps_entry.get() or "15",
            "custom_gif_width": self.custom_gif_width_entry.get() or "480",
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
            "keep_original_on_clip": self.keep_original_on_clip_check.get() == 1 
        }

        recode_mode = self.recode_mode_selector.get()

        if recode_mode == "Modo Rápido":
            if self.apply_quick_preset_checkbox.get() == 1:
                selected_preset_name = self.recode_preset_menu.get()
                preset_params = self._find_preset_params(selected_preset_name)
                options.update(preset_params)
            
            options["keep_original_file"] = self.keep_original_quick_checkbox.get() == 1
        elif recode_mode == "Modo Manual":
            manual_options = {
                "recode_video_enabled": self.recode_video_checkbox.get() == 1,
                "recode_audio_enabled": self.recode_audio_checkbox.get() == 1,
                "keep_original_file": self.keep_original_checkbox.get() == 1,
                "recode_proc": self.proc_type_var.get(),
                "recode_codec_name": self.recode_codec_menu.get(),
                "recode_profile_name": self.recode_profile_menu.get(),
                "custom_bitrate_value": self.custom_bitrate_entry.get(),
                "custom_gif_fps": self.custom_gif_fps_entry.get() or "15",
                "custom_gif_width": self.custom_gif_width_entry.get() or "480",
                "recode_container": self.recode_container_label.cget("text"),
                "recode_audio_codec_name": self.recode_audio_codec_menu.get(),
                "recode_audio_profile_name": self.recode_audio_profile_menu.get(),
                "fps_force_enabled": self.fps_checkbox.get() == 1,
                "fps_value": self.fps_entry.get(),
                "resolution_change_enabled": self.resolution_checkbox.get() == 1,
                "res_width": self.width_entry.get(),
                "res_height": self.height_entry.get(),
                "no_upscaling_enabled": self.no_upscaling_checkbox.get() == 1,
                "original_width": self.original_video_width,
                "original_height": self.original_video_height,
            }
            options.update(manual_options)

        elif recode_mode == "Modo Rápido":
            selected_preset_name = self.recode_preset_menu.get()
            preset_params = self._find_preset_params(selected_preset_name)
            
            options.update(preset_params)

        self.active_operation_thread = threading.Thread(target=self._execute_download_and_recode, args=(options,), daemon=True)
        self.active_operation_thread.start()

    def _execute_download_and_recode(self, options):
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
        try:
            if options["mode"] == "Solo Audio" and not self.audio_formats and self.video_formats:
                audio_extraction_fallback = True
                print("DEBUG: No hay pistas de audio dedicadas. Se activó el fallback de extracción desde el video.")
                best_video_label = next(iter(self.video_formats))
                options["video_format_label"] = best_video_label
            final_output_path_str = options["output_path"]
            user_facing_title = self.sanitize_filename(options['title'])
            title_to_check = user_facing_title
            output_path = Path(final_output_path_str)

            conflicting_file = None

            video_format_info = self.video_formats.get(options["video_format_label"], {})
            audio_format_info = self.audio_formats.get(options["audio_format_label"], {})
            mode = options["mode"]

            expected_ext = self._predict_final_extension(video_format_info, audio_format_info, mode)

            final_filename_to_check = f"{user_facing_title}{expected_ext}"
            full_path_to_check = Path(output_path) / final_filename_to_check

            if full_path_to_check.exists():
                conflicting_file = full_path_to_check
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
                    
            downloaded_filepath, temp_video_for_extraction = self._perform_download(
                options, 
                user_facing_title, 
                audio_extraction_fallback
            )
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
                    downloaded_filepath = clipped_filepath 
                    
                    options["fragment_enabled"] = False
                    options["start_time"] = ""
                    options["end_time"] = ""
                    
                    try: 
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
                
                recode_base_filename = user_facing_title + "_recoded"
                
                final_recoded_path = self._execute_recode_master(
                    input_file=downloaded_filepath,
                    output_dir=final_output_path_str,
                    base_filename=recode_base_filename,
                    recode_options=options
                )
                
                if not options.get("keep_original_file", False):
                    if os.path.exists(downloaded_filepath):
                        os.remove(downloaded_filepath)
                
                self.after(0, self.on_process_finished, True, "Recodificación completada", final_recoded_path)
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
                    self.after(0, lambda: self.on_process_finished(False, "Recodificación cancelada. Archivo original conservado.", keep_file_on_cancel, show_dialog=False))
                else:
                    self.after(0, lambda: self.on_process_finished(False, error_message, downloaded_filepath, show_dialog=False))
            else:
                self.after(0, lambda: self.on_process_finished(False, error_message, downloaded_filepath, show_dialog=False))
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
            self._perform_cleanup(
                process_successful, 
                recode_phase_started, 
                final_recoded_path, 
                temp_video_for_extraction, 
                backup_file_path, 
                cleanup_required, 
                user_facing_title, 
                options,  
                keep_file_on_cancel, 
                downloaded_filepath
            )

    def _execute_recode_master(self, input_file, output_dir, base_filename, recode_options):
        """
        Función maestra y unificada que maneja toda la lógica de recodificación.
        Es llamada tanto por el modo URL como por el modo Local.
        """
        final_recoded_path = None
        backup_file_path = None
        
        try:
            self.after(0, self.update_progress, 0, "Preparando recodificación...")
            final_container = recode_options["recode_container"]
            if not recode_options['recode_video_enabled'] and not recode_options['recode_audio_enabled']:
                _, original_extension = os.path.splitext(input_file)
                final_container = original_extension

            final_filename_with_ext = f"{base_filename}{final_container}"
            final_recoded_path = os.path.join(output_dir, final_filename_with_ext)
            temp_output_path = final_recoded_path + ".temp"

            output_path_candidate = Path(final_recoded_path)
            if output_path_candidate.exists():
                self.ui_request_data = {"type": "ask_conflict_recode", "filename": output_path_candidate.name}
                self.ui_response_event.clear(); self.ui_request_event.set(); self.ui_response_event.wait()
                user_choice = self.ui_response_data.get("result", "cancel")
                if user_choice == "cancel": raise UserCancelledError("Operación cancelada por el usuario.")
                elif user_choice == "rename":
                    counter = 1
                    while True:
                        new_path_candidate = Path(output_dir) / f"{base_filename} ({counter}){final_container}"
                        if not new_path_candidate.exists():
                            final_recoded_path = str(new_path_candidate); break
                        counter += 1
                    temp_output_path = final_recoded_path + ".temp"
                elif user_choice == "overwrite":
                    backup_file_path = final_recoded_path + ".bak"
                    if os.path.exists(backup_file_path): os.remove(backup_file_path)
                    os.rename(final_recoded_path, backup_file_path)

            final_ffmpeg_params = []; pre_params = []
            
            final_ffmpeg_params.extend(['-f', recode_options['recode_container'].lstrip('.')])

            if recode_options.get("fragment_enabled"):
                if recode_options.get("start_time"): pre_params.extend(['-ss', recode_options.get("start_time")])
                if recode_options.get("end_time"): pre_params.extend(['-to', recode_options.get("end_time")])

            if recode_options['mode'] != "Solo Audio":
                if recode_options["recode_video_enabled"]:
                    final_ffmpeg_params.extend(["-metadata:s:v:0", "rotate=0"])
                    proc = recode_options["recode_proc"]
                    codec_db = self.ffmpeg_processor.available_encoders[proc]["Video"]
                    codec_data = codec_db.get(recode_options["recode_codec_name"])
                    ffmpeg_codec_name = next((k for k in codec_data if k != 'container'), None)
                    profile_params_list = codec_data[ffmpeg_codec_name].get(recode_options["recode_profile_name"])

                    if profile_params_list == "CUSTOM_GIF":
                        try:
                            fps = int(recode_options["custom_gif_fps"])
                            width = int(recode_options["custom_gif_width"])
                            filter_string = f"[0:v] fps={fps},scale={width}:-1,split [a][b];[a] palettegen [p];[b][p] paletteuse"
                            final_ffmpeg_params.extend(['-filter_complex', filter_string])
                        except (ValueError, TypeError):
                            raise Exception("Valores de FPS/Ancho para GIF no son válidos.")

                    elif isinstance(profile_params_list, str) and "CUSTOM_BITRATE" in profile_params_list:
                        bitrate_mbps = float(recode_options["custom_bitrate_value"])
                        bitrate_k = int(bitrate_mbps * 1000)
                        if "nvenc" in ffmpeg_codec_name:
                            params_str = f"-c:v {ffmpeg_codec_name} -preset p5 -rc vbr -b:v {bitrate_k}k -maxrate {bitrate_k}k"
                        else:
                            params_str = f"-c:v {ffmpeg_codec_name} -b:v {bitrate_k}k -maxrate {bitrate_k}k -bufsize {bitrate_k*2}k -pix_fmt yuv420p"
                        final_ffmpeg_params.extend(params_str.split())
                    else: 
                        final_ffmpeg_params.extend(profile_params_list)

                    video_filters = []
                    if recode_options.get("fps_force_enabled") and recode_options.get("fps_value"):
                        video_filters.append(f'fps={recode_options["fps_value"]}')
                    if recode_options.get("resolution_change_enabled"):
                        try:
                            width, height = int(recode_options["res_width"]), int(recode_options["res_height"])
                            if recode_options.get("no_upscaling_enabled"):
                                original_width, original_height = recode_options.get("original_width", 0), recode_options.get("original_height", 0)
                                if original_width > 0 and width > original_width: width = original_width
                                if original_height > 0 and height > original_height: height = original_height
                            video_filters.append(f'scale={width}:{height}')
                        except (ValueError, TypeError): pass
                    
                    if video_filters and "filter_complex" not in final_ffmpeg_params:
                        final_ffmpeg_params.extend(['-vf', ",".join(video_filters)])
                else:
                    final_ffmpeg_params.extend(["-c:v", "copy"])

            is_gif_format = "GIF" in recode_options.get("recode_codec_name", "")

            if not is_gif_format:
                is_pro_video_format = False
                if recode_options["recode_video_enabled"]:
                    if any(x in recode_options["recode_codec_name"] for x in ["ProRes", "DNxH"]):
                        is_pro_video_format = True
                
                if is_pro_video_format:
                    final_ffmpeg_params.extend(["-c:a", "pcm_s16le"])
                elif recode_options["recode_audio_enabled"]:
                    audio_codec_db = self.ffmpeg_processor.available_encoders["CPU"]["Audio"]
                    audio_codec_data = audio_codec_db.get(recode_options["recode_audio_codec_name"])
                    ffmpeg_audio_codec = next((k for k in audio_codec_data if k != 'container'), None)
                    audio_profile_params = audio_codec_data[ffmpeg_audio_codec].get(recode_options["recode_audio_profile_name"])
                    if audio_profile_params:
                        final_ffmpeg_params.extend(audio_profile_params)
                else:
                    final_ffmpeg_params.extend(["-c:a", "copy"])

            command_options = {
                "input_file": input_file, "output_file": temp_output_path,
                "duration": recode_options.get('duration', 0), "ffmpeg_params": final_ffmpeg_params,
                "pre_params": pre_params, 
                "mode": recode_options.get('mode'),

                "selected_video_stream_index": None if "-filter_complex" in final_ffmpeg_params else recode_options.get('selected_video_stream_index'),
                
                "selected_audio_stream_index": None if is_gif_format else recode_options.get('selected_audio_stream_index')
            }

            self.ffmpeg_processor.execute_recode(command_options, self.update_progress, self.cancellation_event)

            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, final_recoded_path)
            if backup_file_path and os.path.exists(backup_file_path):
                os.remove(backup_file_path)
            return final_recoded_path
        except Exception as e:
            if os.path.exists(temp_output_path):
                try: os.remove(temp_output_path)
                except OSError: pass
            if backup_file_path and os.path.exists(backup_file_path):
                try: os.rename(backup_file_path, final_recoded_path)
                except OSError: pass
            raise e

    def _perform_download(self, options, user_facing_title, audio_extraction_fallback):
        downloaded_filepath = None
        temp_video_for_extraction = None
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
                        if not self.video_formats and not self.audio_formats:
                            strict_flexible_selector = 'best'
                        else:
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
                            if not self.video_formats and not self.audio_formats:
                                final_selector = 'best'
                            else:
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
        return downloaded_filepath, temp_video_for_extraction

    def _perform_cleanup(self, process_successful, recode_phase_started, final_recoded_path, temp_video_for_extraction, backup_file_path, cleanup_required, user_facing_title, options, keep_file_on_cancel, downloaded_filepath):
        """Esta función se encargará de TODA la limpieza del bloque 'finally'."""
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
        """ Restablece los botones a su estado original, aplicando el color correcto. """
        self.analyze_button.configure(
            text=self.original_analyze_text,
            fg_color=self.original_analyze_fg_color,
            command=self.original_analyze_command,
            state="normal"
        )

        if self.local_file_path:
            button_text = "Iniciar Proceso"
            button_color = self.PROCESS_BTN_COLOR
        else:
            button_text = self.original_download_text
            button_color = self.DOWNLOAD_BTN_COLOR

        hover_color = self.PROCESS_BTN_HOVER if self.local_file_path else self.DOWNLOAD_BTN_HOVER

        self.download_button.configure(
            text=button_text,
            fg_color=button_color,
            hover_color=hover_color,
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
                return thumb_path
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo guardar la miniatura automáticamente: {e}")
        return None

    def on_process_finished(self, success, message, final_filepath, show_dialog=True):
        """
        Callback UNIFICADO. Usa las listas de extensiones de la clase para una clasificación robusta.
        """
        if success and final_filepath and ACTIVE_TARGET_SID:
            with LATEST_FILE_LOCK:
                file_package = {
                    "video": None,
                    "thumbnail": None,
                    "subtitle": None
                }
                file_ext_without_dot = os.path.splitext(final_filepath)[1].lower().lstrip('.')
                if file_ext_without_dot in self.VIDEO_EXTENSIONS or file_ext_without_dot in self.AUDIO_EXTENSIONS:
                    file_package["video"] = final_filepath.replace('\\', '/')
                elif file_ext_without_dot == 'srt':
                    file_package["subtitle"] = final_filepath.replace('\\', '/')
                elif file_ext_without_dot == 'jpg':
                     file_package["thumbnail"] = final_filepath.replace('\\', '/')
                if file_package["video"]:
                    output_dir = os.path.dirname(final_filepath)
                    base_name = os.path.splitext(os.path.basename(final_filepath))[0]
                    if base_name.endswith('_recoded'):
                        base_name = base_name.rsplit('_recoded', 1)[0]
                    expected_thumb_path = os.path.join(output_dir, f"{base_name}.jpg")
                    if os.path.exists(expected_thumb_path):
                        file_package["thumbnail"] = expected_thumb_path.replace('\\', '/')
                    for item in os.listdir(output_dir):
                        if item.startswith(base_name) and item.lower().endswith('.srt'):
                             file_package["subtitle"] = os.path.join(output_dir, item).replace('\\', '/')
                             break
                print(f"INFO: Paquete de archivos listo para enviar: {file_package}")
                socketio.emit('new_file', {'filePackage': file_package}, to=ACTIVE_TARGET_SID)
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
    
    def _predict_final_extension(self, video_info, audio_info, mode):
        """
        Predice la extensión de archivo más probable que yt-dlp usará
        al fusionar los streams de video y audio seleccionados.
        """

        if mode == "Solo Audio":
            return f".{audio_info.get('ext', 'mp3')}"

        if video_info.get('is_combined'):
            return f".{video_info.get('ext', 'mp4')}"

        v_ext = video_info.get('ext')
        a_ext = audio_info.get('ext')
        
        if not a_ext or a_ext == 'none':
            return f".{v_ext}" if v_ext else ".mp4"

        if v_ext == 'mp4' and a_ext in ['m4a', 'mp4']:
            return ".mp4"

        if v_ext == 'webm' and a_ext in ['webm', 'opus']:
            return ".webm"

        return ".mkv"

    def update_progress(self, percentage, message):
        """
        Actualiza la barra de progreso. AHORA es inteligente y acepta
        valores en escala 0-100 (de descargas/recodificación) o 0.0-1.0.
        """
        try:
            progress_value = float(percentage)
        except (ValueError, TypeError):
            progress_value = 0.0

        if progress_value > 1.0:
            progress_value = progress_value / 100.0

        capped_percentage = max(0.0, min(progress_value, 1.0))
        
        def _update():
            self.progress_bar.set(capped_percentage)
            self.progress_label.configure(text=message)
            
        self.after(0, _update)

    def start_analysis_thread(self, event=None):
        self.analysis_is_complete = False
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
        self.analyze_button.configure(text="Cancelar", fg_color=self.CANCEL_BTN_COLOR, hover_color=self.CANCEL_BTN_HOVER, command=self.cancel_operation)
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
        Ejecuta el análisis usando la API de yt-dlp y captura la salida de texto
        para preservar la lógica de análisis de subtítulos.
        """
        try:
            self.after(0, self.update_progress, 0, "Iniciando análisis de URL...")

            ydl_opts = {
                'no_warnings': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'referer': url,
                'noplaylist': True,
                'playlist_items': '1',
                'listsubtitles': True,
                'progress_hooks': [lambda d: self.cancellation_event.is_set() and (_ for _ in ()).throw(UserCancelledError("Análisis cancelado."))],
            }

            cookie_mode = self.cookie_mode_menu.get()
            if cookie_mode == "Archivo Manual..." and self.cookie_path_entry.get():
                ydl_opts['cookiefile'] = self.cookie_path_entry.get()
            elif cookie_mode != "No usar":
                browser_arg = self.browser_var.get()
                profile = self.browser_profile_entry.get()
                if profile:
                    browser_arg += f":{profile}"
                ydl_opts['cookiesfrombrowser'] = (browser_arg,)

            text_capture = io.StringIO()
            info = None

            with redirect_stdout(text_capture):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                    except Exception as e:
                        print(f"\nError interno de yt-dlp: {e}")
            
            if self.cancellation_event.is_set():
                raise UserCancelledError("Análisis cancelado por el usuario.")

            captured_text = text_capture.getvalue()
            other_lines = captured_text.strip().splitlines()

            if info is None:
                raise Exception(f"yt-dlp falló: {' '.join(other_lines)}")

            if 'subtitles' not in info and 'automatic_captions' not in info:
                info['subtitles'], info['automatic_captions'] = self._parse_subtitle_lines_from_text(other_lines)

            if info.get('is_live'):
                self.after(0, self.on_analysis_complete, None, "AVISO: La URL apunta a una transmisión en vivo.")
                return
                
            self.after(0, self.on_analysis_complete, info)

        except UserCancelledError:
            self.after(0, self.on_process_finished, False, "Análisis cancelado.", None, show_dialog=False)
        except Exception as e:
            error_message = f"ERROR: {e}"
            if isinstance(e, yt_dlp.utils.DownloadError):
                error_message = f"ERROR de yt-dlp: {str(e).replace('ERROR:', '').strip()}"
            self.after(0, self.on_analysis_complete, None, error_message)
        finally:
            self.active_subprocess_pid = None

    def _parse_subtitle_lines_from_text(self, lines):
        """
        Parsea una lista de líneas de texto (salida de --list-subs) y la convierte
        en diccionarios de subtítulos manuales y automáticos.
        """
        subtitles = {}
        auto_captions = {}
        current_section = None
        for line in lines:
            if "Available subtitles for" in line:
                current_section = 'subs'
                continue
            if "Available automatic captions for" in line:
                current_section = 'auto'
                continue
            if line.startswith("Language") or line.startswith("ID") or line.startswith('---'):
                continue
            parts = re.split(r'\s+', line.strip())
            if len(parts) < 3:
                continue
            lang_code = parts[0]
            formats = [p.strip() for p in parts[1:-1] if p.strip()]
            if current_section == 'subs':
                target_dict = subtitles
            elif current_section == 'auto':
                target_dict = auto_captions
            else:
                continue
            if lang_code not in target_dict:
                target_dict[lang_code] = []
            for fmt in formats:
                target_dict[lang_code].append({
                    'ext': fmt,
                    'url': None, 
                    'name': ''
                })
        return subtitles, auto_captions

    def on_analysis_complete(self, info, error_message=None):
        try:
            if info and info.get('_type') in ('playlist', 'multi_video'):
                if info.get('entries') and len(info['entries']) > 0:
                    print("DEBUG: Playlist detectada. Extrayendo información del primer video.")
                    info = info['entries'][0]
                else:
                    print("DEBUG: Se detectó una playlist vacía o no válida.")
                    error_message = "La URL corresponde a una lista vacía o no válida."
                    info = None
            self.progress_bar.stop()
            if not info or error_message:
                self.analysis_is_complete = False
                self.progress_bar.set(0)
                final_error_message = error_message or "ERROR: No se pudo obtener la información."
                print(f"Error en el análisis de la URL: {final_error_message}")
                self.title_entry.delete(0, 'end')
                self.title_entry.insert(0, final_error_message)
                self.create_placeholder_label("Fallo el análisis")
                self._clear_subtitle_menus()
                return
            self.progress_bar.set(1)
            self.analysis_is_complete = True
            url = self.url_entry.get()
            self.analysis_cache[url] = {'data': info, 'timestamp': time.time()}
            print(f"DEBUG: Resultado para '{url}' guardado en caché.")
            if info.get('extractor_key', '').lower().startswith('twitch'):
                print("DEBUG: Detectada URL de Twitch, eliminando datos de rechat y deshabilitando menús.")
                info['subtitles'] = {}
                info['automatic_captions'] = {}
                self._clear_subtitle_menus()
            self.title_entry.delete(0, 'end')
            self.title_entry.insert(0, info.get('title', 'Sin título'))
            self.video_duration = info.get('duration', 0)
            formats = info.get('formats', [])
            self.has_video_streams = any(f.get('height') for f in formats)
            self.has_audio_streams = any(f.get('acodec') != 'none' or (not f.get('height') and f.get('vcodec') == 'none') for f in formats)
            thumbnail_url = info.get('thumbnail')
            if thumbnail_url:
                threading.Thread(target=self.load_thumbnail, args=(thumbnail_url,), daemon=True).start()
            elif self.has_audio_streams and not self.has_video_streams:
                self.create_placeholder_label("🎵", font_size=80)
                self.save_thumbnail_button.configure(state="disabled")
                self.auto_save_thumbnail_check.deselect()
                self.auto_save_thumbnail_check.configure(state="disabled")
            else:
                self.create_placeholder_label("Miniatura")
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
                self.thumbnail_label.image = ctk_image
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
        v_opts = list(self.video_formats.keys()) or ["- Sin Formatos de Video -"]
        a_opts = list(self.audio_formats.keys()) or ["- Sin Pistas de Audio -"]

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

        self.video_quality_menu.configure(state="normal" if self.video_formats else "disabled", values=v_opts)
        self.video_quality_menu.set(default_video_selection)
        
        self.audio_quality_menu.configure(state="normal" if self.audio_formats else "disabled", values=a_opts)
        self.audio_quality_menu.set(default_audio_selection)
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