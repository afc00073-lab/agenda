"""Repositorio de notificaciones.

Actúa como cola e historial: el planificador inserta avisos pendientes, los marca
como enviados cuando los muestra el sistema operativo, y la campana de la
interfaz consulta los no vistos. La restricción ``UNIQUE(evento_id,
programada_para)`` garantiza idempotencia entre reinicios.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.base_datos.repositorios.repositorio_base import RepositorioBase


class RepositorioNotificaciones(RepositorioBase):
    """Acceso a la tabla ``notificaciones``."""

    @staticmethod
    def _serializar(fila: dict[str, Any]) -> dict[str, Any]:
        """Normaliza los campos booleanos de una notificación.

        Args:
            fila: Fila de SQLite.

        Returns:
            Notificación con ``enviada`` y ``vista`` como booleanos.
        """

        notificacion = dict(fila)
        notificacion["enviada"] = bool(notificacion.get("enviada"))
        notificacion["vista"] = bool(notificacion.get("vista"))
        return notificacion

    def crear(
        self,
        titulo: str,
        mensaje: str,
        programada_para: str,
        evento_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Inserta un aviso pendiente evitando duplicados.

        Args:
            titulo: Texto principal de la notificación.
            mensaje: Cuerpo del aviso.
            programada_para: Instante ISO en el que debe mostrarse.
            evento_id: Evento relacionado, si existe.

        Returns:
            La notificación creada, o ``None`` si ya existía una idéntica.
        """

        try:
            identificador = self.gestor.ejecutar(
                """
                INSERT INTO notificaciones
                    (evento_id, titulo, mensaje, programada_para, enviada, creada_en)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (evento_id, titulo, mensaje, programada_para, self.marca_tiempo()),
            )
        except sqlite3.IntegrityError:
            return None
        return self.obtener(identificador)

    def obtener(self, notificacion_id: int) -> dict[str, Any] | None:
        """Busca una notificación por identificador.

        Args:
            notificacion_id: Clave primaria.

        Returns:
            Notificación serializada o ``None``.
        """

        fila = self.gestor.consultar_uno(
            """
            SELECT n.*, e.fecha_inicio AS evento_inicio, e.tipo AS evento_tipo
            FROM notificaciones AS n
            LEFT JOIN eventos AS e ON e.id = n.evento_id
            WHERE n.id = ?
            """,
            (notificacion_id,),
        )
        return self._serializar(fila) if fila else None

    def pendientes(self, ahora_iso: str, limite: int = 50) -> list[dict[str, Any]]:
        """Obtiene los avisos cuya hora ya llegó y aún no se enviaron.

        Args:
            ahora_iso: Instante ISO actual.
            limite: Número máximo de avisos por ciclo.

        Returns:
            Notificaciones pendientes ordenadas por antigüedad.
        """

        filas = self.gestor.consultar_todos(
            """
            SELECT n.*, e.fecha_inicio AS evento_inicio, e.tipo AS evento_tipo
            FROM notificaciones AS n
            LEFT JOIN eventos AS e ON e.id = n.evento_id
            WHERE n.enviada = 0
              AND (n.pospuesta_hasta = '' OR n.pospuesta_hasta <= ?)
              AND n.programada_para <= ?
            ORDER BY n.programada_para ASC
            LIMIT ?
            """,
            (ahora_iso, ahora_iso, int(limite)),
        )
        return [self._serializar(fila) for fila in filas]

    def listar(self, limite: int = 50, solo_no_vistas: bool = False) -> list[dict[str, Any]]:
        """Historial de notificaciones para la campana de la interfaz.

        Args:
            limite: Número máximo de entradas.
            solo_no_vistas: Si es ``True``, filtra las ya leídas.

        Returns:
            Notificaciones de la más reciente a la más antigua.
        """

        sentencia = """
            SELECT n.*, e.fecha_inicio AS evento_inicio, e.tipo AS evento_tipo
            FROM notificaciones AS n
            LEFT JOIN eventos AS e ON e.id = n.evento_id
        """
        if solo_no_vistas:
            sentencia += " WHERE n.vista = 0"
        sentencia += " ORDER BY n.programada_para DESC, n.id DESC LIMIT ?"
        return [self._serializar(fila) for fila in self.gestor.consultar_todos(sentencia, (int(limite),))]

    def marcar_enviada(self, notificacion_id: int, momento: str | None = None) -> bool:
        """Marca una notificación como entregada al sistema operativo.

        Args:
            notificacion_id: Identificador del aviso.
            momento: Instante ISO de envío; por defecto, ahora.

        Returns:
            ``True`` si la notificación existía.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute(
                "UPDATE notificaciones SET enviada = 1, enviada_en = ? WHERE id = ?",
                (momento or self.marca_tiempo(), notificacion_id),
            )
            return cursor.rowcount > 0

    def posponer(self, notificacion_id: int, hasta: str) -> dict[str, Any] | None:
        """Pospone un aviso sin perderlo.

        Args:
            notificacion_id: Identificador del aviso.
            hasta: Nuevo instante ISO de entrega.

        Returns:
            Notificación actualizada o ``None`` si no existe.
        """

        self.gestor.ejecutar(
            """
            UPDATE notificaciones
            SET pospuesta_hasta = ?, enviada = 0
            WHERE id = ?
            """,
            (hasta, notificacion_id),
        )
        return self.obtener(notificacion_id)

    def marcar_vista(self, notificacion_id: int, vista: bool = True) -> bool:
        """Marca una notificación como leída o no leída.

        Args:
            notificacion_id: Identificador.
            vista: Nuevo estado.

        Returns:
            ``True`` si existía.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute(
                "UPDATE notificaciones SET vista = ? WHERE id = ?",
                (int(bool(vista)), notificacion_id),
            )
            return cursor.rowcount > 0

    def marcar_todas_vistas(self) -> int:
        """Marca todas las notificaciones como leídas.

        Returns:
            Número de filas actualizadas.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("UPDATE notificaciones SET vista = 1 WHERE vista = 0")
            return cursor.rowcount

    def contar_no_vistas(self) -> int:
        """Cuenta los avisos pendientes de leer para el contador de la campana.

        Returns:
            Número de notificaciones con ``vista = 0``.
        """

        fila = self.gestor.consultar_uno(
            "SELECT COUNT(*) AS total FROM notificaciones WHERE vista = 0"
        )
        return int(fila["total"]) if fila else 0

    def existe(self, evento_id: int | None, programada_para: str) -> bool:
        """Comprueba si ya se programó un aviso para ese evento e instante.

        Args:
            evento_id: Evento relacionado (puede ser ``None`` para el resumen).
            programada_para: Instante ISO programado.

        Returns:
            ``True`` si ya existe.
        """

        if evento_id is None:
            fila = self.gestor.consultar_uno(
                "SELECT 1 AS existe FROM notificaciones "
                "WHERE evento_id IS NULL AND programada_para = ?",
                (programada_para,),
            )
        else:
            fila = self.gestor.consultar_uno(
                "SELECT 1 AS existe FROM notificaciones WHERE evento_id = ? AND programada_para = ?",
                (evento_id, programada_para),
            )
        return fila is not None

    def eliminar_por_evento(self, evento_id: int) -> int:
        """Elimina los avisos de un evento que va a borrarse.

        Args:
            evento_id: Identificador del evento.

        Returns:
            Número de avisos eliminados.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute(
                "DELETE FROM notificaciones WHERE evento_id = ?", (evento_id,)
            )
            return cursor.rowcount
