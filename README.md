# transcriber

Convierte los artículos de blogs exportados desde **Blogger / Google Takeout** a **JSON**, **CSV** y **PDF**.

- Busca exportaciones en una carpeta y en todas sus subcarpetas.
- Exporta los **artículos publicados y los borradores**, estos últimos marcados como tales. Descarta las páginas, el contenido eliminado y la configuración del blog que Blogger incluye en sus exportaciones.
- Antes de convertir cada archivo que tenga **comentarios**, pregunta si incluirlos. Cada comentario aparece bajo su artículo.
- Convierte el HTML de cada artículo en texto limpio, conservando párrafos, saltos de línea, listas y pies de foto.
- Nombra cada exportación como la carpeta que contiene el archivo de origen.
- Funciona con un menú interactivo o directamente desde la línea de comandos, lo que permite usarlo en scripts.
- Si un archivo está dañado, informa del error y sigue con los demás.

---

## Requisitos

- Python **3.10** o superior.

## Instalación

Desde la carpeta del proyecto:

```bash
python -m pip install .
```

> En Windows, usa `py` en lugar de `python`. Si prefieres no instalarlo en tu Python global, [pipx](https://pipx.pypa.io) lo deja aislado: `pipx install .`

Esto instala el comando `transcriber`. También puede ejecutarse como `python -m transcriber`.

---

## Uso

### Menú interactivo

Sin argumentos, el programa busca en `./convert/` (la crea si no existe) y muestra el menú:

```text
$ transcriber

==================================================
                transcriber 0.2.0
==================================================
 Origen:             convert
 Archivos .atom:     2 encontrado(s)
 Carpeta de destino: exports/<nombre_carpeta>
==================================================
1. Convertir a JSON
2. Convertir a CSV
3. Convertir a PDF
4. Convertir a TODOS los formatos
5. Salir
==================================================
Elige una opción (1-5):
```

Si un archivo tiene comentarios, antes de convertirlo se pregunta si incluirlos. Pulsar Intro equivale a «no»:

```text
'mi_blog' tiene 6 comentario(s). ¿Incluirlos en la exportación? [s/N]: s
```

### Indicar otra carpeta o un archivo concreto

```bash
transcriber "C:\Ruta\A\MiCarpetaBlog"
transcriber "C:\MisBlogs\BlogDeViajes\feed.atom"
```

Si indicas una carpeta, se procesan todos los archivos `.atom` que contenga, también los de sus subcarpetas. Si indicas un archivo concreto, se acepta tenga la extensión que tenga, por ejemplo una copia de seguridad `.xml` del formato antiguo de Blogger.

### Sin menú (para scripts)

Con `--formato`, la conversión se hace directamente:

```bash
transcriber convert --formato todos --comentarios
transcriber feed.atom -f json -f csv --sin-comentarios --salida ~/copias-blog
```

| Opción | Descripción |
| --- | --- |
| `ORIGEN` | Archivo `.atom` o carpeta donde buscarlos. Por defecto: `convert`. |
| `-f`, `--formato` | `json`, `csv`, `pdf` o `todos`. Se puede repetir. Sin esta opción se abre el menú. |
| `-o`, `--salida CARPETA` | Carpeta de destino. Por defecto: `exports`. |
| `--comentarios` | Incluye los comentarios sin preguntar. |
| `--sin-comentarios` | Excluye los comentarios sin preguntar. |
| `-q`, `--quiet` | Muestra solo avisos y errores. |
| `--version` | Muestra la versión. |
| `-h`, `--help` | Muestra la ayuda. |

Sin `--comentarios` ni `--sin-comentarios`, la pregunta sobre los comentarios se hace también en este modo. La excepción es cuando no hay un terminal desde el que responder, como en un script; entonces los comentarios no se incluyen.

El programa termina con el código `0` si todo ha ido bien y con `1` si algún archivo no se ha podido convertir o el origen no existe. Si se interrumpe con Ctrl+C, termina con el código `130`.

---

## Qué se exporta

Las exportaciones de Blogger no contienen solo artículos. `transcriber` reconoce los dos formatos de Blogger y separa cada tipo de entrada:

| Se incluye | Opcional | Se omite |
| --- | --- | --- |
| Artículos publicados y borradores | Comentarios, cada uno con su artículo | Páginas, artículos y comentarios eliminados, ajustes del blog y plantilla |

| Formato de origen | Tipo y estado de cada entrada | Artículo de cada comentario |
| --- | --- | --- |
| Google Takeout (`feed.atom`) | `<blogger:type>` y `<blogger:status>` | `<blogger:parent>` |
| Copia de seguridad antigua de Blogger | Categoría `…/kind#post`, `…#comment`… y `<app:draft>` | `<thr:in-reply-to>` |

Al convertir, el programa resume lo que ha leído y lo que ha omitido:

```text
Leyendo 'convert/mi_blog/feed.atom'...
  Omitidas 60 entradas: 57 ajuste(s) del blog, 2 página(s), 1 plantilla(s).
'mi_blog' tiene 6 comentario(s). ¿Incluirlos en la exportación? [s/N]: s
  9 artículo(s) (2 borrador(es)), 6 comentario(s) -> exports/mi_blog
```

Los comentarios aparecen por orden cronológico bajo su artículo. Los que pertenecen a páginas u otras entradas omitidas también se omiten, y se cuentan en el resumen. Los feeds Atom que no proceden de Blogger, y que por tanto no llevan estas marcas, se exportan completos como artículos publicados.

## Resultado

```text
convert/                        <-- Coloca aquí tus exportaciones
├── mi_blog_1/
│   └── feed.atom
└── fotografia_2021/
    └── blog.atom

exports/                        <-- Se crea automáticamente
├── mi_blog_1/
│   ├── mi_blog_1.json
│   ├── mi_blog_1.csv
│   └── mi_blog_1.pdf
└── fotografia_2021/
    ├── fotografia_2021.json
    ├── fotografia_2021.csv
    └── fotografia_2021.pdf
```

Cuando dos archivos `.atom` comparten carpeta, o sus carpetas se llaman igual, las exportaciones se distinguen con un sufijo: `blog`, `blog_2`, `blog_3`… Los archivos y carpetas ocultos (los que empiezan por `.`) se ignoran.

### Formatos

| Formato | Contenido |
| --- | --- |
| **JSON** | Una lista con los campos `titulo`, `fecha`, `enlace`, `contenido_html`, `contenido_texto` y `estado` (`publicado` o `borrador`) de cada artículo, en UTF-8. Si se incluyen los comentarios, cada artículo lleva además una lista `comentarios` con `autor`, `fecha`, `contenido_html` y `contenido_texto`. |
| **CSV** | Los campos `titulo`, `fecha`, `enlace`, `estado` y `contenido_texto`. Si se incluyen los comentarios, una columna `comentarios` los reúne como texto. Se guarda en UTF-8 con BOM para que Excel muestre bien las tildes. |
| **PDF** | Los artículos numerados, con fecha, enlace, texto y, si se incluyen, sus comentarios. Los borradores se marcan como «Borrador (sin publicar)». Incluye cabecera y numeración «Página X de Y». |

Las fechas se guardan tal como vienen en el feed (ISO 8601). En el PDF y en la columna de comentarios del CSV se muestran como `dd/mm/aaaa hh:mm`.

> **Limitación del PDF:** utiliza las fuentes estándar de PDF, que cubren los caracteres del español y de otros idiomas de Europa occidental, además de la tipografía habitual (“comillas”, «comillas», rayas, puntos suspensivos y €). Los caracteres fuera de ese conjunto, como emojis o alfabetos no latinos, aparecen como `?`. JSON y CSV conservan el texto completo.

---

## Desarrollo

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

| Tarea | Comando |
| --- | --- |
| Formato | `ruff format .` |
| Lint | `ruff check .` |
| Tipos | `mypy` |

El repositorio contiene solo lo imprescindible para que la aplicación funcione: `src/`, `pyproject.toml` y este README. Los tests (`tests/`) y la integración continua (`.github/`) se mantienen en local, excluidos mediante `.gitignore`. Donde existan, se ejecutan con `pytest --cov`. Como las herramientas respetan el `.gitignore`, para revisarlos también hay que indicarlos expresamente: `ruff format src tests`, `ruff check src tests` y `mypy src tests`.

### Estructura

```text
src/transcriber/
├── cli.py            Argumentos, menú interactivo y orquestación de la conversión
├── lector.py         Búsqueda de exportaciones y lectura de artículos y comentarios
├── texto.py          Conversión de HTML a texto plano
└── exportadores.py   Generación de JSON, CSV y PDF
```
