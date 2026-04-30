import os
from src.core.davinci_api import importar_a_davinci

class IntegrationManager:
    def __init__(self, main_app):
        self.main_app = main_app

    def broadcast_import(self, source_path, final_path=None, thumb_path=None, bin_name=None, workflow_type="batch"):
        """
        Envía los archivos a las aplicaciones externas activas (Adobe / DaVinci).
        """
        try:
            # 1. Obtener ajustes directamente de MainWindow (Thread-safe para lectura)
            app = self.main_app
            
            # --- Lógica de ADOBE ---
            adobe_enabled = False
            if getattr(app, "adobe_enabled", True):
                if workflow_type == "single":
                    adobe_enabled = getattr(app, "adobe_import_single", True)
                elif workflow_type == "batch":
                    adobe_enabled = getattr(app, "adobe_import_batch", False)
                elif workflow_type == "image":
                    adobe_enabled = getattr(app, "adobe_import_image", False)
            
            if adobe_enabled:
                # Para Adobe, si no hay bin_name, pasamos None para que use su lógica interna (ej. "DowP Importer")
                self._send_to_adobe(final_path or source_path, thumb_path, bin_name)

            # --- Lógica de DAVINCI ---
            davinci_enabled = False
            if getattr(app, "davinci_enabled", True):
                if workflow_type == "single":
                    davinci_enabled = getattr(app, "davinci_import_single", False)
                elif workflow_type == "batch":
                    davinci_enabled = getattr(app, "davinci_import_batch", False)
                elif workflow_type == "image":
                    davinci_enabled = getattr(app, "davinci_import_image", False)
            
            if davinci_enabled:
                # DaVinci sí necesita un nombre por defecto
                dv_bin = bin_name or "DowP Imports"
                files_to_davinci = []
                import_all = getattr(app, "davinci_import_everything", False)
                
                # Si el usuario quiere todo, enviamos original y procesado
                if import_all and source_path and final_path and source_path != final_path:
                    if source_path and os.path.exists(source_path): files_to_davinci.append(source_path)
                    if final_path and os.path.exists(final_path): files_to_davinci.append(final_path)
                else:
                    target = final_path or source_path
                    if target and os.path.exists(target):
                        files_to_davinci.append(target)
                
                if thumb_path and os.path.exists(thumb_path):
                    files_to_davinci.append(thumb_path)
                    
                if files_to_davinci:
                    import threading
                    def run_davinci():
                        try:
                            importar_a_davinci(
                                files_to_davinci, 
                                log_callback=print,
                                import_to_timeline=getattr(app, 'davinci_import_to_timeline', True),
                                bin_name=dv_bin
                            )
                        except Exception as e:
                            print(f"ERROR: Falló la importación a DaVinci: {e}")
                    
                    threading.Thread(target=run_davinci, daemon=True).start()
        except Exception as e:
            print(f"ERROR CRÍTICO en IntegrationManager: {e}")

    def _send_to_adobe(self, file_path, thumb_path, bin_name):
        """Envía el paquete de archivos a Adobe vía SocketIO."""
        if not file_path:
            return

        active_target = self.main_app.ACTIVE_TARGET_SID_accessor()
        if not active_target:
            return

        file_package = {
            "video": str(file_path).replace('\\', '/'),
            "thumbnail": str(thumb_path).replace('\\', '/') if thumb_path else None,
            "subtitle": None
        }
        
        # Solo agregar targetBin si se especificó uno personalizado
        if bin_name:
            file_package["targetBin"] = bin_name
        
        try:
            self.main_app.socketio.emit('new_file', {'filePackage': file_package}, to=active_target)
            print(f"LOG: [Adobe] Enviado: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"ERROR: Falló el envío a Adobe: {e}")

    def broadcast_import_list(self, files, bin_name="DowP Imports", workflow_type="image"):
        """
        Versión para múltiples archivos (principalmente para Image Tools).
        """
        if not bin_name:
            bin_name = "DowP Imports"
            
        try:
            app = self.main_app
            
            # 1. Adobe
            adobe_enabled = False
            if getattr(app, "adobe_enabled", True):
                if workflow_type == "image":
                    adobe_enabled = getattr(app, "adobe_import_image", False)
            
            if adobe_enabled:
                active_target = app.ACTIVE_TARGET_SID_accessor()
                if active_target:
                    import_package = {
                        "files": [f.replace('\\', '/') for f in files],
                        "targetBin": bin_name
                    }
                    try:
                        app.socketio.emit('import_files', import_package, to=active_target)
                        print(f"LOG: [Adobe] Paquete de {len(files)} archivos enviado.")
                    except Exception as e:
                        print(f"ERROR: Falló el envío de lista a Adobe: {e}")

            # 2. DaVinci
            davinci_enabled = False
            if getattr(app, "davinci_enabled", True):
                if workflow_type == "image":
                    davinci_enabled = getattr(app, "davinci_import_image", False)
                
            if davinci_enabled:
                dv_bin = bin_name or "DowP Imports"
                import threading
                def run_davinci():
                    try:
                        importar_a_davinci(
                            files, 
                            log_callback=print,
                            import_to_timeline=getattr(app, 'davinci_import_to_timeline', True),
                            bin_name=dv_bin
                        )
                    except Exception as e:
                        print(f"ERROR: Falló la importación por lote a DaVinci: {e}")
                threading.Thread(target=run_davinci, daemon=True).start()
        except Exception as e:
            print(f"ERROR CRÍTICO en IntegrationManager (List): {e}")
