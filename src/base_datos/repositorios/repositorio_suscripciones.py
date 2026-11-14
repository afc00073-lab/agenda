"""Repositorio de suscripciones iCalendar.

Guarda las direcciones de feeds ``.ics`` (Moodle, Google Calendar, Outlook) y la
fecha de la última sincronización para respetar la frecuencia configurada.
"""

from __future__ import annotations

from typing import Any

from src.base_datos.repositorios.repositorio_base import RepositorioBase


class RepositorioSuscripciones(RepositorioBase):
    """Acceso a la tabla ``suscripciones_ics``."""

    @staticmethod
    def _serializar(fila: dict[str, Any]) -> dict[str, Any]:
        """Normaliza una suscripción para JSON.

        Args:
            fila: Fila de SQLite.

        Returns:
            Suscripción con ``activa`` booleana.
        """

        suscripcion = dict(fila)
        suscripcion["activa"] = bool(suscripcion.get("activa"))
        suscripcion["frecuencia_minutos"] = int(suscripcion.get("frecuencia_minutos") or 60)
        return suscripcion

    def listar(self, solo_activas: bool = False) -> list[dict[str, Any]]:
        """Lista las suscripciones registradas.

        Args:
            solo_activas: Si es ``True``, omite las desactivadas.

        Returns:
            Suscripciones ordenadas por nombre.
        """

        sentencia = "SELECT * FROM suscripciones_ics"
        if solo_activas:
            sentencia += " WHERE activa = 1"
        sentencia += " ORDER BY nombre COLLATE NOCASE"
        return [self._serializar(fila) for fila in self.gestor.consultar_todos(sentencia)]

    def obtener(self, suscripcion_id: int) -> dict[str, Any] | None:
        """Busca una suscripción por identificador.

        Args:
            suscripcion_id: Clave primaria.

        Returns:
            La suscripción o ``None``.
        """

        fila = self.gestor.consultar_uno(
            "SELECT * FROM suscripciones_ics WHERE id = ?", (suscripcion_id,)
        )
        return self._serializar(fila) if fila else None

    def crear(
        self, nombre: str, url: str, frecuencia_minutos: int = 60, activa: bool = True
    ) -> dict[str, Any]:
        """Registra una nueva suscripción.

        Args:
            nombre: Nombre visible del feed.
            url: Dirección HTTP(S) del calendario.
            frecuencia_minutos: Intervalo mínimo entre sincronizaciones.
            activa: Estado inicial.

        Returns:
            Suscripción creada.

        Raises:
            ValueError: Si el nombre está vacío o la URL no es HTTP(S).
        """

        nombre_limpio = (nombre or "").strip()
        url_limpia = (url or "").strip()
        if not nombre_limpio:
            raise ValueError("El nombre de la suscripción es obligatorio")
        if not url_limpia.startswith(("http://", "https://")):
            raise ValueError("La URL debe empezar por http:// o https://")
        identificador = self.gestor.ejecutar(
            """
            INSERT INTO suscripciones_ics
                (nombre, url, activa, ultima_sincronizacion, frecuencia_minutos, creada_en)
            VALUES (?, ?, ?, '', ?, ?)
            """,
            (
                nombre_limpio,
                url_limpia,
                int(bool(activa)),
                max(5, int(frecuencia_minutos)),
                self.marca_tiempo(),
            ),
        )
        suscripcion = self.obtener(identificador)
        assert suscripcion is not None
        return suscripcion

    def actualizar(self, suscripcion_id: int, cambios: dict[str, Any]) -> dict[str, Any] | None:
        """Actualiza una suscripción.

        Args:
            suscripcion_id: Identificador de la suscripción.
            cambios: Campos ``nombre``, ``url``, ``activa`` o ``frecuencia_minutos``.

        Returns:
            Suscripción actualizada o ``None``.
        """

        permitidos = ("nombre", "url", "activa", "frecuencia_minutos")
        campos = [campo for campo in permitidos if campo in cambios]
        if not campos:
            return self.obtener(suscripcion_id)
        valores: list[Any] = []
        for campo in campos:
            valor = cambios[campo]
            if campo == "activa":
                valor = int(bool(valor))
            elif campo == "frecuencia_minutos":
                valor = max(5, int(valor))
            elif isinstance(valor, str):
                valor = valor.strip()
            valores.append(valor)
        valores.append(suscripcion_id)
        self.gestor.ejecutar(
            f"UPDATE suscripciones_ics SET {', '.join(f'{c} = ?' for c in campos)} WHERE id = ?",
            valores,
        )
        return self.obtener(suscripcion_id)

    def marcar_sincronizada(self, suscripcion_id: int, momento: str | None = None) -> None:
        """Anota la fecha de la última sincronización correcta.

        Args:
            suscripcion_id: Identificador de la suscripción.
            momento: Marca ISO; por defecto, ahora.
        """

        self.gestor.ejecutar(
            "UPDATE suscripciones_ics SET ultima_sincronizacion = ? WHERE id = ?",
            (momento or self.marca_tiempo(), suscripcion_id),
        )

    def eliminar(self, suscripcion_id: int) -> bool:
        """Elimina una suscripción sin borrar los eventos ya importados.

        Args:
            suscripcion_id: Identificador de la suscripción.

        Returns:
            ``True`` si existía.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute(
                "DELETE FROM suscripciones_ics WHERE id = ?", (suscripcion_id,)
            )
            return cursor.rowcount > 0
