"""Gestor central de conexiones SQLite en modo WAL.

Este módulo implementa el acceso de bajo nivel a la base de datos:

* una **conexión por hilo** (SQLite no admite compartir conexiones de forma
  segura), almacenada en ``threading.local``;
* escrituras serializadas con un ``RLock`` y transacciones ``BEGIN IMMEDIATE``;
* **migraciones versionadas** aplicadas de forma atómica;
* pragmas de rendimiento y consistencia (``journal_mode=WAL``,
  ``synchronous=NORMAL``, ``foreign_keys=ON`` y ``busy_timeout``);
* utilidades de consulta que devuelven diccionarios listos para JSON.

Example:
    >>> gestor = GestorBaseDatos("datos/agenda.db")
    >>> gestor.aplicar_migraciones()
    >>> gestor.consultar_uno("SELECT COUNT(*) AS total FROM asignaturas")
    {'total': 0}
    >>> gestor.cerrar()
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from src.base_datos.esquema import MIGRACIONES, VERSION_ESQUEMA, Migracion
from src.utilidades import ahora, a_iso


class ErrorBaseDatos(Exception):
    """Error controlado de la capa de datos.

    Se lanza cuando la base de datos no puede abrirse, está corrupta o el
    esquema instalado es más reciente que el que entiende la aplicación.
    """


class GestorBaseDatos:
    """Administra conexiones y migraciones de una base SQLite.

    Args:
        ruta: Ruta del archivo de base de datos. Se crea si no existe.
        aplicar_migraciones_automaticamente: Si es ``True``, aplica las
            migraciones pendientes durante la construcción. Las pruebas suelen
            desactivarlo para inspeccionar el estado inicial.

    Attributes:
        ruta: Ruta absoluta del archivo gestionado.
        bloqueo_escritura: Cerrojo reentrante que serializa transacciones.

    Raises:
        ErrorBaseDatos: Si el archivo no se puede abrir o el esquema es
            incompatible.
    """

    def __init__(
        self,
        ruta: str | Path,
        aplicar_migraciones_automaticamente: bool = True,
    ) -> None:
        self.ruta = Path(ruta).expanduser().resolve()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.bloqueo_escritura = threading.RLock()
        self._local = threading.local()
        self._conexiones: list[sqlite3.Connection] = []
        self._registro_conexiones = threading.Lock()

        # Una conexión inicial valida que el archivo sea utilizable.
        with self.conexion() as conexion:
            conexion.execute("SELECT 1")

        if aplicar_migraciones_automaticamente:
            self.aplicar_migraciones()

    # ------------------------------------------------------------------
    # Conexiones
    # ------------------------------------------------------------------
    @property
    def _conexion_actual(self) -> sqlite3.Connection:
        """Devuelve (o crea) la conexión del hilo que realiza la llamada.

        Returns:
            Conexión SQLite configurada con los pragmas de la aplicación.
        """

        conexion: sqlite3.Connection | None = getattr(self._local, "conexion", None)
        if conexion is None:
            try:
                conexion = sqlite3.connect(
                    str(self.ruta),
                    timeout=10.0,
                    isolation_level=None,  # Control manual de transacciones.
                )
            except sqlite3.Error as error:  # pragma: no cover - defensivo
                raise ErrorBaseDatos(f"No se pudo abrir la base de datos: {error}") from error

            conexion.row_factory = sqlite3.Row
            conexion.execute("PRAGMA foreign_keys = ON")
            conexion.execute("PRAGMA busy_timeout = 8000")
            conexion.execute("PRAGMA synchronous = NORMAL")
            if str(self.ruta) != ":memory:":
                try:
                    conexion.execute("PRAGMA journal_mode = WAL")
                except sqlite3.Error as error:  # pragma: no cover - sistemas exóticos
                    raise ErrorBaseDatos(f"No se pudo activar el modo WAL: {error}") from error
            self._local.conexion = conexion
            with self._registro_conexiones:
                self._conexiones.append(conexion)
        return conexion

    @contextmanager
    def conexion(self) -> Iterator[sqlite3.Connection]:
        """Entrega la conexión del hilo actual sin abrir transacción.

        Yields:
            Conexión SQLite configurada. El contexto no la cierra al salir,
            porque se reutiliza durante toda la vida del hilo.
        """

        yield self._conexion_actual

    @contextmanager
    def transaccion(self) -> Iterator[sqlite3.Connection]:
        """Ejecuta un bloque dentro de una transacción de escritura.

        Usa ``BEGIN IMMEDIATE`` para adquirir el bloqueo de escritura al
        principio y evitar interbloqueos. Si ya hay una transacción abierta en
        el hilo (por ejemplo, una llamada anidada), se reutiliza sin anidar.

        Yields:
            Conexión con la transacción activa.

        Raises:
            ErrorBaseDatos: Si SQLite rechaza la operación; la transacción se
                revierte automáticamente.
        """

        conexion = self._conexion_actual
        with self.bloqueo_escritura:
            transaccion_propia = not conexion.in_transaction
            try:
                if transaccion_propia:
                    conexion.execute("BEGIN IMMEDIATE")
                yield conexion
                if transaccion_propia:
                    conexion.execute("COMMIT")
            except sqlite3.Error as error:
                if transaccion_propia and conexion.in_transaction:
                    conexion.execute("ROLLBACK")
                raise ErrorBaseDatos(f"Error en la transacción: {error}") from error
            except Exception:
                if transaccion_propia and conexion.in_transaction:
                    conexion.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------------
    # Consultas de conveniencia
    # ------------------------------------------------------------------
    def ejecutar(self, sentencia: str, parametros: Sequence[Any] = ()) -> int:
        """Ejecuta una sentencia de escritura y devuelve el último identificador.

        Args:
            sentencia: SQL con marcadores ``?``.
            parametros: Valores a enlazar, siempre parametrizados.

        Returns:
            ``lastrowid`` de la inserción o el número de filas afectadas.

        Raises:
            ErrorBaseDatos: Si la sentencia falla.
        """

        with self.transaccion() as conexion:
            cursor = conexion.execute(sentencia, tuple(parametros))
            return int(cursor.lastrowid or cursor.rowcount or 0)

    def ejecutar_muchos(self, sentencia: str, filas: Sequence[Sequence[Any]]) -> int:
        """Ejecuta una sentencia para varias filas dentro de una transacción.

        Args:
            sentencia: SQL con marcadores ``?``.
            filas: Secuencia de tuplas de parámetros.

        Returns:
            Número de filas insertadas o actualizadas.
        """

        if not filas:
            return 0
        with self.transaccion() as conexion:
            cursor = conexion.executemany(sentencia, [tuple(fila) for fila in filas])
            return int(cursor.rowcount or len(filas))

    def consultar_uno(
        self, sentencia: str, parametros: Sequence[Any] = ()
    ) -> dict[str, Any] | None:
        """Ejecuta una consulta y devuelve la primera fila como diccionario.

        Args:
            sentencia: SQL de solo lectura.
            parametros: Valores a enlazar.

        Returns:
            Diccionario con la fila, o ``None`` si no hay resultados.
        """

        with self.conexion() as conexion:
            fila = conexion.execute(sentencia, tuple(parametros)).fetchone()
        return dict(fila) if fila is not None else None

    def consultar_todos(
        self, sentencia: str, parametros: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        """Ejecuta una consulta y devuelve todas las filas como diccionarios.

        Args:
            sentencia: SQL de solo lectura.
            parametros: Valores a enlazar.

        Returns:
            Lista (posiblemente vacía) de diccionarios.
        """

        with self.conexion() as conexion:
            filas = conexion.execute(sentencia, tuple(parametros)).fetchall()
        return [dict(fila) for fila in filas]

    # ------------------------------------------------------------------
    # Migraciones
    # ------------------------------------------------------------------
    def version_actual(self) -> int:
        """Consulta la versión de esquema instalada.

        Returns:
            Número de la última migración aplicada, o ``0`` en una base nueva.
        """

        with self.transaccion() as conexion:
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS migraciones (
                    version     INTEGER PRIMARY KEY,
                    descripcion TEXT NOT NULL,
                    aplicada_en TEXT NOT NULL
                )
                """
            )
            fila = conexion.execute("SELECT MAX(version) AS version FROM migraciones").fetchone()
        return int(fila["version"] or 0) if fila else 0

    def aplicar_migraciones(self, migraciones: Sequence[Migracion] | None = None) -> list[int]:
        """Aplica las migraciones pendientes en orden ascendente.

        Args:
            migraciones: Migraciones a considerar. Por defecto, las definidas
                en :mod:`src.base_datos.esquema`.

        Returns:
            Lista de versiones aplicadas durante esta llamada.

        Raises:
            ErrorBaseDatos: Si el esquema instalado es más nuevo que el código o
                alguna migración falla (se revierte al completo).
        """

        disponibles = tuple(sorted(migraciones or MIGRACIONES, key=lambda m: m.version))
        actual = self.version_actual()
        maxima_conocida = max((m.version for m in disponibles), default=0)
        if actual > maxima_conocida:
            raise ErrorBaseDatos(
                f"La base de datos usa el esquema v{actual}, más reciente que "
                f"el soportado v{maxima_conocida}. Actualiza la aplicación."
            )

        aplicadas: list[int] = []
        for migracion in disponibles:
            if migracion.version <= actual:
                continue
            try:
                with self.transaccion() as conexion:
                    for sentencia in migracion.sentencias:
                        conexion.execute(sentencia)
                    conexion.execute(
                        "INSERT INTO migraciones (version, descripcion, aplicada_en) VALUES (?, ?, ?)",
                        (migracion.version, migracion.descripcion, a_iso(ahora())),
                    )
                aplicadas.append(migracion.version)
            except ErrorBaseDatos as error:
                raise ErrorBaseDatos(
                    f"Falló la migración v{migracion.version}: {error}"
                ) from error
        return aplicadas

    def verificar_integridad(self) -> bool:
        """Ejecuta la comprobación de integridad nativa de SQLite.

        Returns:
            ``True`` si ``PRAGMA integrity_check`` devuelve ``ok``.
        """

        with self.conexion() as conexion:
            resultado = conexion.execute("PRAGMA integrity_check").fetchone()
        return bool(resultado and resultado[0] == "ok")

    def cerrar(self) -> None:
        """Cierra todas las conexiones abiertas por esta instancia.

        Es seguro llamarlo varias veces. Se usa al cerrar la aplicación y en el
        desmontaje de las pruebas.
        """

        with self._registro_conexiones:
            conexiones, self._conexiones = self._conexiones, []
        for conexion in conexiones:
            try:
                conexion.close()
            except sqlite3.Error:  # pragma: no cover - cierre defensivo
                pass
        self._local = threading.local()

    def __enter__(self) -> GestorBaseDatos:
        """Permite usar el gestor como contexto: ``with GestorBaseDatos(...)``."""

        return self

    def __exit__(self, *_argumentos: object) -> None:
        """Cierra las conexiones al salir del contexto."""

        self.cerrar()


__all__ = ["GestorBaseDatos", "ErrorBaseDatos", "VERSION_ESQUEMA"]
