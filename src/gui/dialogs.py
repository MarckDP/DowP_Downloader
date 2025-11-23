import customtkinter as ctk
import tkinter
import re
import os
import sys
import webbrowser
import subprocess

from tkinter import messagebox

def resource_path(relative_path):
    """Obtiene la ruta absoluta al recurso (para dev y exe)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def apply_icon(window):
    """Aplica el icono a una ventana con un retraso para evitar sobreescritura de CTk."""
    def _set():
        try:
            # Ruta relativa directa, asumiendo que DowP-icon.ico está en la raíz junto a main.py
            # Si usas resource_path, asegúrate de que la ruta sea correcta.
            icon_path = resource_path("DowP-icon.ico") 
            window.iconbitmap(icon_path)
        except Exception:
            pass
        
    window.after(200, _set)

class ConflictDialog(ctk.CTkToplevel):
    def __init__(self, master, filename):
        super().__init__(master)
        self.title("Conflicto de Archivo")
        apply_icon(self)
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()
        self.geometry("500x180")
        self.resizable(False, False)
        self.update_idletasks()
        win_width = 500
        win_height = 180
        master_geo = self.master.geometry()
        master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
        pos_x = master_x + (master_width // 2) - (win_width // 2)
        pos_y = master_y + (master_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        self.result = "cancel"
        main_label = ctk.CTkLabel(self, text=f"El archivo '{filename}' ya existe en la carpeta de destino.", font=ctk.CTkFont(size=14), wraplength=460)
        main_label.pack(pady=(20, 10), padx=20)
        question_label = ctk.CTkLabel(self, text="¿Qué deseas hacer?")
        question_label.pack(pady=5, padx=20)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=15, fill="x", expand=True)
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        overwrite_btn = ctk.CTkButton(button_frame, text="Sobrescribir", command=lambda: self.set_result("overwrite"))
        rename_btn = ctk.CTkButton(button_frame, text="Conservar Ambos", command=lambda: self.set_result("rename"))
        cancel_btn = ctk.CTkButton(button_frame, text="Cancelar", fg_color="red", hover_color="#990000", command=lambda: self.set_result("cancel"))
        overwrite_btn.grid(row=0, column=0, padx=10, sticky="ew")
        rename_btn.grid(row=0, column=1, padx=10, sticky="ew")
        cancel_btn.grid(row=0, column=2, padx=10, sticky="ew")

    def set_result(self, result):
        self.result = result
        self.destroy()

class LoadingWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Iniciando...")
        apply_icon(self)
        self.geometry("350x120")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None) 
        self.transient(master) 
        self.lift()
        self.error_state = False
        win_width = 350
        win_height = 120
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = (screen_width // 2) - (win_width // 2)
        pos_y = (screen_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        self.label = ctk.CTkLabel(self, text="Preparando la aplicación, por favor espera...", wraplength=320)
        self.label.pack(pady=(20, 10), padx=20)
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.grab_set()

class CompromiseDialog(ctk.CTkToplevel):
        """Diálogo que pregunta al usuario si acepta una calidad de descarga alternativa."""
        def __init__(self, master, details_message):
            super().__init__(master)
            self.title("Calidad no Disponible")
            apply_icon(self)
            self.lift()
            self.attributes("-topmost", True)
            self.grab_set()
            self.result = "cancel"
            container = ctk.CTkFrame(self, fg_color="transparent")
            container.pack(padx=20, pady=20, fill="both", expand=True)
            main_label = ctk.CTkLabel(container, text="No se pudo obtener la calidad seleccionada.", font=ctk.CTkFont(size=15, weight="bold"), wraplength=450)
            main_label.pack(pady=(0, 10), anchor="w")
            details_frame = ctk.CTkFrame(container, fg_color="transparent")
            details_frame.pack(pady=5, anchor="w")
            ctk.CTkLabel(details_frame, text="La mejor alternativa disponible es:", font=ctk.CTkFont(size=12)).pack(anchor="w")
            details_label = ctk.CTkLabel(details_frame, text=details_message, font=ctk.CTkFont(size=13, weight="bold"), text_color="#52a2f2", wraplength=450, justify="left")
            details_label.pack(anchor="w")
            question_label = ctk.CTkLabel(container, text="¿Deseas descargar esta versión en su lugar?", font=ctk.CTkFont(size=12), wraplength=450)
            question_label.pack(pady=10, anchor="w")
            button_frame = ctk.CTkFrame(container, fg_color="transparent")
            button_frame.pack(pady=15, fill="x")
            button_frame.grid_columnconfigure((0, 1), weight=1)
            accept_btn = ctk.CTkButton(button_frame, text="Sí, Descargar", command=lambda: self.set_result("accept"))
            cancel_btn = ctk.CTkButton(button_frame, text="No, Cancelar", fg_color="red", hover_color="#990000", command=lambda: self.set_result("cancel"))
            accept_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
            cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")
            self.update()
            self.update_idletasks()
            win_width = self.winfo_reqwidth()
            win_height = self.winfo_reqheight()
            master_geo = self.master.geometry()
            master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
            pos_x = master_x + (master_width // 2) - (win_width // 2)
            pos_y = master_y + (master_height // 2) - (win_height // 2)
            self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

        def set_result(self, result):
            self.result = result
            self.destroy()

class SimpleMessageDialog(ctk.CTkToplevel):
    """Un diálogo para mostrar mensajes de error permitiendo copiar el texto."""
    def __init__(self, master, title, message):
        super().__init__(master)
        self.title(title)
        apply_icon(self)
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()
        
        # Guardamos el mensaje para el botón de copiar
        self.message_text = message

        # Dimensiones un poco más grandes para acomodar el log
        win_width = 500
        win_height = 300
        
        # Centrar ventana
        self.resizable(True, True) # Permitir redimensionar para leer mejor
        self.update_idletasks()
        master_geo = self.master.geometry()
        master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
        pos_x = master_x + (master_width // 2) - (win_width // 2)
        pos_y = master_y + (master_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

        # --- CAMBIO PRINCIPAL: Usar CTkTextbox en lugar de Label ---
        # Esto permite seleccionar texto y tener scroll automático
        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(size=13), wrap="word")
        self.textbox.pack(padx=20, pady=(20, 10), fill="both", expand=True)
        
        # Insertar el texto y deshabilitar edición (modo solo lectura)
        self.textbox.insert("0.0", message)
        self.textbox.configure(state="disabled")

        # --- Botones ---
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=(0, 20), fill="x")
        
        # Botón Copiar
        copy_button = ctk.CTkButton(
            button_frame, 
            text="Copiar Error", 
            fg_color="gray", 
            hover_color="#555555",
            command=self.copy_to_clipboard
        )
        copy_button.pack(side="left", expand=True, padx=(0, 5))

        # Botón OK
        ok_button = ctk.CTkButton(
            button_frame, 
            text="OK", 
            command=self.destroy
        )
        ok_button.pack(side="left", expand=True, padx=(5, 0))

    def copy_to_clipboard(self):
        """Copia el contenido del mensaje al portapapeles."""
        self.clipboard_clear()
        self.clipboard_append(self.message_text)
        self.update() # Necesario para asegurar que el portapapeles se actualice
        
        # Feedback visual temporal en el botón (opcional pero agradable)
        original_text = "Copiar Error"
        self.children['!ctkframe'].children['!ctkbutton'].configure(text="¡Copiado!")
        self.after(1000, lambda: self.children['!ctkframe'].children['!ctkbutton'].configure(text=original_text))

class SavePresetDialog(ctk.CTkToplevel):
        """Diálogo para guardar un preset con nombre personalizado."""
        def __init__(self, master):
            super().__init__(master)
            self.title("Guardar ajuste prestablecido")
            apply_icon(self)
            self.lift()
            self.attributes("-topmost", True)
            self.grab_set()
            self.result = None
            
            self.geometry("450x200")
            self.resizable(False, False)
            
            self.update_idletasks()
            win_width = 450
            win_height = 200
            master_geo = self.master.geometry()
            master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
            pos_x = master_x + (master_width // 2) - (win_width // 2)
            pos_y = master_y + (master_height // 2) - (win_height // 2)
            self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
            
            label = ctk.CTkLabel(
                self, 
                text="Nombre del ajuste prestablecido:",
                font=ctk.CTkFont(size=13)
            )
            label.pack(pady=(20, 10), padx=20)
            
            self.name_entry = ctk.CTkEntry(
                self,
                placeholder_text="Ej: Mi ProRes Personal"
            )
            self.name_entry.pack(pady=10, padx=20, fill="x")
            self.name_entry.focus()
            
            self.name_entry.bind("<Return>", lambda e: self.save())
            
            button_frame = ctk.CTkFrame(self, fg_color="transparent")
            button_frame.pack(pady=15, padx=20, fill="x")
            button_frame.grid_columnconfigure((0, 1), weight=1)
            
            save_btn = ctk.CTkButton(
                button_frame, 
                text="Guardar",
                command=self.save
            )
            save_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
            
            cancel_btn = ctk.CTkButton(
                button_frame,
                text="Cancelar",
                fg_color="gray",
                hover_color="#555555",
                command=self.cancel
            )
            cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        def save(self):
            preset_name = self.name_entry.get().strip()
            if preset_name:
                self.result = preset_name
                self.destroy()
            else:
                messagebox.showwarning("Nombre vacío", "Por favor, ingresa un nombre para el ajuste.")
        
        def cancel(self):
            self.result = None
            self.destroy()

class PlaylistErrorDialog(ctk.CTkToplevel):
    """Diálogo que pregunta qué hacer con un ítem de playlist que falló."""
    def __init__(self, master, url_fragment):
        super().__init__(master)
        self.title("Error de Playlist")
        apply_icon(self)
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()
        self.result = "cancel" # Default
        
        # --- Centrar ventana ---
        self.geometry("500x200")
        self.resizable(False, False)
        self.update_idletasks()
        win_width = 500
        win_height = self.winfo_reqheight() # Ajustar altura al contenido
        master_geo = self.master.geometry()
        master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
        pos_x = master_x + (master_width // 2) - (win_width // 2)
        pos_y = master_y + (master_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(padx=20, pady=20, fill="both", expand=True)
        
        main_label = ctk.CTkLabel(container, text="Se detectó un problema de colección.", font=ctk.CTkFont(size=15, weight="bold"), wraplength=460)
        main_label.pack(pady=(0, 10), anchor="w")
        
        # Mostrar solo una parte de la URL
        display_url = (url_fragment[:70] + '...') if len(url_fragment) > 70 else url_fragment
        
        details_label = ctk.CTkLabel(container, text=f"La URL '{display_url}' parece ser parte de una colección (playlist, set, o hilo) que no se puede descargar en modo individual.", font=ctk.CTkFont(size=13), wraplength=460, justify="left")
        details_label.pack(pady=5, anchor="w")
        
        question_label = ctk.CTkLabel(container, text="¿Qué deseas hacer?", font=ctk.CTkFont(size=12), wraplength=450)
        question_label.pack(pady=10, anchor="w")
        
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(pady=15, fill="x")
        button_frame.grid_columnconfigure((0, 1), weight=1)
        
        accept_btn = ctk.CTkButton(button_frame, text="Enviar a Lotes", command=lambda: self.set_result("send_to_batch"))
        cancel_btn = ctk.CTkButton(button_frame, text="Cancelar", fg_color="red", hover_color="#990000", command=lambda: self.set_result("cancel"))
        
        accept_btn.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # Ajustar altura de nuevo después de añadir widgets
        self.update_idletasks()
        win_height = self.winfo_reqheight()
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

    def set_result(self, result):
        self.result = result
        self.destroy()

class Tooltip:
    """
    Crea un tooltip emergente.
    CORREGIDO v2: Robusto para Multi-Monitor, DPI Scaling y Coordenadas Negativas.
    Usa la geometría de la ventana principal como referencia segura.
    """
    def __init__(self, widget, text, delay_ms=500, wraplength=300):
        self.widget = widget
        self.text = text
        self.delay = delay_ms
        self.wraplength = wraplength
        self.tooltip_window = None
        self.timer_id = None

        # Vincular eventos
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)
        self.widget.bind("<ButtonPress>", self.on_leave)

    def on_enter(self, event=None):
        self.schedule_tooltip()

    def on_leave(self, event=None):
        self.hide_tooltip()

    def schedule_tooltip(self):
        self.cancel_timer()
        self.timer_id = self.widget.after(self.delay, self.show_tooltip)

    def cancel_timer(self):
        if self.timer_id:
            self.widget.after_cancel(self.timer_id)
            self.timer_id = None

    def show_tooltip(self):
        if self.tooltip_window and self.tooltip_window.winfo_exists():
            return

        # Colores (Tema Oscuro)
        bg_color = "#1a1a1a"
        fg_color = "#e0e0e0"
        border_color = "#404040"

        # 1. Crear ventana (Oculta)
        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.withdraw() 
        self.tooltip_window.overrideredirect(True)
        self.tooltip_window.attributes("-topmost", True)

        # 2. Contenido
        frame = ctk.CTkFrame(
            self.tooltip_window,
            fg_color=bg_color,
            border_width=1,
            border_color=border_color,
            corner_radius=4
        )
        frame.pack()

        label = ctk.CTkLabel(
            frame,
            text=self.text,
            fg_color="transparent",
            text_color=fg_color,
            font=ctk.CTkFont(size=12),
            wraplength=self.wraplength,
            justify="left",
            padx=8, 
            pady=4
        )
        label.pack()

        # 3. Calcular dimensiones del tooltip
        frame.update_idletasks()
        tip_w = frame.winfo_reqwidth()
        tip_h = frame.winfo_reqheight()

        # 4. Calcular Posición Inteligente (Relativa a la Ventana Principal)
        try:
            # Posición absoluta del mouse
            mouse_x = self.widget.winfo_pointerx()
            mouse_y = self.widget.winfo_pointery()

            # Información de la ventana "Madre" (DowP)
            # Esto nos da los límites seguros donde el usuario está mirando
            root = self.widget.winfo_toplevel()
            root_x = root.winfo_rootx()
            root_y = root.winfo_rooty()
            root_w = root.winfo_width()
            root_h = root.winfo_height()

            # Offsets iniciales
            offset_x = 15
            offset_y = 10

            # Cálculo tentativo (Abajo-Derecha)
            x = mouse_x + offset_x
            y = mouse_y + offset_y

            # LÓGICA DE REBOTE (Flip Logic)
            # Si el tooltip se sale por la derecha de la ventana de DowP...
            if (x + tip_w) > (root_x + root_w):
                # ... lo ponemos a la izquierda del cursor
                x = mouse_x - tip_w - offset_x
            
            # Si el tooltip se sale por abajo de la ventana de DowP...
            # (Añadimos un margen de 50px extra porque la barra de tareas suele estar abajo)
            if (y + tip_h) > (root_y + root_h + 50): 
                # ... lo ponemos arriba del cursor
                y = mouse_y - tip_h - offset_y

            # 5. Aplicar (Sin clamping forzado a 0 para soportar monitores a la izquierda)
            self.tooltip_window.geometry(f"{tip_w}x{tip_h}+{x}+{y}")
            self.tooltip_window.deiconify()
            
        except Exception as e:
            print(f"Error mostrando tooltip: {e}")
            if self.tooltip_window:
                self.tooltip_window.destroy()
                self.tooltip_window = None

    def hide_tooltip(self):
        self.cancel_timer()
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

class CTkColorPicker(ctk.CTkToplevel):
    """
    Diálogo emergente para seleccionar un color.
    (Basado en el widget de utilidad oficial de CustomTkinter)
    """
    def __init__(self,
                 master=None,
                 width: int = 430,
                 height: int = 320,
                 title: str = "Color Picker",
                 initial_color: str = "#FFFFFF",
                 command=None):
        
        super().__init__(master=master)
        
        self.title(title)
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()
        self.resizable(False, False)
        self.geometry(f"{width}x{height}")
        
        self.command = command
        self._hex_color = initial_color
        self._rgb_color = self._hex_to_rgb(initial_color)

        # --- Frames ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.slider_frame = ctk.CTkFrame(self.main_frame)
        self.slider_frame.pack(fill="x", pady=(0, 10))

        self.preview_frame = ctk.CTkFrame(self.main_frame)
        self.preview_frame.pack(fill="x")

        # --- Sliders ---
        self.r_slider = self._create_slider("R:", (0, 255), self.slider_frame)
        self.g_slider = self._create_slider("G:", (0, 255), self.slider_frame)
        self.b_slider = self._create_slider("B:", (0, 255), self.slider_frame)

        # --- Vista Previa y Entradas ---
        self.preview_box = ctk.CTkFrame(self.preview_frame, height=50, border_width=2)
        self.preview_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.hex_entry = ctk.CTkEntry(self.preview_frame, width=100)
        self.hex_entry.pack(side="left")
        
        self.ok_button = ctk.CTkButton(self.main_frame, text="OK", command=self._ok_event)
        self.ok_button.pack(side="bottom", fill="x", pady=(10, 0))

        # Bindings
        self.r_slider.bind("<ButtonRelease-1>", self._update_from_sliders)
        self.g_slider.bind("<ButtonRelease-1>", self._update_from_sliders)
        self.b_slider.bind("<ButtonRelease-1>", self._update_from_sliders)
        self.hex_entry.bind("<Return>", self._update_from_hex)

        # Estado inicial
        self._update_ui_from_rgb(self._rgb_color)
        self.after(10, self.hex_entry.focus) # Dar foco al entry

    def _create_slider(self, text, range_, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=5, pady=5)
        
        label = ctk.CTkLabel(frame, text=text, width=20)
        label.pack(side="left")
        
        slider = ctk.CTkSlider(frame, from_=range_[0], to=range_[1], number_of_steps=range_[1])
        slider.pack(side="left", fill="x", expand=True, padx=10)
        
        return slider

    def _hex_to_rgb(self, hex_color):
        hex_clean = hex_color.lstrip('#')
        return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(self, rgb_color):
        r, g, b = rgb_color
        return f"#{r:02x}{g:02x}{b:02x}".upper()

    def _update_ui_from_rgb(self, rgb_color):
        r, g, b = rgb_color
        
        self._hex_color = self._rgb_to_hex(rgb_color)
        
        self.r_slider.set(r)
        self.g_slider.set(g)
        self.b_slider.set(b)
        
        self.hex_entry.delete(0, "end")
        self.hex_entry.insert(0, self._hex_color)
        
        self.preview_box.configure(fg_color=self._hex_color)

    def _update_from_sliders(self, event=None):
        r = int(self.r_slider.get())
        g = int(self.g_slider.get())
        b = int(self.b_slider.get())
        
        self._rgb_color = (r, g, b)
        self._update_ui_from_rgb(self._rgb_color)

    def _update_from_hex(self, event=None):
        hex_str = self.hex_entry.get()
        try:
            self._rgb_color = self._hex_to_rgb(hex_str)
            self._update_ui_from_rgb(self._rgb_color)
        except Exception:
            # Si el color es inválido, resetea al color anterior
            self.hex_entry.delete(0, "end")
            self.hex_entry.insert(0, self._hex_color)

    def _ok_event(self, event=None):
        self._update_from_hex() # Asegura que el color del entry se aplique
        
        if self.command:
            self.command(self._hex_color)
        
        self.grab_release()
        self.destroy()

    def get(self):
        self.master.wait_window(self)
        return self._hex_color

class MultiPageDialog(ctk.CTkToplevel):
    """
    Diálogo que pregunta al usuario qué páginas de un documento
    de múltiples páginas desea importar.
    """
    def __init__(self, master, filename, page_count):
        super().__init__(master)
        self.title("Documento de Múltiples Páginas")
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()
        
        self.result = None # Aquí guardaremos el string del rango

        win_width = 450
        win_height = 270
        
        # Centrar la ventana (código de tus otros diálogos)
        self.resizable(False, False)
        self.update_idletasks()
        
        master_geo = self.master.app.geometry() 
        
        master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
        pos_x = master_x + (master_width // 2) - (win_width // 2)
        pos_y = master_y + (master_height // 2) - (win_height // 2)
        self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(padx=20, pady=20, fill="both", expand=True)

        label_info = ctk.CTkLabel(container, text=f"El archivo '{filename}' contiene {page_count} páginas.", 
                                  font=ctk.CTkFont(size=14),
                                  wraplength=410, # <-- Añadir esta línea (450 - 40 de padding)
                                  justify="left") # <-- Añadir esta línea
        label_info.pack(pady=(0, 10), anchor="w")

        label_prompt = ctk.CTkLabel(container, text="¿Qué páginas deseas importar?", font=ctk.CTkFont(size=13, weight="bold"))
        label_prompt.pack(pady=(5, 5), anchor="w")

        self.range_entry = ctk.CTkEntry(container, placeholder_text="Ej: 1-5, 8, 11-15")
        self.range_entry.pack(fill="x", pady=5)
        self.range_entry.focus() # Dar foco al campo de texto
        self.range_entry.bind("<Return>", lambda e: self.set_result(self.range_entry.get()))
        
        label_example = ctk.CTkLabel(container, text="Separa rangos o páginas con comas.", text_color="gray", font=ctk.CTkFont(size=11))
        label_example.pack(anchor="w", padx=5)

        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(pady=15, fill="x", side="bottom")
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)

        btn_first = ctk.CTkButton(button_frame, text="Solo Pág. 1", command=lambda: self.set_result("1"))
        btn_first.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        btn_all = ctk.CTkButton(button_frame, text=f"Todas ({page_count})", command=lambda: self.set_result(f"1-{page_count}"))
        btn_all.grid(row=0, column=1, padx=5, sticky="ew")

        # Usar los colores del botón de proceso de la app principal
        btn_accept = ctk.CTkButton(button_frame, text="Aceptar Rango", 
                                  command=lambda: self.set_result(self.range_entry.get()),
                                  fg_color="#6F42C1", hover_color="#59369A")
        btn_accept.grid(row=0, column=2, padx=(5, 0), sticky="ew")

    def set_result(self, range_string):
        if not range_string.strip():
            messagebox.showwarning("Rango vacío", "Por favor, especifica un rango (ej: '1-5') o usa los botones.", parent=self)
            return
            
        self.result = range_string.strip()
        self.destroy()

    def get_result(self):
        """Espera a que el diálogo se cierre y devuelve el resultado."""
        self.master.wait_window(self)
        return self.result
    
class ManualDownloadDialog(ctk.CTkToplevel):
    """
    Diálogo para guiar al usuario en la descarga manual de modelos con licencia restrictiva.
    """
    def __init__(self, master, model_info, target_dir, filename, on_success_callback=None):
        super().__init__(master)
        self.title("Descarga Manual Requerida")
        apply_icon(self)  # <--- APLICA EL ICONO DEL PROGRAMA
        
        self.model_info = model_info
        self.target_dir = target_dir
        self.filename = filename
        self.on_success_callback = on_success_callback

        # Asegurar que la carpeta exista
        os.makedirs(target_dir, exist_ok=True)

        self.geometry("500x380")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set() # Hace el diálogo modal

        # Centrar ventana
        self.update_idletasks()
        # Usamos la geometría del master para centrar
        try:
            master_x = master.winfo_rootx()
            master_y = master.winfo_rooty()
            master_w = master.winfo_width()
            master_h = master.winfo_height()
            
            x = master_x + (master_w // 2) - (500 // 2)
            y = master_y + (master_h // 2) - (380 // 2)
            self.geometry(f"+{x}+{y}")
        except:
            # Fallback si falla el cálculo
            self.geometry("500x380")

        # --- Contenido UI ---
        ctk.CTkLabel(self, text="⚠️ Este modelo requiere descarga manual", 
                     font=ctk.CTkFont(size=16, weight="bold"), 
                     text_color="orange").pack(pady=(15, 5))
        
        msg = (
            f"El modelo '{filename}' pertenece a BriaAI y requiere licencia.\n"
            "Por razones legales, DowP no puede descargarlo automáticamente.\n\n"
            "PASOS PARA INSTALARLO:"
        )
        ctk.CTkLabel(self, text=msg, justify="center").pack(pady=5, padx=20)
        
        # Lista de pasos
        steps_frame = ctk.CTkFrame(self, fg_color="transparent")
        steps_frame.pack(fill="x", padx=30, pady=5)
        
        ctk.CTkLabel(steps_frame, text="1. Crea una cuenta e inicia sesión en HuggingFace.", anchor="w").pack(fill="x")
        ctk.CTkLabel(steps_frame, text="2. Ve al enlace y acepta los términos de uso.", anchor="w").pack(fill="x")
        ctk.CTkLabel(steps_frame, text=f"3. Descarga el archivo: {filename}", anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x")
        ctk.CTkLabel(steps_frame, text="4. Pégalo en la carpeta que se abrirá a continuación.", anchor="w").pack(fill="x")

        # Botón Enlace
        url = model_info["url"]
        link_btn = ctk.CTkButton(self, text="🌐 Ir a HuggingFace (Descargar)", command=lambda: webbrowser.open(url))
        link_btn.pack(pady=10)

        # Botón Carpeta
        folder_btn = ctk.CTkButton(self, text="📂 Abrir Carpeta de Destino", 
                                   fg_color="#555555", hover_color="#444444", 
                                   command=self.open_target_folder)
        folder_btn.pack(pady=5)

        # Botón Confirmar
        ctk.CTkButton(self, text="Listo, ya lo pegué", 
                      fg_color="green", hover_color="darkgreen", 
                      command=self.check_and_close).pack(pady=(15, 10))

    def open_target_folder(self):
        try:
            if os.name == 'nt':
                os.startfile(self.target_dir)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.target_dir])
            else:
                subprocess.Popen(['xdg-open', self.target_dir])
        except Exception as e:
            print(f"Error abriendo carpeta: {e}")

    def check_and_close(self):
        """Verifica si el archivo existe. Si sí, ejecuta el callback de éxito."""
        target_file = os.path.join(self.target_dir, self.filename)
        
        if os.path.exists(target_file) and os.path.getsize(target_file) > 1024:
            # Éxito
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        else:
            # Fallo (no se encontró)
            # Solo cerramos, el usuario verá el estado "No instalado" en la UI principal
            self.destroy()