# Convertidor de Blogs (Google Takeout a JSON/CSV/PDF)

Herramienta en Python para extraer entradas de blogs desde archivos `.atom` de Google Takeout / Blogger y exportarlas a JSON, CSV y PDF.

El script toma **el nombre de la carpeta contenedora** del archivo `.atom` para nombrar la subcarpeta de destino y los archivos generados (`.json`, `.csv`, `.pdf`).

---

## Estructura del Proyecto

```text
transcriber/
│
├── convert/                  <-- Coloca aquí las carpetas o archivos .atom
│   ├── mi_blog_1/
│   │   └── feed.atom         --> Genera exports/mi_blog_1/mi_blog_1.json, .csv, .pdf
│   └── fotografia_2021/
│       └── blog.atom         --> Genera exports/fotografia_2021/fotografia_2021.json, .csv, .pdf
│
├── exports/                  <-- Se creará automáticamente al exportar
│   ├── mi_blog_1/
│   │   ├── mi_blog_1.json
│   │   ├── mi_blog_1.csv
│   │   └── mi_blog_1.pdf
│   └── fotografia_2021/
│       ├── fotografia_2021.json
│       ├── fotografia_2021.csv
│       └── fotografia_2021.pdf
│
├── convert.py                <-- Script principal
├── requirements.txt          <-- Lista de librerías necesarias
└── README.md                 <-- Manual de uso
```

---

## Instalación

1. Asegúrate de tener **Python 3.8+** instalado.
2. Abre la terminal en la carpeta del proyecto y ejecuta:

```bash
pip install -r requirements.txt
```

---

## Formas de Uso

### 1. Modo Interactivo (Carpeta por defecto `./convert/`)

Si ejecutas el programa sin argumentos:

```bash
py convert.py
```

Escaneará la carpeta `./convert/` (incluyendo sus subcarpetas) e iniciará el menú interactivo:

```text
==================================================
     CONVERTIDOR MULTI-BLOG (FEED.ATOM)
==================================================
 Origen detectado:   convert
 Archivos .atom:     2 encontrado(s)
 Carpeta de destino: ./exports/<nombre_carpeta>/
==================================================
1. Convertir a JSON
2. Convertir a CSV
3. Convertir a PDF
4. Convertir a TODOS los formatos
5. Salir
==================================================
```

---

### 2. Pasar un directorio por parámetro

Puedes indicarle al programa la ruta de cualquier carpeta que contenga uno o varios archivos `.atom`:

```bash
py convert.py "C:\Ruta\A\MiCarpetaBlog"
```

*Tomará el nombre de la carpeta contenedora (`MiCarpetaBlog`) para nombrar la carpeta de salida y los archivos exportados (`MiCarpetaBlog.json`, `MiCarpetaBlog.csv`, `MiCarpetaBlog.pdf`).*

---

### 3. Pasar un archivo `.atom` específico

Si le pasas la ruta directa de un archivo `.atom`:

```bash
py convert.py "C:\MisBlogs\BlogDeViajes\feed.atom"
```

*El script identificará la carpeta que alberga dicho archivo (`BlogDeViajes`) y usará ese nombre para generar la exportación en `./exports/BlogDeViajes/`.*