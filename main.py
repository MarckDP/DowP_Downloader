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
        """Comprueba si un proceso con un PID dado está corriendo."""
        if sys.platform == "win32":
            try:
                output = subprocess.check_output(['tasklist', '/fi', f'PID eq {pid}'], 
                                                 stderr=subprocess.STDOUT, text=True, creationflags=0x08000000)
                return str(pid) in output
            except subprocess.CalledProcessError:
                return False
        else: 
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            else:
                return True
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
    if os.path.isdir(BIN_DIR) and BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = BIN_DIR + os.pathsep + os.environ['PATH']
    print("Iniciando la aplicación...")
    launch_target = sys.argv[1] if len(sys.argv) > 1 else None
    from src.gui.main_window import MainWindow
    app = MainWindow(launch_target=launch_target)
    app.mainloop()