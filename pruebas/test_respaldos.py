"""Pruebas del gestor de copias de seguridad."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.base_datos.contexto import ContextoDatos
from src.servicios.respaldos import ErrorRespaldo, GestorRespaldos


def _gestor(contexto: ContextoDatos, tmp_path: Path) -> GestorRespaldos:
    """Crea un gestor con un directorio de respaldos aislado."""

    return GestorRespaldos(contexto, tmp_path / "respaldos")


def test_crear_y_listar_respaldo(contexto: ContextoDatos, tmp_path: Path) -> None:
    """El ZIP contiene la base y un manifiesto válido."""

    contexto.eventos.crear(titulo="Original", fecha_inicio="2026-11-20T09:00", tipo="clase")
    gestor = _gestor(contexto, tmp_path)

    respaldo = gestor.crear_respaldo("prueba")
    assert respaldo["valido"] is True
    assert respaldo["etiqueta"] == "prueba"
    assert respaldo["tamano_bytes"] > 0

    archivo = Path(respaldo["ruta"])
    assert archivo.exists()
    with zipfile.ZipFile(archivo) as comprimido:
        assert "agenda.db" in comprimido.namelist()
        assert "manifiesto.json" in comprimido.namelist()

    listado = gestor.listar_respaldos()
    assert len(listado) == 1
    assert listado[0]["nombre"] == archivo.name


def test_restaurar_devuelve_los_datos(contexto: ContextoDatos, tmp_path: Path) -> None:
    """Tras restaurar, los eventos borrados vuelven a estar presentes."""

    evento = contexto.eventos.crear(
        titulo="Sobrevive", fecha_inicio="2026-11-21T10:00", tipo="clase"
    )
    gestor = _gestor(contexto, tmp_path)
    respaldo = gestor.crear_respaldo("antes")

    contexto.eventos.eliminar(int(evento["id"]))
    assert contexto.eventos.obtener(int(evento["id"])) is None

    resultado = gestor.restaurar_respaldo(respaldo["ruta"])
    assert resultado["ok"] is True
    assert resultado["integridad"] is True
    assert resultado["copia_previa"]

    recuperado = contexto.eventos.obtener(int(evento["id"]))
    assert recuperado is not None
    assert recuperado["titulo"] == "Sobrevive"


def test_restaurar_rechaza_archivos_invalidos(contexto: ContextoDatos, tmp_path: Path) -> None:
    """Un archivo que no es un ZIP de la agenda lanza ErrorRespaldo."""

    gestor = _gestor(contexto, tmp_path)
    falso = tmp_path / "falso.zip"
    falso.write_text("no soy un zip", encoding="utf-8")

    with pytest.raises(ErrorRespaldo):
        gestor.restaurar_respaldo(falso)


def test_eliminar_solo_dentro_del_directorio(contexto: ContextoDatos, tmp_path: Path) -> None:
    """El borrado está confinado al directorio de respaldos."""

    gestor = _gestor(contexto, tmp_path)
    respaldo = gestor.crear_respaldo("borrar")
    assert gestor.eliminar_respaldo(respaldo["ruta"]) is True
    assert gestor.eliminar_respaldo(respaldo["ruta"]) is False

    ajeno = tmp_path / "ajeno.zip"
    ajeno.write_text("x", encoding="utf-8")
    with pytest.raises(ErrorRespaldo):
        gestor.eliminar_respaldo(ajeno)
