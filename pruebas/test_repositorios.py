"""Pruebas de los repositorios de asignaturas, eventos, notas y configuración."""

from __future__ import annotations

import pytest

from src.base_datos.contexto import ContextoDatos


def test_crud_completo_de_asignatura(contexto: ContextoDatos) -> None:
    """Alta, lectura, actualización y borrado de una asignatura."""

    creada = contexto.asignaturas.crear(
        nombre="Cálculo",
        codigo="CA-101",
        color="#123456",
        profesor="Dra. Prueba",
        aula="A1",
        creditos=6,
        enlaces=[{"titulo": "Apuntes", "url": "https://example.com"}],
    )
    assert creada["nombre"] == "Cálculo"
    assert creada["enlaces"][0]["titulo"] == "Apuntes"

    actualizada = contexto.asignaturas.actualizar(creada["id"], {"aula": "B2", "creditos": 4.5})
    assert actualizada is not None
    assert actualizada["aula"] == "B2"
    assert actualizada["creditos"] == 4.5

    assert contexto.asignaturas.eliminar(creada["id"]) is True
    assert contexto.asignaturas.obtener(creada["id"]) is None


def test_nombre_de_asignatura_obligatorio(contexto: ContextoDatos) -> None:
    """El repositorio rechaza nombres vacíos o compuestos solo por espacios."""

    with pytest.raises(ValueError):
        contexto.asignaturas.crear(nombre="   ")


def test_evento_valida_tipo_y_prioridad(contexto: ContextoDatos) -> None:
    """Los campos enumerados se validan antes de tocar SQLite."""

    with pytest.raises(ValueError):
        contexto.eventos.crear(titulo="X", fecha_inicio="2026-01-01T10:00", tipo="inventado")
    with pytest.raises(ValueError):
        contexto.eventos.crear(titulo="X", fecha_inicio="2026-01-01T10:00", prioridad="urgente")


def test_evento_mover_conserva_duracion(contexto: ContextoDatos) -> None:
    """Al arrastrar un evento se mantiene su duración original."""

    evento = contexto.eventos.crear(
        titulo="Clase de prueba",
        fecha_inicio="2026-03-02T09:00",
        fecha_fin="2026-03-02T11:00",
        tipo="clase",
    )
    movido = contexto.eventos.mover(evento["id"], "2026-03-05T16:00")
    assert movido is not None
    assert movido["fecha_inicio"] == "2026-03-05T16:00"
    assert movido["fecha_fin"] == "2026-03-05T18:00"


def test_kanban_completa_tarea_al_entregar(contexto: ContextoDatos) -> None:
    """Mover a la columna Entregado marca la tarea como completada."""

    tarea = contexto.eventos.crear(
        titulo="Práctica",
        fecha_inicio="2026-04-01T10:00",
        tipo="tarea",
        estado_kanban="pendiente",
    )
    actualizada = contexto.eventos.mover_kanban(tarea["id"], "entregado")
    assert actualizada is not None
    assert actualizada["estado_kanban"] == "entregado"
    assert actualizada["completado"] is True

    reabierta = contexto.eventos.mover_kanban(tarea["id"], "revision")
    assert reabierta is not None
    assert reabierta["completado"] is False


def test_subtareas_calculan_progreso(contexto: ContextoDatos) -> None:
    """El progreso de una tarea refleja sus subtareas completadas."""

    tarea = contexto.eventos.crear(
        titulo="Proyecto", fecha_inicio="2026-04-10T10:00", tipo="tarea"
    )
    primera = contexto.eventos.crear_subtarea(tarea["id"], "Diseño")
    segunda = contexto.eventos.crear_subtarea(tarea["id"], "Código")
    assert primera["orden"] == 0 and segunda["orden"] == 1

    contexto.eventos.alternar_subtarea(primera["id"], True)
    actualizada = contexto.eventos.obtener(tarea["id"])
    assert actualizada is not None
    assert actualizada["progreso"] == 50
    assert actualizada["subtareas"][0]["completada"] is True


def test_eliminar_evento_arrastra_subtareas(contexto: ContextoDatos) -> None:
    """Las subtareas se borran en cascada al eliminar su evento."""

    tarea = contexto.eventos.crear(titulo="X", fecha_inicio="2026-05-01T10:00")
    contexto.eventos.crear_subtarea(tarea["id"], "Una")
    assert contexto.eventos.eliminar(tarea["id"]) is True
    assert contexto.eventos.subtareas_de(tarea["id"]) == []


def test_eliminar_asignatura_arrastra_eventos_y_evaluaciones(
    contexto: ContextoDatos,
) -> None:
    """Al borrar una asignatura no quedan eventos huérfanos ni notas sueltas."""

    asignatura = contexto.asignaturas.crear(nombre="Redes")
    clase = contexto.eventos.crear(
        titulo="Clase de Redes",
        fecha_inicio="2026-05-04T09:00",
        tipo="clase",
        asignatura_id=asignatura["id"],
    )
    tarea = contexto.eventos.crear(
        titulo="Práctica de Redes",
        fecha_inicio="2026-05-08T23:59",
        tipo="tarea",
        asignatura_id=asignatura["id"],
    )
    contexto.evaluaciones.crear(
        asignatura_id=asignatura["id"], nombre="Parcial", peso=50, nota=6
    )

    assert contexto.asignaturas.eliminar(asignatura["id"]) is True

    assert contexto.eventos.obtener(clase["id"]) is None
    assert contexto.eventos.obtener(tarea["id"]) is None
    assert contexto.evaluaciones.listar_por_asignatura(asignatura["id"]) == []
    assert contexto.asignaturas.obtener(asignatura["id"]) is None


def test_evaluacion_y_nota(contexto: ContextoDatos) -> None:
    """Las evaluaciones se guardan con peso, nota y fecha opcional."""

    asignatura = contexto.asignaturas.crear(nombre="Álgebra")
    evaluacion = contexto.evaluaciones.crear(
        asignatura_id=asignatura["id"],
        nombre="Examen parcial",
        peso=40,
        nota=7.5,
        fecha="2026-02-20T09:00",
    )
    assert evaluacion["peso"] == 40.0
    assert evaluacion["nota"] == 7.5
    with pytest.raises(ValueError):
        contexto.evaluaciones.crear(asignatura_id=asignatura["id"], nombre="Peso inválido", peso=140)


def test_configuracion_persistente(contexto: ContextoDatos) -> None:
    """La configuración conserva valores y crea los predeterminados."""

    assert contexto.configuracion.obtener("tema") == "cristal-medianoche"
    contexto.configuracion.guardar("tema", "luz-pura")
    assert contexto.configuracion.obtener("tema") == "luz-pura"
    claves = contexto.configuracion.todas()
    assert claves["opacidad_gadget"] == "0.92"


def test_notificacion_no_duplicada(contexto: ContextoDatos) -> None:
    """La restricción única evita programar dos veces el mismo aviso."""

    evento = contexto.eventos.crear(titulo="Examen", fecha_inicio="2026-06-01T09:00", tipo="examen")
    primera = contexto.notificaciones.crear(
        titulo="Aviso", mensaje="Mensaje", programada_para="2026-05-31T09:00", evento_id=evento["id"]
    )
    segunda = contexto.notificaciones.crear(
        titulo="Aviso", mensaje="Mensaje", programada_para="2026-05-31T09:00", evento_id=evento["id"]
    )
    assert primera is not None
    assert segunda is None
    assert contexto.notificaciones.contar_no_vistas() == 1
