"""Conversión de fragmentos HTML a texto plano legible.

Imita de forma simplificada cómo un navegador distribuye el texto:

* los espacios en blanco del código fuente se colapsan en uno solo;
* ``<br>`` fuerza un salto de línea;
* los bloques (``<div>``, ``<li>``...) empiezan en una línea nueva;
* los bloques con margen (``<p>``, ``<h1>``...) quedan separados por una línea
  en blanco;
* el contenido de ``<pre>`` se conserva tal cual.
"""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from bs4.element import NavigableString, PageElement, Tag

_SALTO_DE_LINEA = 1
_LINEA_EN_BLANCO = 2

# Separación mínima que cada etiqueta de bloque impone antes y después de sí.
# fmt: off
_SEPARACION_DE_BLOQUES: dict[str, int] = {
    **dict.fromkeys(
        (
            'address', 'article', 'aside', 'center', 'dd', 'details', 'div',
            'dt', 'figcaption', 'footer', 'form', 'header', 'li', 'main', 'nav',
            'section', 'summary', 'tr',
        ),
        _SALTO_DE_LINEA,
    ),
    **dict.fromkeys(
        (
            'blockquote', 'dl', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'hr', 'ol', 'p', 'pre', 'table', 'ul',
        ),
        _LINEA_EN_BLANCO,
    ),
}
# fmt: on
_ETIQUETAS_OCULTAS = frozenset({'head', 'noscript', 'script', 'style', 'template'})
_CELDAS = frozenset({'td', 'th'})

# Espacios en blanco según la especificación HTML (``&nbsp;`` no lo es).
_ESPACIOS_HTML = re.compile(r'[ \t\n\r\f]+')
_EXCESO_DE_LINEAS_EN_BLANCO = re.compile(r'\n{3,}')
_NBSP = '\xa0'


def html_a_texto(contenido_html: str) -> str:
    """Convierte un fragmento HTML en texto plano con párrafos y saltos de línea."""
    with warnings.catch_warnings():
        # Un artículo cuyo contenido es solo una URL dispararía este aviso.
        warnings.simplefilter('ignore', MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(contenido_html, 'html.parser')

    redactor = _Redactor()
    profundidad_pre = 0
    # Recorrido iterativo: el HTML de algunos blogs anida cientos de niveles y un
    # recorrido recursivo podría superar el límite de recursión de Python.
    pila: list[tuple[PageElement, bool]] = [(soup, True)]
    while pila:
        nodo, entrando = pila.pop()

        if not isinstance(nodo, Tag):
            # Se descartan comentarios, CDATA, declaraciones y similares.
            if type(nodo) is NavigableString:
                redactor.escribir(nodo, preformateado=profundidad_pre > 0)
            continue

        nombre = nodo.name
        if nombre in _ETIQUETAS_OCULTAS:
            continue
        if nombre == 'br':
            redactor.salto_de_linea()
            continue
        if nombre == 'pre':
            profundidad_pre += 1 if entrando else -1
        if nombre in _CELDAS:
            redactor.separar_palabras()
        redactor.separar_bloque(_SEPARACION_DE_BLOQUES.get(nombre, 0))

        if entrando:
            pila.append((nodo, False))
            pila.extend((hijo, True) for hijo in reversed(nodo.contents))

    return redactor.texto()


class _Redactor:
    """Acumula fragmentos de texto aplicando las reglas de espaciado de HTML.

    Los espacios y saltos de línea no se escriben en cuanto se piden, sino justo
    antes del siguiente fragmento visible. Así nunca quedan espacios al principio
    o al final de una línea y varios bloques seguidos no generan saltos de más.
    """

    def __init__(self) -> None:
        self._partes: list[str] = []
        self._saltos_pendientes = 0
        self._espacio_pendiente = False

    def escribir(self, texto: str, *, preformateado: bool) -> None:
        if preformateado:
            self._emitir(texto)
            return

        colapsado = _ESPACIOS_HTML.sub(' ', texto.replace(_NBSP, ' '))
        if colapsado.startswith(' '):
            self._espacio_pendiente = True
        palabras = colapsado.strip(' ')
        if palabras:
            self._emitir(palabras)
            self._espacio_pendiente = colapsado.endswith(' ')
        elif _NBSP in texto and self._al_inicio_de_linea():
            # Un ``&nbsp;`` aislado ocupa la línea aunque no tenga texto: Blogger
            # lo usa para dejar líneas vacías intencionadas (``<div>&nbsp;</div>``).
            self._emitir('')

    def separar_palabras(self) -> None:
        self._espacio_pendiente = True

    def separar_bloque(self, saltos: int) -> None:
        self._saltos_pendientes = max(self._saltos_pendientes, saltos)

    def salto_de_linea(self) -> None:
        self._saltos_pendientes = min(self._saltos_pendientes + 1, _LINEA_EN_BLANCO)

    def texto(self) -> str:
        texto = ''.join(self._partes).strip('\n')
        return _EXCESO_DE_LINEAS_EN_BLANCO.sub('\n\n', texto)

    def _al_inicio_de_linea(self) -> bool:
        return not self._partes or self._saltos_pendientes > 0

    def _emitir(self, fragmento: str) -> None:
        if self._partes:
            if self._saltos_pendientes:
                self._partes.append('\n' * self._saltos_pendientes)
            elif self._espacio_pendiente:
                self._partes.append(' ')
        self._partes.append(fragmento)
        self._saltos_pendientes = 0
        self._espacio_pendiente = False
