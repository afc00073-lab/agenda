"""Inicio automático de la agenda con el sistema operativo.

Implementa el mecanismo nativo de cada plataforma sin dependencias externas:

* **Linux**: archivo ``.desktop`` en ``~/.config/autostart``.
* **Windows**: valor en ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``.
* **macOS**: ``LaunchAgent`` en ``~/Library/LaunchAgents``.

El directorio base y el nombre del sistema son inyectables para poder probar la
generación del archivo sin tocar la configuración real del usuario.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import sys
from pathlib import Path
from typing import Any

from src.configuracion import DIRECTORIO_RAIZ, IDENTIFICADOR_APLICACION, NOMBRE_APLICACION, RUTA_ICONO_APLICACION

REGISTRO = logging.getLogger(__name__)

NOMBRE_ARCHIVO_LINUX = f"{IDENTIFICADOR_APLICACION}.desktop"
NOMBRE_ARCHIVO_MACOS = f"{IDENTIFICADOR_APLICACION}.plist"


class GestorInicioAutomatico:
    """Activa, desactiva y consulta el arranque automático de la aplicación.

    Args:
        sistema: Sistema operativo simulado o real (``Linux``, ``Windows``,
            ``Darwin``).
        directorio_inicio: Carpeta donde se escribe el archivo de arranque en
            Linux/macOS. Por defecto, ``~/.config/autostart`` o
            ``~/Library/LaunchAgents``.
        ejecutable: Intérprete de Python que ejecutará ``main.py``.
        punto_entrada: Ruta de ``main.py``.

    Attributes:
        sistema: Sistema operativo normalizado.
    """

    def __init__(
        self,
        sistema: str | None = None,
        directorio_inicio: str | Path | None = None,
        ejecutable: str | None = None,
        punto_entrada: str | Path | None = None,
    ) -> None:
        self.sistema = (sistema or platform.system()).strip().lower()
        self.ejecutable = ejecutable or sys.executable
        self.punto_entrada = Path(punto_entrada or (DIRECTORIO_RAIZ / "main.py")).resolve()
        if directorio_inicio is not None:
            self.directorio_inicio = Path(directorio_inicio).expanduser()
        elif self.sistema == "darwin":
            self.directorio_inicio = Path.home() / "Library" / "LaunchAgents"
        else:
            self.directorio_inicio = Path.home() / ".config" / "autostart"

    # ------------------------------------------------------------------
    # Rutas
    # ------------------------------------------------------------------
    @property
    def ruta_archivo(self) -> Path:
        """Ruta del archivo de arranque según la plataforma.

        Returns:
            Ruta del ``.desktop``, ``.plist`` o cadena vacía en Windows.
        """

        if self.sistema == "windows":
            return Path("HKEY_CURRENT_USER")
        if self.sistema == "darwin":
            return self.directorio_inicio / NOMBRE_ARCHIVO_MACOS
        return self.directorio_inicio / NOMBRE_ARCHIVO_LINUX

    def comando(self) -> str:
        """Construye el comando de arranque citando las rutas con espacios.

        Returns:
            Línea de comandos lista para ``Exec=`` o ``ProgramArguments``.
        """

        return f"{shlex.quote(str(self.ejecutable))} {shlex.quote(str(self.punto_entrada))}"

    # ------------------------------------------------------------------
    # Linux
    # ------------------------------------------------------------------
    def contenido_desktop(self) -> str:
        """Genera el contenido del archivo ``.desktop`` de autostart.

        Returns:
            Texto completo con la sección ``[Desktop Entry]``.
        """

        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={NOMBRE_APLICACION}\n"
            f"Comment=Agenda académica con gadget de escritorio y notificaciones\n"
            f"Exec={self.comando()}\n"
            f"Path={DIRECTORIO_RAIZ}\n"
            f"Icon={RUTA_ICONO_APLICACION}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
            "StartupNotify=false\n"
        )

    def _activar_linux(self) -> None:
        """Escribe y hace ejecutable el archivo ``.desktop``."""

        self.directorio_inicio.mkdir(parents=True, exist_ok=True)
        archivo = self.ruta_archivo
        archivo.write_text(self.contenido_desktop(), encoding="utf-8")
        archivo.chmod(0o755)

    def _desactivar_linux(self) -> None:
        """Elimina el archivo ``.desktop`` si existe."""

        self.ruta_archivo.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # macOS
    # ------------------------------------------------------------------
    def contenido_plist(self) -> str:
        """Genera el ``LaunchAgent`` de macOS.

        Returns:
            Documento XML con ``RunAtLoad`` y la ruta del punto de entrada.
        """

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{IDENTIFICADOR_APLICACION}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{self.ejecutable}</string>
        <string>{self.punto_entrada}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{DIRECTORIO_RAIZ}</string>
    <key>StandardOutPath</key>
    <string>{Path.home() / "Library" / "Logs" / "agenda-academica.log"}</string>
    <key>StandardErrorPath</key>
    <string>{Path.home() / "Library" / "Logs" / "agenda-academica-error.log"}</string>
</dict>
</plist>
"""

    def _activar_macos(self) -> None:
        """Escribe el ``LaunchAgent`` en la carpeta del usuario."""

        self.directorio_inicio.mkdir(parents=True, exist_ok=True)
        self.ruta_archivo.write_text(self.contenido_plist(), encoding="utf-8")

    def _desactivar_macos(self) -> None:
        """Elimina el ``LaunchAgent``."""

        self.ruta_archivo.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------
    def _clave_windows(self) -> str:
        """Devuelve la ruta del registro usada para el arranque.

        Returns:
            Clave ``Run`` del usuario actual.
        """

        return r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _activar_windows(self) -> None:
        """Registra la aplicación en el arranque del usuario de Windows."""

        import winreg  # noqa: PLC0415 - solo disponible en Windows

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, self._clave_windows(), 0, winreg.KEY_SET_VALUE
        ) as clave:
            winreg.SetValueEx(clave, IDENTIFICADOR_APLICACION, 0, winreg.REG_SZ, self.comando())

    def _desactivar_windows(self) -> None:
        """Elimina la entrada del registro de Windows si existe."""

        import winreg  # noqa: PLC0415 - solo disponible en Windows

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._clave_windows(), 0, winreg.KEY_SET_VALUE
            ) as clave:
                winreg.DeleteValue(clave, IDENTIFICADOR_APLICACION)
        except FileNotFoundError:
            pass

    def _consultar_windows(self) -> bool:
        """Comprueba si existe el valor de arranque en el registro.

        Returns:
            ``True`` si la aplicación está registrada.
        """

        import winreg  # noqa: PLC0415 - solo disponible en Windows

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._clave_windows(), 0, winreg.KEY_READ
            ) as clave:
                valor, _ = winreg.QueryValueEx(clave, IDENTIFICADOR_APLICACION)
                return bool(valor)
        except FileNotFoundError:
            return False

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def activar(self) -> dict[str, Any]:
        """Activa el inicio automático en la plataforma actual.

        Returns:
            Diccionario con ``ok``, mensaje y ruta del mecanismo usado.
        """

        try:
            if self.sistema == "windows":
                self._activar_windows()
            elif self.sistema == "darwin":
                self._activar_macos()
            else:
                self._activar_linux()
        except (OSError, ImportError) as error:
            REGISTRO.warning("No se pudo activar el inicio automático: %s", error)
            return {"ok": False, "error": f"No se pudo activar el inicio automático: {error}"}
        return {
            "ok": True,
            "sistema": self.sistema,
            "ruta": str(self.ruta_archivo),
            "comando": self.comando(),
        }

    def desactivar(self) -> dict[str, Any]:
        """Desactiva el inicio automático.

        Returns:
            Diccionario con ``ok`` y el estado resultante.
        """

        try:
            if self.sistema == "windows":
                self._desactivar_windows()
            elif self.sistema == "darwin":
                self._desactivar_macos()
            else:
                self._desactivar_linux()
        except (OSError, ImportError) as error:
            return {"ok": False, "error": f"No se pudo desactivar: {error}"}
        return {"ok": True, "activo": False, "ruta": str(self.ruta_archivo)}

    def esta_activo(self) -> bool:
        """Consulta si el arranque automático está configurado.

        Returns:
            ``True`` si el archivo o valor del registro existe.
        """

        if self.sistema == "windows":
            try:
                return self._consultar_windows()
            except (ImportError, OSError):
                return False
        return self.ruta_archivo.exists()

    def alternar(self) -> dict[str, Any]:
        """Activa o desactiva según el estado actual.

        Returns:
            Resultado de la operación.
        """

        return self.desactivar() if self.esta_activo() else self.activar()

    def estado(self) -> dict[str, Any]:
        """Resume el estado para la vista de ajustes.

        Returns:
            Diccionario con sistema, activo, ruta y comando.
        """

        return {
            "sistema": self.sistema,
            "activo": self.esta_activo(),
            "ruta": str(self.ruta_archivo),
            "comando": self.comando(),
        }
