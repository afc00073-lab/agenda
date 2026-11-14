"""Esquema versionado de la base de datos SQLite.

El esquema se define como una lista ordenada de *migraciones*. Cada migración
tiene un número de versión, una descripción legible y una lista de sentencias
DDL que se ejecutan en una única transacción. Para evolucionar la base de datos
basta con añadir una migración nueva al final; el gestor aplica únicamente las
pendientes y registra la versión aplicada.

Attributes:
    MIGRACIONES: Secuencia inmutable de migraciones disponibles.
    VERSION_ESQUEMA: Última versión conocida por este código.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Migracion:
    """Describe una migración del esquema.

    Args:
        version: Número entero creciente que identifica la migración.
        descripcion: Texto corto en español para el historial de migraciones.
        sentencias: Sentencias SQL que se ejecutan de forma atómica.
    """

    version: int
    descripcion: str
    sentencias: tuple[str, ...]


_MIGRACION_1: Final[Migracion] = Migracion(
    version=1,
    descripcion="Tablas base: asignaturas, eventos, evaluaciones y sesiones de estudio",
    sentencias=(
        """
        CREATE TABLE IF NOT EXISTS asignaturas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT    NOT NULL,
            codigo      TEXT    NOT NULL DEFAULT '',
            color       TEXT    NOT NULL DEFAULT '#7c6cff',
            profesor    TEXT    NOT NULL DEFAULT '',
            aula        TEXT    NOT NULL DEFAULT '',
            creditos    REAL    NOT NULL DEFAULT 6.0,
            enlaces     TEXT    NOT NULL DEFAULT '[]',
            creada_en   TEXT    NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS eventos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo         TEXT    NOT NULL,
            descripcion    TEXT    NOT NULL DEFAULT '',
            tipo           TEXT    NOT NULL DEFAULT 'tarea'
                           CHECK (tipo IN ('clase', 'examen', 'entrega', 'tarea', 'estudio')),
            fecha_inicio   TEXT    NOT NULL,
            fecha_fin      TEXT    NOT NULL,
            todo_el_dia    INTEGER NOT NULL DEFAULT 0,
            asignatura_id  INTEGER REFERENCES asignaturas(id) ON DELETE SET NULL,
            ubicacion      TEXT    NOT NULL DEFAULT '',
            prioridad      TEXT    NOT NULL DEFAULT 'media'
                           CHECK (prioridad IN ('baja', 'media', 'alta', 'critica')),
            estado_kanban  TEXT    NOT NULL DEFAULT 'pendiente'
                           CHECK (estado_kanban IN ('pendiente', 'en_desarrollo', 'revision', 'entregado')),
            completado     INTEGER NOT NULL DEFAULT 0,
            uid_ics        TEXT,
            origen         TEXT    NOT NULL DEFAULT 'manual'
                           CHECK (origen IN ('manual', 'ics', 'url')),
            recordatorios  TEXT    NOT NULL DEFAULT '1440,120,15',
            creado_en      TEXT    NOT NULL,
            actualizado_en TEXT    NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS evaluaciones (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            asignatura_id INTEGER NOT NULL REFERENCES asignaturas(id) ON DELETE CASCADE,
            nombre        TEXT    NOT NULL,
            tipo          TEXT    NOT NULL DEFAULT 'examen'
                          CHECK (tipo IN ('practica', 'examen', 'proyecto', 'participacion')),
            peso          REAL    NOT NULL CHECK (peso >= 0 AND peso <= 100),
            nota          REAL             CHECK (nota IS NULL OR nota >= 0),
            nota_maxima   REAL    NOT NULL DEFAULT 10.0 CHECK (nota_maxima > 0),
            fecha         TEXT    NOT NULL DEFAULT '',
            creada_en     TEXT    NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sesiones_estudio (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            asignatura_id    INTEGER REFERENCES asignaturas(id) ON DELETE SET NULL,
            evento_id        INTEGER REFERENCES eventos(id) ON DELETE SET NULL,
            inicio           TEXT    NOT NULL,
            fin              TEXT    NOT NULL,
            duracion_minutos INTEGER NOT NULL CHECK (duracion_minutos >= 0),
            modo             TEXT    NOT NULL DEFAULT '25/5',
            completada       INTEGER NOT NULL DEFAULT 1,
            notas            TEXT    NOT NULL DEFAULT ''
        )
        """,
    ),
)

_MIGRACION_2: Final[Migracion] = Migracion(
    version=2,
    descripcion="Suscripciones ICS, notificaciones, subtareas, configuración e índices",
    sentencias=(
        """
        CREATE TABLE IF NOT EXISTS suscripciones_ics (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre                TEXT    NOT NULL,
            url                   TEXT    NOT NULL,
            activa                INTEGER NOT NULL DEFAULT 1,
            ultima_sincronizacion TEXT    NOT NULL DEFAULT '',
            frecuencia_minutos    INTEGER NOT NULL DEFAULT 60,
            creada_en             TEXT    NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notificaciones (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id        INTEGER REFERENCES eventos(id) ON DELETE CASCADE,
            titulo           TEXT    NOT NULL,
            mensaje          TEXT    NOT NULL DEFAULT '',
            programada_para  TEXT    NOT NULL,
            enviada          INTEGER NOT NULL DEFAULT 0,
            enviada_en       TEXT    NOT NULL DEFAULT '',
            pospuesta_hasta  TEXT    NOT NULL DEFAULT '',
            vista            INTEGER NOT NULL DEFAULT 0,
            creada_en        TEXT    NOT NULL,
            UNIQUE (evento_id, programada_para)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS subtareas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id  INTEGER NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
            titulo     TEXT    NOT NULL,
            completada INTEGER NOT NULL DEFAULT 0,
            orden      INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS configuracion (
            clave         TEXT PRIMARY KEY,
            valor         TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS migraciones (
            version     INTEGER PRIMARY KEY,
            descripcion TEXT NOT NULL,
            aplicada_en TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_eventos_fecha ON eventos (fecha_inicio)",
        "CREATE INDEX IF NOT EXISTS idx_eventos_asignatura ON eventos (asignatura_id)",
        "CREATE INDEX IF NOT EXISTS idx_eventos_estado_kanban ON eventos (estado_kanban)",
        "CREATE INDEX IF NOT EXISTS idx_eventos_completado ON eventos (completado)",
        "CREATE INDEX IF NOT EXISTS idx_evaluaciones_asignatura ON evaluaciones (asignatura_id)",
        "CREATE INDEX IF NOT EXISTS idx_sesiones_inicio ON sesiones_estudio (inicio)",
        "CREATE INDEX IF NOT EXISTS idx_notificaciones_pendientes "
        "ON notificaciones (enviada, programada_para)",
        "CREATE INDEX IF NOT EXISTS idx_subtareas_evento ON subtareas (evento_id, orden)",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_eventos_uid_ics
        ON eventos (uid_ics) WHERE uid_ics IS NOT NULL
        """,
    ),
)

MIGRACIONES: Final[tuple[Migracion, ...]] = (_MIGRACION_1, _MIGRACION_2)
VERSION_ESQUEMA: Final[int] = max(migracion.version for migracion in MIGRACIONES)
