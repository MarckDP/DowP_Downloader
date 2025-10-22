import threading
import time
from uuid import uuid4
import os
import yt_dlp

from src.core.downloader import download_media
from src.core.exceptions import UserCancelledError

from src.core.constants import (
    EDITOR_FRIENDLY_CRITERIA, LANGUAGE_ORDER, DEFAULT_PRIORITY,
    VIDEO_EXTENSIONS, AUDIO_EXTENSIONS
)

class Job:
    """
    Contiene la información y el estado de un único trabajo en la cola.
    """
    def __init__(self, config: dict):
        self.job_id: str = str(uuid4()) 
        self.config: dict = config 
        self.analysis_data: dict | None = None
        self.status: str = "PENDING"
        self.progress_message: str = ""
        self.final_filepath: str | None = None

class QueueManager:
    """
    Gestiona la cola de trabajos (Jobs) en un hilo de trabajo separado
    para no bloquear la interfaz de usuario.
    """
    def __init__(self, main_app, ui_callback):
        self.main_app = main_app
        self.ui_callback = ui_callback
        
        self.jobs: list[Job] = []
        self.jobs_lock = threading.Lock()
        
        self.run_thread = None
        self.pause_event = threading.Event()
        self.pause_event.set()  # Iniciar PAUSADO por defecto
        self.stop_event = threading.Event()
        
        self.user_paused: bool = False # <-- AÑADIR ESTE FLAG
        
        print("INFO: QueueManager inicializado.")

    def start_worker_thread(self):
        """Inicia el hilo de trabajo si no está ya corriendo."""
        if self.run_thread is None or not self.run_thread.is_alive():
            self.stop_event.clear()
            self.run_thread = threading.Thread(target=self._worker_thread, daemon=True)
            self.run_thread.start()
            print("INFO: Hilo de trabajo de la cola iniciado.")

    def stop_worker_thread(self):
        """Detiene el hilo de trabajo."""
        self.stop_event.set()
        if self.run_thread:
            self.run_thread.join()
        print("INFO: Hilo de trabajo de la cola detenido.")

    def _worker_thread(self):
        """
        El bucle principal que se ejecuta en segundo plano.
        Busca trabajos pendientes y los procesa.
        """
        print("DEBUG: El worker de lotes ha empezado a escuchar...")
        while not self.stop_event.is_set():
            if self.pause_event.is_set():
                time.sleep(1)
                continue

            job_to_run: Job | None = None
            with self.jobs_lock:
                job_to_run = next((job for job in self.jobs if job.status == "PENDING"), None)
                if job_to_run:
                    job_to_run.status = "RUNNING"
            
            if job_to_run:
                try:
                    self._execute_job(job_to_run)
                    
                except UserCancelledError as e:
                    job_to_run.status = "PENDING"
                    self.ui_callback(job_to_run.job_id, "PENDING", f"Pausado: {e}")
                
                except Exception as e:
                    print(f"ERROR: Falló el trabajo {job_to_run.job_id}: {e}")
                    job_to_run.status = "FAILED"
                    self.ui_callback(job_to_run.job_id, "FAILED", f"Error: {str(e)[:100]}")
            
            else:
                # No hay trabajos pendientes
                batch_tab = self.main_app.batch_tab
                if batch_tab:
                    if not batch_tab.auto_download_checkbox.get():
                        # Auto-descarga está OFF. Pausar la cola automáticamente.
                        if not self.pause_event.is_set():
                            print("INFO: Cola completada. Auto-descargar deshabilitado, pausando...")
                            self.pause_event.set()
                            self.user_paused = False # <-- NO fue el usuario
                            self.ui_callback("QUEUE_STATUS", "PAUSED", "")
                    else:
                        # Auto-descarga está ON. La cola simplemente espera.
                        # Si llegamos aquí, la cola está inactiva (sin trabajos)
                        # y no fue pausada por el usuario.
                        self.user_paused = False
                
                time.sleep(1) 
            
        print("DEBUG: El worker de lotes ha sido detenido.")

    def add_job(self, job: Job):
        """Añade un nuevo trabajo a la cola y notifica a la UI."""
        with self.jobs_lock:
            self.jobs.append(job)
            print(f"INFO: Nuevo trabajo añadido a la cola: {job.config.get('title', job.job_id)}")
        
        self.ui_callback(job.job_id, "PENDING", job.config.get('title', 'Trabajo pendiente...'))

    def start_queue(self):
        """Inicia o reanuda el procesamiento de la cola."""
        if self.pause_event.is_set():
            print("INFO: Reanudando la cola de lotes.")
            self.pause_event.clear()
            self.user_paused = False # <-- El usuario REANUDA
        
        self.start_worker_thread()
        self.ui_callback("QUEUE_STATUS", "RUNNING", "")

    def pause_queue(self):
        """Pausa el procesamiento de la cola."""
        print("INFO: Pausando la cola de lotes.")
        self.pause_event.set()
        self.user_paused = True # <-- El usuario PAUSA
        self.ui_callback("QUEUE_STATUS", "PAUSED", "")

    def remove_job(self, job_id: str):
        """Elimina un trabajo de la cola usando su ID."""
        with self.jobs_lock:
            job_to_remove = next((j for j in self.jobs if j.job_id == job_id), None)
            if job_to_remove:
                if job_to_remove.status == "RUNNING":
                    job_to_remove.status = "FAILED"
                
                self.jobs.remove(job_to_remove)
                print(f"INFO: Trabajo {job_id} eliminado de la cola.")
            else:
                print(f"ADVERTENCIA: Se intentó eliminar el job {job_id} pero no se encontró.")

    def get_job_by_id(self, job_id: str) -> Job | None:
        """Obtiene un objeto Job por su ID."""
        with self.jobs_lock:
            return next((j for j in self.jobs if j.job_id == job_id), None)

    def _execute_job(self, job: Job):
        """
        Ejecuta un único trabajo (descarga).
        """
        self.ui_callback(job.job_id, "RUNNING", "Iniciando...")
        batch_tab = self.main_app.batch_tab
        
        # Verificar modo de descarga global
        thumbnail_mode = batch_tab.thumbnail_mode_var.get()
        
        if thumbnail_mode == "only_thumbnail":
            # Modo especial: solo descargar miniatura
            self._download_thumbnail_only(job)
            return
        
        # Determinar si se debe descargar miniatura
        should_download_thumbnail = False
        if thumbnail_mode == "with_thumbnail":
            # Modo global: siempre descargar miniatura
            should_download_thumbnail = True
        elif thumbnail_mode == "normal":
            # Modo manual: revisar el checkbox individual del job
            should_download_thumbnail = job.config.get('download_thumbnail', False)

        single_tab = self.main_app.single_tab
        
        output_dir = batch_tab.output_path_entry.get()
        if not output_dir:
            raise Exception("Carpeta de salida no especificada.")
        
        # Usar la subcarpeta si fue creada al iniciar la cola
        if hasattr(self, 'subfolder_path') and self.subfolder_path:
            output_dir = self.subfolder_path
            
        conflict_policy = batch_tab.conflict_policy_menu.get()
        speed_limit = batch_tab.speed_limit_entry.get()
        
        url = job.config.get('url')
        title = single_tab.sanitize_filename(job.config.get('title', 'video_lote'))
        mode = job.config.get('mode', 'Video+Audio')
        v_label = job.config.get('video_format_label', '-')
        a_label = job.config.get('audio_format_label', '-')

        # Si no tenemos análisis completo, hacerlo ahora
        if not job.analysis_data or 'formats' not in job.analysis_data:
            self.ui_callback(job.job_id, "RUNNING", "Analizando formatos...")
            try:
                ydl_opts = {
                    'no_warnings': True,
                    'noplaylist': True,
                }
                
                cookie_mode = single_tab.cookie_mode_menu.get()
                if cookie_mode == "Archivo Manual..." and single_tab.cookie_path_entry.get():
                    ydl_opts['cookiefile'] = single_tab.cookie_path_entry.get()
                elif cookie_mode != "No usar":
                    browser_arg = single_tab.browser_var.get()
                    profile = single_tab.browser_profile_entry.get()
                    if profile:
                        browser_arg += f":{profile}"
                    ydl_opts['cookiesfrombrowser'] = (browser_arg,)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    job.analysis_data = ydl.extract_info(url, download=False)
                    
            except Exception as e:
                raise Exception(f"No se pudo analizar el video: {e}")

        if not job.analysis_data:
            raise Exception("Datos de análisis no encontrados en el Job.")

        # Encontrar los format_id
        (job_video_formats, job_audio_formats) = self._rebuild_format_maps(job.analysis_data)
        
        if v_label == "-" or v_label not in job_video_formats:
            v_label = list(job_video_formats.keys())[0] if job_video_formats else "-"
        
        if a_label == "-" or a_label not in job_audio_formats:
            a_label = list(job_audio_formats.keys())[0] if job_audio_formats else "-"

        v_format_dict = job_video_formats.get(v_label)
        a_format_dict = job_audio_formats.get(a_label)

        v_id = v_format_dict.get('format_id') if v_format_dict else None
        a_id = a_format_dict.get('format_id') if a_format_dict else None
        is_combined = v_format_dict.get('is_combined', False) if v_format_dict else False

        precise_selector = ""
        if mode == "Video+Audio":
            if is_combined and v_id: 
                precise_selector = v_id
            elif v_id and a_id: 
                precise_selector = f"{v_id}+{a_id}"
            elif v_id: 
                precise_selector = v_id
        elif mode == "Solo Audio":
            precise_selector = a_id
        
        if not precise_selector:
            precise_selector = "bv+ba/b"
            self.ui_callback(job.job_id, "RUNNING", "Calidad no especificada, usando mejor...")

        # Resolver Conflictos de Archivo
        predicted_ext = self._predict_final_extension(v_format_dict, a_format_dict, mode)
        desired_filepath = os.path.join(output_dir, f"{title}{predicted_ext}")
        
        final_filepath, backup_path = self._resolve_batch_conflict(desired_filepath, conflict_policy)
        
        if final_filepath is None:
            # ¡ESTA ES LA SOLUCIÓN!
            # No lanzamos un error. Marcamos el trabajo como SKIPPED (Omitido)
            # y salimos limpiamente del método.
            print(f"INFO: Job {job.job_id} omitido (archivo ya existe).")
            job.status = "SKIPPED" # <-- CAMBIADO
            job.final_filepath = desired_filepath 
            self.ui_callback(job.job_id, "SKIPPED", "Omitido: El archivo ya existe") # <-- CAMBIADO
            return # Salir de _execute_job
            
        # Preparar Opciones de yt-dlp
        ydl_opts = {
            'outtmpl': final_filepath,
            'overwrites': True,
            'noplaylist': True,
            'ffmpeg_location': self.main_app.ffmpeg_processor.ffmpeg_path,
            'format': precise_selector,
            'restrictfilenames': True,
        }
        
        if speed_limit:
            try: 
                ydl_opts['ratelimit'] = float(speed_limit) * 1024 * 1024
            except ValueError: 
                pass

        cookie_mode = single_tab.cookie_mode_menu.get()
        if cookie_mode == "Archivo Manual..." and single_tab.cookie_path_entry.get():
            ydl_opts['cookiefile'] = single_tab.cookie_path_entry.get()
        elif cookie_mode != "No usar":
            browser_arg = single_tab.browser_var.get()
            profile = single_tab.browser_profile_entry.get()
            if profile: 
                browser_arg += f":{profile}"
            ydl_opts['cookiesfrombrowser'] = (browser_arg,)

        # Definir el hook de progreso
        def download_hook(d):
            if self.pause_event.is_set() or self.stop_event.is_set():
                 raise UserCancelledError("Proceso pausado por el usuario.")

            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    downloaded = d.get('downloaded_bytes', 0)
                    percentage = (downloaded / total) * 100
                    speed = d.get('speed')
                    speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "N/A"
                    self.ui_callback(job.job_id, "RUNNING", f"Descargando... {percentage:.1f}% ({speed_str})")
            
            elif d['status'] == 'finished':
                self.ui_callback(job.job_id, "RUNNING", "Descarga finalizada. Procesando...")

        ydl_opts['progress_hooks'] = [download_hook]
        
        # Iniciar la descarga
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Limpiar backup si todo salió bien
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)

            # Descargar miniatura si está habilitado
            if should_download_thumbnail:
                self._download_thumbnail_alongside_video(job, final_filepath)

            job.status = "COMPLETED"
            job.final_filepath = final_filepath
            self.ui_callback(job.job_id, "COMPLETED", f"Completado: {os.path.basename(final_filepath)}")

        except Exception as e:
            # Si falló, restaurar el backup si existía
            if backup_path and os.path.exists(backup_path):
                if os.path.exists(final_filepath): 
                    os.remove(final_filepath)
                os.rename(backup_path, final_filepath)
            raise e
        
    def _download_thumbnail_only(self, job: Job):
        """
        Descarga únicamente la miniatura del video.
        """
        try:
            batch_tab = self.main_app.batch_tab
            single_tab = self.main_app.single_tab
            
            output_dir = batch_tab.output_path_entry.get()
            if not output_dir:
                raise Exception("Carpeta de salida no especificada.")
            
            # Crear subcarpeta "Thumbnails" para modo solo-miniaturas
            thumbnails_dir = os.path.join(output_dir, "Thumbnails")
            
            # Si hay subcarpeta personalizada del usuario, usarla como base
            if hasattr(self, 'subfolder_path') and self.subfolder_path:
                thumbnails_dir = os.path.join(self.subfolder_path, "Thumbnails")
            
            os.makedirs(thumbnails_dir, exist_ok=True)
            
            # Obtener URL de la miniatura
            thumbnail_url = job.analysis_data.get('thumbnail')
            if not thumbnail_url:
                raise Exception("No se encontró miniatura para este video")
            
            self.ui_callback(job.job_id, "RUNNING", "Descargando miniatura...")
            
            # Descargar la miniatura
            import requests
            response = requests.get(thumbnail_url, timeout=30)
            response.raise_for_status()
            image_data = response.content
            
            # Detectar formato inteligente
            smart_ext = batch_tab.get_smart_thumbnail_extension(image_data)
            
            # Nombre del archivo
            title = single_tab.sanitize_filename(job.config.get('title', 'thumbnail'))
            final_path = os.path.join(thumbnails_dir, f"{title}{smart_ext}")
            
            # Resolver conflictos
            conflict_policy = batch_tab.conflict_policy_menu.get()
            final_path, backup_path = self._resolve_batch_conflict(final_path, conflict_policy)
            
            if final_path is None:
                raise UserCancelledError("Omitido (archivo ya existe)")
            
            # Guardar miniatura
            with open(final_path, 'wb') as f:
                f.write(image_data)
            
            # Limpiar backup si existía
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
            
            job.status = "COMPLETED"
            job.final_filepath = final_path
            self.ui_callback(job.job_id, "COMPLETED", f"Miniatura guardada: {os.path.basename(final_path)}")
            
        except Exception as e:
            # Restaurar backup si falló
            if 'backup_path' in locals() and backup_path and os.path.exists(backup_path):
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(backup_path, final_path)
            raise e
        
    def _download_thumbnail_alongside_video(self, job: Job, video_filepath: str):
        """
        Descarga la miniatura y la guarda junto al video (mismo nombre, diferente extensión).
        """
        try:
            thumbnail_url = job.analysis_data.get('thumbnail')
            if not thumbnail_url:
                print(f"ADVERTENCIA: No se encontró miniatura para {job.job_id}")
                return
            
            self.ui_callback(job.job_id, "RUNNING", "Descargando miniatura...")
            
            # Descargar la miniatura
            import requests
            response = requests.get(thumbnail_url, timeout=30)
            response.raise_for_status()
            image_data = response.content
            
            # Detectar formato inteligente
            batch_tab = self.main_app.batch_tab
            smart_ext = batch_tab.get_smart_thumbnail_extension(image_data)
            
            # Generar nombre basado en el video (mismo nombre, diferente extensión)
            video_dir = os.path.dirname(video_filepath)
            video_name = os.path.splitext(os.path.basename(video_filepath))[0]
            thumbnail_path = os.path.join(video_dir, f"{video_name}{smart_ext}")
            
            # Guardar miniatura
            with open(thumbnail_path, 'wb') as f:
                f.write(image_data)
            
            print(f"INFO: Miniatura guardada: {thumbnail_path}")
            
        except Exception as e:
            print(f"ERROR al descargar miniatura para {job.job_id}: {e}")
            # No fallar el job completo si solo falla la miniatura

    def _rebuild_format_maps(self, info: dict) -> tuple[dict, dict]:
        """
        Re-crea los mapas de formatos a partir de los datos de análisis.
        """
        formats = info.get('formats', [])
        video_duration = info.get('duration', 0)
        
        job_video_formats = {}
        job_audio_formats = {}

        for f in formats:
            format_type = self._classify_format(f)
            
            size_mb_str = "Tamaño desc."
            filesize = f.get('filesize') or f.get('filesize_approx')
            if filesize: 
                size_mb_str = f"{filesize / (1024*1024):.2f} MB"
            else:
                bitrate = f.get('tbr') or f.get('vbr') or f.get('abr')
                if bitrate and video_duration:
                    estimated_bytes = (bitrate*1000/8)*video_duration
                    size_mb_str = f"Aprox. {estimated_bytes/(1024*1024):.2f} MB"
            
            vcodec_raw = f.get('vcodec')
            acodec_raw = f.get('acodec')
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
                if any(k in note.lower() for k in ['hdr', 'premium', 'dv', 'hlg', 'storyboard']):
                    note_tag = f" [{note}]"
                protocol = f.get('protocol', '')
                protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                label = f"{label_base}{label_codecs}){label_tag}{note_tag}{protocol_tag} - {size_mb_str}"

                tags = []
                compatibility_issues, _ = self._get_format_compatibility_issues(f)
                if not compatibility_issues: 
                    tags.append("✨")
                else: 
                    tags.append("⚠️")
                if tags: 
                    label += f" {' '.join(tags)}"
                
                job_video_formats[label] = {**f, 'is_combined': is_combined}

            elif format_type == 'AUDIO':
                abr = f.get('abr') or f.get('tbr')
                lang_code = f.get('language')
                lang_name = "Idioma Desconocido"
                if lang_code:
                    norm_code = lang_code.replace('_', '-').lower()
                    lang_name = self.main_app.LANG_CODE_MAP.get(norm_code, self.main_app.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code))
                
                lang_prefix = f"{lang_name} - " if lang_code else ""
                note = f.get('format_note') or ''
                drc_tag = " (DRC)" if 'DRC' in note else ""
                protocol = f.get('protocol', '')
                protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                label = f"{lang_prefix}{abr:.0f}kbps ({acodec}, {ext}){drc_tag}{protocol_tag}" if abr else f"{lang_prefix}Audio ({acodec}, {ext}){drc_tag}{protocol_tag}"
                
                if acodec in EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]: 
                    label += " ✨"
                else: 
                    label += " ⚠️"
                
                job_audio_formats[label] = f

        return job_video_formats, job_audio_formats

    def _resolve_batch_conflict(self, desired_filepath, policy):
        """
        Maneja conflictos de archivo basado en una política.
        """
        final_path = desired_filepath
        backup_path = None

        if not os.path.exists(final_path):
            return final_path, backup_path

        if policy == "Omitir":
            return None, None

        elif policy == "Sobrescribir":
            try:
                backup_path = final_path + ".bak"
                if os.path.exists(backup_path): 
                    os.remove(backup_path)
                os.rename(final_path, backup_path)
            except OSError as e:
                raise Exception(f"No se pudo respaldar el archivo original: {e}")
            return final_path, backup_path
        
        elif policy == "Renombrar":
            base, ext = os.path.splitext(final_path)
            counter = 1
            while True:
                new_path_candidate = f"{base} ({counter}){ext}"
                if not os.path.exists(new_path_candidate):
                    final_path = new_path_candidate
                    break
                counter += 1
            return final_path, None

    def _predict_final_extension(self, video_info, audio_info, mode):
        """
        Predice la extensión de archivo más probable.
        """
        if not video_info: 
            video_info = {}
        if not audio_info: 
            audio_info = {}

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

    def _classify_format(self, f):
        """
        Clasifica un formato de yt-dlp.
        """
        if f.get('height') or f.get('width'): 
            return 'VIDEO'
        format_id = (f.get('format_id') or '').lower()
        format_note = (f.get('format_note') or '').lower()
        if 'audio' in format_id or 'audio' in format_note: 
            return 'AUDIO'
        vcodec = f.get('vcodec')
        acodec = f.get('acodec')
        if (vcodec == 'none' or not vcodec) and (acodec and acodec != 'none'): 
            return 'AUDIO'
        if f.get('ext') in AUDIO_EXTENSIONS: 
            return 'AUDIO'
        if f.get('ext') in VIDEO_EXTENSIONS: 
            return 'VIDEO'
        if vcodec == 'none': 
            return 'AUDIO'
        return 'UNKNOWN'

    def _get_format_compatibility_issues(self, format_dict):
        """Comprueba compatibilidad."""
        if not format_dict: 
            return [], []
        issues = []
        vcodec = (format_dict.get('vcodec') or 'none').split('.')[0]
        acodec = (format_dict.get('acodec') or 'none').split('.')[0]
        ext = format_dict.get('ext') or 'none'
        if vcodec != 'none' and vcodec not in EDITOR_FRIENDLY_CRITERIA["compatible_vcodecs"]:
            issues.append(f"video ({vcodec})")
        if acodec != 'none' and acodec not in EDITOR_FRIENDLY_CRITERIA["compatible_acodecs"]:
            issues.append(f"audio ({acodec})")
        if vcodec != 'none' and ext not in EDITOR_FRIENDLY_CRITERIA["compatible_exts"]:
            issues.append(f"contenedor (.{ext})")
        return issues, []