"""Motor de notificaciones y recordatorios inteligentes.

El servicio es **independiente de Qt y de la red**: recibe un reloj y un
notificador inyectables, lo que permite probarlo de forma determinista. La capa
de ventanas lo activa con un ``QTimer`` cada 30 segundos.

Responsabilidades:

* convertir las antelaciones de cada evento (1 día, 2 horas, 15 minutos…) en
  avisos concretos con fecha de entrega;
* enviar los avisos vencidos al centro de notificaciones del sistema operativo;
* construir y enviar un único **resumen matutino** al día;
* registrar todo en SQLite para alimentar la campana de la interfaz.

Example:
    >>> planificador = PlanificadorNotificaciones(contexto, notificador=falso)
    >>> enviados = planificador.revisar(datetime(2026, 5, 1, 8, 0))
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from src.base_datos.contexto import ContextoDatos
from src.utilidades import a_iso, desde_iso, fecha_legible, ahora

REGISTRO = logging.getLogger(__name__)

# Ventana de planificación: se preparan avisos para los eventos de la semana.
DIAS_PLANIFICACION = 7
# Margen de tolerancia para no crear avisos de recordatorios muy antiguos.
MARGEN_ANTIGUEDAD_MINUTOS = 60


class Notificador(Protocol):
    """Contrato mínimo de un notificador de sistema operativo."""

    def enviar(self, titulo: str, mensaje: str, urgencia: str = "normal") -> bool:
        """Muestra una notificación nativa.

        Args:
            titulo: Texto principal.
            mensaje: Cuerpo del aviso.
            urgencia: ``baja``, ``normal`` o ``critica``.

        Returns:
            ``True`` si el sistema aceptó la notificación.
        """

        ...


class NotificadorNativo:
    """Envía notificaciones al sistema operativo con degradación elegante.

    En Linux y macOS usa ``desktop-notifier``; en Windows usa ``winotify``. Si
    ninguna biblioteca está instalada (por ejemplo, en una instalación mínima),
    escribe el aviso en el registro y devuelve ``False`` sin interrumpir la app.

    Args:
        nombre_aplicacion: Nombre mostrado como remitente.
        icono: Ruta opcional al icono de la notificación.
    """

    def __init__(self, nombre_aplicacion: str = "Agenda Académica", icono: str | None = None) -> None:
        self.nombre_aplicacion = nombre_aplicacion
        self.icono = icono
        self._notificador = None
        self._motor = "registro"
        self._preparar_motor()

    def _preparar_motor(self) -> None:
        """Detecta e inicializa la biblioteca nativa disponible.

        No lanza excepciones: cualquier fallo degrada a notificaciones internas.
        """

        try:  # pragma: no cover - depende del sistema operativo
            from desktop_notifier import DesktopNotifier

            self._notificador = DesktopNotifier(app_name=self.nombre_aplicacion)
            self._motor = "desktop-notifier"
            return
        except Exception:  # noqa: BLE001 - importación opcional
            pass
        try:  # pragma: no cover - solo Windows
            from winotify import Notification

            self._notificador = Notification
            self._motor = "winotify"
        except Exception:  # noqa: BLE001 - importación opcional
            self._motor = "registro"

    @property
    def motor(self) -> str:
        """Nombre del backend de notificaciones activo.

        Returns:
            ``desktop-notifier``, ``winotify`` o ``registro``.
        """

        return self._motor

    def enviar(self, titulo: str, mensaje: str, urgencia: str = "normal") -> bool:
        """Muestra una notificación nativa.

        Args:
            titulo: Texto principal del aviso.
            mensaje: Cuerpo del aviso.
            urgencia: Nivel declarativo; se traduce al backend cuando sea posible.

        Returns:
            ``True`` si se entregó al sistema operativo.
        """

        try:  # pragma: no cover - integración con el SO
            if self._motor == "desktop-notifier" and self._notificador is not None:
                from desktop_notifier import Urgency

                mapa = {"baja": Urgency.Low, "normal": Urgency.Normal, "critica": Urgency.Critical}
                self._notificador.send_sync(
                    title=titulo,
                    message=mensaje,
                    urgency=mapa.get(urgencia, Urgency.Normal),
                )
                return True
            if self._motor == "winotify" and self._notificador is not None:
                aviso = self._notificador(
                    app_id=self.nombre_aplicacion,
                    title=titulo,
                    msg=mensaje,
                    icon=self.icono or "",
                )
                aviso.show()
                return True
        except Exception as error:  # noqa: BLE001 - never romper la UI
            REGISTRO.warning("No se pudo enviar la notificación nativa: %s", error)
        REGISTRO.info("[notificación] %s — %s", titulo, mensaje)
        return False


class PlanificadorNotificaciones:
    """Calcula, registra y entrega los recordatorios académicos.

    Args:
        contexto: Contexto de datos con acceso a eventos, notificaciones y
            configuración.
        notificador: Implementación de envío. Por defecto, :class:`NotificadorNativo`.
        reloj: Función que devuelve el instante actual. Inyectable en pruebas.

    Attributes:
        avisos_enviados: Contador acumulado de avisos entregados en la sesión.
    """

    def __init__(
        self,
        contexto: ContextoDatos,
        notificador: Notificador | None = None,
        reloj: Callable[[], datetime] = ahora,
    ) -> None:
        self.contexto = contexto
        self.notificador = notificador or NotificadorNativo()
        self.reloj = reloj
        self.avisos_enviados = 0

    # ------------------------------------------------------------------
    # Planificación
    # ------------------------------------------------------------------
    def calcular_avisos(self, evento: dict[str, Any]) -> list[datetime]:
        """Calcula los instantes de aviso de un evento.

        Args:
            evento: Evento con ``fecha_inicio`` y ``recordatorios``.

        Returns:
            Lista de instantes ordenados de forma ascendente. Los recordatorios
            posteriores al inicio se descartan.
        """

        inicio = desde_iso(str(evento["fecha_inicio"]))
        recordatorios = evento.get("recordatorios") or []
        avisos: list[datetime] = []
        for minutos in recordatorios:
            try:
                momento = inicio - timedelta(minutes=int(minutos))
            except (TypeError, ValueError):
                continue
            if momento <= inicio:
                avisos.append(momento)
        return sorted(set(avisos))

    def preparar_avisos(self, momento: datetime | None = None) -> int:
        """Crea en SQLite los avisos futuros que aún no existen.

        Recorre los eventos no completados de los próximos días y programa una
        notificación por cada antelación. La restricción única de la tabla evita
        duplicados aunque el método se ejecute repetidamente.

        Args:
            momento: Instante de referencia. Por defecto, el reloj del servicio.

        Returns:
            Número de avisos nuevos insertados.
        """

        referencia = momento or self.reloj()
        limite = referencia + timedelta(days=DIAS_PLANIFICACION)
        eventos = self.contexto.eventos.listar(
            desde=a_iso(referencia - timedelta(minutes=MARGEN_ANTIGUEDAD_MINUTOS)),
            hasta=a_iso(limite),
            tipos=("clase", "examen", "entrega", "tarea"),
            solo_pendientes=True,
        )
        creados = 0
        minimo = referencia - timedelta(minutes=MARGEN_ANTIGUEDAD_MINUTOS)
        for evento in eventos:
            if evento["tipo"] == "tarea" and evento["estado_kanban"] == "entregado":
                continue
            for aviso in self.calcular_avisos(evento):
                if aviso < minimo:
                    continue
                titulo, mensaje = self._texto_aviso(evento, aviso)
                nueva = self.contexto.notificaciones.crear(
                    titulo=titulo,
                    mensaje=mensaje,
                    programada_para=a_iso(aviso),
                    evento_id=int(evento["id"]),
                )
                if nueva is not None:
                    creados += 1
        return creados

    def _texto_aviso(self, evento: dict[str, Any], aviso: datetime) -> tuple[str, str]:
        """Genera el título y el cuerpo de un aviso.

        Args:
            evento: Evento origen.
            aviso: Instante programado.

        Returns:
            Tupla ``(titulo, mensaje)`` lista para el sistema operativo.
        """

        inicio = desde_iso(str(evento["fecha_inicio"]))
        diferencia = inicio - aviso
        horas = diferencia.total_seconds() / 3600
        if horas >= 23:
            cuando = f"en {max(1, round(horas / 24))} día(s)"
        elif horas >= 1:
            cuando = f"en {round(horas)} hora(s)"
        else:
            cuando = f"en {max(1, round(diferencia.total_seconds() / 60))} minuto(s)"

        etiquetas = {
            "examen": "📝 Examen próximo",
            "entrega": "📦 Entrega próxima",
            "clase": "🏫 Clase próxima",
            "tarea": "✅ Tarea pendiente",
        }
        titulo = f"{etiquetas.get(evento['tipo'], '🔔 Recordatorio')}: {evento['titulo']}"
        partes = [f"Comienza {cuando} ({inicio.strftime('%d/%m a las %H:%M')})."]
        if evento.get("asignatura_nombre"):
            partes.append(f"Asignatura: {evento['asignatura_nombre']}.")
        if evento.get("ubicacion"):
            partes.append(f"Lugar: {evento['ubicacion']}.")
        return titulo, " ".join(partes)

    # ------------------------------------------------------------------
    # Envío
    # ------------------------------------------------------------------
    def enviar_pendientes(self, momento: datetime | None = None) -> list[dict[str, Any]]:
        """Entrega los avisos vencidos y los marca como enviados.

        Args:
            momento: Instante de referencia.

        Returns:
            Lista de notificaciones efectivamente entregadas.
        """

        referencia = momento or self.reloj()
        pendientes = self.contexto.notificaciones.pendientes(a_iso(referencia))
        enviadas: list[dict[str, Any]] = []
        for aviso in pendientes:
            titulo = str(aviso["titulo"])
            mensaje = str(aviso["mensaje"])
            urgencia = "normal"
            if aviso.get("evento_tipo") == "examen":
                urgencia = "critica"
            elif aviso.get("evento_tipo") == "entrega":
                urgencia = "alta"
            self.notificador.enviar(titulo, mensaje, urgencia)
            self.contexto.notificaciones.marcar_enviada(int(aviso["id"]), a_iso(referencia))
            self.avisos_enviados += 1
            enviadas.append(self.contexto.notificaciones.obtener(int(aviso["id"])) or aviso)
        return enviadas

    def construir_resumen(self, momento: datetime | None = None) -> tuple[str, str]:
        """Construye el resumen matutino del día.

        Args:
            momento: Día de referencia.

        Returns:
            Tupla ``(titulo, mensaje)`` con clases, exámenes y entregas.
        """

        referencia = momento or self.reloj()
        eventos = self.contexto.eventos.listar_dia(a_iso(referencia)[:10])
        clases = [evento for evento in eventos if evento["tipo"] == "clase"]
        hitos = [evento for evento in eventos if evento["tipo"] in ("examen", "entrega")]
        pendientes = [evento for evento in eventos if evento["tipo"] == "tarea" and not evento["completado"]]

        titulo = f"☀️ Buenos días · {fecha_legible(referencia).capitalize()}"
        fragmentos = [f"Tienes {len(clases)} clase(s)"]
        if hitos:
            fragmentos.append(
                "hitos: " + ", ".join(f"{hito['titulo']} ({hito['fecha_inicio'][11:16]})" for hito in hitos[:3])
            )
        if pendientes:
            fragmentos.append(f"{len(pendientes)} tarea(s) pendiente(s)")
        if len(fragmentos) == 1:
            fragmentos.append("sin exámenes ni entregas programadas")
        return titulo, ". ".join(fragmentos) + "."

    def enviar_resumen_si_procede(self, momento: datetime | None = None) -> dict[str, Any] | None:
        """Envía el resumen una sola vez al día tras la hora configurada.

        Args:
            momento: Instante de referencia.

        Returns:
            La notificación enviada, o ``None`` si no procedía.
        """

        referencia = momento or self.reloj()
        if self.contexto.configuracion.obtener("resumen_matutino", "1") != "1":
            return None
        hora_configurada = self.contexto.configuracion.obtener("hora_resumen_matutino", "08:00")
        try:
            hora, minuto = (int(parte) for parte in hora_configurada.split(":", maxsplit=1))
        except (ValueError, TypeError):
            hora, minuto = 8, 0
        if (referencia.hour, referencia.minute) < (hora, minuto):
            return None

        programada = referencia.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        clave = a_iso(programada)
        if self.contexto.notificaciones.existe(None, clave):
            return None
        titulo, mensaje = self.construir_resumen(referencia)
        aviso = self.contexto.notificaciones.crear(
            titulo=titulo,
            mensaje=mensaje,
            programada_para=clave,
            evento_id=None,
        )
        if aviso is None:
            return None
        self.notificador.enviar(titulo, mensaje, "normal")
        self.contexto.notificaciones.marcar_enviada(int(aviso["id"]), a_iso(referencia))
        self.avisos_enviados += 1
        return self.contexto.notificaciones.obtener(int(aviso["id"]))

    def revisar(self, momento: datetime | None = None) -> list[dict[str, Any]]:
        """Ciclo completo del demonio de notificaciones.

        Prepara avisos nuevos, envía los vencidos y, si corresponde, entrega el
        resumen matutino. Está pensado para ejecutarse cada 30 segundos desde un
        ``QTimer``.

        Args:
            momento: Instante de referencia; por defecto, el reloj actual.

        Returns:
            Lista de notificaciones enviadas en este ciclo.
        """

        referencia = momento or self.reloj()
        try:
            self.preparar_avisos(referencia)
            enviadas = self.enviar_pendientes(referencia)
        except Exception as error:  # noqa: BLE001 - el temporizador no debe caer
            REGISTRO.exception("Fallo en el ciclo de notificaciones: %s", error)
            return []
        resumen = self.enviar_resumen_si_procede(referencia)
        if resumen is not None:
            enviadas.append(resumen)
        return enviadas
