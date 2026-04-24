import os
import subprocess
import shutil

class InkscapeService:
    """
    Servicio independiente para gestionar la comunicación con Inkscape externo.
    Permite desacoplar Inkscape del núcleo del programa.
    """
    def __init__(self, custom_path=None):
        self.base_path = custom_path
        self.actual_bin_path = None
        self.version_info = None
        
        if self.base_path:
            self._detect_binary()

    def _detect_binary(self):
        """Busca el ejecutable en la raíz o en /bin de la ruta proporcionada."""
        if not self.base_path:
            return False
            
        exe_name = "inkscape.com" if os.name == "nt" else "inkscape"
        
        # Opción A: Raíz
        path_root = os.path.join(self.base_path, exe_name)
        # Opción B: /bin
        path_bin = os.path.join(self.base_path, "bin", exe_name)
        
        if os.path.exists(path_bin):
            self.actual_bin_path = path_bin
            return True
        elif os.path.exists(path_root):
            self.actual_bin_path = path_root
            return True
            
        return False

    def is_available(self):
        """Verifica si Inkscape está configurado y es funcional."""
        if not self.actual_bin_path:
            # Intentar redetectar si cambió la ruta
            if not self._detect_binary():
                return False
        
        try:
            # Prueba rápida de ejecución
            result = subprocess.run(
                [self.actual_bin_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            if result.returncode == 0:
                self.version_info = result.stdout.decode('utf-8', errors='ignore').strip()
                return True
        except Exception:
            pass
            
        return False

    def build_command(self, filepath, output_path, page_number=1, dpi=300, artboard_id=None):
        """
        Construye el comando CLI de Inkscape.
        """
        if not self.actual_bin_path:
            return None
            
        filepath = os.path.normpath(os.path.abspath(filepath))
        output_path = os.path.normpath(os.path.abspath(output_path))
        ext = os.path.splitext(filepath)[1].lower()
        
        cmd = [
            self.actual_bin_path,
            filepath,
            f"--export-filename={output_path}",
            f"--export-dpi={dpi}",
            "--export-type=png",
            "--export-background-opacity=0",
            "--batch-process"
        ]
        
        # Lógica de importación específica
        if ext in (".ai", ".pdf"):
            # Para Inkscape externo, solemos preferir su importador nativo 
            # a menos que sea multipágina.
            if page_number > 1:
                cmd.insert(2, f"--pages={page_number}")
                cmd.insert(4, "--export-area-page")
            else:
                cmd.insert(4, "--export-area-drawing")
        elif ext in (".eps", ".ps"):
            cmd.insert(2, "--export-area-drawing")
        elif ext == ".svg" and artboard_id:
            cmd.insert(2, f"--export-id={artboard_id}")
            cmd.insert(3, "--export-id-only")
        else:
            cmd.insert(2, "--export-area-drawing")
            
        return cmd

    def get_cwd(self):
        """Devuelve el directorio de trabajo ideal para Inkscape."""
        if self.actual_bin_path:
            return os.path.dirname(self.actual_bin_path)
        return None

    def start_session(self):
        """Inicia una sesión persistente de Inkscape (--shell) para procesamiento por lotes."""
        if not self.actual_bin_path or hasattr(self, '_session_process'):
            return False
            
        try:
            # Iniciamos inkscape en modo shell
            self._session_process = subprocess.Popen(
                [self.actual_bin_path, "--shell"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1, # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            print("INFO: Sesión persistente de Inkscape iniciada.")
            return True
        except Exception as e:
            print(f"ERROR iniciando sesión de Inkscape: {e}")
            return False

    def stop_session(self):
        """Cierra la sesión persistente de Inkscape."""
        if hasattr(self, '_session_process'):
            try:
                self._session_process.stdin.write("quit\n")
                self._session_process.stdin.flush()
                self._session_process.wait(timeout=5)
            except:
                try: self._session_process.kill()
                except: pass
            del self._session_process
            print("INFO: Sesión de Inkscape finalizada.")

    def convert_batch(self, filepath, output_path, page_number=1, dpi=300, target_size=None, maintain_aspect=True):
        """Ejecuta una conversión dentro de la sesión activa."""
        if not hasattr(self, '_session_process'):
            return False
            
        filepath = os.path.normpath(os.path.abspath(filepath)).replace("\\", "/")
        output_path = os.path.normpath(os.path.abspath(output_path)).replace("\\", "/")
        
        # Construir comando de acción
        # Formato: file-open:path; export-filename:path; export-do;
        actions = f"file-open:{filepath}; "
        
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".pdf", ".ai") and page_number > 1:
            actions += f"select-page:{page_number}; "

        if target_size:
            w, h = target_size
            actions += f"export-width:{w}; "
            if not maintain_aspect:
                actions += f"export-height:{h}; "
        else:
            actions += f"export-dpi:{dpi}; "
            
        actions += "export-background-opacity:0; export-type:png; export-do; "
        
        try:
            self._session_process.stdin.write(actions + "\n")
            self._session_process.stdin.flush()
            
            # Esperamos a que Inkscape termine la acción (imprime '>', el prompt del shell)
            # Nota: Esto es síncrono para este hilo de trabajo.
            while True:
                line = self._session_process.stdout.read(1)
                if not line or line == '>':
                    break
            return True
        except Exception as e:
            print(f"ERROR en batch de Inkscape: {e}")
            return False

    def get_env(self):
        """Devuelve el entorno con las rutas necesarias."""
        env = os.environ.copy()
        if self.base_path:
            # Asegurar que el bin de inkscape esté en el PATH
            bin_dir = os.path.join(self.base_path, "bin")
            if os.path.exists(bin_dir):
                env["PATH"] = f"{bin_dir};{env.get('PATH', '')}"
        return env

    def get_ai_artboard_ids(self, filepath):
        """
        Obtiene los IDs de las mesas de trabajo de un archivo .ai usando Inkscape.
        """
        if not self.actual_bin_path:
            return None
            
        try:
            import re
            cmd = [self.actual_bin_path, filepath, "--query-all"]
            
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            
            if result.returncode != 0:
                return None
                
            stdout = result.stdout.decode('utf-8', errors='ignore')
            artboard_ids = []
            
            # Buscar capas o páginas que representen artboards
            for line in stdout.splitlines():
                parts = line.strip().split(',')
                if len(parts) >= 5:
                    obj_id = parts[0]
                    # Capas MC (Multi-Canvas) de Illustrator
                    if re.match(r'^layer-MC\d+$', obj_id) or re.match(r'^page\d+$', obj_id):
                        num = int(re.search(r'\d+', obj_id).group())
                        artboard_ids.append((num, obj_id))
            
            if artboard_ids:
                artboard_ids.sort()
                return [oid for _, oid in artboard_ids]
                
            return None
        except Exception:
            return None
