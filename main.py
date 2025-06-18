# main.py

import threading
import sys
import os
import subprocess

# Lista de dependencias a verificar
REQUIRED_PACKAGES = [
    "customtkinter",
    "yt_dlp",
    "Pillow",  # CORREGIDO: Usar "Pillow" para la verificación e instalación del paquete.
    "requests"
]

def check_and_install_dependencies():
    """
    Verifica si las dependencias necesarias están instaladas.
    Si alguna no lo está, intenta instalar todas desde requirements.txt.
    """
    missing_packages = []
    # Usaremos un enfoque diferente para verificar Pillow ya que se importa como PIL
    package_imports = {
        "customtkinter": "customtkinter",
        "yt_dlp": "yt_dlp",
        "Pillow": "PIL",  # El paquete es Pillow, pero el módulo a importar es PIL
        "requests": "requests"
    }

    for package_name, import_name in package_imports.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)

    if missing_packages:
        print(f"Las siguientes dependencias no están instaladas: {', '.join(missing_packages)}")
        print("Intentando instalar dependencias desde requirements.txt...")
        try:
            # Asumiendo que requirements.txt está en la misma raíz del proyecto
            requirements_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
            if os.path.exists(requirements_path):
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
                print("Dependencias instaladas exitosamente.")
                # Una vez instaladas, verifica nuevamente para asegurar
                for package_name, import_name in package_imports.items():
                    try:
                        __import__(import_name)
                    except ImportError:
                        print(f"Error: La dependencia '{package_name}' aún no se pudo importar después de la instalación.")
                        sys.exit(1)
            else:
                print(f"Error: No se encontró 'requirements.txt' en {requirements_path}.")
                print("Por favor, asegúrate de que el archivo requirements.txt existe y contiene las dependencias.")
                sys.exit(1) # Salir si no se puede instalar por falta de requirements.txt
        except subprocess.CalledProcessError as e:
            print(f"Error al instalar dependencias: {e}")
            print("Por favor, intenta instalarlas manualmente usando 'pip install -r requirements.txt'")
            sys.exit(1) # Salir si la instalación falla
        except Exception as e:
            print(f"Un error inesperado ocurrió durante la instalación de dependencias: {e}")
            sys.exit(1) # Salir en caso de otros errores inesperados
    else:
        print("Todas las dependencias están instaladas. Continuando con la ejecución.")

# Ejecutar la verificación e instalación al inicio
check_and_install_dependencies()

# Ahora que sabemos que las dependencias están instaladas, importamos la aplicación.
# Estas importaciones deben ir después de la función de verificación.
from src.core.downloader import get_video_info
from src.gui.main_window import MainWindow

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
