"""Orquestador de la aplicación de escritorio.

Reúne en un único lugar el ciclo de vida completo de la agenda: crea la
aplicación Qt, abre la base de datos, construye el puente ``QWebChannel``,
instancia la ventana principal, el gadget y la bandeja del sistema, y programa
los temporizadores que mantienen vivos los avisos, la sincronización automática
de calendarios y el reloj Pomodoro.

El diseño separa el arranque (:func:`configurar_aplicacion` y
:func:`iniciar_aplicacion`) de la orquestación (:class:`AplicacionAgenda`) para
que las pruebas puedan instanciar partes sin abrir ventanas reales.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from typing import Sequence

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Qt, Slot
from PySide6.QtWidgets import QApplication

from src.base_datos.contexto import ContextoDatos
from src.configuracion import (
    IDENTIFICADOR_APLICACION,
    NOMBRE_APLICACION,
    ORGANIZACION,
)
from src.puente.api_web import ApiPuente
from src.ventanas.bandeja_sistema import BandejaSistema, cargar_icono
from src.ventanas.ventana_gadget import VentanaGadget
from src.ventanas.ventana_principal import VentanaPrincipal

REGISTRO = logging.getLogger(__name__)

# Frecuencia con la que el demonio revisa recordatorios y resúmenes.
INTERVALO_AVISOS_MS = 30_000
# Frecuencia del reloj interno del Pomodoro.
INTERVALO_POMODORO_MS = 1_000


def configurar_aplicacion(argumentos: Sequence[str] | None = None) -> QApplication:
    """Crea y configura la instancia global de ``QApplication``.

    Debe invocarse antes de construir cualquier ventana. Activa el intercambio
    de contextos OpenGL que exige ``QtWebEngine``, fija la identidad de la
    aplicación y evita que cerrar la última ventana termine el proceso: la
    agenda vive en la bandeja.

    Args:
        argumentos: Argumentos de línea de comandos sin el nombre del programa.

    Returns:
        La aplicación Qt lista para usarse.
    """

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    aplicacion = QApplication(list(argumentos or []))
    aplicacion.setApplicationName(NOMBRE_APLICACION)
    aplicacion.setApplicationDisplayName(NOMBRE_APLICACION)
    aplicacion.setOrganizationName(ORGANIZACION)
    aplicacion.setDesktopFileName(IDENTIFICADOR_APLICACION)
    aplicacion.setWindowIcon(cargar_icono(256))
    aplicacion.setQuitOnLastWindowClosed(False)
    return aplicacion


class AplicacionAgenda(QObject):
    """Coordina servicios, ventanas y temporizadores de la agenda.

    Args:
        aplicacion: Instancia de ``QApplication`` ya configurada.
        mostrar_ventana: Si es ``False``, arranca directamente en la bandeja.
        mostrar_gadget: Si es ``False``, el gadget permanece oculto al inicio.

    Attributes:
        contexto: Fachada de repositorios SQLite.
        api: Puente compartido por la ventana principal y el gadget.
        ventana: Ventana principal con las seis vistas.
        gadget: Gadget flotante «Plan de Hoy».
        bandeja: Icono de la bandeja del sistema.
    """

    def __init__(
        self,
        aplicacion: QApplication,
        mostrar_ventana: bool = True,
        mostrar_gadget: bool = True,
    ) -> None:
        super().__init__()
        self.aplicacion = aplicacion
        self.mostrar_ventana = mostrar_ventana
        self.mostrar_gadget = mostrar_gadget
        self._cerrando = False

        self.contexto = ContextoDatos()
        self.api = ApiPuente(self.contexto)
        self.tema = self.contexto.configuracion.obtener("tema", "cristal-medianoche") or "cristal-medianoche"

        self.ventana = VentanaPrincipal(self.api, tema_inicial=self.tema)
        self.gadget = VentanaGadget(self.api, self.contexto)
        self.bandeja = BandejaSistema(self.ventana)

        self._temporizador_avisos = QTimer(self)
        self._temporizador_sincronizacion = QTimer(self)
        self._temporizador_pomodoro = QTimer(self)

        self._conectar_senales()
        self._programar_temporizadores()
        self._actualizar_bandeja()

    # ------------------------------------------------------------------
    # Cableado de señales
    # ------------------------------------------------------------------
    def _conectar_senales(self) -> None:
        """Conecta bandeja, puente y ventanas entre sí."""

        self.bandeja.abrirSolicitado.connect(self.ventana.mostrar_y_enfocar)
        self.bandeja.gadgetSolicitado.connect(self.alternar_gadget)
        self.bandeja.nuevaTareaSolicitada.connect(self._nueva_tarea)
        self.bandeja.sincronizarSolicitado.connect(self.sincronizar_calendarios)
        self.bandeja.salirSolicitado.connect(self.cerrar)

        self.ventana.ocultadaEnBandeja.connect(self._avisar_ocultacion)
        self.api.notificacionRecibida.connect(self._al_recibir_aviso)
        self.api.datosActualizados.connect(self._al_actualizar_datos)
        self.api.temaCambiado.connect(self._al_cambiar_tema)
        self.api.gadgetConfigurado.connect(self._al_configurar_gadget)

        self._temporizador_avisos.timeout.connect(self._ciclo_avisos)
        self._temporizador_sincronizacion.timeout.connect(self._ciclo_sincronizacion)
        self._temporizador_pomodoro.timeout.connect(self._ciclo_pomodoro)

    def _programar_temporizadores(self) -> None:
        """Arranca los temporizadores y respeta la configuración guardada."""

        self._temporizador_avisos.start(INTERVALO_AVISOS_MS)
        self._temporizador_pomodoro.start(INTERVALO_POMODORO_MS)
        self._reprogramar_sincronizacion()
        # Primer barrido poco después del arranque, sin bloquear la interfaz.
        QTimer.singleShot(4_000, self._ciclo_avisos)

    def _reprogramar_sincronizacion(self) -> None:
        """Ajusta el intervalo de sincronización según las preferencias."""

        activa = self.contexto.configuracion.obtener("sincronizacion_automatica", "1") == "1"
        if not activa:
            self._temporizador_sincronizacion.stop()
            return
        try:
            minutos = int(self.contexto.configuracion.obtener("minutos_sincronizacion", "60") or 60)
        except ValueError:
            minutos = 60
        self._temporizador_sincronizacion.start(max(5, minutos) * 60_000)

    # ------------------------------------------------------------------
    # Arranque y cierre
    # ------------------------------------------------------------------
    def iniciar(self) -> None:
        """Muestra las ventanas y deja la aplicación a la espera de eventos."""

        self.bandeja.mostrar()
        if self.mostrar_ventana:
            self.ventana.mostrar_y_enfocar()
        if self.mostrar_gadget:
            self.gadget.setVisible(True)
            self.bandeja.actualizar_gadget(True)
        else:
            self.gadget.setVisible(False)
            self.bandeja.actualizar_gadget(False)

        if self.contexto.configuracion.obtener("inicio_automatico", "0") == "1":
            try:
                self.api.inicio_automatico.activar()
            except OSError as error:  # pragma: no cover - depende del sistema
                REGISTRO.warning("No se pudo registrar el inicio automático: %s", error)

        REGISTRO.info("%s iniciada (tema %s)", NOMBRE_APLICACION, self.tema)

    def ejecutar(self) -> int:
        """Arranca la interfaz y entra en el bucle de eventos de Qt.

        Returns:
            Código de salida del proceso.
        """

        self.iniciar()
        # Ctrl+C en la terminal debe cerrar la aplicación con limpieza.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        return self.aplicacion.exec()

    @Slot()
    def alternar_gadget(self) -> None:
        """Muestra u oculta el gadget y sincroniza el menú de la bandeja."""

        visible = self.gadget.alternar_visibilidad()
        self.bandeja.actualizar_gadget(visible)

    @Slot()
    def _nueva_tarea(self) -> None:
        """Abre la ventana principal en el modal de nueva tarea."""

        self.ventana.abrir_modal("tarea")

    @Slot()
    def sincronizar_calendarios(self) -> None:
        """Sincroniza todos los feeds iCalendar activos."""

        resultados = self.api.sincronizador.sincronizar_todas()
        if resultados:
            total = sum(int(item.get("importados", 0)) for item in resultados)
            self.ventana.notificar_toast(
                "Calendarios sincronizados",
                f"{total} evento(s) nuevos desde {len(resultados)} suscripción(es).",
                "exito",
            )
        else:
            self.ventana.notificar_toast(
                "Sin suscripciones",
                "Añade un feed .ics en Ajustes para sincronizar tu calendario.",
                "info",
            )
        self.api.datosActualizados.emit("evento")

    @Slot()
    def cerrar(self) -> None:
        """Cierra ordenadamente ventanas, base de datos y proceso."""

        if self._cerrando:
            return
        self._cerrando = True
        self._temporizador_avisos.stop()
        self._temporizador_sincronizacion.stop()
        self._temporizador_pomodoro.stop()
        try:
            self.gadget.hide()
            self.ventana.cerrar_definitivamente()
        finally:
            self.bandeja.hide()
            self.contexto.cerrar()
        self.aplicacion.quit()

    # ------------------------------------------------------------------
    # Ciclos periódicos
    # ------------------------------------------------------------------
    @Slot()
    def _ciclo_avisos(self) -> None:
        """Revisa recordatorios vencidos y actualiza la campana."""

        enviadas = self.api.planificador.revisar()
        for aviso in enviadas:
            self.api.notificacionRecibida.emit(
                json.dumps(aviso, ensure_ascii=False, default=str)
            )
        if enviadas:
            self.api.datosActualizados.emit("panel")
        self._actualizar_bandeja()

    @Slot()
    def _ciclo_sincronizacion(self) -> None:
        """Sincroniza feeds en segundo plano sin interrumpir al usuario."""

        try:
            resultados = self.api.sincronizador.sincronizar_todas()
        except Exception as error:  # noqa: BLE001 - nunca debe tumbar la app
            REGISTRO.warning("Sincronización automática fallida: %s", error)
            return
        if resultados:
            REGISTRO.info("Sincronización automática: %s feed(s)", len(resultados))
            self.api.datosActualizados.emit("evento")

    @Slot()
    def _ciclo_pomodoro(self) -> None:
        """Avanza el Pomodoro solo cuando hay una sesión activa."""

        estado = self.api.gestor_pomodoro.estado_actual
        if not estado.activo or estado.pausado:
            return
        self.api.tick_pomodoro(1)

    # ------------------------------------------------------------------
    # Reacciones a cambios
    # ------------------------------------------------------------------
    @Slot()
    def _avisar_ocultacion(self) -> None:
        """Informa al usuario de que la agenda sigue activa en la bandeja."""

        self.bandeja.showMessage(
            "La agenda sigue contigo",
            "Se minimizó en la bandeja. El gadget y los avisos continúan activos.",
            cargar_icono(64),
            4_000,
        )

    @Slot(str)
    def _al_recibir_aviso(self, carga_json: str) -> None:
        """Refleja un aviso nuevo en el globo de la bandeja.

        Args:
            carga_json: Notificación serializada.
        """

        try:
            aviso = json.loads(carga_json)
        except (TypeError, ValueError):
            return
        self.bandeja.showMessage(
            str(aviso.get("titulo", "Agenda Académica")),
            str(aviso.get("mensaje", "")),
            cargar_icono(64),
            6_000,
        )

    @Slot(str)
    def _al_actualizar_datos(self, categoria: str) -> None:
        """Actualiza contadores y reprograma tareas periódicas.

        Args:
            categoria: Área que cambió (``panel``, ``configuracion``...).
        """

        self._actualizar_bandeja()
        if categoria in ("configuracion", "todo"):
            self._reprogramar_sincronizacion()

    @Slot(str)
    def _al_cambiar_tema(self, tema: str) -> None:
        """Conserva el tema activo para futuras ventanas.

        Args:
            tema: Identificador del tema.
        """

        self.tema = tema

    @Slot(str)
    def _al_configurar_gadget(self, estado_json: str) -> None:
        """Sincroniza el texto del menú con la visibilidad real del gadget.

        Args:
            estado_json: Estado serializado del gadget.
        """

        try:
            estado = json.loads(estado_json)
        except (TypeError, ValueError):
            return
        if "visible" in estado:
            self.bandeja.actualizar_gadget(bool(estado["visible"]))

    def _actualizar_bandeja(self) -> None:
        """Refresca el número de avisos sin leer en el tooltip."""

        try:
            total = self.contexto.notificaciones.contar_no_vistas()
        except Exception:  # noqa: BLE001 - cosmético, nunca crítico
            total = 0
        self.bandeja.actualizar_alertas(total)


def iniciar_aplicacion(argumentos: Sequence[str] | None = None) -> int:
    """Punto de entrada de alto nivel usado por ``main.py``.

    Args:
        argumentos: Argumentos de línea de comandos sin el ejecutable.

    Returns:
        Código de salida del proceso.
    """

    analizador = argparse.ArgumentParser(
        prog="agenda-academica",
        description="Agenda Académica Inteligente: tu plan de estudios en el escritorio.",
    )
    analizador.add_argument(
        "--minimizado",
        action="store_true",
        help="Arranca directamente en la bandeja del sistema.",
    )
    analizador.add_argument(
        "--sin-gadget",
        action="store_true",
        help="No muestra el gadget flotante al arrancar.",
    )
    opciones, restantes = analizador.parse_known_args(list(argumentos or []))

    registro = logging.getLogger()
    if not registro.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
        )

    aplicacion = configurar_aplicacion([sys.argv[0], *restantes])
    orquestador = AplicacionAgenda(
        aplicacion,
        mostrar_ventana=not opciones.minimizado,
        mostrar_gadget=not opciones.sin_gadget,
    )
    return orquestador.ejecutar()
