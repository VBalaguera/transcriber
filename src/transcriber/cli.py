"""Interfaz de línea de comandos: argumentos, menú interactivo y conversión."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

from fpdf.errors import FPDFException

from transcriber import __version__
from transcriber.exportadores import EXPORTADORES
from transcriber.lector import (
    BORRADOR,
    EXTENSION_ATOM,
    ArchivoAtom,
    Entrada,
    FeedInvalidoError,
    buscar_archivos_atom,
    cargar_entradas,
)

logger = logging.getLogger(__name__)

CARPETA_ENTRADA_POR_DEFECTO = Path('convert')
CARPETA_SALIDA_POR_DEFECTO = Path('exports')
FORMATOS = tuple(EXPORTADORES)
_TODOS = 'todos'

EXITO = 0
ERROR = 1
INTERRUMPIDO = 130

_OPCIONES_MENU: dict[str, tuple[str, tuple[str, ...]]] = {
    '1': ('Convertir a JSON', ('json',)),
    '2': ('Convertir a CSV', ('csv',)),
    '3': ('Convertir a PDF', ('pdf',)),
    '4': ('Convertir a TODOS los formatos', FORMATOS),
}
_OPCION_SALIR = '5'
_SEPARADOR = '=' * 50
_RESPUESTAS_SI = frozenset({'s', 'si', 'sí', 'y', 'yes'})
_RESPUESTAS_NO = frozenset({'', 'n', 'no'})


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta el programa y devuelve el código de salida."""
    args = _crear_parser().parse_args(argv)
    _configurar_logging(silencioso=args.quiet)
    try:
        return _ejecutar(args.origen, args.formato, args.salida, args.comentarios)
    except KeyboardInterrupt:
        print('\nOperación cancelada.', file=sys.stderr)
        return INTERRUMPIDO


def _ejecutar(
    origen: Path | None,
    formatos: list[str] | None,
    salida: Path,
    comentarios: bool | None,
) -> int:
    """Lanza la conversión. ``comentarios`` es None si hay que preguntar."""
    origen = origen or _preparar_carpeta_por_defecto()
    try:
        archivos = buscar_archivos_atom(origen)
    except FileNotFoundError as error:
        logger.error('%s', error)
        return ERROR

    if formatos is None:
        return _menu_interactivo(origen, archivos, salida, comentarios)
    if not archivos:
        logger.error(
            "No se han encontrado archivos %s en '%s'.", EXTENSION_ATOM, origen
        )
        return ERROR
    if comentarios is None and not sys.stdin.isatty():
        # Sin un terminal (por ejemplo, en un script) no se puede preguntar.
        comentarios = False
    return _convertir_archivos(
        archivos, _resolver_formatos(formatos), salida, comentarios
    )


def _convertir_archivos(
    archivos: Sequence[ArchivoAtom],
    formatos: Sequence[str],
    salida: Path,
    comentarios: bool | None,
) -> int:
    """Convierte cada archivo; un fallo en uno no impide convertir los demás."""
    fallidos = 0
    for archivo in archivos:
        try:
            _convertir(archivo, formatos, salida, comentarios)
        except (FeedInvalidoError, OSError, FPDFException) as error:
            logger.error("No se ha podido convertir '%s': %s", archivo.ruta, error)
            fallidos += 1

    convertidos = len(archivos) - fallidos
    if fallidos:
        logger.warning(
            'Proceso finalizado con errores: '
            '%d archivo(s) convertido(s), %d fallido(s).',
            convertidos,
            fallidos,
        )
        return ERROR
    logger.info('Proceso finalizado: %d archivo(s) convertido(s).', convertidos)
    return EXITO


def _convertir(
    archivo: ArchivoAtom,
    formatos: Sequence[str],
    salida: Path,
    comentarios: bool | None,
) -> None:
    logger.info("\nLeyendo '%s'...", archivo.ruta)
    entradas = cargar_entradas(archivo.ruta)

    total_comentarios = sum(len(entrada.comentarios or ()) for entrada in entradas)
    if comentarios is None:
        comentarios = total_comentarios > 0 and _preguntar_si_incluir_comentarios(
            archivo.nombre_base, total_comentarios
        )
    if not comentarios:
        entradas = [replace(entrada, comentarios=None) for entrada in entradas]

    destino = salida / archivo.nombre_base
    logger.info(
        '  %s -> %s', _resumir(entradas, total_comentarios, comentarios), destino
    )

    destino.mkdir(parents=True, exist_ok=True)
    for formato in formatos:
        ruta = destino / f'{archivo.nombre_base}.{formato}'
        EXPORTADORES[formato](entradas, ruta)
        logger.info('  Creado: %s', ruta)


def _preguntar_si_incluir_comentarios(nombre: str, cantidad: int) -> bool:
    """Pregunta si se exportan los comentarios del archivo; por defecto, no."""
    pregunta = (
        f"'{nombre}' tiene {cantidad} comentario(s). "
        '¿Incluirlos en la exportación? [s/N]: '
    )
    while True:
        try:
            respuesta = input(pregunta).strip().lower()
        except EOFError:
            print()
            return False
        if respuesta in _RESPUESTAS_SI:
            return True
        if respuesta in _RESPUESTAS_NO:
            return False
        print("Responde 's' (sí) o 'n' (no).")


def _resumir(
    entradas: Sequence[Entrada], total_comentarios: int, con_comentarios: bool
) -> str:
    resumen = f'{len(entradas)} artículo(s)'
    if borradores := sum(entrada.estado == BORRADOR for entrada in entradas):
        resumen += f' ({borradores} borrador(es))'
    if total_comentarios:
        resumen += f', {total_comentarios} comentario(s)'
        if not con_comentarios:
            resumen += ' sin incluir'
    return resumen


def _menu_interactivo(
    origen: Path,
    archivos: Sequence[ArchivoAtom],
    salida: Path,
    comentarios: bool | None,
) -> int:
    resultado = EXITO
    while True:
        _mostrar_menu(origen, archivos, salida)
        try:
            opcion = input(f'Elige una opción (1-{_OPCION_SALIR}): ').strip()
        except EOFError:
            print()
            return resultado

        if opcion == _OPCION_SALIR:
            print('\nCerrando transcriber.')
            return resultado
        if opcion not in _OPCIONES_MENU:
            print(f'Opción no válida. Introduce un número entre 1 y {_OPCION_SALIR}.')
        elif not archivos:
            print('No hay archivos para procesar.')
        else:
            _, formatos = _OPCIONES_MENU[opcion]
            if _convertir_archivos(archivos, formatos, salida, comentarios) != EXITO:
                resultado = ERROR


def _mostrar_menu(origen: Path, archivos: Sequence[ArchivoAtom], salida: Path) -> None:
    lineas = [
        '',
        _SEPARADOR,
        f'transcriber {__version__}'.center(len(_SEPARADOR)).rstrip(),
        _SEPARADOR,
        f' Origen:             {origen}',
        f' Archivos {EXTENSION_ATOM}:     {len(archivos)} encontrado(s)',
        f' Carpeta de destino: {salida / "<nombre_carpeta>"}',
        _SEPARADOR,
        *(f'{clave}. {texto}' for clave, (texto, _) in _OPCIONES_MENU.items()),
        f'{_OPCION_SALIR}. Salir',
        _SEPARADOR,
    ]
    if not archivos:
        lineas += [
            '',
            f'No se han encontrado archivos {EXTENSION_ATOM} en el origen indicado.',
            'Colócalos en esa carpeta o indica otra ruta como parámetro.',
        ]
    print('\n'.join(lineas))


def _preparar_carpeta_por_defecto() -> Path:
    carpeta = CARPETA_ENTRADA_POR_DEFECTO
    if not carpeta.exists():
        carpeta.mkdir(parents=True)
        logger.info(
            "Se ha creado la carpeta '%s': coloca en ella tus archivos %s.",
            carpeta,
            EXTENSION_ATOM,
        )
    return carpeta


def _resolver_formatos(pedidos: Sequence[str]) -> tuple[str, ...]:
    """Expande 'todos' y elimina duplicados respetando el orden de FORMATOS."""
    if _TODOS in pedidos:
        return FORMATOS
    return tuple(formato for formato in FORMATOS if formato in pedidos)


def _ruta(valor: str) -> Path:
    # En Windows, '"C:\carpeta\"' llega como 'C:\carpeta"' porque la barra final
    # escapa la comilla de cierre: se descartan las comillas sobrantes.
    return Path(valor.strip('"\''))


def _crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='transcriber',
        description=(
            'Convierte exportaciones Atom de Blogger / Google Takeout '
            'a JSON, CSV y PDF.'
        ),
        epilog=(
            'Sin --formato se abre un menú interactivo. Si un archivo tiene '
            'comentarios, se pregunta si incluirlos, salvo que se indique '
            '--comentarios o --sin-comentarios.'
        ),
        add_help=False,
    )
    parser.add_argument(
        'origen',
        nargs='?',
        type=_ruta,
        help=(
            f'archivo {EXTENSION_ATOM} o carpeta en la que buscarlos, incluidas sus '
            f'subcarpetas (por defecto: {CARPETA_ENTRADA_POR_DEFECTO})'
        ),
    )
    parser.add_argument(
        '-f',
        '--formato',
        action='append',
        choices=(*FORMATOS, _TODOS),
        help='formato de salida; se puede repetir',
    )
    parser.add_argument(
        '-o',
        '--salida',
        type=_ruta,
        default=CARPETA_SALIDA_POR_DEFECTO,
        metavar='CARPETA',
        help='carpeta de destino (por defecto: %(default)s)',
    )
    comentarios = parser.add_mutually_exclusive_group()
    comentarios.add_argument(
        '--comentarios',
        action='store_true',
        default=None,
        help='incluye los comentarios de los artículos sin preguntar',
    )
    comentarios.add_argument(
        '--sin-comentarios',
        dest='comentarios',
        action='store_false',
        help='excluye los comentarios de los artículos sin preguntar',
    )
    parser.add_argument(
        '-q', '--quiet', action='store_true', help='muestra solo avisos y errores'
    )
    parser.add_argument(
        '-h', '--help', action='help', help='muestra esta ayuda y termina'
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}',
        help='muestra la versión y termina',
    )
    return parser


class _Formateador(logging.Formatter):
    """Antepone 'Aviso:' o 'Error:' a los mensajes según su nivel."""

    _PREFIJOS: ClassVar[dict[int, str]] = {
        logging.WARNING: 'Aviso: ',
        logging.ERROR: 'Error: ',
        logging.CRITICAL: 'Error: ',
    }

    def format(self, record: logging.LogRecord) -> str:
        return self._PREFIJOS.get(record.levelno, '') + super().format(record)


def _configurar_logging(*, silencioso: bool) -> None:
    manejador = logging.StreamHandler()
    manejador.setFormatter(_Formateador('%(message)s'))
    registro = logging.getLogger('transcriber')
    for anterior in list(registro.handlers):
        registro.removeHandler(anterior)
    registro.addHandler(manejador)
    registro.setLevel(logging.WARNING if silencioso else logging.INFO)
    registro.propagate = False
