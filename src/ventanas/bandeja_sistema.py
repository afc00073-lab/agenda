"""Icono y menú contextual de la bandeja del sistema.

La agenda sigue viva cuando se cierra la ventana principal. Este módulo crea el
``QSystemTrayIcon``, su menú en español y las señales que el orquestador conecta
con las ventanas. Usa el icono SVG de la aplicación y, si el plugin de SVG no
estuviera disponible, dibuja un icono de respaldo con ``QPainter``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from src.configuracion import NOMBRE_APLICACION, RUTA_ICONO_APLICACION

REGISTRO = logging.getLogger(__name__)


def cargar_icono(tamano: int = 64) -> QIcon:
    """Carga el icono SVG de la aplicación con respaldo dibujado.

    Args:
        tamano: Lado del icono de respaldo en píxeles.

    Returns:
        Un ``QIcon`` válido incluso si el SVG no puede cargarse.
    """

    icono = QIcon(str(RUTA_ICONO_APLICACION))
    if not icono.isNull():
        return icono

    pixmap = QPixmap(tamano, tamano)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    degradado = QLinearGradient(0, 0, tamano, tamano)
    degradado.setColorAt(0.0, QColor("#7c6cff"))
    degradado.setColorAt(0.55, QColor("#4aa8ff"))
    degradado.setColorAt(1.0, QColor("#34e2c4"))
    pintor.setBrush(degradado)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.drawRoundedRect(2, 2, tamano - 4, tamano - 4, 16, 16)
    pintor.setPen(QPen(QColor("#ffffff"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    pintor.drawRect(17, 18, tamano - 34, tamano - 36)
    pintor.drawLine(17, 30, tamano - 17, 30)
    pintor.drawLine(27, 12, 27, 23)
    pintor.drawLine(tamano - 27, 12, tamano - 27, 23)
    pintor.drawLine(27, 42, 34, 49)
    pintor.drawLine(34, 49, 46, 36)
    pintor.end()
    return QIcon(pixmap)


class BandejaSistema(QSystemTrayIcon):
    """Icono de la bandeja con menú contextual de acciones rápidas.

    Args:
        padre: Objeto Qt propietario.

    Signals:
        abrirSolicitado: El usuario quiere abrir la agenda.
        gadgetSolicitado: Mostrar u ocultar el gadget.
        nuevaTareaSolicitada: Abrir el modal de nueva tarea.
        sincronizarSolicitado: Lanzar la sincronización de feeds ICS.
        salirSolicitado: Cerrar la aplicación por completo.
    """

    abrirSolicitado = Signal()
    gadgetSolicitado = Signal()
    nuevaTareaSolicitada = Signal()
    sincronizarSolicitado = Signal()
    salirSolicitado = Signal()

    def __init__(self, padre: QWidget | None = None) -> None:
        super().__init__(cargar_icono(), padre)
        self.setToolTip(f"{NOMBRE_APLICACION} · tu plan académico")
        self._gadget_visible = True
        self._menu = QMenu()
        self._acciones: dict[str, QAction] = {}
        self._construir_menu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._al_activar)

    # ------------------------------------------------------------------
    # Construcción del menú
    # ------------------------------------------------------------------
    def _construir_menu(self) -> None:
        """Crea las acciones del menú contextual con iconos coherentes."""

        accion_abrir = QAction("Abrir Agenda", self._menu)
        accion_abrir.triggered.connect(self.abrirSolicitado.emit)
        self._menu.addAction(accion_abrir)
        self._acciones["abrir"] = accion_abrir

        self._accion_gadget = QAction("Ocultar Gadget", self._menu)
        self._accion_gadget.triggered.connect(self.gadgetSolicitado.emit)
        self._menu.addAction(self._accion_gadget)
        self._acciones["gadget"] = self._accion_gadget

        self._menu.addSeparator()

        accion_tarea = QAction("Nueva Tarea…", self._menu)
        accion_tarea.triggered.connect(self.nuevaTareaSolicitada.emit)
        self._menu.addAction(accion_tarea)
        self._acciones["tarea"] = accion_tarea

        accion_sincronizar = QAction("Sincronizar calendarios .ics", self._menu)
        accion_sincronizar.triggered.connect(self.sincronizarSolicitado.emit)
        self._menu.addAction(accion_sincronizar)
        self._acciones["sincronizar"] = accion_sincronizar

        self._menu.addSeparator()

        accion_salir = QAction("Salir", self._menu)
        accion_salir.triggered.connect(self.salirSolicitado.emit)
        self._menu.addAction(accion_salir)
        self._acciones["salir"] = accion_salir

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def _al_activar(self, motivo: QSystemTrayIcon.ActivationReason) -> None:
        """Abre la agenda al hacer clic o doble clic en el icono.

        Args:
            motivo: Tipo de activación recibido de Qt.
        """

        if motivo in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.abrirSolicitado.emit()

    def actualizar_gadget(self, visible: bool) -> None:
        """Actualiza el texto de la acción del gadget.

        Args:
            visible: Si el gadget está actualmente visible.
        """

        self._gadget_visible = visible
        self._accion_gadget.setText("Ocultar Gadget" if visible else "Mostrar Gadget")

    def actualizar_alertas(self, total: int) -> None:
        """Refleja el número de avisos sin leer en el tooltip.

        Args:
            total: Número de notificaciones no vistas.
        """

        sufijo = f" · {total} aviso(s) sin leer" if total else ""
        self.setToolTip(f"{NOMBRE_APLICACION} · tu plan académico{sufijo}")

    def mostrar(self) -> None:
        """Muestra el icono si el entorno dispone de bandeja del sistema."""

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.show()
        else:  # pragma: no cover - entornos sin bandeja
            REGISTRO.info("La bandeja del sistema no está disponible en este entorno")

    def notificar(self, titulo: str, mensaje: str) -> None:
        """Muestra una notificación de respaldo desde la propia bandeja.

        Se usa cuando el backend nativo de notificaciones no está disponible.

        Args:
            titulo: Texto principal.
            mensaje: Cuerpo del aviso.
        """

        if self.isVisible():
            self.showMessage(titulo, mensaje, cargar_icono(64), 5000)
