# 📄 Créditos y Licencias — DowP

DowP es un proyecto **open-source**, **no comercial** y con su código completamente público. Esto permite cumplir de forma correcta con todas las licencias incluidas, incluso aquellas que requieren copyleft (GPL y AGPL).

---

## 📊 Resumen de Licencias

| Componente | Licencia | Copyleft | Redistribución |
|------------|----------|----------|----------------|
| yt-dlp | Unlicense | No | ✅ Ilimitada |
| FFmpeg | GPL v3 | Sí | ✅ (con código público) |
| CustomTkinter | MIT | No | ✅ Ilimitada |
| Poppler | GPL v2 | Sí | ✅ (con código público) |
| Ghostscript | AGPL | Sí | ✅ (con código público) |
| Modelos IA (MIT/Apache) | Permisivas | No | ✅ Ilimitada |
| RMBG 2.0 oficial | CC BY-NC 4.0 | No | ⚠️ Solo no comercial |

---

## 🛠️ Motores Principales

### **yt-dlp**
- **Función:** Motor principal de descarga
- **Licencia:** [The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)
- **Repositorio:** https://github.com/yt-dlp/yt-dlp

### **FFmpeg (builds de BtbN)**
- **Función:** Procesamiento y conversión multimedia
- **Licencia:** [GPL v3](https://www.gnu.org/licenses/gpl-3.0.html) (builds usadas)
- **Repositorio:** https://github.com/BtbN/FFmpeg-Builds
- **⚖️ Nota legal:** DowP incluye binarios GPL de FFmpeg. Al ser un proyecto open-source con código público en GitHub, cumple plenamente con los términos de redistribución GPL.

### **CustomTkinter**
- **Función:** Interfaz gráfica moderna
- **Licencia:** [MIT](https://github.com/TomSchimansky/CustomTkinter/blob/master/LICENSE)
- **Repositorio:** https://github.com/TomSchimansky/CustomTkinter

---

## 🧰 Herramientas Externas (Incluidas en el Instalador)

### **Deno**
- **Función:** Runtime JavaScript para herramientas internas
- **Licencia:** [MIT](https://github.com/denoland/deno/blob/main/LICENSE.md)
- **Repositorio:** https://github.com/denoland/deno

### **Poppler (Windows builds)**
- **Función:** Renderizado y conversión de PDF
- **Licencia:** [GPL v2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)
- **Repositorio:** https://github.com/oschwartz10612/poppler-windows
- **⚖️ Nota legal:** Poppler es GPL. DowP cumple la licencia por ser open-source con código público.

### **Inkscape**
- **Función:** Conversión y manipulación de archivos vectoriales
- **Licencia:** [GPL v2+](https://gitlab.com/inkscape/inkscape/-/blob/master/COPYING)
- **Repositorio:** https://gitlab.com/inkscape/inkscape
- **⚖️ Nota legal:** Binarios incluidos según GPL v2+. Totalmente compatible con la naturaleza open-source de DowP.

### **Ghostscript**
- **Función:** Procesamiento PostScript y PDF
- **Licencia:** [AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html)
- **Repositorio:** https://github.com/ArtifexSoftware/ghostpdl-downloads
- **⚖️ Nota legal:** La AGPL requiere que el código completo del programa sea público. DowP cumple esta condición.

---

## 🤖 Inteligencia Artificial

DowP utiliza varios modelos para eliminación de fondo y reescalado de imágenes.

### 🟢 Modelos de Eliminación de Fondo (Incluidos Automáticamente)

#### **U2Net / U2NetP**
- **Archivos:** `u2net.onnx`, `u2netp.onnx`
- **Licencia:** [Apache 2.0](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE)
- **Repositorio:** https://github.com/xuebinqin/U-2-Net
- **Paper:** https://arxiv.org/abs/2005.09007

#### **ISNet (General Use)**
- **Archivo:** `isnet-general-use.onnx`
- **Licencia:** [Apache 2.0](https://github.com/xuebinqin/DIS/blob/main/LICENSE.md)
- **Repositorio:** https://github.com/xuebinqin/DIS

#### **BiRefNet** (opcional)
- **Licencia:** [MIT](https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE)
- **Repositorio:** https://github.com/ZhengPeng7/BiRefNet

---

### 🟣 Caso Especial: RMBG 2.0

#### **RMBG 2.0 — Versión MIT (convertida por Daniel Gatis)**
- **Archivo:** `bria-rmbg-2.0.onnx`
- **Licencia:** [MIT](https://github.com/danielgatis/rembg/blob/main/LICENSE.txt) (heredada del proyecto rembg)
- **Repositorio:** https://github.com/danielgatis/rembg
- **✅ Distribución:** Incluida automáticamente. Esta versión **no** está sujeta a restricciones No Comerciales.

#### **RMBG 2.0 Oficial (BriaAI)**
- **Licencia:** [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) **(No Comercial)**
- **Repositorio:** https://huggingface.co/briaai/RMBG-2.0
- **⚠️ Distribución:** **No incluida** en el instalador. Requiere descarga manual por parte del usuario para cumplir con la licencia no comercial.

---

## 🔍 Reescalado (Upscaling)

Implementaciones portables NCNN-Vulkan desarrolladas por nihui y xinntao.

### **Modelos Incluidos**
- **waifu2x-ncnn-vulkan** (optimizado para arte anime)
- **realsr-ncnn-vulkan** (optimizado para fotografías reales)
- **srmd-ncnn-vulkan** (manejo de degradaciones múltiples)
- **Real-ESRGAN** (restauración de imágenes de propósito general)
- **Upscayl NCNN** (binario unificado para procesamiento de alto rendimiento)
- **Upscayl Custom Models** (colección de modelos especializados)

### **Licencias**
- waifu2x, RealSR, SRMD: [MIT License](https://opensource.org/licenses/MIT)
- Real-ESRGAN: [BSD-3-Clause](https://opensource.org/licenses/BSD-3-Clause)
- Upscayl NCNN: [AGPL v3](https://github.com/upscayl/upscayl-ncnn/blob/master/LICENSE)
- Upscayl Custom Models: [Varios (MIT/Apache)](https://github.com/upscayl/custom-models/blob/main/README.md)

### **Repositorios Oficiales**
- https://github.com/nihui/waifu2x-ncnn-vulkan
- https://github.com/nihui/realsr-ncnn-vulkan
- https://github.com/nihui/srmd-ncnn-vulkan
- https://github.com/xinntao/Real-ESRGAN
- https://github.com/upscayl/upscayl-ncnn
- https://github.com/upscayl/custom-models

### **Distribución en DowP**
Algunos modelos vienen pre-incluidos en el instalador. Los componentes faltantes se descargan automáticamente al iniciar DowP por primera vez.

---

## 🐍 Librerías Python

DowP utiliza las siguientes librerías, todas con licencias permisivas:

| Librería | Función | Licencia | Repositorio |
|----------|---------|----------|-------------|
| **Pillow (PIL)** | Procesamiento de imágenes | [HPND](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | [Ver repo](https://github.com/python-pillow/Pillow) |
| **rawpy** | Lectura de imágenes RAW | [MIT](https://github.com/letmaik/rawpy/blob/master/LICENSE) | [Ver repo](https://github.com/letmaik/rawpy) |
| **cairosvg** | Conversión SVG | [LGPL v3+](https://github.com/Kozea/CairoSVG/blob/master/LICENSE) | [Ver repo](https://github.com/Kozea/CairoSVG) |
| **pdf2image** | Wrapper de Poppler | [MIT](https://github.com/Belval/pdf2image/blob/master/LICENSE) | [Ver repo](https://github.com/Belval/pdf2image) |
| **Flask** | Framework web | [BSD-3](https://github.com/pallets/flask/blob/main/LICENSE.txt) | [Ver repo](https://github.com/pallets/flask) |
| **Flask-SocketIO** | WebSockets para Flask | [MIT](https://github.com/miguelgrinberg/Flask-SocketIO/blob/main/LICENSE) | [Ver repo](https://github.com/miguelgrinberg/Flask-SocketIO) |
| **python-socketio** | Motor Socket.IO | [MIT](https://github.com/miguelgrinberg/python-socketio/blob/main/LICENSE) | [Ver repo](https://github.com/miguelgrinberg/python-socketio) |
| **requests** | Cliente HTTP | [Apache 2.0](https://github.com/psf/requests/blob/main/LICENSE) | [Ver repo](https://github.com/psf/requests) |
| **py7zr** | Descompresión 7z | [LGPL v2.1+](https://github.com/miurahr/py7zr/blob/master/LICENSE) | [Ver repo](https://github.com/miurahr/py7zr) |
| **tkinterdnd2** | Drag & Drop para Tkinter | [MIT](https://github.com/pmgagne/tkinterdnd2/blob/master/LICENSE) | [Ver repo](https://github.com/pmgagne/tkinterdnd2) |
| **img2pdf** | Conversión de imágenes a PDF sin pérdida | [LGPL v3](https://gitlab.mister-muffin.de/josch/img2pdf/src/branch/main/LICENSE) | [Ver repo](https://gitlab.mister-muffin.de/josch/img2pdf) |
| **pillow-avif** | Soporte para imágenes AVIF en Pillow | [BSD-3-Clause](https://github.com/fdintino/pillow-avif-plugin/blob/main/LICENSE) | [Ver repo](https://github.com/fdintino/pillow-avif-plugin) |

Todas estas librerías permiten redistribución sin restricciones significativas.

---

## 🔗 Componentes Relacionados

### **DowP Extension**
- **Función:** Extensión para importar/exportar archivos entre DowP y línea de tiempo
- **Licencia:** MIT
- **Repositorio:** https://github.com/MarckDP/DowP_Importer-Adobe
- **Comunicación:** Se conecta a DowP mediante WebSocket (Socket.IO)

---

## 🔄 Si Creas un Fork de DowP

Para mantener el cumplimiento legal al hacer un fork:

- ✅ **Mantén el código público** (requerido por GPL/AGPL de FFmpeg, Poppler, Inkscape y Ghostscript)
- ✅ **Conserva esta sección de créditos** completa
- ✅ **Respeta las licencias No Comerciales** (si distribuyes RMBG 2.0 oficial de BriaAI)
- ✅ **Incluye el archivo LICENSE** del proyecto original
- ✅ **Documenta cualquier cambio** significativo que realices

---

## 📝 Declaración Final de Cumplimiento

**DowP cumple completamente con todas las licencias** de software y modelos incluidos gracias a que:

1. Es un proyecto **open-source** con código público
2. No tiene **fines comerciales**
3. Publica todo su código en **GitHub**
4. No distribuye componentes con **restricciones incompatibles** (como modelos NC sin autorización)
5. Respeta los términos **copyleft** (GPL/AGPL) mediante transparencia total del código fuente

---

**Todas las marcas registradas, logos y tecnologías mencionadas pertenecen a sus respectivos propietarios.**

*Última actualización: Noviembre 2025*