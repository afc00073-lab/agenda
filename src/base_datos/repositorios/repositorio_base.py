"""Base común de los repositorios.

Concentra utilidades compartidas: acceso al gestor de base de datos, creación de
marcas de tiempo y conversión segura de valores JSON almacenados en columnas de
texto. Los repositorios concretos heredan de esta clase para no duplicar código.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from src.base_datos.conexion import GestorBaseDatos
from src.utilidades import a_iso, ahora


class RepositorioBase:
    """Clase base de los repositorios de la aplicación.

    Args:
        gestor: Gestor de conexiones SQLite ya inicializado y migrado.
    """

    def __init__(self, gestor: GestorBaseDatos) -> None:
        self.gestor = gestor

    @staticmethod
    def marca_tiempo() -> str:
        """Devuelve la marca temporal ISO que se guarda en las columnas de auditoría.

        Returns:
            Cadena ``AAAA-MM-DDTHH:MM`` con la hora local actual.
        """

        return a_iso(ahora())

    @staticmethod
    def leer_json(texto: Any, valor_predeterminado: Any) -> Any:
        """Deserializa una columna JSON sin propagar errores de formato.

        Args:
            texto: Contenido de la columna (puede ser ``None``).
            valor_predeterminado: Valor devuelto si el JSON es inválido.

        Returns:
            El objeto Python equivalente al JSON almacenado.
        """

        if not texto:
            return valor_predeterminado
        if isinstance(texto, (list, dict)):
            return texto
        try:
            return json.loads(texto)
        except (TypeError, ValueError):
            return valor_predeterminado

    @staticmethod
    def escribir_json(valor: Any) -> str:
        """Serializa un objeto Python a JSON compacto y seguro para SQLite.

        Args:
            valor: Objeto serializable.

        Returns:
            Cadena JSON con caracteres no ASCII preservados.
        """

        return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def lista_minutos_a_texto(valores: Iterable[int]) -> str:
        """Convierte una colección de antelaciones a la cadena almacenada.

        Args:
            valores: Minutos de antelación, por ejemplo ``[1440, 120, 15]``.

        Returns:
            Cadena ordenada y sin duplicados, por ejemplo ``"15,120,1440"``.
        """

        limpios = sorted({int(valor) for valor in valores if int(valor) >= 0})
        return ",".join(str(valor) for valor in limpios)

    @staticmethod
    def texto_a_lista_minutos(texto: Any) -> list[int]:
        """Interpreta la columna de recordatorios como lista de enteros.

        Args:
            texto: Cadena ``"1440,120,15"`` o secuencia ya convertida.

        Returns:
            Lista de minutos ordenada; vacía si el contenido no es válido.
        """

        if isinstance(texto, (list, tuple)):
            return sorted({int(valor) for valor in texto if int(valor) >= 0})
        if not texto:
            return []
        try:
            return sorted({int(parte) for parte in str(texto).split(",") if parte.strip()})
        except ValueError:
            return []
