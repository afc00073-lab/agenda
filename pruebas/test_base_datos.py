"""Pruebas del gestor de base de datos y de las migraciones.

Se verifica el modo WAL, la aplicación idempotente de migraciones, el rechazo de
esquemas más recientes y la integridad del archivo.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.base_datos.conexion import ErrorBaseDatos, GestorBaseDatos
from src.base_datos.esquema import VERSION_ESQUEMA, Migracion


def test_aplica_todas_las_migraciones(gestor: GestorBaseDatos) -> None:
    """La versión instalada debe coincidir con la última del código."""

    assert gestor.version_actual() == VERSION_ESQUEMA
    assert gestor.verificar_integridad() is True


def test_modo_wal_activo(gestor: GestorBaseDatos) -> None:
    """El pragma ``journal_mode`` debe devolver ``wal`` en archivos reales."""

    fila = gestor.consultar_uno("PRAGMA journal_mode")
    assert fila is not None
    assert str(fila["journal_mode"]).lower() == "wal"


def test_migraciones_son_idempotentes(gestor: GestorBaseDatos) -> None:
    """Volver a aplicar migraciones no debe crear ni borrar nada."""

    aplicadas = gestor.aplicar_migraciones()
    assert aplicadas == []
    tablas = {
        fila["name"]
        for fila in gestor.consultar_todos(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"asignaturas", "eventos", "evaluaciones", "notificaciones"} <= tablas


def test_rechaza_esquema_mas_nuevo(ruta_base_datos: Path) -> None:
    """Un archivo con versión futura debe rechazarse con un error claro."""

    gestor = GestorBaseDatos(ruta_base_datos)
    gestor.ejecutar(
        "INSERT INTO migraciones (version, descripcion, aplicada_en) VALUES (?, ?, ?)",
        (VERSION_ESQUEMA + 5, "Migración futura", "2026-01-01T00:00"),
    )
    with pytest.raises(ErrorBaseDatos):
        gestor.aplicar_migraciones()
    gestor.cerrar()


def test_migracion_fallida_se_revierte(ruta_base_datos: Path) -> None:
    """Una migración inválida no debe dejar el esquema a medias."""

    gestor = GestorBaseDatos(ruta_base_datos)
    invalida = Migracion(
        version=VERSION_ESQUEMA + 1,
        descripcion="Migración rota de prueba",
        sentencias=("CREATE TABLE tabla_temporal_prueba (id INTEGER)", "SQL INVALIDO"),
    )
    with pytest.raises(ErrorBaseDatos):
        gestor.aplicar_migraciones([invalida])
    tablas = {
        fila["name"]
        for fila in gestor.consultar_todos("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "tabla_temporal_prueba" not in tablas
    gestor.cerrar()


def test_consultas_parametrizadas_evitan_inyeccion(gestor: GestorBaseDatos) -> None:
    """Un intento de inyección debe tratarse como texto literal."""

    gestor.ejecutar(
        "INSERT INTO asignaturas (nombre, creada_en) VALUES (?, ?)",
        ("'; DROP TABLE asignaturas; --", "2026-01-01T00:00"),
    )
    assert gestor.consultar_uno("SELECT COUNT(*) AS total FROM asignaturas")["total"] == 1


def test_cierre_libera_conexiones(gestor: GestorBaseDatos, ruta_base_datos: Path) -> None:
    """Tras cerrar, el archivo debe poder abrirse con otra conexión."""

    gestor.cerrar()
    conexion = sqlite3.connect(ruta_base_datos)
    assert conexion.execute("SELECT COUNT(*) FROM asignaturas").fetchone()[0] == 0
    conexion.close()
