import sys
import os
import subprocess
import multiprocessing

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
REQUIREMENTS_FILE = os.path.join(PROJECT_ROOT, "requirements.txt")

def install_dependencies():
    """Instala las dependencias desde requirements.txt si no están presentes."""
    try:
        import customtkinter
        return True
    except ImportError:
        print("Dependencia 'customtkinter' no encontrada. Instalando todas las dependencias...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE])
            print("Dependencias instaladas correctamente.")
            import customtkinter
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"ERROR: No se pudieron instalar las dependencias desde '{REQUIREMENTS_FILE}'.")
            print(f"Detalle del error: {e}")
            try:
                from tkinter import Tk, Label
                root = Tk()
                root.title("Error Crítico")
                Label(root, text=f"No se pudieron instalar las dependencias.\nAsegúrate de que 'requirements.txt' exista y tengas conexión a internet.\n\nError: {e}", padx=20, pady=20).pack()
                root.mainloop()
            except ImportError:
                pass 
            return False

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    if not install_dependencies():
        sys.exit(1)
    if os.path.isdir(BIN_DIR) and BIN_DIR not in os.environ['PATH']:
        os.environ['PATH'] = BIN_DIR + os.pathsep + os.environ['PATH']
    print("Iniciando la aplicación...")
    from src.gui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()