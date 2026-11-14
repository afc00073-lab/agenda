"""Datos de demostración para el primer arranque.

Una agenda vacía no permite apreciar el diseño ni probar el calendario, el
tablero o las analíticas. Este módulo siembra un curso ficticio completo
(asignaturas, clases de la semana, exámenes, entregas, tareas con subtareas,
evaluaciones y sesiones de estudio) **solo cuando la base de datos no contiene
asignaturas**, de modo que nunca sobrescribe datos reales.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from src.base_datos.conexion import GestorBaseDatos
from src.base_datos.repositorios.repositorio_asignaturas import RepositorioAsignaturas
from src.base_datos.repositorios.repositorio_evaluaciones import RepositorioEvaluaciones
from src.base_datos.repositorios.repositorio_eventos import RepositorioEventos
from src.base_datos.repositorios.repositorio_notificaciones import RepositorioNotificaciones
from src.base_datos.repositorios.repositorio_sesiones import RepositorioSesiones
from src.utilidades import a_iso, ahora


def _fecha_hora(base: Any, dias: int, hora: int, minuto: int = 0) -> str:
    """Construye una fecha ISO desplazada respecto a un instante base.

    Args:
        base: Instante de referencia (``datetime``).
        dias: Desplazamiento en días.
        hora: Hora del día.
        minuto: Minutos.

    Returns:
        Cadena ISO canónica de la aplicación.
    """

    momento = (base + timedelta(days=dias)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(hours=hora, minutes=minuto)
    return a_iso(momento)


def sembrar_demostracion(gestor: GestorBaseDatos, forzar: bool = False) -> bool:
    """Crea un curso de ejemplo si la base está vacía.

    Args:
        gestor: Gestor de base de datos migrado.
        forzar: Si es ``True``, siembra aunque ya existan asignaturas (útil en
            demostraciones; no se usa desde la interfaz).

    Returns:
        ``True`` si se insertaron datos, ``False`` si se respetó la base actual.
    """

    asignaturas = RepositorioAsignaturas(gestor)
    if asignaturas.contar() > 0 and not forzar:
        return False

    eventos = RepositorioEventos(gestor)
    evaluaciones = RepositorioEvaluaciones(gestor)
    sesiones = RepositorioSesiones(gestor)
    notificaciones = RepositorioNotificaciones(gestor)
    base = ahora()
    lunes = base - timedelta(days=base.weekday())

    # ------------------------------------------------------------------
    # Asignaturas del semestre
    # ------------------------------------------------------------------
    datos_asignaturas = [
        {
            "nombre": "Estructuras de Datos",
            "codigo": "ED-2026",
            "color": "#7c6cff",
            "profesor": "Dra. Elena Ruiz",
            "aula": "Laboratorio A3.2",
            "creditos": 6.0,
            "enlaces": [
                {"titulo": "Moodle de la asignatura", "url": "https://moodle.ujaen.es"},
                {"titulo": "Repositorio de prácticas", "url": "https://github.com"},
            ],
        },
        {
            "nombre": "Sistemas Operativos",
            "codigo": "SO-2026",
            "color": "#28c8a0",
            "profesor": "Dr. Manuel Ortega",
            "aula": "Aula B1.4",
            "creditos": 6.0,
            "enlaces": [{"titulo": "Apuntes de procesos", "url": "https://moodle.ujaen.es"}],
        },
        {
            "nombre": "Bases de Datos",
            "codigo": "BD-2026",
            "color": "#ff7a59",
            "profesor": "Dra. Lucía Márquez",
            "aula": "Laboratorio C2.1",
            "creditos": 6.0,
            "enlaces": [{"titulo": "Guion de SQL", "url": "https://sqlite.org"}],
        },
        {
            "nombre": "Redes de Computadores",
            "codigo": "RC-2026",
            "color": "#4aa8ff",
            "profesor": "Dr. Javier Peña",
            "aula": "Laboratorio de redes",
            "creditos": 6.0,
            "enlaces": [{"titulo": "Wireshark", "url": "https://wireshark.org"}],
        },
        {
            "nombre": "Ingeniería del Software",
            "codigo": "IS-2026",
            "color": "#ff5c8a",
            "profesor": "Dra. Carmen Vidal",
            "aula": "Aula A2.3",
            "creditos": 6.0,
            "enlaces": [{"titulo": "Tablero del equipo", "url": "https://github.com"}],
        },
        {
            "nombre": "Estadística",
            "codigo": "ES-2026",
            "color": "#ffc857",
            "profesor": "Dr. Andrés Molina",
            "aula": "Aula B3.1",
            "creditos": 6.0,
            "enlaces": [],
        },
    ]
    creadas = [asignaturas.crear(**datos) for datos in datos_asignaturas]
    por_nombre = {asignatura["nombre"]: asignatura for asignatura in creadas}

    # ------------------------------------------------------------------
    # Horario semanal (dos clases por día laborable)
    # ------------------------------------------------------------------
    horario = [
        (0, 9, 0, 11, 0, "Estructuras de Datos", "Laboratorio A3.2"),
        (0, 12, 0, 13, 30, "Estadística", "Aula B3.1"),
        (1, 9, 0, 11, 0, "Sistemas Operativos", "Aula B1.4"),
        (1, 16, 0, 18, 0, "Bases de Datos", "Laboratorio C2.1"),
        (2, 10, 0, 12, 0, "Redes de Computadores", "Laboratorio de redes"),
        (2, 12, 30, 14, 0, "Ingeniería del Software", "Aula A2.3"),
        (3, 9, 0, 11, 0, "Bases de Datos", "Laboratorio C2.1"),
        (3, 15, 0, 17, 0, "Estructuras de Datos", "Laboratorio A3.2"),
        (4, 9, 0, 10, 30, "Ingeniería del Software", "Aula A2.3"),
        (4, 11, 0, 13, 0, "Sistemas Operativos", "Aula B1.4"),
    ]
    for dia, hora_inicio, minuto_inicio, hora_fin, minuto_fin, nombre, aula in horario:
        asignatura = por_nombre[nombre]
        eventos.crear(
            titulo=f"Clase · {nombre}",
            tipo="clase",
            fecha_inicio=a_iso(
                (lunes + timedelta(days=dia)).replace(hour=hora_inicio, minute=minuto_inicio)
            ),
            fecha_fin=a_iso((lunes + timedelta(days=dia)).replace(hour=hora_fin, minute=minuto_fin)),
            asignatura_id=asignatura["id"],
            ubicacion=aula,
            recordatorios=[60],
            descripcion="Sesión presencial del horario semanal.",
        )

    # ------------------------------------------------------------------
    # Hitos próximos: exámenes y entregas
    # ------------------------------------------------------------------
    hitos = [
        {
            "titulo": "Examen parcial de Estructuras de Datos",
            "tipo": "examen",
            "asignatura": "Estructuras de Datos",
            "dias": 6,
            "hora": 9,
            "prioridad": "critica",
            "descripcion": "Temas 1 a 5: listas, pilas, colas y árboles binarios.",
            "ubicacion": "Aula de exámenes 1",
        },
        {
            "titulo": "Entrega · Práctica 3 de Bases de Datos",
            "tipo": "entrega",
            "asignatura": "Bases de Datos",
            "dias": 3,
            "hora": 23,
            "prioridad": "alta",
            "descripcion": "Índices B+ y optimización de consultas en SQLite.",
            "ubicacion": "Moodle",
        },
        {
            "titulo": "Examen de Sistemas Operativos",
            "tipo": "examen",
            "asignatura": "Sistemas Operativos",
            "dias": 13,
            "hora": 10,
            "prioridad": "alta",
            "descripcion": "Planificación de procesos, memoria virtual y sistemas de archivos.",
            "ubicacion": "Aula de exámenes 2",
        },
        {
            "titulo": "Entrega · Proyecto de Ingeniería del Software",
            "tipo": "entrega",
            "asignatura": "Ingeniería del Software",
            "dias": 9,
            "hora": 20,
            "prioridad": "alta",
            "descripcion": "Sprint 2: historias de usuario, pruebas y despliegue.",
            "ubicacion": "GitHub Classroom",
        },
        {
            "titulo": "Examen de Estadística",
            "tipo": "examen",
            "asignatura": "Estadística",
            "dias": 20,
            "hora": 9,
            "prioridad": "media",
            "descripcion": "Distribuciones, intervalos de confianza y contrastes.",
            "ubicacion": "Aula B3.1",
        },
    ]
    for hito in hitos:
        eventos.crear(
            titulo=hito["titulo"],
            tipo=hito["tipo"],
            fecha_inicio=_fecha_hora(base, hito["dias"], hito["hora"]),
            fecha_fin=_fecha_hora(base, hito["dias"], hito["hora"] + 2),
            asignatura_id=por_nombre[hito["asignatura"]]["id"],
            prioridad=hito["prioridad"],
            descripcion=hito["descripcion"],
            ubicacion=hito["ubicacion"],
            recordatorios=[1440, 120, 15],
        )

    # ------------------------------------------------------------------
    # Tablero Kanban con subtareas
    # ------------------------------------------------------------------
    tareas = [
        {
            "titulo": "Práctica 3 · Índices B+",
            "asignatura": "Bases de Datos",
            "columna": "en_desarrollo",
            "prioridad": "alta",
            "dias": 3,
            "subtareas": [("Modelo relacional", True), ("Consultas base", True), ("Índices y planes", False), ("Memoria final", False)],
        },
        {
            "titulo": "Proyecto · Sprint 2",
            "asignatura": "Ingeniería del Software",
            "columna": "en_desarrollo",
            "prioridad": "critica",
            "dias": 9,
            "subtareas": [("Historias de usuario", True), ("API REST", False), ("Pruebas de integración", False), ("Despliegue", False)],
        },
        {
            "titulo": "Hoja de ejercicios de árboles AVL",
            "asignatura": "Estructuras de Datos",
            "columna": "revision",
            "prioridad": "media",
            "dias": 2,
            "subtareas": [("Rotaciones simples", True), ("Rotaciones dobles", True), ("Ejercicios 7-12", False)],
        },
        {
            "titulo": "Informe de laboratorio de redes",
            "asignatura": "Redes de Computadores",
            "columna": "pendiente",
            "prioridad": "media",
            "dias": 7,
            "subtareas": [("Capturas Wireshark", False), ("Análisis TCP", False), ("Conclusiones", False)],
        },
        {
            "titulo": "Resumen de planificación de procesos",
            "asignatura": "Sistemas Operativos",
            "columna": "entregado",
            "prioridad": "baja",
            "dias": -1,
            "subtareas": [("Round Robin", True), ("SJF", True), ("Comparativa", True)],
        },
        {
            "titulo": "Ejercicios de intervalos de confianza",
            "asignatura": "Estadística",
            "columna": "pendiente",
            "prioridad": "baja",
            "dias": 5,
            "subtareas": [("Ejercicios 1-5", False), ("Autoevaluación", False)],
        },
    ]
    for tarea in tareas:
        evento = eventos.crear(
            titulo=tarea["titulo"],
            tipo="tarea",
            fecha_inicio=_fecha_hora(base, tarea["dias"], 18),
            fecha_fin=_fecha_hora(base, tarea["dias"], 20),
            asignatura_id=por_nombre[tarea["asignatura"]]["id"],
            prioridad=tarea["prioridad"],
            estado_kanban=tarea["columna"],
            descripcion="Trabajo práctico del curso de ejemplo.",
            recordatorios=[120],
        )
        for titulo_subtarea, completada in tarea["subtareas"]:
            subtarea = eventos.crear_subtarea(evento["id"], titulo_subtarea)
            if completada:
                eventos.alternar_subtarea(subtarea["id"], True)

    # ------------------------------------------------------------------
    # Evaluaciones y notas
    # ------------------------------------------------------------------
    plan_evaluacion = {
        "Estructuras de Datos": [("Prácticas de laboratorio", "practica", 30, 8.4, 3), ("Examen parcial", "examen", 30, 7.2, 6), ("Examen final", "examen", 40, None, 24)],
        "Sistemas Operativos": [("Prácticas", "practica", 40, 8.9, 4), ("Examen final", "examen", 60, None, 13)],
        "Bases de Datos": [("Práctica 1", "practica", 15, 9.1, -8), ("Práctica 2", "practica", 15, 8.2, -2), ("Examen final", "examen", 70, None, 18)],
        "Redes de Computadores": [("Laboratorio", "practica", 35, 7.5, 0), ("Examen final", "examen", 65, None, 21)],
        "Ingeniería del Software": [("Sprint 1", "proyecto", 25, 8.8, -12), ("Sprint 2", "proyecto", 25, None, 9), ("Examen", "examen", 50, None, 19)],
        "Estadística": [("Tareas", "participacion", 20, 6.5, -5), ("Examen final", "examen", 80, None, 20)],
    }
    for nombre_asignatura, pruebas in plan_evaluacion.items():
        for titulo, tipo, peso, nota, dias in pruebas:
            evaluaciones.crear(
                asignatura_id=por_nombre[nombre_asignatura]["id"],
                nombre=titulo,
                tipo=tipo,
                peso=peso,
                nota=nota,
                fecha=_fecha_hora(base, dias, 9) if dias is not None else "",
            )

    # ------------------------------------------------------------------
    # Historial de estudio para las gráficas
    # ------------------------------------------------------------------
    duraciones = [50, 25, 75, 45, 100, 25, 50, 90, 30, 60, 25, 80, 50, 45]
    for indice, minutos in enumerate(duraciones):
        dia = base - timedelta(days=indice % 12)
        asignatura = creadas[indice % len(creadas)]
        inicio = a_iso((dia - timedelta(days=0)).replace(hour=17, minute=30))
        fin = a_iso((dia).replace(hour=17, minute=30) + timedelta(minutes=minutos))
        sesiones.registrar(
            inicio=inicio,
            fin=fin,
            duracion_minutos=minutos,
            asignatura_id=asignatura["id"],
            modo="50/10" if minutos >= 50 else "25/5",
            notas="Sesión de ejemplo",
        )

    # ------------------------------------------------------------------
    # Historial de la campana de notificaciones
    # ------------------------------------------------------------------
    avisos = [
        ("Próximo examen", "Estructuras de Datos · en 6 días", 1, 0),
        ("Entrega cercana", "Práctica 3 de Bases de Datos · en 3 días", 1, 1),
        ("Resumen matutino", "Hoy tienes 2 clases y una entrega próxima", 1, 0),
    ]
    for indice, (titulo, mensaje, vista, dias_atras) in enumerate(avisos):
        aviso = notificaciones.crear(
            titulo=titulo,
            mensaje=mensaje,
            programada_para=_fecha_hora(base, -dias_atras, 8 + indice),
        )
        if aviso:
            notificaciones.marcar_enviada(aviso["id"])
            if vista:
                notificaciones.marcar_vista(aviso["id"], True)

    return True
