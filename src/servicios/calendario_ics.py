"""Analizador y sincronizador de calendarios iCalendar (``.ics``).

Permite tres flujos:

1. **Importación local** de un archivo descargado de Moodle, Google Calendar u
   Outlook.
2. **Suscripción por URL** con sincronización periódica y timeout de red.
3. **Deduplicación por UID**: un mismo evento no se duplica al resincronizar y
   sus cambios de hora o título se actualizan en lugar de insertarse de nuevo.

El analizador implementa el subconjunto de RFC 5545 necesario para calendarios
académicos: plegado de líneas, propiedades con parámetros, fechas con y sin
hora, zonas UTC, texto escapado y recurrencias ``DAILY``/``WEEKLY``.

Example:
    >>> analizador = AnalizadorICS()
    >>> eventos = analizador.analizar(texto_ics)
    >>> sincronizador = SincronizadorICS(contexto)
    >>> resultado = sincronizador.importar_texto(texto_ics)
"""

from __future__ import annotations

import logging
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from src.base_datos.contexto import ContextoDatos
from src.utilidades import a_iso, ahora, desde_iso

REGISTRO = logging.getLogger(__name__)

# Límites defensivos para feeds grandes o mal formados.
MAX_EVENTOS_POR_FEED = 2000
MAX_OCURRENCIAS_RECURRENTES = 120

_PATRON_PROPIEDAD = re.compile(r"^(?P<nombre>[A-Za-z0-9-]+)(?P<parametros>(?:;[^:]*)?):(?P<valor>.*)$")


@dataclass
class EventoICS:
    """Evento normalizado extraído de un feed iCalendar.

    Attributes:
        uid: Identificador global del evento (obligatorio para deduplicar).
        titulo: Resumen legible.
        inicio: Fecha y hora ISO de inicio.
        fin: Fecha y hora ISO de fin.
        todo_el_dia: Indica si el evento ocupa el día completo.
        descripcion: Texto libre sin escapes.
        ubicacion: Lugar o enlace.
        tipo: Tipo inferido (``examen``, ``entrega`` o ``clase``).
        prioridad: Prioridad inferida para la interfaz.
        recurrencia: Regla RRULE original, si existe.
    """

    uid: str
    titulo: str
    inicio: str
    fin: str
    todo_el_dia: bool = False
    descripcion: str = ""
    ubicacion: str = ""
    tipo: str = "clase"
    prioridad: str = "media"
    recurrencia: str = ""
    extras: dict[str, str] = field(default_factory=dict)


def _desplegar_lineas(texto: str) -> list[str]:
    """Despliega las líneas plegadas de un archivo iCalendar.

    El estándar permite partir propiedades largas insertando ``CRLF`` seguido de
    un espacio o tabulador. Esta función reconstruye la línea lógica completa.

    Args:
        texto: Contenido bruto del archivo.

    Returns:
        Líneas lógicas sin plegado.
    """

    lineas: list[str] = []
    for linea in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if linea.startswith((" ", "\t")) and lineas:
            lineas[-1] += linea[1:]
        else:
            lineas.append(linea)
    return lineas


def _desescapar(texto: str) -> str:
    """Convierte las secuencias escapadas de iCalendar a texto plano.

    Args:
        texto: Valor con ``\\n``, ``\\,``, ``\\;`` o ``\\\\``.

    Returns:
        Texto legible.
    """

    return (
        texto.replace("\\N", "\n")
        .replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _separar_parametros(segmento: str) -> dict[str, str]:
    """Extrae los parámetros de una propiedad iCalendar.

    Args:
        segmento: Texto posterior al nombre, por ejemplo
            ``";TZID=Europe/Madrid"``.

    Returns:
        Diccionario de parámetros en mayúsculas.
    """

    parametros: dict[str, str] = {}
    for parte in segmento.split(";")[1:]:
        if "=" in parte:
            clave, valor = parte.split("=", maxsplit=1)
            parametros[clave.upper()] = valor.strip('"')
    return parametros


def _interpretar_fecha(valor: str, parametros: dict[str, str]) -> tuple[datetime, bool]:
    """Interpreta una propiedad ``DTSTART``/``DTEND``.

    Args:
        valor: Texto de la fecha (``20260514``, ``20260514T090000Z``…).
        parametros: Parámetros de la propiedad (``VALUE``, ``TZID``).

    Returns:
        Tupla ``(instante_local, es_dia_completo)``.

    Raises:
        ValueError: Si el formato no se reconoce.
    """

    valor = valor.strip()
    es_fecha = parametros.get("VALUE", "").upper() == "DATE" or (
        len(valor) == 8 and "T" not in valor
    )
    if es_fecha:
        return datetime.strptime(valor[:8], "%Y%m%d"), True

    es_utc = valor.endswith("Z")
    limpio = valor.rstrip("Z")
    formatos = ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%dT%H%S")
    for formato in formatos:
        try:
            momento = datetime.strptime(limpio, formato)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Fecha iCalendar no reconocida: {valor}")

    if es_utc:
        momento = momento.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    return momento, False


class AnalizadorICS:
    """Convierte texto iCalendar en objetos :class:`EventoICS`."""

    def analizar(self, texto: str) -> list[EventoICS]:
        """Analiza un documento iCalendar completo.

        Args:
            texto: Contenido del archivo ``.ics``.

        Returns:
            Lista de eventos normalizados. Las entradas sin ``UID`` reciben uno
            derivado del título y la fecha para poder deduplicarlas.

        Raises:
            ValueError: Si el texto está vacío o no contiene ningún ``VEVENT``.
        """

        if not texto or "BEGIN:VEVENT" not in texto.upper():
            raise ValueError("El contenido no es un calendario iCalendar con eventos")

        eventos: list[EventoICS] = []
        bloque: dict[str, tuple[str, dict[str, str]]] | None = None
        for linea in _desplegar_lineas(texto):
            linea_limpia = linea.strip()
            if not linea_limpia:
                continue
            coincidencia = _PATRON_PROPIEDAD.match(linea_limpia)
            if not coincidencia:
                continue
            nombre = coincidencia.group("nombre").upper()
            parametros = _separar_parametros(coincidencia.group("parametros") or "")
            valor = coincidencia.group("valor")

            if nombre == "BEGIN" and valor.upper() == "VEVENT":
                bloque = {}
                continue
            if nombre == "END" and valor.upper() == "VEVENT":
                if bloque is not None:
                    try:
                        eventos.extend(self._construir_evento(bloque))
                    except (KeyError, ValueError) as error:
                        REGISTRO.warning("Evento ICS descartado: %s", error)
                bloque = None
                continue
            if bloque is not None:
                bloque[nombre] = (valor, parametros)

            if len(eventos) >= MAX_EVENTOS_POR_FEED:
                break

        if not eventos:
            raise ValueError("El calendario no contiene eventos válidos")
        return eventos

    def _construir_evento(
        self, bloque: dict[str, tuple[str, dict[str, str]]]
    ) -> list[EventoICS]:
        """Construye uno o varios eventos a partir de un bloque ``VEVENT``.

        Si el bloque contiene ``RRULE``, se generan las ocurrencias diarias o
        semanales indicadas (hasta :data:`MAX_OCURRENCIAS_RECURRENTES`).

        Args:
            bloque: Propiedades del bloque, indexadas por nombre.

        Returns:
            Lista de eventos (una sola entrada si no hay recurrencia).

        Raises:
            ValueError: Si faltan ``DTSTART`` o el título.
        """

        if "DTSTART" not in bloque:
            raise ValueError("VEVENT sin DTSTART")
        inicio, todo_el_dia = _interpretar_fecha(*bloque["DTSTART"])
        if "DTEND" in bloque:
            fin, _ = _interpretar_fecha(*bloque["DTEND"])
        elif "DURATION" in bloque:
            fin = inicio + self._interpretar_duracion(bloque["DURATION"][0])
        else:
            fin = inicio + (timedelta(days=1) if todo_el_dia else timedelta(hours=1))

        titulo = _desescapar(bloque.get("SUMMARY", ("(Sin título)", {}))[0]).strip()
        if not titulo:
            raise ValueError("VEVENT sin título")
        descripcion = _desescapar(bloque.get("DESCRIPTION", ("", {}))[0])
        ubicacion = _desescapar(bloque.get("LOCATION", ("", {}))[0])
        uid_base = _desescapar(bloque.get("UID", ("", {}))[0])
        if not uid_base:
            uid_base = f"sin-uid-{inicio.strftime('%Y%m%d%H%M')}-{abs(hash(titulo)) % 100000}"
        tipo, prioridad = self._inferir_tipo(titulo, descripcion)
        recurrencia = bloque.get("RRULE", ("", {}))[0]

        ocurrencias = self._expandir_recurrencia(inicio, fin, recurrencia)
        eventos: list[EventoICS] = []
        for indice, (inicio_ocurrencia, fin_ocurrencia) in enumerate(ocurrencias):
            eventos.append(
                EventoICS(
                    uid=uid_base if indice == 0 else f"{uid_base}-{indice}",
                    titulo=titulo,
                    inicio=a_iso(inicio_ocurrencia),
                    fin=a_iso(fin_ocurrencia),
                    todo_el_dia=todo_el_dia,
                    descripcion=descripcion,
                    ubicacion=ubicacion,
                    tipo=tipo,
                    prioridad=prioridad,
                    recurrencia=recurrencia,
                )
            )
        return eventos

    @staticmethod
    def _interpretar_duracion(texto: str) -> timedelta:
        """Convierte una duración ISO 8601 básica (``PT1H30M``, ``P1D``).

        Args:
            texto: Duración en formato iCalendar.

        Returns:
            Desplazamiento temporal equivalente.
        """

        coincidencia = re.match(
            r"^P(?:(?P<dias>\d+)D)?(?:T(?:(?P<horas>\d+)H)?(?:(?P<minutos>\d+)M)?)?$",
            texto.strip().upper(),
        )
        if not coincidencia:
            return timedelta(hours=1)
        partes = {clave: int(valor or 0) for clave, valor in coincidencia.groupdict().items()}
        return timedelta(days=partes["dias"], hours=partes["horas"], minutes=partes["minutos"])

    @staticmethod
    def _inferir_tipo(titulo: str, descripcion: str) -> tuple[str, str]:
        """Deduce el tipo de evento y su prioridad a partir del texto.

        Args:
            titulo: Resumen del evento.
            descripcion: Cuerpo del evento.

        Returns:
            Tupla ``(tipo, prioridad)`` compatible con la base de datos.
        """

        texto = f"{titulo} {descripcion}".lower()
        if any(palabra in texto for palabra in ("examen", "parcial", "prueba escrita", "exam")):
            return "examen", "alta"
        if any(palabra in texto for palabra in ("entrega", "práctica", "practica", "tarea", "proyecto", "deadline")):
            return "entrega", "alta"
        return "clase", "media"

    @staticmethod
    def _expandir_recurrencia(
        inicio: datetime, fin: datetime, regla: str
    ) -> list[tuple[datetime, datetime]]:
        """Expande una regla ``RRULE`` sencilla en ocurrencias concretas.

        Solo se admiten frecuencias ``DAILY`` y ``WEEKLY``, con ``COUNT`` o
        ``UNTIL``. El resto de reglas se interpreta como un evento único para
        evitar duplicados masivos.

        Args:
            inicio: Inicio de la primera ocurrencia.
            fin: Fin de la primera ocurrencia.
            regla: Valor de ``RRULE``.

        Returns:
            Lista de pares ``(inicio, fin)``; al menos la ocurrencia original.
        """

        if not regla:
            return [(inicio, fin)]
        propiedades = {
            clave: valor
            for parte in regla.split(";")
            if "=" in parte
            for clave, valor in [parte.split("=", maxsplit=1)]
        }
        frecuencia = propiedades.get("FREQ", "").upper()
        if frecuencia not in ("DAILY", "WEEKLY"):
            return [(inicio, fin)]

        intervalo = max(1, int(propiedades.get("INTERVAL", "1") or 1))
        try:
            total = min(int(propiedades.get("COUNT", "12")), MAX_OCURRENCIAS_RECURRENTES)
        except ValueError:
            total = 12
        limite: datetime | None = None
        if propiedades.get("UNTIL"):
            try:
                limite, _ = _interpretar_fecha(propiedades["UNTIL"], {})
            except ValueError:
                limite = None

        duracion = fin - inicio
        salto = timedelta(days=intervalo if frecuencia == "DAILY" else 7 * intervalo)
        ocurrencias: list[tuple[datetime, datetime]] = []
        actual = inicio
        for _ in range(total):
            if limite and actual > limite:
                break
            ocurrencias.append((actual, actual + duracion))
            actual += salto
        return ocurrencias or [(inicio, fin)]


class SincronizadorICS:
    """Importa y sincroniza feeds iCalendar con la base de datos.

    Args:
        contexto: Contexto de datos.
        descargador: Función ``url -> texto``. Por defecto usa ``urllib`` con
            timeout de 15 segundos. Las pruebas inyectan un descargador local.
    """

    def __init__(
        self,
        contexto: ContextoDatos,
        descargador: Callable[[str], str] | None = None,
        analizador: AnalizadorICS | None = None,
    ) -> None:
        self.contexto = contexto
        self.descargador = descargador or self._descargar_url
        self.analizador = analizador or AnalizadorICS()

    @staticmethod
    def _descargar_url(url: str) -> str:
        """Descarga un feed remoto con timeout y agente de usuario identificable.

        Args:
            url: Dirección HTTP(S) del calendario.

        Returns:
            Contenido de la respuesta como texto.

        Raises:
            ValueError: Si la URL no es HTTP(S).
            OSError: Si la descarga falla o expira.
        """

        if not url.startswith(("http://", "https://")):
            raise ValueError("Solo se admiten feeds http:// o https://")
        solicitud = urllib.request.Request(
            url,
            headers={"User-Agent": "AgendaAcademica/1.0 (+https://github.com/afc00073-lab/agenda)"},
        )
        with urllib.request.urlopen(solicitud, timeout=15) as respuesta:  # noqa: S310 - URL validada
            datos: bytes = respuesta.read()
        return datos.decode("utf-8", errors="replace")

    def importar_archivo(self, ruta: str | Path, origen: str = "ics") -> dict[str, Any]:
        """Importa un archivo ``.ics`` del sistema de archivos.

        Args:
            ruta: Ruta del archivo.
            origen: Etiqueta de procedencia (``ics`` o ``url``).

        Returns:
            Resumen con contadores ``creados``, ``actualizados``, ``omitidos``.

        Raises:
            OSError: Si el archivo no se puede leer.
            ValueError: Si el contenido no es un calendario válido.
        """

        contenido = Path(ruta).read_text(encoding="utf-8", errors="replace")
        return self.importar_texto(contenido, origen=origen, referencia=str(ruta))

    def importar_texto(
        self,
        texto: str,
        origen: str = "ics",
        referencia: str = "importación local",
    ) -> dict[str, Any]:
        """Importa eventos desde texto iCalendar y evita duplicados por UID.

        Args:
            texto: Contenido iCalendar.
            origen: ``ics`` o ``url``.
            referencia: Nombre del archivo o URL para el informe.

        Returns:
            Diccionario con contadores y la lista de incidencias.

        Raises:
            ValueError: Si el texto no contiene eventos válidos.
        """

        eventos = self.analizador.analizar(texto)
        creados = 0
        actualizados = 0
        omitidos = 0
        incidencias: list[str] = []
        for evento in eventos:
            try:
                existente = self.contexto.eventos.buscar_por_uid(evento.uid)
                if existente is None:
                    self.contexto.eventos.crear(
                        titulo=evento.titulo,
                        fecha_inicio=evento.inicio,
                        fecha_fin=evento.fin,
                        tipo=evento.tipo,
                        descripcion=evento.descripcion,
                        todo_el_dia=evento.todo_el_dia,
                        ubicacion=evento.ubicacion,
                        prioridad=evento.prioridad,
                        uid_ics=evento.uid,
                        origen=origen,
                        recordatorios=(1440, 120, 15),
                    )
                    creados += 1
                else:
                    cambios: dict[str, Any] = {
                        "titulo": evento.titulo,
                        "fecha_inicio": evento.inicio,
                        "fecha_fin": evento.fin,
                        "descripcion": evento.descripcion,
                        "ubicacion": evento.ubicacion,
                        "todo_el_dia": evento.todo_el_dia,
                        "tipo": evento.tipo,
                    }
                    if any(existente.get(clave) != valor for clave, valor in cambios.items()):
                        self.contexto.eventos.actualizar(int(existente["id"]), cambios)
                        actualizados += 1
                    else:
                        omitidos += 1
            except ValueError as error:
                incidencias.append(f"{evento.titulo}: {error}")

        return {
            "ok": True,
            "referencia": referencia,
            "total": len(eventos),
            "creados": creados,
            "actualizados": actualizados,
            "omitidos": omitidos,
            "incidencias": incidencias,
        }

    def sincronizar_suscripcion(self, suscripcion_id: int) -> dict[str, Any]:
        """Sincroniza una suscripción concreta.

        Args:
            suscripcion_id: Identificador de la suscripción.

        Returns:
            Resultado de la importación, o un diccionario de error controlado.
        """

        suscripcion = self.contexto.suscripciones.obtener(suscripcion_id)
        if suscripcion is None:
            return {"ok": False, "error": "La suscripción no existe"}
        try:
            contenido = self.descargador(str(suscripcion["url"]))
            resultado = self.importar_texto(
                contenido,
                origen="url",
                referencia=str(suscripcion["nombre"]),
            )
        except (OSError, ValueError) as error:
            REGISTRO.warning("Sincronización fallida de %s: %s", suscripcion["nombre"], error)
            return {
                "ok": False,
                "error": f"No se pudo sincronizar «{suscripcion['nombre']}»: {error}",
                "suscripcion_id": suscripcion_id,
            }
        self.contexto.suscripciones.marcar_sincronizada(suscripcion_id, a_iso(ahora()))
        resultado["suscripcion_id"] = suscripcion_id
        resultado["nombre"] = suscripcion["nombre"]
        return resultado

    def sincronizar_todas(self, momento: datetime | None = None) -> list[dict[str, Any]]:
        """Sincroniza las suscripciones activas cuya frecuencia haya vencido.

        Args:
            momento: Instante de referencia para comparar frecuencias.

        Returns:
            Lista de resultados, una por suscripción procesada.
        """

        referencia = momento or ahora()
        resultados: list[dict[str, Any]] = []
        for suscripcion in self.contexto.suscripciones.listar(solo_activas=True):
            ultima = str(suscripcion.get("ultima_sincronizacion") or "")
            if ultima:
                try:
                    proxima = desde_iso(ultima) + timedelta(
                        minutes=int(suscripcion.get("frecuencia_minutos") or 60)
                    )
                    if referencia < proxima:
                        continue
                except ValueError:
                    pass
            resultados.append(self.sincronizar_suscripcion(int(suscripcion["id"])))
        return resultados

    def importar_varios(self, rutas: Iterable[str | Path]) -> list[dict[str, Any]]:
        """Importa una colección de archivos y acumula los resultados.

        Args:
            rutas: Rutas de archivos ``.ics``.

        Returns:
            Lista de resultados individuales; los archivos ilegibles se
            devuelven como error sin detener el resto.
        """

        resultados: list[dict[str, Any]] = []
        for ruta in rutas:
            try:
                resultados.append(self.importar_archivo(ruta))
            except (OSError, ValueError) as error:
                resultados.append({"ok": False, "referencia": str(ruta), "error": str(error)})
        return resultados
