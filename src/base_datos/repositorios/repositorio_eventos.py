"""Repositorio de eventos académicos.

Un *evento* representa cualquier elemento con fecha: una clase, un examen, una
entrega, una tarea del tablero o una sesión planificada de estudio. El repositorio
ofrece consultas por rango, búsquedas para el panel y el gadget, movimiento entre
días u horas, cambio de columna Kanban y gestión de subtareas.

Notes:
    Las fechas se almacenan en ISO-8601 (``AAAA-MM-DDTHH:MM``). Las columnas
    ``completado`` y ``todo_el_dia`` se exponen como ``bool``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable, Sequence

from src.base_datos.repositorios.repositorio_base import RepositorioBase
from src.utilidades import ahora, a_iso, desde_iso, minutos_entre

TIPOS_EVENTO: tuple[str, ...] = ("clase", "examen", "entrega", "tarea", "estudio")
PRIORIDADES: tuple[str, ...] = ("baja", "media", "alta", "critica")
COLUMNAS_KANBAN: tuple[str, ...] = ("pendiente", "en_desarrollo", "revision", "entregado")

_SELECT_BASE = """
    SELECT e.*, a.nombre AS asignatura_nombre, a.color AS asignatura_color
    FROM eventos AS e
    LEFT JOIN asignaturas AS a ON a.id = e.asignatura_id
"""

_SELECT_BASE_CON_PROGRESO = """
    SELECT e.*, a.nombre AS asignatura_nombre, a.color AS asignatura_color,
           (SELECT COUNT(*) FROM subtareas s WHERE s.evento_id = e.id) AS total_subtareas,
           (SELECT COUNT(*) FROM subtareas s WHERE s.evento_id = e.id AND s.completada = 1)
               AS subtareas_completadas
    FROM eventos AS e
    LEFT JOIN asignaturas AS a ON a.id = e.asignatura_id
"""


class RepositorioEventos(RepositorioBase):
    """Acceso a la tabla ``eventos`` y a sus subtareas."""

    _CAMPOS_ACTUALIZABLES = (
        "titulo",
        "descripcion",
        "tipo",
        "fecha_inicio",
        "fecha_fin",
        "todo_el_dia",
        "asignatura_id",
        "ubicacion",
        "prioridad",
        "estado_kanban",
        "completado",
        "recordatorios",
        "uid_ics",
        "origen",
    )

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------
    def _serializar(self, fila: dict[str, Any]) -> dict[str, Any]:
        """Convierte una fila SQL en un evento apto para JSON.

        Args:
            fila: Fila cruda con la unión de asignatura y contadores.

        Returns:
            Evento con booleanos normalizados, recordatorios como lista y
            campos calculados de progreso.
        """

        evento = dict(fila)
        evento["completado"] = bool(evento.get("completado"))
        evento["todo_el_dia"] = bool(evento.get("todo_el_dia"))
        evento["recordatorios"] = self.texto_a_lista_minutos(evento.get("recordatorios"))
        total = int(evento.pop("total_subtareas", 0) or 0)
        completadas = int(evento.pop("subtareas_completadas", 0) or 0)
        evento["progreso"] = int(round(completadas * 100 / total)) if total else 0
        evento["total_subtareas"] = total
        evento["subtareas_completadas"] = completadas
        evento["subtareas"] = []
        return evento

    def _cargar_subtareas(self, eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Adjunta las subtareas de todos los eventos en una sola consulta.

        Evita el problema N+1 consultando únicamente los identificadores
        presentes en la página actual.

        Args:
            eventos: Lista de eventos ya serializados (se modifica in situ).

        Returns:
            La misma lista, con la clave ``subtareas`` rellena.
        """

        identificadores = [int(evento["id"]) for evento in eventos if evento.get("id")]
        if not identificadores:
            return eventos
        marcadores = ",".join("?" for _ in identificadores)
        filas = self.gestor.consultar_todos(
            f"""
            SELECT * FROM subtareas
            WHERE evento_id IN ({marcadores})
            ORDER BY orden ASC, id ASC
            """,
            identificadores,
        )
        agrupadas: dict[int, list[dict[str, Any]]] = {}
        for fila in filas:
            subtarea = dict(fila)
            subtarea["completada"] = bool(subtarea["completada"])
            agrupadas.setdefault(int(subtarea["evento_id"]), []).append(subtarea)
        for evento in eventos:
            evento["subtareas"] = agrupadas.get(int(evento["id"]), [])
        return eventos

    def _adjuntar_subtareas(self, evento: dict[str, Any]) -> dict[str, Any]:
        """Carga las subtareas de un único evento.

        Args:
            evento: Evento serializado.

        Returns:
            El evento con su lista de subtareas.
        """

        self._cargar_subtareas([evento])
        return evento

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def obtener(self, evento_id: int) -> dict[str, Any] | None:
        """Busca un evento por identificador.

        Args:
            evento_id: Clave primaria del evento.

        Returns:
            Evento con subtareas, o ``None`` si no existe.
        """

        fila = self.gestor.consultar_uno(
            f"{_SELECT_BASE_CON_PROGRESO} WHERE e.id = ?", (evento_id,)
        )
        return self._adjuntar_subtareas(self._serializar(fila)) if fila else None

    def listar(
        self,
        desde: str | None = None,
        hasta: str | None = None,
        tipos: Iterable[str] | None = None,
        asignatura_id: int | None = None,
        solo_pendientes: bool = False,
        texto: str | None = None,
        limite: int | None = None,
    ) -> list[dict[str, Any]]:
        """Consulta eventos con filtros opcionales combinables.

        Args:
            desde: Fecha ISO mínima de inicio (inclusive).
            hasta: Fecha ISO máxima de inicio (inclusive).
            tipos: Tipos de evento admitidos (``clase``, ``examen``...).
            asignatura_id: Restringe a una asignatura concreta.
            solo_pendientes: Si es ``True``, excluye los completados.
            texto: Búsqueda parcial en título, descripción o ubicación.
            limite: Número máximo de resultados.

        Returns:
            Lista ordenada por fecha de inicio ascendente.
        """

        condiciones: list[str] = []
        parametros: list[Any] = []
        if desde:
            condiciones.append("e.fecha_inicio >= ?")
            parametros.append(desde)
        if hasta:
            condiciones.append("e.fecha_inicio <= ?")
            parametros.append(hasta)
        if tipos:
            lista_tipos = [tipo for tipo in tipos if tipo in TIPOS_EVENTO]
            if lista_tipos:
                condiciones.append(f"e.tipo IN ({','.join('?' for _ in lista_tipos)})")
                parametros.extend(lista_tipos)
        if asignatura_id:
            condiciones.append("e.asignatura_id = ?")
            parametros.append(asignatura_id)
        if solo_pendientes:
            condiciones.append("e.completado = 0")
        if texto:
            condiciones.append("(e.titulo LIKE ? OR e.descripcion LIKE ? OR e.ubicacion LIKE ?)")
            patron = f"%{texto.strip()}%"
            parametros.extend([patron, patron, patron])

        sentencia = _SELECT_BASE_CON_PROGRESO
        if condiciones:
            sentencia += " WHERE " + " AND ".join(condiciones)
        sentencia += " ORDER BY e.fecha_inicio ASC, e.id ASC"
        if limite:
            sentencia += " LIMIT ?"
            parametros.append(int(limite))

        eventos = [self._serializar(fila) for fila in self.gestor.consultar_todos(sentencia, parametros)]
        return self._cargar_subtareas(eventos)

    def listar_dia(self, fecha: str | None = None) -> list[dict[str, Any]]:
        """Devuelve los eventos de un día completo.

        Args:
            fecha: Día en formato ISO. Por defecto, hoy.

        Returns:
            Eventos ordenados por hora.
        """

        dia = fecha or a_iso(ahora())[:10]
        return self.listar(desde=f"{dia}T00:00", hasta=f"{dia}T23:59")

    def proximos_examenes(
        self, limite: int = 3, desde: str | None = None
    ) -> list[dict[str, Any]]:
        """Obtiene los próximos exámenes y entregas pendientes.

        Args:
            limite: Número máximo de resultados.
            desde: Instante ISO de referencia. Por defecto, ahora.

        Returns:
            Lista de eventos críticos ordenados por cercanía.
        """

        referencia = desde or a_iso(ahora())
        filas = self.gestor.consultar_todos(
            f"""
            {_SELECT_BASE_CON_PROGRESO}
            WHERE e.tipo IN ('examen', 'entrega')
              AND e.completado = 0
              AND e.fecha_inicio >= ?
            ORDER BY e.fecha_inicio ASC
            LIMIT ?
            """,
            (referencia, int(limite)),
        )
        eventos = [self._serializar(fila) for fila in filas]
        return self._cargar_subtareas(eventos)

    def proximo_hito(self, desde: str | None = None) -> dict[str, Any] | None:
        """Devuelve el siguiente examen o entrega para la cuenta atrás del gadget.

        Args:
            desde: Instante ISO de referencia. Por defecto, ahora.

        Returns:
            El evento más cercano o ``None`` si no hay hitos futuros.
        """

        proximos = self.proximos_examenes(limite=1, desde=desde)
        return proximos[0] if proximos else None

    def listar_kanban(self) -> list[dict[str, Any]]:
        """Obtiene las tareas del tablero ordenadas por prioridad y fecha.

        Returns:
            Tareas de tipo ``tarea`` con subtareas y progreso.
        """

        filas = self.gestor.consultar_todos(
            f"""
            {_SELECT_BASE_CON_PROGRESO}
            WHERE e.tipo = 'tarea'
            ORDER BY
                CASE e.prioridad
                    WHEN 'critica' THEN 0
                    WHEN 'alta' THEN 1
                    WHEN 'media' THEN 2
                    ELSE 3
                END,
                e.fecha_inicio ASC,
                e.id ASC
            """
        )
        tareas = [self._serializar(fila) for fila in filas]
        return self._cargar_subtareas(tareas)

    def contar_entregas_proximas(self, dias: int = 7, desde: str | None = None) -> int:
        """Cuenta entregas y exámenes pendientes en los próximos días.

        Args:
            dias: Ventana temporal en días.
            desde: Instante de referencia.

        Returns:
            Número de hitos pendientes dentro de la ventana.
        """

        inicio = desde_iso(desde) if desde else ahora()
        fin = a_iso(inicio + timedelta(days=dias))
        fila = self.gestor.consultar_uno(
            """
            SELECT COUNT(*) AS total FROM eventos
            WHERE tipo IN ('examen', 'entrega')
              AND completado = 0
              AND fecha_inicio >= ?
              AND fecha_inicio <= ?
            """,
            (desde or a_iso(inicio), fin),
        )
        return int(fila["total"]) if fila else 0

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------
    def crear(
        self,
        titulo: str,
        fecha_inicio: str,
        fecha_fin: str | None = None,
        tipo: str = "tarea",
        descripcion: str = "",
        todo_el_dia: bool = False,
        asignatura_id: int | None = None,
        ubicacion: str = "",
        prioridad: str = "media",
        estado_kanban: str = "pendiente",
        uid_ics: str | None = None,
        origen: str = "manual",
        recordatorios: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        """Crea un evento validando los campos enumerados.

        Args:
            titulo: Título visible (obligatorio).
            fecha_inicio: Fecha y hora ISO de inicio.
            fecha_fin: Fin del evento. Si se omite, se usa ``fecha_inicio``.
            tipo: Uno de :data:`TIPOS_EVENTO`.
            descripcion: Texto libre.
            todo_el_dia: Marca el evento como de día completo.
            asignatura_id: Asignatura relacionada o ``None``.
            ubicacion: Aula, enlace o lugar.
            prioridad: Una de :data:`PRIORIDADES`.
            estado_kanban: Columna inicial si es una tarea.
            uid_ics: Identificador global del feed iCalendar.
            origen: ``manual``, ``ics`` o ``url``.
            recordatorios: Minutos de antelación. Por defecto 1 día, 2 horas y 15 minutos.

        Returns:
            El evento creado con sus subtareas (vacías).

        Raises:
            ValueError: Si el título está vacío o algún campo enumerado no es válido.
        """

        titulo_limpio = (titulo or "").strip()
        if not titulo_limpio:
            raise ValueError("El título del evento es obligatorio")
        if tipo not in TIPOS_EVENTO:
            raise ValueError(f"Tipo de evento no válido: {tipo}")
        if prioridad not in PRIORIDADES:
            raise ValueError(f"Prioridad no válida: {prioridad}")
        if estado_kanban not in COLUMNAS_KANBAN:
            raise ValueError(f"Estado Kanban no válido: {estado_kanban}")

        marca = self.marca_tiempo()
        identificador = self.gestor.ejecutar(
            """
            INSERT INTO eventos (
                titulo, descripcion, tipo, fecha_inicio, fecha_fin, todo_el_dia,
                asignatura_id, ubicacion, prioridad, estado_kanban, completado,
                uid_ics, origen, recordatorios, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                titulo_limpio,
                (descripcion or "").strip(),
                tipo,
                fecha_inicio,
                fecha_fin or fecha_inicio,
                int(bool(todo_el_dia)),
                asignatura_id,
                (ubicacion or "").strip(),
                prioridad,
                estado_kanban,
                uid_ics,
                origen,
                self.lista_minutos_a_texto(recordatorios if recordatorios is not None else (1440, 120, 15)),
                marca,
                marca,
            ),
        )
        evento = self.obtener(identificador)
        assert evento is not None
        return evento

    def actualizar(self, evento_id: int, cambios: dict[str, Any]) -> dict[str, Any] | None:
        """Actualiza un evento existente.

        Args:
            evento_id: Identificador del evento.
            cambios: Campos a modificar; las claves desconocidas se ignoran.

        Returns:
            Evento actualizado o ``None`` si no existe.

        Raises:
            ValueError: Si se intenta asignar un tipo, prioridad o estado inválido.
        """

        if "tipo" in cambios and cambios["tipo"] not in TIPOS_EVENTO:
            raise ValueError(f"Tipo de evento no válido: {cambios['tipo']}")
        if "prioridad" in cambios and cambios["prioridad"] not in PRIORIDADES:
            raise ValueError(f"Prioridad no válida: {cambios['prioridad']}")
        if "estado_kanban" in cambios and cambios["estado_kanban"] not in COLUMNAS_KANBAN:
            raise ValueError(f"Estado Kanban no válido: {cambios['estado_kanban']}")

        campos = [campo for campo in self._CAMPOS_ACTUALIZABLES if campo in cambios]
        if not campos:
            return self.obtener(evento_id)

        valores: list[Any] = []
        for campo in campos:
            valor = cambios[campo]
            if campo == "recordatorios":
                valor = self.lista_minutos_a_texto(valor or [])
            elif campo in ("completado", "todo_el_dia"):
                valor = int(bool(valor))
            elif isinstance(valor, str):
                valor = valor.strip()
            valores.append(valor)
        valores.extend([self.marca_tiempo(), evento_id])

        self.gestor.ejecutar(
            f"UPDATE eventos SET {', '.join(f'{campo} = ?' for campo in campos)}, "
            "actualizado_en = ? WHERE id = ?",
            valores,
        )
        return self.obtener(evento_id)

    def mover(
        self,
        evento_id: int,
        fecha_inicio: str,
        fecha_fin: str | None = None,
        estado_kanban: str | None = None,
    ) -> dict[str, Any] | None:
        """Mueve un evento a otra fecha conservando su duración si no se indica fin.

        Args:
            evento_id: Evento que se arrastra en el calendario.
            fecha_inicio: Nueva fecha y hora de inicio.
            fecha_fin: Nueva fecha final. Si se omite, se conserva la duración.
            estado_kanban: Columna destino si también se mueve en el tablero.

        Returns:
            Evento actualizado o ``None`` si no existe.
        """

        evento = self.obtener(evento_id)
        if evento is None:
            return None
        duracion = minutos_entre(evento["fecha_inicio"], evento["fecha_fin"])
        fin_calculado = fecha_fin or a_iso(
            desde_iso(fecha_inicio) + timedelta(minutes=max(duracion, 0))
        )
        cambios: dict[str, Any] = {"fecha_inicio": fecha_inicio, "fecha_fin": fin_calculado}
        if estado_kanban:
            cambios["estado_kanban"] = estado_kanban
        return self.actualizar(evento_id, cambios)

    def marcar_completado(self, evento_id: int, completado: bool = True) -> dict[str, Any] | None:
        """Marca o desmarca un evento como completado.

        Args:
            evento_id: Identificador del evento.
            completado: Nuevo estado de finalización.

        Returns:
            Evento actualizado o ``None`` si no existe.
        """

        return self.actualizar(evento_id, {"completado": completado})

    def mover_kanban(self, evento_id: int, columna: str) -> dict[str, Any] | None:
        """Cambia la columna Kanban de una tarea.

        Args:
            evento_id: Identificador de la tarea.
            columna: Una de :data:`COLUMNAS_KANBAN`.

        Returns:
            Tarea actualizada o ``None`` si no existe.

        Raises:
            ValueError: Si la columna no es válida.
        """

        if columna not in COLUMNAS_KANBAN:
            raise ValueError(f"Columna Kanban no válida: {columna}")
        cambios: dict[str, Any] = {"estado_kanban": columna}
        if columna == "entregado":
            cambios["completado"] = True
        elif columna in ("pendiente", "en_desarrollo", "revision"):
            cambios["completado"] = False
        return self.actualizar(evento_id, cambios)

    def eliminar(self, evento_id: int) -> bool:
        """Elimina un evento y, en cascada, sus subtareas y notificaciones.

        Args:
            evento_id: Identificador del evento.

        Returns:
            ``True`` si existía y se eliminó.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("DELETE FROM eventos WHERE id = ?", (evento_id,))
            return cursor.rowcount > 0

    def buscar_por_uid(self, uid: str) -> dict[str, Any] | None:
        """Busca un evento importado por su ``UID`` iCalendar.

        Args:
            uid: Identificador global del feed.

        Returns:
            Evento encontrado o ``None``.
        """

        if not uid:
            return None
        fila = self.gestor.consultar_uno(f"{_SELECT_BASE} WHERE e.uid_ics = ?", (uid,))
        return self._serializar(fila) if fila else None

    # ------------------------------------------------------------------
    # Subtareas
    # ------------------------------------------------------------------
    def crear_subtarea(self, evento_id: int, titulo: str, orden: int | None = None) -> dict[str, Any]:
        """Añade una subtarea a una tarea o entrega.

        Args:
            evento_id: Evento propietario.
            titulo: Descripción breve de la subtarea.
            orden: Posición; si se omite, se añade al final.

        Returns:
            Subtarea creada.

        Raises:
            ValueError: Si el título está vacío.
        """

        titulo_limpio = (titulo or "").strip()
        if not titulo_limpio:
            raise ValueError("El título de la subtarea es obligatorio")
        if orden is None:
            fila = self.gestor.consultar_uno(
                "SELECT COALESCE(MAX(orden), -1) + 1 AS siguiente FROM subtareas WHERE evento_id = ?",
                (evento_id,),
            )
            orden = int(fila["siguiente"]) if fila else 0
        identificador = self.gestor.ejecutar(
            "INSERT INTO subtareas (evento_id, titulo, completada, orden) VALUES (?, ?, 0, ?)",
            (evento_id, titulo_limpio, int(orden)),
        )
        fila = self.gestor.consultar_uno("SELECT * FROM subtareas WHERE id = ?", (identificador,))
        assert fila is not None
        fila["completada"] = bool(fila["completada"])
        return fila

    def alternar_subtarea(self, subtarea_id: int, completada: bool | None = None) -> dict[str, Any] | None:
        """Cambia el estado de una subtarea.

        Args:
            subtarea_id: Identificador de la subtarea.
            completada: Nuevo estado; si es ``None``, se invierte el actual.

        Returns:
            Subtarea actualizada o ``None`` si no existe.
        """

        fila = self.gestor.consultar_uno("SELECT * FROM subtareas WHERE id = ?", (subtarea_id,))
        if fila is None:
            return None
        nuevo_estado = (not bool(fila["completada"])) if completada is None else bool(completada)
        self.gestor.ejecutar(
            "UPDATE subtareas SET completada = ? WHERE id = ?", (int(nuevo_estado), subtarea_id)
        )
        actualizada = self.gestor.consultar_uno("SELECT * FROM subtareas WHERE id = ?", (subtarea_id,))
        assert actualizada is not None
        actualizada["completada"] = bool(actualizada["completada"])
        return actualizada

    def eliminar_subtarea(self, subtarea_id: int) -> bool:
        """Elimina una subtarea.

        Args:
            subtarea_id: Identificador de la subtarea.

        Returns:
            ``True`` si se borró.
        """

        with self.gestor.transaccion() as conexion:
            cursor = conexion.execute("DELETE FROM subtareas WHERE id = ?", (subtarea_id,))
            return cursor.rowcount > 0

    def subtareas_de(self, evento_id: int) -> list[dict[str, Any]]:
        """Lista las subtareas de un evento ordenadas.

        Args:
            evento_id: Evento propietario.

        Returns:
            Lista de subtareas.
        """

        filas = self.gestor.consultar_todos(
            "SELECT * FROM subtareas WHERE evento_id = ? ORDER BY orden, id", (evento_id,)
        )
        for fila in filas:
            fila["completada"] = bool(fila["completada"])
        return filas
