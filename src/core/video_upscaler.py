"""
video_upscaler.py
Modulo de reescalado de video usando motores NCNN (Real-ESRGAN, Waifu2x, RealSR, SRMD).
Flujo: extraer frames (FFmpeg) -> reescalar carpeta (NCNN) -> reensamblar + audio (FFmpeg).
"""

import os
import json
import shutil
import tempfile
import subprocess
import multiprocessing
import time
import threading

from src.core.constants import (
    WAIFU2X_MODELS,
    SRMD_MODELS,
    UPSCALING_TOOLS,
)
from src.core.exceptions import UserCancelledError


# ─── Ruta raiz de los binarios ───────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", "bin"))

# ─── Mapeo de contenedores a codecs video/audio seguros ──────────────────────
CONTAINER_CODECS = {
    ".mp4":  {"vcodec": "libx264",      "acodec": "aac",          "pix_fmt": "yuv420p"},
    ".mkv":  {"vcodec": "libx264",      "acodec": "copy",         "pix_fmt": "yuv420p"},
    ".mov":  {"vcodec": "libx264",      "acodec": "aac",          "pix_fmt": "yuv420p"},
    ".avi":  {"vcodec": "libx264",      "acodec": "libmp3lame",   "pix_fmt": "yuv420p"},
}


class VideoUpscaler:
    """
    Motor de reescalado de video usando ejecutables NCNN.
    """

    def __init__(self, ffmpeg_dir: str, upscaling_dir: str = None, cancellation_event=None, progress_callback=None):
        """
        Args:
            ffmpeg_dir: Carpeta donde vive ffmpeg.exe / ffprobe.exe
            upscaling_dir: Ruta base de los modelos de upscaling (opcional)
            cancellation_event: threading.Event para cancelacion externa
            progress_callback: callable(pct: float, msg: str)
        """
        self.ffmpeg_dir = ffmpeg_dir
        self.ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        self.ffprobe_exe = os.path.join(ffmpeg_dir, "ffprobe.exe")
        self.cancellation_event = cancellation_event
        self.progress_callback = progress_callback or (lambda p, m: None)
        
        if upscaling_dir:
            self.models_root = upscaling_dir
        else:
            # Fallback (no recomendado en EXE)
            _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
            BIN_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", "bin"))
            self.models_root = os.path.join(BIN_DIR, "models", "upscaling")

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _check_dependencies(self):
        """Verifica que FFmpeg y FFprobe existan."""
        for exe in [self.ffmpeg_exe, self.ffprobe_exe]:
            if not os.path.exists(exe):
                raise Exception(f"Dependencia no encontrada: {exe}. Por favor, reinstala FFmpeg.")

    def _check_cancel(self, proc=None):
        if self.cancellation_event and self.cancellation_event.is_set():
            if proc:
                try:
                    print(f"DEBUG [VideoUpscaler] Cancelación detectada. Terminando proceso {proc.pid}...")
                    proc.kill()
                    proc.wait(timeout=2.0)
                except:
                    pass
            raise UserCancelledError("Proceso cancelado por el usuario.")

    def _report(self, pct: float, msg: str):
        self.progress_callback(pct, msg)

    def _creationflags(self):
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def _thread_args(self) -> str:
        n = multiprocessing.cpu_count()
        if n >= 8:
            return "2:4:2"
        elif n >= 4:
            return "1:2:2"
        return "1:1:1"

    # ─── Paso 1: Obtener info del video original ─────────────────────────────

    def _get_video_info(self, input_path: str) -> dict:
        """Usa ffprobe para obtener FPS, extension, codec de audio."""
        self._report(2, "Analizando video original...")
        cmd = [
            self.ffprobe_exe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            input_path
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                creationflags=self._creationflags()
            )
            data = json.loads(result.stdout)
        except Exception as e:
            print(f"ADVERTENCIA: ffprobe fallo ({e}), usando valores por defecto.")
            return {"fps": "30", "ext": os.path.splitext(input_path)[1].lower(), "has_audio": False}

        fps = "30"
        has_audio = False

        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video":
                r_fps = stream.get("r_frame_rate", "30/1")
                try:
                    num, den = r_fps.split("/")
                    fps = str(round(int(num) / int(den), 3))
                except Exception:
                    fps = "30"
            elif codec_type == "audio":
                has_audio = True

        ext = os.path.splitext(input_path)[1].lower()
        return {"fps": fps, "ext": ext, "has_audio": has_audio}

    # ─── Paso 2: Extraer frames ──────────────────────────────────────────────

    def _extract_frames(self, input_path: str, frames_dir: str, fps: str):
        """Extrae todos los frames como PNG con FFmpeg."""
        self._check_cancel()
        self._report(5, "Preparando extracción de fotogramas...")

        pattern = os.path.join(frames_dir, "frame_%08d.png")
        cmd = [
            self.ffmpeg_exe,
            "-i", input_path,
            "-vsync", "0",       # Sin duplicar ni omitir frames
            "-f", "image2",
            pattern,
            "-y"
        ]
        print(f"DEBUG [VideoUpscaler] Ejecutando FFmpeg: {' '.join(cmd)}")
        
        # Hilo para consumir la salida y evitar el llenado del buffer (Deadlock)
        _logs = []
        def log_reader(pipe):
            try:
                for line in pipe:
                    if line:
                        _logs.append(line)
                        # Imprimir solo errores o warnings en consola para no saturar
                        if "error" in line.lower() or "warning" in line.lower():
                            print(f"FFMPEG LOG: {line.strip()}")
            except: pass

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=self._creationflags(),
            text=True,
            errors="ignore",
            bufsize=1
        )
        
        reader_thread = threading.Thread(target=log_reader, args=(proc.stderr,), daemon=True)
        reader_thread.start()
        
        # Monitorizar el proceso
        start_t = time.time()
        while proc.poll() is None:
            self._check_cancel(proc)
            elapsed = time.time() - start_t
            p = min(14.9, 5 + (elapsed / 2.0)) 
            self._report(p, f"Extrayendo fotogramas ({int(elapsed)}s)...")
            time.sleep(0.5)

        proc.wait() # Asegurar cierre
        reader_thread.join(timeout=1.0)
        
        if proc.returncode != 0:
            stderr_out = "".join(_logs)
            print(f"ERROR FFMPEG EXTRACT: {stderr_out}")
            raise Exception(f"FFmpeg fallo al extraer frames (Codigo {proc.returncode}).\n\n{stderr_out[:200]}")

        frames = [f for f in os.listdir(frames_dir) if f.endswith(".png")]
        total = len(frames)
        print(f"INFO [VideoUpscaler] Extraction completa. Total frames: {total}")
        self._report(15, f"Extracción lista: {total} fotogramas.")
        return total

    # ─── Paso 3: Reescalar con NCNN ─────────────────────────────────────────

    def _build_ncnn_cmd(self, engine: str, model_friendly: str, scale: str,
                        in_dir: str, out_dir: str, tile_size: str = "0", denoise: str = "-1", tta: bool = False) -> list:
        """Construye el comando NCNN para procesar un directorio de frames."""
        if not tile_size: tile_size = "0"
        threads_arg = self._thread_args()

        if engine == "SRMD":
            info = SRMD_MODELS.get(model_friendly, {})
            internal = info.get("model", "models-srmd")
            exe = os.path.join(self.models_root, "srmd", "srmd-ncnn-vulkan.exe")
            model_path = os.path.join(self.models_root, "srmd", internal)
            cmd = [
                exe,
                "-i", in_dir, "-o", out_dir,
                "-m", model_path,
                "-n", denoise,
                "-s", scale,
                "-t", tile_size,
                "-f", "png",
                "-j", threads_arg,
            ]
            if tta: cmd += ["-x"]
            return cmd

        elif engine == "Upscayl":
            from src.core.constants import UPSCAYL_MODELS_MAP
            rev_map = {v: k for k, v in UPSCAYL_MODELS_MAP.items()}
            internal_model = rev_map.get(model_friendly, model_friendly)
            
            exe = os.path.join(self.models_root, "upscayl", "upscayl-bin.exe")
            model_path = os.path.join(self.models_root, "upscayl", "models")
            cmd = [
                exe,
                "-i", in_dir, "-o", out_dir,
                "-n", internal_model,
                "-m", model_path,
                "-s", scale,
                "-f", "png",
                "-j", threads_arg,
            ]
            
            # --- NUEVO: Detectar escala nativa del modelo (-z) ---
            import re
            match = re.search(r"[xX]([2-3])", internal_model)
            if match:
                cmd.extend(["-z", match.group(1)])
                
            # upscayl-bin inherits from realesrgan-ncnn so it supports -t and -x
            if tile_size and tile_size != "0":
                cmd += ["-t", tile_size]
            if tta: cmd += ["-x"]
            return cmd

        else:  # Waifu2x
            info = WAIFU2X_MODELS.get(model_friendly, {})
            internal = info.get("model", "models-cunet")
            exe = os.path.join(self.models_root, "waifu2x", "waifu2x-ncnn-vulkan.exe")
            model_path = os.path.join(self.models_root, "waifu2x", internal)
            cmd = [
                exe,
                "-i", in_dir, "-o", out_dir,
                "-m", model_path,
                "-n", denoise,
                "-s", scale,
                "-t", tile_size,
                "-f", "png",
                "-j", threads_arg,
            ]
            if tta: cmd += ["-x"]
            return cmd

    def _run_ncnn(self, engine: str, model_friendly: str, scale: str,
                  in_dir: str, out_dir: str, total_frames: int, tile_size: str = "0", denoise: str = "-1", tta: bool = False):
        """Ejecuta el proceso NCNN y reporta progreso estimado."""
        self._check_cancel()
        self._report(15, f"Iniciando motor AI ({engine})...")

        cmd = self._build_ncnn_cmd(engine, model_friendly, scale, in_dir, out_dir, tile_size, denoise, tta)
        print(f"DEBUG [VideoUpscaler] NCNN cmd: {' '.join(cmd)}")

        exe = cmd[0]
        if not os.path.exists(exe):
            raise Exception(
                f"El motor '{engine}' no está instalado.\n\n"
                f"Búscalo en 'Herramientas de Imagen' y descárgalo desde allí "
                "antes de usar el reescalador de video."
            )

        # Hilo para consumir la salida y evitar el llenado del buffer (Deadlock)
        _logs = []
        def log_reader(pipe):
            try:
                for line in pipe:
                    if line:
                        _logs.append(line)
                        if "error" in line.lower() or "failed" in line.lower():
                            print(f"UPSCALER LOG: {line.strip()}")
            except: pass

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=self._creationflags(),
            text=True,
            errors="ignore",
            bufsize=1
        )

        reader_thread = threading.Thread(target=log_reader, args=(proc.stderr,), daemon=True)
        reader_thread.start()

        # Progreso estimado mientras NCNN trabaja (15% → 85%)
        start_time = time.time()
        last_done = -1
        while proc.poll() is None:
            self._check_cancel(proc)
            
            # Contar PNGs en la carpeta de salida
            try:
                done = len([f for f in os.listdir(out_dir) if f.endswith(".png")])
            except:
                done = last_done

            if done != last_done:
                pct = 15 + (done / max(total_frames, 1)) * 70
                elapsed = int(time.time() - start_time)
                msg = f"Procesando: {done}/{total_frames} fotogramas ({elapsed}s)"
                self._report(min(pct, 84.9), msg)
                print(f"UPSCALER: {msg}")
                last_done = done
            
            time.sleep(1.0) # Esperar un poco mas para no saturar disco contando archivos

        proc.wait()
        reader_thread.join(timeout=1.0)

        if proc.returncode != 0:
            stderr_out = "".join(_logs)
            print(f"ERROR NCNN: {stderr_out}")
            raise Exception(f"El motor AI falló (Código {proc.returncode}).\n\nDetalles:\n{stderr_out[:500]}")

        self._report(85, "Reescalado completado con éxito.")

    # ─── Paso 4: Reensamblar con FFmpeg ─────────────────────────────────────

    def _reassemble(self, upscaled_dir: str, original_path: str,
                    output_path: str, fps: str, container: str, has_audio: bool):
        """Ensambla los frames reescalados + audio original en el video final."""
        self._check_cancel()
        self._report(86, "Preparando ensamblado final...")

        ext = container if container.startswith(".") else f".{container}"
        codec_info = CONTAINER_CODECS.get(ext, CONTAINER_CODECS[".mp4"])

        frame_pattern = os.path.join(upscaled_dir, "frame_%08d.png")

        cmd = [
            self.ffmpeg_exe,
            "-framerate", fps,
            "-i", frame_pattern,
        ]

        if has_audio:
            cmd += ["-i", original_path]

        cmd += [
            "-c:v", codec_info["vcodec"],
            "-pix_fmt", codec_info["pix_fmt"],
            "-crf", "18",           # Calidad alta
            "-preset", "fast",
        ]

        if has_audio:
            # Copiar audio del segundo input (-i original_path)
            cmd += ["-c:a", codec_info["acodec"], "-map", "0:v:0", "-map", "1:a:0?"]

        cmd += ["-y", output_path]

        print(f"DEBUG [VideoUpscaler] Reensamblando: {' '.join(cmd)}")
        
        _logs = []
        def log_reader(pipe):
            try:
                for line in pipe:
                    if line:
                        _logs.append(line)
                        if "error" in line.lower() or "warning" in line.lower():
                            print(f"FFMPEG REASSEMBLE LOG: {line.strip()}")
            except: pass

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=self._creationflags(),
            text=True,
            errors="ignore",
            bufsize=1
        )
        
        reader_thread = threading.Thread(target=log_reader, args=(proc.stderr,), daemon=True)
        reader_thread.start()
        
        start_t = time.time()
        while proc.poll() is None:
            self._check_cancel(proc)
            elapsed = int(time.time() - start_t)
            # Progreso del 86% al 98%
            p = min(98, 86 + (elapsed * 2)) 
            self._report(p, "Guardando video final (unificando audio)...")
            time.sleep(0.5)

        proc.wait()
        reader_thread.join(timeout=1.0)

        if proc.returncode != 0:
            stderr_out = "".join(_logs)
            print(f"ERROR FFMPEG REASSEMBLE: {stderr_out}")
            raise Exception(f"FFmpeg falló al crear el video final (Codigo {proc.returncode}):\n{stderr_out[-500:]}")

        self._report(100, "¡Vídeo reescalado con éxito!")

    # ─── Orquestador principal ───────────────────────────────────────────────

    def upscale_video(self, input_path: str, output_path: str, options: dict) -> str:
        """
        Proceso completo: extraer -> reescalar -> reensamblar.
        """
        self._check_dependencies()
        
        engine = options.get("upscale_engine", "Real-ESRGAN")
        model = options.get("upscale_model_friendly", "")
        if not model:
            if engine == "Upscayl":
                upscayl_models_dir = os.path.join(self.models_root, "upscayl", "models")
                if os.path.exists(upscayl_models_dir):
                    models = [f[:-6] for f in os.listdir(upscayl_models_dir) if f.endswith(".param")]
                    model = sorted(models)[0] if models else "realesrgan-x4plus"
                else:
                    model = "realesrgan-x4plus"
            else:
                model_map = {
                    "Waifu2x":     WAIFU2X_MODELS,
                    "SRMD":        SRMD_MODELS,
                }
                model = list(model_map.get(engine, WAIFU2X_MODELS).keys())[0]

        scale = options.get("upscale_scale", "2").replace("x", "")
        container_choice = options.get("upscale_container", "")

        # Info del video original
        info = self._get_video_info(input_path)
        fps = info["fps"]
        has_audio = info["has_audio"]

        # Determinar extension de salida
        if not container_choice or container_choice.lower() == "mismo que el original":
            ext_out = info["ext"] if info["ext"] else ".mp4"
        else:
            ext_out = container_choice if container_choice.startswith(".") else f".{container_choice}"

        # Ajustar output_path con la extension elegida
        base, _ = os.path.splitext(output_path)
        output_path = base + ext_out

        frames_dir = None
        upscaled_dir = None
        try:
            # Crear directorios temporales
            frames_dir = tempfile.mkdtemp(prefix="dowp_upscale_in_")
            upscaled_dir = tempfile.mkdtemp(prefix="dowp_upscale_out_")

            # Paso 1: Extraer frames
            total = self._extract_frames(input_path, frames_dir, fps)
            if total == 0:
                raise Exception("No se pudieron extraer fotogramas del video.")

            # Paso 2: Reescalar con NCNN (Pasamos el tile size y denoise desde opciones)
            tile_size = options.get("upscale_tile", "0")
            denoise = options.get("upscale_denoise", "-1")
            tta = options.get("upscale_tta", False)
            self._run_ncnn(engine, model, scale, frames_dir, upscaled_dir, total, tile_size=tile_size, denoise=denoise, tta=tta)

            # Paso 3: Reensamblar
            self._reassemble(upscaled_dir, input_path, output_path, fps, ext_out, has_audio)

        finally:
            # Limpieza garantizada
            for d in [frames_dir, upscaled_dir]:
                if d and os.path.exists(d):
                    try:
                        shutil.rmtree(d, ignore_errors=True)
                    except:
                        pass

        return output_path
