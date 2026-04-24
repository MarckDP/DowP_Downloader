import os
import io
import re
import subprocess
import tempfile
from PIL import Image, ImageChops

class HideCmdWindow:
    """
    Context Manager que fuerza a todos los subprocesos (Popen) creados dentro
    de su bloque a ejecutarse sin ventana (CREATE_NO_WINDOW) en Windows.
    """
    def __enter__(self):
        if os.name == 'nt':
            self._orig_popen = subprocess.Popen
            def new_popen(*args, **kwargs):
                # 0x08000000 es el flag CREATE_NO_WINDOW
                kwargs.setdefault('creationflags', 0x08000000)
                return self._orig_popen(*args, **kwargs)
            subprocess.Popen = new_popen
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.name == 'nt':
            subprocess.Popen = self._orig_popen

# Import conversion libraries
try:
    import cairosvg
    CAN_SVG = True
except ImportError:
    CAN_SVG = False
    print("ADVERTENCIA: 'cairosvg' no instalado. No se podrán previsualizar archivos .svg")

try:
    from pdf2image import convert_from_path, pdfinfo_from_path
    CAN_PDF = True
except ImportError:
    CAN_PDF = False
    print("ADVERTENCIA: 'pdf2image' no instalado. No se podrán previsualizar archivos .pdf, .ai, .eps")

# Import format constants
from src.core.constants import (
    IMAGE_RASTER_FORMATS, IMAGE_INPUT_FORMATS, IMAGE_RAW_FORMATS
)

# Convert sets to tuples for .endswith()
RASTER_EXT = tuple(f.lower() for f in IMAGE_RASTER_FORMATS)
VECTOR_EXT = tuple(f.lower() for f in IMAGE_INPUT_FORMATS)

class ImageProcessor:
    def __init__(self, poppler_path=None, inkscape_service=None, ffmpeg_path=None):
        self.poppler_path = poppler_path
        self.inkscape_service = inkscape_service
        self.ffmpeg_path = ffmpeg_path
        
        # ✅ NUEVO: Caché para almacenar el conteo de páginas y evitar bloqueos
        self._page_count_cache = {}
        
        if CAN_PDF and self.poppler_path:
            print(f"INFO: ImageProcessor usará Poppler desde: {self.poppler_path}")
            
        # ✅ NUEVO: Detectar Ghostscript para EPS transparentes
        self.gs_exe = self._find_ghostscript()
        if self.gs_exe:
            print(f"INFO: ImageProcessor usará Ghostscript desde: {self.gs_exe}")
        
        if self.inkscape_service:
            print(f"INFO: ImageProcessor usará Inkscape Service")
        else:
            print("INFO: Inkscape no habilitado. Usando motores nativos.")

    def _command_exists(self, cmd):
        """Verifica si un comando está disponible en el PATH."""
        import shutil
        return shutil.which(cmd) is not None

    def _fix_svg_attributes(self, svg_path):
        """
        Lee un SVG y corrige atributos width/height inválidos.
        """
        try:
            import tempfile
            
            with open(svg_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
            
            svg_tag_pattern = r'<svg([^>]*)>'
            match = re.search(svg_tag_pattern, svg_content, re.IGNORECASE)
            
            if not match:
                return None
            
            svg_attributes = match.group(1)
            needs_fix = False
            fixed_attributes = svg_attributes
            
            simple_patterns = [
                (r'width\s*=\s*"px"', 'width="180"'),
                (r'width\s*=\s*""', 'width="180"'),
                (r'width\s*=\s*"\s*px\s*"', 'width="180"'),
                (r'height\s*=\s*"px"', 'height="180"'),
                (r'height\s*=\s*""', 'height="180"'),
                (r'height\s*=\s*"\s*px\s*"', 'height="180"'),
            ]
            
            for pattern, replacement in simple_patterns:
                if re.search(pattern, fixed_attributes, re.IGNORECASE):
                    fixed_attributes = re.sub(pattern, replacement, fixed_attributes, flags=re.IGNORECASE)
                    needs_fix = True
            
            def clean_px_width(match):
                value = match.group(0).split('"')[1]
                value_clean = value.replace('px', '').strip()
                return f'width="{value_clean}"'
            
            def clean_px_height(match):
                value = match.group(0).split('"')[1]
                value_clean = value.replace('px', '').strip()
                return f'height="{value_clean}"'
            
            if re.search(r'width\s*=\s*"\d+px"', fixed_attributes, re.IGNORECASE):
                fixed_attributes = re.sub(r'width\s*=\s*"\d+px"', clean_px_width, fixed_attributes, flags=re.IGNORECASE)
                needs_fix = True
            
            if re.search(r'height\s*=\s*"\d+px"', fixed_attributes, re.IGNORECASE):
                fixed_attributes = re.sub(r'height\s*=\s*"\d+px"', clean_px_height, fixed_attributes, flags=re.IGNORECASE)
                needs_fix = True
            
            if not needs_fix:
                return None
            
            fixed_svg_content = re.sub(
                svg_tag_pattern, 
                f'<svg{fixed_attributes}>', 
                svg_content, 
                count=1, 
                flags=re.IGNORECASE
            )
            
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False, encoding='utf-8')
            temp_file.write(fixed_svg_content)
            temp_file.close()
            
            print(f"DEBUG: SVG corregido guardado en: {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo preprocesar el SVG: {e}")
            return None

    def get_document_page_count(self, filepath):
        """
        Obtiene el número de páginas de un documento con caché para evitar bloqueos.
        """
        # ✅ 1. Verificar caché primero (Operación O(1) instantánea)
        if filepath in self._page_count_cache:
            return self._page_count_cache[filepath]

        ext = os.path.splitext(filepath)[1].lower()
        count = 1  # Valor por defecto

        try:
            # --- CASO 1: Archivos PDF (Usar Poppler) ---
            if ext == ".pdf":
                try:
                    # ✅ ENVOLVER CON HideCmdWindow
                    with HideCmdWindow():
                        info = pdfinfo_from_path(filepath, poppler_path=self.poppler_path)
                    count = int(info.get('Pages', 1))
                except Exception as e:
                    print(f"ADVERTENCIA: Poppler falló leyendo PDF {filepath}: {e}")
                    count = 1

            # --- CASO 2: Archivos EPS, AI, PS (Leer cabecera PostScript) ---
            elif ext in (".eps", ".ai", ".ps"):
                try:
                    with open(filepath, 'rb') as f:
                        header = f.read(4096).decode('latin-1', errors='ignore')
                        
                        # Buscar patrón "%%Pages: (número)"
                        match = re.search(r'%%Pages:\s*(\d+)', header)
                        if match:
                            count = max(1, int(match.group(1)))
                            
                        # Si es un .ai moderno (PDF), intentar Poppler si la cabecera falla o es ambigua
                        if ext == ".ai" and b"%PDF" in header.encode('latin-1'):
                            try:
                                # ✅ ENVOLVER CON HideCmdWindow
                                with HideCmdWindow():
                                    info = pdfinfo_from_path(filepath, poppler_path=self.poppler_path)
                                count = int(info.get('Pages', 1))
                                print(f"DEBUG: Archivo .ai detectado como PDF con {count} página(s)")
                            except Exception as e:
                                print(f"DEBUG: .ai no pudo leerse como PDF: {e}")
                                # Mantener el count que teníamos o 1
                                pass

                except Exception as e:
                    print(f"DEBUG: No se pudo leer cabecera EPS/AI de {filepath}: {e}")
                    count = 1
            
            # ✅ 2. Guardar en caché antes de retornar
            self._page_count_cache[filepath] = count
            return count

        except Exception as e:
            print(f"ERROR CRÍTICO obteniendo páginas: {e}")
            return 1

    def generate_thumbnail(self, filepath, size=(400, 400), page_number=None, dpi=None):
        """
        Genera una miniatura (PIL.Image) para un archivo.
        OPTIMIZADO: Prioriza velocidad sobre calidad.
        """
        original_path = os.environ.get('PATH', '')
        print(f"DEBUG: [Thumb] Iniciando generación para: {os.path.basename(filepath)} (Size: {size}, Page: {page_number}, DPI: {dpi})")

        try:
            ext = os.path.splitext(filepath)[1].lower()
            pil_image = None

            # ===== NUEVO: RAW DE CÁMARA (RAWPY) =====
            if ext.upper() in IMAGE_RAW_FORMATS:
                try:
                    import rawpy
                    import numpy as np
                    
                    with rawpy.imread(filepath) as raw:
                        try:
                            # 🚀 ESTRATEGIA PRO: Extraer la miniatura incrustada
                            thumb = raw.extract_thumb()
                            
                            if thumb.format == rawpy.ThumbFormat.JPEG:
                                pil_image = Image.open(io.BytesIO(thumb.data))
                            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                                pil_image = Image.fromarray(thumb.data)
                            
                            print(f"DEBUG: [RAW] Miniatura extraída: {pil_image.size}, Formato: {thumb.format}")
                            
                            # 🔍 VALIDACIÓN DE TAMAÑO:
                            if pil_image and (max(pil_image.size) < 800):
                                print(f"DEBUG: [RAW] Miniatura demasiado pequeña ({pil_image.size}), forzando revelado.")
                                raise Exception("Miniatura demasiado pequeña")
                                
                            print(f"DEBUG: [RAW] Miniatura validada exitosamente: {pil_image.size}")
                                
                        except Exception:
                            # 🔄 FALLBACK: Revelado de mayor calidad para previsualización
                            print(f"DEBUG: [RAW] Realizando revelado de alta calidad para {os.path.basename(filepath)}...")
                            rgb = raw.postprocess(
                                use_camera_wb=True,
                                half_size=False,         # 🎨 CALIDAD: Resolución completa
                                no_auto_bright=False,
                                output_bps=8,
                                output_color=rawpy.ColorSpace.sRGB,
                                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD
                            )
                            pil_image = Image.fromarray(rgb)
                            print(f"DEBUG: [RAW] Revelado finalizado. Tamaño: {pil_image.size}")
                    
                    
                    # Aplicar rotación EXIF si existe
                    try:
                        from PIL import ImageOps
                        pil_image = ImageOps.exif_transpose(pil_image)
                        print(f"DEBUG: [RAW] Tras rotación EXIF: {pil_image.size}")
                    except Exception as e:
                        print(f"DEBUG: [RAW] Error en rotación: {e}")
                        pass
                    
                except ImportError:
                    print("⚠️ rawpy no instalado. Ejecuta: pip install rawpy")
                    pil_image = None
                except Exception as e:
                    print(f"❌ ERROR al revelar RAW: {e}")
                    pil_image = None

            # ===== RASTER: Carga directa (RÁPIDO) =====
            elif ext in RASTER_EXT: 
                print(f"DEBUG: [Thumb] Procesando como RASTER: {ext}")
                pil_image = Image.open(filepath)
            
            # ===== VECTORIAL: Poppler / CairoSVG / Inkscape (Centralizado) =====
            elif ext in VECTOR_EXT:
                print(f"DEBUG: [Thumb] Procesando como VECTORIAL: {ext}")
                pil_image = self._generate_vector_thumbnail(filepath, size, page_number, dpi=dpi)

            # ===== Fallback General (Raster, JP2, BMP, etc) =====
            else:
                try:
                    print(f"DEBUG: [Thumb] Procesando como RASTER/FALLBACK: {ext}")
                    # Image.open es "lazy" (no lee datos), hay que llamar a load() para detectar corrupción
                    temp_img = Image.open(filepath)
                    temp_img.load() # <--- AQUÍ es donde salta el error de "broken data stream"
                    pil_image = temp_img
                except OSError as e:
                    # Capturar errores de archivos corruptos (ej. el JP2 roto)
                    print(f"ADVERTENCIA: [Thumb] Archivo corrupto o ilegible '{os.path.basename(filepath)}': {e}")
                    return None # Retornar None para que la UI muestre el icono de error ❌
                except Exception as e:
                    # Otros errores
                    print(f"ADVERTENCIA: [Thumb] Formato no soportado o error desconocido en '{filepath}': {e}")
                    return None

            if not pil_image:
                print(f"DEBUG: [Thumb] ❌ Falló la carga de imagen para {os.path.basename(filepath)}")
                return None

            if pil_image.mode != "RGBA":
                pil_image = pil_image.convert("RGBA")

            # ❌ CORRECCIÓN FINAL: No aplicar thumbnail destructivo a los RAW o Previews Vectoriales Grandes.
            # Queremos que el visor reciba la resolución completa para permitir Zoom fluido.
            ext_upper = ext.upper() if 'ext' in locals() else ""
            is_large_preview = max(size) > 500
            
            if ext_upper in IMAGE_RAW_FORMATS:
                print(f"DEBUG: [RAW] Saltando thumbnail final para mantener resolución: {pil_image.size}")
            elif ext in VECTOR_EXT and is_large_preview:
                print(f"DEBUG: [Thumb] Saltando thumbnail final para Vector (Preview HD): {pil_image.size}")
            else:
                # Solo para iconos pequeños de la lista o archivos raster normales
                pil_image.thumbnail(size, Image.Resampling.LANCZOS)
                
            print(f"DEBUG: [Thumb] ✅ Miniatura generada exitosamente ({pil_image.size})")
            return pil_image

        except Exception as e:
            print(f"ERROR: No se pudo generar miniatura para {filepath}")
            return None

    def _generate_vector_thumbnail(self, filepath, size, page_number=1, dpi=None):
        """
        Genera miniatura para archivos vectoriales con fondo inteligente:
        - PDF: Fondo Blanco (Documento)
        - AI, EPS, SVG: Transparente (Logo/Icono)
        - SIEMPRE usa motores nativos para velocidad.
        """
        ext = os.path.splitext(filepath)[1].lower()
        
        try:
            # Motores Nativos (Rápidos para previsualización)
            if ext == ".svg":
                return self._generate_svg_thumbnail(filepath, size)
            elif ext == ".pdf":
                return self._generate_pdf_thumbnail(filepath, size, page_number, transparent=False, dpi=dpi)
            elif ext == ".ai":
                return self._generate_pdf_thumbnail(filepath, size, page_number, transparent=True, dpi=dpi)
            elif ext in (".eps", ".ps"):
                return self._generate_eps_thumbnail(filepath, size, page_number, dpi=dpi)
                
            return None
        except Exception as e:
            print(f"DEBUG: Error generando miniatura vectorial ({ext}): {e}")
            return None

    def _generate_thumbnail_with_inkscape(self, filepath, size, page_number, dpi=96):
        """Usa Inkscape para la miniatura (Lento pero preciso)."""
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_png:
            tmp_png_path = tmp_png.name
        
        # 🗑️ IMPORTANTE: Borramos el archivo vacío creado por tempfile.
        # Así, si Inkscape falla, el archivo NO existirá y no intentaremos abrirlo.
        if os.path.exists(tmp_png_path):
            os.remove(tmp_png_path)
            
        try:
            render_dpi = dpi if dpi else 96
            cmd = self.inkscape_service.build_command(filepath, tmp_png_path, page_number, dpi=render_dpi)
            
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                           env=self.inkscape_service.get_env(), cwd=self.inkscape_service.get_cwd(), 
                           timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            
            if os.path.exists(tmp_png_path) and os.path.getsize(tmp_png_path) > 0:
                img = Image.open(tmp_png_path)
                img.load()
                img.thumbnail(size, Image.Resampling.LANCZOS)
                return img
            else:
                return None
        finally:
            if os.path.exists(tmp_png_path):
                try: os.remove(tmp_png_path)
                except: pass
        return None

    def _generate_svg_thumbnail(self, filepath, size):
        """Usa CairoSVG para la miniatura con corrección automática y fallback a Inkscape."""
        if not CAN_SVG:
            if self.inkscape_service:
                return self._generate_thumbnail_with_inkscape(filepath, size, 1)
            return None

        temp_svg = None
        try:
            w, h = size
            # 1. Intento normal con CairoSVG
            try:
                out = cairosvg.svg2png(url=filepath, output_width=w, output_height=h)
                img = Image.open(io.BytesIO(out))
                img.load()
                return img
            except (ValueError, TypeError, Exception) as e:
                print(f"DEBUG: [Thumb] CairoSVG falló para {os.path.basename(filepath)}: {e}. Intentando corrección...")
                
            # 2. Intentar corregir atributos (width/height inválidos)
            temp_svg = self._fix_svg_attributes(filepath)
            if temp_svg:
                try:
                    out = cairosvg.svg2png(url=temp_svg, output_width=w, output_height=h)
                    img = Image.open(io.BytesIO(out))
                    img.load()
                    return img
                except:
                    print(f"DEBUG: [Thumb] CairoSVG también falló con SVG corregido.")
            
            # 3. Fallback final a Inkscape (si está habilitado)
            if self.inkscape_service:
                print(f"DEBUG: [Thumb] Usando Inkscape como fallback para vista previa de SVG.")
                return self._generate_thumbnail_with_inkscape(temp_svg if temp_svg else filepath, size, 1)
                
            return None
        except Exception as e:
            print(f"DEBUG: [Thumb] Error total en vista previa SVG: {e}")
            return None
        finally:
            if temp_svg and os.path.exists(temp_svg):
                try: os.remove(temp_svg)
                except: pass

    def _generate_pdf_thumbnail(self, filepath, size, page_number, transparent=False, dpi=None):
        """Usa Poppler para la miniatura con fondo controlado."""
        if not CAN_PDF or not self.poppler_path: return None
        try:
            # 📈 LÓGICA DE CALIDAD:
            # Si el tamaño solicitado es grande (>500px), es para el VISOR.
            # En ese caso, queremos una resolución que se vea perfecta.
            is_large_preview = max(size) > 500
            
            if is_large_preview:
                # Para el visor, usamos un DPI que garantice nitidez (mínimo 200, idealmente lo que pida el usuario)
                render_dpi = max(200, dpi if dpi else 300)
            else:
                # Para la lista de archivos, algo rápido (100 DPI)
                render_dpi = 100

            images = convert_from_path(filepath, dpi=render_dpi, first_page=page_number, last_page=page_number, 
                                       poppler_path=self.poppler_path, transparent=transparent, use_pdftocairo=True)
            if images:
                img = images[0].convert("RGBA")
                
                # Solo aplicamos thumbnail destructivo si NO es la previsualización grande
                if not is_large_preview:
                    img.thumbnail(size, Image.Resampling.LANCZOS)
                else:
                    print(f"DEBUG: [Thumb] Render de alta calidad para visor ({img.size})")
                    
                return img
        except Exception as e:
            print(f"DEBUG: [Thumb] Error en render PDF/EPS: {e}")
            return None
        return None

    def _find_ghostscript(self):
        """Busca Ghostscript localmente para miniaturas EPS."""
        try:
            base_path = os.getcwd()
            possible_dirs = [
                os.path.join(base_path, "bin", "ghostscript", "bin"),
                os.path.join(base_path, "bin", "ghostscript"),
            ]
            binaries = ["gswin64c.exe", "gswin32c.exe", "gs.exe", "gs"]
            for folder in possible_dirs:
                if os.path.exists(folder):
                    for binary in binaries:
                        path = os.path.join(folder, binary)
                        if os.path.exists(path): return path
            return None
        except: return None

    def _generate_eps_thumbnail(self, filepath, size, page_number, dpi=None):
        """Genera miniatura EPS con transparencia usando Ghostscript."""
        import re # Fail-safe
        if self.gs_exe and CAN_PDF:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                temp_pdf = tmp_pdf.name
            try:
                cmd = [self.gs_exe, "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", 
                       f"-sOutputFile={temp_pdf}", "-dEPSCrop", filepath]
                subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                return self._generate_pdf_thumbnail(temp_pdf, size, page_number, transparent=True, dpi=dpi)
            except: pass
            finally:
                if os.path.exists(temp_pdf):
                    try: os.remove(temp_pdf)
                    except: pass
        try:
            img = Image.open(filepath)
            img.load()
            img.thumbnail(size, Image.Resampling.LANCZOS)
            return img
        except: return None