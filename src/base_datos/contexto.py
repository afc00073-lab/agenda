"""Contexto de datos compartido por la aplicación.

Agrupa el gestor de base de datos y una instancia de cada repositorio para que
los servicios y el puente web reciban una única dependencia coherente. También
se encarga de sembrar los datos de demostración en el primer arranque, solo
cuando el archivo de base de datos se crea por primera vez.
"""

from __future__ import annotations

from pathlib import Path

from src.base_datos.conexion import GestorBaseDatos
from src.base_datos.datos_iniciales import sembrar_demostracion
from src.base_datos.repositorios.repositorio_asignaturas import RepositorioAsignaturas
from src.base_datos.repositorios.repositorio_configuracion import RepositorioConfiguracion
from src.base_datos.repositorios.repositorio_evaluaciones import RepositorioEvaluaciones
from src.base_datos.repositorios.repositorio_eventos import RepositorioEventos
from src.base_datos.repositorios.repositorio_notificaciones import RepositorioNotificaciones
from src.base_datos.repositorios.repositorio_sesiones import RepositorioSesiones
from src.base_datos.repositorios.repositorio_suscripciones import RepositorioSuscripciones
from src.configuracion import DIRECTORIO_DATOS, RUTA_BASE_DATOS, asegurar_directorios


class ContextoDatos:
    """Fachada de acceso a todos los repositorios de la aplicación.

    Args:
        ruta: Ruta de la base de datos. Por defecto, la de la configuración.
        sembrar_ejemplo: Si es ``True``, crea el curso de demostración la
            primera vez que se crea el archivo de base de datos. Un archivo
            existente nunca se vuelve a sembrar, aunque esté vacío.

    Attributes:
        gestor: Gestor de conexiones SQLite en modo WAL.
        asignaturas: Repositorio de asignaturas.
        eventos: Repositorio de eventos y subtareas.
        evaluaciones: Repositorio de evaluaciones.
        sesiones: Repositorio de sesiones de estudio.
        suscripciones: Repositorio de feeds iCalendar.
        notificaciones: Repositorio de avisos.
        configuracion: Repositorio de preferencias.
    """

    def __init__(
        self,
        ruta: str | Path | None = None,
        sembrar_ejemplo: bool = True,
    ) -> None:
        asegurar_directorios()
        ruta_final = Path(ruta).expanduser() if ruta is not None else RUTA_BASE_DATOS
        # Los datos de demostración solo se crean junto con el archivo de base
        # de datos. Si ya existía, se respeta aunque el estudiante lo haya
        # vaciado: borrar todas las asignaturas no debe resucitar el curso.
        primera_creacion = not ruta_final.exists()
        self.gestor = GestorBaseDatos(ruta or RUTA_BASE_DATOS)
        self.asignaturas = RepositorioAsignaturas(self.gestor)
        self.eventos = RepositorioEventos(self.gestor)
        self.evaluaciones = RepositorioEvaluaciones(self.gestor)
        self.sesiones = RepositorioSesiones(self.gestor)
        self.suscripciones = RepositorioSuscripciones(self.gestor)
        self.notificaciones = RepositorioNotificaciones(self.gestor)
        self.configuracion = RepositorioConfiguracion(self.gestor)
        self.configuracion.asegurar_predeterminados()
        if sembrar_ejemplo and primera_creacion:
            sembrar_demostracion(self.gestor)

    @property
    def directorio_datos(self) -> Path:
        """Directorio que contiene la base de datos y los respaldos.

        Returns:
            Ruta del directorio de datos.
        """

        return self.gestor.ruta.parent if self.gestor.ruta.parent != Path(".") else DIRECTORIO_DATOS

    def cerrar(self) -> None:
        """Cierra la base de datos y libera todas las conexiones."""

        self.gestor.cerrar()

    def __enter__(self) -> ContextoDatos:
        """Permite usar el contexto como gestor de recursos."""

        return self

    def __exit__(self, *_argumentos: object) -> None:
        """Cierra las conexiones al salir del bloque ``with``."""

        self.cerrar()
