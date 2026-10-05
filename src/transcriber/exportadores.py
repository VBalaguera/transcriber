"""Exportación de entradas a JSON, CSV y PDF.

Los comentarios solo se exportan si las entradas los incluyen (``comentarios`` no
es ``None``): en el JSON como lista dentro de cada artículo, en el CSV como una
columna adicional y en el PDF a continuación de cada artículo.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Final

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from transcriber import __version__
from transcriber.lector import BORRADOR, Comentario, Entrada

Exportador = Callable[[Sequence[Entrada], Path], None]

CAMPOS_CSV: Final = ('titulo', 'fecha', 'enlace', 'estado', 'contenido_texto')
CAMPO_COMENTARIOS: Final = 'comentarios'

# Las fuentes estándar de PDF solo cubren windows-1252 (suficiente para el
# español y la tipografía habitual); el resto de caracteres, como los emojis, se
# sustituyen por '?'.
_CODIFICACION_PDF = 'windows-1252'
_CARACTERES_PDF = str.maketrans(
    {
        '\u00a0': ' ',  # espacio de no separación
        '\u200b': None,  # espacio de ancho cero
        '\ufeff': None,  # marca de orden de bytes
        '\r': None,
        '\t': '    ',
    }
)
_FUENTE = 'Helvetica'
_MARGEN_INFERIOR = 15
# Espacio libre (mm) necesario para empezar una entrada sin dejar el título solo
# al pie de la página: título, metadatos y unas líneas de contenido.
_ALTO_MINIMO_ENTRADA = 30
_ALTO_MINIMO_COMENTARIOS = 20
_SANGRIA_COMENTARIOS = 6
_FORMATO_FECHA = '%d/%m/%Y %H:%M'
_GRIS_META = (100, 100, 100)
_GRIS_SEPARADOR = (200, 200, 200)
_SIN_CONTENIDO = '[Sin contenido de texto]'


def exportar_json(entradas: Sequence[Entrada], ruta: Path) -> None:
    """Guarda todas las entradas, incluido su HTML original, en un JSON."""
    with ruta.open('w', encoding='utf-8') as archivo:
        json.dump(
            [_entrada_como_diccionario(entrada) for entrada in entradas],
            archivo,
            ensure_ascii=False,
            indent=4,
        )
        archivo.write('\n')


def exportar_csv(entradas: Sequence[Entrada], ruta: Path) -> None:
    """Guarda las entradas, sin su HTML, en un CSV."""
    con_comentarios = _incluyen_comentarios(entradas)
    campos = (*CAMPOS_CSV, CAMPO_COMENTARIOS) if con_comentarios else CAMPOS_CSV
    # El BOM de 'utf-8-sig' es lo que permite a Excel detectar la codificación.
    with ruta.open('w', encoding='utf-8-sig', newline='') as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        for entrada in entradas:
            fila = {campo: getattr(entrada, campo) for campo in CAMPOS_CSV}
            if con_comentarios:
                fila[CAMPO_COMENTARIOS] = _comentarios_como_texto(
                    entrada.comentarios or ()
                )
            escritor.writerow(fila)


def exportar_pdf(entradas: Sequence[Entrada], ruta: Path) -> None:
    """Genera un PDF con todas las entradas, titulado con el nombre del archivo."""
    pdf = _DocumentoPdf(titulo=ruta.stem)
    pdf.add_page()
    for numero, entrada in enumerate(entradas, start=1):
        if numero > 1:
            _dibujar_separador(pdf)
        _escribir_entrada(pdf, numero, entrada)
    pdf.output(str(ruta))


EXPORTADORES: Final[dict[str, Exportador]] = {
    'json': exportar_json,
    'csv': exportar_csv,
    'pdf': exportar_pdf,
}


def _incluyen_comentarios(entradas: Sequence[Entrada]) -> bool:
    return any(entrada.comentarios is not None for entrada in entradas)


def _entrada_como_diccionario(entrada: Entrada) -> dict[str, object]:
    datos = asdict(entrada)
    if entrada.comentarios is None:
        del datos[CAMPO_COMENTARIOS]
    return datos


def _comentarios_como_texto(comentarios: Sequence[Comentario]) -> str:
    return '\n\n'.join(
        f'{_cabecera_de_comentario(comentario)}:\n{comentario.contenido_texto}'
        for comentario in comentarios
    )


def _cabecera_de_comentario(comentario: Comentario) -> str:
    return f'{comentario.autor} ({_fecha_legible(comentario.fecha)})'


class _DocumentoPdf(FPDF):
    """PDF con cabecera de título y pie con número de página."""

    def __init__(self, titulo: str) -> None:
        super().__init__()
        self.core_fonts_encoding = _CODIFICACION_PDF
        self.titulo = titulo
        self.set_title(titulo)
        self.set_creator(f'transcriber {__version__}')
        self.set_auto_page_break(auto=True, margin=_MARGEN_INFERIOR)

    def header(self) -> None:
        self.set_font(_FUENTE, 'B', 14)
        self.cell(
            0,
            10,
            _texto_pdf(f'Exportación de Blog: {self.titulo}'),
            align='C',
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-_MARGEN_INFERIOR)
        self.set_font(_FUENTE, 'I', 8)
        # fpdf2 sustituye '{nb}' por el número total de páginas.
        self.cell(0, 10, f'Página {self.page_no()} de {{nb}}', align='C')


def _escribir_entrada(pdf: FPDF, numero: int, entrada: Entrada) -> None:
    if pdf.get_y() > _limite_inferior(pdf) - _ALTO_MINIMO_ENTRADA:
        pdf.add_page()

    pdf.set_font(_FUENTE, 'B', 12)
    _parrafo(pdf, f'{numero}. {entrada.titulo}', alto_linea=7)

    meta = f'Fecha: {_fecha_legible(entrada.fecha)}'
    if entrada.estado == BORRADOR:
        meta += ' | Borrador (sin publicar)'
    if entrada.enlace:
        meta += f' | Enlace: {entrada.enlace}'
    pdf.set_font(_FUENTE, 'I', 9)
    pdf.set_text_color(*_GRIS_META)
    _parrafo(pdf, meta)
    pdf.set_text_color(0)
    pdf.ln(2)

    pdf.set_font(_FUENTE, '', 10)
    _parrafo(pdf, entrada.contenido_texto.strip() or _SIN_CONTENIDO)

    if entrada.comentarios:
        _escribir_comentarios(pdf, entrada.comentarios)


def _escribir_comentarios(pdf: FPDF, comentarios: Sequence[Comentario]) -> None:
    pdf.ln(4)
    if pdf.get_y() > _limite_inferior(pdf) - _ALTO_MINIMO_COMENTARIOS:
        pdf.add_page()
    pdf.set_font(_FUENTE, 'B', 10)
    _parrafo(pdf, f'Comentarios ({len(comentarios)})')

    for comentario in comentarios:
        pdf.ln(2)
        pdf.set_font(_FUENTE, 'I', 9)
        pdf.set_text_color(*_GRIS_META)
        _parrafo(pdf, _cabecera_de_comentario(comentario), sangria=_SANGRIA_COMENTARIOS)
        pdf.set_text_color(0)
        pdf.set_font(_FUENTE, '', 9)
        _parrafo(
            pdf,
            comentario.contenido_texto.strip() or _SIN_CONTENIDO,
            sangria=_SANGRIA_COMENTARIOS,
        )


def _dibujar_separador(pdf: FPDF) -> None:
    pdf.ln(6)
    y = pdf.get_y()
    # Pegada al final de la página, la línea quedaría huérfana: se omite.
    if y < _limite_inferior(pdf) - 10:
        pdf.set_draw_color(*_GRIS_SEPARADOR)
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(5)


def _limite_inferior(pdf: FPDF) -> float:
    """Posición vertical a partir de la cual fpdf2 salta de página."""
    return pdf.h - pdf.b_margin


def _fecha_legible(fecha: str) -> str:
    """Muestra una fecha ISO 8601 como 'dd/mm/aaaa hh:mm'; si no lo es, no la toca."""
    try:
        return datetime.fromisoformat(fecha).strftime(_FORMATO_FECHA)
    except ValueError:
        return fecha


def _parrafo(pdf: FPDF, texto: str, alto_linea: float = 5, sangria: float = 0) -> None:
    # multi_cell empieza cada línea en la posición horizontal de la primera.
    pdf.set_x(pdf.l_margin + sangria)
    pdf.multi_cell(
        0, alto_linea, _texto_pdf(texto), new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )


def _texto_pdf(texto: str) -> str:
    """Adapta el texto a la codificación de las fuentes estándar de PDF."""
    # NFC une las letras y las tildes que llegan como caracteres separados (una
    # 'e' seguida de una tilde combinable pasa a ser 'é'), ya que esas tildes
    # sueltas no existen en windows-1252.
    texto = unicodedata.normalize('NFC', texto).translate(_CARACTERES_PDF)
    return texto.encode(_CODIFICACION_PDF, 'replace').decode(_CODIFICACION_PDF)
