import csv
import html
import json
import os
import re
import sys
import feedparser
from bs4 import BeautifulSoup
from fpdf import FPDF

CARPETA_ENTRADA_DEFECTO = 'convert'
CARPETA_SALIDA = 'exports'


def limpiar_html(html_content):
    """Transforma HTML a texto respetando párrafos, saltos de línea y espacios."""
    if not html_content:
        return ""

    html_content = html.unescape(html_content)
    soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup.find_all(['br', 'hr']):
        tag.replace_with('\n')

    for tag in soup.find_all(
        ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']
    ):
        tag.insert_before('\n')
        tag.insert_after('\n')

    texto = soup.get_text(separator=" ", strip=True)
    texto = re.sub(r'\n[ \t\n]*\n', '\n\n', texto)
    texto = re.sub(r'[ \t]+', ' ', texto)

    return texto.strip()


def sanitizar_texto_pdf(texto):
    """Limpia caracteres invisibles y los reemplaza por compatibles con Latin-1."""
    if not texto:
        return ""

    reemplazos = {
        '“': '"',
        '”': '"',
        '‘': "'",
        '’': "'",
        '—': '-',
        '–': '-',
        '…': '...',
        '«': '"',
        '»': '"',
        '\xa0': ' ',
        '\u200b': '',
        '\r': '',
        '\t': ' ',
    }

    for orig, reemplazo in reemplazos.items():
        texto = texto.replace(orig, reemplazo)

    return texto.encode('latin-1', 'replace').decode('latin-1')


def dividir_palabras_largas(texto, max_len=30):
    """Inserta espacios en cadenas largas (como URLs) para no desbordar el PDF."""
    if not texto:
        return ""

    def romper_cadena(match):
        word = match.group(0)
        return ' '.join(
            [word[i : i + max_len] for i in range(0, len(word), max_len)]
        )

    patron = r'\S{' + str(max_len + 1) + r',}'
    return re.sub(patron, romper_cadena, texto)


def cargar_entradas(ruta_archivo):
    """Lee y procesa un archivo .atom específico."""
    nombre_fichero = os.path.basename(ruta_archivo)
    print(f"\n⏳ Leyendo y procesando '{nombre_fichero}'...")
    feed = feedparser.parse(ruta_archivo)

    if not feed.entries:
        print(
            f"❌ No se encontraron entradas o el archivo '{nombre_fichero}' no es un Atom válido."
        )
        return None

    entradas = []
    for entry in feed.entries:
        if 'content' in entry and len(entry.content) > 0:
            contenido_html = entry.content[0].value
        elif 'summary' in entry:
            contenido_html = entry.summary
        else:
            contenido_html = ''

        contenido_texto = limpiar_html(contenido_html)

        entradas.append({
            'titulo': entry.get('title', 'Sin título'),
            'fecha': entry.get('published', 'Sin fecha'),
            'enlace': entry.get('link', ''),
            'contenido_html': contenido_html,
            'contenido_texto': contenido_texto,
        })

    print(
        f"✅ Se procesaron {len(entradas)} entradas correctamente de '{nombre_fichero}'."
    )
    return entradas


def exportar_json(entradas, carpeta_destino, nombre_base):
    nombre_archivo = os.path.join(carpeta_destino, f"{nombre_base}.json")
    print(f"  ⏳ Generando JSON: {nombre_archivo}")
    with open(nombre_archivo, 'w', encoding='utf-8') as f:
        json.dump(entradas, f, ensure_ascii=False, indent=4)
    print("  ✅ Archivo JSON creado.")


def exportar_csv(entradas, carpeta_destino, nombre_base):
    nombre_archivo = os.path.join(carpeta_destino, f"{nombre_base}.csv")
    print(f"  ⏳ Generando CSV: {nombre_archivo}")
    campos = ['titulo', 'fecha', 'enlace', 'contenido_texto']
    with open(nombre_archivo, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for entrada in entradas:
            writer.writerow({
                'titulo': entrada['titulo'],
                'fecha': entrada['fecha'],
                'enlace': entrada['enlace'],
                'contenido_texto': entrada['contenido_texto'],
            })
    print("  ✅ Archivo CSV creado.")


def exportar_pdf(entradas, carpeta_destino, nombre_base):
    nombre_archivo = os.path.join(carpeta_destino, f"{nombre_base}.pdf")
    print(f"  ⏳ Generando PDF: {nombre_archivo}")

    class PDF(FPDF):

        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.cell(
                0,
                10,
                sanitizar_texto_pdf(f'Exportación de Blog: {nombre_base}'),
                border=0,
                new_x="LMARGIN",
                new_y="NEXT",
                align='C',
            )
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(
                0,
                10,
                sanitizar_texto_pdf(f'Página {self.page_no()}'),
                border=0,
                new_x="LMARGIN",
                new_y="NEXT",
                align='C',
            )

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    for idx, entrada in enumerate(entradas, start=1):
        pdf.set_x(pdf.l_margin)

        # Título
        pdf.set_font('Helvetica', 'B', 12)
        titulo_limpio = dividir_palabras_largas(entrada['titulo'], max_len=30)
        titulo = sanitizar_texto_pdf(f"{idx}. {titulo_limpio}")
        pdf.multi_cell(0, 7, titulo, new_x="LMARGIN", new_y="NEXT")

        # Meta información
        pdf.set_font('Helvetica', 'I', 9)
        pdf.set_text_color(100, 100, 100)
        enlace_limpio = dividir_palabras_largas(entrada['enlace'], max_len=30)
        meta = sanitizar_texto_pdf(
            f"Fecha: {entrada['fecha']} | Enlace: {enlace_limpio}"
        )
        pdf.multi_cell(0, 5, meta, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # Contenido
        pdf.set_font('Helvetica', '', 10)
        texto_procesado = dividir_palabras_largas(
            entrada['contenido_texto'], max_len=40
        )
        contenido = sanitizar_texto_pdf(texto_procesado)

        if contenido.strip():
            pdf.multi_cell(0, 5, contenido, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(
                0,
                5,
                sanitizar_texto_pdf('[Sin contenido de texto]'),
                new_x="LMARGIN",
                new_y="NEXT",
            )

        # Separador entre entradas
        pdf.ln(6)
        pdf.set_draw_color(200, 200, 200)
        y_actual = pdf.get_y()
        if y_actual < (pdf.h - pdf.b_margin - 10):
            pdf.line(10, y_actual, 200, y_actual)
            pdf.ln(5)

    pdf.output(nombre_archivo)
    print("  ✅ Archivo PDF creado.")


def obtener_lista_archivos(origen_param=None):
    """
    Determina los archivos .atom a procesar y usa el nombre de la carpeta contenedora
    para nombrar los archivos exportados y la subcarpeta de destino.
    """
    if not origen_param:
        origen_param = CARPETA_ENTRADA_DEFECTO
        if not os.path.exists(origen_param):
            os.makedirs(origen_param, exist_ok=True)

    origen_param = origen_param.strip('"\'')

    if not os.path.exists(origen_param):
        print(f"❌ Error: La ruta '{origen_param}' no existe.")
        return [], origen_param

    archivos_encontrados = []
    nombres_usados = {}

    def registrar_archivo(ruta_abs):
        carpeta_padre = os.path.dirname(ruta_abs)
        nombre_carpeta = os.path.basename(carpeta_padre)

        if not nombre_carpeta:
            nombre_carpeta = "export"

        # Si hay más de un archivo .atom en la misma carpeta, se desambigua con un índice
        if nombre_carpeta in nombres_usados:
            nombres_usados[nombre_carpeta] += 1
            nombre_base = f"{nombre_carpeta}_{nombres_usados[nombre_carpeta]}"
        else:
            nombres_usados[nombre_carpeta] = 1
            nombre_base = nombre_carpeta

        archivos_encontrados.append((ruta_abs, nombre_base))

    if os.path.isdir(origen_param):
        for root, _, files in os.walk(origen_param):
            for f in files:
                if f.lower().endswith('.atom'):
                    ruta_completa = os.path.abspath(os.path.join(root, f))
                    registrar_archivo(ruta_completa)

    elif os.path.isfile(origen_param):
        if origen_param.lower().endswith('.atom'):
            ruta_completa = os.path.abspath(origen_param)
            registrar_archivo(ruta_completa)
        else:
            print(f"⚠️ El archivo '{origen_param}' no tiene extensión .atom.")

    return archivos_encontrados, origen_param


def procesar_conversiones(opcion, lista_archivos):
    if not lista_archivos:
        print("\n⚠️ No se encontraron archivos .atom para procesar.")
        return

    for ruta_atom, nombre_base in lista_archivos:
        carpeta_destino = os.path.join(CARPETA_SALIDA, nombre_base)
        os.makedirs(carpeta_destino, exist_ok=True)

        entradas = cargar_entradas(ruta_atom)
        if not entradas:
            continue

        print(
            f"\n⚙️ Nombre de la carpeta utilizado: '{nombre_base}' -> Salida: '{carpeta_destino}/'"
        )

        if opcion in ['1', '4']:
            exportar_json(entradas, carpeta_destino, nombre_base)

        if opcion in ['2', '4']:
            exportar_csv(entradas, carpeta_destino, nombre_base)

        if opcion in ['3', '4']:
            try:
                exportar_pdf(entradas, carpeta_destino, nombre_base)
            except Exception as e:
                print(f"  ❌ Error al generar PDF para '{nombre_base}': {e}")

    print("\n🎉 ¡Proceso finalizado!")


def menu_principal():
    origen_arg = sys.argv[1] if len(sys.argv) > 1 else None

    lista_archivos, origen_usado = obtener_lista_archivos(origen_arg)

    while True:
        print("\n" + "=" * 50)
        print("     transcriber")
        print("=" * 50)
        print(f" Origen detectado:   {origen_usado}")
        print(f" Archivos .atom:     {len(lista_archivos)} encontrado(s)")
        print(f" Carpeta de destino: ./{CARPETA_SALIDA}/<nombre_carpeta>/")
        print("=" * 50)
        print("1. Convertir a JSON")
        print("2. Convertir a CSV")
        print("3. Convertir a PDF")
        print("4. Convertir a TODOS los formatos")
        print("5. Salir")
        print("=" * 50)

        if not lista_archivos:
            print(
                "\n⚠️️ No se han encontrado archivos .atom en el origen indicado."
            )
            print(
                "Asegúrate de colocar archivos .atom en la ruta o pasársela como parámetro."
            )

        opcion = input("Elige una opción (1-5): ").strip()

        if opcion in ['1', '2', '3', '4']:
            if lista_archivos:
                procesar_conversiones(opcion, lista_archivos)
            else:
                print("❌ No hay archivos para procesar.")
        elif opcion == '5':
            print("\nCerrando transcriber")
            break
        else:
            print(
                "⚠ Opción no válida. Por favor introduce un número entre 1 y 5."
            )


if __name__ == '__main__':
    menu_principal()