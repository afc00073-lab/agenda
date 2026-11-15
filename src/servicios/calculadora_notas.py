"""Calculadora de notas ponderadas y expediente académico.

El módulo es puro: no toca la base de datos ni Qt. Recibe evaluaciones ya
serializadas (diccionarios con ``peso``, ``nota`` y ``nota_maxima``) y devuelve
los datos que necesita la vista de asignaturas: media actual, nota provisional,
peso evaluado, peso pendiente y la calificación necesaria para alcanzar un
objetivo.

Todas las notas se normalizan a una escala de 0 a 10 para que evaluaciones con
máximos distintos (sobre 100, sobre 20 o sobre 10) convivan sin ambigüedad.
"""

from __future__ import annotations

from typing import Any, Iterable

UMBRAL_APROBADO: float = 5.0
NOTA_MAXIMA_REFERENCIA: float = 10.0


def _redondear(valor: float | None, decimales: int = 2) -> float | None:
    """Redondea de forma segura un valor que puede ser ``None``.

    Args:
        valor: Número o ``None``.
        decimales: Posiciones decimales que conservar.

    Returns:
        El número redondeado o ``None``.
    """

    if valor is None:
        return None
    return round(float(valor), decimales)


def nota_sobre_diez(evaluacion: dict[str, Any]) -> float | None:
    """Convierte la nota de una evaluación a la escala 0-10.

    Args:
        evaluacion: Evaluación con ``nota`` y ``nota_maxima``.

    Returns:
        Nota normalizada, o ``None`` si la evaluación aún no tiene calificación.
    """

    nota = evaluacion.get("nota")
    if nota is None:
        return None
    maxima = float(evaluacion.get("nota_maxima") or NOTA_MAXIMA_REFERENCIA)
    if maxima <= 0:
        return None
    return float(nota) / maxima * NOTA_MAXIMA_REFERENCIA


def calcular_asignatura(
    evaluaciones: Iterable[dict[str, Any]],
    objetivo: float = UMBRAL_APROBADO,
) -> dict[str, Any]:
    """Calcula el estado de una asignatura a partir de sus evaluaciones.

    Args:
        evaluaciones: Evaluaciones de la asignatura. Las que no tienen nota se
            consideran pendientes.
        objetivo: Nota final que se desea alcanzar (escala 0-10).

    Returns:
        Diccionario con ``peso_evaluado``, ``peso_pendiente``, ``media_actual``,
        ``nota_provisional``, ``nota_necesaria``, ``aprobada`` y el detalle de
        cada evaluación enriquecido con ``nota_sobre_diez``.
    """

    lista = list(evaluaciones)
    peso_evaluado = 0.0
    peso_pendiente = 0.0
    puntos = 0.0
    detalle: list[dict[str, Any]] = []

    for evaluacion in lista:
        peso = max(0.0, float(evaluacion.get("peso") or 0))
        normalizada = nota_sobre_diez(evaluacion)
        enriquecida = dict(evaluacion)
        enriquecida["nota_sobre_diez"] = _redondear(normalizada)
        detalle.append(enriquecida)
        if normalizada is None:
            peso_pendiente += peso
        else:
            peso_evaluado += peso
            puntos += normalizada * peso

    peso_total = peso_evaluado + peso_pendiente
    media_actual = puntos / peso_evaluado if peso_evaluado > 0 else None
    nota_provisional = puntos / 100.0 if peso_total > 0 else None
    nota_necesaria: float | None = None
    if peso_pendiente > 0:
        restante = (float(objetivo) * 100.0 - puntos) / peso_pendiente
        nota_necesaria = min(NOTA_MAXIMA_REFERENCIA, max(0.0, restante))

    return {
        "evaluaciones": detalle,
        "total_evaluaciones": len(detalle),
        "evaluadas": sum(1 for evaluacion in detalle if evaluacion["nota"] is not None),
        "peso_evaluado": _redondear(peso_evaluado),
        "peso_pendiente": _redondear(peso_pendiente),
        "peso_total": _redondear(peso_total),
        "media_actual": _redondear(media_actual),
        "nota_provisional": _redondear(nota_provisional),
        "nota_necesaria": _redondear(nota_necesaria),
        "objetivo": _redondear(float(objetivo)) or 0.0,
        "aprobada": bool(nota_provisional is not None and nota_provisional >= UMBRAL_APROBADO),
        "completa": bool(peso_total >= 100.0 - 1e-6 and peso_pendiente <= 1e-6),
    }


def calcular_expediente(
    asignaturas: Iterable[dict[str, Any]],
    evaluaciones_por_asignatura: dict[int, Iterable[dict[str, Any]]],
    objetivo: float = UMBRAL_APROBADO,
) -> dict[str, Any]:
    """Construye el resumen académico global ponderado por créditos ECTS.

    Args:
        asignaturas: Asignaturas serializadas.
        evaluaciones_por_asignatura: Mapa ``id_asignatura -> evaluaciones``.
        objetivo: Nota objetivo usada en cada calculadora.

    Returns:
        Diccionario con la lista de asignaturas enriquecidas y los agregados
        ``media_ponderada``, ``creditos_evaluados``, ``creditos_totales`` y
        ``asignaturas_aprobadas``.
    """

    detalle: list[dict[str, Any]] = []
    suma_ponderada = 0.0
    creditos_evaluados = 0.0
    creditos_totales = 0.0
    aprobadas = 0

    for asignatura in asignaturas:
        identificador = int(asignatura["id"])
        calculo = calcular_asignatura(
            evaluaciones_por_asignatura.get(identificador, []), objetivo
        )
        creditos = float(asignatura.get("creditos") or 0)
        creditos_totales += creditos
        nota = calculo["media_actual"]
        if nota is not None and calculo["peso_evaluado"]:
            suma_ponderada += nota * creditos
            creditos_evaluados += creditos
        if calculo["aprobada"]:
            aprobadas += 1
        detalle.append({**asignatura, "calculo": calculo})

    media_ponderada = (
        suma_ponderada / creditos_evaluados if creditos_evaluados > 0 else None
    )
    return {
        "asignaturas": detalle,
        "media_ponderada": _redondear(media_ponderada),
        "creditos_evaluados": _redondear(creditos_evaluados, 1),
        "creditos_totales": _redondear(creditos_totales, 1),
        "asignaturas_aprobadas": aprobadas,
        "total_asignaturas": len(detalle),
        "objetivo": _redondear(float(objetivo)) or 0.0,
    }
