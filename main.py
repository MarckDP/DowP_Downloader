import sys
import os
import subprocess
import multiprocessing
import tempfile  
import atexit    
from tkinter import messagebox 

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
FFMPEG_BIN_DIR = os.path.join(BIN_DIR, "ffmpeg")

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
    SingleInstance()
    multiprocessing.freeze_support()
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    # Añadir el directorio 'bin' principal (para Deno, etc.)
    if os.path.isdir(BIN_DIR) and BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = BIN_DIR + os.pathsep + os.environ['PATH']
    
    # Añadir el subdirectorio de FFmpeg
    if os.path.isdir(FFMPEG_BIN_DIR) and FFMPEG_BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = FFMPEG_BIN_DIR + os.pathsep + os.environ['PATH']
        
    print("Iniciando la aplicación...")
    launch_target = sys.argv[1] if len(sys.argv) > 1 else None
    from src.gui.main_window import MainWindow
    app = MainWindow(launch_target=launch_target, project_root=PROJECT_ROOT)
    app.mainloop()