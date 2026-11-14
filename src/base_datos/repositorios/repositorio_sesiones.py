"""Repositorio de sesiones de estudio.

Almacena cada bloque de estudio Pomodoro terminado, con su asignatura, duración
y modo. Las consultas agregadas alimentan las gráficas de analíticas.
"""

from __future__ import annotations

from typing import Any

from src.base_datos.repositorios.repositorio_base import RepositorioBase


class RepositorioSesiones(RepositorioBase):
    """Acceso a la tabla ``sesiones_estudio``."""

    @staticmethod
    def _serializar(fila: dict[str, Any]) -> dict[str, Any]:
        """Convierte una fila en una sesión serializable.

        Args:
            fila: Fila de SQLite.

        Returns:
            Sesión con ``completada`` booleana y duración entera.
        """

        sesion = dict(fila)
        sesion["completada"] = bool(sesion.get("completada"))
        sesion["duracion_minutos"] = int(sesion.get("duracion_minutos") or 0)
        return sesion

    def registrar(
        self,
        inicio: str,
        fin: str,
        duracion_minutos: int,
        asignatura_id: int | None = None,
        evento_id: int | None = None,
        modo: str = "25/5",
        completada: bool = True,
        notas: str = "",
    ) -> dict[str, Any]:
        """Guarda una sesión de estudio finalizada.

        Args:
            inicio: Fecha y hora ISO de comienzo.
            fin: Fecha y hora ISO de fin.
            duracion_minutos: Minutos efectivos de estudio.
            asignatura_id: Asignatura estudiada (opcional).
            evento_id: Evento o tarea relacionada (opcional).
            modo: ``25/5``, ``50/10`` o ``personalizado``.
            completada: Si la sesión se completó sin abandonar.
            notas: Comentarios del estudiante.

        Returns:
            La sesión registrada.

        Raises:
            ValueError: Si la duración es negativa.
        """

        if int(duracion_minutos) < 0:
            raise ValueError("La duración no puede ser negativa")
        identificador = self.gestor.ejecutar(
            """
            INSERT INTO sesiones_estudio
                (asignatura_id, evento_id, inicio, fin, duracion_minutos, modo, completada, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asignatura_id,
                evento_id,
                inicio,
                fin,
                int(duracion_minutos),
                modo,
                int(bool(completada)),
                (notas or "").strip(),
            ),
        )
        fila = self.gestor.consultar_uno(
            """
            SELECT s.*, a.nombre AS asignatura_nombre, a.color AS asignatura_color
            FROM sesiones_estudio AS s
            LEFT JOIN asignaturas AS a ON a.id = s.asignatura_id
            WHERE s.id = ?
            """,
            (identificador,),
        )
        assert fila is not None
        return self._serializar(fila)

    def listar(
        self, desde: str | None = None, hasta: str | None = None, limite: int = 200
    ) -> list[dict[str, Any]]:
        """Lista sesiones en un intervalo temporal.

        Args:
            desde: Fecha ISO mínima (inclusive).
            hasta: Fecha ISO máxima (inclusive).
            limite: Número máximo de sesiones.

        Returns:
            Sesiones ordenadas de la más reciente a la más antigua.
        """

        condiciones: list[str] = []
        parametros: list[Any] = []
        if desde:
            condiciones.append("s.inicio >= ?")
            parametros.append(desde)
        if hasta:
            condiciones.append("s.inicio <= ?")
            parametros.append(hasta)
        sentencia = """
            SELECT s.*, a.nombre AS asignatura_nombre, a.color AS asignatura_color
            FROM sesiones_estudio AS s
            LEFT JOIN asignaturas AS a ON a.id = s.asignatura_id
        """
        if condiciones:
            sentencia += " WHERE " + " AND ".join(condiciones)
        sentencia += " ORDER BY s.inicio DESC LIMIT ?"
        parametros.append(int(limite))
        return [self._serializar(fila) for fila in self.gestor.consultar_todos(sentencia, parametros)]

    def total_minutos(self, desde: str | None = None, hasta: str | None = None) -> int:
        """Suma los minutos estudiados en un intervalo.

        Args:
            desde: Fecha ISO mínima.
            hasta: Fecha ISO máxima.

        Returns:
            Total de minutos completados.
        """

        condiciones = ["completada = 1"]
        parametros: list[Any] = []
        if desde:
            condiciones.append("inicio >= ?")
            parametros.append(desde)
        if hasta:
            condiciones.append("inicio <= ?")
            parametros.append(hasta)
        fila = self.gestor.consultar_uno(
            f"SELECT COALESCE(SUM(duracion_minutos), 0) AS total FROM sesiones_estudio "
            f"WHERE {' AND '.join(condiciones)}",
            parametros,
        )
        return int(fila["total"]) if fila else 0

    def minutos_por_asignatura(
        self, desde: str | None = None, hasta: str | None = None
    ) -> list[dict[str, Any]]:
        """Agrupa los minutos de estudio por asignatura.

        Args:
            desde: Fecha ISO mínima.
            hasta: Fecha ISO máxima.

        Returns:
            Lista de ``{"asignatura", "color", "minutos"}`` ordenada de mayor a menor.
        """

        condiciones = ["s.completada = 1"]
        parametros: list[Any] = []
        if desde:
            condiciones.append("s.inicio >= ?")
            parametros.append(desde)
        if hasta:
            condiciones.append("s.inicio <= ?")
            parametros.append(hasta)
        filas = self.gestor.consultar_todos(
            f"""
            SELECT COALESCE(a.nombre, 'Sin asignatura') AS asignatura,
                   COALESCE(a.color, '#8a8fa8') AS color,
                   COALESCE(SUM(s.duracion_minutos), 0) AS minutos
            FROM sesiones_estudio AS s
            LEFT JOIN asignaturas AS a ON a.id = s.asignatura_id
            WHERE {' AND '.join(condiciones)}
            GROUP BY a.id
            HAVING minutos > 0
            ORDER BY minutos DESC
            """,
            parametros,
        )
        return [{"asignatura": fila["asignatura"], "color": fila["color"], "minutos": int(fila["minutos"])} for fila in filas]

    def minutos_por_dia(self, dias: int = 14, desde: str | None = None) -> list[dict[str, Any]]:
        """Obtiene los minutos estudiados por día para la gráfica de carga.

        Args:
            dias: Número de días a devolver.
            desde: Fecha ISO de inicio; por defecto, hace ``dias`` días.

        Returns:
            Lista de ``{"dia": "AAAA-MM-DD", "minutos": n}`` ordenada.
        """

        if desde:
            dia_inicio = desde[:10]
        else:
            from datetime import timedelta

            from src.utilidades import ahora

            dia_inicio = (ahora() - timedelta(days=dias - 1)).date().isoformat()
        filas = self.gestor.consultar_todos(
            """
            SELECT substr(inicio, 1, 10) AS dia, COALESCE(SUM(duracion_minutos), 0) AS minutos
            FROM sesiones_estudio
            WHERE completada = 1 AND substr(inicio, 1, 10) >= ?
            GROUP BY dia
            ORDER BY dia ASC
            """,
            (dia_inicio,),
        )
        return [{"dia": fila["dia"], "minutos": int(fila["minutos"])} for fila in filas]

    def eliminar(self, sesion_id: int) -> bool:
        """Elimina una sesión registrada.

        Args:
            sesion_id: Identificador de la sesión.

        Returns:
            ``True`` si existía.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("DELETE FROM sesiones_estudio WHERE id = ?", (sesion_id,))
            return cursor.rowcount > 0
