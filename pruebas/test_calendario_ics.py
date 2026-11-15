"""Pruebas del analizador y del sincronizador iCalendar."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.base_datos.contexto import ContextoDatos
from src.servicios.calendario_ics import AnalizadorICS, SincronizadorICS

CALENDARIO = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Agenda//Pruebas//ES
BEGIN:VEVENT
UID:examen-1@agenda
SUMMARY:Examen de Bases de Datos
DESCRIPTION:Traer calculadora y una línea plegada que
 continúa aquí
DTSTART:20261220T090000
DTEND:20261220T110000
LOCATION:Aula 3.2
END:VEVENT
BEGIN:VEVENT
UID:entrega-2@agenda
SUMMARY:Entrega de práctica
DTSTART;VALUE=DATE:20261218
END:VEVENT
END:VCALENDAR
"""


def test_analizador_extrae_eventos_y_tipos() -> None:
    """Dos eventos, tipos inferidos y línea plegada reconstruida."""

    eventos = AnalizadorICS().analizar(CALENDARIO)

    assert len(eventos) == 2
    examen, entrega = eventos
    assert examen.uid == "examen-1@agenda"
    assert examen.tipo == "examen"
    assert examen.prioridad == "alta"
    assert examen.inicio == "2026-12-20T09:00"
    assert "continúa aquí" in examen.descripcion
    assert examen.ubicacion == "Aula 3.2"

    assert entrega.tipo == "entrega"
    assert entrega.todo_el_dia is True
    assert entrega.inicio.startswith("2026-12-18")


def test_calendario_invalido_lanza_error() -> None:
    """Un texto sin VEVENT se rechaza con un mensaje claro."""

    with pytest.raises(ValueError):
        AnalizadorICS().analizar("BEGIN:VCALENDAR\nEND:VCALENDAR")


def test_recurrencia_diaria_genera_ocurrencias() -> None:
    """RRULE DAILY con COUNT produce tantos eventos como indica la regla."""

    texto = CALENDARIO.replace(
        "DTEND:20261220T110000",
        "DTEND:20261220T110000\nRRULE:FREQ=DAILY;COUNT=3",
    )
    eventos = AnalizadorICS().analizar(texto)
    assert len(eventos) == 4
    assert len({evento.uid for evento in eventos}) == 4


def test_importacion_es_idempotente(contexto: ContextoDatos) -> None:
    """Reimportar el mismo calendario actualiza y no duplica eventos."""

    sincronizador = SincronizadorICS(contexto)

    primera = sincronizador.importar_texto(CALENDARIO)
    assert primera["ok"] is True
    assert primera["creados"] == 2
    assert primera["actualizados"] == 0

    segunda = sincronizador.importar_texto(CALENDARIO)
    assert segunda["creados"] == 0
    assert segunda["actualizados"] == 0
    assert segunda["omitidos"] == 2

    tercera = sincronizador.importar_texto(
        CALENDARIO.replace("Examen de Bases de Datos", "Examen final de Bases de Datos")
    )
    assert tercera["actualizados"] == 1
    assert tercera["omitidos"] == 1

    assert len(contexto.eventos.listar(desde="2026-12-01", hasta="2026-12-31")) == 2


def test_sincronizacion_usa_el_descargador_inyectado(contexto: ContextoDatos) -> None:
    """La suscripción remota se resuelve sin tocar la red."""

    urls: list[str] = []

    def descargador(url: str) -> str:
        urls.append(url)
        return CALENDARIO

    sincronizador = SincronizadorICS(contexto, descargador=descargador)
    suscripcion = contexto.suscripciones.crear(
        nombre="Facultad", url="https://ejemplo.test/agenda.ics", frecuencia_minutos=60
    )

    resultado = sincronizador.sincronizar_suscripcion(int(suscripcion["id"]))
    assert resultado["ok"] is True
    assert resultado["creados"] == 2
    assert urls == ["https://ejemplo.test/agenda.ics"]

    actualizada = contexto.suscripciones.obtener(int(suscripcion["id"]))
    assert actualizada is not None
    assert actualizada["ultima_sincronizacion"]


def test_sincronizacion_de_suscripcion_inexistente(contexto: ContextoDatos) -> None:
    """Un identificador desconocido devuelve un error controlado."""

    sincronizador = SincronizadorICS(contexto, descargador=lambda _url: CALENDARIO)
    resultado = sincronizador.sincronizar_suscripcion(9999)
    assert resultado["ok"] is False
    assert "no existe" in resultado["error"].lower()


def test_sincronizar_todas_respeta_la_frecuencia(contexto: ContextoDatos) -> None:
    """Un feed recién sincronizado no se vuelve a descargar antes de tiempo."""

    descargas: list[str] = []

    def descargador(url: str) -> str:
        descargas.append(url)
        return CALENDARIO

    sincronizador = SincronizadorICS(contexto, descargador=descargador)
    contexto.suscripciones.crear(
        nombre="Facultad", url="https://ejemplo.test/agenda.ics", frecuencia_minutos=120
    )
    momento = datetime(2026, 11, 15, 10, 0)
    primera = sincronizador.sincronizar_todas(momento)
    segunda = sincronizador.sincronizar_todas(momento)
    assert len(primera) == 1
    assert segunda == []
    assert len(descargas) == 1
