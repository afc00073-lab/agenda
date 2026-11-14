/**
 * ============================================================================
 *  VISTA KANBAN · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Tablero de cuatro columnas para conducir las tareas académicas desde la
 *  idea hasta la entrega:
 *
 *      Pendiente → En desarrollo → Revisión / Pruebas → Entregado
 *
 *  Cada tarjeta muestra su prioridad, la asignatura, la fecha límite, el
 *  avance de sus subtareas y un botón de completado rápido. Las tarjetas se
 *  arrastran con el ratón entre columnas (HTML5 Drag & Drop) y, al pulsarlas,
 *  se abre una ficha lateral para gestionar subtareas, editar o eliminar.
 *
 *  No se registra ningún atajo de teclado.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const {
        escapar, icono, fechaCorta, fechaRelativa, diasHasta, horaCorta,
        COLORES_PRIORIDAD
    } = U;

    /** Definición visual de las columnas, en el orden del flujo de trabajo. */
    const COLUMNAS = [
        {
            id: "pendiente",
            titulo: "Pendiente",
            descripcion: "Ideas y entregas por arrancar",
            color: "#8a8fa8",
            icono: "carpeta"
        },
        {
            id: "en_desarrollo",
            titulo: "En desarrollo",
            descripcion: "Trabajo en curso",
            color: "#4aa8ff",
            icono: "rayo"
        },
        {
            id: "revision",
            titulo: "Revisión / Pruebas",
            descripcion: "Últimos repasos antes de entregar",
            color: "#ffc857",
            icono: "objetivo"
        },
        {
            id: "entregado",
            titulo: "Entregado",
            descripcion: "Trabajo cerrado y archivado",
            color: "#28c8a0",
            icono: "trofeo"
        }
    ];

    const ESTADO = {
        columnas: [],
        total: 0,
        filtro: "",
        busqueda: "",
        raiz: null,
        contexto: null,
        cargando: false,
        arrastre: null,
        panel: null,
        temporizador: null
    };

    /* ------------------------------------------------------------------
       Utilidades locales
       ------------------------------------------------------------------ */
    /**
     * Devuelve el color de prioridad con un valor de reserva.
     * @param {string} prioridad Prioridad de la tarea.
     * @returns {string} Color CSS.
     */
    function colorPrioridad(prioridad) {
        return COLORES_PRIORIDAD[prioridad] || COLORES_PRIORIDAD.media || "var(--acento)";
    }

    /**
     * Describe la fecha límite en lenguaje natural y con su urgencia.
     * @param {string} iso Fecha ISO de la tarea.
     * @returns {{texto: string, estado: string}} Texto y estado visual.
     */
    function vencimiento(iso) {
        if (!iso) {
            return { texto: "Sin fecha", estado: "sin-fecha" };
        }
        const dias = diasHasta(iso);
        if (dias < 0) {
            return { texto: `Vencida hace ${Math.abs(dias)} d`, estado: "vencida" };
        }
        if (dias === 0) {
            return { texto: "Vence hoy", estado: "hoy" };
        }
        if (dias === 1) {
            return { texto: "Vence mañana", estado: "proxima" };
        }
        if (dias <= 3) {
            return { texto: `Faltan ${dias} días`, estado: "proxima" };
        }
        return { texto: fechaCorta(iso, { day: "numeric", month: "short" }), estado: "lejana" };
    }

    /**
     * Cuenta las tareas que vencen en los próximos siete días.
     * @returns {number} Número de tareas urgentes.
     */
    function contarUrgentes() {
        return ESTADO.columnas
            .filter((columna) => columna.id !== "entregado")
            .flatMap((columna) => columna.tareas)
            .filter((tarea) => {
                const dias = diasHasta(tarea.fecha_inicio);
                return dias <= 7;
            }).length;
    }

    /**
     * Calcula el avance global del tablero ponderando las columnas.
     * @returns {number} Porcentaje entre 0 y 100.
     */
    function progresoGlobal() {
        if (!ESTADO.total) {
            return 0;
        }
        const pesos = { pendiente: 0.1, en_desarrollo: 0.45, revision: 0.8, entregado: 1 };
        const suma = ESTADO.columnas.reduce((total, columna) => {
            const peso = pesos[columna.id] ?? 0;
            return total + columna.tareas.length * peso;
        }, 0);
        return Math.round((suma / ESTADO.total) * 100);
    }

    /* ------------------------------------------------------------------
       Plantillas
       ------------------------------------------------------------------ */
    /**
     * Construye las pastillas de filtro por asignatura.
     * @returns {string} HTML de la barra de filtros.
     */
    function filtrosAsignatura() {
        const asignaturas = ESTADO.contexto?.asignaturas || [];
        if (!asignaturas.length) {
            return "";
        }
        const opciones = [
            `<button class="kanban-filtro ${ESTADO.filtro === "" ? "activo" : ""}"
                     type="button" data-filtro="">
                ${icono("capas")} Todas
            </button>`,
            ...asignaturas.map((asignatura) => `
                <button class="kanban-filtro ${String(ESTADO.filtro) === String(asignatura.id) ? "activo" : ""}"
                        type="button" data-filtro="${asignatura.id}"
                        style="--tono-filtro:${asignatura.color || "var(--acento)"}">
                    <span class="kanban-filtro__punto"></span>${escapar(asignatura.nombre)}
                </button>`)
        ];
        return `<div class="kanban-filtros" role="group" aria-label="Filtrar por asignatura">${opciones.join("")}</div>`;
    }

    /**
     * Cabecera con indicadores del tablero.
     * @returns {string} HTML del resumen.
     */
    function resumenTablero() {
        const enCurso = ESTADO.columnas.find((columna) => columna.id === "en_desarrollo")?.tareas.length || 0;
        const entregadas = ESTADO.columnas.find((columna) => columna.id === "entregado")?.tareas.length || 0;
        const avance = progresoGlobal();
        return `
            <div class="kanban-resumen">
                <article class="kanban-metrica">
                    <span class="kanban-metrica__icono" style="--tono:var(--color-informacion)">${icono("kanban")}</span>
                    <div>
                        <p class="kanban-metrica__valor">${ESTADO.total}</p>
                        <p class="kanban-metrica__etiqueta">Tareas totales</p>
                    </div>
                </article>
                <article class="kanban-metrica">
                    <span class="kanban-metrica__icono" style="--tono:#4aa8ff">${icono("rayo")}</span>
                    <div>
                        <p class="kanban-metrica__valor">${enCurso}</p>
                        <p class="kanban-metrica__etiqueta">En desarrollo</p>
                    </div>
                </article>
                <article class="kanban-metrica">
                    <span class="kanban-metrica__icono" style="--tono:var(--color-aviso)">${icono("alerta")}</span>
                    <div>
                        <p class="kanban-metrica__valor">${contarUrgentes()}</p>
                        <p class="kanban-metrica__etiqueta">Vencen esta semana</p>
                    </div>
                </article>
                <article class="kanban-metrica kanban-metrica--progreso">
                    <div class="kanban-metrica__cabecera">
                        <span class="kanban-metrica__icono" style="--tono:var(--color-exito)">${icono("trofeo")}</span>
                        <span class="kanban-metrica__porcentaje">${avance}%</span>
                    </div>
                    <div class="barra-progreso barra-progreso--fina">
                        <span class="barra-progreso__relleno" style="width:${avance}%"></span>
                    </div>
                    <p class="kanban-metrica__etiqueta">${entregadas} de ${ESTADO.total} entregadas</p>
                </article>
            </div>`;
    }

    /**
     * Tarjeta de una tarea.
     * @param {object} tarea Tarea serializada por el puente.
     * @returns {string} HTML de la tarjeta.
     */
    function tarjeta(tarea) {
        const vence = vencimiento(tarea.fecha_inicio);
        const progreso = Number(tarea.progreso) || 0;
        const completada = Boolean(tarea.completado);
        const subtareas = tarea.subtareas || [];
        const pendientes = subtareas.filter((subtarea) => !subtarea.completada);
        const color = tarea.asignatura_color || U.colorDesdeTexto(tarea.asignatura_nombre || tarea.titulo);
        return `
            <article class="kanban-tarjeta ${completada ? "completada" : ""}"
                     draggable="true" data-tarea="${Number(tarea.id)}"
                     style="--color-prioridad:${colorPrioridad(tarea.prioridad)};--color-materia:${color}">
                <div class="kanban-tarjeta__franja"></div>
                <header class="kanban-tarjeta__cabecera">
                    <span class="kanban-tarjeta__materia">
                        <span class="kanban-tarjeta__punto"></span>${escapar(tarea.asignatura_nombre || "Sin asignatura")}
                    </span>
                    <button class="kanban-tarjeta__completar ${completada ? "activa" : ""}"
                            type="button" data-completar-tarjeta="${Number(tarea.id)}"
                            aria-label="${completada ? "Reabrir tarea" : "Marcar como completada"}">
                        ${icono("check")}
                    </button>
                </header>
                <h3 class="kanban-tarjeta__titulo">${escapar(tarea.titulo)}</h3>
                ${tarea.descripcion ? `<p class="kanban-tarjeta__descripcion">${escapar(tarea.descripcion)}</p>` : ""}
                <div class="kanban-tarjeta__meta">
                    <span class="kanban-tarjeta__vence kanban-tarjeta__vence--${vence.estado}">
                        ${icono("reloj")}${escapar(vence.texto)}
                    </span>
                    <span class="etiqueta etiqueta--${tarea.prioridad === "critica" ? "critica" : tarea.prioridad}">
                        ${escapar(U.etiquetaPrioridad(tarea.prioridad))}
                    </span>
                </div>
                ${subtareas.length ? `
                    <div class="kanban-tarjeta__progreso">
                        <div class="kanban-tarjeta__progreso-texto">
                            <span>${icono("check")}${tarea.subtareas_completadas}/${tarea.total_subtareas}</span>
                            <span>${progreso}%</span>
                        </div>
                        <div class="barra-progreso barra-progreso--mini">
                            <span class="barra-progreso__relleno" style="width:${progreso}%"></span>
                        </div>
                        ${pendientes.length ? `
                            <p class="kanban-tarjeta__siguiente">
                                Siguiente: ${escapar(pendientes[0].titulo)}
                            </p>` : `
                            <p class="kanban-tarjeta__siguiente kanban-tarjeta__siguiente--hecho">
                                ${icono("exito")} Todas las subtareas completadas
                            </p>`}
                    </div>` : `
                    <p class="kanban-tarjeta__sin-subtareas">${icono("mas")} Sin subtareas todavía</p>`}
            </article>`;
    }

    /**
     * Columna completa con su zona de soltar.
     * @param {object} columna Columna con tareas.
     * @returns {string} HTML de la columna.
     */
    function columnaKanban(columna) {
        const vacia = columna.tareas.length === 0;
        return `
            <section class="kanban-columna" data-columna="${columna.id}"
                     style="--color-columna:${columna.color}">
                <header class="kanban-columna__cabecera">
                    <div class="kanban-columna__titulo">
                        <span class="kanban-columna__icono">${icono(columna.icono)}</span>
                        <div>
                            <h2>${escapar(columna.titulo)}</h2>
                            <p>${escapar(columna.descripcion)}</p>
                        </div>
                    </div>
                    <span class="kanban-columna__contador">${columna.tareas.length}</span>
                </header>
                <div class="kanban-columna__cuerpo" data-zona-soltar="${columna.id}">
                    ${columna.tareas.map(tarjeta).join("")}
                    ${vacia ? `
                        <div class="kanban-vacio">
                            ${icono("capas")}
                            <p>Arrastra una tarjeta aquí</p>
                            <span>o crea una tarea nueva en esta columna</span>
                        </div>` : ""}
                </div>
                <footer class="kanban-columna__pie">
                    <button class="kanban-agregar" type="button" data-nueva-en="${columna.id}">
                        ${icono("mas")} Añadir tarea
                    </button>
                </footer>
            </section>`;
    }

    /** Plantilla completa de la vista. */
    function plantilla() {
        return `
            <div class="kanban">
                <div class="kanban-barra">
                    <div class="kanban-barra__izquierda">
                        <label class="kanban-busqueda" for="kanban-buscar">
                            ${icono("buscar")}
                            <input id="kanban-buscar" type="search" data-buscar
                                   placeholder="Buscar una tarea…" value="${escapar(ESTADO.busqueda)}"
                                   autocomplete="off">
                        </label>
                        ${filtrosAsignatura()}
                    </div>
                    <button class="boton boton--primario boton--pequeno" type="button" data-nueva-tarea>
                        ${icono("mas")} Nueva tarea
                    </button>
                </div>

                ${resumenTablero()}

                <div class="kanban-tablero" id="kanban-tablero">
                    ${ESTADO.columnas.map(columnaKanban).join("")}
                </div>

                <p class="kanban-leyenda">
                    ${icono("informacion")}
                    Arrastra las tarjetas entre columnas para actualizar su estado.
                    Pulsa una tarjeta para abrir la ficha de subtareas.
                </p>
            </div>`;
    }

    /* ------------------------------------------------------------------
       Carga y filtrado
       ------------------------------------------------------------------ */
    /** Descarga el tablero desde la base de datos. */
    async function cargar() {
        if (ESTADO.cargando) {
            return;
        }
        ESTADO.cargando = true;
        try {
            const datos = await global.PuenteAgenda.obtener("listar_kanban");
            ESTADO.columnas = (datos.columnas || []).map((columna) => ({
                ...columna,
                tareas: filtrarTareas(columna.tareas || [])
            }));
            ESTADO.total = ESTADO.columnas.reduce((total, columna) => total + columna.tareas.length, 0);
        } catch (error) {
            ESTADO.contexto.toast("No se pudo cargar el tablero", String(error.message || error), "error");
        } finally {
            ESTADO.cargando = false;
        }
    }

    /**
     * Aplica búsqueda y filtro de asignatura a una lista de tareas.
     * @param {object[]} tareas Tareas de la columna.
     * @returns {object[]} Tareas visibles.
     */
    function filtrarTareas(tareas) {
        const termino = ESTADO.busqueda.trim().toLowerCase();
        return tareas.filter((tarea) => {
            const coincideMateria =
                !ESTADO.filtro || String(tarea.asignatura_id) === String(ESTADO.filtro);
            const coincideTexto = !termino || [
                tarea.titulo,
                tarea.descripcion,
                tarea.asignatura_nombre
            ].filter(Boolean).some((texto) => String(texto).toLowerCase().includes(termino));
            return coincideMateria && coincideTexto;
        });
    }

    /** Vuelve a pintar el tablero conservando los filtros. */
    async function recargar() {
        if (!ESTADO.raiz) {
            return;
        }
        await cargar();
        ESTADO.raiz.innerHTML = plantilla();
        conectar();
    }

    /* ------------------------------------------------------------------
       Interacción
       ------------------------------------------------------------------ */
    /** Conecta todos los controles de la vista. */
    function conectar() {
        const raiz = ESTADO.raiz;
        if (!raiz) {
            return;
        }

        const buscador = raiz.querySelector("[data-buscar]");
        if (buscador) {
            buscador.addEventListener("input", () => {
                ESTADO.busqueda = buscador.value;
                global.clearTimeout(ESTADO.temporizador);
                ESTADO.temporizador = global.setTimeout(() => {
                    recargar();
                    const nuevo = ESTADO.raiz?.querySelector("[data-buscar]");
                    if (nuevo) {
                        nuevo.focus();
                        nuevo.setSelectionRange(nuevo.value.length, nuevo.value.length);
                    }
                }, 220);
            });
        }

        raiz.querySelectorAll("[data-filtro]").forEach((boton) => {
            boton.addEventListener("click", () => {
                ESTADO.filtro = boton.dataset.filtro || "";
                recargar();
            });
        });

        raiz.querySelector("[data-nueva-tarea]")?.addEventListener("click", () => {
            ESTADO.contexto.abrirModal("tarea", { estado_kanban: "pendiente" });
        });

        raiz.querySelectorAll("[data-nueva-en]").forEach((boton) => {
            boton.addEventListener("click", () => {
                ESTADO.contexto.abrirModal("tarea", { estado_kanban: boton.dataset.nuevaEn });
            });
        });

        raiz.querySelectorAll("[data-completar-tarjeta]").forEach((boton) => {
            boton.addEventListener("click", async (evento) => {
                evento.stopPropagation();
                const identificador = Number(boton.dataset.completarTarjeta);
                const activa = boton.classList.contains("activa");
                try {
                    await global.PuenteAgenda.obtener(
                        "completar_evento", identificador, !activa
                    );
                    ESTADO.contexto.toast(
                        activa ? "Tarea reabierta" : "Tarea completada",
                        "El tablero se ha actualizado",
                        activa ? "info" : "exito",
                        2400
                    );
                    await recargar();
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo actualizar", String(error.message || error), "error");
                }
            });
        });

        raiz.querySelectorAll(".kanban-tarjeta").forEach((elemento) => {
            elemento.addEventListener("click", () => abrirDetalle(Number(elemento.dataset.tarea)));
            elemento.addEventListener("dragstart", (evento) => iniciarArrastre(evento, elemento));
            elemento.addEventListener("dragend", finalizarArrastre);
        });

        raiz.querySelectorAll("[data-zona-soltar]").forEach((zona) => {
            zona.addEventListener("dragover", (evento) => {
                if (!ESTADO.arrastre) {
                    return;
                }
                evento.preventDefault();
                evento.dataTransfer.dropEffect = "move";
                zona.classList.add("zona-activa");
            });
            zona.addEventListener("dragleave", (evento) => {
                if (!zona.contains(evento.relatedTarget)) {
                    zona.classList.remove("zona-activa");
                }
            });
            zona.addEventListener("drop", async (evento) => {
                evento.preventDefault();
                zona.classList.remove("zona-activa");
                await soltarEn(zona.dataset.zonaSoltar, evento);
            });
        });
    }

    /**
     * Prepara el arrastre de una tarjeta.
     * @param {DragEvent} evento Evento nativo.
     * @param {HTMLElement} elemento Tarjeta arrastrada.
     */
    function iniciarArrastre(evento, elemento) {
        ESTADO.arrastre = {
            id: Number(elemento.dataset.tarea),
            origen: elemento.closest("[data-columna]")?.dataset.columna,
            elemento
        };
        elemento.classList.add("arrastrando");
        if (evento.dataTransfer) {
            evento.dataTransfer.effectAllowed = "move";
            evento.dataTransfer.setData("text/plain", String(ESTADO.arrastre.id));
        }
    }

    /** Limpia el estado visual del arrastre. */
    function finalizarArrastre() {
        ESTADO.arrastre?.elemento?.classList.remove("arrastrando");
        ESTADO.raiz?.querySelectorAll(".zona-activa").forEach((zona) =>
            zona.classList.remove("zona-activa")
        );
        ESTADO.arrastre = null;
    }

    /**
     * Mueve la tarjeta arrastrada a la columna de destino.
     * @param {string} destino Identificador de la columna.
     * @param {DragEvent} evento Evento de soltado.
     */
    async function soltarEn(destino, evento) {
        const arrastre = ESTADO.arrastre;
        finalizarArrastre();
        if (!arrastre || !destino || arrastre.origen === destino) {
            return;
        }
        const columnaDestino = ESTADO.columnas.find((columna) => columna.id === destino);
        if (columnaDestino) {
            columnaDestino.tareas.unshift({
                id: arrastre.id,
                titulo: arrastre.elemento.querySelector(".kanban-tarjeta__titulo")?.textContent || "Tarea",
                completado: destino === "entregado",
                prioridad: "media",
                subtareas: []
            });
        }
        try {
            await global.PuenteAgenda.obtener("mover_tarjeta", arrastre.id, destino);
            const tituloColumna = COLUMNAS.find((columna) => columna.id === destino)?.titulo || destino;
            ESTADO.contexto.toast("Tarjeta movida", tituloColumna, "exito", 2200);
            await recargar();
        } catch (error) {
            ESTADO.contexto.toast("No se pudo mover la tarjeta", String(error.message || error), "error");
            await recargar();
        }
    }

    /* ------------------------------------------------------------------
       Ficha lateral de la tarea
       ------------------------------------------------------------------ */
    /**
     * Abre el panel lateral con las subtareas y acciones de una tarea.
     * @param {number} identificador Identificador de la tarea.
     */
    async function abrirDetalle(identificador) {
        cerrarDetalle();
        let tarea;
        try {
            tarea = await global.PuenteAgenda.obtener("obtener_evento", identificador);
        } catch (error) {
            ESTADO.contexto.toast("No se pudo abrir la tarea", String(error.message || error), "error");
            return;
        }
        if (!tarea) {
            return;
        }

        const color = tarea.asignatura_color || "var(--acento)";
        const vence = vencimiento(tarea.fecha_inicio);
        const fondo = document.createElement("div");
        fondo.className = "panel-lateral__fondo";
        fondo.dataset.cerrarPanel = "1";

        const panel = document.createElement("aside");
        panel.className = "panel-lateral panel-lateral--kanban";
        panel.id = "panel-tarea";
        panel.style.setProperty("--color-evento", color);
        panel.innerHTML = `
            <header class="panel-lateral__cabecera">
                <span class="panel-evento__icono" style="--color-evento:${color}">
                    ${icono("check")}
                </span>
                <div style="min-width:0;flex:1">
                    <p class="panel-evento__tipo">Tarea · ${escapar(COLUMNAS.find((columna) => columna.id === tarea.estado_kanban)?.titulo || "Pendiente")}</p>
                    <h2 class="panel-evento__titulo">${escapar(tarea.titulo)}</h2>
                    <p class="panel-evento__materia">${escapar(tarea.asignatura_nombre || "Sin asignatura")}</p>
                </div>
                <button class="modal__cerrar" type="button" data-cerrar-panel aria-label="Cerrar detalle">
                    ${icono("x")}
                </button>
            </header>
            <div class="panel-lateral__cuerpo">
                <div class="panel-evento__datos">
                    <div class="panel-dato">
                        <span class="panel-dato__etiqueta">${icono("reloj")} Fecha límite</span>
                        <span class="panel-dato__valor ${vence.estado === "vencida" ? "texto-peligro" : ""}">
                            ${escapar(fechaRelativa(tarea.fecha_inicio))}
                            ${horaCorta(tarea.fecha_inicio) ? ` · ${escapar(horaCorta(tarea.fecha_inicio))}` : ""}
                        </span>
                    </div>
                    <div class="panel-dato">
                        <span class="panel-dato__etiqueta">${icono("alerta")} Prioridad</span>
                        <span class="panel-dato__valor">
                            <span class="etiqueta ${tarea.prioridad === "critica" ? "etiqueta--critica" : `etiqueta--${tarea.prioridad || "media"}`}">
                                ${escapar(U.etiquetaPrioridad(tarea.prioridad))}
                            </span>
                        </span>
                    </div>
                    <div class="panel-dato">
                        <span class="panel-dato__etiqueta">${icono("objetivo")} Avance</span>
                        <span class="panel-dato__valor">${Number(tarea.progreso) || 0}%</span>
                    </div>
                </div>

                <div class="barra-progreso barra-progreso--panel">
                    <span class="barra-progreso__relleno" style="width:${Number(tarea.progreso) || 0}%"></span>
                </div>

                ${tarea.descripcion ? `
                    <div class="panel-evento__bloque">
                        <h3 class="panel-evento__subtitulo">${icono("nota")} Notas</h3>
                        <p class="panel-evento__texto">${escapar(tarea.descripcion)}</p>
                    </div>` : ""}

                <div class="panel-evento__bloque">
                    <h3 class="panel-evento__subtitulo">
                        ${icono("check")} Subtareas
                        <span class="texto-tenue">${tarea.subtareas_completadas}/${tarea.total_subtareas}</span>
                    </h3>
                    <div class="panel-subtareas">
                        ${(tarea.subtareas || []).map((subtarea) => `
                            <div class="panel-subtarea-fila">
                                <button class="panel-subtarea ${subtarea.completada ? "completada" : ""}"
                                        type="button" data-subtarea="${Number(subtarea.id)}"
                                        data-estado="${subtarea.completada ? "1" : "0"}">
                                    <span class="marca-verificacion ${subtarea.completada ? "activa" : ""}">${icono("check")}</span>
                                    <span class="panel-subtarea__texto">${escapar(subtarea.titulo)}</span>
                                </button>
                                <button class="panel-subtarea__borrar" type="button"
                                        data-borrar-subtarea="${Number(subtarea.id)}"
                                        aria-label="Eliminar subtarea">${icono("x")}</button>
                            </div>`).join("")}
                        ${(tarea.subtareas || []).length ? "" : `
                            <p class="panel-vacio">Aún no hay subtareas. Divide la tarea en pasos pequeños.</p>`}
                    </div>
                    <form class="panel-subtarea-form" data-form-subtarea>
                        <input type="text" class="campo__control" name="subtarea"
                               placeholder="Añadir un paso…" autocomplete="off" required>
                        <button class="boton boton--primario boton--pequeno" type="submit">
                            ${icono("mas")} Añadir
                        </button>
                    </form>
                </div>
            </div>
            <footer class="panel-lateral__pie">
                <button class="boton boton--primario boton--pequeno" type="button" data-completar-evento>
                    ${icono(tarea.completado ? "reiniciar" : "check")}
                    ${tarea.completado ? "Reabrir" : "Completar"}
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
                await global.PuenteAgenda.obtener("completar_evento", tarea.id, !tarea.completado);
                ESTADO.contexto.toast(
                    tarea.completado ? "Tarea reabierta" : "Tarea completada",
                    tarea.titulo,
                    tarea.completado ? "info" : "exito",
                    2600
                );
                cerrarDetalle();
                await recargar();
            } catch (error) {
                ESTADO.contexto.toast("No se pudo actualizar", String(error.message || error), "error");
            }
        });

        panel.querySelector("[data-editar-evento]").addEventListener("click", () => {
            cerrarDetalle();
            ESTADO.contexto.abrirModal("tarea", {
                ...tarea,
                fecha: (tarea.fecha_inicio || "").slice(0, 10),
                hora: (tarea.fecha_inicio || "").slice(11, 16)
            });
        });

        const botonEliminar = panel.querySelector("[data-eliminar-evento]");
        botonEliminar.addEventListener("click", async () => {
            if (botonEliminar.dataset.confirmar !== "1") {
                botonEliminar.dataset.confirmar = "1";
                botonEliminar.innerHTML = `${icono("alerta")} Confirmar`;
                global.setTimeout(() => {
                    if (botonEliminar.isConnected) {
                        botonEliminar.dataset.confirmar = "0";
                        botonEliminar.innerHTML = `${icono("basura")} Eliminar`;
                    }
                }, 3200);
                return;
            }
            try {
                await global.PuenteAgenda.obtener("eliminar_evento", tarea.id);
                ESTADO.contexto.toast("Tarea eliminada", tarea.titulo, "info", 2600);
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
                    await abrirDetalle(tarea.id);
                    await recargar();
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo actualizar la subtarea", String(error.message || error), "error");
                }
            });
        });

        panel.querySelectorAll("[data-borrar-subtarea]").forEach((boton) => {
            boton.addEventListener("click", async () => {
                try {
                    await global.PuenteAgenda.obtener(
                        "eliminar_subtarea", Number(boton.dataset.borrarSubtarea)
                    );
                    cerrarDetalle();
                    await abrirDetalle(tarea.id);
                    await recargar();
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo eliminar la subtarea", String(error.message || error), "error");
                }
            });
        });

        panel.querySelector("[data-form-subtarea]").addEventListener("submit", async (evento) => {
            evento.preventDefault();
            const entrada = evento.currentTarget.elements.subtarea;
            const titulo = (entrada?.value || "").trim();
            if (!titulo) {
                ESTADO.contexto.toast("Falta el texto", "Escribe el nombre del paso.", "aviso");
                return;
            }
            try {
                await global.PuenteAgenda.obtener("crear_subtarea", tarea.id, titulo);
                cerrarDetalle();
                await abrirDetalle(tarea.id);
                await recargar();
            } catch (error) {
                ESTADO.contexto.toast("No se pudo añadir la subtarea", String(error.message || error), "error");
            }
        });

        panel.querySelector("[data-form-subtarea] input")?.focus();
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
        }, 260);
    }

    /* ------------------------------------------------------------------
       Ciclo de vida de la vista
       ------------------------------------------------------------------ */
    /**
     * Monta la vista Kanban.
     * @param {HTMLElement} raiz Contenedor de la vista.
     * @param {object} contexto Contexto de la aplicación.
     */
    async function montar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        await recargar();
    }

    /**
     * Refresca el tablero cuando cambian los datos globales.
     * @param {HTMLElement} raiz Contenedor de la vista.
     * @param {object} contexto Contexto de la aplicación.
     */
    async function actualizar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        if (!raiz.querySelector(".kanban-tablero")) {
            await recargar();
            return;
        }
        await recargar();
    }

    global.AgendaApp.registrarVista("kanban", { montar, actualizar });
})(window);
