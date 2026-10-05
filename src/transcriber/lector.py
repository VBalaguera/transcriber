"""Búsqueda y lectura de archivos Atom exportados desde Blogger / Google Takeout.

Las exportaciones de Blogger no contienen solo artículos: los mezclan con sus
comentarios, con las páginas del blog, con contenido eliminado y, en el formato
antiguo, con la configuración y la plantilla. Cada formato los distingue así:

* Google Takeout (``feed.atom``): ``<blogger:type>`` (``POST``, ``PAGE``,
  ``COMMENT``), ``<blogger:status>`` (``DRAFT``, ``DELETED``...) y, en cada
  comentario, ``<blogger:parent>`` con el identificador de su artículo.
* Copia de seguridad antigua de Blogger: una categoría con el esquema
  ``http://schemas.google.com/g/2005#kind`` (``...#post``, ``...#comment``,
  ``...#settings``...), ``<app:draft>yes</app:draft>`` en los borradores y, en
  cada comentario, ``<thr:in-reply-to ref="...">`` con el identificador de su
  artículo.

Se leen los artículos, publicados o en borrador, cada uno con sus comentarios.
Las entradas de un feed Atom genérico, sin estas marcas, se consideran todas
artículos publicados.
"""

from __future__ import annotations

import html
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import feedparser

from transcriber.texto import html_a_texto

logger = logging.getLogger(__name__)

EXTENSION_ATOM = '.atom'
SIN_TITULO = 'Sin título'
SIN_FECHA = 'Sin fecha'
SIN_AUTOR = 'Anónimo'

Estado = Literal['publicado', 'borrador']
PUBLICADO: Final = 'publicado'
BORRADOR: Final = 'borrador'

_NOMBRE_POR_DEFECTO = 'export'
_TIPO_TEXTO_PLANO = 'text/plain'

_ESQUEMA_DE_TIPO_ANTIGUO = 'http://schemas.google.com/g/2005#kind'
_TIPO_ARTICULO = 'post'
_TIPO_COMENTARIO = 'comment'
_ESTADO_BORRADOR = 'draft'
_ESTADO_ELIMINADO = 'deleted'
# Motivo de omisión -> descripción para el resumen que se muestra al usuario.
_DESCRIPCION_DE_OMISIONES = {
    'page': 'página(s)',
    'settings': 'ajuste(s) del blog',
    'template': 'plantilla(s)',
    'articulo-eliminado': 'artículo(s) eliminado(s)',
    'comentario-eliminado': 'comentario(s) eliminado(s)',
    'comentario-huerfano': 'comentario(s) de entradas que no se exportan',
}


class FeedInvalidoError(Exception):
    """El archivo no es un feed Atom legible o no contiene ningún artículo."""


@dataclass(frozen=True, slots=True)
class Comentario:
    """Un comentario de un artículo."""

    autor: str
    fecha: str
    contenido_html: str
    contenido_texto: str


@dataclass(frozen=True, slots=True)
class Entrada:
    """Un artículo del blog, listo para exportar."""

    titulo: str
    fecha: str
    enlace: str
    contenido_html: str
    contenido_texto: str
    estado: Estado = PUBLICADO
    # Por orden cronológico; None cuando se ha decidido no exportarlos.
    comentarios: tuple[Comentario, ...] | None = None


@dataclass(frozen=True, slots=True)
class ArchivoAtom:
    """Un archivo a convertir y el nombre (único) que tendrá su exportación."""

    ruta: Path
    nombre_base: str


def buscar_archivos_atom(origen: Path) -> list[ArchivoAtom]:
    """Devuelve los archivos a convertir que hay en ``origen``.

    Si ``origen`` es una carpeta, se buscan archivos ``.atom`` en ella y en sus
    subcarpetas, ignorando los ocultos. Si es un archivo, se acepta sea cual sea
    su extensión, ya que el usuario lo ha indicado expresamente.

    Cada exportación se nombra como la carpeta que contiene el archivo; cuando
    dos archivos comparten carpeta (o nombre de carpeta) se añade un sufijo
    numérico (``blog``, ``blog_2``...). El resultado está ordenado por ruta para
    que los nombres asignados sean siempre los mismos.

    Raises:
        FileNotFoundError: si ``origen`` no existe.
    """
    origen = origen.resolve()
    if origen.is_dir():
        rutas = sorted(
            ruta
            for ruta in origen.rglob('*')
            if ruta.suffix.lower() == EXTENSION_ATOM
            and ruta.is_file()
            and not _es_oculta(ruta.relative_to(origen))
        )
    elif origen.is_file():
        rutas = [origen]
    else:
        raise FileNotFoundError(f"La ruta '{origen}' no existe.")
    return _asignar_nombres(rutas)


def cargar_entradas(ruta: Path) -> list[Entrada]:
    """Lee un archivo Atom y devuelve sus artículos, cada uno con sus comentarios.

    Se incluyen los artículos publicados y los borradores. Se omiten, informando
    de cuántas son, las páginas, el contenido eliminado y el resto de entradas
    que no son artículos ni comentarios.

    Raises:
        FeedInvalidoError: si el archivo no es un feed válido o no contiene
            ningún artículo.
        OSError: si el archivo no se puede leer.
    """
    # Se abre el archivo explícitamente: si se le pasa una ruta, feedparser
    # interpreta el propio texto de la ruta como XML cuando el archivo no existe.
    with ruta.open('rb') as archivo:
        feed = feedparser.parse(archivo)

    if not feed.entries:
        detalle = f' ({feed.bozo_exception})' if feed.bozo else ''
        raise FeedInvalidoError(
            f"'{ruta.name}' no contiene entradas o no es un feed Atom válido{detalle}."
        )
    if feed.bozo:
        logger.warning(
            "'%s' tiene errores de formato (%s); se usarán las %d entradas legibles.",
            ruta.name,
            feed.bozo_exception,
            len(feed.entries),
        )

    articulos: list[Any] = []
    comentarios_por_articulo: defaultdict[str, list[Any]] = defaultdict(list)
    omitidas: Counter[str] = Counter()
    for entrada in feed.entries:
        tipo = _tipo_de_entrada(entrada)
        eliminada = _estado_en_blogger(entrada) == _ESTADO_ELIMINADO
        if tipo == _TIPO_ARTICULO:
            if eliminada:
                omitidas['articulo-eliminado'] += 1
            else:
                articulos.append(entrada)
        elif tipo == _TIPO_COMENTARIO:
            if eliminada:
                omitidas['comentario-eliminado'] += 1
            elif articulo := _articulo_comentado(entrada):
                comentarios_por_articulo[articulo].append(entrada)
            else:
                omitidas['comentario-huerfano'] += 1
        else:
            omitidas[tipo] += 1

    entradas = [
        _crear_entrada(articulo, comentarios_por_articulo.pop(articulo.get('id'), []))
        for articulo in articulos
    ]
    # Los que quedan comentan páginas u otras entradas que no se exportan.
    if huerfanos := sum(map(len, comentarios_por_articulo.values())):
        omitidas['comentario-huerfano'] += huerfanos

    if omitidas:
        logger.info(
            '  Omitidas %d entradas: %s.',
            omitidas.total(),
            _describir_omisiones(omitidas),
        )
    if not entradas:
        raise FeedInvalidoError(f"'{ruta.name}' no contiene artículos.")
    return entradas


def _crear_entrada(entrada: Any, comentarios: list[Any]) -> Entrada:
    contenido_html, contenido_texto = _contenido(entrada)
    return Entrada(
        titulo=entrada.get('title', '').strip() or SIN_TITULO,
        fecha=_fecha(entrada),
        enlace=entrada.get('link', ''),
        contenido_html=contenido_html,
        contenido_texto=contenido_texto,
        estado=BORRADOR if _es_borrador(entrada) else PUBLICADO,
        comentarios=tuple(
            _crear_comentario(comentario)
            for comentario in sorted(comentarios, key=_orden_cronologico)
        ),
    )


def _crear_comentario(entrada: Any) -> Comentario:
    contenido_html, contenido_texto = _contenido(entrada)
    autor = (entrada.get('author_detail') or {}).get('name') or ''
    return Comentario(
        autor=autor.strip() or SIN_AUTOR,
        fecha=_fecha(entrada),
        contenido_html=contenido_html,
        contenido_texto=contenido_texto,
    )


def _contenido(entrada: Any) -> tuple[str, str]:
    """Devuelve el contenido de la entrada como HTML y como texto plano."""
    if entrada.get('content'):
        detalle = entrada.content[0]
    else:
        detalle = entrada.get('summary_detail') or {}
    contenido: str = detalle.get('value', '')

    if detalle.get('type') == _TIPO_TEXTO_PLANO:
        return html.escape(contenido), contenido.strip()
    return contenido, html_a_texto(contenido)


def _fecha(entrada: Any) -> str:
    return str(entrada.get('published') or entrada.get('updated') or SIN_FECHA)


def _orden_cronologico(entrada: Any) -> tuple[int, ...]:
    # Las fechas *_parsed están en UTC: ordenan bien aunque cambie la zona horaria.
    fecha = entrada.get('published_parsed') or entrada.get('updated_parsed')
    return tuple(fecha[:6]) if fecha else ()


def _tipo_de_entrada(entrada: Any) -> str:
    """Devuelve el tipo de entrada de Blogger ('post', 'comment', 'page'...).

    Las entradas que no indican su tipo se consideran artículos.
    """
    if tipo := entrada.get('blogger_type'):
        return str(tipo).lower()
    for categoria in entrada.get('tags', []):
        if categoria.get('scheme') == _ESQUEMA_DE_TIPO_ANTIGUO:
            return str(categoria.get('term', '')).rpartition('#')[2].lower()
    return _TIPO_ARTICULO


def _estado_en_blogger(entrada: Any) -> str:
    return str(entrada.get('blogger_status', '')).lower()


def _es_borrador(entrada: Any) -> bool:
    return (
        _estado_en_blogger(entrada) == _ESTADO_BORRADOR
        or str(entrada.get('app_draft', '')).lower() == 'yes'
    )


def _articulo_comentado(comentario: Any) -> str:
    """Devuelve el identificador del artículo al que pertenece el comentario."""
    if padre := comentario.get('blogger_parent'):
        return str(padre).strip()
    respuesta_a = comentario.get('thr_in-reply-to') or {}
    return str(respuesta_a.get('ref', ''))


def _describir_omisiones(omitidas: Counter[str]) -> str:
    return ', '.join(
        f'{cantidad} {_DESCRIPCION_DE_OMISIONES.get(motivo, f"de tipo {motivo!r}")}'
        for motivo, cantidad in omitidas.most_common()
    )


def _es_oculta(ruta_relativa: Path) -> bool:
    """Indica si la ruta o alguna de sus carpetas es oculta (``.git``, ``._x``...)."""
    return any(parte.startswith('.') for parte in ruta_relativa.parts)


def _asignar_nombres(rutas: list[Path]) -> list[ArchivoAtom]:
    usados: set[str] = set()
    archivos = []
    for ruta in rutas:
        base = ruta.parent.name or _NOMBRE_POR_DEFECTO
        nombre, indice = base, 1
        while nombre in usados:
            indice += 1
            nombre = f'{base}_{indice}'
        usados.add(nombre)
        archivos.append(ArchivoAtom(ruta=ruta, nombre_base=nombre))
    return archivos
