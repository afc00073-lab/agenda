"""Pruebas del sembrado de datos de demostración.

El curso de ejemplo debe aparecer solo la primera vez que se crea la base de
datos. Si el estudiante borra todas sus asignaturas, un arranque posterior no
puede resucitar el curso ficticio.
"""

from __future__ import annotations

from pathlib import Path

from src.base_datos.contexto import ContextoDatos


def test_siembra_al_crear_la_base_por_primera_vez(tmp_path: Path) -> None:
    """Un archivo nuevo recibe el curso de demostración completo."""

    ruta = tmp_path / "nueva.db"
    with ContextoDatos(ruta) as contexto:
        assert contexto.asignaturas.contar() == 6
        assert len(contexto.eventos.listar()) > 0


def test_no_resiembra_si_el_estudiante_borra_todo(tmp_path: Path) -> None:
    """Borrar todas las asignaturas debe sobrevivir a un reinicio."""

    ruta = tmp_path / "vacia.db"
    with ContextoDatos(ruta) as contexto:
        for asignatura in contexto.asignaturas.listar():
            contexto.asignaturas.eliminar(int(asignatura["id"]))
        assert contexto.asignaturas.contar() == 0
        assert contexto.eventos.listar() == []

    with ContextoDatos(ruta) as contexto:
        assert contexto.asignaturas.contar() == 0
        assert contexto.eventos.listar() == []


def test_sembrar_ejemplo_desactivado_no_crea_nada(tmp_path: Path) -> None:
    """La opción ``sembrar_ejemplo=False`` deja la base vacía."""

    ruta = tmp_path / "sin_demo.db"
    with ContextoDatos(ruta, sembrar_ejemplo=False) as contexto:
        assert contexto.asignaturas.contar() == 0
