"""Gestor de sesiones Pomodoro.

Mantiene el estado del temporizador (fase de trabajo o descanso, tiempo restante
y ciclos completados) y persiste cada bloque de trabajo finalizado en SQLite.
El servicio no depende de Qt: la interfaz lo consulta y avanza con ``tick()``,
lo que permite probar la lógica con un reloj simulado.

Example:
    >>> gestor = GestorPomodoro(contexto)
    >>> gestor.iniciar(modo="25/5")
    >>> gestor.tick(1500)
    >>> gestor.estado()["fase"]
    'descanso'
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from src.base_datos.contexto import ContextoDatos
from src.utilidades import a_iso, ahora


@dataclass
class EstadoPomodoro:
    """Estado completo del temporizador en un instante.

    Attributes:
        activo: Si hay una sesión en curso.
        pausado: Si el temporizador está detenido temporalmente.
        fase: ``trabajo`` o ``descanso``.
        modo: Etiqueta del modo elegido.
        restante_segundos: Tiempo que queda en la fase actual.
        total_segundos: Duración total de la fase actual.
        ciclos_completados: Bloques de trabajo terminados en esta sesión.
        asignatura_id: Asignatura asociada.
        evento_id: Tarea o evento asociado.
    """

    activo: bool = False
    pausado: bool = False
    fase: str = "trabajo"
    modo: str = "25/5"
    restante_segundos: int = 0
    total_segundos: int = 0
    ciclos_completados: int = 0
    asignatura_id: int | None = None
    evento_id: int | None = None
    notas: str = ""
    iniciado_en: str = ""
    progreso: float = 0.0

    def a_diccionario(self) -> dict[str, Any]:
        """Serializa el estado para el puente web.

        Returns:
            Diccionario con todos los campos y los minutos restantes.
        """

        datos = {
            "activo": self.activo,
            "pausado": self.pausado,
            "fase": self.fase,
            "modo": self.modo,
            "restante_segundos": self.restante_segundos,
            "total_segundos": self.total_segundos,
            "restante_minutos": round(self.restante_segundos / 60, 2),
            "ciclos_completados": self.ciclos_completados,
            "asignatura_id": self.asignatura_id,
            "evento_id": self.evento_id,
            "notas": self.notas,
            "iniciado_en": self.iniciado_en,
            "progreso": round(self.progreso, 4),
        }
        return datos


class GestorPomodoro:
    """Temporizador Pomodoro con persistencia de sesiones.

    Args:
        contexto: Contexto de datos para guardar las sesiones.
        reloj: Función de reloj inyectable para las pruebas.

    Attributes:
        estado_actual: Estado mutable del temporizador.
    """

    MODOS_VALIDOS = ("25/5", "50/10", "personalizado")

    def __init__(
        self, contexto: ContextoDatos, reloj: Callable[[], datetime] = ahora
    ) -> None:
        self.contexto = contexto
        self.reloj = reloj
        self.estado_actual = EstadoPomodoro()
        self._inicio_real: datetime | None = None
        self._segundos_trabajo_objetivo = 0

    # ------------------------------------------------------------------
    # Control de la sesión
    # ------------------------------------------------------------------
    def iniciar(
        self,
        asignatura_id: int | None = None,
        evento_id: int | None = None,
        modo: str = "25/5",
        duracion_trabajo: int | None = None,
        duracion_descanso: int | None = None,
        notas: str = "",
    ) -> dict[str, Any]:
        """Arranca una sesión de estudio nueva.

        Args:
            asignatura_id: Asignatura que se va a estudiar.
            evento_id: Tarea o evento relacionado.
            modo: ``25/5``, ``50/10`` o ``personalizado``.
            duracion_trabajo: Minutos de trabajo; si se omite, se derivan del modo.
            duracion_descanso: Minutos de descanso; si se omite, se derivan del modo.
            notas: Comentario inicial de la sesión.

        Returns:
            Estado serializado tras el arranque.

        Raises:
            ValueError: Si la duración no es positiva o el modo no es válido.
        """

        modo_limpio = modo if modo in self.MODOS_VALIDOS else "25/5"
        trabajo_por_defecto, descanso_por_defecto = {
            "25/5": (25, 5),
            "50/10": (50, 10),
            "personalizado": (25, 5),
        }[modo_limpio]
        minutos_trabajo = int(duracion_trabajo or trabajo_por_defecto)
        minutos_descanso = int(duracion_descanso or descanso_por_defecto)
        if minutos_trabajo <= 0 or minutos_descanso <= 0:
            raise ValueError("Las duraciones deben ser mayores que cero")

        self._segundos_trabajo_objetivo = minutos_trabajo * 60
        self._inicio_real = self.reloj()
        self.estado_actual = EstadoPomodoro(
            activo=True,
            pausado=False,
            fase="trabajo",
            modo=modo_limpio,
            restante_segundos=minutos_trabajo * 60,
            total_segundos=minutos_trabajo * 60,
            asignatura_id=asignatura_id,
            evento_id=evento_id,
            notas=notas,
            iniciado_en=a_iso(self._inicio_real),
        )
        self._actualizar_progreso()
        return self.estado_actual.a_diccionario()

    def pausar(self) -> dict[str, Any]:
        """Pausa el temporizador sin perder el tiempo restante.

        Returns:
            Estado serializado.
        """

        if self.estado_actual.activo:
            self.estado_actual.pausado = True
        return self.estado_actual.a_diccionario()

    def reanudar(self) -> dict[str, Any]:
        """Reanuda una sesión pausada.

        Returns:
            Estado serializado.
        """

        if self.estado_actual.activo:
            self.estado_actual.pausado = False
        return self.estado_actual.a_diccionario()

    def alternar_pausa(self) -> dict[str, Any]:
        """Conmuta entre pausa y marcha con un único botón visual.

        Returns:
            Estado serializado.
        """

        return self.pausar() if not self.estado_actual.pausado else self.reanudar()

    def cancelar(self) -> dict[str, Any]:
        """Cancela la sesión sin guardar el bloque actual.

        Returns:
            Estado reiniciado.
        """

        self.estado_actual = EstadoPomodoro()
        self._inicio_real = None
        return self.estado_actual.a_diccionario()

    def finalizar(self) -> dict[str, Any]:
        """Termina la sesión guardando el tiempo de trabajo efectivo.

        Si el estudiante abandona durante la fase de trabajo, se registra una
        sesión parcial marcada como no completada (si estudió al menos un minuto).

        Returns:
            Diccionario con la sesión guardada (o ``None``) y el estado final.
        """

        sesion: dict[str, Any] | None = None
        if self.estado_actual.activo and self.estado_actual.fase == "trabajo":
            transcurrido = max(0, self.estado_actual.total_segundos - self.estado_actual.restante_segundos)
            minutos = int(transcurrido // 60)
            if minutos > 0:
                sesion = self._guardar_sesion(minutos, completada=False)
        self.estado_actual = EstadoPomodoro()
        self._inicio_real = None
        return {"sesion": sesion, "estado": self.estado_actual.a_diccionario()}

    # ------------------------------------------------------------------
    # Avance del reloj
    # ------------------------------------------------------------------
    def tick(self, segundos: int = 1) -> dict[str, Any]:
        """Avanza el temporizador y gestiona la transición de fase.

        Args:
            segundos: Segundos transcurridos desde la última llamada.

        Returns:
            Estado serializado. Las claves adicionales ``sesion_guardada`` y
            ``cambio_fase`` indican si ocurrió una transición relevante.
        """

        if not self.estado_actual.activo or self.estado_actual.pausado:
            return self.estado_actual.a_diccionario()

        self.estado_actual.restante_segundos -= max(0, int(segundos))
        if self.estado_actual.restante_segundos > 0:
            self._actualizar_progreso()
            return self.estado_actual.a_diccionario()

        sesion_guardada: dict[str, Any] | None = None
        if self.estado_actual.fase == "trabajo":
            sesion_guardada = self._guardar_sesion(
                int(self.estado_actual.total_segundos // 60), completada=True
            )
            self.estado_actual.ciclos_completados += 1
            self.estado_actual.fase = "descanso"
            descanso = max(1, int(self.estado_actual.total_segundos // 60 // 5)) * 60
            self.estado_actual.restante_segundos = descanso
            self.estado_actual.total_segundos = descanso
        else:
            self.estado_actual.fase = "trabajo"
            self.estado_actual.restante_segundos = self._segundos_trabajo_objetivo
            self.estado_actual.total_segundos = self._segundos_trabajo_objetivo
            self._inicio_real = self.reloj()

        self._actualizar_progreso()
        resultado = self.estado_actual.a_diccionario()
        resultado["sesion_guardada"] = sesion_guardada
        resultado["cambio_fase"] = True
        return resultado

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------
    def _guardar_sesion(self, minutos: int, completada: bool) -> dict[str, Any]:
        """Persiste un bloque de trabajo en la base de datos.

        Args:
            minutos: Duración efectiva.
            completada: Si el bloque terminó de forma natural.

        Returns:
            Sesión registrada.
        """

        inicio = self._inicio_real or self.reloj()
        fin = self.reloj()
        return self.contexto.sesiones.registrar(
            inicio=a_iso(inicio),
            fin=a_iso(fin),
            duracion_minutos=max(1, int(minutos)),
            asignatura_id=self.estado_actual.asignatura_id,
            evento_id=self.estado_actual.evento_id,
            modo=self.estado_actual.modo,
            completada=completada,
            notas=self.estado_actual.notas,
        )

    def _actualizar_progreso(self) -> None:
        """Recalcula el porcentaje completado de la fase actual."""

        total = max(1, self.estado_actual.total_segundos)
        completado = total - max(0, self.estado_actual.restante_segundos)
        self.estado_actual.progreso = min(1.0, max(0.0, completado / total))

    def estado(self) -> dict[str, Any]:
        """Devuelve el estado actual sin avanzar el reloj.

        Returns:
            Estado serializado.
        """

        self._actualizar_progreso()
        return self.estado_actual.a_diccionario()
