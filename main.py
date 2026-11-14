"""Punto de entrada de la Agenda Académica Inteligente.

Ejecuta ``python main.py`` para abrir la agenda. Opciones disponibles:

* ``--minimizado``: arranca directamente en la bandeja del sistema.
* ``--sin-gadget``: no muestra el gadget flotante «Plan de Hoy».

La lógica de arranque vive en :mod:`src.ventanas.aplicacion`; este archivo solo
prepara la ruta de importación cuando se ejecuta desde el código fuente.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el proyecto sin instalarlo como paquete.
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.ventanas.aplicacion import iniciar_aplicacion  # noqa: E402


def main() -> int:
    """Inicia la aplicación y devuelve su código de salida.

    Returns:
        Código de salida del proceso (``0`` si todo fue bien).
    """

    return iniciar_aplicacion(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
