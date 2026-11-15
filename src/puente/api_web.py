"""API del puente entre Python y la interfaz web (``QWebChannel``).

Cada método público es una **ranura Qt** que recibe y devuelve cadenas JSON.
Este contrato evita problemas de conversión de tipos entre JavaScript y Python y
permite que la interfaz muestre errores controlados en lugar de romperse.

Señales emitidas:

* ``datosActualizados(categoria)``: la interfaz recarga la vista afectada y el
  gadget se sincroniza al instante.
* ``gadgetConfigurado(json)``: opacidad, tamaño, bloqueo o posición cambiaron.
* ``pomodoroActualizado(json)``: avance del temporizador de estudio.
* ``notificacionRecibida(json)``: aviso reciente para la campana y los *toasts*.
* ``solicitudNavegacion(vista)``: la bandeja del sistema pide abrir una vista.
* ``solicitudModal(tipo)``: la bandeja pide abrir el modal de nueva tarea.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from src.base_datos.contexto import ContextoDatos
from src.configuracion import NOMBRE_APLICACION
from src.servicios.calendario_ics import SincronizadorICS
from src.servicios.calculadora_notas import calcular_asignatura, calcular_expediente
from src.servicios.inicio_automatico import GestorInicioAutomatico
from src.servicios.notificaciones import PlanificadorNotificaciones
from src.servicios.pomodoro import GestorPomodoro
from src.servicios.respaldos import ErrorRespaldo, GestorRespaldos
from src.utilidades import a_iso, ahora, fecha_legible, rango_semana

REGISTRO = logging.getLogger(__name__)

CATEGORIAS_VALIDAS = ("panel", "evento", "kanban", "notas", "gadget", "configuracion", "todo")


class ApiPuente(QObject):
    """Ranuras y señales expuestas a JavaScript.

    Args:
        contexto: Contexto de datos de la aplicación.
        planificador: Motor de notificaciones. Si se omite se crea uno nuevo.
        sincronizador: Sincronizador de feeds iCalendar.
        gestor_pomodoro: Temporizador Pomodoro compartido.
        gestor_respaldos: Servicio de copias de seguridad.
        inicio_automatico: Gestor de arranque con el sistema.
    """

    datosActualizados = Signal(str)
    gadgetConfigurado = Signal(str)
    pomodoroActualizado = Signal(str)
    notificacionRecibida = Signal(str)
    solicitudNavegacion = Signal(str)
    solicitudModal = Signal(str)
    temaCambiado = Signal(str)
    gadgetArrastrado = Signal(str)

    def __init__(
        self,
        contexto: ContextoDatos,
        planificador: PlanificadorNotificaciones | None = None,
        sincronizador: SincronizadorICS | None = None,
        gestor_pomodoro: GestorPomodoro | None = None,
        gestor_respaldos: GestorRespaldos | None = None,
        inicio_automatico: GestorInicioAutomatico | None = None,
    ) -> None:
        super().__init__()
        self.contexto = contexto
        self.planificador = planificador or PlanificadorNotificaciones(contexto)
        self.sincronizador = sincronizador or SincronizadorICS(contexto)
        self.gestor_pomodoro = gestor_pomodoro or GestorPomodoro(contexto)
        self.gestor_respaldos = gestor_respaldos or GestorRespaldos(contexto)
        self.inicio_automatico = inicio_automatico or GestorInicioAutomatico()

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    @staticmethod
    def _respuesta(datos: Any = None, mensaje: str = "") -> str:
        """Construye una respuesta JSON de éxito.

        Args:
            datos: Carga útil serializable.
            mensaje: Texto opcional para el *toast* de la interfaz.

        Returns:
            Cadena JSON con ``ok`` y ``datos``.
        """

        return json.dumps(
            {"ok": True, "datos": datos, "mensaje": mensaje}, ensure_ascii=False, default=str
        )

    @staticmethod
    def _error(mensaje: str, codigo: str = "error") -> str:
        """Construye una respuesta JSON de error controlado.

        Args:
            mensaje: Descripción legible en español.
            codigo: Identificador corto para la interfaz.

        Returns:
            Cadena JSON con ``ok = False``.
        """

        return json.dumps({"ok": False, "error": mensaje, "codigo": codigo}, ensure_ascii=False)

    def _responder(self, operacion: Callable[[], Any], categoria: str = "") -> str:
        """Ejecuta una operación capturando cualquier error de negocio.

        Args:
            operacion: Función sin argumentos que produce el resultado.
            categoria: Si se indica, emite ``datosActualizados`` al terminar.

        Returns:
            Respuesta JSON serializada.
        """

        try:
            resultado = operacion()
        except (ValueError, ErrorRespaldo, OSError) as error:
            REGISTRO.warning("Operación rechazada: %s", error)
            return self._error(str(error))
        except Exception as error:  # noqa: BLE001 - la UI nunca debe caer
            REGISTRO.exception("Error inesperado en el puente: %s", error)
            return self._error(f"Error inesperado: {error}", "interno")
        if categoria:
            self.datosActualizados.emit(categoria)
        return self._respuesta(resultado)

    @staticmethod
    def _leer_json(texto: str | dict[str, Any] | None) -> dict[str, Any]:
        """Interpreta un objeto JSON recibido de JavaScript.

        Args:
            texto: Cadena JSON, diccionario o ``None``.

        Returns:
            Diccionario de datos; vacío si la entrada es inválida.
        """

        if isinstance(texto, dict):
            return texto
        if not texto:
            return {}
        try:
            datos = json.loads(texto)
            return datos if isinstance(datos, dict) else {}
        except (TypeError, ValueError):
            return {}

    # ------------------------------------------------------------------
    # Arranque e información general
    # ------------------------------------------------------------------
    @Slot(result=str)
    def obtener_inicializacion(self) -> str:
        """Entrega el estado inicial completo de la aplicación.

        Returns:
            JSON con configuración, asignaturas, panel, notificaciones, gadget,
            tema y rutas de las páginas (para depuración).
        """

        return self._responder(
            lambda: {
                "aplicacion": NOMBRE_APLICACION,
                "configuracion": self.contexto.configuracion.todas(),
                "asignaturas": self.contexto.asignaturas.listar(),
                "panel": self._construir_panel(),
                "notificaciones": self.contexto.notificaciones.listar(limite=20),
                "alertas": self.contexto.notificaciones.contar_no_vistas(),
                "gadget": self._estado_gadget(),
                "sistema": {
                    "notificador": getattr(self.planificador.notificador, "motor", "desconocido"),
                    "inicio_automatico": self.inicio_automatico.esta_activo(),
                },
            }
        )

    @Slot(result=str)
    def obtener_panel_inicio(self) -> str:
        """Devuelve los datos de la vista Inicio.

        Returns:
            JSON con KPIs, próximos exámenes, agenda del día y progreso.
        """

        return self._responder(self._construir_panel)

    def _construir_panel(self) -> dict[str, Any]:
        """Calcula todos los indicadores de la pantalla de inicio.

        Returns:
            Diccionario serializable con las tarjetas KPI y listas de la vista.
        """

        referencia = ahora()
        lunes, domingo = rango_semana(referencia)
        eventos_semana = self.contexto.eventos.listar(
            desde=a_iso(lunes), hasta=a_iso(domingo)
        )
        completados = [
            evento
            for evento in eventos_semana
            if evento["completado"] and evento["tipo"] in ("tarea", "entrega")
        ]
        minutos_semana = self.contexto.sesiones.total_minutos(a_iso(lunes), a_iso(domingo))
        hoy = self.contexto.eventos.listar_dia(a_iso(referencia)[:10])
        proximos = self.contexto.eventos.proximos_examenes(limite=3)
        proximo_hito = proximos[0] if proximos else None

        total_hoy = len(hoy)
        completados_hoy = len([evento for evento in hoy if evento["completado"]])
        progreso = int(round(completados_hoy * 100 / total_hoy)) if total_hoy else 0

        return {
            "saludo": self._saludo(referencia.hour),
            "nombre_estudiante": self.contexto.configuracion.obtener("nombre_estudiante", "Estudiante"),
            "fecha": fecha_legible(referencia),
            "fecha_iso": a_iso(referencia),
            "hora": referencia.strftime("%H:%M"),
            "progreso_dia": progreso,
            "kpis": {
                "tareas_completadas_semana": len(completados),
                "horas_estudio_semana": round(minutos_semana / 60, 1),
                "entregas_proximas": self.contexto.eventos.contar_entregas_proximas(
                    dias=7, desde=a_iso(referencia)
                ),
                "alertas_sin_ver": self.contexto.notificaciones.contar_no_vistas(),
                "minutos_enfoque_hoy": self.contexto.sesiones.total_minutos(
                    a_iso(referencia)[:10] + "T00:00", a_iso(referencia)[:10] + "T23:59"
                ),
            },
            "proximos_examenes": proximos,
            "proximo_hito": proximo_hito,
            "agenda_hoy": hoy,
            "tareas_hoy": [evento for evento in hoy if evento["tipo"] == "tarea" and not evento["completado"]],
            "asignaturas": self.contexto.asignaturas.listar(),
            "notificaciones": self.contexto.notificaciones.listar(limite=8),
        }

    @staticmethod
    def _saludo(hora: int) -> str:
        """Genera un saludo según la hora del día.

        Args:
            hora: Hora local en formato 24 horas.

        Returns:
            Saludo en español con emoji.
        """

        if hora < 6:
            return "🌙 Buenas noches"
        if hora < 13:
            return "☀️ Buenos días"
        if hora < 20:
            return "🌤️ Buenas tardes"
        return "🌙 Buenas noches"

    # ------------------------------------------------------------------
    # Asignaturas
    # ------------------------------------------------------------------
    @Slot(result=str)
    def listar_asignaturas(self) -> str:
        """Lista todas las asignaturas.

        Returns:
            JSON con la lista de asignaturas.
        """

        return self._responder(self.contexto.asignaturas.listar)

    @Slot(str, result=str)
    def crear_asignatura(self, datos_json: str) -> str:
        """Crea una asignatura desde el formulario de la interfaz.

        Args:
            datos_json: JSON con nombre, código, color, profesor, aula, créditos
                y enlaces.

        Returns:
            JSON con la asignatura creada.
        """

        datos = self._leer_json(datos_json)
        return self._responder(
            lambda: self.contexto.asignaturas.crear(
                nombre=str(datos.get("nombre", "")),
                codigo=str(datos.get("codigo", "")),
                color=str(datos.get("color", "#7c6cff")),
                profesor=str(datos.get("profesor", "")),
                aula=str(datos.get("aula", "")),
                creditos=float(datos.get("creditos", 6) or 6),
                enlaces=datos.get("enlaces", []),
            ),
            "notas",
        )

    @Slot(int, str, result=str)
    def actualizar_asignatura(self, asignatura_id: int, datos_json: str) -> str:
        """Actualiza una asignatura existente.

        Args:
            asignatura_id: Identificador de la asignatura.
            datos_json: Campos a modificar.

        Returns:
            JSON con la asignatura actualizada.
        """

        cambios = self._leer_json(datos_json)
        return self._responder(
            lambda: self.contexto.asignaturas.actualizar(asignatura_id, cambios),
            "notas",
        )

    @Slot(int, result=str)
    def eliminar_asignatura(self, asignatura_id: int) -> str:
        """Elimina una asignatura y sus evaluaciones.

        Args:
            asignatura_id: Identificador de la asignatura.

        Returns:
            JSON con ``eliminada: true``.
        """

        return self._responder(
            lambda: {"eliminada": self.contexto.asignaturas.eliminar(asignatura_id)},
            "notas",
        )

    # ------------------------------------------------------------------
    # Evaluaciones y calculadora de notas
    # ------------------------------------------------------------------
    @Slot(int, result=str)
    def listar_evaluaciones(self, asignatura_id: int) -> str:
        """Lista las evaluaciones de una asignatura.

        Args:
            asignatura_id: Identificador de la asignatura.

        Returns:
            JSON con la lista de evaluaciones y el cálculo actualizado.
        """

        def construir() -> dict[str, Any]:
            asignatura = self.contexto.asignaturas.obtener(asignatura_id)
            evaluaciones = self.contexto.evaluaciones.listar_por_asignatura(asignatura_id)
            calculo: dict[str, Any] = {}
            if asignatura:
                expediente = calcular_expediente([asignatura], {asignatura_id: evaluaciones})
                calculo = expediente["asignaturas"][0]["calculo"]
            return {"evaluaciones": evaluaciones, "calculo": calculo}

        return self._responder(construir)

    @Slot(str, result=str)
    def crear_evaluacion(self, datos_json: str) -> str:
        """Registra una evaluación para una asignatura.

        Args:
            datos_json: JSON con ``asignatura_id``, ``nombre``, ``peso``, ``tipo``,
                ``nota``, ``nota_maxima`` y ``fecha``.

        Returns:
            JSON con la evaluación creada.
        """

        datos = self._leer_json(datos_json)
        return self._responder(
            lambda: self.contexto.evaluaciones.crear(
                asignatura_id=int(datos.get("asignatura_id") or 0),
                nombre=str(datos.get("nombre") or ""),
                peso=float(datos.get("peso") or 0),
                tipo=str(datos.get("tipo") or "examen"),
                nota=float(datos["nota"]) if datos.get("nota") not in (None, "") else None,
                nota_maxima=float(datos.get("nota_maxima") or 10),
                fecha=str(datos.get("fecha") or ""),
            ),
            "notas",
        )

    @Slot(int, str, result=str)
    def actualizar_evaluacion(self, evaluacion_id: int, datos_json: str) -> str:
        """Actualiza una evaluación existente.

        Args:
            evaluacion_id: Identificador de la evaluación.
            datos_json: Campos a modificar.

        Returns:
            JSON con la evaluación actualizada.
        """

        datos = self._leer_json(datos_json)
        if "nota" in datos and datos["nota"] in ("", None):
            datos["nota"] = None
        return self._responder(
            lambda: self.contexto.evaluaciones.actualizar(evaluacion_id, datos), "notas"
        )

    @Slot(int, result=str)
    def eliminar_evaluacion(self, evaluacion_id: int) -> str:
        """Elimina una evaluación.

        Args:
            evaluacion_id: Identificador de la evaluación.

        Returns:
            JSON con ``eliminada: true``.
        """

        return self._responder(
            lambda: {"eliminada": self.contexto.evaluaciones.eliminar(evaluacion_id)},
            "notas",
        )

    @Slot(float, result=str)
    def obtener_expediente(self, objetivo: float = 5.0) -> str:
        """Calcula el expediente completo ponderado por créditos.

        Args:
            objetivo: Nota objetivo para la calculadora (escala 0-10).

        Returns:
            JSON con asignaturas enriquecidas, media ponderada y agregados.
        """

        def construir() -> dict[str, Any]:
            asignaturas = self.contexto.asignaturas.listar()
            evaluaciones = {
                int(asignatura["id"]): self.contexto.evaluaciones.listar_por_asignatura(
                    int(asignatura["id"])
                )
                for asignatura in asignaturas
            }
            expediente = calcular_expediente(asignaturas, evaluaciones, objetivo)
            for asignatura in expediente["asignaturas"]:
                eventos = self.contexto.eventos.listar(asignatura_id=int(asignatura["id"]))
                asignatura["total_eventos"] = len(eventos)
                asignatura["eventos_pendientes"] = sum(
                    1 for evento in eventos if not evento["completado"]
                )
            return expediente

        return self._responder(construir)

    @Slot(int, float, result=str)
    def calcular_escenario(self, asignatura_id: int, objetivo: float) -> str:
        """Recalcula una asignatura para una nota objetivo concreta.

        Args:
            asignatura_id: Identificador de la asignatura.
            objetivo: Nota final deseada (escala 0-10).

        Returns:
            JSON con media actual, nota provisional y nota necesaria.
        """

        objetivo_acotado = min(10.0, max(0.0, float(objetivo)))
        return self._responder(
            lambda: calcular_asignatura(
                self.contexto.evaluaciones.listar_por_asignatura(asignatura_id),
                objetivo_acotado,
            )
        )

    # ------------------------------------------------------------------
    # Eventos y calendario
    # ------------------------------------------------------------------
    @Slot(str, str, result=str)
    def listar_eventos(self, desde: str, hasta: str) -> str:
        """Lista eventos en un rango de fechas.

        Args:
            desde: Fecha ISO inicial; vacía para sin límite.
            hasta: Fecha ISO final; vacía para sin límite.

        Returns:
            JSON con la lista de eventos.
        """

        return self._responder(
            lambda: self.contexto.eventos.listar(desde=desde or None, hasta=hasta or None)
        )

    @Slot(int, result=str)
    def obtener_evento(self, evento_id: int) -> str:
        """Devuelve un evento concreto con sus subtareas.

        Args:
            evento_id: Identificador del evento.

        Returns:
            JSON con el evento o un error si no existe.
        """

        evento = self.contexto.eventos.obtener(evento_id)
        if evento is None:
            return self._error("El evento no existe", "no_encontrado")
        return self._respuesta(evento)

    @Slot(str, result=str)
    def crear_evento(self, datos_json: str) -> str:
        """Crea un evento, clase, examen, entrega o tarea.

        Args:
            datos_json: Campos del evento.

        Returns:
            JSON con el evento creado.
        """

        datos = self._leer_json(datos_json)
        if not datos.get("fecha_inicio"):
            return self._error("La fecha de inicio es obligatoria")
        return self._responder(
            lambda: self.contexto.eventos.crear(
                titulo=str(datos.get("titulo", "")),
                fecha_inicio=str(datos["fecha_inicio"]),
                fecha_fin=str(datos.get("fecha_fin") or datos["fecha_inicio"]),
                tipo=str(datos.get("tipo", "tarea")),
                descripcion=str(datos.get("descripcion", "")),
                todo_el_dia=bool(datos.get("todo_el_dia", False)),
                asignatura_id=int(datos["asignatura_id"]) if datos.get("asignatura_id") else None,
                ubicacion=str(datos.get("ubicacion", "")),
                prioridad=str(datos.get("prioridad", "media")),
                estado_kanban=str(datos.get("estado_kanban", "pendiente")),
                recordatorios=datos.get("recordatorios", (1440, 120, 15)),
            ),
            "evento",
        )

    @Slot(int, str, result=str)
    def actualizar_evento(self, evento_id: int, datos_json: str) -> str:
        """Actualiza los campos de un evento.

        Args:
            evento_id: Identificador del evento.
            datos_json: Campos a modificar.

        Returns:
            JSON con el evento actualizado.
        """

        return self._responder(
            lambda: self.contexto.eventos.actualizar(evento_id, self._leer_json(datos_json)),
            "evento",
        )

    @Slot(int, str, str, result=str)
    def mover_evento(self, evento_id: int, fecha_inicio: str, fecha_fin: str) -> str:
        """Mueve un evento en el calendario (arrastrar y soltar).

        Args:
            evento_id: Identificador del evento.
            fecha_inicio: Nueva fecha ISO de inicio.
            fecha_fin: Nueva fecha ISO de fin; vacía para conservar duración.

        Returns:
            JSON con el evento actualizado.
        """

        return self._responder(
            lambda: self.contexto.eventos.mover(
                evento_id, fecha_inicio, fecha_fin or None
            ),
            "evento",
        )

    @Slot(int, bool, result=str)
    def completar_evento(self, evento_id: int, completado: bool) -> str:
        """Marca o desmarca una tarea como completada.

        Args:
            evento_id: Identificador del evento.
            completado: Nuevo estado.

        Returns:
            JSON con el evento actualizado.
        """

        return self._responder(
            lambda: self.contexto.eventos.marcar_completado(evento_id, completado),
            "evento",
        )

    @Slot(int, result=str)
    def eliminar_evento(self, evento_id: int) -> str:
        """Elimina un evento y sus dependencias.

        Args:
            evento_id: Identificador del evento.

        Returns:
            JSON con ``eliminado: true``.
        """

        return self._responder(
            lambda: {"eliminado": self.contexto.eventos.eliminar(evento_id)},
            "evento",
        )

    @Slot(result=str)
    def listar_kanban(self) -> str:
        """Devuelve las tareas agrupadas por columna Kanban.

        Returns:
            JSON con ``columnas`` (lista ordenada) y contadores.
        """

        return self._responder(self._construir_kanban)

    def _construir_kanban(self) -> dict[str, Any]:
        """Agrupa las tareas en las cuatro columnas del tablero.

        Returns:
            Diccionario con columnas, títulos, colores y tareas.
        """

        tareas = self.contexto.eventos.listar_kanban()
        definicion = [
            {"id": "pendiente", "titulo": "Pendiente", "color": "#8a8fa8"},
            {"id": "en_desarrollo", "titulo": "En desarrollo", "color": "#4aa8ff"},
            {"id": "revision", "titulo": "Revisión / Pruebas", "color": "#ffc857"},
            {"id": "entregado", "titulo": "Entregado", "color": "#28c8a0"},
        ]
        columnas = []
        for columna in definicion:
            tareas_columna = [tarea for tarea in tareas if tarea["estado_kanban"] == columna["id"]]
            columnas.append(
                {
                    **columna,
                    "tareas": tareas_columna,
                    "total": len(tareas_columna),
                    "progreso_medio": int(
                        round(
                            sum(tarea["progreso"] for tarea in tareas_columna) / len(tareas_columna)
                        )
                    )
                    if tareas_columna
                    else 0,
                }
            )
        return {"columnas": columnas, "total": len(tareas)}


    @Slot(int, str, result=str)
    def mover_tarjeta(self, evento_id: int, columna: str) -> str:
        """Mueve una tarjeta a otra columna del tablero.

        Args:
            evento_id: Identificador de la tarea.
            columna: Columna destino.

        Returns:
            JSON con la tarea actualizada.
        """

        return self._responder(
            lambda: self.contexto.eventos.mover_kanban(evento_id, columna), "kanban"
        )

    @Slot(int, str, result=str)
    def crear_subtarea(self, evento_id: int, titulo: str) -> str:
        """Añade una subtarea a una tarjeta.

        Args:
            evento_id: Evento propietario.
            titulo: Texto de la subtarea.

        Returns:
            JSON con la subtarea creada.
        """

        return self._responder(
            lambda: self.contexto.eventos.crear_subtarea(evento_id, titulo), "kanban"
        )

    @Slot(int, bool, result=str)
    def alternar_subtarea(self, subtarea_id: int, completada: bool) -> str:
        """Cambia el estado de una subtarea.

        Args:
            subtarea_id: Identificador de la subtarea.
            completada: Nuevo estado.

        Returns:
            JSON con la subtarea y el evento actualizado.
        """

        def operacion() -> dict[str, Any]:
            subtarea = self.contexto.eventos.alternar_subtarea(subtarea_id, completada)
            if subtarea is None:
                raise ValueError("La subtarea no existe")
            evento = self.contexto.eventos.obtener(int(subtarea["evento_id"]))
            return {"subtarea": subtarea, "evento": evento}

        return self._responder(operacion, "kanban")

    @Slot(int, result=str)
    def eliminar_subtarea(self, subtarea_id: int) -> str:
        """Elimina una subtarea.

        Args:
            subtarea_id: Identificador de la subtarea.

        Returns:
            JSON con ``eliminada: true``.
        """

        return self._responder(
            lambda: {"eliminada": self.contexto.eventos.eliminar_subtarea(subtarea_id)}, "kanban"
        )

    # ------------------------------------------------------------------
    # Notificaciones
    # ------------------------------------------------------------------
    @Slot(str, result=str)
    def listar_notificaciones(self, solo_no_vistas: str = "") -> str:
        """Devuelve el historial de la campana.

        Args:
            solo_no_vistas: ``"1"`` para filtrar las no leídas.

        Returns:
            JSON con las notificaciones y el contador de alertas.
        """

        return self._responder(
            lambda: {
                "notificaciones": self.contexto.notificaciones.listar(
                    limite=50, solo_no_vistas=solo_no_vistas == "1"
                ),
                "alertas": self.contexto.notificaciones.contar_no_vistas(),
            }
        )

    @Slot(int, result=str)
    def marcar_notificacion_vista(self, notificacion_id: int) -> str:
        """Marca una notificación como leída.

        Args:
            notificacion_id: Identificador del aviso.

        Returns:
            JSON con el nuevo contador de alertas.
        """

        return self._responder(
            lambda: {
                "vista": self.contexto.notificaciones.marcar_vista(notificacion_id, True),
                "alertas": self.contexto.notificaciones.contar_no_vistas(),
            },
            "panel",
        )

    @Slot(result=str)
    def marcar_todas_notificaciones_vistas(self) -> str:
        """Marca toda la campana como leída.

        Returns:
            JSON con el contador a cero.
        """

        return self._responder(
            lambda: {
                "actualizadas": self.contexto.notificaciones.marcar_todas_vistas(),
                "alertas": 0,
            },
            "panel",
        )

    @Slot(int, int, result=str)
    def posponer_notificacion(self, notificacion_id: int, minutos: int) -> str:
        """Pospone un aviso y lo reenvía pasados unos minutos.

        Args:
            notificacion_id: Identificador del aviso.
            minutos: Minutos de espera (normalmente 15).

        Returns:
            JSON con la notificación pospuesta.
        """

        hasta = a_iso(ahora() + timedelta(minutes=max(1, int(minutos))))
        return self._responder(
            lambda: self.contexto.notificaciones.posponer(notificacion_id, hasta), "panel"
        )

    @Slot(result=str)
    def ejecutar_ciclo_notificaciones(self) -> str:
        """Fuerza una revisión del planificador y devuelve los avisos enviados.

        Returns:
            JSON con la lista de notificaciones entregadas.
        """

        enviadas = self.planificador.revisar()
        for aviso in enviadas:
            self.notificacionRecibida.emit(json.dumps(aviso, ensure_ascii=False, default=str))
        if enviadas:
            self.datosActualizados.emit("panel")
        return self._respuesta(enviadas)

    # ------------------------------------------------------------------
    # Pomodoro
    # ------------------------------------------------------------------
    @Slot(str, result=str)
    def iniciar_pomodoro(self, datos_json: str) -> str:
        """Arranca una sesión Pomodoro.

        Args:
            datos_json: Asignatura, evento, modo y duraciones.

        Returns:
            JSON con el estado del temporizador.
        """

        datos = self._leer_json(datos_json)
        estado = self.gestor_pomodoro.iniciar(
            asignatura_id=int(datos["asignatura_id"]) if datos.get("asignatura_id") else None,
            evento_id=int(datos["evento_id"]) if datos.get("evento_id") else None,
            modo=str(datos.get("modo", "25/5")),
            duracion_trabajo=int(datos["duracion_trabajo"]) if datos.get("duracion_trabajo") else None,
            duracion_descanso=int(datos["duracion_descanso"]) if datos.get("duracion_descanso") else None,
            notas=str(datos.get("notas", "")),
        )
        self.pomodoroActualizado.emit(json.dumps(estado, ensure_ascii=False))
        return self._respuesta(estado)

    @Slot(int, result=str)
    def tick_pomodoro(self, segundos: int = 1) -> str:
        """Avanza el temporizador y notifica cambios de fase.

        Args:
            segundos: Segundos transcurridos.

        Returns:
            JSON con el estado y la sesión guardada si cambió la fase.
        """

        estado = self.gestor_pomodoro.tick(segundos)
        self.pomodoroActualizado.emit(json.dumps(estado, ensure_ascii=False, default=str))
        if estado.get("sesion_guardada"):
            self.datosActualizados.emit("panel")
            self.notificacionRecibida.emit(
                json.dumps(
                    {
                        "titulo": "🍅 Bloque de estudio completado",
                        "mensaje": "Tómate un descanso: lo has ganado.",
                        "programada_para": a_iso(ahora()),
                    },
                    ensure_ascii=False,
                )
            )
        return self._respuesta(estado)

    @Slot(result=str)
    def alternar_pausa_pomodoro(self) -> str:
        """Pausa o reanuda el temporizador.

        Returns:
            JSON con el estado actualizado.
        """

        estado = self.gestor_pomodoro.alternar_pausa()
        self.pomodoroActualizado.emit(json.dumps(estado, ensure_ascii=False))
        return self._respuesta(estado)

    @Slot(result=str)
    def finalizar_pomodoro(self) -> str:
        """Termina la sesión y guarda el tiempo efectivo.

        Returns:
            JSON con la sesión guardada y el estado final.
        """

        resultado = self.gestor_pomodoro.finalizar()
        self.pomodoroActualizado.emit(json.dumps(resultado["estado"], ensure_ascii=False))
        if resultado.get("sesion"):
            self.datosActualizados.emit("panel")
        return self._respuesta(resultado)

    @Slot(result=str)
    def estado_pomodoro(self) -> str:
        """Consulta el estado del temporizador sin avanzarlo.

        Returns:
            JSON con el estado actual.
        """

        return self._respuesta(self.gestor_pomodoro.estado())

    # ------------------------------------------------------------------
    # Calendarios iCalendar
    # ------------------------------------------------------------------
    @Slot(result=str)
    def elegir_e_importar_ics(self) -> str:
        """Abre un selector de archivos e importa el ``.ics`` elegido.

        Returns:
            JSON con el resultado de la importación o un aviso de cancelación.
        """

        ruta, _ = QFileDialog.getOpenFileName(
            None,
            "Seleccionar calendario iCalendar",
            str(Path.home()),
            "Calendarios (*.ics);;Todos los archivos (*)",
        )
        if not ruta:
            return self._respuesta({"cancelado": True}, "No se seleccionó ningún archivo")
        return self._responder(lambda: self.sincronizador.importar_archivo(ruta), "evento")

    @Slot(str, result=str)
    def importar_texto_ics(self, texto: str) -> str:
        """Importa contenido iCalendar pegado o descargado por la interfaz.

        Args:
            texto: Documento iCalendar completo.

        Returns:
            JSON con los contadores de la importación.
        """

        return self._responder(
            lambda: self.sincronizador.importar_texto(texto), "evento"
        )

    @Slot(result=str)
    def listar_suscripciones(self) -> str:
        """Lista los feeds iCalendar configurados.

        Returns:
            JSON con las suscripciones.
        """

        return self._responder(self.contexto.suscripciones.listar)

    @Slot(str, result=str)
    def crear_suscripcion(self, datos_json: str) -> str:
        """Registra una suscripción a un calendario remoto.

        Args:
            datos_json: Nombre, URL y frecuencia en minutos.

        Returns:
            JSON con la suscripción creada.
        """

        datos = self._leer_json(datos_json)
        return self._responder(
            lambda: self.contexto.suscripciones.crear(
                nombre=str(datos.get("nombre", "")),
                url=str(datos.get("url", "")),
                frecuencia_minutos=int(datos.get("frecuencia_minutos", 60) or 60),
            ),
            "configuracion",
        )

    @Slot(int, str, result=str)
    def actualizar_suscripcion(self, suscripcion_id: int, datos_json: str) -> str:
        """Actualiza una suscripción existente.

        Args:
            suscripcion_id: Identificador de la suscripción.
            datos_json: Campos a modificar.

        Returns:
            JSON con la suscripción actualizada.
        """

        return self._responder(
            lambda: self.contexto.suscripciones.actualizar(
                suscripcion_id, self._leer_json(datos_json)
            ),
            "configuracion",
        )

    @Slot(int, result=str)
    def eliminar_suscripcion(self, suscripcion_id: int) -> str:
        """Elimina una suscripción sin borrar los eventos importados.

        Args:
            suscripcion_id: Identificador de la suscripción.

        Returns:
            JSON con ``eliminada: true``.
        """

        return self._responder(
            lambda: {"eliminada": self.contexto.suscripciones.eliminar(suscripcion_id)},
            "configuracion",
        )

    @Slot(int, result=str)
    def sincronizar_suscripcion(self, suscripcion_id: int) -> str:
        """Sincroniza manualmente una suscripción.

        Args:
            suscripcion_id: Identificador de la suscripción.

        Returns:
            JSON con el resultado de la importación.
        """

        resultado = self.sincronizador.sincronizar_suscripcion(suscripcion_id)
        if resultado.get("ok"):
            self.datosActualizados.emit("evento")
        return json.dumps(resultado, ensure_ascii=False, default=str)

    @Slot(result=str)
    def sincronizar_todo_ics(self) -> str:
        """Sincroniza todos los feeds cuya frecuencia haya vencido.

        Returns:
            JSON con la lista de resultados.
        """

        resultados = self.sincronizador.sincronizar_todas()
        if any(resultado.get("ok") for resultado in resultados):
            self.datosActualizados.emit("evento")
        return self._respuesta(resultados)

    # ------------------------------------------------------------------
    # Gadget y tema
    # ------------------------------------------------------------------
    def _estado_gadget(self) -> dict[str, Any]:
        """Reúne la configuración visual del gadget.

        Returns:
            Diccionario con opacidad, bloqueo, modo compacto y posición.
        """

        configuracion = self.contexto.configuracion
        return {
            "opacidad": float(configuracion.obtener("opacidad_gadget", "0.92") or 0.92),
            "bloqueado": configuracion.obtener("gadget_bloqueado", "0") == "1",
            "compacto": configuracion.obtener("gadget_compacto", "0") == "1",
            "visible": configuracion.obtener("gadget_visible", "1") == "1",
            "posicion_x": configuracion.obtener("gadget_posicion_x", ""),
            "posicion_y": configuracion.obtener("gadget_posicion_y", ""),
            "tema": configuracion.obtener("tema", "cristal-medianoche"),
        }

    @Slot(result=str)
    def obtener_estado_gadget(self) -> str:
        """Consulta la configuración visual del gadget.

        Returns:
            JSON con el estado del gadget y los datos del día.
        """

        return self._responder(
            lambda: {
                **self._estado_gadget(),
                "panel": self._construir_panel(),
            }
        )

    @Slot(str, result=str)
    def guardar_estado_gadget(self, datos_json: str) -> str:
        """Persiste opacidad, bloqueo, tamaño o posición del gadget.

        Args:
            datos_json: Cambios de configuración visual.

        Returns:
            JSON con el estado resultante.
        """

        datos = self._leer_json(datos_json)
        cambios: dict[str, str] = {}
        if "opacidad" in datos:
            opacidad = min(1.0, max(0.3, float(datos["opacidad"])))
            cambios["opacidad_gadget"] = f"{opacidad:.2f}"
        if "bloqueado" in datos:
            cambios["gadget_bloqueado"] = "1" if datos["bloqueado"] else "0"
        if "compacto" in datos:
            cambios["gadget_compacto"] = "1" if datos["compacto"] else "0"
        if "visible" in datos:
            cambios["gadget_visible"] = "1" if datos["visible"] else "0"
        if "posicion_x" in datos:
            cambios["gadget_posicion_x"] = str(datos["posicion_x"])
        if "posicion_y" in datos:
            cambios["gadget_posicion_y"] = str(datos["posicion_y"])
        if datos.get("tema"):
            cambios["tema"] = str(datos["tema"])
        self.contexto.configuracion.guardar_varias(cambios)
        estado = self._estado_gadget()
        self.gadgetConfigurado.emit(json.dumps(estado, ensure_ascii=False))
        if "tema" in cambios:
            self.temaCambiado.emit(cambios["tema"])
        return self._respuesta(estado)

    @Slot(bool, result=str)
    def alternar_gadget(self, visible: bool) -> str:
        """Muestra u oculta el gadget.

        Args:
            visible: Estado deseado.

        Returns:
            JSON con la configuración actualizada.
        """

        return self.guardar_estado_gadget(json.dumps({"visible": visible}))

    @Slot(result=str)
    def iniciar_arrastre_gadget(self) -> str:
        """Inicia el arrastre de la ventana nativa del gadget.

        Returns:
            JSON de confirmación; la ventana recuerda su posición de origen.
        """

        self.gadgetArrastrado.emit(json.dumps({"accion": "iniciar"}))
        return self._respuesta({"arrastrando": True})

    @Slot(int, int, result=str)
    def mover_gadget(self, delta_x: int, delta_y: int) -> str:
        """Desplaza el gadget según el delta del puntero.

        Args:
            delta_x: Desplazamiento horizontal en píxeles.
            delta_y: Desplazamiento vertical en píxeles.

        Returns:
            JSON de confirmación.
        """

        self.gadgetArrastrado.emit(
            json.dumps({"accion": "mover", "dx": int(delta_x), "dy": int(delta_y)})
        )
        return self._respuesta({"ok": True})

    @Slot(result=str)
    def soltar_gadget(self) -> str:
        """Finaliza el arrastre y pide guardar la posición.

        Returns:
            JSON de confirmación.
        """

        self.gadgetArrastrado.emit(json.dumps({"accion": "soltar"}))
        return self._respuesta({"soltado": True})

    @Slot(result=str)
    def abrir_agenda(self) -> str:
        """Solicita mostrar la ventana principal en la vista de inicio.

        Returns:
            JSON de confirmación.
        """

        self.solicitudNavegacion.emit("inicio")
        return self._respuesta({"ok": True})

    @Slot(str, result=str)
    def cambiar_tema(self, tema: str) -> str:
        """Cambia el tema visual de la aplicación y del gadget.

        Args:
            tema: ``cristal-medianoche``, ``noche-nordica`` o ``luz-pura``.

        Returns:
            JSON con el tema activo.
        """

        tema_limpio = tema if tema in ("cristal-medianoche", "noche-nordica", "luz-pura") else "cristal-medianoche"
        self.contexto.configuracion.guardar("tema", tema_limpio)
        self.temaCambiado.emit(tema_limpio)
        self.gadgetConfigurado.emit(
            json.dumps({**self._estado_gadget(), "tema": tema_limpio}, ensure_ascii=False)
        )
        return self._respuesta({"tema": tema_limpio})

    # ------------------------------------------------------------------
    # Configuración, respaldos e informes
    # ------------------------------------------------------------------
    @Slot(result=str)
    def obtener_configuracion(self) -> str:
        """Devuelve toda la configuración persistida.

        Returns:
            JSON con el diccionario de preferencias.
        """

        return self._responder(self.contexto.configuracion.todas)

    @Slot(str, result=str)
    def guardar_configuracion(self, datos_json: str) -> str:
        """Guarda preferencias enviadas por la vista de ajustes.

        Args:
            datos_json: Diccionario de cambios.

        Returns:
            JSON con la configuración resultante.
        """

        datos = self._leer_json(datos_json)

        def operacion() -> dict[str, str]:
            self.contexto.configuracion.guardar_varias(datos)
            return self.contexto.configuracion.todas()

        return self._responder(operacion, "configuracion")

    @Slot(result=str)
    def crear_respaldo(self) -> str:
        """Crea un ZIP con una instantánea de la base de datos.

        Returns:
            JSON con los metadatos del respaldo.
        """

        return self._responder(
            lambda: self.gestor_respaldos.crear_respaldo("manual"), "configuracion"
        )

    @Slot(result=str)
    def listar_respaldos(self) -> str:
        """Lista las copias de seguridad disponibles.

        Returns:
            JSON con los respaldos ordenados por fecha.
        """

        return self._responder(self.gestor_respaldos.listar_respaldos)

    @Slot(result=str)
    def elegir_y_restaurar_respaldo(self) -> str:
        """Abre un selector de ZIP y restaura la copia elegida.

        Returns:
            JSON con el resultado de la restauración.
        """

        ruta, _ = QFileDialog.getOpenFileName(
            None,
            "Seleccionar copia de seguridad",
            str(self.gestor_respaldos.directorio),
            "Copias de seguridad (*.zip)",
        )
        if not ruta:
            return self._respuesta({"cancelado": True}, "Restauración cancelada")
        return self._responder(
            lambda: self.gestor_respaldos.restaurar_respaldo(ruta), "todo"
        )

    @Slot(str, result=str)
    def restaurar_respaldo(self, ruta: str) -> str:
        """Restaura una copia por su ruta.

        Args:
            ruta: Archivo ZIP de respaldo.

        Returns:
            JSON con el resultado de la restauración.
        """

        return self._responder(
            lambda: self.gestor_respaldos.restaurar_respaldo(ruta), "todo"
        )

    @Slot(result=str)
    def estado_inicio_automatico(self) -> str:
        """Consulta si la agenda arranca con el sistema.

        Returns:
            JSON con el estado del mecanismo nativo.
        """

        return self._respuesta(self.inicio_automatico.estado())

    @Slot(result=str)
    def alternar_inicio_automatico(self) -> str:
        """Activa o desactiva el arranque automático.

        Returns:
            JSON con el estado resultante.
        """

        resultado = self.inicio_automatico.alternar()
        self.contexto.configuracion.guardar(
            "inicio_automatico", "1" if self.inicio_automatico.esta_activo() else "0"
        )
        return json.dumps(resultado, ensure_ascii=False, default=str)

    @Slot(str, result=str)
    def abrir_enlace(self, url: str) -> str:
        """Abre un enlace externo en el navegador del sistema.

        Args:
            url: Dirección ``http(s)`` o ``mailto``.

        Returns:
            JSON con ``ok`` o un error si el esquema no está permitido.
        """

        esquema = urlparse(url).scheme.lower()
        if esquema not in ("http", "https", "mailto"):
            return self._error("Solo se permiten enlaces http, https o mailto")
        abierto = QDesktopServices.openUrl(QUrl(url))
        return self._respuesta({"abierto": bool(abierto)})

    @Slot(str, result=str)
    def abrir_modal(self, tipo: str) -> str:
        """Pide a la interfaz que abra un modal (usado por la bandeja).

        Args:
            tipo: ``tarea``, ``evento`` o ``asignatura``.

        Returns:
            JSON de confirmación.
        """

        self.solicitudModal.emit(tipo)
        return self._respuesta({"solicitado": tipo})

    @Slot(result=str)
    def solicitar_nueva_tarea(self) -> str:
        """Solicita el modal de nueva tarea y trae la ventana al frente.

        Returns:
            JSON de confirmación.
        """

        self.solicitudModal.emit("tarea")
        return self._respuesta({"ok": True})
