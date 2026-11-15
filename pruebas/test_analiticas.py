"""Pruebas del servicio de analíticas de estudio."""

from __future__ import annotations

from datetime import date, datetime

from src.servicios.analiticas import construir_analiticas, nivel_actividad

REFERENCIA = datetime(2026, 11, 15, 18, 0)


def _sesiones() -> list[dict[str, object]]:
    """Sesiones de ejemplo: hoy, ayer y una fuera del periodo."""

    return [
        {
            "inicio": "2026-11-15T10:00",
            "duracion_minutos": 50,
            "modo": "25/5",
            "asignatura_nombre": "Bases de Datos",
            "asignatura_color": "#7c6cff",
            "completada": True,
        },
        {
            "inicio": "2026-11-14T20:00",
            "duracion_minutos": 30,
            "modo": "50/10",
            "asignatura_nombre": "Redes",
            "asignatura_color": "#4aa8ff",
            "completada": True,
        },
        {
            "inicio": "2026-08-01T09:00",
            "duracion_minutos": 90,
            "modo": "25/5",
            "asignatura_nombre": "Bases de Datos",
            "completada": True,
        },
        {
            "inicio": "2026-11-15T12:00",
            "duracion_minutos": 25,
            "modo": "25/5",
            "asignatura_nombre": "Bases de Datos",
            "completada": False,
        },
    ]


def _eventos() -> list[dict[str, object]]:
    """Tareas de ejemplo con una vencida y otra completada."""

    return [
        {
            "tipo": "tarea",
            "fecha_fin": "2026-11-14T23:59",
            "completado": False,
        },
        {
            "tipo": "entrega",
            "fecha_fin": "2026-11-12T23:59",
            "completado": True,
        },
        {
            "tipo": "clase",
            "fecha_fin": "2026-11-15T11:00",
            "completado": False,
        },
    ]


def test_nivel_de_actividad_por_tramos() -> None:
    """Los umbrales del mapa de calor son estables."""

    assert [nivel_actividad(minutos) for minutos in (0, 10, 30, 60, 120, 300)] == [
        0,
        1,
        2,
        3,
        4,
        4,
    ]


def test_agregados_del_periodo() -> None:
    """KPIs, reparto, franjas y estado académico se calculan sin Qt."""

    datos = construir_analiticas(
        _sesiones(),
        _eventos(),
        [{"id": 1, "nombre": "Bases de Datos"}, {"id": 2, "nombre": "Redes"}],
        dias=14,
        referencia=REFERENCIA,
    )

    assert datos["periodo"]["dias"] == 14
    assert datos["kpis"]["total_minutos"] == 80
    assert datos["kpis"]["sesiones"] == 2
    assert datos["kpis"]["racha"] == 2
    assert datos["kpis"]["variacion_semanal"] == 100
    assert datos["kpis"]["mejor_dia"]["minutos"] == 50

    serie = datos["por_dia"]
    assert len(serie) == 14
    assert serie[-1]["dia"] == "2026-11-15"
    assert serie[-1]["minutos"] == 50

    reparto = {elemento["asignatura"]: elemento for elemento in datos["por_asignatura"]}
    assert reparto["Bases de Datos"]["minutos"] == 50
    assert reparto["Redes"]["minutos"] == 30
    assert reparto["Bases de Datos"]["porcentaje"] == 62

    franjas = {franja["id"]: franja["minutos"] for franja in datos["franjas"]}
    assert franjas == {"madrugada": 0, "manana": 50, "tarde": 0, "noche": 30}

    academico = datos["academico"]
    assert academico["total"] == 2
    assert academico["completadas"] == 1
    assert academico["pendientes"] == 1
    assert academico["vencidas"] == 1
    assert academico["tasa"] == 50


def test_mapa_de_calor_empieza_en_lunes() -> None:
    """Ocho semanas completas alineadas de lunes a domingo."""

    datos = construir_analiticas(_sesiones(), [], [], dias=7, referencia=REFERENCIA)

    celdas = datos["mapa_calor"]
    assert len(celdas) == 56
    assert date.fromisoformat(celdas[0]["dia"]).weekday() == 0
    assert date.fromisoformat(celdas[-1]["dia"]).weekday() == 6
    assert celdas[-1]["dia"] == "2026-11-15"


def test_periodo_invalido_se_normaliza() -> None:
    """Solo se admiten 7, 14 o 30 días; el resto se aproxima."""

    datos = construir_analiticas([], [], [], dias=5, referencia=REFERENCIA)
    assert datos["periodo"]["dias"] == 7
    assert datos["consejo"].startswith("Empieza con un bloque")
