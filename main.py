# main.py

import threading
from src.core.downloader import get_video_info
from src.gui.main_window import MainWindow
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.gui.main_window import MainWindow

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()