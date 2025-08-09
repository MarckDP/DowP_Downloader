# DowP
**Esta hecho con IA (Gemini).**
Es una GUI para **`yt-dlp`** y **`ffmpeg`** hecha con **`Python`** y sirve para descargar videos y/o recodificar videos tanto al descargar como al importar archivos locales en el mismo programa, lo pensé para editores de video, principalmente para **Adobe Premiere Pro**

<div align="center">
  <img width="300" height="451" alt="image" src="https://github.com/user-attachments/assets/64227026-4731-4985-bc30-dcbb1937cf0e"/>
  <img width="300" height="451" alt="image" src="https://github.com/user-attachments/assets/f04c45a3-2882-41d2-8576-9f0ab23a28a0" />
  <img width="300" height="451" alt="image" src="https://github.com/user-attachments/assets/48b0f02c-1f9c-48cd-8f26-74270affd9e8" />
</div>

## Instalación
- Obvio ocupan [Python](https://www.python.org/downloads/) 
- Solo abran el `main.py` y este ya se encargará de descargar e instalar las dependencias y todo lo necesario, pero por si algún motivo no lo hace usen el:

  ```bash
  pip install -r requirements.txt
  ```
- El [`ffmpeg`](https://www.gyan.dev/ffmpeg/builds/) ya se instala con el `main.py` pero si no lo hace tendrán que instalarlo manualmente en el **PATH** de su sistema o copiar la carpeta bin la carpeta del script. 

## Características
Cuanta con dos modos principales: El modo de **URL** y **Recodificación Local**, las opciones de recodificación en ambos casos no cambian.
### Modo URL
En este modo podemos analizar una URL de cualquier sitio web que el yt-dlp soporte para que nos arroje toda la información en video y audio que consiga del archivo que queramos descargar.
Arriba del todo tenemos la sección para pegar o escribir la **URL** que queramos y a su derecha el botón para **"Analizar"**.

<div align="center">
<img width="820" height="34" alt="image" src="https://github.com/user-attachments/assets/cdd2f258-772e-4951-a4df-15fefb8d8dc4" />
</div>

**En el panel izquierdo tenemos:**
- La zona de la **Miniatura**: donde se mostrara la miniatura del video o archivo que queramos descargar. Debajo de esta estarán las opciones de descarga de la miniatura: el botón para **"Descargar Miniatura..."** que... descarga la miniatura xd y la casilla de **"Descargar miniatura con el video"** que funciona al momento de darle al botón de **"Iniciar Descarga"** y descarga tanto el video como la miniatura.

<div align="center">
<img width="340" height="271" alt="image" src="https://github.com/user-attachments/assets/d60e1914-e79b-40ee-aa9f-263a407cd3e0" />
</div>
  
- La sección de los **Subtítulos**: Donde tenemos las opciones de:
  
  <div align="center">
  <img width="291" height="194" alt="image" src="https://github.com/user-attachments/assets/e0cdab08-463d-4996-91c1-a4d3ed71d94b" />
  </div>
  
  - **Idioma:** Para seleccionar todos los idiomas disponibles en la URL que se analizó.
    
    <div align="center">
    <img width="182" height="437" alt="image" src="https://github.com/user-attachments/assets/9ad843e5-8617-44e8-86fc-fcb8cc62a5f8" />
    </div>
    
  - **Formato:** Donde estarán todos los formatos de subtítulo disponibles para el idioma del subtitulo que se seleccionó. Los que digan "Manual" son los subidos a la web por el creador del video mientras que los que digan "Automatico" son  los generados automaticamente por el sitio Web.

    <div align="center">
    <img width="288" height="174" alt="image" src="https://github.com/user-attachments/assets/0398dd49-3e78-42e5-8cc7-261de24eba1a" />
    </div>

  - **Las opciones de descarga del subtítulo:** Al igual que en la Miniatura, aquí podemos seleccionar si queremos **"Descargar Subtítulos"** individualmente o **"Descargar subtítulos con el video"** para hacerlo al momento de **"Iniciar Descarga"**
  - Al seleccionar un formato de subtítulo **".vtt"**  se mostrará la casilla de **"Simplificar a formato estándar (SRT)"** que sirve  en caso de que el subtitulo .vtt tenga marcadores de tiempo para Karaoke, así se simplifica, en caso de que el .vtt no este en modo "Karaoke" se mantendrá igual no importa que esta casilla este marcada (No convierte solo simplifica).

<div align="center">
<img width="258" height="33" alt="image" src="https://github.com/user-attachments/assets/cd068f72-3d71-4187-be61-44cb6f580ebb" />
</div>

- La sección de Cookies: para que el yt-dlp pueda analizar y descargar URL's en las que se necesite estar logueado para poder verlas (por restricción de edad, sean privados o por limite de la propia web) se necesitan las cookies de un navegador real, para esto contamos con la opción de usar un **"Archivo Manual..."** que se haya descargado o extraído de un navegador o intentar extraer las cookies **"Desde el Navegador"** de preferencia que se tenga instalado.

  <div align="center">
  <img width="284" height="81" alt="image" src="https://github.com/user-attachments/assets/bafa644a-9ff1-415f-93a6-da7eadbea522" />
  </div>
> [!WARNING]
> Para la opcion de **"Archivo Manual..."** recomiendo usar [Get Cookies LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY) para extraer las cookies de cualquier navegador, pero con la opción de **"Desde el Navegador"** hay varios problemas en navegadores basados en Chromium (Google Chrome, Edge,  Opera, Breve, etc...) esto porque estos navegadores tienen varios sistemas de seguridad para sus cookies y el yt-dlp no suele poder extraerlos sin ayuda externa, así que es recomendado usar las cookies del navegador de Firefox y obvio que este instalado e iniciado sesión en las paginas web donde se necesite descargar videos.
- La sección de **Mantenimiento** por el momento solo sirve para actualizar el FFmpeg en caso de que se necesite una comprobación e instalación luego de haber negado las actualizaciones automáticas al iniciar el programa.

  <div align="center">
  <img width="295" height="128" alt="image" src="https://github.com/user-attachments/assets/75ef1c3d-da35-4ed2-bbd9-e7e395a52f3f" />
  </div>

**En el panel derecho tenemos:**
- La Sección del **"Título"** donde se muestra el titulo de la **URL** que analizamos y donde podremos cambiar el titulo final del archivo que vayamos a Descargar y/o Recodificar, no importan los caracteres que se pongan, el programa esta hecho para soportar cualquiera (o eso espero :,v en todas las pruebas que hice no hubo fallas xd)
- En las opciones de **"Modo"** podemos cambiar entre la  descarga del **"Video+Audio"** y el **"Solo Audio"** y dentro de cada una encontraremos los menús de las **Calidades** para Video y Audio. Dentro de estos menús estarán todas las calidades que el yt-dlp nos entregue además que en las opciones de **"Calidad de Audio"** se mostraran los idiomas de audio que estén disponibles (esto funciona en YouTube, es la única que conozco con esas opciones jaja).

  <div align="center">
  <img width="473" height="260" alt="image" src="https://github.com/user-attachments/assets/069e1253-3fc8-441e-a970-eee342c0ffef" />
  </div>

> [!NOTE]
> Dentro de cada menú de calidad tendremos varios indicadores con iconos y palabras que muestran si el stream en cuestión en compatible o no con Adobe Premiere Pro, si seleccionamos el ideal tanto en la calidad de video como en la de audio no habrá necesidad de         recodificar la descarga. En la parte de abajo de las calidades, si la interfaz está vacía o seleccionamos las opciones ideales, se mostraran los significados de cada icono.

<div align="center">
<img width="315" height="331" alt="image" src="https://github.com/user-attachments/assets/3d696248-6388-4381-955f-ded48a57aa88" />
</div>

- Debajo de las opciones de Calidades aparecerán advertencias sobre la compatibilidad de los streams seleccionados para Adobe Premiere Pro y que acción se debería tomar en la recodificación para mitigar estos problemas.

  <div align="center">
  <img width="369" height="39" alt="image" src="https://github.com/user-attachments/assets/a8ce25cb-3823-4ad6-829f-a1c2ce52cb4a" />
  </div>

### Opciones de Recodificación
Creo que es lo mas interesante, aquí podremos recodificar un video, tanto Descargado como Local, para que sea compatible con Adobe Premiere Pro u otros programas dedicados a la edición de video. Tiene varias opciones que van a variar según lo que seleccionemos en el **"Modo"** (Video+Audio ó Solo Audio):
**En modo **Video+Audio****
- Tenemos dos casillas: Recodificar Video y Recodificar Audio, si marcamos solo una de estas el programa copiara el stream original del video o audio que queramos recodificar tanto en el modo de **URL** como en el de **Recodificación Local**.
- La casilla de **"Mantener los Archivos originales"** siempre estará marcada por Default y nos sirve para conservar o eliminar los archivos originales descargados inicialmente o importados para la recodificación.
> [!WARNING]
> En caso de desactivar esta opción los archivos originales se eliminaran al finalizar cualquier operación ***(esto incluye el video descargado/importado, la miniatura o los subtítulos, así que cuidado con esta opción).
- Cuando seleccionemos alguna opción de Recodificación se mostraran sus opciones. Para la recodificación de video están:
  - Los códecs por CPU o GPU (Es importante que sepan cual es su GPU porque el programa no está hecho para detectar su Hardware). Al seleccionar cualquiera de estas opciones se les habilitan el resto de opciones:
   - **Codec:** Aquí están todos los códecs disponibles para la GPU o CPU.
   - **Perfil/Clidad:** Estas opciones dependerán del Códec escogido. Si escogieron códecs como el de H264, H265, AVI, etc, se habilitaran las opciones de Bitrate Personalizado donde pueden escoger entre CBR y VBR y agregar la cantidad de Mbps que deseen.
   - **Contenedor:** Aquí aparecerá el contendor final que tendrá la recodificación (mp4, mov, webm, mp3, etc...). 
 - La opción para **"Forzar a FPS Constantes (CFR)"** sirve para eso jaja, fuerza al video recodificado a tener framerate constante para evitar errores de sincronización de audio en los programas de edición.
 - La opción de **"Cambiar Resolución"** tiene algunas opciones para cambiar la resolución del video a recodificar si lo ven necesario, en personalizado ponen el valor que quieran y pueden mantener la relación de aspecto si así lo quieren o usar cualquiera de los prestes con los que viene, la casilla de **"No ampliar resolución"** es para que eviten un aumento de resolución accidental. 
> [!WARNING]
> Es importante que sepan que esto no recorta el tamaño video sino que estira el video en resoluciones que no respeten la relación de aspecto del video original.   
- Si marcamos también la opción de Recodificar Audio tenemos básicamente lo mismo que en video pero en Audio xd:
 - Aquí no hay opciones de GPU o CPU porque siempre se procesa el Audio con la CPU
 - En **"Códec de Audio:"** Están todos los códecs de audio disponibles.
 - En **"Perfil de Audio:"** Depende de lo seleccionado en el **Códec de Audio** y muestra todas las opciones que hay para cada códec.

**En modo **"Solo Audio"****
- En este modo podemos convertir un video a un audio, o extraer solo el audio de algún video que descarguemos o importemos, si el archivo importado solo es un audio pues solo lo recodificaremos y ya.
- Tenemos la casilla de **"Activar la Recodificación para Audio"** y la de **"Mantener los Archivos Originales"** que ya vimos antes, Si activamos la casilla de recodificación simplemente muestra las opciones de Audio que vimos antes.

> [!TIP]
> Tanto en el modo de **Video+Audio** como en el de **Solo Audio**, justo después de las  casillas de recodificación y mantener archivos hay un espacio para mensajes de advertencia que muestran si la combinación de códec de video es correcta, puede causar problemas o directamente es imposible (En caso de ser imposible bloquearan el botón de **Iniciar Descarga** o **Iniciar Proceso** para evitar errores), estos mensajes toman en cuenta también a los códecs del video original en caso de solo marcar una casilla o estar en modo de **Solo Audio** y se mostraran de la misma manera en el modo de **Recodificacion Local**

En ambos modos al final de todas las opciones se muestra el boton de **"Importar Archivo Local para Recodificar"** que sirve para activar el **Modo de Recodificación Local** que veremos mas adelante.

### Modo de Recodificación Local
En si este modo es igual que el de URL, para activarlo tenemos que presionar el botón de **"Importar Archivo Local para Recodificar"** Que vimos en las opciones de Recodificación y entonces seleccionamos el Video o Audio que queramos Recodificar, al hacerlo notaremos algunos cambios:
- La sección de la miniatura mostrará un fotograma inicial del video que importemos, si se importa un audio solo muestra un ícono de audio.
- Se deshabilitarán las secciones de Descarga de Miniatura y Subtítulo.
- El **Título** funciona de la misma manera que en el modo de URL, es decir, permite ver y cambiar el nombre del archivo final.
- En el **Modo** la función es la misma, si queremos Recodificar en **"Video+Audio"** o **"Solo Audio"**. Si importamos un audio de pondrá automaticamente en modo de **"Solo Audio"**, no bloquea el de **"Video+Audio"** pero no es recomendable hacer cambio en ese modo.
- Dentro del **Modo** ahora los menús de Calidades pasarán a ser informativos y muestran la información del video o audio que se importó.
- Los mensajes de advertencias funciona de la misma manera que en el modo URL y en las opciones de Recodificación.
- Ahora beajo del boton de **"Importar Archivo Local para Recodificar"** hay un nuevo botón: **"Limpiar y Volver a Modo URL"**, con este botn volvemos al modo URL de forma simple pero tambien podemos simplemente poner una URL y darle al boton de Analizar para regredar al modo de URL.

Aquí dejo esta cosa jaja, ya en algun futuro lejano haré actualizaciones si no muero antes.

