# DowP

**Está hecho con IA (Gemini).**

Es una GUI para **`yt-dlp`** y **`ffmpeg`** hecha con **`Python`**. Sirve para descargar videos y/o recodificar videos tanto al descargar como al importar archivos locales en el mismo programa. Lo pensé para editores de video, principalmente para **Adobe Premiere Pro**.

<div align="center">
  <img width="300" height="451" alt="DowP Interface 1" src="https://github.com/user-attachments/assets/64227026-4731-4985-bc30-dcbb1937cf0e"/>
  <img width="300" height="451" alt="DowP Interface 2" src="https://github.com/user-attachments/assets/f04c45a3-2882-41d2-8576-9f0ab23a28a0" />
  <img width="300" height="451" alt="DowP Interface 3" src="https://github.com/user-attachments/assets/48b0f02c-1f9c-48cd-8f26-74270affd9e8" />
</div>

## Instalación

### Requisitos
- [Python](https://www.python.org/downloads/) - **IMPORTANTE**: Marcar las casillas para poner Python en el PATH y ejecutarlo siempre como administrador

### Pasos
1. **Instalación automática**: Solo abre `main.py` y este se encargará de descargar e instalar las dependencias y todo lo necesario.

2. **Instalación manual** (si la automática falla):
   ```bash
   pip install -r requirements.txt
   ```

3. **FFmpeg**: Se instala automáticamente con `main.py`. Si no funciona, instálalo manualmente:
   - Descarga [FFmpeg](https://www.gyan.dev/ffmpeg/builds/)
   - Instálalo en el **PATH** de tu sistema, o
   - Copia la carpeta `bin` a la carpeta del script

## Características Principales

DowP cuenta con dos modos principales: **Modo URL** y **Recodificación Local**. Las opciones de recodificación son las mismas en ambos casos.

---

## 🌐 Modo URL

En este modo puedes analizar cualquier URL compatible con yt-dlp para obtener toda la información de video y audio disponible.

### Interfaz Principal
<div align="center">
<img width="820" height="34" alt="URL Interface" src="https://github.com/user-attachments/assets/cdd2f258-772e-4951-a4df-15fefb8d8dc4" />
</div>

Arriba del todo tienes la sección para pegar la **URL** y a su derecha el botón **"Analizar"**.

### Panel Izquierdo

#### 🖼️ Miniatura
<div align="center">
<img width="340" height="271" alt="Thumbnail Section" src="https://github.com/user-attachments/assets/d60e1914-e79b-40ee-aa9f-263a407cd3e0" />
</div>

- **Zona de miniatura**: Muestra la miniatura del video/archivo a descargar
- **"Descargar Miniatura..."**: Descarga solo la miniatura
- **"Descargar miniatura con el video"**: Descarga ambos al usar "Iniciar Descarga"

#### 📝 Subtítulos
<div align="center">
<img width="291" height="194" alt="Subtitles Section" src="https://github.com/user-attachments/assets/e0cdab08-463d-4996-91c1-a4d3ed71d94b" />
</div>

- **Idioma**: Selecciona entre todos los idiomas disponibles
  <div align="center">
  <img width="182" height="437" alt="Language Options" src="https://github.com/user-attachments/assets/9ad843e5-8617-44e8-86fc-fcb8cc62a5f8" />
  </div>

- **Formato**: Muestra formatos disponibles para el idioma seleccionado
  - "Manual": Subidos por el creador del video
  - "Automático": Generados automáticamente por la plataforma
  <div align="center">
  <img width="288" height="174" alt="Format Options" src="https://github.com/user-attachments/assets/0398dd49-3e78-42e5-8cc7-261de24eba1a" />
  </div>

- **Opciones de descarga**: 
  - "Descargar Subtítulos" (individual)
  - "Descargar subtítulos con el video" (al usar "Iniciar Descarga")

- **Simplificación VTT**: Para archivos `.vtt`, aparece la opción **"Simplificar a formato estándar (SRT)"**
  <div align="center">
  <img width="258" height="33" alt="VTT Simplify" src="https://github.com/user-attachments/assets/cd068f72-3d71-4187-be61-44cb6f580ebb" />
  </div>

#### 🍪 Cookies
<div align="center">
<img width="284" height="81" alt="Cookies Section" src="https://github.com/user-attachments/assets/bafa644a-9ff1-415f-93a6-da7eadbea522" />
</div>

Para descargar contenido que requiere login (restricciones de edad, videos privados, etc.):
- **"Archivo Manual..."**: Usa un archivo de cookies descargado
- **"Desde el Navegador"**: Extrae cookies del navegador seleccionado

> [!WARNING]
> **Recomendaciones para cookies:**
> - Para **"Archivo Manual"**: Usa [Get Cookies LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY)
> - Para **"Desde el Navegador"**: Los navegadores basados en Chromium (Chrome, Edge, Opera, Brave) tienen problemas de seguridad. **Se recomienda usar Firefox** e iniciar sesión en las páginas necesarias.

#### 🔧 Mantenimiento
<div align="center">
<img width="295" height="128" alt="Maintenance Section" src="https://github.com/user-attachments/assets/75ef1c3d-da35-4ed2-bbd9-e7e395a52f3f" />
</div>

Por el momento solo sirve para actualizar FFmpeg si se necesita después de negar las actualizaciones automáticas.

### Panel Derecho

#### 📋 Título
- Muestra el título de la URL analizada
- Permite cambiar el nombre final del archivo a descargar/recodificar
- Soporta cualquier carácter (o eso espero :,v)

#### 🎥 Opciones de Modo
<div align="center">
<img width="473" height="260" alt="Mode Options" src="https://github.com/user-attachments/assets/069e1253-3fc8-441e-a970-eee342c0ffef" />
</div>

- **"Video+Audio"** vs **"Solo Audio"**
- Cada modo incluye menús de **Calidades** para Video y Audio
- Las calidades de audio muestran idiomas disponibles (funciona en YouTube)

> [!NOTE]
> **Indicadores de compatibilidad**: Cada menú de calidad tiene iconos que muestran si el stream es compatible con Adobe Premiere Pro. Si seleccionas las opciones ideales, no necesitarás recodificar.

<div align="center">
<img width="315" height="331" alt="Compatibility Indicators" src="https://github.com/user-attachments/assets/3d696248-6388-4381-955f-ded48a57aa88" />
</div>

#### ⚠️ Advertencias de Compatibilidad
<div align="center">
<img width="369" height="39" alt="Compatibility Warnings" src="https://github.com/user-attachments/assets/a8ce25cb-3823-4ad6-829f-a1c2ce52cb4a" />
</div>

Muestra advertencias sobre compatibilidad con Adobe Premiere Pro y qué hacer en la recodificación.

---

## 🎬 Opciones de Recodificación

Esta es la parte más interesante. Aquí puedes recodificar videos (descargados o locales) para que sean compatibles con Adobe Premiere Pro u otros editores.

### Modo "Video+Audio"

#### Opciones Básicas
- **Recodificar Video**: Marca para recodificar solo el video
- **Recodificar Audio**: Marca para recodificar solo el audio
- **"Mantener los Archivos originales"**: Conserva o elimina archivos originales

> [!WARNING]
> Si desactivas "Mantener Archivos originales", se eliminarán **TODOS** los archivos originales (video, miniatura, subtítulos). ¡Ten cuidado!

#### Opciones de Video
- **Códecs CPU/GPU**: Es importante que sepas cuál es tu GPU (el programa no detecta hardware automáticamente)
  - **Códec**: Todos los códecs disponibles para tu selección
  - **Perfil/Calidad**: Depende del códec. Para H264, H265, AV1, etc., aparecen opciones de Bitrate (CBR/VBR)
  - **Contenedor**: Formato final (mp4, mov, webm, etc.)

#### Opciones Adicionales
- **"Forzar a FPS Constantes (CFR)"**: Evita errores de sincronización de audio
- **"Cambiar Resolución"**: 
  - Presets disponibles o resolución personalizada
  - Mantener relación de aspecto
  - "No ampliar resolución" para evitar aumentos accidentales

> [!WARNING]
> Cambiar resolución **estira** el video, no lo recorta. Puede distorsionar si no respetas la relación de aspecto original.

#### Opciones de Audio
- **Códec de Audio**: Todos los códecs disponibles (siempre procesado por CPU)
- **Perfil de Audio**: Opciones específicas según el códec seleccionado

### Modo "Solo Audio"

- Convierte video a audio o extrae audio de videos
- **"Activar la Recodificación para Audio"**: Habilita opciones de recodificación
- **"Mantener los Archivos Originales"**: Misma función que antes

> [!TIP]
> **Mensajes de advertencia**: En ambos modos aparecen mensajes que indican si la combinación de códecs es correcta, problemática o imposible. Los códecs imposibles bloquearán los botones de inicio para evitar errores.

---

## 📁 Modo de Recodificación Local

Actívalo con el botón **"Importar Archivo Local para Recodificar"** al final de las opciones de recodificación.

### Cambios en la Interfaz
- **Miniatura**: Muestra fotograma inicial del video (o ícono de audio)
- **Secciones deshabilitadas**: Descarga de Miniatura y Subtítulos
- **Título**: Funciona igual que en modo URL
- **Modo**: Misma función, se pone automáticamente en "Solo Audio" si importas audio
- **Menús de Calidades**: Ahora son informativos (muestran info del archivo importado)
- **Nuevo botón**: **"Limpiar y Volver a Modo URL"** para regresar fácilmente

### Regreso al Modo URL
- Usa el botón "Limpiar y Volver a Modo URL", o
- Simplemente pega una URL nueva y dale "Analizar"

---

## 🚀 ¿Y ahora qué?

Aquí dejo esta cosa jaja. En algún futuro lejano haré actualizaciones... si no muero antes.

---

**¿Problemas?** Abre un issue o busca ayuda en la comunidad. ¡El programa está en constante mejora!
