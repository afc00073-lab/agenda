"""Gestión de copias de seguridad completas en formato ``.zip``.

Las copias usan la API de *backup* en línea de SQLite, que produce una
instantánea coherente incluso con el modo WAL activo. Un respaldo contiene:

* ``agenda.db``: la base de datos consolidada;
* ``manifiesto.json``: versión de esquema, fecha, aplicación y tamaño.

La restauración valida el ZIP (sin rutas maliciosas), comprueba la integridad
del SQLite extraído y guarda automáticamente un respaldo de seguridad del estado
anterior antes de reemplazar el archivo en caliente.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from src.base_datos.contexto import ContextoDatos
from src.configuracion import DIRECTORIO_RESPALDOS, NOMBRE_APLICACION, asegurar_directorios
from src.utilidades import a_iso, ahora

REGISTRO = logging.getLogger(__name__)

NOMBRE_BASE = "agenda.db"
NOMBRE_MANIFIESTO = "manifiesto.json"


class ErrorRespaldo(Exception):
    """Error controlado durante la creación, validación o restauración de un ZIP."""


class GestorRespaldos:
    """Crea, lista, valida y restaura copias de seguridad de la agenda.

    Args:
        contexto: Contexto de datos cuya base se desea respaldar.
        directorio: Carpeta de respaldos. Por defecto, ``datos/respaldos``.
    """

    def __init__(self, contexto: ContextoDatos, directorio: str | Path | None = None) -> None:
        self.contexto = contexto
        self.directorio = Path(directorio or DIRECTORIO_RESPALDOS).expanduser().resolve()
        asegurar_directorios()
        self.directorio.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    def crear_respaldo(self, etiqueta: str = "") -> dict[str, Any]:
        """Genera un ZIP con una instantánea consistente de la base de datos.

        Args:
            etiqueta: Sufijo opcional para identificar la copia.

        Returns:
            Metadatos del respaldo: ruta, nombre, tamaño, fecha y versión.

        Raises:
            ErrorRespaldo: Si la base no puede copiarse o el ZIP no se crea.
        """

        marca = ahora()
        sufijo = ""
        if etiqueta.strip():
            limpio = "".join(caracter for caracter in etiqueta.strip() if caracter.isalnum() or caracter in "-_")
            if limpio:
                sufijo = f"_{limpio}"
        nombre = f"agenda_{marca.strftime('%Y%m%d_%H%M%S')}{sufijo}.zip"
        destino = self.directorio / nombre

        try:
            with tempfile.TemporaryDirectory(prefix="agenda_respaldo_") as carpeta:
                instantanea = Path(carpeta) / NOMBRE_BASE
                self._copiar_base_datos(instantanea)
                if not self._verificar_sqlite(instantanea):
                    raise ErrorRespaldo("La instantánea de la base de datos no supera la verificación de integridad")
                manifiesto = {
                    "aplicacion": NOMBRE_APLICACION,
                    "fecha": a_iso(marca),
                    "version_esquema": self.contexto.gestor.version_actual(),
                    "tamano_bytes": instantanea.stat().st_size,
                    "etiqueta": etiqueta.strip(),
                }
                (Path(carpeta) / NOMBRE_MANIFIESTO).write_text(
                    json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
                    archivo.write(instantanea, NOMBRE_BASE)
                    archivo.write(Path(carpeta) / NOMBRE_MANIFIESTO, NOMBRE_MANIFIESTO)
        except (OSError, sqlite3.Error, zipfile.BadZipFile) as error:
            if destino.exists():
                destino.unlink(missing_ok=True)
            raise ErrorRespaldo(f"No se pudo crear el respaldo: {error}") from error

        datos = self._metadatos(destino)
        REGISTRO.info("Respaldo creado en %s", destino)
        return datos

    def _copiar_base_datos(self, destino: Path) -> None:
        """Copia la base de datos con la API en línea de SQLite.

        Args:
            destino: Archivo de salida consolidado.

        Raises:
            sqlite3.Error: Si SQLite no puede completar la copia.
        """

        with closing(sqlite3.connect(str(self.contexto.gestor.ruta), timeout=10)) as origen:
            with closing(sqlite3.connect(str(destino))) as copia:
                origen.backup(copia)

    @staticmethod
    def _verificar_sqlite(ruta: Path) -> bool:
        """Comprueba la cabecera, la integridad y la presencia de tablas.

        Args:
            ruta: Archivo SQLite a validar.

        Returns:
            ``True`` si el archivo es una base de la aplicación utilizable.
        """

        try:
            with open(ruta, "rb") as archivo:
                if archivo.read(16) != b"SQLite format 3\x00":
                    return False
            with closing(sqlite3.connect(str(ruta))) as conexion:
                integridad = conexion.execute("PRAGMA integrity_check").fetchone()
                tablas = conexion.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN "
                    "('asignaturas', 'eventos', 'configuracion')"
                ).fetchone()
            return bool(integridad and integridad[0] == "ok" and tablas and tablas[0] == 3)
        except (OSError, sqlite3.Error):
            return False

    # ------------------------------------------------------------------
    # Listado y borrado
    # ------------------------------------------------------------------
    def _metadatos(self, ruta: Path) -> dict[str, Any]:
        """Extrae los metadatos de un respaldo del ZIP o del sistema de archivos.

        Args:
            ruta: Archivo ZIP.

        Returns:
            Diccionario con nombre, ruta, fecha, tamaño y etiqueta.
        """

        informacion: dict[str, Any] = {
            "nombre": ruta.name,
            "ruta": str(ruta),
            "fecha": datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%Y-%m-%dT%H:%M"),
            "tamano_bytes": ruta.stat().st_size,
            "etiqueta": "",
            "version_esquema": None,
        }
        try:
            with zipfile.ZipFile(ruta) as archivo:
                if NOMBRE_MANIFIESTO in archivo.namelist():
                    manifiesto = json.loads(archivo.read(NOMBRE_MANIFIESTO).decode("utf-8"))
                    informacion.update(
                        {
                            "fecha": manifiesto.get("fecha", informacion["fecha"]),
                            "etiqueta": manifiesto.get("etiqueta", ""),
                            "version_esquema": manifiesto.get("version_esquema"),
                            "aplicacion": manifiesto.get("aplicacion", ""),
                        }
                    )
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
            informacion["valido"] = False
        else:
            informacion["valido"] = True
        return informacion

    def listar_respaldos(self) -> list[dict[str, Any]]:
        """Lista los respaldos disponibles, del más reciente al más antiguo.

        Returns:
            Lista de metadatos.
        """

        archivos = sorted(self.directorio.glob("agenda_*.zip"), key=lambda ruta: ruta.stat().st_mtime, reverse=True)
        return [self._metadatos(ruta) for ruta in archivos]

    def eliminar_respaldo(self, ruta: str | Path) -> bool:
        """Borra un respaldo del disco.

        Args:
            ruta: Archivo a eliminar.

        Returns:
            ``True`` si se eliminó.
        """

        archivo = Path(ruta).expanduser().resolve()
        if archivo.parent != self.directorio:
            raise ErrorRespaldo("El respaldo debe estar dentro del directorio de respaldos")
        if archivo.exists():
            archivo.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Restauración
    # ------------------------------------------------------------------
    def restaurar_respaldo(self, ruta: str | Path) -> dict[str, Any]:
        """Restaura un respaldo validado sobre la base de datos activa.

        Antes de reemplazar el archivo se crea un respaldo de seguridad
        automático con prefijo ``antes_de_restaurar``. Tras cerrar las conexiones
        se copia la base restaurada y se eliminan los archivos ``-wal`` y ``-shm``
        obsoletos.

        Args:
            ruta: Archivo ZIP de respaldo.

        Returns:
            Diccionario con ``ok``, la copia previa y el respaldo restaurado.

        Raises:
            ErrorRespaldo: Si el ZIP es inválido, no contiene la base esperada o
                la restauración falla.
        """

        archivo = Path(ruta).expanduser().resolve()
        if not archivo.exists() or not zipfile.is_zipfile(archivo):
            raise ErrorRespaldo("El archivo indicado no es un respaldo ZIP válido")

        try:
            with zipfile.ZipFile(archivo) as comprimido:
                nombres = comprimido.namelist()
                if NOMBRE_BASE not in nombres:
                    raise ErrorRespaldo("El respaldo no contiene agenda.db")
                for nombre in nombres:
                    if "/" in nombre or "\\" in nombre or nombre.startswith(".."):
                        raise ErrorRespaldo("El respaldo contiene rutas no permitidas")
                with tempfile.TemporaryDirectory(prefix="agenda_restaurar_") as carpeta:
                    comprimido.extract(NOMBRE_BASE, carpeta)
                    extraida = Path(carpeta) / NOMBRE_BASE
                    if not self._verificar_sqlite(extraida):
                        raise ErrorRespaldo("La base del respaldo está dañada o no pertenece a la agenda")

                    previo = self.crear_respaldo(etiqueta="antes_de_restaurar")
                    self.contexto.gestor.cerrar()
                    shutil.copy2(extraida, self.contexto.gestor.ruta)
                    for sufijo in ("-wal", "-shm"):
                        Path(f"{self.contexto.gestor.ruta}{sufijo}").unlink(missing_ok=True)
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
            raise ErrorRespaldo(f"No se pudo restaurar el respaldo: {error}") from error

        # Reabre y valida la base restaurada.
        if not self.contexto.gestor.verificar_integridad():
            raise ErrorRespaldo("La base restaurada no supera la verificación de integridad")
        self.contexto.gestor.aplicar_migraciones()
        REGISTRO.info("Respaldo restaurado desde %s", archivo)
        return {
            "ok": True,
            "restaurado": archivo.name,
            "copia_previa": previo["nombre"],
            "integridad": True,
        }

    def obtener_ultimo_respaldo(self) -> dict[str, Any] | None:
        """Devuelve el respaldo más reciente.

        Returns:
            Metadatos del último ZIP o ``None`` si no hay copias.
        """

        respaldos = self.listar_respaldos()
        return respaldos[0] if respaldos else None
