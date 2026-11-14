"""Repositorio de configuración clave-valor.

La configuración se guarda en una tabla de pares ``clave``/``valor`` para poder
añadir preferencias nuevas sin migrar el esquema. Todos los valores se almacenan
como texto y se interpretan en la capa de servicios o en JavaScript.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.configuracion import CONFIGURACION_PREDETERMINADA
from src.base_datos.repositorios.repositorio_base import RepositorioBase


class RepositorioConfiguracion(RepositorioBase):
    """Acceso a la tabla ``configuracion``."""

    def obtener(self, clave: str, predeterminado: str = "") -> str:
        """Lee un valor de configuración.

        Args:
            clave: Nombre de la preferencia.
            predeterminado: Valor devuelto si no existe.

        Returns:
            Valor almacenado o el predeterminado.
        """

        fila = self.gestor.consultar_uno(
            "SELECT valor FROM configuracion WHERE clave = ?", (clave,)
        )
        return str(fila["valor"]) if fila else predeterminado

    def todas(self) -> dict[str, str]:
        """Devuelve toda la configuración como diccionario plano.

        Returns:
            Diccionario ``clave -> valor``.
        """

        filas = self.gestor.consultar_todos("SELECT clave, valor FROM configuracion")
        return {str(fila["clave"]): str(fila["valor"]) for fila in filas}

    def guardar(self, clave: str, valor: Any) -> None:
        """Inserta o actualiza una preferencia.

        Args:
            clave: Nombre de la preferencia.
            valor: Valor serializado como texto.
        """

        self.gestor.ejecutar(
            """
            INSERT INTO configuracion (clave, valor, actualizado_en)
            VALUES (?, ?, ?)
            ON CONFLICT(clave) DO UPDATE SET
                valor = excluded.valor,
                actualizado_en = excluded.actualizado_en
            """,
            (clave, str(valor), self.marca_tiempo()),
        )

    def guardar_varias(self, valores: Mapping[str, Any]) -> None:
        """Guarda un conjunto de preferencias en una sola transacción.

        Args:
            valores: Diccionario de cambios.
        """

        if not valores:
            return
        marca = self.marca_tiempo()
        with self.gestor.transaccion() as conexion:
            conexion.executemany(
                """
                INSERT INTO configuracion (clave, valor, actualizado_en)
                VALUES (?, ?, ?)
                ON CONFLICT(clave) DO UPDATE SET
                    valor = excluded.valor,
                    actualizado_en = excluded.actualizado_en
                """,
                [(clave, str(valor), marca) for clave, valor in valores.items()],
            )

    def asegurar_predeterminados(self) -> dict[str, str]:
        """Crea las claves que falten con sus valores por defecto.

        Returns:
            Diccionario completo de configuración tras la operación.
        """

        actuales = self.todas()
        faltantes = {
            clave: valor
            for clave, valor in CONFIGURACION_PREDETERMINADA.items()
            if clave not in actuales
        }
        if faltantes:
            self.guardar_varias(faltantes)
            actuales.update(faltantes)
        return actuales

    def eliminar(self, clave: str) -> bool:
        """Elimina una preferencia.

        Args:
            clave: Nombre de la preferencia.

        Returns:
            ``True`` si existía.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("DELETE FROM configuracion WHERE clave = ?", (clave,))
            return cursor.rowcount > 0
