/**
 * ============================================================================
 *  VISTA CALENDARIO · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Ofrece dos lecturas complementarias de la misma base de datos:
 *
 *  * **Semana**: rejilla horaria con las clases y entregas situadas en su hora,
 *    línea del instante actual, detección de solapamientos en columnas y
 *    arrastre con el ratón para reprogramar un evento.
 *  * **Mes**: panorama de seis semanas con chips compactos por día.
 *
 *  Al pulsar un evento se abre un panel lateral con todos sus datos, sus
 *  subtareas y acciones para completarlo, editarlo o eliminarlo.
 *
 *  No se registra ningún atajo de teclado: se usa el ratón de principio a fin.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const {
        escapar, icono, claveFecha, horaCorta, fechaCorta, fechaLarga,
        hoyIso, dosDigitos, limitar, COLORES_PRIORIDAD
    } = U;

    const HORA_INICIO = 7;
    const HORA_FIN = 23;
    const ALTO_HORA = 64;
    const PX_POR_MINUTO = ALTO_HORA / 60;

    const ESTADO = {
        modo: "semana",
        cursor: new Date(),
        eventos: [],
        filtro: "",
        raiz: null,
        contexto: null,
        cargando: false,
        inicializado: false,
        arrastre: null,
        intervalo: null,
        panel: null,
        eventoPendiente: null
    };

    /* ------------------------------------------------------------------
       Fechas y horas
       ------------------------------------------------------------------ */
    /** @param {Date} fecha Fecha. @returns {string} Clave `AAAA-MM-DD`. */
    const isoDia = (fecha) => claveFecha(fecha);

    /** @param {Date} fecha Fecha. @returns {string} Inicio del día ISO. */
    const isoInicio = (fecha) => `${claveFecha(fecha)}T00:00`;

    /** @param {Date} fecha Fecha. @returns {string} Fin del día ISO. */
    const isoFin = (fecha) => `${claveFecha(fecha)}T23:59`;

    /** @param {Date} fecha Fecha base. @param {number} dias Desplazamiento. */
    function sumarDias(fecha, dias) {
        const copia = new Date(fecha);
        copia.setDate(copia.getDate() + dias);
        return copia;
    }

    /** @param {string} iso Fecha ISO. @returns {number} Minutos desde medianoche. */
    function minutosDelDia(iso) {
        if (!iso || iso.length < 16) {
            return 0;
        }
        return Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));
    }

    /** @param {Date} fecha Fecha. @returns {string} Texto del mes y año. */
    function tituloMes(fecha) {
        const texto = new Intl.DateTimeFormat("es-ES", { month: "long", year: "numeric" }).format(fecha);
        return texto.charAt(0).toUpperCase() + texto.slice(1);
    }

    /** @returns {{desde: string, hasta: string, dias: Date[]}} Rango visible. */
    function rangoVisible() {
        if (ESTADO.modo === "mes") {
            const primero = new Date(ESTADO.cursor.getFullYear(), ESTADO.cursor.getMonth(), 1);
            const inicio = U.lunesDe(primero);
            const dias = Array.from({ length: 42 }, (_, indice) => sumarDias(inicio, indice));
            return { desde: isoInicio(dias[0]), hasta: isoFin(dias[dias.length - 1]), dias };
        }
        const inicio = U.lunesDe(ESTADO.cursor);
        const dias = Array.from({ length: 7 }, (_, indice) => sumarDias(inicio, indice));
        return { desde: isoInicio(dias[0]), hasta: isoFin(dias[6]), dias };
    }

    /** @returns {string} Rango de fechas legible para la barra de herramientas. */
    function tituloRango(dias) {
        if (ESTADO.modo === "mes") {
            return tituloMes(ESTADO.cursor);
        }
        const inicio = dias[0];
        const fin = dias[6];
        const mismoMes = inicio.getMonth() === fin.getMonth();
        const formatoInicio = new Intl.DateTimeFormat("es-ES", {
            day: "numeric",
            month: mismoMes ? undefined : "short"
        }).format(inicio);
        const formatoFin = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" }).format(fin);
        return `${formatoInicio} – ${formatoFin} de ${fin.getFullYear()}`;
    }

    /* ------------------------------------------------------------------
       Datos
       ------------------------------------------------------------------ */
    /** Descarga los eventos del rango visible. */
    async function cargarEventos() {
        const { desde, hasta } = rangoVisible();
        ESTADO.eventos = await global.PuenteAgenda.obtener("listar_eventos", desde, hasta);
    }

    /** Aplica el filtro de asignatura activo. */
    function eventosFiltrados() {
        if (!ESTADO.filtro) {
            return ESTADO.eventos;
        }
        return ESTADO.eventos.filter(
            (evento) => String(evento.asignatura_id || "") === String(ESTADO.filtro)
        );
    }

    /**
     * Agrupa los eventos por día.
     * @param {object[]} eventos Lista filtrada.
     * @returns {Record<string, object[]>} Eventos indexados por `AAAA-MM-DD`.
     */
    function agruparPorDia(eventos) {
        const mapa = {};
        eventos.forEach((evento) => {
            const clave = (evento.fecha_inicio || "").slice(0, 10);
            if (!clave) {
                return;
            }
            mapa[clave] = mapa[clave] || [];
            mapa[clave].push(evento);
        });
        return mapa;
    }

    /**
     * Calcula columnas para eventos que se solapan en el mismo día.
     * @param {object[]} eventos Eventos de un día.
     * @returns {Map<number, {columna: number, total: number}>} Distribución.
     */
    function calcularSolapamientos(eventos) {
        const ordenados = eventos
            .slice()
            .sort((a, b) => minutosDelDia(a.fecha_inicio) - minutosDelDia(b.fecha_inicio));
        const distribucion = new Map();
        let grupo = [];
        let finGrupo = -1;

        const cerrarGrupo = () => {
            if (!grupo.length) {
                return;
            }
            const finales = [];
            grupo.forEach((elemento) => {
                let columna = finales.findIndex((fin) => fin <= elemento.inicio);
                if (columna === -1) {
                    columna = finales.length;
                    finales.push(elemento.fin);
                } else {
                    finales[columna] = elemento.fin;
                }
                elemento.columna = columna;
            });
            grupo.forEach((elemento) => {
                distribucion.set(elemento.evento.id, {
                    columna: elemento.columna,
                    total: finales.length
                });
            });
            grupo = [];
            finGrupo = -1;
        };

        ordenados.forEach((evento) => {
            const inicio = minutosDelDia(evento.fecha_inicio);
            const fin = Math.max(
                inicio + 30,
                Math.min(minutosDelDia(evento.fecha_fin) || inicio + 60, HORA_FIN * 60)
            );
            if (grupo.length && inicio >= finGrupo) {
                cerrarGrupo();
            }
            grupo.push({ evento, inicio, fin });
            finGrupo = Math.max(finGrupo, fin);
        });
        cerrarGrupo();
        return distribucion;
    }

    /* ------------------------------------------------------------------
       Plantillas
       ------------------------------------------------------------------ */
    /**
     * Construye un bloque de evento dentro de la rejilla semanal.
     * @param {object} evento Evento.
     * @param {{columna: number, total: number}} posicion Distribución.
     * @returns {string} HTML del bloque.
     */
    function bloqueEvento(evento, posicion) {
        const inicio = minutosDelDia(evento.fecha_inicio);
        const fin = Math.max(inicio + 30, minutosDelDia(evento.fecha_fin) || inicio + 60);
        const top = (limitM(inicio) - HORA_INICIO * 60) * PX_POR_MINUTO;
        const alto = Math.max(24, (limitM(fin) - limitM(inicio)) * PX_POR_MINUTO - 3);
        const ancho = 100 / posicion.total;
        const izquierda = posicion.columna * ancho;
        const color = evento.asignatura_color || U.colorDesdeTexto(evento.titulo);
        const completado = evento.completado ? " completado" : "";
        const hora = horaCorta(evento.fecha_inicio);
        return `
            <article class="calendario-evento${completado}" draggable="true"
                     data-evento="${Number(evento.id)}"
                     style="top:${top}px;height:${alto}px;left:calc(${izquierda}% + 2px);width:calc(${ancho}% - 4px);--color-evento:${color}"
                     title="${escapar(evento.titulo)} · ${escapar(hora)} · ${escapar(U.etiquetaTipo(evento.tipo))}">
                <span class="calendario-evento__hora">${escapar(hora)}</span>
                <span class="calendario-evento__titulo">${escapar(evento.titulo)}</span>
                ${evento.ubicacion && alto > 42 ? `<span class="calendario-evento__lugar">${escapar(evento.ubicacion)}</span>` : ""}
            </article>`;
    }

    /** Limita un minuto al rango visible de la rejilla. */
    function limitM(minuto) {
        return limitar(minuto, HORA_INICIO * 60, HORA_FIN * 60);
    }

    /**
     * Construye una columna diaria de la vista semanal.
     * @param {Date} dia Día representado.
     * @param {object[]} eventos Eventos del día.
     * @returns {string} HTML de la columna.
     */
    function columnaDia(dia, eventos) {
        const clave = isoDia(dia);
        const conHora = eventos.filter((evento) => !evento.todo_el_dia);
        const distribucion = calcularSolapamientos(conHora);
        const esHoy = clave === hoyIso();
        const lineas = conHora
            .map((evento) =>
                bloqueEvento(
                    evento,
                    distribucion.get(evento.id) || { columna: 0, total: 1 }
                )
            )
            .join("");
        return `
            <div class="calendario-dia ${esHoy ? "hoy" : ""}" data-fecha="${clave}">
                ${lineas}
                ${esHoy ? '<span class="calendario-ahora" data-ahora><span class="calendario-ahora__punto"></span></span>' : ""}
                <span class="calendario-guia oculto"><span class="calendario-guia__etiqueta"></span></span>
            </div>`;
    }

    /**
     * Construye la fila de eventos de día completo.
     * @param {Date[]} dias Días de la semana.
     * @param {object[]} eventos Eventos visibles.
     * @returns {string} HTML de la fila.
     */
    function filaTodoElDia(dias, eventos) {
        const porDia = agruparPorDia(eventos.filter((evento) => evento.todo_el_dia));
        return `
            <div class="calendario-todoeldia">
                <span class="calendario-todoeldia__etiqueta">Todo el día</span>
                <div class="calendario-todoeldia__dias">
                    ${dias.map((dia) => {
                        const lista = porDia[isoDia(dia)] || [];
                        return `<div class="calendario-todoeldia__dia">
                            ${lista.map((evento) => `
                                <button class="calendario-chip" type="button" data-evento="${Number(evento.id)}"
                                        style="--color-evento:${evento.asignatura_color || "var(--acento)"}">
                                    ${escapar(evento.titulo)}
                                </button>`).join("")}
                        </div>`;
                    }).join("")}
                </div>
            </div>`;
    }

    /**
     * Construye la rejilla semanal completa.
     * @param {Date[]} dias Días visibles.
     * @param {object[]} eventos Eventos filtrados.
     * @returns {string} HTML de la semana.
     */
    function vistaSemana(dias, eventos) {
        const porDia = agruparPorDia(eventos.filter((evento) => !evento.todo_el_dia));
        const horas = [];
        for (let hora = HORA_INICIO; hora <= HORA_FIN; hora += 1) {
            const top = (hora - HORA_INICIO) * ALTO_HORA;
            horas.push(`<span class="calendario-horas__marca" style="top:${top}px">${dosDigitos(hora)}:00</span>`);
        }
        return `
            <div class="calendario-cabecera-semana">
                <span class="calendario-cabecera-semana__zona">Hora</span>
                <div class="calendario-cabecera-semana__dias">
                    ${dias.map((dia) => {
                        const clave = isoDia(dia);
                        const esHoy = clave === hoyIso();
                        const nombre = new Intl.DateTimeFormat("es-ES", { weekday: "short" }).format(dia);
                        return `
                            <button class="calendario-dia-cabecera ${esHoy ? "hoy" : ""}" type="button"
                                    data-ir-dia="${clave}">
                                <span class="calendario-dia-cabecera__nombre">${escapar(nombre.replace(".", ""))}</span>
                                <span class="calendario-dia-cabecera__numero">${dia.getDate()}</span>
                            </button>`;
                    }).join("")}
                </div>
            </div>
            ${filaTodoElDia(dias, eventos)}
            <div class="calendario-cuerpo">
                <div class="calendario-horas">
                    ${horas.join("")}
                </div>
                <div class="calendario-columnas">
                    ${dias.map((dia) => columnaDia(dia, porDia[isoDia(dia)] || [])).join("")}
                </div>
            </div>`;
    }

    /**
     * Construye la vista mensual de seis semanas.
     * @param {Date[]} dias Días visibles.
     * @param {object[]} eventos Eventos filtrados.
     * @returns {string} HTML del mes.
     */
    function vistaMes(dias, eventos) {
        const porDia = agruparPorDia(eventos);
        const mesActual = ESTADO.cursor.getMonth();
        const nombres = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
        return `
            <div class="calendario-mes">
                <div class="calendario-mes__cabecera">
                    ${nombres.map((nombre) => `<span>${nombre}</span>`).join("")}
                </div>
                <div class="calendario-mes__rejilla">
                    ${dias.map((dia) => {
                        const clave = isoDia(dia);
                        const lista = porDia[clave] || [];
                        const otroMes = dia.getMonth() !== mesActual;
                        const esHoy = clave === hoyIso();
                        const visibles = lista.slice(0, 3);
                        return `
                            <div class="calendario-mes__celda ${otroMes ? "otro-mes" : ""} ${esHoy ? "hoy" : ""}"
                                 data-dia="${clave}">
                                <div class="calendario-mes__numero-fila">
                                    <button class="calendario-mes__numero" type="button" data-ir-dia="${clave}">
                                        ${dia.getDate()}
                                    </button>
                                    ${lista.length > 3 ? `<span class="calendario-mes__total">${lista.length} eventos</span>` : ""}
                                </div>
                                <div class="calendario-mes__eventos">
                                    ${visibles.map((evento) => `
                                        <button class="calendario-chip calendario-chip--mes" type="button"
                                                data-evento="${Number(evento.id)}"
                                                style="--color-evento:${evento.asignatura_color || "var(--acento)"}">
                                            <span class="calendario-chip__hora">${escapar(horaCorta(evento.fecha_inicio))}</span>
                                            <span class="calendario-chip__texto">${escapar(evento.titulo)}</span>
                                        </button>`).join("")}
                                    ${lista.length > 3 ? `<button class="calendario-mes__mas" type="button" data-ir-dia="${clave}">
                                        +${lista.length - 3} más
                                    </button>` : ""}
                                </div>
                            </div>`;
                    }).join("")}
                </div>
            </div>`;
    }

    /**
     * Genera la barra de herramientas del calendario.
     * @param {Date[]} dias Días visibles.
     * @returns {string} HTML de la barra.
     */
    function barraHerramientas(dias) {
        const asignaturas = ESTADO.contexto.asignaturas || [];
        return `
            <div class="calendario-barra">
                <div class="segmentado" role="group" aria-label="Cambiar entre semana y mes">
                    <button class="segmentado__opcion ${ESTADO.modo === "semana" ? "activo" : ""}"
                            type="button" data-modo="semana">Semana</button>
                    <button class="segmentado__opcion ${ESTADO.modo === "mes" ? "activo" : ""}"
                            type="button" data-modo="mes">Mes</button>
                </div>

                <div class="calendario-navegacion">
                    <button class="boton-icono" type="button" data-nav="anterior" aria-label="Periodo anterior"
                            data-tooltip="Anterior">${icono("chevronIzquierda")}</button>
                    <p class="calendario-titulo">${escapar(tituloRango(dias))}</p>
                    <button class="boton-icono" type="button" data-nav="siguiente" aria-label="Periodo siguiente"
                            data-tooltip="Siguiente">${icono("chevronDerecha")}</button>
                    <button class="boton boton--fantasma boton--pequeno" type="button" data-nav="hoy">Hoy</button>
                </div>

                <div class="calendario-barra__acciones">
                    <label class="campo campo--filtro" for="filtro-asignatura">
                        <span class="solo-lectores">Filtrar por asignatura</span>
                        <select class="campo__control campo__control--compacto" id="filtro-asignatura">
                            <option value="">Todas las asignaturas</option>
                            ${asignaturas.map((asignatura) => `
                                <option value="${asignatura.id}" ${String(asignatura.id) === String(ESTADO.filtro) ? "selected" : ""}>
                                    ${escapar(asignatura.nombre)}
                                </option>`).join("")}
                        </select>
                    </label>
                    <button class="boton boton--primario boton--pequeno" type="button" data-accion="nuevo-evento">
                        ${icono("mas")} Nuevo evento
                    </button>
                </div>
            </div>`;
    }

    /** Genera el esqueleto completo de la vista. */
    function plantilla() {
        const { dias } = rangoVisible();
        const eventos = eventosFiltrados();
        return `
            ${barraHerramientas(dias)}
            ${ESTADO.cargando
                ? `<div class="calendario-cargando"><span class="cargando__rueda"></span> Cargando eventos…</div>`
                : ESTADO.modo === "mes" ? vistaMes(dias, eventos) : vistaSemana(dias, eventos)}
            <p class="calendario-leyenda">
                ${icono("informacion")} Arrastra un bloque para cambiarlo de hora o de día.
                Pulsa un evento para ver su ficha completa.
            </p>`;
    }

    /* ------------------------------------------------------------------
       Panel lateral de detalle
       ------------------------------------------------------------------ */
    /**
     * Abre el panel lateral con la ficha de un evento.
     * @param {number} identificador Identificador del evento.
     */
    async function abrirDetalle(identificador) {
        cerrarDetalle();
        let evento;
        try {
            evento = await global.PuenteAgenda.obtener("obtener_evento", identificador);
        } catch (error) {
            ESTADO.contexto.toast("No se pudo abrir el evento", String(error.message || error), "error");
            return;
        }
        if (!evento) {
            return;
        }

        const color = evento.asignatura_color || "var(--acento)";
        const fondo = document.createElement("div");
        fondo.className = "panel-lateral__fondo";
        fondo.dataset.cerrarPanel = "1";

        const panel = document.createElement("aside");
        panel.className = "panel-lateral";
        panel.id = "panel-evento";
        panel.style.setProperty("--color-evento", color);
        panel.innerHTML = `
            <header class="panel-lateral__cabecera">
                <span class="panel-evento__icono" style="--color-evento:${color}">
                    ${icono(evento.tipo === "examen" ? "nota" : evento.tipo === "entrega" ? "subir" : evento.tipo === "tarea" ? "check" : "libro")}
                </span>
                <div style="min-width:0;flex:1">
                    <p class="panel-evento__tipo">${escapar(U.etiquetaTipo(evento.tipo))}</p>
                    <h2 class="panel-evento__titulo">${escapar(evento.titulo)}</h2>
                    <p class="panel-evento__materia">${escapar(evento.asignatura_nombre || "Sin asignatura")}</p>
                </div>
                <button class="modal__cerrar" type="button" data-cerrar-panel aria-label="Cerrar detalle">
                    ${icono("x")}
                </button>
            </header>
            <div class="panel-lateral__cuerpo">
                <div class="panel-evento__datos">
                    <div class="panel-dato">
                        <span class="panel-dato__etiqueta">${icono("calendario")} Fecha</span>
                        <span class="panel-dato__valor">${escapar(fechaLarga(evento.fecha_inicio))}</span>
                    </div>
                    <div class="panel-dato">
                        <span class="panel-dato__etiqueta">${icono("reloj")} Horario</span>
                        <span class="panel-dato__valor">
                            ${escapar(horaCorta(evento.fecha_inicio))}
                            ${horaCorta(evento.fecha_fin) && horaCorta(evento.fecha_fin) !== horaCorta(evento.fecha_inicio)
                                ? `– ${escapar(horaCorta(evento.fecha_fin))}` : ""}
                        </span>
                    </div>
                    <div class="panel-dato">
                        <span class="panel-dato__etiqueta">${icono("alerta")} Prioridad</span>
                        <span class="panel-dato__valor">
                            <span class="etiqueta ${evento.prioridad === "critica" ? "etiqueta--critica" : `etiqueta--${evento.prioridad || "media"}`}">
                                ${escapar(U.etiquetaPrioridad(evento.prioridad))}
                            </span>
                        </span>
                    </div>
                    ${evento.ubicacion ? `
                        <div class="panel-dato">
                            <span class="panel-dato__etiqueta">${icono("ubicacion")} Lugar</span>
                            <span class="panel-dato__valor">${escapar(evento.ubicacion)}</span>
                        </div>` : ""}
                    ${evento.origen === "ics" ? `
                        <div class="panel-dato">
                            <span class="panel-dato__etiqueta">${icono("sincronizar")} Origen</span>
                            <span class="panel-dato__valor">Suscripción iCalendar</span>
                        </div>` : ""}
                </div>

                ${evento.descripcion ? `
                    <div class="panel-evento__bloque">
                        <h3 class="panel-evento__subtitulo">${icono("nota")} Descripción</h3>
                        <p class="panel-evento__texto">${escapar(evento.descripcion)}</p>
                    </div>` : ""}

                ${evento.subtareas?.length ? `
                    <div class="panel-evento__bloque">
                        <h3 class="panel-evento__subtitulo">
                            ${icono("check")} Subtareas
                            <span class="texto-tenue">${evento.subtareas_completadas}/${evento.total_subtareas}</span>
                        </h3>
                        <div class="panel-subtareas">
                            ${evento.subtareas.map((subtarea) => `
                                <button class="panel-subtarea ${subtarea.completada ? "completada" : ""}"
                                        type="button" data-subtarea="${Number(subtarea.id)}"
                                        data-estado="${subtarea.completada ? "1" : "0"}">
                                    <span class="marca-verificacion ${subtarea.completada ? "activa" : ""}">${icono("check")}</span>
                                    <span class="panel-subtarea__texto">${escapar(subtarea.titulo)}</span>
                                </button>`).join("")}
                        </div>
                    </div>` : ""}
            </div>
            <footer class="panel-lateral__pie">
                <button class="boton boton--primario boton--pequeno" type="button" data-completar-evento>
                    ${icono(evento.completado ? "reiniciar" : "check")}
                    ${evento.completado ? "Reabrir" : "Completar"}
                </button>
                <button class="boton boton--fantasma boton--pequeno" type="button" data-editar-evento>
                    ${icono("editar")} Editar
                </button>
                <button class="boton boton--peligro boton--pequeno" type="button" data-eliminar-evento>
                    ${icono("basura")} Eliminar
                </button>
            </footer>`;

        document.body.append(fondo, panel);
        ESTADO.panel = { panel, fondo };
        global.requestAnimationFrame(() => {
            panel.classList.add("abierto");
            fondo.classList.add("visible");
        });

        fondo.addEventListener("click", cerrarDetalle);
        panel.querySelector("[data-cerrar-panel]").addEventListener("click", cerrarDetalle);

        panel.querySelector("[data-completar-evento]").addEventListener("click", async () => {
            try {
                await global.PuenteAgenda.obtener(
                    "completar_evento", evento.id, !evento.completado
                );
                ESTADO.contexto.toast(
                    evento.completado ? "Evento reabierto" : "Evento completado",
                    evento.titulo,
                    evento.completado ? "info" : "exito",
                    2800
                );
                cerrarDetalle();
                await recargar();
            } catch (error) {
                ESTADO.contexto.toast("No se pudo actualizar", String(error.message || error), "error");
            }
        });

        panel.querySelector("[data-editar-evento]").addEventListener("click", () => {
            cerrarDetalle();
            ESTADO.contexto.abrirModal("evento", {
                ...evento,
                fecha: (evento.fecha_inicio || "").slice(0, 10),
                hora: (evento.fecha_inicio || "").slice(11, 16),
                fecha_fin: (evento.fecha_fin || "").slice(0, 10),
                hora_fin: (evento.fecha_fin || "").slice(11, 16)
            });
        });

        const botonEliminar = panel.querySelector("[data-eliminar-evento]");
        botonEliminar.addEventListener("click", async () => {
            if (botonEliminar.dataset.confirmar !== "1") {
                botonEliminar.dataset.confirmar = "1";
                botonEliminar.innerHTML = `${icono("alerta")} Confirmar eliminación`;
                global.setTimeout(() => {
                    if (botonEliminar.isConnected) {
                        botonEliminar.dataset.confirmar = "0";
                        botonEliminar.innerHTML = `${icono("basura")} Eliminar`;
                    }
                }, 3200);
                return;
            }
            try {
                await global.PuenteAgenda.obtener("eliminar_evento", evento.id);
                ESTADO.contexto.toast("Evento eliminado", evento.titulo, "info", 2800);
                cerrarDetalle();
                await recargar();
            } catch (error) {
                ESTADO.contexto.toast("No se pudo eliminar", String(error.message || error), "error");
            }
        });

        panel.querySelectorAll("[data-subtarea]").forEach((boton) => {
            boton.addEventListener("click", async () => {
                const identificadorSubtarea = Number(boton.dataset.subtarea);
                const completada = boton.dataset.estado === "1";
                try {
                    await global.PuenteAgenda.obtener(
                        "alternar_subtarea", identificadorSubtarea, !completada
                    );
                    cerrarDetalle();
                    await abrirDetalle(evento.id);
                    await recargar(true);
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo actualizar la subtarea", String(error.message || error), "error");
                }
            });
        });
    }

    /** Cierra el panel lateral si está abierto. */
    function cerrarDetalle() {
        if (!ESTADO.panel) {
            return;
        }
        const { panel, fondo } = ESTADO.panel;
        ESTADO.panel = null;
        panel.classList.remove("abierto");
        fondo.classList.remove("visible");
        global.setTimeout(() => {
            panel.remove();
            fondo.remove();
        }, 420);
    }

    /* ------------------------------------------------------------------
       Interacción
       ------------------------------------------------------------------ */
    /**
     * Calcula el minuto de la rejilla a partir de la posición del ratón.
     * @param {MouseEvent} evento Evento del navegador.
     * @param {HTMLElement} columna Columna diaria.
     * @returns {number} Minutos desde medianoche, ajustados a 15.
     */
    function minutoDesdeRaton(evento, columna) {
        const rect = columna.getBoundingClientRect();
        const y = limitar(evento.clientY - rect.top, 0, rect.height);
        const minutos = HORA_INICIO * 60 + y / PX_POR_MINUTO;
        return limitar(Math.round(minutos / 15) * 15, HORA_INICIO * 60, HORA_FIN * 60);
    }

    /** Muestra la guía visual de arrastre en una columna. */
    function mostrarGuia(columna, minutos) {
        const guia = columna.querySelector(".calendario-guia");
        if (!guia) {
            return;
        }
        const top = (minutos - HORA_INICIO * 60) * PX_POR_MINUTO;
        guia.style.top = `${top}px`;
        guia.querySelector(".calendario-guia__etiqueta").textContent =
            `${dosDigitos(Math.floor(minutos / 60))}:${dosDigitos(minutos % 60)}`;
        guia.classList.remove("oculto");
    }

    /** Oculta todas las guías de arrastre. */
    function ocultarGuias() {
        ESTADO.raiz?.querySelectorAll(".calendario-guia").forEach((guia) =>
            guia.classList.add("oculto")
        );
    }

    /** Conecta los eventos de la interfaz del calendario. */
    function conectar() {
        const raiz = ESTADO.raiz;
        const contexto = ESTADO.contexto;

        raiz.querySelectorAll("[data-modo]").forEach((boton) => {
            boton.addEventListener("click", () => {
                if (ESTADO.modo !== boton.dataset.modo) {
                    ESTADO.modo = boton.dataset.modo;
                    ESTADO.cursor = ESTADO.modo === "mes" ? new Date(ESTADO.cursor) : ESTADO.cursor;
                    recargar();
                }
            });
        });

        raiz.querySelectorAll("[data-nav]").forEach((boton) => {
            boton.addEventListener("click", () => {
                const accion = boton.dataset.nav;
                if (accion === "hoy") {
                    ESTADO.cursor = new Date();
                } else if (ESTADO.modo === "mes") {
                    const delta = accion === "anterior" ? -1 : 1;
                    ESTADO.cursor = new Date(
                        ESTADO.cursor.getFullYear(),
                        ESTADO.cursor.getMonth() + delta,
                        1
                    );
                } else {
                    ESTADO.cursor = sumarDias(ESTADO.cursor, accion === "anterior" ? -7 : 7);
                }
                recargar();
            });
        });

        raiz.querySelectorAll("[data-ir-dia]").forEach((boton) => {
            boton.addEventListener("click", (evento) => {
                evento.stopPropagation();
                ESTADO.cursor = new Date(`${boton.dataset.irDia}T12:00`);
                ESTADO.modo = "semana";
                recargar();
            });
        });

        raiz.querySelectorAll("[data-evento]").forEach((elemento) => {
            const identificador = Number(elemento.dataset.evento);
            elemento.addEventListener("click", () => {
                if (ESTADO.arrastre?.movido) {
                    return;
                }
                abrirDetalle(identificador);
            });
            if (elemento.classList.contains("calendario-evento")) {
                elemento.addEventListener("dragstart", (evento) => {
                    const eventoDatos = ESTADO.eventos.find((item) => item.id === identificador);
                    if (!eventoDatos) {
                        return;
                    }
                    const duracion = Math.max(
                        30,
                        minutosDelDia(eventoDatos.fecha_fin) - minutosDelDia(eventoDatos.fecha_inicio)
                    );
                    ESTADO.arrastre = { identificador, duracion, movido: false };
                    evento.dataTransfer.setData("text/plain", String(identificador));
                    evento.dataTransfer.effectAllowed = "move";
                    elemento.classList.add("arrastrando");
                });
                elemento.addEventListener("dragend", () => {
                    elemento.classList.remove("arrastrando");
                    ocultarGuias();
                    global.setTimeout(() => {
                        ESTADO.arrastre = null;
                    }, 180);
                });
            }
        });

        raiz.querySelectorAll(".calendario-dia").forEach((columna) => {
            columna.addEventListener("dragover", (evento) => {
                if (!ESTADO.arrastre) {
                    return;
                }
                evento.preventDefault();
                evento.dataTransfer.dropEffect = "move";
                mostrarGuia(columna, minutoDesdeRaton(evento, columna));
            });
            columna.addEventListener("dragleave", (evento) => {
                if (!columna.contains(evento.relatedTarget)) {
                    columna.querySelector(".calendario-guia")?.classList.add("oculto");
                }
            });
            columna.addEventListener("drop", async (evento) => {
                evento.preventDefault();
                if (!ESTADO.arrastre) {
                    return;
                }
                const { identificador, duracion } = ESTADO.arrastre;
                ESTADO.arrastre.movido = true;
                const minutos = minutoDesdeRaton(evento, columna);
                const minutosFin = limitar(minutos + duracion, HORA_INICIO * 60, 23 * 60 + 59);
                const fecha = columna.dataset.fecha;
                const inicio = `${fecha}T${dosDigitos(Math.floor(minutos / 60))}:${dosDigitos(minutos % 60)}`;
                const fin = `${fecha}T${dosDigitos(Math.floor(minutosFin / 60))}:${dosDigitos(minutosFin % 60)}`;
                ocultarGuias();
                try {
                    await global.PuenteAgenda.obtener("mover_evento", identificador, inicio, fin);
                    ESTADO.contexto.toast(
                        "Evento reprogramado",
                        `${fechaCorta(inicio)} · ${horaCorta(inicio)}`,
                        "exito",
                        2800
                    );
                    await recargar();
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo mover", String(error.message || error), "error");
                }
            });
        });

        raiz.querySelector("[data-accion='nuevo-evento']")?.addEventListener("click", () => {
            ESTADO.contexto.abrirModal("evento");
        });

        const filtro = raiz.querySelector("#filtro-asignatura");
        filtro?.addEventListener("change", () => {
            ESTADO.filtro = filtro.value;
            pintar();
        });

        // Clic en una celda del mes (fuera de un chip) salta a esa semana.
        raiz.querySelectorAll(".calendario-mes__celda").forEach((celda) => {
            celda.addEventListener("click", (evento) => {
                if (evento.target.closest("[data-evento]") || evento.target.closest("[data-ir-dia]")) {
                    return;
                }
                ESTADO.cursor = new Date(`${celda.dataset.dia}T12:00`);
                ESTADO.modo = "semana";
                recargar();
            });
        });
    }

    /** Vuelve a pintar la vista con los datos actuales. */
    function pintar() {
        if (!ESTADO.raiz) {
            return;
        }
        const scrollPrevio = document.getElementById("contenido")?.scrollTop || 0;
        ESTADO.raiz.innerHTML = plantilla();
        conectar();
        actualizarLineaAhora();
        const contenido = document.getElementById("contenido");
        if (contenido) {
            contenido.scrollTop = scrollPrevio;
        }
    }

    /** Recarga los eventos desde Python y repinta. */
    async function recargar(conservarPanel = false) {
        ESTADO.cargando = true;
        if (!conservarPanel) {
            cerrarDetalle();
        }
        try {
            pintar();
            await cargarEventos();
        } catch (error) {
            ESTADO.contexto.toast("No se pudo cargar el calendario", String(error.message || error), "error");
        } finally {
            ESTADO.cargando = false;
            pintar();
            if (ESTADO.eventoPendiente) {
                const pendiente = ESTADO.eventoPendiente;
                ESTADO.eventoPendiente = null;
                abrirDetalle(pendiente);
            }
        }
    }

    /** Sitúa la línea del instante actual en la columna de hoy. */
    function actualizarLineaAhora() {
        const ahora = new Date();
        const minutos = ahora.getHours() * 60 + ahora.getMinutes();
        ESTADO.raiz?.querySelectorAll("[data-ahora]").forEach((linea) => {
            if (minutos < HORA_INICIO * 60 || minutos > HORA_FIN * 60) {
                linea.classList.add("oculto");
                return;
            }
            linea.classList.remove("oculto");
            linea.style.top = `${(minutos - HORA_INICIO * 60) * PX_POR_MINUTO}px`;
        });
    }

    /* ------------------------------------------------------------------
       Módulo de vista
       ------------------------------------------------------------------ */
    /**
     * Monta la vista Calendario.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto de la aplicación.
     */
    function montar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        if (!ESTADO.inicializado) {
            ESTADO.cursor = new Date();
            ESTADO.inicializado = true;
        }
        if (contexto.evento) {
            ESTADO.eventoPendiente = contexto.evento;
        }
        raiz.innerHTML = plantilla();
        conectar();
        recargar();
        detenerReloj();
        ESTADO.intervalo = global.setInterval(() => {
            actualizarLineaAhora();
            const ahora = new Date();
            if (ahora.getHours() === 0 && ahora.getMinutes() === 0) {
                recargar();
            }
        }, 60_000);
    }

    /**
     * Refresca la vista sin perder el modo ni el periodo elegido.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto de la aplicación.
     */
    function actualizar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        recargar();
    }

    /** Detiene el intervalo de la línea del ahora. */
    function detenerReloj() {
        if (ESTADO.intervalo) {
            global.clearInterval(ESTADO.intervalo);
            ESTADO.intervalo = null;
        }
    }

    global.AgendaApp.registrarVista("calendario", { montar, actualizar });
})(window);
