# DowP
**Esta hecho con IA (Gemini).**
Es una GUI para **`yt-dlp`** y **`ffmpeg`** hecha con **`Python`** y sirve para descargar videos y/o recodificarlos en el mismo programa, lo pensé para editores de video, principalmente para **Adobe Premiere Pro**

![01](https://github.com/user-attachments/assets/c1d22b99-b537-4973-858b-a522e7a6cb20)

Permite elegir entre descargar video+audio o solo audio, además de que puedes escoger que calidades quieres descargar. Gracias a que usa `yt-dlp` soporta una [gran cantidad de sitios web](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) y tienen la opción de recodificar directamente el video luego de descargarlo para importarlo en su software de edición, se priorizan los códecs profesionales para edición de video.

## Instalación
- Obvio ocupan [Python](https://www.python.org/downloads/) 
- Solo abran el `main.py` y este ya se encargará de descargar e instalar las dependencias, pero por si algún motivo no lo hace usen el:

  ```bash
  pip install -r requirements.txt
  ```
- El [`ffmpeg`](https://www.gyan.dev/ffmpeg/builds/) ya se instala con el `main.py` pero si no lo hace tendrán que instalarlo manualmente en el **PATH** de su sistema o copiar la carpeta bin la carpeta del script. 

## Características
Es fácil:
- La barra de arriba es para la **URL** del video.
  
  ![image](https://github.com/user-attachments/assets/b713af69-7669-4b0a-98fd-e70459cdfd90)

- Presionan el botón de **Analizar** y se mostrará la miniatura, el titulo y las opciones de calidad de audio y video del video que quieran descargar. En la sección del título pueden cambiar el nombre que tendrá su video final.

  ![image](https://github.com/user-attachments/assets/8064190e-8362-4551-9962-39c11e192574)

- Debajo de la miniatura tienen las opciones para descargarla directamente o que se guarde junto al video que vayan a descargar.
- Tienen dos modos de descarga: **Video+Audio** ó **Solo Audio** y en las opciones de las calidades se mostraran todas las que `yt-dlp` encuentre, en cada una se mostrara la resolución, el contendor, el códec y el tamaño del formato y además de una nota que indica si el formato es compatible con **Premiere Pro** o si requiere recodificación para que sea compatible.

  ![image](https://github.com/user-attachments/assets/9e470e1f-89b7-4b95-b4d2-927f5ec5997d)

- Cuenta con una sección debajo de la miniatura para usar `cookies` genéricas de distintos navegadores o usar las que hayan extraído por su cuenta en caso que quieran descargar videos privados, con restricción de edad o que requieran un inicio de sesión para poder verlos.

  ![image](https://github.com/user-attachments/assets/1784c5b4-cbcb-4940-b3c2-542fd599453a)

- Cuenta con la opción de recodificar si lo ven necesario, solo marquen la casilla y se habilitara el menú donde pueden escoger los códecs para **GPU** (H264, H265 , AVI) o los de **CPU** (AppleProRes, DNxHR, DNxHQ, GoPro CineForm, etc...)

  ![image](https://github.com/user-attachments/assets/99a893a4-d416-4794-9faa-b6a310b0f98c)

- Tiene una sección para poder escoger la carpeta de salida y si en algún caso la conexión se bloquea porque descargaron gran cantidad de archivos de un solo sitio web, pueden limitar la velocidad de descarga para que puedan volver a descargar. Aquí también esta el  botón de **Iniciar Descarga** xd.
  
  ![image](https://github.com/user-attachments/assets/7a80df4e-c391-4a56-973d-cd3128f46a7d)
