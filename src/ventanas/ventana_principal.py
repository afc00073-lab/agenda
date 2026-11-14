"""Ventana principal de la agenda (contenedor de la interfaz web).

Carga ``index.html`` dentro de un ``QWebEngineView`` y expone métodos de alto
nivel para navegar entre vistas, abrir modales o lanzar avisos internos desde la
bandeja del sistema. Al cerrarse, la ventana no termina el proceso: se oculta y
la aplicación continúa en la bandeja con el gadget activo.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from src.configuracion import NOMBRE_APLICACION, RUTA_HTML_PRINCIPAL
from src.puente.api_web import ApiPuente
from src.ventanas.bandeja_sistema import cargar_icono
from src.ventanas.utilidades_web import crear_vista_web

REGISTRO = logging.getLogger(__name__)


class VentanaPrincipal(QMainWindow):
    """Ventana nativa que hospeda la aplicación principal de seis vistas.

    Args:
        api: Puente compartido con el gadget.
        tema_inicial: Tema CSS que se aplica en cuanto carga la página.

    Signals:
        ocultadaEnBandeja: La ventana se cerró pero la app sigue activa.
    """

    ocultadaEnBandeja = Signal()

    def __init__(self, api: ApiPuente, tema_inicial: str = "cristal-medianoche") -> None:
        super().__init__()
        self.api = api
        self.tema_inicial = tema_inicial
        self._salir_de_verdad = False
        self._vista_pendiente: str | None = None
        self._modal_pendiente: str | None = None

        self.setWindowTitle(NOMBRE_APLICACION)
        self.setWindowIcon(cargar_icono(128))
        self.setMinimumSize(1060, 700)
        self.resize(1420, 900)

        self.vista: QWebEngineView = crear_vista_web(self, RUTA_HTML_PRINCIPAL, api)
        self.setCentralWidget(self.vista)
        self.vista.loadFinished.connect(self._al_cargar)

        # Señales del puente que requieren actuar sobre la ventana nativa.
        self.api.solicitudNavegacion.connect(self.navegar)
        self.api.solicitudModal.connect(self.abrir_modal)
        self.api.temaCambiado.connect(self.aplicar_tema)
        self.api.notificacionRecibida.connect(self._al_recibir_notificacion)

        self._centrar()

    def _centrar(self) -> None:
        """Coloca la ventana en el centro de la pantalla disponible."""

        pantalla = QGuiApplication.primaryScreen()
        if pantalla is None:  # pragma: no cover - entorno sin pantalla
            return
        area = pantalla.availableGeometry()
        ancho = min(1420, int(area.width() * 0.92))
        alto = min(900, int(area.height() * 0.92))
        self.resize(ancho, alto)
        self.move(
            area.left() + (area.width() - ancho) // 2,
            area.top() + (area.height() - alto) // 2,
        )

    # ------------------------------------------------------------------
    # Carga de la interfaz
    # ------------------------------------------------------------------
    def _al_cargar(self, correcto: bool) -> None:
        """Aplica el tema y las acciones pendientes al terminar la carga.

        Args:
            correcto: Resultado de la carga de la página.
        """

        if not correcto:
            REGISTRO.error("No se pudo cargar la interfaz principal")
            return
        self.aplicar_tema(self.tema_inicial)
        if self._vista_pendiente:
            self.navegar(self._vista_pendiente)
            self._vista_pendiente = None
        if self._modal_pendiente:
            self.abrir_modal(self._modal_pendiente)
            self._modal_pendiente = None

    @Slot(str)
    def aplicar_tema(self, tema: str) -> None:
        """Cambia el tema de la página sin recargarla.

        Args:
            tema: Identificador del tema.
        """

        tema_seguro = json.dumps(tema)
        self.vista.page().runJavaScript(
            f"document.documentElement.dataset.tema = {tema_seguro};"
            f"window.dispatchEvent(new CustomEvent('agenda:temaExterno', {{detail: {tema_seguro}}}));"
        )

    @Slot(str)
    def navegar(self, vista: str) -> None:
        """Navega a una de las seis vistas de la aplicación.

        Args:
            vista: ``inicio``, ``calendario``, ``kanban``, ``asignaturas``,
                ``estudio`` o ``analiticas``.
        """

        if not self.vista.page().url().isValid():
            self._vista_pendiente = vista
            return
        vista_segura = json.dumps(vista)
        self.vista.page().runJavaScript(
            f"window.AgendaApp && window.AgendaApp.navegarA({vista_segura});"
        )
        self.mostrar_y_enfocar()

    @Slot(str)
    def abrir_modal(self, tipo: str) -> None:
        """Abre un modal de creación en la interfaz.

        Args:
            tipo: ``tarea``, ``evento``, ``asignatura`` o ``evaluacion``.
        """

        tipo_seguro = json.dumps(tipo)
        self.vista.page().runJavaScript(
            f"window.AgendaApp && window.AgendaApp.abrirModal({tipo_seguro});"
        )
        self.mostrar_y_enfocar()

    def notificar_toast(self, titulo: str, mensaje: str, variante: str = "info") -> None:
        """Solicita un aviso interno animado en la interfaz web.

        Args:
            titulo: Texto principal.
            mensaje: Detalle.
            variante: ``info``, ``exito``, ``aviso`` o ``error``.
        """

        argumentos = json.dumps({"titulo": titulo, "mensaje": mensaje, "variante": variante}, ensure_ascii=False)
        self.vista.page().runJavaScript(
            f"window.AgendaApp && window.AgendaApp.toast({argumentos});"
        )

    def _al_recibir_notificacion(self, carga_json: str) -> None:
        """Refresca el contador de la campana cuando llega un aviso.

        Args:
            carga_json: Notificación serializada emitida por el puente.
        """

        try:
            aviso = json.loads(carga_json)
        except (TypeError, ValueError):
            return
        self.notificar_toast(
            str(aviso.get("titulo", "Nuevo aviso")),
            str(aviso.get("mensaje", "")),
            "info",
        )

    # ------------------------------------------------------------------
    # Visibilidad
    # ------------------------------------------------------------------
    def mostrar_y_enfocar(self) -> None:
        """Muestra, restaura y activa la ventana principal."""

        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, evento: QCloseEvent) -> None:  # noqa: N802 - API de Qt
        """Oculta la ventana en lugar de cerrar la aplicación.

        Args:
            evento: Evento de cierre de Qt.
        """

        if self._salir_de_verdad:
            evento.accept()
            return
        evento.ignore()
        self.hide()
        self.ocultadaEnBandeja.emit()

    def cerrar_definitivamente(self) -> None:
        """Permite que el cierre real termine el proceso."""

        self._salir_de_verdad = True
        self.close()
