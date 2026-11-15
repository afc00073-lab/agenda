"""Pruebas de la calculadora de notas ponderadas y del expediente."""

from __future__ import annotations

from src.servicios.calculadora_notas import (
    calcular_asignatura,
    calcular_expediente,
    nota_sobre_diez,
)


def test_normaliza_notas_de_escalas_distintas() -> None:
    """Las notas sobre 10, 20 y 100 se convierten a la misma escala."""

    assert nota_sobre_diez({"nota": 8, "nota_maxima": 10}) == 8
    assert nota_sobre_diez({"nota": 16, "nota_maxima": 20}) == 8
    assert nota_sobre_diez({"nota": 80, "nota_maxima": 100}) == 8
    assert nota_sobre_diez({"nota": None, "nota_maxima": 10}) is None


def test_media_ponderada_y_nota_necesaria() -> None:
    """Solo las evaluaciones con nota entran en la media y el cálculo restante."""

    calculo = calcular_asignatura(
        [
            {"peso": 40, "nota": 8, "nota_maxima": 10},
            {"peso": 60, "nota": None, "nota_maxima": 10},
        ],
        objetivo=5,
    )
    assert calculo["media_actual"] == 8
    assert calculo["peso_evaluado"] == 40
    assert calculo["peso_pendiente"] == 60
    assert calculo["nota_necesaria"] == 3
    assert calculo["nota_provisional"] == 3.2
    assert calculo["aprobada"] is False


def test_nota_necesaria_nunca_supera_diez() -> None:
    """Si ni con un 10 se alcanza el objetivo, el valor se acota a 10."""

    calculo = calcular_asignatura(
        [
            {"peso": 10, "nota": 0, "nota_maxima": 10},
            {"peso": 90, "nota": None, "nota_maxima": 10},
        ],
        objetivo=9.5,
    )
    assert calculo["nota_necesaria"] == 10


def test_expediente_pondera_por_creditos() -> None:
    """La media global usa los créditos de cada asignatura como peso."""

    asignaturas = [
        {"id": 1, "nombre": "Álgebra", "creditos": 6},
        {"id": 2, "nombre": "Historia", "creditos": 3},
        {"id": 3, "nombre": "Física", "creditos": 6},
    ]
    evaluaciones = {
        1: [{"peso": 100, "nota": 9, "nota_maxima": 10}],
        2: [{"peso": 100, "nota": 5, "nota_maxima": 10}],
        3: [{"peso": 50, "nota": 7, "nota_maxima": 10}],
    }
    expediente = calcular_expediente(asignaturas, evaluaciones, objetivo=5)

    assert expediente["total_asignaturas"] == 3
    assert expediente["creditos_totales"] == 15
    assert expediente["creditos_evaluados"] == 15
    assert expediente["asignaturas_aprobadas"] == 2
    assert expediente["media_ponderada"] == 7.4
