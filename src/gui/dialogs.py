import customtkinter as ctk
import tkinter
import re
from tkinter import messagebox

class ConflictDialog(ctk.CTkToplevel):
    def __init__(self, master, filename):
        super().__init__(master)
        self.title("Conflicto de Archivo")
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
        """Un diálogo simple para mostrar un mensaje de error o información."""
        def __init__(self, master, title, message):
            super().__init__(master)
            self.title(title)
            self.lift()
            self.attributes("-topmost", True)
            self.grab_set()
            self.resizable(False, False)
            message_label = ctk.CTkLabel(self, text=message, font=ctk.CTkFont(size=13), wraplength=450, justify="left")
            message_label.pack(padx=20, pady=20, fill="both", expand=True)
            ok_button = ctk.CTkButton(self, text="OK", command=self.destroy, width=100)
            ok_button.pack(padx=20, pady=(0, 20))
            self.update()
            win_width = self.winfo_reqwidth()
            win_height = self.winfo_reqheight()
            master_geo = self.master.geometry()
            master_width, master_height, master_x, master_y = map(int, re.split('[x+]', master_geo))
            pos_x = master_x + (master_width // 2) - (win_width // 2)
            pos_y = master_y + (master_height // 2) - (win_height // 2)
            self.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

class SavePresetDialog(ctk.CTkToplevel):
        """Diálogo para guardar un preset con nombre personalizado."""
        def __init__(self, master):
            super().__init__(master)
            self.title("Guardar ajuste prestablecido")
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
