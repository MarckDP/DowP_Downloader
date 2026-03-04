# DowP

**Está hecho con IA (Gemini).**

Es una interfaz gráfica para **`yt-dlp`** y **`ffmpeg`** desarrollada en **`Python`**. Permite la descarga y/o recodificación de medios (video y audio) tanto de fuentes remotas como locales. Diseñada para flujos de trabajo con **Adobe Premiere Pro**.

<div align="center">
  <img width="300" height="451" alt="image" src="https://github.com/user-attachments/assets/ac367935-bc6e-43ef-be37-fd9cb7e01d31" />
  <img width="300" height="451" alt="image" src="https://github.com/user-attachments/assets/fa4c0c7d-83c4-49e1-abd9-b215d6adb021" />
  <img width="300" height="451" alt="image" src="https://github.com/user-attachments/assets/c089d6fb-034b-4bb6-8b12-d2edc19063d3" />

</div></div>

### 🎯 Pestañas Principales
- **Proceso Único**: Descarga e importación individual con opciones de recodificación.
- **Proceso por Lotes**: Gestión masiva de Playlists y listas de URLs.
- **Herramientas de Imagen**: Procesamiento vectorial, RAW y eliminación de fondos con IA.
- **Ajustes**: Configuración global de la aplicación y gestión de dependencias.
## 💻 Cómo Usar o Compilar el Código Fuente

Este repositorio contiene el **código fuente** de la aplicación.
Si solo deseas instalar y usar el programa finalizado, dirígete al [Repositorio Principal de DowP (Releases)](https://github.com/MarckDP/DowP/releases) y descarga el setup `.exe`.

Si eres desarrollador y deseas clonar, usar o compilar este código fuente en tu máquina:

1. **Clona el repositorio** e instala los requerimientos:
   ```bash
   git clone https://github.com/MarckDP/DowP_Downloader.git
   cd DowP_Downloader
   pip install -r requirements.txt
   ```
2. **Ejecutar desde el código**:
   Simplemente ejecuta el archivo principal:
   ```bash
   python main.py
   ```
3. **Dependencias Externas**:
   - **FFmpeg**: Se descarga automáticamente desde dentro de la app (repositorio **gyanv**).
   - Opcionalmente puedes compilarlo a ejecutable usando PyInstaller u otras herramientas que prefieras.
## Características Principales

DowP cuenta con dos modos principales: **Modo URL** y **Recodificación Local**. Las opciones de recodificación son las mismas en ambos casos.

## 🌐 Modo URL

En este modo puedes analizar cualquier URL compatible con yt-dlp para obtener toda la información de video y audio disponible.

### Panel Izquierdo

#### 🖼️ Miniatura
- **Zona de miniatura**: Muestra la miniatura del video/archivo a descargar
- **"Descargar Miniatura..."**: Descarga solo la miniatura
- **"Descargar miniatura con el video"**: Descarga ambos al usar "Iniciar Descarga"

#### ✂️ Segmentar
Selecciona un segmento específico del video o audio indicando los tiempos de inicio y fin. Opciones avanzadas:
- **Corte Preciso (Lento/Recodificar)**: Recodifica los bordes del fragmento para exactitud total milimétrica.
- **Descargar completo para cortar (Rápido)**: Descarga primero a máxima velocidad y corta localmente, ideal si tienes internet rápido pero el servidor tarda en procesar el corte remoto.
- **Conservar completo**: Guarda el video entero además del fragmento recortado.

#### ✨ Extras
Esta sección (antes "Modo Extraer") incluye herramientas adicionales para el procesamiento:
- **Reescalado con IA**: Mejora la resolución de fotos y videos usando motores **Real-ESRGAN, Waifu2x, RealSR y SRMD**. Permite elegir escala (2x, 3x, 4x) y motor según tu GPU/CPU.
- **Extraer Fotogramas**: Extrae frames del video a una secuencia de imágenes. Puedes configurar los FPS, elegir formato PNG o ajustar la compresión JPG usando un slider interactivo, y guardar todo en una subcarpeta automática.
- **Auto-enviar a H.I. (Herramientas de Imagen)**: Opción en el panel de miniaturas para enviar automáticamente la vista previa descargada y poder editarla, quitar sus fondos o reescalarla.

#### 📝 Subtítulos
Muestra los subtítulos disponibles de la URL analizada:
- **Idioma**: Selecciona entre todos los idiomas disponibles
- **Formato**: Muestra formatos disponibles para el idioma seleccionado
  - "Manual": Subidos por el creador del video
  - "Automático": Generados automáticamente por la plataforma
- **Opciones de descarga**: 
  - "Descargar Subtítulos" (individual)
  - "Descargar subtítulos con el video" (al usar "Iniciar Descarga")
- **Simplificación VTT**: Para archivos `.vtt`, aparece la opción **"Simplificar a formato estándar (SRT)"**

#### 🍪 Cookies
Para descargar contenido que requiere login (restricciones de edad, videos privados, etc.):
- **"Archivo Manual..."**: Usa un archivo de cookies descargado
- **"Desde el Navegador"**: Extrae cookies del navegador seleccionado

> [!WARNING]
> **Recomendaciones para cookies:**
> - Para **"Archivo Manual"**: Usa [Get Cookies LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY)
> - Para **"Desde el Navegador"**: Los navegadores basados en Chromium (Chrome, Edge, Opera, Brave) tienen problemas de seguridad. **Se recomienda usar Firefox** e iniciar sesión en las páginas necesarias.
> - **Importante**: Nunca compartas tu archivo cookies.txt. Contiene tokens de sesión que permiten acceder a tu cuenta.

#### 🔧 Mantenimiento
Actualiza FFmpeg si es necesario después de negar las actualizaciones automáticas.

### Panel Derecho

#### 📋 Título
- Muestra el título de la URL analizada
- Permite cambiar el nombre final del archivo a descargar/recodificar
- Soporta cualquier carácter

#### 🎥 Opciones de Modo
- **"Video+Audio"** vs **"Solo Audio"**
- Cada modo incluye menús de **Calidades** para Video y Audio
- Las calidades de audio muestran idiomas disponibles (funciona en YouTube)

#### 📊 Calidades
Muestra todas las calidades disponibles con información detallada: resolución, FPS, Kbps, códec, formato/contenedor, tamaño aproximado.

**Indicadores de compatibilidad:**

| Icono/Mensaje | Significado |
|---------------|-------------|
| ✨ | Ideal para Adobe Premiere o After Effects |
| ⚠️ | Problemático con Ae o Pr por códec o contenedor |
| `[Streaming]` | Mejor calidad pero más restrictivo, recomendable usar cookies |
| `[Combinado]` | Video y audio en el mismo archivo, sin opción de calidad de audio separada |
| `[Premium]` | Contenido premium, requiere cookies |

> [!NOTE]
> Si seleccionas las opciones ideales (✨), no necesitarás recodificar.

#### ⚠️ Advertencias de Compatibilidad
Muestra advertencias sobre compatibilidad con Adobe Premiere Pro y qué hacer en la recodificación.

---

Esta sección permite recodificar medios (descargados o locales) para asegurar compatibilidad con editores como Adobe Premiere Pro. Las opciones disponibles varían según el modo seleccionado:

### Modo "Video+Audio"

#### Opciones Básicas
- **Recodificar Video**: Marca para recodificar solo el video
- **Recodificar Audio**: Marca para recodificar solo el audio  
- **"Mantener los Archivos originales"**: Conserva o elimina archivos originales

> [!WARNING]
> Si desactivas "Mantener Archivos originales", se eliminarán **TODOS** los archivos originales (video, miniatura, subtítulos). ¡Ten cuidado!

#### **Advertencias de recodificación**
Muestra alertas sobre compatibilidad de códecs:
- **Verde**: Combinación correcta
- **Amarillo**: Posiblemente incompatible (bajo tu riesgo)
- **Rojo**: Directamente incompatible (no permitirá procesar)

#### Opciones de Video
- **Códecs CPU/GPU**: Es importante que sepas cuál es tu GPU (el programa no detecta hardware automáticamente)
  - **GPU**: Permiten aceleración por hardware (H264, H265, AV1, VP9) - Dependen de tu GPU (Nvidia, AMD, Intel)
  - **CPU**: Códecs profesionales (Apple ProRes, DNxHD/HR, GoPro Cineform, etc.)
  - **Códec**: Todos los códecs disponibles para tu selección
  - **Perfil/Calidad**: Depende del códec. Para H264, H265, AV1, etc., aparecen opciones de Bitrate (CBR/VBR)
  - **Contenedor**: Formato final (mp4, mov, webm, etc.)

#### Opciones Adicionales
- **"Forzar a FPS Constantes (CFR)"**: Evita errores de sincronización de audio
- **"Cambiar Resolución"**: 
  - Presets disponibles o resolución personalizada
  - Mantener relación de aspecto
  - "No ampliar resolución" para evitar aumentos accidentales
- **Guardar Ajustes y Presets**: Los ajustes personalizados ahora se pueden guardar en json internos. Hay botones dedicados de "Importar", "Exportar" y "Eliminar" presets.

> [!WARNING]
> Cambiar resolución **estira** el video, no lo recorta. Puede distorsionar si no respetas la relación de aspecto original.

#### Opciones de Audio
- **Códec de Audio**: Todos los códecs disponibles (siempre procesado por CPU). Muestran únicamente códecs compatibles con el video seleccionado
- **Perfil de Audio**: Opciones específicas según el códec seleccionado

### Modo "Solo Audio"

- Convierte video a audio o extrae audio de videos
- **"Activar la Recodificación para Audio"**: Habilita opciones de recodificación. Al activar la recodificación, aparecen TODOS los códecs de audio disponibles
- **"Mantener los Archivos Originales"**: Misma función que antes

> [!TIP]
> **Mensajes de advertencia**: En ambos modos aparecen mensajes que indican si la combinación de códecs es correcta, problemática o imposible. Los códecs imposibles bloquearán los botones de inicio para evitar errores.

---

## 📁 Modo de Recodificación Local

Actívalo con el botón **"Importar Archivo Local"** o simplemente arrastrando tus archivos a la interfaz.

### Cambios en la Interfaz
- **Miniatura**: Muestra un fotograma inicial del video (o icono 🎵 para audio)
- **Secciones deshabilitadas**: Descarga de Miniatura y Subtítulos
- **Título**: Funciona igual que en modo URL
- **Modo**: Misma función, se pone automáticamente en "Solo Audio" si importas audio. Permiten convertir formato (ej: video con audio → solo audio)
- **Menús de Calidades**: Ahora son informativos (muestran info del archivo importado)
- **Múltiples pistas de audio**: Se pueden seleccionar individualmente para procesar
- **Nueva opción**: "Guardar en la misma carpeta que el original"
- **Nuevo botón**: **"Limpiar y Volver a Modo URL"** para regresar fácilmente

### Regreso al Modo URL
- Usa el botón "Limpiar y Volver a Modo URL", o
- Simplemente pega una URL nueva y dale "Analizar"

---

## 📦 Proceso por Lotes (Batch)

Ideal para descargar playlists de YouTube o listas de enlaces personalizados.
- **Importación Masiva**: Pega una URL de playlist o una lista de links.
- **NUEVO: Importación Local**: Activa el modo de recodificación local seleccionando múltiples archivos a la vez directos desde el ordenador.
- **Configuración Individual o Global**: Aplica recodificación específica manual para cada elemento de la lista o activa "Recodificación Global" para imponer tus **presets de conversión previstos** en toda la cola con 1 sólo clic.
- **Manejo de Conflictos**: Al detectar un archivo con un mismo nombre al guardar, el lote tiene nuevas normas seleccionables ("Sobrescribir", "Renombrar", u "Omitir").
- **Drag & Drop Masivo**: Soporte en la pestaña mediante "arrastrar y soltar" directamente a la lista.
- **Gestión de Cola**: Visualiza el progreso de cada descarga y proceso de forma independiente.

---

## 🎨 Herramientas de Imagen

Módulo avanzado para el procesamiento de archivos de imagen:
- **NUEVOS Visores Interactivos:** Soporte nativo para visualizar zoom al nivel de los pixeles usando rueda del ratón y arrastre. Hay 1 visor regular y 1 visor interactivo de doble capa ("Antes/Después") que incluye un slider desplazable para comparar diferencias visuales al procesar.
- **Soporte extendido de Formatos:** Adicional a lo habitual (.png, .webp, .jpeg) ahora hay soporte para múltiples imágenes vectoriales (.ai, .eps, .ps) gracias a Ghostscript, así como los **archivos RAW en bruto** que usan directamente múltiples cámaras (.dng, .cr2, .arw, .nef).
- **IA Background Remover**: Elimina fondos automáticamente.
  - Sliders de **Suavizado** y **Expansión/Contracción** para un control total sobre los bordes del recorte.
- **Procesamiento en Lote**: Aplica cambios de tamaño, formato o márgenes a cientos de imágenes simultáneamente y exporta en lotes unificados (por ej. a .avif).

---

## ⚙️ Pestaña de Ajustes

Configura DowP a tu medida:
- **Rutas por Defecto**: Establece dónde se guardarán tus descargas y procesos (separando descargas únicas de los lotes masivos).
- **Gestión de Dependencias y Modelos**: Verifica y actualiza herramientas de sistema (FFmpeg, Deno, Poppler, etc.) y ahora, puedes **visualizar, descargar y eliminar** de forma controlada todos los modelos de Inteligencia Artificial (modelos rembg de BriaAI, motores Waifu2X y Real-ESRGAN, etc.) desde la propia interfaz para gestionar mejor tu espacio local.
- **Comportamiento Global**: Configura si quieres que se abra la carpeta al finalizar, si prefieres modo rápido en lotes, etc.

---

## 📤 Opciones de Salida

- **Carpeta de salida**: Selecciona con "..." o escribe la ruta directamente
- **Botón 📂**: Se activa después de completar operaciones para abrir la carpeta de destino
- **Límite**: (Solo modo URL) Limita la velocidad de descarga para evitar rechazos por "TOO MANY REQUEST"
- **Botón de acción**: "Iniciar Descarga" (URL) o "Iniciar Proceso" (Local), cambia a "Cancelar" durante operaciones

---

## 🔧 Solución de Problemas

### Errores de Descarga

Los errores más comunes ocurren durante las descargas. Para mitigarlos:

1. **Usa cookies**: Especialmente para archivos con restricciones o descargas masivas
2. **Subtítulos automáticos**: Son más restrictivos, prefiere subtítulos manuales del creador
3. **Límite de descarga**: Ayuda a "engañar" a las webs que rechazan muchas peticiones

### Sistema de Reintentos Automáticos

Si DowP no puede descargar, intentará automáticamente:
1. **Primer intento**: Según configuración solicitada
2. **Segundo intento**: Calidad similar pero menos restrictiva (esto cambiará el idioma de audio que hayas escogido, si es que escogiste alguno)
3. **Tercer intento**: Método bv+ba (mejor video + mejor audio disponible) como último recurso ignorando todo lo que hayan pedido pero priorizando una descarga sí o sí
4. Si falla todo, mostrará error con recomendaciones

### Problemas con Playlists

Para URLs con playlists de sitios poco comunes que muestren error "No se puede encontrar la ruta del archivo", verifica que uses la URL correcta del video/audio individual. En ocasiones con URLs con playlist de sitios poco comunes, puede llegar a fallar en determinar qué archivo descargar, y DowP no está hecho para descargar archivos en cola (por ahora). Las descargas en cola se implementarán en futuras actualizaciones.
