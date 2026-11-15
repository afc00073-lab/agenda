"""Pruebas del planificador de notificaciones nativas."""

from __future__ import annotations

from datetime import datetime

from src.base_datos.contexto import ContextoDatos
from src.servicios.notificaciones import PlanificadorNotificaciones

REFERENCIA = datetime(2026, 11, 15, 9, 0)


class NotificadorFalso:
    """Captura los avisos enviados sin tocar el escritorio."""

    def __init__(self) -> None:
        self.enviados: list[tuple[str, str, str]] = []

    def enviar(self, titulo: str, mensaje: str, urgencia: str = "normal") -> bool:
        """Registra la llamada y simula éxito."""

        self.enviados.append((titulo, mensaje, urgencia))
        return True


def _evento(contexto: ContextoDatos) -> dict[str, object]:
    """Crea una entrega dentro de dos horas con dos recordatorios."""

    return contexto.eventos.crear(
        titulo="Práctica de índices",
        fecha_inicio="2026-11-15T11:00",
        fecha_fin="2026-11-15T12:00",
        tipo="entrega",
        recordatorios=[120, 15],
    )


def test_calcular_avisos_descarta_tiempos_pasados() -> None:
    """Los recordatorios se ordenan y se calculan hacia atrás."""

    planificador = PlanificadorNotificaciones.__new__(PlanificadorNotificaciones)
    avisos = planificador.calcular_avisos(
        {"fecha_inicio": "2026-11-15T11:00", "recordatorios": [120, 15, -30]}
    )
    assert avisos == [
        datetime(2026, 11, 15, 9, 0),
        datetime(2026, 11, 15, 10, 45),
    ]


def test_preparar_y_enviar_avisos(contexto: ContextoDatos) -> None:
    """El ciclo inserta avisos idempotentes y entrega los vencidos."""

    _evento(contexto)
    notificador = NotificadorFalso()
    planificador = PlanificadorNotificaciones(
        contexto, notificador=notificador, reloj=lambda: REFERENCIA
    )

    assert planificador.preparar_avisos(REFERENCIA) == 2
    assert planificador.preparar_avisos(REFERENCIA) == 0

    enviadas = planificador.enviar_pendientes(REFERENCIA)
    assert len(enviadas) == 1
    assert enviadas[0]["enviada"] is True
    assert notificador.enviados[0][2] == "alta"
    assert planificador.avisos_enviados == 1

    assert planificador.enviar_pendientes(REFERENCIA) == []


def test_resumen_matutino_una_vez_al_dia(contexto: ContextoDatos) -> None:
    """El resumen respeta la hora configurada y no se repite."""

    notificador = NotificadorFalso()
    planificador = PlanificadorNotificaciones(
        contexto, notificador=notificador, reloj=lambda: REFERENCIA
    )

    assert planificador.enviar_resumen_si_procede(datetime(2026, 11, 15, 7, 30)) is None
    primero = planificador.enviar_resumen_si_procede(REFERENCIA)
    assert primero is not None
    assert "Buenos días" in primero["titulo"]
    assert planificador.enviar_resumen_si_procede(REFERENCIA) is None


def test_resumen_desactivado_en_configuracion(contexto: ContextoDatos) -> None:
    """Con la preferencia a 0 no se envía nada."""

    contexto.configuracion.guardar("resumen_matutino", "0")
    planificador = PlanificadorNotificaciones(
        contexto, notificador=NotificadorFalso(), reloj=lambda: REFERENCIA
    )
    assert planificador.enviar_resumen_si_procede(REFERENCIA) is None


def test_revisar_agrupa_planificacion_y_entrega(contexto: ContextoDatos) -> None:
    """El ciclo completo devuelve las notificaciones recién enviadas."""

    _evento(contexto)
    notificador = NotificadorFalso()
    planificador = PlanificadorNotificaciones(
        contexto, notificador=notificador, reloj=lambda: REFERENCIA
    )
    enviadas = planificador.revisar(REFERENCIA)
    assert any("Práctica de índices" in aviso["titulo"] for aviso in enviadas)
    assert notificador.enviados
