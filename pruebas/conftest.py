"""Fixtures compartidas de la suite de pruebas.

Todas las pruebas trabajan sobre una base de datos temporal aislada y sin datos
de demostración, de modo que pueden ejecutarse en paralelo y no dependen de la
red ni del escritorio gráfico.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from src.base_datos.contexto import ContextoDatos
from src.base_datos.conexion import GestorBaseDatos


@pytest.fixture()
def ruta_base_datos(tmp_path: Path) -> Path:
    """Ruta de un archivo SQLite dentro del directorio temporal del test.

    Args:
        tmp_path: Directorio único que pytest crea por prueba.

    Returns:
        Ruta del archivo de base de datos.
    """

    return tmp_path / "prueba.db"


@pytest.fixture()
def gestor(ruta_base_datos: Path) -> Iterator[GestorBaseDatos]:
    """Gestor migrado y vacío para las pruebas de bajo nivel.

    Yields:
        Un ``GestorBaseDatos`` conectado al archivo temporal.
    """

    instancia = GestorBaseDatos(ruta_base_datos)
    yield instancia
    instancia.cerrar()


@pytest.fixture()
def contexto(ruta_base_datos: Path) -> Iterator[ContextoDatos]:
    """Contexto completo con repositorios, sin datos de ejemplo.

    Yields:
        Un ``ContextoDatos`` aislado.
    """

    instancia = ContextoDatos(ruta_base_datos, sembrar_ejemplo=False)
    yield instancia
    instancia.cerrar()
