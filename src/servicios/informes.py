"""Generador de informes académicos en Markdown.

El módulo combina tres fuentes ya calculadas por otros servicios —el expediente
ponderado por créditos, las analíticas de estudio y la lista de eventos— para
producir un documento legible que el estudiante puede guardar, imprimir o
compartir.

No toca la base de datos ni Qt: recibe diccionarios serializados y devuelve
tanto una estructura para pintar en la interfaz como el texto Markdown final.

Example:
    >>> informe = construir_informe(expediente, analiticas, eventos)
    >>> "Informe académico" in informe["markdown"]
    True
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

from src.utilidades import ahora

MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

TIPOS_ENTREGA = ("tarea", "entrega", "examen")
DIAS_ENTREGAS = 14
UMBRAL_APROBADO = 5.0


def _texto_nota(valor: Any) -> str:
    """Formatea una nota con dos decimales o un guion si no existe.

    Args:
        valor: Número o ``None``.

    Returns:
        Texto listo para Markdown.
    """

    if valor is None:
        return "—"
    return f"{float(valor):.2f}"


def _texto_porcentaje(valor: Any) -> str:
    """Formatea un porcentaje redondeado.

    Args:
        valor: Número o ``None``.

    Returns:
        Texto como ``40 %``.
    """

    if valor is None:
        return "0 %"
    return f"{round(float(valor))} %"


def _fecha_de(iso: Any) -> date | None:
    """Interpreta una marca ISO sin lanzar excepciones.

    Args:
        iso: Cadena ISO completa o parcial.

    Returns:
        La fecha resultante o ``None``.
    """

    if not iso:
        return None
    texto = str(iso)
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        try:
            return date.fromisoformat(texto[:10])
        except ValueError:
            return None


def _texto_horas(minutos: Any) -> str:
    """Convierte minutos en horas y minutos legibles.

    Args:
        minutos: Minutos totales.

    Returns:
        Texto como ``12 h 30 min``.
    """

    total = max(0, int(round(float(minutos or 0))))
    horas, resto = divmod(total, 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h {resto} min" if resto else f"{horas} h"


def _entregas_proximas(
    eventos: Iterable[dict[str, Any]], referencia: datetime
) -> list[dict[str, Any]]:
    """Filtra las entregas pendientes de las próximas dos semanas.

    Args:
        eventos: Eventos serializados.
        referencia: Instante de referencia.

    Returns:
        Lista ordenada por fecha de fin con descripción breve.
    """

    hoy = referencia.date()
    limite = hoy + timedelta(days=DIAS_ENTREGAS)
    proximas: list[dict[str, Any]] = []
    for evento in eventos:
        if evento.get("tipo") not in TIPOS_ENTREGA or evento.get("completado"):
            continue
        fecha = _fecha_de(evento.get("fecha_fin")) or _fecha_de(evento.get("fecha_inicio"))
        if fecha is None or fecha < hoy or fecha > limite:
            continue
        proximas.append(
            {
                "titulo": str(evento.get("titulo") or "Sin título"),
                "tipo": str(evento.get("tipo")),
                "asignatura": str(evento.get("asignatura_nombre") or "Sin asignatura"),
                "fecha": fecha.isoformat(),
                "dias": (fecha - hoy).days,
                "prioridad": str(evento.get("prioridad") or "media"),
            }
        )
    proximas.sort(key=lambda entrega: (entrega["fecha"], entrega["titulo"]))
    return proximas


def _recomendaciones(
    expediente: dict[str, Any],
    analiticas: dict[str, Any],
    entregas: list[dict[str, Any]],
) -> list[str]:
    """Genera consejos accionables a partir de los datos del informe.

    Args:
        expediente: Expediente ponderado.
        analiticas: Analíticas de estudio.
        entregas: Entregas próximas ya filtradas.

    Returns:
        Lista de recomendaciones en texto plano.
    """

    consejos: list[str] = []
    objetivo = float(expediente.get("objetivo") or UMBRAL_APROBADO)
    en_riesgo = [
        asignatura["nombre"]
        for asignatura in expediente.get("asignaturas", [])
        if asignatura.get("calculo", {}).get("media_actual") is not None
        and asignatura["calculo"]["media_actual"] < objetivo
    ]
    if en_riesgo:
        nombres = ", ".join(en_riesgo[:3])
        consejos.append(
            f"Refuerza {nombres}: su media actual queda por debajo del objetivo {_texto_nota(objetivo)}."
        )

    vencidas = int(analiticas.get("academico", {}).get("vencidas") or 0)
    if vencidas:
        consejos.append(
            f"Tienes {vencidas} entrega(s) vencida(s). Resuélvelas antes de empezar nuevos bloques."
        )

    urgentes = [entrega for entrega in entregas if entrega["dias"] <= 2]
    if urgentes:
        consejos.append(
            f"{len(urgentes)} entrega(s) vencen en menos de 48 horas. Reserva hoy un bloque Pomodoro para ellas."
        )

    kpis = analiticas.get("kpis", {})
    if int(kpis.get("racha") or 0) >= 3:
        consejos.append(
            f"Mantén la racha de {kpis['racha']} días: la constancia pesa más que las sesiones maratón."
        )
    elif int(kpis.get("sesiones") or 0):
        consejos.append("Programa un bloque de 25 minutos mañana para consolidar el hábito de estudio.")

    consejo_analiticas = analiticas.get("consejo")
    if consejo_analiticas:
        consejos.append(str(consejo_analiticas))

    if not consejos:
        consejos.append("Registra evaluaciones y sesiones de estudio para recibir recomendaciones personalizadas.")
    return consejos


def construir_informe(
    expediente: dict[str, Any],
    analiticas: dict[str, Any],
    eventos: Iterable[dict[str, Any]],
    referencia: datetime | None = None,
) -> dict[str, Any]:
    """Ensambla el informe académico completo.

    Args:
        expediente: Resultado de ``calcular_expediente``.
        analiticas: Resultado de ``construir_analiticas``.
        eventos: Eventos y tareas serializados.
        referencia: Instante de referencia; por defecto, ahora.

    Returns:
        Diccionario con ``titulo``, ``fecha``, ``metricas``, ``asignaturas``,
        ``entregas``, ``recomendaciones`` y ``markdown``.
    """

    referencia = referencia or ahora()
    entregas = _entregas_proximas(eventos, referencia)
    asignaturas = []
    for asignatura in expediente.get("asignaturas", []):
        calculo = asignatura.get("calculo", {})
        asignaturas.append(
            {
                "nombre": str(asignatura.get("nombre") or "Sin nombre"),
                "codigo": str(asignatura.get("codigo") or ""),
                "creditos": float(asignatura.get("creditos") or 0),
                "media": calculo.get("media_actual"),
                "peso_evaluado": calculo.get("peso_evaluado"),
                "necesaria": calculo.get("nota_necesaria"),
                "aprobada": bool(calculo.get("aprobada")),
            }
        )

    kpis = analiticas.get("kpis", {})
    metricas = [
        {"etiqueta": "Media ponderada", "valor": _texto_nota(expediente.get("media_ponderada"))},
        {
            "etiqueta": "Créditos evaluados",
            "valor": f"{_texto_nota(expediente.get('creditos_evaluados')).rstrip('0').rstrip('.')} / "
            f"{_texto_nota(expediente.get('creditos_totales')).rstrip('0').rstrip('.')}",
        },
        {
            "etiqueta": "Asignaturas aprobadas",
            "valor": f"{expediente.get('asignaturas_aprobadas', 0)} de {expediente.get('total_asignaturas', 0)}",
        },
        {"etiqueta": "Tiempo estudiado", "valor": _texto_horas(kpis.get("total_minutos"))},
        {"etiqueta": "Racha actual", "valor": f"{int(kpis.get('racha') or 0)} días"},
        {"etiqueta": "Entregas próximas", "valor": str(len(entregas))},
    ]

    recomendaciones = _recomendaciones(expediente, analiticas, entregas)
    fecha = f"{referencia.day} de {MESES[referencia.month - 1]} de {referencia.year}"
    informe = {
        "titulo": "Informe académico",
        "fecha": fecha,
        "periodo": analiticas.get("periodo", {}),
        "metricas": metricas,
        "asignaturas": asignaturas,
        "entregas": entregas,
        "recomendaciones": recomendaciones,
    }
    informe["markdown"] = a_markdown(informe)
    return informe


def a_markdown(informe: dict[str, Any]) -> str:
    """Convierte el informe estructurado en un documento Markdown.

    Args:
        informe: Diccionario devuelto por :func:`construir_informe`.

    Returns:
        Texto Markdown con tablas, listas y un resumen ejecutivo.
    """

    lineas: list[str] = [
        f"# {informe.get('titulo', 'Informe académico')}",
        "",
        f"*Generado el {informe.get('fecha', '')} · Agenda Académica Inteligente*",
        "",
        "## Resumen ejecutivo",
        "",
        "| Indicador | Valor |",
        "| --- | --- |",
    ]
    for metrica in informe.get("metricas", []):
        lineas.append(f"| {metrica['etiqueta']} | {metrica['valor']} |")

    lineas += [
        "",
        "## Rendimiento por asignatura",
        "",
        "| Asignatura | Créditos | Media | Peso evaluado | Necesaria | Estado |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for asignatura in informe.get("asignaturas", []):
        estado = "Aprobada" if asignatura["aprobada"] else "En curso"
        lineas.append(
            "| {nombre} | {creditos:.1f} | {media} | {peso} | {necesaria} | {estado} |".format(
                nombre=asignatura["nombre"],
                creditos=asignatura["creditos"],
                media=_texto_nota(asignatura["media"]),
                peso=_texto_porcentaje(asignatura["peso_evaluado"]),
                necesaria=_texto_nota(asignatura["necesaria"]),
                estado=estado,
            )
        )

    lineas += ["", f"## Entregas de los próximos {DIAS_ENTREGAS} días", ""]
    if informe.get("entregas"):
        for entrega in informe["entregas"]:
            cuando = "hoy" if entrega["dias"] == 0 else f"en {entrega['dias']} día(s)"
            lineas.append(
                f"- **{entrega['titulo']}** · {entrega['asignatura']} · "
                f"{entrega['fecha']} ({cuando}, prioridad {entrega['prioridad']})"
            )
    else:
        lineas.append("_No hay entregas pendientes en este periodo._")

    lineas += ["", "## Recomendaciones", ""]
    for consejo in informe.get("recomendaciones", []):
        lineas.append(f"- {consejo}")

    lineas += [
        "",
        "---",
        "",
        "_Documento generado automáticamente. Los datos provienen de la base local de la agenda._",
        "",
    ]
    return "\n".join(lineas)
