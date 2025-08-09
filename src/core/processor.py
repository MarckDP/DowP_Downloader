import json
import tempfile
import subprocess
import threading
import os
import re
import sys
import time
from .exceptions import UserCancelledError

# Reemplaza el diccionario CODEC_PROFILES existente con este bloque completo
CODEC_PROFILES = {
    "Video": {
        "H.264 (x264)": {
            "libx264": {
                "Alta Calidad (CRF 18)": "-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p",
                "Calidad Media (CRF 23)": "-c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p",
                "Calidad Rápida (CRF 28)": "-c:v libx264 -preset veryfast -crf 28 -pix_fmt yuv420p",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.265 (x265)": {
            "libx265": {
                "Calidad Alta (CRF 20)": "-c:v libx265 -preset slow -crf 20 -tag:v hvc1",
                "Calidad Media (CRF 24)": "-c:v libx265 -preset medium -crf 24 -tag:v hvc1",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "Apple ProRes (prores_aw) (Velocidad)": {
            "prores_aw": {
                "422 Proxy":    "-map 0:v:0 -map 0:a? -c:v prores_aw -profile:v 0 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "422 LT":       "-map 0:v:0 -map 0:a? -c:v prores_aw -profile:v 1 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "422 Standard": "-map 0:v:0 -map 0:a? -c:v prores_aw -profile:v 2 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "422 HQ":       "-map 0:v:0 -map 0:a? -c:v prores_aw -profile:v 3 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "4444":         "-map 0:v:0 -map 0:a? -c:v prores_aw -profile:v 4 -vendor ap10 -pix_fmt yuv444p10le -threads 0",
                "4444 XQ":      "-map 0:v:0 -map 0:a? -c:v prores_aw -profile:v 5 -vendor ap10 -pix_fmt yuv444p10le -threads 0"
            }, "container": ".mov"
        },
        "Apple ProRes (prores_ks) (Precisión)": {
            "prores_ks": {
                "422 Proxy":    "-c:v prores_ks -profile:v 0 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "422 LT":       "-c:v prores_ks -profile:v 1 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "422 Standard": "-c:v prores_ks -profile:v 2 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "422 HQ":       "-c:v prores_ks -profile:v 3 -vendor ap10 -pix_fmt yuv422p10le -threads 0",
                "4444":         "-c:v prores_ks -profile:v 4 -vendor ap10 -pix_fmt yuv444p10le -threads 0",
                "4444 XQ":      "-c:v prores_ks -profile:v 5 -vendor ap10 -pix_fmt yuv444p10le -threads 0"
            }, "container": ".mov"
        },
        "DNxHD (dnxhd)": {
            "dnxhd": {
                "1080p25 (145 Mbps)": "-c:v dnxhd -b:v 145M -pix_fmt yuv422p",
                "1080p29.97 (145 Mbps)": "-c:v dnxhd -b:v 145M -pix_fmt yuv422p",
                "1080i50 (120 Mbps)": "-c:v dnxhd -b:v 120M -pix_fmt yuv422p -flags +ildct+ilme -top 1",
                "1080i59.94 (120 Mbps)": "-c:v dnxhd -b:v 120M -pix_fmt yuv422p -flags +ildct+ilme -top 1",
                "720p50 (90 Mbps)": "-c:v dnxhd -b:v 90M -pix_fmt yuv422p",
                "720p59.94 (90 Mbps)": "-c:v dnxhd -b:v 90M -pix_fmt yuv422p"
            }, "container": ".mov"
        },
        "DNxHR (dnxhd)": {
            "dnxhd": {
                "LB (8-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_lb -pix_fmt yuv422p",
                "SQ (8-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_sq -pix_fmt yuv422p",
                "HQ (8-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_hq -pix_fmt yuv422p",
                "HQX (10-bit 4:2:2)": "-c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le",
                "444 (10-bit 4:4:4)": "-c:v dnxhd -profile:v dnxhr_444 -pix_fmt yuv444p10le"
            }, "container": ".mov"
        },
        "VP8 (libvpx)": {
             "libvpx": {
                "Calidad Alta (CRF 10)": "-c:v libvpx -crf 10 -b:v 0",
                "Calidad Media (CRF 20)": "-c:v libvpx -crf 20 -b:v 0",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR"
             }, "container": ".webm"
        },
        "VP9 (libvpx-vp9)": {
            "libvpx-vp9": {
                "Calidad Alta (CRF 28)": "-c:v libvpx-vp9 -crf 28 -b:v 0",
                "Calidad Media (CRF 33)": "-c:v libvpx-vp9 -crf 33 -b:v 0",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR"
            }, "container": ".webm"
        },
        "AV1 (libaom-av1)": {
            "libaom-av1": {
                "Calidad Alta (CRF 28)": "-c:v libaom-av1 -strict experimental -cpu-used 4 -crf 28",
                "Calidad Media (CRF 35)": "-c:v libaom-av1 -strict experimental -cpu-used 6 -crf 35",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR"
            }, "container": ".mkv"
        },
        "H.264 (NVIDIA NVENC)": {
            "h264_nvenc": {
                "Calidad Alta (CQP 18)": "-c:v h264_nvenc -preset p7 -rc vbr -cq 18",
                "Calidad Media (CQP 23)": "-c:v h264_nvenc -preset p5 -rc vbr -cq 23",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.265/HEVC (NVIDIA NVENC)": {
            "hevc_nvenc": {
                "Calidad Alta (CQP 20)": "-c:v hevc_nvenc -preset p7 -rc vbr -cq 20",
                "Calidad Media (CQP 24)": "-c:v hevc_nvenc -preset p5 -rc vbr -cq 24",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "AV1 (NVENC)": {
            "av1_nvenc": {
                "Calidad Alta (CQP 24)": "-c:v av1_nvenc -preset p7 -rc vbr -cq 24",
                "Calidad Media (CQP 28)": "-c:v av1_nvenc -preset p5 -rc vbr -cq 28",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.264 (AMD AMF)": {
            "h264_amf": {
                "Alta Calidad": "-c:v h264_amf -quality quality -rc cqp -qp_i 18 -qp_p 18",
                "Calidad Balanceada": "-c:v h264_amf -quality balanced -rc cqp -qp_i 23 -qp_p 23",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.265/HEVC (AMD AMF)": {
            "hevc_amf": {
                "Alta Calidad": "-c:v hevc_amf -quality quality -rc cqp -qp_i 20 -qp_p 20",
                "Calidad Balanceada": "-c:v hevc_amf -quality balanced -rc cqp -qp_i 24 -qp_p 24",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "AV1 (AMF)": {
            "av1_amf": {
                "Alta Calidad": "-c:v av1_amf -quality quality -rc cqp -qp_i 28 -qp_p 28",
                "Calidad Balanceada": "-c:v av1_amf -quality balanced -rc cqp -qp_i 32 -qp_p 32",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.264 (Intel QSV)": {
            "h264_qsv": {
                "Alta Calidad": "-c:v h264_qsv -preset veryslow -global_quality 18",
                "Calidad Media": "-c:v h264_qsv -preset medium -global_quality 23",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.265/HEVC (Intel QSV)": {
            "hevc_qsv": {
                "Alta Calidad": "-c:v hevc_qsv -preset veryslow -global_quality 20",
                "Calidad Media": "-c:v hevc_qsv -preset medium -global_quality 24",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "AV1 (QSV)": {
            "av1_qsv": {
                "Calidad Alta": "-c:v av1_qsv -global_quality 25 -preset slow",
                "Calidad Media": "-c:v av1_qsv -global_quality 30 -preset medium",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "VP9 (QSV)": {
            "vp9_qsv": {
                "Calidad Alta": "-c:v vp9_qsv -global_quality 25 -preset slow",
                "Calidad Media": "-c:v vp9_qsv -global_quality 30 -preset medium",
                "Bitrate Personalizado (VBR)": "CUSTOM_BITRATE_VBR",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.264 (Apple VideoToolbox)": {
            "h264_videotoolbox": {
                "Alta Calidad": "-c:v h264_videotoolbox -profile:v high -q:v 70",
                "Calidad Media": "-c:v h264_videotoolbox -profile:v main -q:v 50",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "H.265/HEVC (Apple VideoToolbox)": {
            "hevc_videotoolbox": {
                "Alta Calidad": "-c:v hevc_videotoolbox -profile:v main -q:v 80",
                "Calidad Media": "-c:v hevc_videotoolbox -profile:v main -q:v 65",
                "Bitrate Personalizado (CBR)": "CUSTOM_BITRATE_CBR"
            }, "container": ".mp4"
        },
        "XDCAM HD422": {
            "mpeg2video": {
                "1080i50 (50 Mbps)": "-c:v mpeg2video -pix_fmt yuv422p -b:v 50M -flags +ildct+ilme -top 1 -minrate 50M -maxrate 50M",
                "1080p25 (50 Mbps)": "-c:v mpeg2video -pix_fmt yuv422p -b:v 50M -minrate 50M -maxrate 50M",
                "720p50 (50 Mbps)": "-c:v mpeg2video -pix_fmt yuv422p -b:v 50M -minrate 50M -maxrate 50M"
            }, "container": ".mxf"
        },
        "XDCAM HD 35": {
            "mpeg2video": {
                "1080i50 (35 Mbps)": "-c:v mpeg2video -pix_fmt yuv420p -b:v 35M -flags +ildct+ilme -top 1 -minrate 35M -maxrate 35M",
                "1080p25 (35 Mbps)": "-c:v mpeg2video -pix_fmt yuv420p -b:v 35M -minrate 35M -maxrate 35M",
                "720p50 (35 Mbps)": "-c:v mpeg2video -pix_fmt yuv420p -b:v 35M -minrate 35M -maxrate 35M"
            }, "container": ".mxf"
        },
        "AVC-Intra 100 (x264)": {
            "libx264": {
                "1080p (100 Mbps)": "-c:v libx264 -preset veryfast -profile:v high422 -level 4.1 -b:v 100M -minrate 100M -maxrate 100M -bufsize 2M -g 1 -keyint_min 1 -pix_fmt yuv422p10le",
                "720p (50 Mbps)": "-c:v libx264 -preset veryfast -profile:v high422 -level 3.1 -b:v 50M -minrate 50M -maxrate 50M -bufsize 1M -g 1 -keyint_min 1 -pix_fmt yuv422p10le"
            }, "container": ".mov"
        },
        "GoPro CineForm": {
            "cfhd": {
                "Baja": "-c:v cfhd -quality 1", "Media": "-c:v cfhd -quality 4", "Alta": "-c:v cfhd -quality 6"
            }, "container": ".mov"
        },
        "QT Animation (qtrle)": { "qtrle": { "Estándar": "-c:v qtrle" }, "container": ".mov" },
        "HAP": { "hap": { "Estándar": "-c:v hap" }, "container": ".mov" }
    },
    "Audio": {
        "AAC": {
            "aac": {
                "Alta Calidad (~256kbps)": "-c:a aac -b:a 256k",
                "Buena Calidad (~192kbps)": "-c:a aac -b:a 192k",
                "Calidad Media (~128kbps)": "-c:a aac -b:a 128k"
            },
            "container": ".m4a"
        },
        "MP3 (libmp3lame)": {
            "libmp3lame": {
                "320kbps (CBR)": "-c:a libmp3lame -b:a 320k",
                "256kbps (VBR)": "-c:a libmp3lame -q:a 0",
                "192kbps (CBR)": "-c:a libmp3lame -b:a 192k"
            },
            "container": ".mp3"
        },
        "Opus (libopus)": {
            "libopus": {
                "Calidad Transparente (~256kbps)": "-c:a libopus -b:a 256k",
                "Calidad Alta (~192kbps)": "-c:a libopus -b:a 192k",
                "Calidad Media (~128kbps)": "-c:a libopus -b:a 128k"
            },
            "container": ".opus"
        },
        "Vorbis (libvorbis)": {
            "libvorbis": {
                "Calidad Muy Alta (q8)": "-c:a libvorbis -q:a 8",
                "Calidad Alta (q6)": "-c:a libvorbis -q:a 6",
                "Calidad Media (q4)": "-c:a libvorbis -q:a 4"
            },
            "container": ".ogg"
        },
        "AC-3 (Dolby Digital)": {
            "ac3": {
                "Stereo (192kbps)": "-c:a ac3 -b:a 192k",
                "Stereo (256kbps)": "-c:a ac3 -b:a 256k",
                "Surround 5.1 (448kbps)": "-c:a ac3 -b:a 448k -ac 6",
                "Surround 5.1 (640kbps)": "-c:a ac3 -b:a 640k -ac 6"
            },
            "container": ".ac3"
        },
        "ALAC (Apple Lossless)": {
            "alac": {
                "Estándar (Sin Pérdida)": "-c:a alac"
            },
            "container": ".m4a"
        },
        "FLAC (Sin Pérdida)": {
            "flac": {
                "Nivel de Compresión 5": "-c:a flac -compression_level 5",
                "Nivel de Compresión 8 (Más Lento)": "-c:a flac -compression_level 8"
            },
            "container": ".flac"
        },
        "WAV (Sin Comprimir)": {
            "pcm_s16le": {
                "PCM 16-bit": "-c:a pcm_s16le",
                "PCM 24-bit": "-c:a pcm_s24le"
            },
            "container": ".wav"
        },
        "WMA v2 (Windows Media)": {
            "wmav2": {
                "Calidad Alta (192kbps)": "-c:a wmav2 -b:a 192k",
                "Calidad Media (128kbps)": "-c:a wmav2 -b:a 128k"
            },
            "container": ".wma"
        }
    }
}

class FFmpegProcessor:
    def __init__(self):
        if getattr(sys, 'frozen', False):
            project_root = os.path.dirname(sys.executable)
        else:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        bin_dir = os.path.join(project_root, "bin")
        ffmpeg_exe_name = "ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
        self.ffmpeg_path = os.path.join(bin_dir, ffmpeg_exe_name)
        self.gpu_vendor = None
        self.is_detection_complete = False
        self.available_encoders = {"CPU": {"Video": {}, "Audio": {}}, "GPU": {"Video": {}}}
        self.current_process = None
    def cancel_current_process(self):
        """
        Cancela el proceso de FFmpeg que se esté ejecutando actualmente.
        """
        if self.current_process and self.current_process.poll() is None:
            print("DEBUG: Enviando señal de terminación al proceso de FFmpeg...")
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=5) 
                print("DEBUG: Proceso de FFmpeg terminado.")
            except Exception as e:
                print(f"ERROR: No se pudo terminar el proceso de FFmpeg: {e}")
            self.current_process = None

    def run_detection_async(self, callback):
        threading.Thread(target=self._detect_encoders, args=(callback,), daemon=True).start()

    def _detect_encoders(self, callback):
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.check_output([self.ffmpeg_path, '-version'], stderr=subprocess.STDOUT, creationflags=creationflags)
            all_encoders_output = subprocess.check_output([self.ffmpeg_path, '-encoders'], text=True, encoding='utf-8', stderr=subprocess.STDOUT, creationflags=creationflags)
            try:
                if getattr(sys, 'frozen', False):
                    base_path = os.path.dirname(sys.executable)
                else:
                    base_path = os.path.dirname(os.path.abspath(__file__))
                log_path = os.path.join(base_path, "..", "..", "ffmpeg_encoders_log.txt")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("--- ENCODERS DETECTADOS POR FFmpeg ---\n")
                    f.write(all_encoders_output)
                print(f"DEBUG: Se ha guardado un registro de los códecs de FFmpeg en {log_path}")
            except Exception as e:
                print(f"ADVERTENCIA: No se pudo escribir el log de códecs de FFmpeg: {e}")
            for category, codecs in CODEC_PROFILES.items():
                for friendly_name, details in codecs.items():
                    ffmpeg_codec_name = next((key for key in details if key != 'container'), None)
                    if not ffmpeg_codec_name:
                        continue 
                    search_pattern = r"^\s[A-Z\.]{6}\s+" + re.escape(ffmpeg_codec_name) + r"\s"
                    if re.search(search_pattern, all_encoders_output, re.MULTILINE):
                        proc_type = "GPU" if "nvenc" in ffmpeg_codec_name or "qsv" in ffmpeg_codec_name or "amf" in ffmpeg_codec_name or "videotoolbox" in ffmpeg_codec_name else "CPU"
                        if proc_type == "GPU" and self.gpu_vendor is None:
                            if "nvenc" in ffmpeg_codec_name: self.gpu_vendor = "NVIDIA"
                            elif "qsv" in ffmpeg_codec_name: self.gpu_vendor = "Intel"
                            elif "amf" in ffmpeg_codec_name: self.gpu_vendor = "AMD"
                            elif "videotoolbox" in ffmpeg_codec_name: self.gpu_vendor = "Apple"
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
        process = None
        try:
            if cancellation_event.is_set():
                raise UserCancelledError("Recodificación cancelada por el usuario antes de iniciar.")
            input_file = options['input_file']
            output_file = options['output_file']
            duration = options.get('duration', 0)
            command = [self.ffmpeg_path, '-y', '-nostdin', '-progress', '-', '-i', input_file]
            command.extend(options['ffmpeg_params'])
            command.append(output_file)
            print("--- Comando FFmpeg a ejecutar ---")
            print(" ".join(command))
            print("---------------------------------")
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            error_output_buffer = []
            process = subprocess.Popen(command,stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', creationflags=creationflags)
            self.current_process = process

            def read_stream_into_buffer(stream, buffer):
                """Lee línea por línea de un stream y lo guarda en una lista."""
                for line in iter(stream.readline, ''):
                    buffer.append(line.strip())
            stdout_reader_thread = threading.Thread(target=self._read_stdout_for_progress, args=(process.stdout, progress_callback, cancellation_event, duration), daemon=True)
            stderr_reader_thread = threading.Thread(target=read_stream_into_buffer, args=(process.stderr, error_output_buffer), daemon=True)
            stdout_reader_thread.start()
            stderr_reader_thread.start()
            while process.poll() is None:
                if cancellation_event.is_set():
                    raise UserCancelledError("Recodificación cancelada por el usuario.")
                time.sleep(0.2) 
            stdout_reader_thread.join()
            stderr_reader_thread.join() 
            if process.returncode != 0 and not cancellation_event.is_set():
                full_error_log = " ".join(error_output_buffer)
                print(f"\n--- ERROR DETALLADO DE FFmpeg ---\n{full_error_log}\n---------------------------------\n")
                # Y lanzamos una excepción con un mensaje simple para la UI
                raise Exception(f"FFmpeg falló (ver consola para detalles técnicos).")
            if cancellation_event.is_set():
                raise UserCancelledError("Recodificación cancelada por el usuario.")
            return output_file
        except UserCancelledError as e:
            self.cancel_current_process()
            raise e
        except Exception as e:
            self.cancel_current_process()
            raise Exception(f"Error en recodificación: {e}")
        finally:
            if process:
                if process.stdout: process.stdout.close()
                if process.stderr: process.stderr.close()
            self.current_process = None

    def _read_stdout_for_progress(self, stream, progress_callback, cancellation_event, duration):
        """Lee el stdout de FFmpeg para el progreso, actualizando menos frecuentemente."""
        last_reported_percentage = -1.0
        for line in iter(stream.readline, ''):
            if cancellation_event.is_set():
                break
            if 'out_time_ms=' in line:
                try:
                    progress_us = int(line.strip().split('=')[1])
                    if duration > 0:
                        progress_seconds = progress_us / 1_000_000
                        percentage = (progress_seconds / duration) * 100
                        if percentage >= last_reported_percentage + 1.0 or percentage >= 99.9 or percentage <= 0.1:
                            progress_callback(percentage, f"Recodificando... {percentage:.1f}%")
                            last_reported_percentage = percentage
                except ValueError:
                    pass

    def get_local_media_info(self, input_file):
        """
        Usa ffprobe para obtener información detallada de un archivo local.
        Esta versión usa Popen para un manejo más robusto de timeouts y streams.
        """
        command = [
            self.ffmpeg_path.replace('ffmpeg', 'ffprobe'),
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            input_file
        ]
        
        print(f"DEBUG: Ejecutando comando ffprobe con Popen: {' '.join(command)}")

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            # Usamos Popen para un control más fino
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=creationflags
            )
            
            # communicate() maneja la espera y el timeout de forma más segura
            stdout, stderr = process.communicate(timeout=60)
            
            # Comprobamos si hubo un error después de que el proceso terminó
            if process.returncode != 0:
                print("--- ERROR DETALLADO DE FFPROBE (Popen) ---")
                print(f"El proceso ffprobe falló con el código de salida: {process.returncode}")
                print(f"Salida estándar (stdout):\n{stdout}")
                print(f"Salida de error (stderr):\n{stderr}")
                print("-----------------------------------------")
                return None
                
            return json.loads(stdout)

        except subprocess.TimeoutExpired:
            print("--- ERROR: TIMEOUT DE FFPROBE ---")
            print("La operación de análisis del archivo local tardó demasiado (más de 60s) y fue cancelada.")
            if 'process' in locals() and process:
                process.kill() # Aseguramos que el proceso colgado muera
                process.communicate() # Limpiamos los buffers
            print("---------------------------------")
            return None
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"ERROR: No se pudo obtener información de '{input_file}' con ffprobe: {e}")
            return None

    def get_frame_from_video(self, input_file, at_time='00:00:05'):
        """
        Extrae un único fotograma de un video y lo guarda en un archivo temporal.
        Devuelve la ruta al archivo de imagen temporal.
        """
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"dowp_thumbnail_{os.path.basename(input_file)}.jpg")

        command = [
            self.ffmpeg_path,
            '-y',
            '-i', input_file,
            '-ss', at_time,  # Extrae el frame a los 5 segundos (puedes hacerlo aleatorio)
            '-vframes', '1',
            '-q:v', '2', # Buena calidad
            output_path
        ]
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.run(command, check=True, capture_output=True, creationflags=creationflags)
            return output_path
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"ERROR: No se pudo extraer el fotograma: {e}")
            return None

def clean_and_convert_vtt_to_srt(vtt_path):
    """
    Lee un archivo VTT, elimina las etiquetas de estilo karaoke y lo convierte a formato SRT.
    Ahora maneja correctamente múltiples líneas de texto por cada cue de tiempo.
    Sobrescribe el archivo original con la versión SRT si la conversión es exitosa.
    """
    try:
        # Si el archivo ya es SRT y no tiene formato VTT, no hacemos nada.
        if vtt_path.endswith('.srt'):
            with open(vtt_path, 'r', encoding='utf-8') as f:
                content_check = f.read()
                if 'WEBVTT' not in content_check and '<c>' not in content_check:
                    print(f"DEBUG: El archivo '{os.path.basename(vtt_path)}' ya es SRT estándar. No se requiere conversión.")
                    return vtt_path

        with open(vtt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Si no hay etiquetas de karaoke, no es necesario convertir
        if '<c>' not in content and '<v' not in content and 'X-word-ms' not in content and 'WEBVTT' not in content:
            return vtt_path

        print(f"DEBUG: Detectado subtítulo tipo karaoke o VTT en '{vtt_path}'. Convirtiendo a SRT...")
        
        lines = content.splitlines()
        srt_content = []
        cue_index = 1
        current_cue_text = []

        # ... (el resto de la lógica de conversión se mantiene igual) ...
        for i, line in enumerate(lines):
            if '-->' in line:
                if current_cue_text:
                    srt_content.append("\n".join(current_cue_text))
                    srt_content.append("")
                    current_cue_text = []

                srt_content.append(str(cue_index))
                timestamps = line.split('-->')
                start_time = timestamps[0].strip().replace('.', ',')
                end_time = timestamps[1].strip().split(' ')[0].replace('.', ',')
                srt_content.append(f"{start_time} --> {end_time}")
                cue_index += 1
            
            elif line.strip() and '-->' not in line and 'WEBVTT' not in line:
                clean_line = re.sub(r'<[^>]+>', '', line).strip()
                if clean_line:
                    current_cue_text.append(clean_line)
            
            elif not line.strip() and current_cue_text:
                srt_content.append("\n".join(current_cue_text))
                srt_content.append("")
                current_cue_text = []
        
        if current_cue_text:
            srt_content.append("\n".join(current_cue_text))
            srt_content.append("")

        if not srt_content:
            return vtt_path
            
        srt_path = os.path.splitext(vtt_path)[0] + '.srt'
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_content))
            
        # --- LA CORRECCIÓN CLAVE ESTÁ AQUÍ ---
        # Solo borramos el archivo original si la conversión creó un archivo con un nombre diferente (ej. .vtt -> .srt)
        if srt_path != vtt_path and os.path.exists(vtt_path):
            os.remove(vtt_path)

        print(f"DEBUG: Subtítulo convertido exitosamente a '{srt_path}'")
        return srt_path

    except Exception as e:
        print(f"ERROR: Falló la conversión de subtítulo: {e}")
        return vtt_path