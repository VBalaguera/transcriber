"""Permite ejecutar el paquete con ``python -m transcriber``."""

import sys

from transcriber.cli import main

if __name__ == '__main__':
    sys.exit(main())
