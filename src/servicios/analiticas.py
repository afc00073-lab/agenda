"""Analíticas de estudio y rendimiento académico.

El servicio combine sesiones Pomodoro, eventos y asignaturas ya serializados
para producir todos los datos que pinta la vista de analíticas: KPIs, serie
diaria, reparto por asignatura, franjas horarias, mapa de calor de ocho semanas
y estado de las tareas. No depende de Qt ni de la base de datos, de modo que
puede probarse con listas pequeñas y relojes simulados.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from src.utilidades import ahora

DIAS_MAPA_CALOR = 56
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
FRANJAS = (
    ("madrugada", "Madrugada", 0, 6),
    ("manana", "Mañana", 6, 12),
    ("tarde", "Tarde", 12, 18),
    ("noche", "Noche", 18, 24),
)


def _fecha_de(iso: str | None) -> date | None:
    """Extrae la fecha de una marca ISO sin lanzar excepciones.

    Args:
        iso: Texto ISO, por ejemplo ``2026-11-15T09:30``.

    Returns:
        La fecha o ``None`` si el texto no es válido.
    """

    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso)).date()
    except ValueError:
        try:
            return date.fromisoformat(str(iso)[:10])
        except ValueError:
            return None


def _hora_de(iso: str | None) -> int | None:
    """Extrae la hora (0-23) de una marca ISO.

    Args:
        iso: Texto ISO.

    Returns:
        La hora o ``None`` si no se puede interpretar.
    """

    if not iso or len(iso) < 13:
        return None
    try:
        return int(str(iso)[11:13])
    except ValueError:
        return None


def nivel_actividad(minutos: int) -> int:
    """Traduce minutos estudiados a un nivel de intensidad 0-4.

    Args:
        minutos: Minutos completados en un día.

    Returns:
        Nivel usado por el mapa de calor.
    """

    if minutos <= 0:
        return 0
    if minutos < 30:
        return 1
    if minutos < 60:
        return 2
    if minutos < 120:
        return 3
    return 4


def _racha(por_dia: dict[str, int], hoy: date) -> int:
    """Cuenta los días consecutivos con estudio hasta hoy.

    Args:
        por_dia: Minutos indexados por fecha ISO.
        hoy: Fecha de referencia.

    Returns:
        Número de días seguidos con al menos un minuto.
    """

    racha = 0
    cursor = hoy
    while por_dia.get(cursor.isoformat(), 0) > 0:
        racha += 1
        cursor -= timedelta(days=1)
    return racha


def construir_analiticas(
    sesiones: Iterable[dict[str, Any]],
    eventos: Iterable[dict[str, Any]],
    asignaturas: Iterable[dict[str, Any]],
    dias: int = 14,
    referencia: datetime | None = None,
) -> dict[str, Any]:
    """Calcula todos los agregados de la vista de analíticas.

    Args:
        sesiones: Sesiones Pomodoro serializadas.
        eventos: Eventos y tareas del periodo.
        asignaturas: Asignaturas del curso.
        dias: Días visibles en la serie principal (7, 14 o 30).
        referencia: Instante de referencia; por defecto, ahora.

    Returns:
        Diccionario con ``periodo``, ``kpis``, ``por_dia``, ``por_asignatura``,
        ``franjas``, ``mapa_calor``, ``modos``, ``academico`` y ``consejo``.
    """

    referencia = referencia or ahora()
    hoy = referencia.date()
    dias = 7 if dias <= 7 else 30 if dias >= 30 else 14
    inicio = hoy - timedelta(days=dias - 1)
    inicio_mapa = hoy - timedelta(days=hoy.weekday() + DIAS_MAPA_CALOR - 7)

    lista_sesiones = [sesion for sesion in sesiones if sesion.get("completada", True)]
    minutos_por_dia: dict[str, int] = defaultdict(int)
    minutos_por_asignatura: dict[str, dict[str, Any]] = {}
    franjas: dict[str, int] = {identificador: 0 for identificador, *_ in FRANJAS}
    modos: Counter[str] = Counter()
    total_minutos = 0
    total_sesiones = 0

    for sesion in lista_sesiones:
        fecha = _fecha_de(sesion.get("inicio"))
        if fecha is None:
            continue
        minutos = int(sesion.get("duracion_minutos") or 0)
        if minutos < 0:
            continue
        minutos_por_dia[fecha.isoformat()] += minutos
        if inicio <= fecha <= hoy:
            total_minutos += minutos
            total_sesiones += 1
            modos[str(sesion.get("modo") or "25/5")] += 1
            nombre = str(sesion.get("asignatura_nombre") or "Sin asignatura")
            registro = minutos_por_asignatura.setdefault(
                nombre,
                {
                    "asignatura": nombre,
                    "color": sesion.get("asignatura_color") or "#8a8fa8",
                    "minutos": 0,
                },
            )
            registro["minutos"] += minutos
            hora = _hora_de(sesion.get("inicio"))
            if hora is not None:
                for identificador, _, desde, hasta in FRANJAS:
                    if desde <= hora < hasta:
                        franjas[identificador] += minutos
                        break

    serie: list[dict[str, Any]] = []
    for indice in range(dias):
        dia = inicio + timedelta(days=indice)
        minutos = minutos_por_dia.get(dia.isoformat(), 0)
        serie.append(
            {
                "dia": dia.isoformat(),
                "etiqueta": f"{DIAS_SEMANA[dia.weekday()]} {dia.day}",
                "minutos": minutos,
                "nivel": nivel_actividad(minutos),
            }
        )

    mapa_calor: list[dict[str, Any]] = []
    for indice in range(DIAS_MAPA_CALOR):
        dia = inicio_mapa + timedelta(days=indice)
        minutos = minutos_por_dia.get(dia.isoformat(), 0)
        mapa_calor.append(
            {
                "dia": dia.isoformat(),
                "etiqueta": f"{DIAS_SEMANA[dia.weekday()]} {dia.day}",
                "minutos": minutos,
                "nivel": nivel_actividad(minutos),
            }
        )

    semana_actual = sum(
        minutos_por_dia.get((hoy - timedelta(days=indice)).isoformat(), 0)
        for indice in range(7)
    )
    semana_anterior = sum(
        minutos_por_dia.get((hoy - timedelta(days=indice + 7)).isoformat(), 0)
        for indice in range(7)
    )
    if semana_anterior:
        variacion = round((semana_actual - semana_anterior) * 100 / semana_anterior)
    else:
        variacion = 100 if semana_actual else 0

    reparto = sorted(
        minutos_por_asignatura.values(), key=lambda elemento: elemento["minutos"], reverse=True
    )
    for elemento in reparto:
        elemento["porcentaje"] = (
            round(elemento["minutos"] * 100 / total_minutos) if total_minutos else 0
        )

    mejor_dia = max(serie, key=lambda elemento: elemento["minutos"])
    media_diaria = round(total_minutos / dias) if dias else 0
    promedio_sesion = round(total_minutos / total_sesiones) if total_sesiones else 0

    tareas = [evento for evento in eventos if evento.get("tipo") in ("tarea", "entrega", "examen")]
    completadas = sum(1 for tarea in tareas if tarea.get("completado"))
    vencidas = sum(
        1
        for tarea in tareas
        if not tarea.get("completado")
        and (_fecha_de(tarea.get("fecha_fin")) or hoy) < hoy
    )
    pendientes = len(tareas) - completadas
    tasa = round(completadas * 100 / len(tareas)) if tareas else 0

    total_asignaturas = len(list(asignaturas))
    if not total_sesiones:
        consejo = "Empieza con un bloque de 25 minutos: la constancia importa más que la intensidad."
    elif variacion >= 20:
        consejo = "Tu ritmo crece respecto a la semana anterior. Mantén el mismo horario de estudio."
    elif vencidas:
        consejo = f"Tienes {vencidas} entrega(s) vencida(s). Dedica el próximo bloque a desbloquearlas."
    elif total_minutos >= 600:
        consejo = "Has superado las 10 horas de estudio. Reserva un descanso largo para consolidar."
    else:
        consejo = "Alterna bloques de 25 y 50 minutos para sostener la atención sin fatiga."

    return {
        "periodo": {
            "dias": dias,
            "desde": inicio.isoformat(),
            "hasta": hoy.isoformat(),
        },
        "kpis": {
            "total_minutos": total_minutos,
            "total_horas": round(total_minutos / 60, 1),
            "media_diaria": media_diaria,
            "promedio_sesion": promedio_sesion,
            "racha": _racha(minutos_por_dia, hoy),
            "sesiones": total_sesiones,
            "variacion_semanal": variacion,
            "mejor_dia": mejor_dia,
        },
        "por_dia": serie,
        "por_asignatura": reparto,
        "franjas": [
            {"id": identificador, "etiqueta": etiqueta, "minutos": franjas[identificador]}
            for identificador, etiqueta, *_ in FRANJAS
        ],
        "mapa_calor": mapa_calor,
        "modos": [
            {"modo": modo, "sesiones": cantidad}
            for modo, cantidad in modos.most_common()
        ],
        "academico": {
            "total": len(tareas),
            "completadas": completadas,
            "pendientes": pendientes,
            "vencidas": vencidas,
            "tasa": tasa,
            "asignaturas": total_asignaturas,
        },
        "consejo": consejo,
    }
