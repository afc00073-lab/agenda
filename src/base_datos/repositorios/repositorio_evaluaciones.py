"""Repositorio de evaluaciones.

Cada evaluación pertenece a una asignatura y tiene un peso porcentual sobre la
nota final. El repositorio permite el alta, la edición y el cálculo de los datos
necesarios para la calculadora de notas.
"""

from __future__ import annotations

from typing import Any

from src.base_datos.repositorios.repositorio_base import RepositorioBase


class RepositorioEvaluaciones(RepositorioBase):
    """Acceso a la tabla ``evaluaciones``."""

    _CAMPOS_ACTUALIZABLES = (
        "asignatura_id",
        "nombre",
        "tipo",
        "peso",
        "nota",
        "nota_maxima",
        "fecha",
    )

    @staticmethod
    def _serializar(fila: dict[str, Any]) -> dict[str, Any]:
        """Normaliza una evaluación para su envío a la interfaz.

        Args:
            fila: Fila cruda de SQLite.

        Returns:
            Evaluación con ``peso``, ``nota`` y ``nota_maxima`` como ``float``.
        """

        evaluacion = dict(fila)
        evaluacion["peso"] = float(evaluacion.get("peso") or 0)
        evaluacion["nota_maxima"] = float(evaluacion.get("nota_maxima") or 10)
        evaluacion["nota"] = (
            float(evaluacion["nota"]) if evaluacion.get("nota") is not None else None
        )
        return evaluacion

    def listar_por_asignatura(self, asignatura_id: int) -> list[dict[str, Any]]:
        """Lista las evaluaciones de una asignatura.

        Args:
            asignatura_id: Identificador de la asignatura.

        Returns:
            Evaluaciones ordenadas por tipo y fecha.
        """

        filas = self.gestor.consultar_todos(
            """
            SELECT * FROM evaluaciones
            WHERE asignatura_id = ?
            ORDER BY fecha ASC, id ASC
            """,
            (asignatura_id,),
        )
        return [self._serializar(fila) for fila in filas]

    def listar_todas(self) -> list[dict[str, Any]]:
        """Devuelve todas las evaluaciones con el nombre de su asignatura.

        Returns:
            Lista global de evaluaciones.
        """

        filas = self.gestor.consultar_todos(
            """
            SELECT ev.*, a.nombre AS asignatura_nombre, a.color AS asignatura_color
            FROM evaluaciones AS ev
            JOIN asignaturas AS a ON a.id = ev.asignatura_id
            ORDER BY ev.fecha ASC, ev.id ASC
            """
        )
        return [self._serializar(fila) for fila in filas]

    def obtener(self, evaluacion_id: int) -> dict[str, Any] | None:
        """Busca una evaluación por identificador.

        Args:
            evaluacion_id: Clave primaria.

        Returns:
            La evaluación o ``None``.
        """

        fila = self.gestor.consultar_uno(
            "SELECT * FROM evaluaciones WHERE id = ?", (evaluacion_id,)
        )
        return self._serializar(fila) if fila else None

    def crear(
        self,
        asignatura_id: int,
        nombre: str,
        peso: float,
        tipo: str = "examen",
        nota: float | None = None,
        nota_maxima: float = 10.0,
        fecha: str = "",
    ) -> dict[str, Any]:
        """Registra una evaluación en una asignatura.

        Args:
            asignatura_id: Asignatura evaluada.
            nombre: Nombre de la prueba o práctica.
            peso: Porcentaje sobre la nota final (0-100).
            tipo: ``practica``, ``examen``, ``proyecto`` o ``participacion``.
            nota: Nota obtenida; ``None`` si aún no se conoce.
            nota_maxima: Puntuación máxima de la escala.
            fecha: Fecha ISO de la prueba, si procede.

        Returns:
            La evaluación creada.

        Raises:
            ValueError: Si el nombre está vacío o el peso está fuera de rango.
        """

        nombre_limpio = (nombre or "").strip()
        if not nombre_limpio:
            raise ValueError("El nombre de la evaluación es obligatorio")
        if not 0 <= float(peso) <= 100:
            raise ValueError("El peso debe estar entre 0 y 100")
        if nota is not None and float(nota) < 0:
            raise ValueError("La nota no puede ser negativa")
        if float(nota_maxima) <= 0:
            raise ValueError("La nota máxima debe ser mayor que cero")

        identificador = self.gestor.ejecutar(
            """
            INSERT INTO evaluaciones
                (asignatura_id, nombre, tipo, peso, nota, nota_maxima, fecha, creada_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asignatura_id,
                nombre_limpio,
                tipo,
                float(peso),
                float(nota) if nota is not None else None,
                float(nota_maxima),
                fecha or "",
                self.marca_tiempo(),
            ),
        )
        evaluacion = self.obtener(identificador)
        assert evaluacion is not None
        return evaluacion

    def actualizar(self, evaluacion_id: int, cambios: dict[str, Any]) -> dict[str, Any] | None:
        """Actualiza los campos editables de una evaluación.

        Args:
            evaluacion_id: Identificador de la evaluación.
            cambios: Campos a modificar.

        Returns:
            Evaluación actualizada o ``None`` si no existe.

        Raises:
            ValueError: Si el peso o la nota no son válidos.
        """

        if "peso" in cambios and not 0 <= float(cambios["peso"]) <= 100:
            raise ValueError("El peso debe estar entre 0 y 100")
        if cambios.get("nota") is not None and float(cambios["nota"]) < 0:
            raise ValueError("La nota no puede ser negativa")

        campos = [campo for campo in self._CAMPOS_ACTUALIZABLES if campo in cambios]
        if not campos:
            return self.obtener(evaluacion_id)
        valores: list[Any] = []
        for campo in campos:
            valor = cambios[campo]
            if campo in ("peso", "nota_maxima"):
                valor = float(valor)
            elif campo == "nota":
                valor = float(valor) if valor is not None else None
            elif isinstance(valor, str):
                valor = valor.strip()
            valores.append(valor)
        valores.append(evaluacion_id)
        self.gestor.ejecutar(
            f"UPDATE evaluaciones SET {', '.join(f'{campo} = ?' for campo in campos)} WHERE id = ?",
            valores,
        )
        return self.obtener(evaluacion_id)

    def eliminar(self, evaluacion_id: int) -> bool:
        """Elimina una evaluación.

        Args:
            evaluacion_id: Identificador de la evaluación.

        Returns:
            ``True`` si se eliminó.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("DELETE FROM evaluaciones WHERE id = ?", (evaluacion_id,))
            return cursor.rowcount > 0
