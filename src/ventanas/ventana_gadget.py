"""Ventana nativa del gadget «Plan de Hoy».

Es una ventana **sin bordes, translúcida y anclada al escritorio** que hospeda
``gadget.html``. El arrastre se delega en JavaScript: al pulsar la cabecera, la
página envía deltas a través de ``QWebChannel`` y esta ventana mueve su posición
nativa. El control de opacidad modifica una variable CSS para conservar el
glassmorphism y la legibilidad.

Características:
    * ``FramelessWindowHint`` y ``WA_TranslucentBackground`` para un cristal real.
    * ``Tool`` + ``WindowStaysOnBottomHint`` para no tapar el trabajo del usuario.
    * Posición y tamaño persistidos en la configuración.
    * Vista compacta y detallada con animación de altura.
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.base_datos.contexto import ContextoDatos
from src.configuracion import RUTA_HTML_GADGET
from src.puente.api_web import ApiPuente
from src.ventanas.utilidades_web import crear_vista_web

TAMANO_DETALLADO = QSize(404, 584)
TAMANO_COMPACTO = QSize(404, 318)
MARGEN_ESCRITORIO = 28


class VentanaGadget(QWidget):
    """Gadget flotante transparente con el plan del día.

    Args:
        api: Puente compartido con la ventana principal.
        contexto: Contexto de datos para leer y guardar la configuración.
        padre: Widget propietario opcional.
    """

    def __init__(
        self,
        api: ApiPuente,
        contexto: ContextoDatos,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.api = api
        self.contexto = contexto
        self._bloqueado = False
        self._compacto = False
        self._origen_arrastre = QPoint()
        self._tamano_actual = TAMANO_DETALLADO
        self._animacion: QPropertyAnimation | None = None

        self.setWindowTitle("Plan de Hoy · Agenda Académica")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(0, 0, 0, 0)
        disposicion.setSpacing(0)

        self.vista: QWebEngineView = crear_vista_web(
            self, RUTA_HTML_GADGET, api, transparente=True
        )
        disposicion.addWidget(self.vista)

        self.resize(TAMANO_DETALLADO)
        self._cargar_estado_guardado()

        # Señales del puente que afectan a la ventana nativa.
        self.api.gadgetConfigurado.connect(self.aplicar_configuracion)
        self.api.gadgetArrastrado.connect(self._procesar_arrastre)
        self.api.temaCambiado.connect(self.aplicar_tema)

    # ------------------------------------------------------------------
    # Estado persistente
    # ------------------------------------------------------------------
    def _cargar_estado_guardado(self) -> None:
        """Restaura posición, tamaño y visibilidad desde la configuración."""

        configuracion = self.contexto.configuracion
        self._compacto = configuracion.obtener("gadget_compacto", "0") == "1"
        self._bloqueado = configuracion.obtener("gadget_bloqueado", "0") == "1"
        self._tamano_actual = TAMANO_COMPACTO if self._compacto else TAMANO_DETALLADO
        self.resize(self._tamano_actual)

        x_texto = configuracion.obtener("gadget_posicion_x", "")
        y_texto = configuracion.obtener("gadget_posicion_y", "")
        if x_texto and y_texto:
            self.move(self._posicion_valida(int(float(x_texto)), int(float(y_texto))))
        else:
            self._colocar_abajo_derecha()

        visible = configuracion.obtener("gadget_visible", "1") == "1"
        self.setVisible(visible)

    def _posicion_valida(self, x: int, y: int) -> QPoint:
        """Ajusta una posición para que el gadget quede dentro de una pantalla.

        Args:
            x: Coordenada horizontal guardada.
            y: Coordenada vertical guardada.

        Returns:
            Punto corregido si la posición original quedaba fuera del escritorio.
        """

        pantalla = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        if pantalla is None:  # pragma: no cover - entorno sin pantalla
            return QPoint(x, y)
        area = pantalla.availableGeometry()
        ancho = self._tamano_actual.width()
        alto = self._tamano_actual.height()
        x_corregido = min(max(x, area.left() - ancho // 3), area.right() - ancho // 2)
        y_corregido = min(max(y, area.top()), area.bottom() - 40)
        return QPoint(x_corregido, y_corregido)

    def _colocar_abajo_derecha(self) -> None:
        """Sitúa el gadget en la esquina inferior derecha del escritorio."""

        pantalla = QGuiApplication.primaryScreen()
        if pantalla is None:  # pragma: no cover - entorno sin pantalla
            self.move(80, 80)
            return
        area = pantalla.availableGeometry()
        x = area.right() - self.width() - MARGEN_ESCRITORIO
        y = area.bottom() - self.height() - MARGEN_ESCRITORIO
        self.move(max(area.left(), x), max(area.top(), y))

    def _guardar_posicion(self) -> None:
        """Persiste la posición actual del gadget."""

        self.contexto.configuracion.guardar_varias(
            {"gadget_posicion_x": str(self.x()), "gadget_posicion_y": str(self.y())}
        )

    # ------------------------------------------------------------------
    # Configuración en vivo
    # ------------------------------------------------------------------
    @Slot(str)
    def aplicar_configuracion(self, estado_json: str) -> None:
        """Aplica opacidad, bloqueo, tamaño y visibilidad recibidos del puente.

        Args:
            estado_json: Estado serializado del gadget.
        """

        try:
            estado = json.loads(estado_json)
        except (TypeError, ValueError):
            return
        self._aplicar_estado(estado)

    def _aplicar_estado(self, estado: dict[str, Any]) -> None:
        """Sincroniza el estado visual y la geometría de la ventana.

        Args:
            estado: Diccionario con claves ``opacidad``, ``bloqueado``,
                ``compacto`` y ``visible``.
        """

        if "bloqueado" in estado:
            self._bloqueado = bool(estado["bloqueado"])
        if "compacto" in estado:
            self._cambiar_compacto(bool(estado["compacto"]))
        if "visible" in estado:
            self.setVisible(bool(estado["visible"]))
        if estado.get("tema"):
            self.aplicar_tema(str(estado["tema"]))

    @Slot(str)
    def aplicar_tema(self, tema: str) -> None:
        """Cambia el tema del documento web sin recargar la página.

        Args:
            tema: Identificador del tema.
        """

        tema_seguro = json.dumps(tema)
        self.vista.page().runJavaScript(
            f"document.documentElement.dataset.tema = {tema_seguro};"
        )

    def _cambiar_compacto(self, compacto: bool) -> None:
        """Activa o desactiva la vista compacta con animación de altura.

        Args:
            compacto: Estado deseado.
        """

        if compacto == self._compacto:
            return
        self._compacto = compacto
        destino = TAMANO_COMPACTO if compacto else TAMANO_DETALLADO
        self._tamano_actual = destino

        if self._animacion is not None:
            self._animacion.stop()
        self._animacion = QPropertyAnimation(self, b"size", self)
        self._animacion.setDuration(460)
        self._animacion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animacion.setStartValue(self.size())
        self._animacion.setEndValue(destino)
        self._animacion.start()

        # Si está anclado abajo, la ventana crece hacia arriba sin salirse.
        pantalla = QGuiApplication.primaryScreen()
        if pantalla is not None:
            area = pantalla.availableGeometry()
            if self.y() + destino.height() > area.bottom():
                self.move(self.x(), max(area.top(), area.bottom() - destino.height()))

    # ------------------------------------------------------------------
    # Arrastre nativo
    # ------------------------------------------------------------------
    @Slot(str)
    def _procesar_arrastre(self, orden_json: str) -> None:
        """Mueve la ventana siguiendo las órdenes de la cabecera HTML.

        Args:
            orden_json: JSON con ``accion`` (``iniciar``/``mover``/``soltar``)
                y los desplazamientos ``dx``/``dy``.
        """

        try:
            orden = json.loads(orden_json)
        except (TypeError, ValueError):
            return
        accion = orden.get("accion")
        if accion == "iniciar":
            if self._bloqueado:
                return
            self._origen_arrastre = self.pos()
        elif accion == "mover" and not self._bloqueado:
            self.move(
                self._origen_arrastre.x() + int(orden.get("dx", 0)),
                self._origen_arrastre.y() + int(orden.get("dy", 0)),
            )
        elif accion == "soltar":
            if not self._bloqueado:
                self._guardar_posicion()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def alternar_visibilidad(self) -> bool:
        """Muestra u oculta el gadget y persiste el estado.

        Returns:
            La nueva visibilidad.
        """

        visible = not self.isVisible()
        self.setVisible(visible)
        self.contexto.configuracion.guardar("gadget_visible", "1" if visible else "0")
        self.api.gadgetConfigurado.emit(
            json.dumps(
                {
                    "visible": visible,
                    "compacto": self._compacto,
                    "bloqueado": self._bloqueado,
                }
            )
        )
        return visible

    def mostrar_y_enfocar(self) -> None:
        """Muestra el gadget sin robar el foco de la aplicación activa."""

        self.setVisible(True)
        self.contexto.configuracion.guardar("gadget_visible", "1")
