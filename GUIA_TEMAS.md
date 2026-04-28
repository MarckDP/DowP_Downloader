# 🎨 Guía Maestra: Creación de Temas para DowP Downloader

Esta guía explica cómo funciona el motor de temas **v5.1** de DowP. El sistema permite personalizar cada aspecto visual de la aplicación mediante un archivo JSON, utilizando un formato dual que soporta **Modo Claro** y **Modo Oscuro** simultáneamente.

---

## 🏗️ Estructura del Archivo JSON
Un tema de DowP se divide en tres secciones principales:
1.  **Metadatos (`_INSTRUCCIONES_DOWP` y `ThemeName`)**: Información técnica y nombre del tema.
2.  **Colores Personalizados (`CustomColors`)**: Colores específicos para botones y estados lógicos de la aplicación.
3.  **Widgets Core (`CTk...`)**: Estilos base para todos los componentes de CustomTkinter.

---

## 🔴 1. CustomColors (Colores Lógicos)

Esta sección es el corazón del tema. Casi todas las propiedades aceptan el formato `["Modo Claro", "Modo Oscuro"]`.

### 🔘 Botones de Acción (Fondo y Texto)
Para cada tipo de botón, puedes definir tanto el color de fondo (`_BTN`) como el del texto (`_TEXT`) y el color al pasar el ratón (`_HOVER`).

| Propiedad Base | Descripción | Asignado a... |
| :--- | :--- | :--- |
| `DOWNLOAD_...` | Éxito / Acción Principal. | Botón "Descargar", "Añadir Modelo", "Importar". |
| `ANALYZE_...` | Proceso / Búsqueda. | Botón "Analizar", "Exportar", "Buscar Actualizaciones". |
| `CANCEL_...` | Peligro / Cancelación. | Botón "Cancelar", "Borrar", "Eliminar". |
| `SECONDARY_...`| Utilidad / Neutral. | Botones de carpetas, limpiar campos, cookies. |
| `TERTIARY_...` | Soporte / Herramientas. | Botones pequeños, visor de plantillas, iconos. |

### 🖼️ Interfaz y Paneles de Ajustes
Nuevas propiedades para el rediseño de la interfaz en la v5.1.

| Propiedad | Descripción |
| :--- | :--- |
| `CONFIG_CARD_BG` | Fondo de las "tarjetas" de opciones en los Ajustes. |
| `CONFIG_CARD_BORDER` | Borde de las tarjetas de opciones. |
| `CONFIG_CARD_RADIUS` | Radio de las esquinas de las tarjetas (número entero). |
| `MENU_NORMAL_TEXT` | Color del texto de los botones del menú lateral (inactivos). |
| `MENU_SELECTED_BG` | Fondo del botón del menú lateral cuando está seleccionado. |

### 🖥️ Consola de Diagnóstico
| Propiedad | Descripción |
| :--- | :--- |
| `CONSOLE_BG` | Fondo de la caja de texto de la consola. |
| `CONSOLE_TEXT` | Color del texto principal (logs) de la consola. |

### 🖼️ Visor y Listas (Image Tools / Lotes)
| Propiedad | Descripción |
| :--- | :--- |
| `LISTBOX_BG` | Fondo de las listas de archivos. |
| `LISTBOX_TEXT` | Color del texto de los archivos. |
| `LISTBOX_SELECTED_BG`| Resaltado del archivo seleccionado. |
| `VIEWER_BG` | Fondo del área de previsualización de imágenes. |

---

## 🎨 2. Widgets Core (CustomTkinter)

Aquí se definen los estilos base globales. Si un widget no tiene un color específico en `CustomColors`, usará estos valores.

### 📐 Propiedades por Widget
- `fg_color`: Color de fondo principal.
- `text_color`: Color del texto.
- `border_color`: Color del borde (**Importante: No usar "transparent" en bordes**).
- `button_color`: Color del botón (para componentes como ComboBox o OptionMenu).

| Componente | Uso Principal |
| :--- | :--- |
| `CTk` | Fondo de la ventana principal. |
| `CTkFrame` | Fondo de los paneles principales detrás de las tarjetas. |
| `CTkEntry` | Campos de entrada de texto. |
| `CTkSwitch` | Interruptores de opciones. |
| `CTkProgressBar`| Barras de progreso de descarga. |

---

## 🚀 Ejemplo de Skeleton (v5.1)

Copia este código y úsalo como base para tu nuevo tema:

```json
{
  "_INSTRUCCIONES_DOWP": "v5.1 - Engine de Temas Dinámicos",
  "ThemeName": "Mi Tema Personalizado",
  "CustomColors": {
    "DOWNLOAD_BTN": ["#2ecc71", "#27ae60"],
    "DOWNLOAD_TEXT": ["#ffffff", "#ffffff"],
    "CONFIG_CARD_BG": ["#ffffff", "#1e1e1e"],
    "CONFIG_CARD_BORDER": ["#dddddd", "#333333"],
    "CONSOLE_BG": ["#f8f9fa", "#0c0c0c"],
    "CONSOLE_TEXT": ["#333333", "#00ff00"],
    "MENU_SELECTED_BG": ["#e0e0e0", "#2d2d2d"],
    "STATUS_SUCCESS": ["#28a745", "#28a745"],
    "STATUS_ERROR": ["#dc3545", "#dc3545"]
  },
  "CTk": {
    "fg_color": ["#f0f2f5", "#121212"]
  },
  "CTkFrame": {
    "fg_color": ["#ffffff", "#181818"],
    "corner_radius": 10
  },
  "CTkFont": {
    "Windows": { "family": "Segoe UI", "size": 13, "weight": "normal" }
  }
}
```

---

## 💡 Consejos de Oro
1.  **Herencia**: Si no defines un color en `CustomColors`, DowP buscará en `Widgets Core`. Si tampoco está ahí, usará el color por defecto de la aplicación.
2.  **Modo de Prueba**: Usa el botón "📁" en Ajustes para abrir la carpeta de temas, pega tu JSON allí y reinicia el programa o usa el menú para cambiar de tema al instante.
3.  **Contraste**: Siempre asegúrate de que el `DOWNLOAD_TEXT` contraste bien con el `DOWNLOAD_BTN`.
