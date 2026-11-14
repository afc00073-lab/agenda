"""Utilidades compartidas para las vistas basadas en ``QWebEngineView``.

Centraliza la configuración segura del motor web: transparencia real, permisos
mínimos, puente ``QWebChannel`` y bloqueo de navegación hacia URLs externas (que
se abren en el navegador del sistema). Evita duplicar configuración entre la
ventana principal y el gadget.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget


class PaginaSegura(QWebEnginePage):
    """Página web que solo permite recursos locales.

    Cualquier intento de navegar a ``http``, ``https`` o ``mailto`` se deriva al
    navegador del sistema; nunca se carga dentro de la aplicación. Esto protege
    al usuario frente a enlaces maliciosos incrustados en feeds iCalendar.

    Args:
        padre: Objeto Qt propietario de la página.
    """

    def acceptNavigationRequest(  # noqa: N802 - API de Qt
        self, url: QUrl, tipo: QWebEnginePage.NavigationType, es_marco_principal: bool
    ) -> bool:
        """Decide si una navegación se permite dentro del motor web.

        Args:
            url: Destino solicitado.
            tipo: Tipo de navegación (clic, formulario, redirección...).
            es_marco_principal: Si afecta al documento principal.

        Returns:
            ``True`` para recursos locales y ``False`` para el resto.
        """

        if url.isLocalFile() or url.scheme() in ("qrc", "about", "data", "blob"):
            return True
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
        return False


def crear_vista_web(
    padre: QWidget,
    ruta_html: str | Path,
    api: object,
    transparente: bool = False,
) -> QWebEngineView:
    """Crea una vista web configurada y conectada al puente Python.

    Args:
        padre: Widget contenedor.
        ruta_html: Archivo HTML local que se va a cargar.
        api: Objeto ``QObject`` expuesto a JavaScript como ``puente``.
        transparente: Si es ``True``, el fondo del documento es transparente
            (necesario para el gadget).

    Returns:
        La vista web lista para mostrarse.

    Raises:
        FileNotFoundError: Si el archivo HTML no existe.
    """

    archivo = Path(ruta_html)
    if not archivo.exists():
        raise FileNotFoundError(f"No se encontró la interfaz web: {archivo}")

    vista = QWebEngineView(padre)
    pagina = PaginaSegura(vista)
    if transparente:
        pagina.setBackgroundColor(QColor(0, 0, 0, 0))

    ajustes = pagina.settings()
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
    ajustes.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)

    canal = QWebChannel(pagina)
    canal.registerObject("puente", api)
    pagina.setWebChannel(canal)
    vista.setPage(pagina)
    vista.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    vista.setUrl(QUrl.fromLocalFile(str(archivo.resolve())))
    vista.show()
    return vista
