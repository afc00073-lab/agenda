"""Pruebas de concurrencia sobre SQLite en modo WAL.

Simulan varios hilos (por ejemplo, la interfaz, el gadget y el temporizador de
notificaciones) escribiendo a la vez para comprobar que el bloqueo de escritura
serializa las transacciones sin perder filas.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from src.base_datos.contexto import ContextoDatos


def test_escrituras_concurrentes_no_pierden_filas(contexto: ContextoDatos) -> None:
    """Cuatro hilos insertan 20 eventos cada uno y se cuentan los 80."""

    def insertar(indice_hilo: int) -> None:
        for numero in range(20):
            contexto.eventos.crear(
                titulo=f"Evento {indice_hilo}-{numero}",
                fecha_inicio=f"2026-07-{1 + indice_hilo:02d}T{8 + numero % 10:02d}:00",
                tipo="tarea",
                recordatorios=[15],
            )

    with ThreadPoolExecutor(max_workers=4) as ejecutor:
        list(ejecutor.map(insertar, range(4)))

    fila = contexto.gestor.consultar_uno("SELECT COUNT(*) AS total FROM eventos")
    assert fila is not None
    assert fila["total"] == 80
    assert contexto.gestor.verificar_integridad() is True


def test_lecturas_mientras_se_escribe(contexto: ContextoDatos) -> None:
    """Las consultas del gadget no fallan durante una ráfaga de escrituras."""

    contexto.eventos.crear(titulo="Inicial", fecha_inicio="2026-08-01T09:00")

    def escribir() -> None:
        for numero in range(30):
            contexto.eventos.crear(
                titulo=f"Escritura {numero}", fecha_inicio="2026-08-02T10:00", tipo="tarea"
            )

    def leer() -> int:
        total = 0
        for _ in range(30):
            total += len(contexto.eventos.listar())
        return total

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        escritura = ejecutor.submit(escribir)
        lectura = ejecutor.submit(leer)
        escritura.result()
        assert lectura.result() >= 30

    assert contexto.eventos.listar()[0]["titulo"]
    assert contexto.gestor.verificar_integridad() is True
