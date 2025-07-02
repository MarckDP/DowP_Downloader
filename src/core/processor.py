# src/core/processor.py

import subprocess
import threading
import os
import re

# Excepción personalizada para manejar cancelaciones de usuario
class UserCancelledError(Exception):
    """Excepción lanzada cuando el usuario cancela una operación."""
    pass

# --- BASE DE DATOS DE CÓDECS Y PERFILES ---
CODEC_PROFILES = {
    "Video": {
        "H.264 (x264)": {
            "libx264": {
                "Alta Calidad (CRF 18)": "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p",
                "Calidad Media (CRF 23)": "-c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p",
                "Calidad Rápida (CRF 28)": "-c:v libx264 -preset veryfast -crf 28 -pix_fmt yuv420p"
            }, "container": ".mp4"
        },
        "H.265 (x265)": {
            "libx265": {
                "Calidad Alta (CRF 20)": "-c:v libx265 -preset slow -crf 20 -tag:v hvc1",
                "Calidad Media (CRF 24)": "-c:v libx265 -preset medium -crf 24 -tag:v hvc1"
            }, "container": ".mp4"
        },
        "Apple ProRes (prores_ks)": {
            "prores_ks": {
                "422 Proxy": "-c:v prores_ks -profile:v 0", # ProRes Proxy
                "422 LT": "-c:v prores_ks -profile:v 1",    # ProRes LT
                "422 Standard": "-c:v prores_ks -profile:v 2", # ProRes 422
                "422 HQ": "-c:v prores_ks -profile:v 3",    # ProRes 422 HQ
                "4444": "-c:v prores_ks -profile:v 4 -pix_fmt yuv444p10le", # ProRes 4444
                "4444 XQ": "-c:v prores_ks -profile:v 5 -pix_fmt yuv444p10le" # ProRes 4444 XQ
            }, "container": ".mov"
        },
        "DNxHD (dnxhd)": { # Digital Nonlinear Extensible High Definition (codec específico para HD)
            "dnxhd": {
                # Perfiles de DNxHD (8-bit 4:2:2) - Comunes y bien soportados por 'dnxhd'
                "1080p25 (145 Mbps)": "-c:v dnxhd -b:v 145M -pix_fmt yuv422p",
                "1080p29.97 (145 Mbps)": "-c:v dnxhd -b:v 145M -pix_fmt yuv422p",
                "1080i50 (120 Mbps)": "-c:v dnxhd -b:v 120M -pix_fmt yuv422p -flags +ildct+ilme -top 1",
                "1080i59.94 (120 Mbps)": "-c:v dnxhd -b:v 120M -pix_fmt yuv422p -flags +ildct+ilme -top 1",
                "720p50 (90 Mbps)": "-c:v dnxhd -b:v 90M -pix_fmt yuv422p",
                "720p59.94 (90 Mbps)": "-c:v dnxhd -b:v 90M -pix_fmt yuv422p"
            }, "container": ".mov" # También puede ser .mxf
        },
        "DNxHR (dnxhd)": { # Digital Nonlinear Extensible High Resolution (utilizando el codificador 'dnxhd')
            "dnxhd": {
                # Perfiles de DNxHR (simulados via dnxhd)
                "LB (8-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_lb -pix_fmt yuv422p",
                "SQ (8-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_sq -pix_fmt yuv422p",
                "HQ (8-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_hq -pix_fmt yuv422p",
                "HQX (10-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le",
                "444 (10-bit 4:4:4)": "-c:v dnxhd -profile:v dnxhr_444 -pix_fmt yuv444p10le"
            }, "container": ".mov" # También puede ser .mxf
        },
        "XDCAM HD422": { # Basado en MPEG-2, 4:2:2 a 50Mbps
            "mpeg2video": {
                "1080i50 (50 Mbps)": "-c:v mpeg2video -pix_fmt yuv422p -b:v 50M -flags +ildct+ilme -top 1 -minrate 50M -maxrate 50M",
                "1080p25 (50 Mbps)": "-c:v mpeg2video -pix_fmt yuv422p -b:v 50M -minrate 50M -maxrate 50M",
                "720p50 (50 Mbps)": "-c:v mpeg2video -pix_fmt yuv422p -b:v 50M -minrate 50M -maxrate 50M"
            }, "container": ".mxf" # XDCAM suele usar MXF
        },
        "XDCAM HD 35": { # Basado en MPEG-2, 4:2:0 o 4:2:2 a 35Mbps
            "mpeg2video": {
                "1080i50 (35 Mbps)": "-c:v mpeg2video -pix_fmt yuv420p -b:v 35M -flags +ildct+ilme -top 1 -minrate 35M -maxrate 35M",
                "1080p25 (35 Mbps)": "-c:v mpeg2video -pix_fmt yuv420p -b:v 35M -minrate 35M -maxrate 35M",
                "720p50 (35 Mbps)": "-c:v mpeg2video -pix_fmt yuv420p -b:v 35M -minrate 35M -maxrate 35M"
            }, "container": ".mxf"
        },
        "AVC-Intra 100 (x264)": { # Emulación de AVC-Intra 100 usando libx264
            "libx264": {
                # Importante: AVC-Intra es un códec intra-frame (all-I). Esto es una emulación.
                # FFmpeg no tiene un codificador nativo de AVC-Intra a menos que se compile con soporte específico.
                # Esto usa x264 en modo intra-frame con alta calidad y bitrate constante.
                "1080p (100 Mbps)": "-c:v libx264 -preset veryfast -profile:v high422 -level 4.1 -x264opts \"nal-hrd=cbr:force-cfr=1\" -b:v 100M -maxrate 100M -bufsize 200M -g 1 -keyint_min 1 -intra",
                "720p (50 Mbps)": "-c:v libx264 -preset veryfast -profile:v high422 -level 3.1 -x264opts \"nal-hrd=cbr:force-cfr=1\" -b:v 50M -maxrate 50M -bufsize 100M -g 1 -keyint_min 1 -intra"
            }, "container": ".mov" # También puede ser .mxf
        },
        "GoPro CineForm": {
            "cfhd": {
                "Baja": "-c:v cfhd -quality 1", "Media": "-c:v cfhd -quality 4", "Alta": "-c:v cfhd -quality 6"
            }, "container": ".mov"
        },
        "QT Animation (qtrle)": { "qtrle": { "Estándar": "-c:v qtrle" }, "container": ".mov" },
        "HAP": { "hap": { "Estándar": "-c:v hap" }, "container": ".mov" },
        "VP8 (libvpx)": {
             "libvpx": {
                "Calidad Alta (CRF 10)": "-c:v libvpx -crf 10 -b:v 0",
                "Calidad Media (CRF 20)": "-c:v libvpx -crf 20 -b:v 0"
             }, "container": ".webm"
        },
        "VP9 (libvpx-vp9)": {
            "libvpx-vp9": {
                "Calidad Alta (CRF 28)": "-c:v libvpx-vp9 -crf 28 -b:v 0",
                "Calidad Media (CRF 33)": "-c:v libvpx-vp9 -crf 33 -b:v 0"
            }, "container": ".webm"
        },
        "AV1 (libaom-av1)": {
            "libaom-av1": {
                "Calidad Alta (CRF 28)": "-c:v libaom-av1 -strict experimental -cpu-used 4 -crf 28",
                "Calidad Media (CRF 35)": "-c:v libaom-av1 -strict experimental -cpu-used 6 -crf 35"
            }, "container": ".mkv"
        },
        "H.264 (NVIDIA NVENC)": {
            "h264_nvenc": {
                "Calidad Alta (CQP 18)": "-c:v h264_nvenc -preset p7 -rc vbr -cq 18",
                "Calidad Media (CQP 23)": "-c:v h264_nvenc -preset p5 -rc vbr -cq 23"
            }, "container": ".mp4"
        },
        "H.265/HEVC (NVIDIA NVENC)": {
            "hevc_nvenc": {
                "Calidad Alta (CQP 20)": "-c:v hevc_nvenc -preset p7 -rc vbr -cq 20",
                "Calidad Media (CQP 24)": "-c:v hevc_nvenc -preset p5 -rc vbr -cq 24"
            }, "container": ".mp4"
        },
        "H.264 (Intel QSV)": {
            "h264_qsv": {
                "Alta Calidad": "-c:v h264_qsv -preset veryslow -global_quality 18",
                "Calidad Media": "-c:v h264_qsv -preset medium -global_quality 23"
            }, "container": ".mp4"
        },
        "H.265/HEVC (Intel QSV)": {
            "hevc_qsv": {
                "Alta Calidad": "-c:v hevc_qsv -preset veryslow -global_quality 20",
                "Calidad Media": "-c:v hevc_qsv -preset medium -global_quality 24"
            }, "container": ".mp4"
        },
        "H.264 (AMD AMF)": {
            "h264_amf": {
                "Alta Calidad": "-c:v h264_amf -quality quality -rc cqp -qp_i 18 -qp_p 18",
                "Calidad Balanceada": "-c:v h264_amf -quality balanced -rc cqp -qp_i 23 -qp_p 23"
            }, "container": ".mp4"
        },
        "H.265/HEVC (AMD AMF)": {
            "hevc_amf": {
                "Alta Calidad": "-c:v hevc_amf -quality quality -rc cqp -qp_i 20 -qp_p 20",
                "Calidad Balanceada": "-c:v hevc_amf -quality balanced -rc cqp -qp_i 24 -qp_p 24"
            }, "container": ".mp4"
        },
        "H.264 (Apple VideoToolbox)": {
            "h264_videotoolbox": {
                "Alta Calidad": "-c:v h264_videotoolbox -profile:v high -q:v 70",
                "Calidad Media": "-c:v h264_videotoolbox -profile:v main -q:v 50"
            }, "container": ".mp4"
        },
        "H.265/HEVC (Apple VideoToolbox)": {
            "hevc_videotoolbox": {
                "Alta Calidad": "-c:v hevc_videotoolbox -profile:v main -q:v 80",
                "Calidad Media": "-c:v hevc_videotoolbox -profile:v main -q:v 65"
            }, "container": ".mp4"
        }        
    },
    "Audio": {
        "AAC": {
            "aac": { "Alta Calidad (~256kbps)": "-c:a aac -b:a 256k", "Buena Calidad (~192kbps)": "-c:a aac -b:a 192k" },
            "container": ".m4a"
        },
        "MP3 (libmp3lame)": {
            "libmp3lame": { "320kbps (CBR)": "-c:a libmp3lame -b:a 320k", "192kbps (CBR)": "-c:a libmp3lame -b:a 192k" },
            "container": ".mp3"
        },
        "Opus (libopus)": {
            "libopus": { "Calidad Alta (~192kbps)": "-c:a libopus -b:a 192k", "Calidad Media (~128kbps)": "-c:a libopus -b:a 128k" },
            "container": ".opus"
        },
        "FLAC (Sin Pérdida)": { "flac": { "Nivel de Compresión 5": "-c:a flac -compression_level 5" }, "container": ".flac" },
        "WAV (Sin Comprimir)": { "pcm_s16le": { "PCM 16-bit": "-c:a pcm_s16le" }, "container": ".wav" }
    }
}

class FFmpegProcessor:
    def __init__(self):
        self.ffmpeg_path = "ffmpeg"
        self.gpu_vendor = None
        self.is_detection_complete = False
        self.available_encoders = {"CPU": {"Video": {}, "Audio": {}}, "GPU": {"Video": {}}}

    def run_detection_async(self, callback):
        threading.Thread(target=self._detect_encoders, args=(callback,), daemon=True).start()

    def _detect_encoders(self, callback):
        try:
            # Ocultar la ventana de la consola en Windows
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            subprocess.check_output([self.ffmpeg_path, '-version'], stderr=subprocess.STDOUT, creationflags=creationflags)
            all_encoders_output = subprocess.check_output([self.ffmpeg_path, '-encoders'], text=True, encoding='utf-8', stderr=subprocess.STDOUT, creationflags=creationflags)

            for category, codecs in CODEC_PROFILES.items():
                for friendly_name, details in codecs.items():
                    # El primer elemento es el nombre del codec en ffmpeg
                    ffmpeg_codec_name = list(details.keys())[0]

                    # Se ha corregido para usar concatenación de cadenas en lugar de format()
                    # Esto evita cualquier posible malinterpretación de las llaves {} por format().
                    search_pattern = r"^\s[A-Z\.]{6}\s+" + re.escape(ffmpeg_codec_name) + r"\s"

                    if re.search(search_pattern, all_encoders_output, re.MULTILINE):
                        proc_type = "GPU" if "nvenc" in ffmpeg_codec_name else "CPU"
                        if proc_type == "GPU" and self.gpu_vendor is None:
                            self.gpu_vendor = "NVIDIA" # Asumimos NVIDIA por ahora

                        # Almacenamos el codec disponible
                        target_category = self.available_encoders[proc_type].get(category, {})
                        target_category[friendly_name] = details
                        self.available_encoders[proc_type][category] = target_category

            self.is_detection_complete = True
            callback(True, "Detección completada.")

        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            self.is_detection_complete = True
            callback(False, "Error: ffmpeg no está instalado o no se encuentra en el PATH.")
        except Exception as e:
            self.is_detection_complete = True
            callback(False, f"Error inesperado durante la detección: {e}")

    def execute_recode(self, options, progress_callback, cancellation_event: threading.Event):
        """
        Construye y ejecuta el comando de FFmpeg de forma síncrona (bloqueante),
        capturando el progreso y devolviendo la ruta del archivo final.
        Se ha añadido un mecanismo de cancelación limpia.
        """
        try:
            # Verificar cancelación justo antes de iniciar la recodificación
            if cancellation_event.is_set():
                raise UserCancelledError("Recodificación cancelada por el usuario antes de iniciar.")

            input_file = options['input_file']
            output_file = options['output_file']
            duration = options.get('duration', 0)

            command = ['ffmpeg', '-y', '-progress', '-', '-i', input_file]
            command.extend(options['ffmpeg_params'].split())
            command.append(output_file)

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', creationflags=creationflags)

            for line in iter(process.stdout.readline, ''):
                # Verificar si hay una solicitud de cancelación mientras se lee la salida
                if cancellation_event.is_set():
                    process.terminate() # Terminar el proceso de FFmpeg
                    raise UserCancelledError("Recodificación cancelada por el usuario.")

                # FFmpeg con '-progress -' emite 'out_time_ms=' que es más fiable
                if 'out_time_ms=' in line:
                    progress_us = int(line.strip().split('=')[1])
                    if duration > 0:
                        progress_seconds = progress_us / 1_000_000
                        percentage = (progress_seconds / duration) * 100
                        progress_callback(percentage, f"Recodificando... {percentage:.1f}%")
                # También imprimimos la línea para depuración si es necesario
                # print(line.strip())

            process.wait()
            if process.returncode != 0:
                raise Exception(f"FFmpeg falló con el código {process.returncode}. Revisa los parámetros del códec.")

            return output_file

        except UserCancelledError as e:
            # Relanzamos la excepción UserCancelledError para que la UI pueda manejarla específicamente.
            print(f"DEBUG: Operación de recodificación interrumpida: {e}")
            raise e
        except Exception as e:
            raise Exception(f"Error en recodificación: {e}")