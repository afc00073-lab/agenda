"""Repositorio de asignaturas.

Gestiona el ciclo de vida de las asignaturas del curso: alta, consulta,
actualización y borrado. Los enlaces rápidos se guardan como JSON en una única
columna para no requerir una tabla adicional.
"""

from __future__ import annotations

from typing import Any, Sequence

from src.base_datos.repositorios.repositorio_base import RepositorioBase


class RepositorioAsignaturas(RepositorioBase):
    """Acceso a la tabla ``asignaturas``.

    Todas las operaciones devuelven tipos nativos de Python (``dict``, ``list``,
    ``bool``) para que puedan serializarse directamente a JSON.
    """

    _CAMPOS_ACTUALIZABLES = (
        "nombre",
        "codigo",
        "color",
        "profesor",
        "aula",
        "creditos",
        "enlaces",
    )

    def _serializar(self, fila: dict[str, Any]) -> dict[str, Any]:
        """Normaliza una fila de la base de datos.

        Args:
            fila: Diccionario crudo devuelto por SQLite.

        Returns:
            Diccionario con ``enlaces`` como lista y ``creditos`` como ``float``.
        """

        asignatura = dict(fila)
        asignatura["enlaces"] = self.leer_json(asignatura.get("enlaces"), [])
        asignatura["creditos"] = float(asignatura.get("creditos") or 0)
        return asignatura

    def listar(self) -> list[dict[str, Any]]:
        """Devuelve todas las asignaturas ordenadas por nombre.

        Returns:
            Lista de asignaturas serializadas.
        """

        filas = self.gestor.consultar_todos(
            "SELECT * FROM asignaturas ORDER BY nombre COLLATE NOCASE"
        )
        return [self._serializar(fila) for fila in filas]

    def obtener(self, asignatura_id: int) -> dict[str, Any] | None:
        """Busca una asignatura por su identificador.

        Args:
            asignatura_id: Clave primaria de la asignatura.

        Returns:
            La asignatura o ``None`` si no existe.
        """

        fila = self.gestor.consultar_uno("SELECT * FROM asignaturas WHERE id = ?", (asignatura_id,))
        return self._serializar(fila) if fila else None

    def crear(
        self,
        nombre: str,
        codigo: str = "",
        color: str = "#7c6cff",
        profesor: str = "",
        aula: str = "",
        creditos: float = 6.0,
        enlaces: Sequence[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Crea una asignatura nueva.

        Args:
            nombre: Nombre visible de la asignatura (obligatorio).
            codigo: Código académico, por ejemplo ``"ED-2026"``.
            color: Color hexadecimal usado en calendario y tarjetas.
            profesor: Nombre del docente.
            aula: Aula o laboratorio habitual.
            creditos: Créditos ECTS.
            enlaces: Lista de enlaces ``{"titulo": ..., "url": ...}``.

        Returns:
            La asignatura recién creada, ya serializada.

        Raises:
            ValueError: Si el nombre está vacío.
        """

        nombre_limpio = (nombre or "").strip()
        if not nombre_limpio:
            raise ValueError("El nombre de la asignatura es obligatorio")

        identificador = self.gestor.ejecutar(
            """
            INSERT INTO asignaturas
                (nombre, codigo, color, profesor, aula, creditos, enlaces, creada_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre_limpio,
                (codigo or "").strip(),
                color or "#7c6cff",
                (profesor or "").strip(),
                (aula or "").strip(),
                float(creditos),
                self.escribir_json(list(enlaces or [])),
                self.marca_tiempo(),
            ),
        )
        asignatura = self.obtener(identificador)
        assert asignatura is not None  # La inserción acaba de confirmarse.
        return asignatura

    def actualizar(self, asignatura_id: int, cambios: dict[str, Any]) -> dict[str, Any] | None:
        """Actualiza los campos permitidos de una asignatura.

        Args:
            asignatura_id: Identificador de la asignatura.
            cambios: Diccionario con los campos a modificar. Las claves
                desconocidas se ignoran.

        Returns:
            La asignatura actualizada o ``None`` si no existe.
        """

        campos = [campo for campo in self._CAMPOS_ACTUALIZABLES if campo in cambios]
        if not campos:
            return self.obtener(asignatura_id)

        valores: list[Any] = []
        for campo in campos:
            valor = cambios[campo]
            if campo == "enlaces":
                valor = self.escribir_json(list(valor or []))
            elif campo == "creditos":
                valor = float(valor)
            elif isinstance(valor, str):
                valor = valor.strip()
            valores.append(valor)
        valores.append(asignatura_id)

        self.gestor.ejecutar(
            f"UPDATE asignaturas SET {', '.join(f'{campo} = ?' for campo in campos)} WHERE id = ?",
            valores,
        )
        return self.obtener(asignatura_id)

    def eliminar(self, asignatura_id: int) -> bool:
        """Elimina una asignatura.

        Los eventos y sesiones asociados quedan con ``asignatura_id`` nulo
        (``ON DELETE SET NULL``); las evaluaciones se eliminan en cascada.

        Args:
            asignatura_id: Identificador a borrar.

        Returns:
            ``True`` si se eliminó alguna fila.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("DELETE FROM asignaturas WHERE id = ?", (asignatura_id,))
            return cursor.rowcount > 0

    def contar(self) -> int:
        """Cuenta las asignaturas registradas.

        Returns:
            Número total de asignaturas.
        """

        fila = self.gestor.consultar_uno("SELECT COUNT(*) AS total FROM asignaturas")
        return int(fila["total"]) if fila else 0
