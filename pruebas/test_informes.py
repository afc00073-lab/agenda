"""Pruebas del generador de informes académicos en Markdown."""

from __future__ import annotations

from datetime import datetime

from src.servicios.analiticas import construir_analiticas
from src.servicios.informes import a_markdown, construir_informe

REFERENCIA = datetime(2026, 11, 15, 18, 0)


def _expediente() -> dict[str, object]:
    """Expediente con una asignatura en riesgo y otra aprobada."""

    return {
        "media_ponderada": 6.33,
        "creditos_evaluados": 12.0,
        "creditos_totales": 18.0,
        "asignaturas_aprobadas": 1,
        "total_asignaturas": 2,
        "objetivo": 7.0,
        "asignaturas": [
            {
                "nombre": "Bases de Datos",
                "codigo": "BD-101",
                "creditos": 6.0,
                "calculo": {
                    "media_actual": 8.65,
                    "peso_evaluado": 30,
                    "nota_necesaria": 3.44,
                    "aprobada": False,
                },
            },
            {
                "nombre": "Redes",
                "codigo": "RD-201",
                "creditos": 6.0,
                "calculo": {
                    "media_actual": 4.0,
                    "peso_evaluado": 100,
                    "nota_necesaria": None,
                    "aprobada": False,
                },
            },
        ],
    }


def _eventos() -> list[dict[str, object]]:
    """Una entrega próxima, una vencida y una lejana."""

    return [
        {
            "titulo": "Hoja de ejercicios",
            "tipo": "tarea",
            "fecha_fin": "2026-11-17T23:59",
            "asignatura_nombre": "Redes",
            "prioridad": "alta",
            "completado": False,
        },
        {
            "titulo": "Práctica vencida",
            "tipo": "entrega",
            "fecha_fin": "2026-11-13T23:59",
            "asignatura_nombre": "Bases de Datos",
            "completado": False,
        },
        {
            "titulo": "Examen lejano",
            "tipo": "examen",
            "fecha_fin": "2027-01-20T09:00",
            "asignatura_nombre": "Bases de Datos",
            "completado": False,
        },
    ]


def _informe() -> dict[str, object]:
    """Informe completo construido con datos fijos."""

    analiticas = construir_analiticas(
        [], _eventos(), [], dias=30, referencia=REFERENCIA
    )
    return construir_informe(_expediente(), analiticas, _eventos(), REFERENCIA)


def test_metricas_y_entregas_del_informe() -> None:
    """El resumen usa tan solo las entregas de las próximas dos semanas."""

    informe = _informe()

    metricas = {metrica["etiqueta"]: metrica["valor"] for metrica in informe["metricas"]}
    assert metricas["Media ponderada"] == "6.33"
    assert metricas["Créditos evaluados"] == "12 / 18"
    assert metricas["Entregas próximas"] == "1"

    assert [entrega["titulo"] for entrega in informe["entregas"]] == ["Hoja de ejercicios"]
    assert informe["entregas"][0]["dias"] == 2


def test_markdown_incluye_tablas_y_porcentajes_correctos() -> None:
    """El peso evaluado ya viene en escala 0-100 y no se multiplica otra vez."""

    markdown = _informe()["markdown"]

    assert markdown.startswith("# Informe académico")
    assert "| Media ponderada | 6.33 |" in markdown
    assert "| Bases de Datos | 6.0 | 8.65 | 30 % | 3.44 | En curso |" in markdown
    assert "3000 %" not in markdown
    assert "**Hoja de ejercicios**" in markdown
    assert "en 2 día(s)" in markdown


def test_recomendaciones_detectan_riesgo_y_vencimientos() -> None:
    """Las recomendaciones combinan medias, vencidas y entregas urgentes."""

    recomendaciones = " ".join(_informe()["recomendaciones"])

    assert "Refuerza Redes" in recomendaciones
    assert "entrega(s) vencida(s)" in recomendaciones
    assert "48 horas" in recomendaciones


def test_markdown_es_estable() -> None:
    """La función pública coincide con el texto guardado en el informe."""

    informe = _informe()
    assert a_markdown(informe) == informe["markdown"]
