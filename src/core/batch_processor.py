import threading
import time
from uuid import uuid4
import os
import yt_dlp
import shutil

import requests
from PIL import Image
from io import BytesIO

from src.core.downloader import download_media, apply_site_specific_rules, apply_yt_patch
from src.core.exceptions import UserCancelledError
from src.core.video_upscaler import VideoUpscaler
from main import UPSCALING_DIR

from src.core.constants import (
    EDITOR_FRIENDLY_CRITERIA, LANGUAGE_ORDER, DEFAULT_PRIORITY,
    VIDEO_EXTENSIONS, AUDIO_EXTENSIONS
)


def get_smart_thumbnail_extension(image_data):
    """
    Detecta el formato óptimo para guardar la miniatura:
    - PNG si tiene transparencia
    - JPG en otros casos (más compacto)
    """
    try:
        from PIL import Image
        import io
        
        img = Image.open(io.BytesIO(image_data))
        
        # Verificar transparencia
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            return '.png'
        
        # Por defecto JPG (más compacto)
        return '.jpg'
        
    except Exception as e:
        print(f"ERROR detectando formato de miniatura: {e}")
        return '.jpg'  # Fallback seguro

class Job:
    """
    Contiene la información y el estado de un único trabajo en la cola.
    """
    def __init__(self, config: dict, job_type: str = "DOWNLOAD"):
        self.job_id: str = str(uuid4()) 
        self.config: dict = config 
        self.analysis_data: dict | None = None
        self.status: str = "PENDING"
        self.progress_message: str = ""
        self.final_filepath: str | None = None
        self.total_items: int = 0
        self.job_type: str = job_type

class QueueManager:
    """
    Gestiona la cola de trabajos (Jobs) en un hilo de trabajo separado
    para no bloquear la interfaz de usuario.
    """
    def __init__(self, main_app, ui_callback):
        self.main_app = main_app
        self.ui_callback = ui_callback

        self.analysis_cache = {}
        
        self.jobs: list[Job] = []
        self.jobs_lock = threading.Lock()
        
        self.run_thread = None
        self.pause_event = threading.Event()
        self.pause_event.set() 
        self.stop_event = threading.Event()
        
        self.user_paused: bool = False
        self.jobs_completed: int = 0 
        
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
                    # --- INICIO DE MODIFICACIÓN: Lógica de enrutamiento ---
                    if job_to_run.job_type == "DOWNLOAD":
                        self._execute_download_job(job_to_run)
                    elif job_to_run.job_type == "LOCAL_RECODE":
                        self._execute_recode_job(job_to_run)
                    elif job_to_run.job_type == "PLAYLIST":  # <--- NUEVO CASO
                        self._execute_playlist_job(job_to_run)
                    else:
                        raise Exception(f"Tipo de trabajo desconocido: {job_to_run.job_type}")
                    # --- FIN DE MODIFICACIÓN ---

                except UserCancelledError as e:
                    job_to_run.status = "PENDING"
                    self.ui_callback(job_to_run.job_id, "PENDING", f"Pausado: {e}")
                
                except Exception as e:
                    print(f"ERROR: Falló el trabajo {job_to_run.job_id}: {e}")
                    job_to_run.status = "FAILED"
                    self.ui_callback(job_to_run.job_id, "FAILED", f"Error: {str(e)[:100]}")
                
                # --- INICIO DE MODIFICACIÓN (Progreso Global) ---
                # Este bloque se ejecuta SIEMPRE, ya sea que el job haya fallado,
                # se haya completado, o se haya omitido (dentro de _execute_job)
                if job_to_run.status not in ("PENDING", "RUNNING"):
                    with self.jobs_lock:
                        # Contar todos los trabajos que ya no están en la cola de espera
                        self.jobs_completed = sum(1 for j in self.jobs if j.status not in ("PENDING", "RUNNING"))
                        total_jobs = len(self.jobs)
                        
                    if total_jobs > 0:
                        progress_percent = self.jobs_completed / total_jobs
                        
                        # Mensaje de progreso
                        current_title = job_to_run.config.get('title', 'Ítem')
                        if len(current_title) > 40:
                            current_title = current_title[:37] + "..."
                        
                        progress_message = f"({self.jobs_completed}/{total_jobs}) Completado: {current_title}"
                        
                        if job_to_run.status == "FAILED":
                            progress_message = f"({self.jobs_completed}/{total_jobs}) Falló: {current_title}"
                        elif job_to_run.status == "SKIPPED":
                            progress_message = f"({self.jobs_completed}/{total_jobs}) Omitido: {current_title}"
                        
                        self.ui_callback("GLOBAL_PROGRESS", "UPDATE", progress_message, progress_percent)
                # --- FIN DE MODIFICACIÓN ---
            
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

        # ✅ CORRECCIÓN: Forzar actualización inmediata de la barra
        # Esto elimina el "100%" residual del análisis y pone la barra en 0% (o en el estado actual)
        with self.jobs_lock:
            total_jobs = len(self.jobs)
            # Recalcular completados reales al momento de iniciar
            current_completed = sum(1 for j in self.jobs if j.status not in ("PENDING", "RUNNING"))
            
            # Sincronizar el contador interno
            self.jobs_completed = current_completed
        
        if total_jobs > 0:
            progress_percent = current_completed / total_jobs
            msg = f"Iniciando... ({current_completed}/{total_jobs})"
            self.ui_callback("GLOBAL_PROGRESS", "UPDATE", msg, progress_percent)
        else:
            self.ui_callback("GLOBAL_PROGRESS", "RESET", "Esperando...", 0.0)

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

    def reset_progress(self):
        """Resetea el contador de progreso global."""
        print("INFO: Reseteando el progreso global de la cola.")
        self.jobs_completed = 0
        self.ui_callback("GLOBAL_PROGRESS", "RESET", "Esperando para iniciar la cola...", 0.0)

    def _execute_playlist_job(self, job: Job):
        """
        Procesa una playlist completa. Maneja lógica de 'Solo Miniaturas' 
        y descarga de miniaturas en PNG/Alta Calidad si se requiere.
        """
        selected_indices = job.config.get('selected_indices', [])
        total_videos = len(selected_indices)
        entries = job.analysis_data.get('entries', [])
        
        # Configuración global
        mode = job.config.get('playlist_mode', 'Video+Audio')
        quality_setting = job.config.get('playlist_quality', 'Mejor Calidad (Auto)')
        
        # Verificar modo de miniaturas global (Radial Checks)
        batch_tab = self.main_app.batch_tab
        thumbnail_mode = batch_tab.thumbnail_mode_var.get() # 'normal', 'with_thumbnail', 'only_thumbnail'
        conflict_policy = batch_tab.conflict_policy_menu.get() if hasattr(batch_tab, 'conflict_policy_menu') else "Renombrar"
        
        # Directorio base y subcarpeta
        base_output_dir = batch_tab.output_path_entry.get()
        # Verificar si hay subcarpeta de lote activa
        if hasattr(self, 'subfolder_path') and self.subfolder_path:
            base_output_dir = self.subfolder_path

        # Crear carpeta de la playlist
        raw_title = job.config.get('title', 'Playlist')
        playlist_title = self.main_app.single_tab.sanitize_filename(raw_title)
        playlist_dir = os.path.join(base_output_dir, playlist_title)
        os.makedirs(playlist_dir, exist_ok=True)

        print(f"INFO: Iniciando playlist '{playlist_title}' ({total_videos} items). Modo Miniatura: {thumbnail_mode}")
        self.ui_callback(job.job_id, "RUNNING", f"Iniciando playlist ({total_videos} items)...")

        # --- CASO ESPECIAL: SOLO MINIATURAS ---
        if thumbnail_mode == "only_thumbnail":
            # Crear carpeta específica de thumbnails dentro de la playlist (opcional, o usar la raíz de la playlist)
            # El usuario pidió "descargue las miniaturas de la playlist", lo pondremos en la carpeta de la playlist.
            
            for i, index in enumerate(selected_indices):
                if self.pause_event.is_set(): return 
                if self.stop_event.is_set(): return

                if index >= len(entries): continue
                entry = entries[index]
                video_title = entry.get('title', f"Video {index}")
                
                # Calcular progreso
                percent = ((i + 1) / total_videos) * 100
                msg = f"[{i+1}/{total_videos}] Miniatura: {video_title[:20]}..."
                self.ui_callback(job.job_id, "RUNNING", msg, percent)
                
                # Descargar SOLO la miniatura en PNG
                try:
                    # 1. Capturamos la ruta
                    thumb_path = self._download_best_thumb_png(entry, playlist_dir, video_title)
                    
                    # 2. Verificar si Auto-envío está activo
                    if thumb_path and self.main_app.batch_tab.auto_send_to_it_checkbox.get() == 1:
                        # 3. Enviar a Herramientas de Imagen (Usando after para seguridad de hilos)
                        self.main_app.after(0, self.main_app.image_tab._process_imported_files, [thumb_path])
                        
                except Exception as e:
                    print(f"ERROR miniatura {i}: {e}")
            
            job.status = "COMPLETED"
            job.final_filepath = playlist_dir
            self.ui_callback(job.job_id, "COMPLETED", "Miniaturas descargadas ✅", 100.0)
            return

        # --- CASO NORMAL (VIDEO/AUDIO) ---
        for i, index in enumerate(selected_indices):
            if self.pause_event.is_set():
                self.ui_callback(job.job_id, "PENDING", f"Pausado en video {i+1}/{total_videos}")
                return 
            if self.stop_event.is_set(): return
            
            if index >= len(entries): continue
            entry = entries[index]
            
            video_url = entry.get('url')
            video_title = entry.get('title', f"Video {index}")
            
            # Callback de progreso interno
            def playlist_progress_callback(vid_percent, vid_message):
                chunk_size = 100 / total_videos
                base_progress = i * chunk_size
                current_contribution = (vid_percent / 100) * chunk_size
                global_percent = base_progress + current_contribution
                
                short_title = (video_title[:20] + '..') if len(video_title) > 20 else video_title
                status_msg = f"[{i+1}/{total_videos}] {short_title}: {vid_percent:.0f}%"
                self.ui_callback(job.job_id, "RUNNING", status_msg, global_percent)

            # Opciones de descarga
            child_options = {
                'url': video_url,
                'title': video_title,
                'output_path': playlist_dir,
                'mode': mode,
                'cookie_mode': self.main_app.cookies_mode_saved,
            }
            
            self._apply_playlist_quality(child_options, mode, quality_setting)
            
            # Inicializar variables para importación
            thumb_path = None
            final_path_for_import = None

            try:
                # 1. Descargar Video/Audio
                downloaded_path = self._download_single_video_in_playlist(child_options, playlist_progress_callback, job.job_id)
                
                # ✅ ROBUSTEZ: Corregir ruta si cambió la extensión (ej: Solo Audio)
                if downloaded_path and not os.path.exists(downloaded_path):
                    base_path_no_ext = os.path.splitext(downloaded_path)[0]
                    for ext in ['.m4a', '.mp3', '.mp4', '.webm', '.opus', '.wav']:
                        candidate = f"{base_path_no_ext}{ext}"
                        if os.path.exists(candidate):
                            downloaded_path = candidate
                            break

                final_path_for_import = downloaded_path # Por defecto, es el descargado
                
                # ✅ LÓGICA DE HERENCIA DE RECODIFICACIÓN
                if job.config.get('recode_enabled', False) and downloaded_path and os.path.exists(downloaded_path):
                    
                    preset_name = job.config.get('recode_preset_name')
                    preset_params = self._find_preset_params(preset_name)
                    
                    if preset_params:
                        output_dir = os.path.dirname(downloaded_path)
                        base_name = os.path.splitext(os.path.basename(downloaded_path))[0]
                        
                        # ✅ CORRECCIÓN: Inyectar el modo de la playlist en las opciones
                        recode_options = preset_params.copy()
                        recode_options['mode'] = mode 

                        # --- INTERCEPCIÓN DE EXTRAS ---
                        is_extraction = preset_params.get('extract_frames_enabled', False)
                        is_upscaling = preset_params.get('upscale_video_enabled', False)
                        processed_by_extra = False

                        # Solo aplicar extras si NO es modo Solo Audio
                        if mode != "Solo Audio" and (is_extraction or is_upscaling):
                            if is_extraction:
                                self.ui_callback(job.job_id, "RUNNING", f"[{i+1}/{total_videos}] Fotogramas: {video_title}...")
                                folder_name = f"{base_name}_frames"
                                final_output_directory = os.path.join(output_dir, folder_name)
                                
                                extraction_options = {
                                    'input_file': downloaded_path,
                                    'output_folder': final_output_directory,
                                    'image_format': preset_params.get('extract_format', 'png'),
                                    'fps': preset_params.get('extract_fps'),
                                    'jpg_quality': preset_params.get('extract_jpg_quality', '2'),
                                    'duration': self._get_job_media_duration(job, downloaded_path),
                                    'pre_params': []
                                }
                                
                                output_folder = self.main_app.ffmpeg_processor.execute_video_to_images(
                                    extraction_options,
                                    lambda p, m: self.ui_callback(job.job_id, "RUNNING", f"[{i+1}/{total_videos}] Extraer {p:.1f}%"),
                                    self.pause_event
                                )
                                
                                if not preset_params.get('keep_original_file', True):
                                    try: os.remove(downloaded_path)
                                    except OSError: pass
                                
                                final_path_for_import = output_folder
                                processed_by_extra = True

                            elif is_upscaling:
                                self.ui_callback(job.job_id, "RUNNING", f"[{i+1}/{total_videos}] Reescalando: {video_title}...")
                                scale_str = str(preset_params.get("upscale_scale", "2")).replace("x", "")
                                out_stem = f"{base_name}_upscaled_x{scale_str}"
                                desired_out_path = os.path.join(output_dir, out_stem + ".mp4")
                                
                                # Resolución de conflictos
                                out_path, _ = self._resolve_batch_conflict(desired_out_path, conflict_policy)
                                
                                if out_path:
                                    ffmpeg_dir = os.path.dirname(self.main_app.ffmpeg_processor.ffmpeg_path)
                                    upscaler = VideoUpscaler(
                                        ffmpeg_dir=ffmpeg_dir,
                                        upscaling_dir=UPSCALING_DIR,
                                        cancellation_event=self.pause_event,
                                        progress_callback=lambda p, m: self.ui_callback(job.job_id, "RUNNING", f"[{i+1}/{total_videos}] {m} ({p:.1f}%)" if isinstance(p, float) and p >= 0 else f"[{i+1}/{total_videos}] {m}")
                                    )
                                    final_path = upscaler.upscale_video(downloaded_path, out_path, preset_params)
                                    
                                    if not preset_params.get('keep_originals', True):
                                        try: os.remove(downloaded_path)
                                        except OSError: pass
                                        
                                    final_path_for_import = final_path
                                    processed_by_extra = True
                                else:
                                    print(f"INFO: Item {i+1} omitido (upscale ya existe).")
                                    # Si se omite el upscale, final_path_for_import sigue siendo el descargado
                        
                        # Si no se procesó por extra, ejecutar recodificación normal
                        if not processed_by_extra:
                            self.ui_callback(job.job_id, "RUNNING", f"[{i+1}/{total_videos}] Recodificando: {video_title}...")
                            recoded_base_name = f"{base_name}_recoded"
                            
                            recoded_path = self._execute_recode_master(
                                job=job,
                                input_file=downloaded_path,
                                output_dir=output_dir,
                                base_filename=recoded_base_name,
                                recode_options=recode_options
                            )
                            final_path_for_import = recoded_path
                            
                            if not job.config.get('recode_keep_original', True):
                                try: os.remove(downloaded_path)
                                except: pass
                
                # 3. Descargar Miniatura (Si el modo es "con video/audio" o "manual" activado)
                if thumbnail_mode == "with_thumbnail":
                    thumb_path = self._download_best_thumb_png(entry, playlist_dir, video_title)
                    
                    # ✅ Lógica de Auto-Envío para ítems de Playlist
                    if thumb_path and self.main_app.batch_tab.auto_send_to_it_checkbox.get() == 1:
                        self.main_app.after(0, self.main_app.image_tab._process_imported_files, [thumb_path])
                    
                # 4. ✅ LÓGICA DE IMPORTACIÓN AUTOMÁTICA A ADOBE (NUEVO)
                if self.main_app.batch_tab.auto_import_checkbox.get() and final_path_for_import:
                    active_target = self.main_app.ACTIVE_TARGET_SID_accessor()
                    
                    if active_target:
                        # Determinar el nombre del Bin (Carpeta en Premiere)
                        # Usamos el nombre de la playlist (playlist_title) que ya calculamos arriba
                        target_bin_name = playlist_title 
                        
                        # Si hay una subcarpeta de lote global, podemos combinarla o usarla
                        # Por simplicidad, usaremos el título de la playlist para agrupar los ítems
                        
                        file_package = {
                            "video": final_path_for_import.replace('\\', '/'),
                            "thumbnail": thumb_path.replace('\\', '/') if thumb_path else None,
                            "subtitle": None, # (Podrías añadir lógica de subtítulos aquí en el futuro)
                            "targetBin": target_bin_name
                        }
                        
                        print(f"INFO: [Playlist Item] Enviando a Adobe: {os.path.basename(final_path_for_import)}")
                        self.main_app.socketio.emit('new_file', {'filePackage': file_package}, to=active_target)

            except Exception as e:
                print(f"ERROR procesando item {i+1} ({video_title}): {e}")
                continue

        job.status = "COMPLETED"
        job.final_filepath = playlist_dir
        self.ui_callback(job.job_id, "COMPLETED", "Playlist completada ✅", 100.0)

    def _apply_playlist_quality(self, options, mode, quality_setting):
        """Traduce la selección del menú a selectores de formato de yt-dlp."""
        
        # Selectores base
        selector = "best" 
        
        if mode == "Video+Audio":
            if "Mejor Compatible" in quality_setting:
                # Buscar H.264 (avc1) y AAC (mp4a) en contenedor MP4
                # Fallback a best si no encuentra MP4 exacto
                selector = "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            elif "4K" in quality_setting:
                selector = "bestvideo[height=2160]+bestaudio/best[height=2160]/best"
            elif "1080p" in quality_setting:
                selector = "bestvideo[height=1080]+bestaudio/best[height=1080]/best"
            elif "720p" in quality_setting:
                selector = "bestvideo[height=720]+bestaudio/best[height=720]/best"
            elif "480p" in quality_setting:
                selector = "bestvideo[height=480]+bestaudio/best[height=480]/best"
            else:
                # Mejor Calidad (Auto)
                selector = "bv+ba/b"

        elif mode == "Solo Audio":
            if "Mejor Compatible" in quality_setting:
                # Preferir M4A (AAC) o MP3 directo.
                # Si no existe, descargará el mejor y luego convertiremos (post-proceso)
                selector = "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio"
                options['recode_audio_enabled'] = True # Forzar recodificación si es necesario
                options['recode_audio_codec_name'] = "MP3 (libmp3lame)" # Estandarizar a MP3
            else:
                selector = "bestaudio/best"
        
        options['format_selector'] = selector

    def _download_single_video_in_playlist(self, options, progress_callback, job_id):
        """
        Versión mini de _execute_download_job para uso interno en playlists.
        """
        output_dir = options['output_path']
        title = self.main_app.single_tab.sanitize_filename(options['title'])
        
        # Template de salida
        output_template = os.path.join(output_dir, f"{title}.%(ext)s")
        
        ydl_opts = {
            'outtmpl': output_template,
            'format': options.get('format_selector', 'best'),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'ffmpeg_location': self.main_app.ffmpeg_processor.ffmpeg_path
        }
        
        # Cookies (Importante heredar esto)
        cookie_mode = self.main_app.cookies_mode_saved
        using_cookies = False

        if cookie_mode == "Archivo Manual..." and self.main_app.cookies_path:
            ydl_opts['cookiefile'] = self.main_app.cookies_path
            using_cookies = True
        elif cookie_mode != "No usar":
            browser = self.main_app.selected_browser_saved
            profile = self.main_app.browser_profile_saved
            if profile:
                ydl_opts['cookiesfrombrowser'] = (f"{browser}:{profile}",)
                using_cookies = True
            else:
                ydl_opts['cookiesfrombrowser'] = (browser,)
                using_cookies = True

        # Aplicar parche SOLO con cookies
        if using_cookies:
            ydl_opts = apply_yt_patch(ydl_opts)

        # Hook de progreso
        def hook(d):
            if self.pause_event.is_set():
                # Truco para pausar yt-dlp: lanzar error
                raise UserCancelledError("Pausado")
            
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    pct = (downloaded / total) * 100
                    progress_callback(pct, f"Descargando: {title}")
            elif d['status'] == 'finished':
                progress_callback(100, f"Procesando: {title}")

        ydl_opts['progress_hooks'] = [hook]
        
        # Ejecutar descarga
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # ✅ CAMBIO: Capturar info para obtener el nombre real del archivo
                info = ydl.extract_info(options['url'], download=True)
                
                # Obtener la ruta final del archivo descargado
                filename = ydl.prepare_filename(info)
                return filename # <--- AÑADIR ESTE RETURN
                
        except UserCancelledError:
            raise # Re-lanzar para manejar la pausa arriba
        except Exception as e:
            print(f"Error interno en video playlist: {e}")
            raise e

    def _execute_download_job(self, job: Job):
        """
        Ejecuta un único trabajo de DESCARGA (desde URL).
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
                    'noprogress': True,
                }

                using_cookies = False               
                cookie_mode = self.main_app.cookies_mode_saved

                if cookie_mode == "Archivo Manual..." and self.main_app.cookies_path:
                    ydl_opts['cookiefile'] = self.main_app.cookies_path
                    using_cookies = True
                elif cookie_mode != "No usar":
                    browser_arg = self.main_app.selected_browser_saved
                    profile = self.main_app.browser_profile_saved
                    if profile:
                        browser_arg += f":{profile}"
                    ydl_opts['cookiesfrombrowser'] = (browser_arg,)
                    using_cookies = True
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    job.analysis_data = ydl.extract_info(url, download=False)

                # Aplicar parche SOLO con cookies
                if using_cookies:
                    ydl_opts = apply_yt_patch(ydl_opts)
                
                # ✅ INYECCIÓN DEL PARCHE
                if job.analysis_data:
                    job.analysis_data = apply_site_specific_rules(job.analysis_data)

                # 🆕 CRÍTICO: Normalizar si falta información
                job.analysis_data = self._normalize_info_dict(job.analysis_data)
                    
            except Exception as e:
                raise Exception(f"No se pudo analizar el video: {e}")

        # 🆕 Verificación adicional
        if not job.analysis_data or 'formats' not in job.analysis_data:
            raise Exception("No se pudo extraer información de formatos del video")
        
        extractor_key = job.analysis_data.get('extractor_key', '').lower()

        # TWITCH: Deshabilitar subtítulos (no funciona bien)
        if 'twitch' in extractor_key:
            print("DEBUG: Twitch detectado, deshabilitando subtítulos")
            job.analysis_data['subtitles'] = {}
            job.analysis_data['automatic_captions'] = {}

        # TWITTER/X: Usar mejor opción disponible
        if any(x in extractor_key for x in ['twitter', 'x.com']):
            print("DEBUG: Twitter/X detectado, usando estrategia especial")
            # Ya se maneja con fallback

        # SOUNDCLOUD: Audio directo
        if 'soundcloud' in extractor_key:
            print("DEBUG: SoundCloud detectado (audio directo)")
            mode = "Solo Audio"  # Forzar modo audio

        # IMGUR/GIF: Sin audio
        if any(x in extractor_key for x in ['imgur', 'gfycat', 'giphy']):
            print("DEBUG: Sitio de GIF/video detectado")
            job.analysis_data['subtitles'] = {}
            job.analysis_data['automatic_captions'] = {}

        # Encontrar los format_id
        (job_video_formats, job_audio_formats) = self._rebuild_format_maps(job.analysis_data)

        if mode == "Solo Audio" and not job_audio_formats:
            print(f"DEBUG: Job {job.job_id} omitido (modo 'Solo Audio' pero no hay audio).")
            job.status = "NO_AUDIO" # Asignar nuevo estado
            self.ui_callback(job.job_id, "NO_AUDIO", "Este ítem no tiene audio.")
            return # Salir de la ejecución del job

        # --- INICIO DE LA CORRECCIÓN 1 ---
        # Lógica de fallback mejorada para encontrar el formato "✨"
        
        if v_label == "-" or v_label not in job_video_formats:
            v_opts = list(job_video_formats.keys())
            if v_opts:
                default_video_selection = v_opts[0] # Fallback por si no hay "✨"
                for option in v_opts:
                    if "✨" in option:
                        default_video_selection = option
                        break
                v_label = default_video_selection
            else:
                v_label = "-"

        if a_label == "-" or a_label not in job_audio_formats:
            a_opts = list(job_audio_formats.keys())
            if a_opts:
                default_audio_selection = a_opts[0] # Fallback
                for option in a_opts:
                    if "✨" in option:
                        default_audio_selection = option
                        break
                a_label = default_audio_selection
            else:
                a_label = "-"

        v_format_dict = job_video_formats.get(v_label)
        a_format_dict = job_audio_formats.get(a_label)

        # 🆕 Prioridad 1: IDs guardados explícitamente
        v_id = job.config.get('resolved_video_format_id')
        a_id = job.config.get('resolved_audio_format_id')

        # 🆕 Fallback: Extraer de los formatos si no hay IDs guardados
        if not v_id:
            v_id = v_format_dict.get('format_id') if v_format_dict else None
        if not a_id:
            a_id = a_format_dict.get('format_id') if a_format_dict else None

        print(f"DEBUG: Descargando con v_id={v_id}, a_id={a_id}")

        # 🔧 LÓGICA DE SELECTOR (Multiidioma Fix)
        # Eliminada la dependencia directa de batch_tab.combined_audio_map (inseguro para hilos)
        # v_id y a_id ya vienen resueltos desde el hilo de la UI.
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
        
        # 🆕 FALLBACK INTELIGENTE: Si no hay selector precisó
        if not precise_selector:
            self.ui_callback(job.job_id, "RUNNING", "Selector no especificado, usando fallback...")
            
            # Intentar estrategia 1: best
            if mode == "Video+Audio":
                precise_selector = "bv+ba/b"  # best video + best audio
            elif mode == "Solo Audio":
                precise_selector = "ba"  # best audio
            else:
                precise_selector = "best"  # anything
            
            print(f"DEBUG: Fallback selector: {precise_selector}")

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
            
        # 1. Extraer el nombre base (sin extensión) del archivo que resolvimos
        title_with_conflict_resolution = os.path.splitext(os.path.basename(final_filepath))[0]
        
        # 2. Crear un template de salida para que yt-dlp elija la extensión
        output_template = os.path.join(output_dir, f"{title_with_conflict_resolution}.%(ext)s")

        # Preparar Opciones de yt-dlp
        ydl_opts = {
            'outtmpl': output_template,
            'overwrites': True,
            'ffmpeg_location': self.main_app.ffmpeg_processor.ffmpeg_path,
            'format': precise_selector,
            'restrictfilenames': True,
            'noprogress': True,
        }

        # ✅ CORRECCIÓN DINÁMICA: Extraer audio respetando el formato original
        if mode == "Solo Audio":
            # 1. Determinar el formato de destino basado en el códec original
            target_ext = 'mp3' # Fallback por compatibilidad
            
            if a_format_dict:
                acodec = a_format_dict.get('acodec', '').lower()
                
                # Mapeo de códecs a extensiones para extracción sin pérdidas (Copy)
                if 'aac' in acodec or 'mp4a' in acodec:
                    target_ext = 'm4a'
                elif 'opus' in acodec:
                    target_ext = 'opus'
                elif 'vorbis' in acodec:
                    target_ext = 'ogg'
                elif 'flac' in acodec:
                    target_ext = 'flac'
                elif 'mp3' in acodec:
                    target_ext = 'mp3'
                # Si es unknown, se queda en mp3 por seguridad
            
            print(f"DEBUG: Modo Solo Audio. Codec origen: {acodec if a_format_dict else '?'}. Extrayendo a: {target_ext}")
            
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': target_ext,
                'preferredquality': '192',
            }]
        
        playlist_index = job.config.get('playlist_index')
        if playlist_index is not None:
            # Le dice a yt-dlp que SOLO descargue este ítem
            ydl_opts['playlist_items'] = str(playlist_index)
            print(f"DEBUG: Configurando --playlist-items para {playlist_index}")
        else:
            # Esto no es de una playlist, así que forzamos 'noplaylist'
            ydl_opts['noplaylist'] = True
            print(f"DEBUG: Configurando --noplaylist (video único)")

        if speed_limit:
            try: 
                ydl_opts['ratelimit'] = float(speed_limit) * 1024 * 1024
            except ValueError: 
                pass

        using_cookies = False
        cookie_mode = self.main_app.cookies_mode_saved
        cookie_flag = "" # Para el log de CLI
        if cookie_mode == "Archivo Manual..." and self.main_app.cookies_path:
            ydl_opts['cookiefile'] = self.main_app.cookies_path
            cookie_flag = f' --cookies "{self.main_app.cookies_path}"'
            using_cookies = True
        elif cookie_mode != "No usar":
            browser_arg = self.main_app.selected_browser_saved
            profile = self.main_app.browser_profile_saved
            if profile: 
                browser_arg += f":{profile}"
            ydl_opts['cookiesfrombrowser'] = (browser_arg,)
            cookie_flag = f' --cookies-from-browser {browser_arg}'
            using_cookies = True

        # Aplicar parche SOLO con cookies
        if using_cookies:
            ydl_opts = apply_yt_patch(ydl_opts)

        # 🔧 GENERACIÓN DE COMANDO CLI EQUIVALENTE
        cli_command = f'yt-dlp -f "{precise_selector}"{cookie_flag} "{url}" -o "{output_template}"'
        
        print(f"\n{'='*80}")
        print(f"🔍 [LOTE] COMANDO EQUIVALENTE DE CLI:")
        print(f"{cli_command}")
        print(f"{'='*80}\n")

        # Definir el hook de progreso
        def download_hook(d):
            if self.pause_event.is_set() or self.stop_event.is_set():
                 raise UserCancelledError("Proceso pausado por el usuario.")
            
            # ✅ NUEVO: Detectar si el usuario eliminó el trabajo (X en la GUI)
            if job.status == "FAILED" or job.status == "CANCELLED":
                 print(f"DEBUG: Trabajo {job.job_id} fue eliminado, abortando descarga.")
                 raise UserCancelledError("Trabajo cancelado/eliminado por el usuario.")

            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    downloaded = d.get('downloaded_bytes', 0)
                    percentage = (downloaded / total) * 100
                    speed = d.get('speed')

                    if speed:
                        speed_mb = speed / 1024 / 1024
                        if speed_mb >= 1.0:
                            speed_str = f"{speed_mb:.1f} MB/s"
                        else:
                            speed_kb = speed / 1024
                            speed_str = f"{speed_kb:.0f} KB/s" # KB/s sin decimales
                    else:
                        speed_str = "N/A"
                    # --- FIN DE MODIFICACIÓN ---

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
            
            thumbnail_path = None # Inicializar
            
            # Descargar miniatura si está habilitado
            if should_download_thumbnail:
                thumbnail_path = self._download_thumbnail_alongside_video(job, final_filepath)

            # ✅ CORRECCIÓN: Actualizar ruta final si cambió la extensión (Modo Solo Audio)
            # Si yt-dlp convirtió el video a audio y borró el original, 'final_filepath' apunta a la nada.
            if mode == "Solo Audio" and not os.path.exists(final_filepath):
                # Obtener el nombre base sin extensión
                base_path_no_ext = os.path.splitext(final_filepath)[0]
                
                # 1. Intentar con la extensión objetivo calculada antes (target_ext)
                if 'target_ext' in locals():
                    candidate = f"{base_path_no_ext}.{target_ext}"
                    if os.path.exists(candidate):
                        final_filepath = candidate
                        print(f"DEBUG: Ruta corregida (Audio): {final_filepath}")
                
                # 2. Si sigue sin existir, buscar cualquier extensión de audio común
                if not os.path.exists(final_filepath):
                    for audio_ext in ['.m4a', '.mp3', '.opus', '.wav', '.flac', '.ogg']:
                        candidate = f"{base_path_no_ext}{audio_ext}"
                        if os.path.exists(candidate):
                            final_filepath = candidate
                            print(f"DEBUG: Ruta corregida por búsqueda (Audio): {final_filepath}")
                            break

            # --- INICIO DE LA LÓGICA DE RECODIFICACIÓN ---
            
            if job.config.get('recode_enabled', False):
                self.ui_callback(job.job_id, "RUNNING", "Recodificación en cola...")
                
                preset_name = job.config.get('recode_preset_name')
                if not preset_name or preset_name.startswith('-'):
                    raise Exception("Preset de recodificación no válido seleccionado.")
                
                preset_params = self._find_preset_params(preset_name)
                if not preset_params:
                    raise Exception(f"No se encontraron parámetros para el preset '{preset_name}'.")
                
                # Obtener el directorio y nombre base del archivo descargado
                output_dir = os.path.dirname(final_filepath)
                base_name = os.path.splitext(os.path.basename(final_filepath))[0]

                # --- INTERCEPCIÓN DE EXTRAS ---
                is_extraction = preset_params.get('extract_frames_enabled', False)
                is_upscaling = preset_params.get('upscale_video_enabled', False)
                
                if mode != "Solo Audio" and (is_extraction or is_upscaling):
                    if is_extraction:
                        self.ui_callback(job.job_id, "RUNNING", "Extrayendo fotogramas...")
                        folder_name = f"{base_name}_frames"
                        final_output_directory = os.path.join(output_dir, folder_name)
                        
                        extraction_options = {
                            'input_file': final_filepath,
                            'output_folder': final_output_directory,
                            'image_format': preset_params.get('extract_format', 'png'),
                            'fps': preset_params.get('extract_fps'),
                            'jpg_quality': preset_params.get('extract_jpg_quality', '2'),
                            'duration': self._get_job_media_duration(job, final_filepath),
                            'pre_params': []
                        }
                        
                        # Usa execute_video_to_images que ya está disponible en ffmpeg_processor
                        output_folder = self.main_app.ffmpeg_processor.execute_video_to_images(
                            extraction_options,
                            lambda p, m: self.ui_callback(job.job_id, "RUNNING", f"Extrayendo... {p:.1f}%"),
                            self.pause_event
                        )
                        
                        if not preset_params.get('keep_original_file', True):
                            try:
                                os.remove(final_filepath)
                            except OSError:
                                pass
                        
                        job.status = "COMPLETED"
                        job.final_filepath = output_folder
                        self.ui_callback(job.job_id, "COMPLETED", f"Completado (Fotogramas): {folder_name}")
                        return
                    
                    elif is_upscaling:
                        self.ui_callback(job.job_id, "RUNNING", "Reescalando video (IA)...")
                        scale_str = str(preset_params.get("upscale_scale", "2")).replace("x", "")
                        out_stem = f"{base_name}_upscaled_x{scale_str}"
                        desired_out_path = os.path.join(output_dir, out_stem + ".mp4")
                        
                        # Resolución de conflictos
                        out_path, _ = self._resolve_batch_conflict(desired_out_path, conflict_policy)
                        if out_path is None:
                            job.status = "SKIPPED"
                            self.ui_callback(job.job_id, "SKIPPED", "Omitido: El archivo reescalado ya existe")
                            return
                        
                        ffmpeg_dir = os.path.dirname(self.main_app.ffmpeg_processor.ffmpeg_path)
                        
                        upscaler = VideoUpscaler(
                            ffmpeg_dir=ffmpeg_dir,
                            upscaling_dir=UPSCALING_DIR,
                            cancellation_event=self.pause_event,
                            progress_callback=lambda p, m: self.ui_callback(job.job_id, "RUNNING", f"({p:.1f}%) {m}" if isinstance(p, float) and p >= 0 else f"{m}")
                        )
                        
                        final_path = upscaler.upscale_video(final_filepath, out_path, preset_params)
                        
                        if not preset_params.get('keep_originals', True):
                            try: os.remove(final_filepath)
                            except OSError: pass
                            
                        job.status = "COMPLETED"
                        job.final_filepath = final_path
                        self.ui_callback(job.job_id, "COMPLETED", f"Completado (Upscaled): {os.path.basename(final_path)}")
                        return
                # --- FIN INTERCEPCIÓN DE EXTRAS ---

                recoded_base_name = f"{base_name}_recoded"

                # Ejecutar la recodificación
                recoded_filepath = self._execute_recode_master(
                    job=job,
                    input_file=final_filepath,
                    output_dir=output_dir,
                    base_filename=recoded_base_name,
                    recode_options=preset_params
                )
                
                # Manejar el archivo original
                if not job.config.get('recode_keep_original', True):
                    try:
                        os.remove(final_filepath)
                        print(f"DEBUG: Archivo original (sin recodificar) eliminado: {final_filepath}")
                        
                        # Si se borró el original, renombrar la miniatura si existe
                        if thumbnail_path and os.path.exists(thumbnail_path):
                            thumb_dir, thumb_name = os.path.split(thumbnail_path)
                            if thumb_name.startswith(base_name):
                                new_thumb_name = thumb_name.replace(base_name, recoded_base_name, 1)
                                new_thumbnail_path = os.path.join(thumb_dir, new_thumb_name)
                                os.rename(thumbnail_path, new_thumbnail_path)
                                thumbnail_path = new_thumbnail_path
                                print(f"DEBUG: Miniatura renombrada a: {new_thumbnail_path}")

                    except OSError as e:
                        print(f"ADVERTENCIA: No se pudo eliminar el archivo original: {e}")
                
                # El archivo final ahora es el recodificado
                final_filepath = recoded_filepath
            
            # --- FIN DE LA LÓGICA DE RECODIFICACIÓN ---

            job.status = "COMPLETED"
            job.final_filepath = final_filepath # ✅ Ahora apunta al archivo real (.m4a/.mp3)
            self.ui_callback(job.job_id, "COMPLETED", f"Completado: {os.path.basename(final_filepath)}")

            # --- LÓGICA DE IMPORTACIÓN AUTOMÁTICA ---
            
            # 1. Verificar si el usuario quiere importar
            batch_tab = self.main_app.batch_tab
            # (Usamos tu nuevo texto "Import Pr/Ae" para encontrar el checkbox)
            if batch_tab and batch_tab.auto_import_checkbox.get():
                
                # 2. Verificar si hay una extensión de Adobe conectada
                active_target = self.main_app.ACTIVE_TARGET_SID_accessor()
                if active_target:
                    
                    # 3. Determinar la papelera (bin) de destino
                    target_bin_name = None
                    if hasattr(self, 'subfolder_path') and self.subfolder_path:
                        # self.subfolder_path es la RUTA COMPLETA (ej: C:/.../DowP List 01)
                        # Necesitamos solo el nombre final.
                        try:
                            target_bin_name = os.path.basename(os.path.normpath(self.subfolder_path))
                        except Exception:
                            target_bin_name = None # Fallback
                    
                    # 4. Armar el paquete de archivos
                    file_package = {
                        "video": job.final_filepath.replace('\\', '/'),
                        "thumbnail": thumbnail_path.replace('\\', '/') if thumbnail_path else None,
                        "subtitle": None,
                        "targetBin": target_bin_name # <-- AÑADIDO
                    }
                    
                    print(f"INFO: [Lote] Enviando paquete a CEP: {file_package}")
                    
                    # 5. Enviar el paquete por el socket
                    self.main_app.socketio.emit('new_file', {'filePackage': file_package}, to=active_target)
            
        except UserCancelledError as e:
            # Limpiar temporales si el usuario canceló
            if 'final_filepath' in locals() and final_filepath:
                output_dir = os.path.dirname(final_filepath)
                base_title = os.path.splitext(os.path.basename(final_filepath))[0]
                import glob
                patterns = [
                    f"{base_title}*.part", f"{base_title}*.f[0-9]*", f"{base_title}*.ytdl",
                    f"{base_title}*.temp", f"*.f[0-9]*.part", f"{base_title}*.temp.*", f"{base_title}*.part-*", f".{base_title}*"
                ]
                for p in patterns:
                    for f in glob.glob(os.path.join(output_dir, p)):
                        try:
                            os.remove(f)
                            print(f"DEBUG: Eliminado temp (Lote): {f}")
                        except Exception:
                            pass
            
            # Restaurar backup (.bak) si existía
            if 'backup_path' in locals() and backup_path and os.path.exists(backup_path):
                if 'final_filepath' in locals() and os.path.exists(final_filepath): 
                    os.remove(final_filepath)
                os.rename(backup_path, final_filepath)
                
            raise e
            
        except Exception as e:
            # Si falló, restaurar el backup si existía
            if backup_path and os.path.exists(backup_path):
                if os.path.exists(final_filepath): 
                    os.remove(final_filepath)
                os.rename(backup_path, final_filepath)
            raise e
        
    def _execute_recode_job(self, job: Job):
        """
        Ejecuta un único trabajo de RECODIFICACIÓN LOCAL (desde archivo).
        """
        # (Necesitaremos 'os' y 'shutil' para mover la miniatura)
        import os
        import shutil

        final_filepath = None
        try:
            self.ui_callback(job.job_id, "RUNNING", "Iniciando recodificación local...")
            
            # 1. Verificar si la recodificación está activada
            if not job.config.get('recode_enabled', False):
                job.status = "SKIPPED"
                self.ui_callback(job.job_id, "SKIPPED", "Omitido: La recodificación no está activada.")
                return

            # 2. Validar el Preset
            preset_name = job.config.get('recode_preset_name')
            if not preset_name or preset_name.startswith('-'):
                raise Exception("Preset de recodificación no válido seleccionado.")
                
            preset_params = self._find_preset_params(preset_name)
            if not preset_params:
                raise Exception(f"No se encontraron parámetros para el preset '{preset_name}'.")

            # 3. Validar el archivo de entrada
            input_file = job.config.get('local_file_path')
            if not input_file or not os.path.exists(input_file):
                raise Exception(f"No se encontró el archivo local: {input_file}")

            # 4. Determinar la carpeta de salida
            batch_tab = self.main_app.batch_tab
            output_dir = batch_tab.output_path_entry.get()
            if hasattr(self, 'subfolder_path') and self.subfolder_path:
                output_dir = self.subfolder_path
            
            if not output_dir:
                raise Exception("Carpeta de salida no especificada.")

            # 5. Determinar el nombre del archivo de salida
            base_name = os.path.splitext(os.path.basename(input_file))[0]

            # --- INTERCEPCIÓN DE EXTRAS (LOCAL) ---
            is_extraction = preset_params.get('extract_frames_enabled', False)
            is_upscaling = preset_params.get('upscale_video_enabled', False)
            
            if is_extraction:
                self.ui_callback(job.job_id, "RUNNING", "Extrayendo fotogramas...")
                folder_name = f"{base_name}_frames"
                final_output_directory = os.path.join(output_dir, folder_name)
                
                # Conflicto: si la carpeta ya existe, respetar politica
                conflict_policy = batch_tab.conflict_policy_menu.get() if hasattr(batch_tab, 'conflict_policy_menu') else "Renombrar"
                if os.path.exists(final_output_directory):
                    if conflict_policy == "Omitir":
                        job.status = "SKIPPED"
                        self.ui_callback(job.job_id, "SKIPPED", "Omitido: La carpeta de fotogramas ya existe.")
                        return
                    elif conflict_policy == "Renombrar":
                        idx = 1
                        while os.path.exists(final_output_directory):
                            final_output_directory = os.path.join(output_dir, f"{folder_name} ({idx})")
                            idx += 1
                
                extraction_options = {
                    'input_file': input_file,
                    'output_folder': final_output_directory,
                    'image_format': preset_params.get('extract_format', 'png'),
                    'fps': preset_params.get('extract_fps'),
                    'jpg_quality': preset_params.get('extract_jpg_quality', '2'),
                    'duration': self._get_job_media_duration(job, input_file),
                    'pre_params': []
                }
                
                output_folder = self.main_app.ffmpeg_processor.execute_video_to_images(
                    extraction_options,
                    lambda p, m: self.ui_callback(job.job_id, "RUNNING", f"Extrayendo... {p:.1f}%"),
                    self.pause_event
                )
                
                if not preset_params.get('keep_original_file', True):
                    try:
                        os.remove(input_file)
                    except OSError:
                        pass
                
                job.status = "COMPLETED"
                job.final_filepath = output_folder
                self.ui_callback(job.job_id, "COMPLETED", f"Completado (Fotogramas): {os.path.basename(final_output_directory)}")
                return
            
            elif is_upscaling:
                self.ui_callback(job.job_id, "RUNNING", "Reescalando video (IA)...")
                scale_str = str(preset_params.get("upscale_scale", "2")).replace("x", "")
                out_stem = f"{base_name}_upscaled_x{scale_str}"
                desired_out_path = os.path.join(output_dir, out_stem + ".mp4")
                
                # Resolución de conflictos
                conflict_policy = batch_tab.conflict_policy_menu.get() if hasattr(batch_tab, 'conflict_policy_menu') else "Renombrar"
                out_path, _ = self._resolve_batch_conflict(desired_out_path, conflict_policy)
                if out_path is None:
                    job.status = "SKIPPED"
                    self.ui_callback(job.job_id, "SKIPPED", "Omitido: El archivo reescalado ya existe")
                    return
                
                ffmpeg_dir = os.path.dirname(self.main_app.ffmpeg_processor.ffmpeg_path)
                
                upscaler = VideoUpscaler(
                    ffmpeg_dir=ffmpeg_dir,
                    upscaling_dir=UPSCALING_DIR,
                    cancellation_event=self.pause_event,
                    progress_callback=lambda p, m: self.ui_callback(job.job_id, "RUNNING", f"({p:.1f}%) {m}" if isinstance(p, float) and p >= 0 else f"{m}")
                )
                
                final_path = upscaler.upscale_video(input_file, out_path, preset_params)
                
                if not preset_params.get('keep_originals', True):
                    try: os.remove(input_file)
                    except OSError: pass
                    
                job.status = "COMPLETED"
                job.final_filepath = final_path
                self.ui_callback(job.job_id, "COMPLETED", f"Completado (Upscaled): {os.path.basename(final_path)}")
                return
            # --- FIN INTERCEPCIÓN DE EXTRAS ---

            recoded_base_name = f"{base_name}_recoded"

            # 6. Ejecutar la recodificación (usando la misma función maestra)
            recoded_filepath = self._execute_recode_master(
                job=job,
                input_file=input_file,
                output_dir=output_dir,
                base_filename=recoded_base_name,
                recode_options=preset_params
            )
            
            # 7. Manejar el archivo original (si no se quiere conservar)
            if not job.config.get('recode_keep_original', True):
                try:
                    os.remove(input_file)
                    print(f"DEBUG: Archivo local original eliminado: {input_file}")
                except OSError as e:
                    print(f"ADVERTENCIA: No se pudo eliminar el archivo local original: {e}")
            
            final_filepath = recoded_filepath
            
            # 8. Marcar como completado
            job.status = "COMPLETED"
            job.final_filepath = final_filepath
            self.ui_callback(job.job_id, "COMPLETED", f"Recodificado: {os.path.basename(final_filepath)}")

            # 9. Lógica de Importación Automática (adaptada para locales)
            thumbnail_path = None
            if batch_tab and batch_tab.auto_import_checkbox.get():
                active_target = self.main_app.ACTIVE_TARGET_SID_accessor()
                if active_target:
                    
                    # Generar una miniatura sobre la marcha para la importación
                    try:
                        print(f"DEBUG: Generando miniatura para importación automática...")
                        duration = self._get_job_media_duration(job, final_filepath)
                        temp_thumb_path = self.main_app.ffmpeg_processor.get_frame_from_video(final_filepath, duration)
                        
                        if temp_thumb_path and os.path.exists(temp_thumb_path):
                            # Mover la miniatura junto al video recodificado
                            thumb_dir = os.path.dirname(final_filepath)
                            thumb_name = os.path.splitext(os.path.basename(final_filepath))[0] + ".jpg"
                            thumbnail_path = os.path.join(thumb_dir, thumb_name)
                            
                            if os.path.exists(thumbnail_path):
                                os.remove(thumbnail_path) # Sobrescribir si ya existe
                                
                            shutil.move(temp_thumb_path, thumbnail_path)
                            print(f"DEBUG: Miniatura generada para importación: {thumbnail_path}")
                    except Exception as e:
                        print(f"ADVERTENCIA: No se pudo generar la miniatura para importar: {e}")

                    # Determinar el 'bin' de destino
                    target_bin_name = None
                    if hasattr(self, 'subfolder_path') and self.subfolder_path:
                        target_bin_name = os.path.basename(os.path.normpath(self.subfolder_path))
                    
                    # Armar el paquete de archivos
                    file_package = {
                        "video": final_filepath.replace('\\', '/'),
                        "thumbnail": thumbnail_path.replace('\\', '/') if thumbnail_path else None,
                        "subtitle": None,
                        "targetBin": target_bin_name
                    }
                    
                    print(f"INFO: [Lote Local] Enviando paquete a CEP: {file_package}")
                    
                    # Enviar el paquete
                    self.main_app.socketio.emit('new_file', {'filePackage': file_package}, to=active_target)

        except Exception as e:
            # Si falla, la excepción será capturada por _worker_thread
            print(f"ERROR: Falló el trabajo de recodificación local {job.job_id}: {e}")
            raise e # Re-lanzar para que el worker lo marque como FAILED
        
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
            smart_ext = get_smart_thumbnail_extension(image_data) # <-- USAR NUEVA FUNCIÓN
            
            # Nombre del archivo
            title = single_tab.sanitize_filename(job.config.get('title', 'thumbnail'))
            final_path_smart = os.path.join(thumbnails_dir, f"{title}{smart_ext}") # <-- Usar smart_ext
            
            # Resolver conflictos
            conflict_policy = batch_tab.conflict_policy_menu.get()
            final_path, backup_path = self._resolve_batch_conflict(final_path_smart, conflict_policy) # <-- Usar ruta smart
            
            if final_path is None:
                # Si se omite, no es un error, solo se salta
                job.status = "SKIPPED"
                job.final_filepath = final_path_smart
                self.ui_callback(job.job_id, "SKIPPED", "Omitido: Miniatura ya existe")
                return # Salir limpiamente

            # Re-codificar imagen con PIL (preservando transparencia)
            try:
                pil_image = Image.open(BytesIO(image_data))
                if smart_ext == '.png':
                    pil_image.save(final_path, "PNG")
                else:
                    pil_image.convert("RGB").save(final_path, "JPEG", quality=95)
            except Exception as pil_e:
                print(f"ERROR: Falló el procesamiento de la imagen (PIL): {pil_e}")
                # Fallback: guardar el archivo original (podría fallar la importación)
                with open(final_path, 'wb') as f:
                    f.write(image_data)
            
            # Limpiar backup si existía
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
            
            job.status = "COMPLETED"
            job.final_filepath = final_path
            job.thumbnail_path = final_path # ✅ NUEVO: Guardar ruta explícitamente
            self.ui_callback(job.job_id, "COMPLETED", f"Miniatura guardada: {os.path.basename(final_path)}")

            # 1. Verificar si el usuario quiere importar
            batch_tab = self.main_app.batch_tab
            if batch_tab and batch_tab.auto_import_checkbox.get():
                
                # 2. Verificar si hay una extensión de Adobe conectada
                active_target = self.main_app.ACTIVE_TARGET_SID_accessor()
                if active_target:
                    
                    # 3. Determinar el nombre del bin (LÓGICA CORREGIDA)
                    base_bin_name = None
                    # Comprobar si hay una subcarpeta de lote (ej: "Mi Lote 01")
                    if hasattr(self, 'subfolder_path') and self.subfolder_path:
                        base_bin_name = os.path.basename(os.path.normpath(self.subfolder_path))

                    target_bin_name = "Thumbnails" # Nombre por defecto
                    
                    # Si había una carpeta de lote, crear un nombre combinado
                    if base_bin_name:
                        target_bin_name = f"{base_bin_name} - Thumbnails"
                    
                    # 4. Armar el paquete (solo contiene la miniatura)
                    file_package = {
                        "video": None, # Importante: video es null
                        "thumbnail": final_path.replace('\\', '/'), # Ruta de la imagen
                        "subtitle": None,
                        "targetBin": target_bin_name # ej: "Thumbnails" o "Mi Lote 01 - Thumbnails"
                    }
                    
                    print(f"INFO: [Lote Miniaturas] Enviando paquete a CEP: {file_package}")
                    
                    # 5. Enviar el paquete
                    self.main_app.socketio.emit('new_file', {'filePackage': file_package}, to=active_target)
            
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
            smart_ext = get_smart_thumbnail_extension(image_data) # <-- USAR NUEVA FUNCIÓN
            
            # Generar nombre basado en el video
            video_dir = os.path.dirname(video_filepath)
            video_name = os.path.splitext(os.path.basename(video_filepath))[0]
            thumbnail_path_smart = os.path.join(video_dir, f"{video_name}{smart_ext}") # <-- Usar smart_ext

            # Re-codificar imagen con PIL (preservando transparencia)
            try:
                pil_image = Image.open(BytesIO(image_data))
                if smart_ext == '.png':
                    pil_image.save(thumbnail_path_smart, "PNG")
                else:
                    pil_image.convert("RGB").save(thumbnail_path_smart, "JPEG", quality=95)
                
                print(f"INFO: Miniatura (re-codificada) guardada: {thumbnail_path_smart}")
                job.thumbnail_path = thumbnail_path_smart # ✅ NUEVO: Guardar en el job
                return thumbnail_path_smart
            # --- FIN DE CORRECCIÓN ---
            except Exception as pil_e:
                print(f"ERROR: Falló el procesamiento de la imagen (PIL): {pil_e}")
                # Fallback: guardar el archivo original (podría fallar la importación)
                # Usamos el nombre .jpg original para consistencia
                with open(thumbnail_path_smart, 'wb') as f:
                    f.write(image_data)
                print(f"INFO: Miniatura (raw) guardada: {thumbnail_path_smart}")
                return thumbnail_path_smart
            
        except Exception as e:
            print(f"ERROR al descargar miniatura para {job.job_id}: {e}")
            # No fallar el job completo si solo falla la miniatura
            return None

    def _rebuild_format_maps(self, info: dict) -> tuple[dict, dict]:
        """
        Re-crea los mapas de formatos con soporte para multiidioma.
        """
        formats = info.get('formats', [])
        video_duration = info.get('duration', 0)
        
        job_video_formats = {}
        job_audio_formats = {}
        combined_variants = {}  # 🆕 Para agrupar variantes multiidioma

        # 🆕 PASADA PREVIA: Agrupar variantes combinadas
        for f in formats:
            format_type = self._classify_format(f)
            
            if format_type in ['VIDEO', 'VIDEO_ONLY']:
                vcodec_raw = f.get('vcodec')
                acodec_raw = f.get('acodec')
                vcodec = vcodec_raw.split('.')[0] if vcodec_raw else 'none'
                acodec = acodec_raw.split('.')[0] if acodec_raw else 'none'
                is_combined = acodec != 'none' and acodec is not None
                
                if is_combined:
                    fps = f.get('fps')
                    height = f.get('height', 0)
                    fps_val = int(fps) if fps else 0
                    ext = f.get('ext', 'N/A')
                    
                    tbr = f.get('tbr', 0)
                    tbr_rounded = round(tbr / 100) * 100 if tbr else 0
                    
                    quality_key = f"{height}p{fps_val}_{ext}_{vcodec}_{acodec}_tbr{tbr_rounded}"
                    
                    if quality_key not in combined_variants:
                        combined_variants[quality_key] = []
                    combined_variants[quality_key].append(f)
        
        # 🆕 Filtrar grupos REALMENTE multiidioma (2+ idiomas DIFERENTES)
        real_multilang_keys = set()
        for quality_key, variants in combined_variants.items():
            unique_languages = set()
            for variant in variants:
                lang = variant.get('language', '')
                if lang:
                    unique_languages.add(lang)
            
            if len(unique_languages) >= 2:
                real_multilang_keys.add(quality_key)
                print(f"DEBUG: Grupo multiidioma detectado: {quality_key}")

        # 🆕 Tracking de deduplicación
        combined_keys_seen = set()

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
            
            if format_type in ['VIDEO', 'VIDEO_ONLY']:  # 🆕 Incluir VIDEO_ONLY
                is_combined = acodec != 'none' and acodec is not None
                fps = f.get('fps')
                fps_tag = f"{fps:.0f}" if fps else ""
                
                quality_key = None
                if is_combined:
                    height = f.get('height', 0)
                    fps_val = int(fps) if fps else 0
                    tbr = f.get('tbr', 0)
                    tbr_rounded = round(tbr / 100) * 100 if tbr else 0
                    quality_key = f"{height}p{fps_val}_{ext}_{vcodec}_{acodec}_tbr{tbr_rounded}"
                    
                    # 🆕 Solo deduplicar si es REALMENTE multiidioma
                    if quality_key in real_multilang_keys:
                        if quality_key in combined_keys_seen:
                            continue
                        combined_keys_seen.add(quality_key)
                
                label_base = f"{f.get('height', 'Video')}p{fps_tag} ({ext}"
                label_codecs = f", {vcodec}+{acodec}" if is_combined else f", {vcodec}"
                
                # 🆕 [Sin Audio] solo si NO hay audio
                no_audio_tag = ""
                if format_type == 'VIDEO_ONLY':
                    no_audio_tag = " [Sin Audio]"
                
                # 🆕 [Multiidioma] solo si es REALMENTE multiidioma
                audio_lang_tag = ""
                if is_combined and quality_key:
                    if quality_key in real_multilang_keys:
                        audio_lang_tag = " [Multiidioma]"
                
                label_tag = " [Combinado]" if is_combined else ""
                note = f.get('format_note') or ''
                note_tag = ""
                if any(k in note.lower() for k in ['hdr', 'premium', 'dv', 'hlg', 'storyboard']):
                    note_tag = f" [{note}]"
                protocol = f.get('protocol', '')
                protocol_tag = " [Streaming]" if 'm3u8' in protocol else ""
                
                label = f"{label_base}{label_codecs}){label_tag}{audio_lang_tag}{no_audio_tag}{note_tag}{protocol_tag} - {size_mb_str}"

                tags = []
                compatibility_issues, _ = self._get_format_compatibility_issues(f)
                if not compatibility_issues: 
                    tags.append("✨")
                else: 
                    tags.append("⚠️")
                if tags: 
                    label += f" {' '.join(tags)}"
                
                # 🆕 Guardar también quality_key y is_combined
                job_video_formats[label] = {
                    **f, 
                    'is_combined': is_combined,
                    'quality_key': quality_key
                }

            elif format_type == 'AUDIO':
                abr = f.get('abr') or f.get('tbr')
                lang_code = f.get('language')
                lang_name = "Idioma Desconocido"
                if lang_code:
                    norm_code = lang_code.replace('_', '-').lower()
                    lang_name = self.main_app.LANG_CODE_MAP.get(
                        norm_code, 
                        self.main_app.LANG_CODE_MAP.get(norm_code.split('-')[0], lang_code)
                    )
                
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

        # ✅ NUEVO: Generar opciones de "Extraer Audio" (Copia los videos a la lista de audios)
        for label, video_data in job_video_formats.items():
            if video_data.get('is_combined', False):
                acodec = video_data.get('acodec', 'unknown')
                if acodec == 'none': continue
                
                acodec_clean = acodec.split('.')[0]
                # Limpiar la etiqueta para que quede bonita (ej: "1080p60")
                res_part = label.split('|')[0].strip()
                if '(' in res_part: res_part = res_part.split('(')[0].strip()
                
                audio_extract_label = f"Extraer de {res_part} ({acodec_clean})"
                
                # Agregarlo al mapa de audio.
                # IMPORTANTE: Esto evita que job_audio_formats quede vacío en Twitch Clips
                if audio_extract_label not in job_audio_formats:
                    job_audio_formats[audio_extract_label] = video_data

        # 1. Convertir los dicts a listas de entradas (como en single_tab)
        video_entries = []
        for label, data in job_video_formats.items():
            video_entries.append({
                'label': label,
                'format': data, # El 'format' aquí es el dict de formato completo
                'is_combined': data.get('is_combined', False),
                'quality_key': data.get('quality_key')
            })

        audio_entries = []
        for label, data in job_audio_formats.items():
            audio_entries.append({
                'label': label,
                'format': data
            })

        # 2. Copiar la LÓGICA DE ORDENAMIENTO EXACTA de single_download_tab.py
        
        # Ordenar Video
        video_entries.sort(key=lambda e: (
            -(e['format'].get('height') or 0),      
            1 if "[Combinado]" in e['label'] else 0, 
            0 if "✨" in e['label'] else 1,         
            -(e['format'].get('tbr') or 0)          
        ))
        
        # Ordenar Audio
        def custom_audio_sort_key(entry):
            f = entry['format']
            lang_code_raw = f.get('language') or ''
            norm_code = lang_code_raw.replace('_', '-')
            # Usar los constantes importados
            lang_priority = self.main_app.LANGUAGE_ORDER.get(
                norm_code, 
                self.main_app.LANGUAGE_ORDER.get(norm_code.split('-')[0], self.main_app.DEFAULT_PRIORITY)
            )
            quality = f.get('abr') or f.get('tbr') or 0
            return (lang_priority, -quality)
            
        audio_entries.sort(key=custom_audio_sort_key)

        # 3. Reconstruir los diccionarios (ahora ordenados)
        # Se usa dict() para crear un nuevo diccionario ordenado
        job_video_formats = {e['label']: e['format'] for e in video_entries}
        job_audio_formats = {e['label']: e['format'] for e in audio_entries}

        
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
        Clasifica un formato (v3.2 - Manejo de codecs 'unknown')
        """
        ext = f.get('ext', '')
        vcodec = f.get('vcodec', '')
        acodec = f.get('acodec', '')
        format_id = (f.get('format_id') or '').lower()
        format_note = (f.get('format_note') or '').lower()
        protocol = f.get('protocol', '')
        
        # 🆕 REGLA -1: Formato sintético
        if 'audio directo' in format_note or 'livestream' in format_note:
            if 'audio' in format_note:
                return 'AUDIO'
            return 'VIDEO'
        
        # 🆕 REGLA 0: Casos especiales de vcodec literal
        vcodec_special_cases = {
            'audio only': 'AUDIO',
            'images': 'VIDEO',
            'slideshow': 'VIDEO',
        }
        
        if vcodec in vcodec_special_cases:
            return vcodec_special_cases[vcodec]
        
        # 📋 REGLA 1: GIF explícito
        if ext == 'gif' or vcodec == 'gif':
            return 'VIDEO'
        
        # 📋 REGLA 2: Tiene dimensiones → VIDEO (con o sin audio)
        if f.get('height') or f.get('width'):
            # 🆕 CRÍTICO: Si ambos codecs son 'unknown' o faltan → ASUMIR COMBINADO
            vcodec_is_unknown = not vcodec or vcodec in ['unknown', 'N/A', '']
            acodec_is_unknown = not acodec or acodec in ['unknown', 'N/A', '']
            
            if vcodec_is_unknown and acodec_is_unknown:
                print(f"DEBUG: Formato {f.get('format_id')} con codecs desconocidos → asumiendo VIDEO combinado")
                return 'VIDEO'
            
            if acodec in ['none']:
                return 'VIDEO_ONLY'
            
            return 'VIDEO'
        
        # 🆕 REGLA 2.5: Livestreams
        if f.get('is_live') or 'live' in format_id:
            return 'VIDEO'
        
        # 📋 REGLA 3: Resolución en format_note
        resolution_patterns = ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p', '4320p']
        if any(res in format_note for res in resolution_patterns):
            if acodec in ['none']:
                return 'VIDEO_ONLY'
            return 'VIDEO'
        
        # 📋 REGLA 4: "audio" explícito en IDs
        if 'audio' in format_id or 'audio' in format_note:
            return 'AUDIO'
        
        # 🆕 REGLA 4.5: "video" explícito en IDs
        if 'video' in format_id or 'video' in format_note:
            if f.get('height') or (vcodec == 'unknown' and acodec == 'unknown'):
                return 'VIDEO'
            return 'VIDEO_ONLY' if acodec in ['none'] else 'VIDEO'
        
        # 📋 REGLA 5: Extensión tiene MÁXIMA PRIORIDAD
        if ext in self.main_app.AUDIO_EXTENSIONS:
            return 'AUDIO'
        
        # 🆕 REGLA 6: Audio sin video (codec EXPLÍCITAMENTE 'none')
        if vcodec == 'none' and acodec and acodec not in ['none', '', 'N/A', 'unknown']:
            return 'AUDIO'
        
        # 🆕 REGLA 7: Video sin audio (codec EXPLÍCITAMENTE 'none')
        if acodec == 'none' and vcodec and vcodec not in ['none', '', 'N/A', 'unknown']:
            return 'VIDEO_ONLY'
        
        # 📋 REGLA 8: Extensión de video + codecs válidos o desconocidos
        if ext in self.main_app.VIDEO_EXTENSIONS:
            if vcodec in ['unknown', ''] and acodec in ['unknown', '']:
                return 'VIDEO'
            return 'VIDEO'
        
        # 📋 REGLA 9: Ambos codecs explícitamente válidos
        valid_vcodecs = ['h264', 'h265', 'vp8', 'vp9', 'av1', 'hevc', 'mpeg4', 'xvid', 'theora']
        valid_acodecs = ['aac', 'mp3', 'opus', 'vorbis', 'flac', 'ac3', 'eac3', 'pcm']
        
        vcodec_lower = (vcodec or '').lower()
        acodec_lower = (acodec or '').lower()
        
        if vcodec_lower in valid_vcodecs:
            if acodec_lower in valid_acodecs:
                return 'VIDEO'
            else:
                return 'VIDEO_ONLY'
        
        # 📋 REGLA 10: Protocolo m3u8/dash
        if 'm3u8' in protocol or 'dash' in protocol:
            return 'VIDEO'
        
        # 🆕 REGLA 11: Casos de formatos sin codecs claros pero con metadata
        if f.get('tbr') and not f.get('abr'):
            return 'VIDEO'
        elif f.get('abr') and not f.get('vbr'):
            return 'AUDIO'
        
        # 🆕 REGLA 12: Fallback para casos ambiguos con extensión de video
        if ext in self.main_app.VIDEO_EXTENSIONS:
            print(f"⚠️ ADVERTENCIA: Formato {f.get('format_id')} ambiguo → asumiendo VIDEO combinado por extensión")
            return 'VIDEO'
        
        # 📋 REGLA 13: Si llegamos aquí → UNKNOWN
        print(f"⚠️ ADVERTENCIA: Formato sin clasificación clara: {f.get('format_id')} (vcodec={vcodec}, acodec={acodec}, ext={ext})")
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
    
    def _normalize_info_dict(self, info):
        """
        Normaliza el diccionario de info para casos donde yt-dlp no devuelve 'formats'.
        Maneja contenido de audio directo.
        """
        if not info:
            return info
        
        # ✅ INYECCIÓN DEL PARCHE (Igual que en single_tab y batch_tab)
        # Asegura que el procesador vea códecs válidos y no falle al clasificar.
        info = apply_site_specific_rules(info)
        
        formats = info.get('formats', [])
        
        if formats:
            return info
        
        # Detectar contenido de audio directo
        url = info.get('url')
        ext = info.get('ext')
        vcodec = info.get('vcodec', 'none')
        acodec = info.get('acodec')
        
        is_audio_content = False
        
        if url and ext and (vcodec == 'none' or not vcodec) and acodec and acodec != 'none':
            is_audio_content = True
        elif ext in self.main_app.AUDIO_EXTENSIONS:
            is_audio_content = True
            if not acodec or acodec == 'none':
                acodec = {'mp3': 'mp3', 'opus': 'opus', 'aac': 'aac', 'm4a': 'aac'}.get(ext, ext)
        elif info.get('extractor_key', '').lower() in ['applepodcasts', 'soundcloud', 'audioboom', 'spreaker']:
            is_audio_content = True
            if not acodec:
                acodec = 'mp3'
        
        if is_audio_content:
            print(f"DEBUG: 🎵 Contenido de audio directo detectado (ext={ext})")
            
            synthetic_format = {
                'format_id': '0',
                'url': url or info.get('manifest_url') or '',
                'ext': ext or 'mp3',
                'vcodec': 'none',
                'acodec': acodec or 'unknown',
                'abr': info.get('abr'),
                'tbr': info.get('tbr'),
                'filesize': info.get('filesize'),
                'filesize_approx': info.get('filesize_approx'),
                'protocol': info.get('protocol', 'https'),
                'format_note': 'Audio directo',
            }
            
            info['formats'] = [synthetic_format]
            print(f"DEBUG: ✅ Formato sintético creado")
        
        return info
    
    def _find_preset_params(self, preset_name):
        """
        Busca un preset por su nombre (personalizados y luego integrados).
        Adaptado de batch_download_tab.py, busca en single_tab.
        """
        # Buscar en personalizados
        for preset in getattr(self.main_app.single_tab, 'custom_presets', []):
            if preset.get("name") == preset_name:
                return preset.get("data", {})
        
        # Buscar en integrados
        if preset_name in self.main_app.single_tab.built_in_presets:  
            return self.main_app.single_tab.built_in_presets[preset_name]
            
        return {}

    def _get_job_media_duration(self, job: Job, input_file: str) -> float:
        """
        Obtiene la duración del medio, priorizando los datos del análisis
        y usando ffprobe como fallback.
        """
        # 1. Prioridad: Datos del análisis (más rápido)
        if job.analysis_data:
            duration = job.analysis_data.get('duration')
            if duration:
                return float(duration)
        
        # 2. Fallback: Usar ffprobe (más lento pero preciso)
        try:
            media_info = self.main_app.ffmpeg_processor.get_local_media_info(input_file)
            if media_info:
                return float(media_info['format']['duration'])
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo obtener duración con ffprobe: {e}")
            
        return 0.0 # No se pudo determinar

    def _execute_recode_master(self, job: Job, input_file, output_dir, base_filename, recode_options):
        """
        Función maestra que maneja la lógica de recodificación para un job.
        Adaptada de single_download_tab.py.
        """
        final_recoded_path = None
        backup_file_path = None
        
        try:
            self.ui_callback(job.job_id, "RUNNING", "Preparando recodificación...")
            
            final_container = recode_options["recode_container"]
            if not recode_options['recode_video_enabled'] and not recode_options['recode_audio_enabled']:
                _, original_extension = os.path.splitext(input_file)
                final_container = original_extension

            final_filename_with_ext = f"{base_filename}{final_container}"
            desired_recoded_path = os.path.join(output_dir, final_filename_with_ext)
            
            # Resolver conflictos de archivo
            final_recoded_path, backup_file_path = self._resolve_batch_conflict(desired_recoded_path, "Sobrescribir")

            temp_output_path = final_recoded_path + ".temp"

            final_ffmpeg_params = []
            pre_params = []

            # --- INICIO DE CORRECCIÓN (Muxer vs Contenedor) ---
            container_ext = recode_options.get('recode_container', '.mp4')
            if container_ext == "-":
                container_ext = ".mp4"
            
            # Buscar un muxer específico en el mapa (ej: .m4a -> mp4)
            # Usamos self.main_app.FORMAT_MUXER_MAP
            muxer_name = self.main_app.FORMAT_MUXER_MAP.get(container_ext, container_ext.lstrip('.'))
            
            final_ffmpeg_params.extend(['-f', muxer_name])
            print(f"DEBUG: [Muxer] Contenedor: {container_ext}, Muxer: {muxer_name}")
            # --- FIN DE CORRECCIÓN ---

            # ====== PROCESAMIENTO DE VIDEO ======
            if recode_options['mode_compatibility'] != "Solo Audio":
                if recode_options["recode_video_enabled"]:
                    final_ffmpeg_params.extend(["-metadata:s:v:0", "rotate=0"])
                    proc = recode_options["recode_proc"]
                    codec_db = self.main_app.ffmpeg_processor.available_encoders[proc]["Video"]
                    codec_data = codec_db.get(recode_options["recode_codec_name"])
                    ffmpeg_codec_name = next((k for k in codec_data if k != 'container'), None)
                    profile_params_list = codec_data[ffmpeg_codec_name].get(recode_options["recode_profile_name"])

                    if profile_params_list == "CUSTOM_GIF":
                        try:
                            fps = int(recode_options["custom_gif_fps"] or "15")
                            width = int(recode_options["custom_gif_width"] or "480")
                            filter_string = f"[0:v] fps={fps},scale={width}:-1,split [a][b];[a] palettegen [p];[b][p] paletteuse"
                            final_ffmpeg_params.extend(['-filter_complex', filter_string])
                        except (ValueError, TypeError):
                            raise Exception("Valores de FPS/Ancho para GIF no son válidos.")

                    elif isinstance(profile_params_list, str) and "CUSTOM_BITRATE" in profile_params_list:
                        bitrate_mbps = float(recode_options["custom_bitrate_value"] or "8")
                        bitrate_k = int(bitrate_mbps * 1000)
                        if "nvenc" in ffmpeg_codec_name:
                            params_str = f"-c:v {ffmpeg_codec_name} -preset p5 -rc vbr -b:v {bitrate_k}k -maxrate {bitrate_k}k -pix_fmt yuv420p"
                        else:
                            params_str = f"-c:v {ffmpeg_codec_name} -b:v {bitrate_k}k -maxrate {bitrate_k}k -bufsize {bitrate_k*2}k -pix_fmt yuv420p"
                        final_ffmpeg_params.extend(params_str.split())
                    else: 
                        final_ffmpeg_params.extend(profile_params_list)

                    # Filtros de video (FPS y resolución)
                    video_filters = []
                    if recode_options.get("fps_force_enabled") and recode_options.get("fps_value"):
                        video_filters.append(f'fps={recode_options["fps_value"]}')
                    
                    if recode_options.get("resolution_change_enabled"):
                        # (La lógica de preset/personalizado ya está resuelta en el preset)
                        try:
                            target_w = int(recode_options["res_width"])
                            target_h = int(recode_options["res_height"])

                            if target_w > 0 and target_h > 0:
                                if recode_options.get("no_upscaling_enabled"):
                                    # Obtener resolución original
                                    media_info = self.main_app.ffmpeg_processor.get_local_media_info(input_file)
                                    original_width = 0
                                    original_height = 0
                                    if media_info and media_info.get('streams'):
                                        video_stream = next((s for s in media_info['streams'] if s.get('codec_type') == 'video'), None)
                                        if video_stream:
                                            original_width = video_stream.get('width', 0)
                                            original_height = video_stream.get('height', 0)
                                    
                                    if original_width > 0 and target_w > original_width:
                                        target_w = original_width
                                    if original_height > 0 and target_h > original_height:
                                        target_h = original_height
                                
                                video_filters.append(f'scale={target_w}:{target_h}')
                        except (ValueError, TypeError):
                            pass # Ignorar si los valores de res están vacíos

                    if video_filters and "filter_complex" not in final_ffmpeg_params:
                        final_ffmpeg_params.extend(['-vf', ",".join(video_filters)])
                else:
                    final_ffmpeg_params.extend(["-c:v", "copy"])
            else:
                # Modo Solo Audio, asegurarse de no incluir video
                final_ffmpeg_params.extend(["-vn"])

            # ====== PROCESAMIENTO DE AUDIO ======
            is_gif_format = "GIF" in recode_options.get("recode_codec_name", "")

            if not is_gif_format:
                is_pro_video_format = False
                if recode_options.get("recode_video_enabled", False):
                    if any(x in recode_options.get("recode_codec_name", "") for x in ["ProRes", "DNxH"]):
                        is_pro_video_format = True
                
                if is_pro_video_format:
                    final_ffmpeg_params.extend(["-c:a", "pcm_s16le"])
                elif recode_options.get("recode_audio_enabled", False):
                    audio_codec_db = self.main_app.ffmpeg_processor.available_encoders["CPU"]["Audio"]
                    audio_codec_data = audio_codec_db.get(recode_options["recode_audio_codec_name"])
                    ffmpeg_audio_codec = next((k for k in audio_codec_data if k != 'container'), None)
                    audio_profile_params = audio_codec_data[ffmpeg_audio_codec].get(recode_options["recode_audio_profile_name"])
                    if audio_profile_params:
                        final_ffmpeg_params.extend(audio_profile_params)
                else:
                    final_ffmpeg_params.extend(["-c:a", "copy"])
            else:
                final_ffmpeg_params.extend(["-an"]) # Es un GIF, eliminar audio

            # --- INICIO DE CORRECCIÓN (Soporte Multipista Local v2) ---
            
            # 1. Determinar el índice de audio
            selected_audio_idx = None
            if not is_gif_format:
                # Por defecto, "all" (comportamiento anterior para descargas)
                selected_audio_idx = "all" 
                
                # Comprobar si es un trabajo local
                if job.job_type == "LOCAL_RECODE":
                    # Leer el estado del checkbox "Usar todas las pistas"
                    use_all_tracks = job.config.get('recode_all_audio_tracks', False)
                    
                    if use_all_tracks:
                        selected_audio_idx = "all"
                        print(f"DEBUG: [Recodificación Local] Usando 'all' pistas de audio (checkbox activado).")
                    else:
                        # Checkbox no activado, buscar el índice específico guardado
                        saved_idx = job.config.get('resolved_audio_stream_index')
                        if saved_idx is not None:
                            selected_audio_idx = int(saved_idx)
                            print(f"DEBUG: [Recodificación Local] Usando pista de audio específica: {selected_audio_idx}")
                        else:
                            # Fallback: no hay índice guardado, usar la primera pista de audio (índice 0)
                            # Esto es más seguro que "all" para evitar el error del muxer
                            try:
                                audio_streams = job.analysis_data.get('local_info', {}).get('audio_streams', [])
                                if audio_streams:
                                    selected_audio_idx = audio_streams[0].get('index', 0)
                                    print(f"ADVERTENCIA: [Recodificación Local] No se encontró índice de audio guardado. Usando fallback a la primera pista (índice {selected_audio_idx}).")
                                else:
                                    selected_audio_idx = None # No hay audio
                            except Exception:
                                selected_audio_idx = 0 # Fallback final
                
            # 2. Determinar el índice de video (asumir el primero si existe)
            selected_video_idx = None
            if "-filter_complex" not in final_ffmpeg_params and recode_options.get('mode_compatibility') != "Solo Audio":
                if job.job_type == "LOCAL_RECODE":
                    try:
                        video_stream = job.analysis_data.get('local_info', {}).get('video_stream')
                        if video_stream:
                            selected_video_idx = video_stream.get('index', 0)
                    except Exception:
                        selected_video_idx = 0 # Fallback
                else:
                    selected_video_idx = 0 # Fallback para descargas

            # --- FIN DE CORRECCIÓN ---

            command_options = {
                "input_file": input_file, 
                "output_file": temp_output_path,
                "duration": self._get_job_media_duration(job, input_file), 
                "ffmpeg_params": final_ffmpeg_params,
                "pre_params": pre_params, 
                "mode": recode_options.get('mode_compatibility'),
                "selected_video_stream_index": selected_video_idx, # <-- CORREGIDO
                "selected_audio_stream_index": selected_audio_idx   # <-- CORREGIDO
            }

            # Función de callback de progreso para este job
            def recode_progress_callback(percentage, message):
                self.ui_callback(job.job_id, "RUNNING", message)

            # Ejecutar recodificación
            self.main_app.ffmpeg_processor.execute_recode(
                command_options, 
                recode_progress_callback, 
                self.pause_event # Usar el pause_event de la cola
            )

            if self.pause_event.is_set():
                raise UserCancelledError("Proceso pausado por el usuario.")

            # Renombrar archivo temporal al nombre final
            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, final_recoded_path)
            
            # Eliminar backup si existía
            if backup_file_path and os.path.exists(backup_file_path):
                os.remove(backup_file_path)
            
            return final_recoded_path
            
        except Exception as e:
            # Limpieza en caso de error
            if os.path.exists(temp_output_path):
                try: os.remove(temp_output_path)
                except OSError: pass
            
            if backup_file_path and os.path.exists(backup_file_path):
                try: os.rename(backup_file_path, final_recoded_path)
                except OSError: pass
            
            raise e # Re-lanzar la excepción
        
    def _download_best_thumb_png(self, entry, output_dir, title):
        """
        Descarga la mejor miniatura disponible (Forzando MaxRes) y la guarda como PNG.
        """
        try:
            # 1. Buscar la URL base
            thumb_url = None
            thumbs = entry.get('thumbnails')
            
            if thumbs:
                sorted_thumbs = sorted(thumbs, key=lambda x: x.get('width', 0) or 0, reverse=True)
                thumb_url = sorted_thumbs[0].get('url')
            
            if not thumb_url:
                thumb_url = entry.get('thumbnail')
            
            if not thumb_url: return

            # 2. INTENTO INTELIGENTE: Forzar MaxResDefault
            # Primero intentamos descargar la versión HD forzada.
            # Si falla (404), caemos a la versión original (hqdefault).
            final_url = thumb_url
            if "i.ytimg.com" in thumb_url:
                import re
                max_res_url = re.sub(r'/(hq|mq|sd|default)default', '/maxresdefault', thumb_url)
                
                # Probamos si maxres existe (haciendo una petición HEAD o GET rápida)
                try:
                    check_resp = requests.get(max_res_url, timeout=5, stream=True)
                    if check_resp.status_code == 200:
                        final_url = max_res_url
                        check_resp.close() # Cerramos stream
                    # Si da 404, nos quedamos con thumb_url original
                except:
                    pass # Si falla la comprobación, usar la original

            # 3. Descargar datos reales
            response = requests.get(final_url, timeout=30)
            response.raise_for_status()
            image_data = response.content
            
            # 4. Procesar y guardar como PNG
            sanitized_title = self.main_app.single_tab.sanitize_filename(title)
            output_path = os.path.join(output_dir, f"{sanitized_title}.png")
            
            from PIL import Image
            from io import BytesIO

            img = Image.open(BytesIO(image_data))
            img.save(output_path, "PNG")
            print(f"DEBUG: Miniatura PNG guardada ({'MAXRES' if final_url != thumb_url else 'ORIG'}): {output_path}")
            
            return output_path # <--- AÑADIDO: Devolver la ruta
            
        except Exception as e:
            print(f"ADVERTENCIA: Falló descarga de miniatura PNG para '{title}': {e}")
            return None # <--- AÑADIDO: Devolver None si falla