"""Configuración global y rutas del sistema de archivos.

Este módulo centraliza las rutas de trabajo de la aplicación (base de datos,
directorio de respaldos, recursos de la interfaz) y los valores por defecto de
la configuración persistente. Todas las rutas se calculan a partir del
directorio del proyecto para que la aplicación funcione de forma portable,
pero puede sobrescribirse con la variable de entorno ``AGENDA_DIRECTORIO_DATOS``
(útil en pruebas y en instalaciones de solo lectura).

Attributes:
    DIRECTORIO_RAIZ: Ruta absoluta de la raíz del proyecto.
    DIRECTORIO_DATOS: Carpeta donde se guardan la base de datos y los respaldos.
    RUTA_BASE_DATOS: Ruta del archivo SQLite principal.
    DIRECTORIO_RESPALDOS: Carpeta destino de las copias de seguridad.
    DIRECTORIO_INTERFAZ: Carpeta con HTML, CSS, JS e imágenes de la interfaz.
    CONFIGURACION_PREDETERMINADA: Valores iniciales de configuración.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
DIRECTORIO_RAIZ: Final[Path] = Path(__file__).resolve().parent.parent
DIRECTORIO_INTERFAZ: Final[Path] = DIRECTORIO_RAIZ / "src" / "interfaz"

_directorio_datos_entorno: str | None = os.environ.get("AGENDA_DIRECTORIO_DATOS")
DIRECTORIO_DATOS: Final[Path] = (
    Path(_directorio_datos_entorno).expanduser().resolve()
    if _directorio_datos_entorno
    else DIRECTORIO_RAIZ / "datos"
)
RUTA_BASE_DATOS: Final[Path] = DIRECTORIO_DATOS / "agenda.db"
DIRECTORIO_RESPALDOS: Final[Path] = DIRECTORIO_DATOS / "respaldos"

# Archivos de la interfaz gráfica
RUTA_HTML_PRINCIPAL: Final[Path] = DIRECTORIO_INTERFAZ / "index.html"
RUTA_HTML_GADGET: Final[Path] = DIRECTORIO_INTERFAZ / "gadget.html"
RUTA_ICONO_APLICACION: Final[Path] = DIRECTORIO_INTERFAZ / "recursos" / "img" / "icono.svg"

# ---------------------------------------------------------------------------
# Identidad de la aplicación
# ---------------------------------------------------------------------------
NOMBRE_APLICACION: Final[str] = "Agenda Académica Inteligente"
IDENTIFICADOR_APLICACION: Final[str] = "agenda-academica-inteligente"
ORGANIZACION: Final[str] = "Universidad"

# ---------------------------------------------------------------------------
# Valores iniciales de configuración (clave -> valor serializado)
# ---------------------------------------------------------------------------
CONFIGURACION_PREDETERMINADA: Final[dict[str, str]] = {
    "tema": "cristal-medianoche",
    "opacidad_gadget": "0.92",
    "gadget_visible": "1",
    "gadget_bloqueado": "0",
    "gadget_compacto": "0",
    "gadget_posicion_x": "",
    "gadget_posicion_y": "",
    "inicio_automatico": "0",
    "notificaciones_activas": "1",
    "resumen_matutino": "1",
    "hora_resumen_matutino": "08:00",
    "avisos_predeterminados": "1440,120,15",
    "duracion_pomodoro": "25",
    "duracion_descanso": "5",
    "sincronizacion_automatica": "1",
    "minutos_sincronizacion": "60",
    "nombre_estudiante": "Estudiante",
    "objetivo_academico": "5.0",
}

# Antelaciones de aviso disponibles, en minutos, con su etiqueta legible.
ANTELACIONES_AVISO: Final[dict[int, str]] = {
    0: "En el momento",
    15: "15 minutos antes",
    60: "1 hora antes",
    120: "2 horas antes",
    1440: "1 día antes",
    2880: "2 días antes",
    10080: "1 semana antes",
}

# Paleta usada al crear asignaturas nuevas (colores accesibles en los 3 temas).
PALETA_ASIGNATURAS: Final[tuple[str, ...]] = (
    "#7c6cff",
    "#28c8a0",
    "#ff7a59",
    "#ffc857",
    "#4aa8ff",
    "#ff5c8a",
    "#9b8cff",
    "#3ddc97",
)


def asegurar_directorios() -> None:
    """Crea los directorios de datos y respaldos si no existen.

    La función es idempotente: puede llamarse tantas veces como sea necesario.
    Se invoca al arrancar la aplicación y antes de crear un respaldo.
    """

    DIRECTORIO_DATOS.mkdir(parents=True, exist_ok=True)
    DIRECTORIO_RESPALDOS.mkdir(parents=True, exist_ok=True)
