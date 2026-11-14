"""Utilidades transversales de fechas y serialización.

Funciones auxiliares sin dependencias de Qt ni de la base de datos, usadas por
los servicios, los repositorios y las pruebas. El formato canónico de fecha y
hora es ISO-8601 con precisión de minutos (``AAAA-MM-DDTHH:MM``); SQLite lo
ordena lexicográficamente y JavaScript lo interpreta de forma nativa.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Final

FORMATO_FECHA: Final[str] = "%Y-%m-%d"
FORMATO_FECHA_HORA: Final[str] = "%Y-%m-%dT%H:%M"

DIAS_SEMANA: Final[tuple[str, ...]] = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

MESES: Final[tuple[str, ...]] = (
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


def ahora() -> datetime:
    """Devuelve la fecha y hora local actual, sin zona horaria.

    Returns:
        Un ``datetime`` local que sirve como reloj por defecto de los servicios.
    """

    return datetime.now().replace(second=0, microsecond=0)


def a_iso(momento: datetime | date) -> str:
    """Convierte una fecha u hora al formato ISO canónico de la aplicación.

    Args:
        momento: Fecha u hora que se desea serializar.

    Returns:
        Cadena ``AAAA-MM-DD`` para fechas y ``AAAA-MM-DDTHH:MM`` para horas.
    """

    if isinstance(momento, datetime):
        return momento.strftime(FORMATO_FECHA_HORA)
    return momento.strftime(FORMATO_FECHA)


def desde_iso(texto: str) -> datetime:
    """Interpreta una cadena ISO de la aplicación.

    Acepta tanto ``AAAA-MM-DD`` como ``AAAA-MM-DDTHH:MM`` y variantes con
    segundos o zona horaria (que se descarta para trabajar en hora local).

    Args:
        texto: Cadena de fecha u hora.

    Returns:
        El ``datetime`` equivalente.

    Raises:
        ValueError: Si el texto no tiene un formato de fecha reconocible.
    """

    limpio = texto.strip().replace("Z", "+00:00")
    if not limpio:
        raise ValueError("La fecha está vacía")
    try:
        return datetime.fromisoformat(limpio)
    except ValueError:
        # Algunos feeds usan fechas compactas tipo 20260131.
        return datetime.strptime(limpio, "%Y%m%d")


def fecha_legible(momento: datetime) -> str:
    """Genera una fecha larga en español, por ejemplo «martes 14 de abril».

    Args:
        momento: Fecha a formatear.

    Returns:
        Texto legible sin año, útil para cabeceras del gadget y del panel.
    """

    return f"{DIAS_SEMANA[momento.weekday()]} {momento.day} de {MESES[momento.month - 1]}"


def rango_dia(momento: datetime) -> tuple[str, str]:
    """Calcula el intervalo ISO que cubre un día completo.

    Args:
        momento: Cualquier instante del día deseado.

    Returns:
        Tupla ``(inicio, fin)`` que abarca desde las 00:00 hasta las 23:59.
    """

    inicio = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = inicio + timedelta(hours=23, minutes=59)
    return a_iso(inicio), a_iso(fin)


def rango_semana(momento: datetime) -> tuple[datetime, datetime]:
    """Obtiene el lunes y el domingo de la semana de una fecha.

    Args:
        momento: Instante de referencia.

    Returns:
        Tupla con el lunes a las 00:00 y el domingo a las 23:59.
    """

    lunes = momento - timedelta(days=momento.weekday())
    lunes = lunes.replace(hour=0, minute=0, second=0, microsecond=0)
    domingo = lunes + timedelta(days=6, hours=23, minutes=59)
    return lunes, domingo


def minutos_entre(inicio: str, fin: str) -> int:
    """Calcula la diferencia en minutos entre dos fechas ISO.

    Args:
        inicio: Fecha inicial.
        fin: Fecha final.

    Returns:
        Número de minutos (puede ser negativo si ``fin`` es anterior).
    """

    return int((desde_iso(fin) - desde_iso(inicio)).total_seconds() // 60)


def sumar_minutos(momento: datetime, minutos: int) -> datetime:
    """Suma minutos a un instante sin perder el formato canónico.

    Args:
        momento: Instante de partida.
        minutos: Cantidad de minutos a sumar (puede ser negativa).

    Returns:
        Nuevo ``datetime`` desplazado.
    """

    return momento + timedelta(minutes=minutos)
