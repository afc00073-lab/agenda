/**
 * ============================================================================
 *  VISTA ASIGNATURAS · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Convierte el expediente en un panel visual claro:
 *
 *  * Un héroe con la media ponderada por créditos ECTS y un selector de nota
 *    objetivo que recalcula todas las asignaturas al instante.
 *  * Tarjetas por materia con su color, profesorado, nota provisional, peso
 *    evaluado y la calificación que aún hace falta para llegar a la meta.
 *  * Una ficha lateral con el desglose de evaluaciones, la calculadora de
 *    escenarios y las acciones para añadir, editar o eliminar notas y materias.
 *
 *  Toda la interacción es con ratón; no hay atajos de teclado.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { escapar, icono, fechaCorta, diasHasta, limitar } = U;

    const TIPOS_EVALUACION = {
        examen: { etiqueta: "Examen", icono: "nota" },
        practica: { etiqueta: "Práctica", icono: "editar" },
        proyecto: { etiqueta: "Proyecto", icono: "capas" },
        participacion: { etiqueta: "Participación", icono: "usuarios" }
    };

    const ESTADO = {
        expediente: null,
        objetivo: 5,
        raiz: null,
        contexto: null,
        panel: null,
        asignaturaAbierta: null,
        calculoPanel: null,
        temporizador: null,
        cargando: false
    };

    /* ------------------------------------------------------------------
       Formato y cálculo visual
       ------------------------------------------------------------------ */
    /**
     * Da formato a una nota con un decimal y sin ceros sobrantes.
     * @param {number|null} nota Calificación.
     * @returns {string} Texto listo para pintar.
     */
    function formatearNota(nota) {
        if (nota === null || nota === undefined || Number.isNaN(Number(nota))) {
            return "—";
        }
        return Number(nota).toFixed(2).replace(/\.?0+$/, "");
    }

    /**
     * Asigna una clase semántica según la calificación.
     * @param {number|null} nota Nota sobre diez.
     * @returns {string} Nombre del tono.
     */
    function tonoNota(nota) {
        if (nota === null || nota === undefined) {
            return "vacia";
        }
        if (nota >= 9) {
            return "sobresaliente";
        }
        if (nota >= 7) {
            return "notable";
        }
        if (nota >= 5) {
            return "aprobada";
        }
        return "suspensa";
    }

    /**
     * Describe el estado de una asignatura.
     * @param {object} calculo Cálculo devuelto por el servicio.
     * @returns {string} Texto breve.
     */
    function estadoAsignatura(calculo) {
        if (!calculo) {
            return "Sin evaluaciones";
        }
        if (!calculo.peso_evaluado) {
            return "Pendiente de notas";
        }
        if (calculo.completa) {
            return "Nota cerrada";
        }
        return "En curso";
    }

    /**
     * Texto de la calculadora para una asignatura.
     * @param {object} calculo Cálculo de la asignatura.
     * @param {number} objetivo Meta global.
     * @returns {{texto: string, tono: string}} Mensaje y tono visual.
     */
    function mensajeCalculadora(calculo, objetivo) {
        if (!calculo || !calculo.peso_pendiente) {
            return {
                texto: calculo?.nota_provisional !== null
                    ? `Nota final: ${formatearNota(calculo.nota_provisional)}`
                    : "Sin evaluaciones registradas",
                tono: "neutro"
            };
        }
        const necesaria = calculo.nota_necesaria;
        if (calculo.peso_evaluado === 0) {
            return {
                texto: `Necesitas ${formatearNota(necesaria)} para un ${formatearNota(objetivo)}`,
                tono: "neutro"
            };
        }
        if (necesaria !== null && necesaria > 10) {
            return {
                texto: `Meta inalcanzable: haría falta ${formatearNota(necesaria)}`,
                tono: "peligro"
            };
        }
        if (necesaria === 0) {
            return {
                texto: `Meta asegurada con un ${formatearNota(objetivo)}`,
                tono: "exito"
            };
        }
        return {
            texto: `Necesitas ${formatearNota(necesaria)} en el ${formatearNota(calculo.peso_pendiente)} % restante`,
            tono: necesaria >= 8 ? "aviso" : "neutro"
        };
    }

    /* ------------------------------------------------------------------
       Plantillas
       ------------------------------------------------------------------ */
    /**
     * Indicador circular de media.
     * @param {number|null} media Media ponderada.
     * @returns {string} HTML del anillo.
     */
    function anilloMedia(media) {
        const valor = media === null ? 0 : limitar(media, 0, 10);
        const porcentaje = valor * 10;
        return `
            <div class="notas-anillo tono-${tonoNota(media)}" style="--progreso:${porcentaje}%">
                <div class="notas-anillo__interior">
                    <strong>${formatearNota(media)}</strong>
                    <span>/ 10</span>
                    <small>media ponderada</small>
                </div>
            </div>`;
    }

    /** Héroe con la media global y el selector de objetivo. */
    function heroe() {
        const datos = ESTADO.expediente || {};
        const media = datos.media_ponderada;
        const aprobadas = datos.asignaturas_aprobadas || 0;
        const total = datos.total_asignaturas || 0;
        const evaluadas = (datos.asignaturas || []).reduce(
            (suma, asignatura) => suma + (asignatura.calculo?.evaluadas || 0), 0
        );
        const pendientes = (datos.asignaturas || []).reduce(
            (suma, asignatura) => suma + (asignatura.total_eventos || 0) - (asignatura.eventos_pendientes || 0),
            0
        );
        return `
            <section class="notas-heroe">
                ${anilloMedia(media)}
                <div class="notas-heroe__texto">
                    <p class="notas-heroe__etiqueta">${icono("trofeo")} Expediente académico</p>
                    <h2 class="notas-heroe__titulo">
                        ${total ? `${total} asignaturas en seguimiento` : "Añade tu primera asignatura"}
                    </h2>
                    <p class="notas-heroe__detalle">
                        ${total ? `${aprobadas} aprobadas · ` : ""}Media ponderada por créditos ECTS ·
                        ${escapar(datos.creditos_evaluados ?? 0)} de
                        ${escapar(datos.creditos_totales ?? 0)} créditos con notas registradas
                    </p>
                    <div class="notas-heroe__insignias">
                        <span class="notas-insignia">${icono("nota")} ${evaluadas} ${evaluadas === 1 ? "evaluación con nota" : "evaluaciones con nota"}</span>
                        <span class="notas-insignia">${icono("check")} ${pendientes} ${pendientes === 1 ? "evento cerrado" : "eventos cerrados"}</span>
                    </div>
                </div>
                <div class="notas-objetivo">
                    <div class="notas-objetivo__cabecera">
                        <span>${icono("objetivo")} Nota objetivo</span>
                        <strong id="objetivo-valor">${formatearNota(ESTADO.objetivo)}</strong>
                    </div>
                    <input class="notas-objetivo__rango" type="range" min="5" max="10" step="0.5"
                           value="${ESTADO.objetivo}" data-objetivo-global
                           aria-label="Nota objetivo global">
                    <div class="notas-objetivo__escala">
                        <span>5</span><span>6</span><span>7</span><span>8</span><span>9</span><span>10</span>
                    </div>
                    <p class="notas-objetivo__ayuda">Mueve el control para recalcular todos los escenarios.</p>
                </div>
            </section>`;
    }

    /**
     * Tarjeta de una asignatura.
     * @param {object} asignatura Asignatura con su cálculo.
     * @returns {string} HTML de la tarjeta.
     */
    function tarjetaAsignatura(asignatura) {
        const calculo = asignatura.calculo || {};
        const nota = calculo.nota_provisional;
        const mensaje = mensajeCalculadora(calculo, ESTADO.objetivo);
        const peso = limitar(Number(calculo.peso_evaluado) || 0, 0, 100);
        const color = asignatura.color || "var(--acento)";
        return `
            <article class="notas-tarjeta" data-asignatura="${Number(asignatura.id)}"
                     style="--color-materia:${color}">
                <div class="notas-tarjeta__brillo"></div>
                <header class="notas-tarjeta__cabecera">
                    <span class="notas-tarjeta__codigo">${escapar(asignatura.codigo || "SIN CÓDIGO")}</span>
                    <span class="notas-tarjeta__creditos">${escapar(asignatura.creditos || 0)} ECTS</span>
                </header>
                <h3 class="notas-tarjeta__nombre">${escapar(asignatura.nombre)}</h3>
                <p class="notas-tarjeta__profesor">
                    ${icono("usuarios")} ${escapar(asignatura.profesor || "Profesorado sin asignar")}
                    ${asignatura.aula ? ` · ${escapar(asignatura.aula)}` : ""}
                </p>
                <div class="notas-tarjeta__nota">
                    <span class="notas-tarjeta__valor tono-${tonoNota(nota)}">${formatearNota(nota)}</span>
                    <div class="notas-tarjeta__nota-detalle">
                        <span class="etiqueta etiqueta--${calculo.aprobada ? "baja" : "media"}">
                            ${escapar(estadoAsignatura(calculo))}
                        </span>
                        <small>${calculo.evaluadas || 0}/${calculo.total_evaluaciones || 0} evaluaciones</small>
                    </div>
                </div>
                <div class="notas-tarjeta__avance">
                    <div class="notas-tarjeta__avance-texto">
                        <span>Peso evaluado</span>
                        <span>${formatearNota(peso)} %</span>
                    </div>
                    <div class="barra-progreso barra-progreso--mini">
                        <span class="barra-progreso__relleno" style="width:${peso}%"></span>
                    </div>
                </div>
                <p class="notas-tarjeta__mensaje notas-tarjeta__mensaje--${mensaje.tono}">
                    ${icono(mensaje.tono === "peligro" ? "alerta" : mensaje.tono === "exito" ? "exito" : "objetivo")}
                    ${escapar(mensaje.texto)}
                </p>
                <footer class="notas-tarjeta__pie">
                    <span>${icono("calendario")} ${asignatura.eventos_pendientes || 0} eventos pendientes</span>
                    <span class="notas-tarjeta__abrir">Ver desglose ${icono("flechaDerecha")}</span>
                </footer>
            </article>`;
    }

    /** Plantilla principal. */
    function plantilla() {
        const asignaturas = ESTADO.expediente?.asignaturas || [];
        const contenido = asignaturas.length
            ? `<div class="notas-rejilla">${asignaturas.map(tarjetaAsignatura).join("")}</div>`
            : U.vacio(
                "asignaturas",
                "Todavía no hay asignaturas",
                "Crea tu primera materia para empezar a registrar evaluaciones y notas.",
                '<button class="boton boton--primario" type="button" data-nueva-asignatura>Crear asignatura</button>'
            );
        return `
            <div class="notas">
                ${heroe()}
                <div class="notas-barra">
                    <div>
                        <h2 class="notas-barra__titulo">Mis asignaturas</h2>
                        <p class="notas-barra__detalle">Pulsa una tarjeta para abrir la calculadora y el desglose de notas.</p>
                    </div>
                    <div class="notas-barra__acciones">
                        <button class="boton boton--fantasma boton--pequeno" type="button" data-nueva-evaluacion>
                            ${icono("nota")} Añadir nota
                        </button>
                        <button class="boton boton--primario boton--pequeno" type="button" data-nueva-asignatura>
                            ${icono("mas")} Nueva asignatura
                        </button>
                    </div>
                </div>
                ${contenido}
            </div>`;
    }

    /* ------------------------------------------------------------------
       Carga
       ------------------------------------------------------------------ */
    /** Descarga el expediente completo. */
    async function cargar() {
        if (ESTADO.cargando) {
            return;
        }
        ESTADO.cargando = true;
        try {
            ESTADO.expediente = await global.PuenteAgenda.obtener(
                "obtener_expediente", ESTADO.objetivo
            );
        } catch (error) {
            ESTADO.contexto.toast("No se pudo cargar el expediente", String(error.message || error), "error");
        } finally {
            ESTADO.cargando = false;
        }
    }

    /** Repinta la vista y reabre la ficha si estaba abierta. */
    async function recargar() {
        if (!ESTADO.raiz) {
            return;
        }
        await cargar();
        ESTADO.raiz.innerHTML = plantilla();
        conectar();
        if (ESTADO.asignaturaAbierta) {
            const existe = (ESTADO.expediente?.asignaturas || []).some(
                (asignatura) => Number(asignatura.id) === Number(ESTADO.asignaturaAbierta)
            );
            if (existe) {
                await abrirDetalle(ESTADO.asignaturaAbierta, true);
            } else {
                cerrarDetalle();
            }
        }
    }

    /* ------------------------------------------------------------------
       Interacción principal
       ------------------------------------------------------------------ */
    /** Conecta los controles de la vista. */
    function conectar() {
        const raiz = ESTADO.raiz;
        if (!raiz) {
            return;
        }
        raiz.querySelectorAll("[data-nueva-asignatura]").forEach((boton) => {
            boton.addEventListener("click", () => ESTADO.contexto.abrirModal("asignatura"));
        });

        raiz.querySelectorAll("[data-nueva-evaluacion]").forEach((boton) => {
            boton.addEventListener("click", () => {
                const primera = ESTADO.expediente?.asignaturas?.[0];
                ESTADO.contexto.abrirModal("evaluacion", {
                    asignatura_id: primera?.id || ""
                });
            });
        });

        raiz.querySelectorAll(".notas-tarjeta").forEach((tarjeta) => {
            tarjeta.addEventListener("click", () => abrirDetalle(Number(tarjeta.dataset.asignatura)));
        });

        const rangoGlobal = raiz.querySelector("[data-objetivo-global]");
        rangoGlobal?.addEventListener("input", (evento) => {
            ESTADO.objetivo = Number(evento.target.value);
            const etiqueta = raiz.querySelector("#objetivo-valor");
            if (etiqueta) {
                etiqueta.textContent = formatearNota(ESTADO.objetivo);
            }
        });
        rangoGlobal?.addEventListener("change", () => recargar());
    }

    /* ------------------------------------------------------------------
       Ficha lateral
       ------------------------------------------------------------------ */
    /**
     * Abre el detalle de una asignatura.
     * @param {number} identificador Identificador.
     * @param {boolean} [silencioso] Evita animar si ya estaba abierta.
     */
    async function abrirDetalle(identificador, silencioso = false) {
        cerrarDetalle(false, true);
        ESTADO.asignaturaAbierta = identificador;
        const asignatura = (ESTADO.expediente?.asignaturas || []).find(
            (elemento) => Number(elemento.id) === Number(identificador)
        );
        if (!asignatura) {
            return;
        }
        let datos;
        let calculo;
        try {
            [datos, calculo] = await Promise.all([
                global.PuenteAgenda.obtener("listar_evaluaciones", identificador),
                global.PuenteAgenda.obtener("calcular_escenario", identificador, ESTADO.objetivo)
            ]);
        } catch (error) {
            ESTADO.contexto.toast("No se pudo abrir la asignatura", String(error.message || error), "error");
            return;
        }
        ESTADO.calculoPanel = calculo;
        const evaluaciones = calculo?.evaluaciones?.length
            ? calculo.evaluaciones
            : (datos?.evaluaciones || []);
        const color = asignatura.color || "var(--acento)";
        const mensaje = mensajeCalculadora(calculo, ESTADO.objetivo);

        const fondo = document.createElement("div");
        fondo.className = "panel-lateral__fondo";
        fondo.dataset.cerrarPanel = "1";

        const panel = document.createElement("aside");
        panel.className = "panel-lateral panel-lateral--notas";
        panel.id = "panel-asignatura";
        panel.style.setProperty("--color-evento", color);
        panel.innerHTML = `
            <header class="panel-lateral__cabecera">
                <span class="panel-evento__icono" style="--color-evento:${color}">
                    ${icono("asignaturas")}
                </span>
                <div style="min-width:0;flex:1">
                    <p class="panel-evento__tipo">${escapar(asignatura.codigo || "Asignatura")} · ${escapar(asignatura.creditos || 0)} ECTS</p>
                    <h2 class="panel-evento__titulo">${escapar(asignatura.nombre)}</h2>
                    <p class="panel-evento__materia">${escapar(asignatura.profesor || "Profesorado sin asignar")}</p>
                </div>
                <button class="modal__cerrar" type="button" data-cerrar-panel aria-label="Cerrar detalle">
                    ${icono("x")}
                </button>
            </header>
            <div class="panel-lateral__cuerpo">
                <div class="notas-panel__resumen">
                    <div class="notas-panel__dato">
                        <span>Nota provisional</span>
                        <strong class="tono-${tonoNota(calculo.nota_provisional)}">${formatearNota(calculo.nota_provisional)}</strong>
                    </div>
                    <div class="notas-panel__dato">
                        <span>Media evaluada</span>
                        <strong class="tono-${tonoNota(calculo.media_actual)}">${formatearNota(calculo.media_actual)}</strong>
                    </div>
                    <div class="notas-panel__dato">
                        <span>Peso evaluado</span>
                        <strong>${formatearNota(calculo.peso_evaluado)} %</strong>
                    </div>
                </div>

                <div class="notas-calculadora">
                    <div class="notas-calculadora__cabecera">
                        <span>${icono("objetivo")} Calculadora de meta</span>
                        <strong id="panel-objetivo">${formatearNota(ESTADO.objetivo)}</strong>
                    </div>
                    <input class="notas-objetivo__rango" type="range" min="5" max="10" step="0.5"
                           value="${ESTADO.objetivo}" data-objetivo-panel
                           aria-label="Nota objetivo de la asignatura">
                    <p class="notas-calculadora__mensaje notas-tarjeta__mensaje--${mensaje.tono}">
                        ${icono("rayo")} <span data-mensaje-calculadora>${escapar(mensaje.texto)}</span>
                    </p>
                </div>

                <div class="notas-panel__evaluaciones-cabecera">
                    <h3 class="panel-evento__subtitulo">${icono("nota")} Evaluaciones</h3>
                    <button class="boton boton--fantasma boton--pequeno" type="button" data-anadir-evaluacion>
                        ${icono("mas")} Añadir
                    </button>
                </div>

                <div class="notas-panel__pesos">
                    <div class="notas-panel__pesos-texto">
                        <span>Peso total configurado</span>
                        <span class="${calculo.peso_total > 100 ? "texto-peligro" : ""}">${formatearNota(calculo.peso_total)} %</span>
                    </div>
                    <div class="barra-progreso barra-progreso--mini">
                        <span class="barra-progreso__relleno" style="width:${limitar(calculo.peso_total || 0, 0, 100)}%"></span>
                    </div>
                </div>

                <div class="notas-evaluaciones">
                    ${evaluaciones.length ? evaluaciones.map((evaluacion) => filaEvaluacion(evaluacion)).join("") : `
                        <div class="notas-evaluaciones__vacio">
                            ${icono("nota")}
                            <p>Aún no hay evaluaciones</p>
                            <span>Añade exámenes, prácticas o proyectos con su peso.</span>
                        </div>`}
                </div>
            </div>
            <footer class="panel-lateral__pie">
                <button class="boton boton--primario boton--pequeno" type="button" data-editar-asignatura>
                    ${icono("editar")} Editar materia
                </button>
                <button class="boton boton--peligro boton--pequeno" type="button" data-eliminar-asignatura>
                    ${icono("basura")} Eliminar
                </button>
            </footer>`;

        document.body.append(fondo, panel);
        ESTADO.panel = { panel, fondo };
        if (!silencioso) {
            global.requestAnimationFrame(() => {
                panel.classList.add("abierto");
                fondo.classList.add("visible");
            });
        } else {
            panel.classList.add("abierto");
            fondo.classList.add("visible");
        }

        fondo.addEventListener("click", () => cerrarDetalle());
        panel.querySelector("[data-cerrar-panel]").addEventListener("click", () => cerrarDetalle());

        panel.querySelector("[data-anadir-evaluacion]").addEventListener("click", () => {
            ESTADO.contexto.abrirModal("evaluacion", { asignatura_id: asignatura.id });
        });

        panel.querySelectorAll("[data-editar-evaluacion]").forEach((boton) => {
            boton.addEventListener("click", (evento) => {
                evento.stopPropagation();
                const evaluacion = evaluaciones.find(
                    (elemento) => Number(elemento.id) === Number(boton.dataset.editarEvaluacion)
                );
                if (evaluacion) {
                    ESTADO.contexto.abrirModal("evaluacion", evaluacion);
                }
            });
        });

        panel.querySelectorAll(".notas-evaluacion").forEach((fila) => {
            fila.addEventListener("click", () => {
                const evaluacion = evaluaciones.find(
                    (elemento) => Number(elemento.id) === Number(fila.dataset.evaluacion)
                );
                if (evaluacion) {
                    ESTADO.contexto.abrirModal("evaluacion", evaluacion);
                }
            });
        });

        panel.querySelectorAll("[data-borrar-evaluacion]").forEach((boton) => {
            boton.addEventListener("click", async (evento) => {
                evento.stopPropagation();
                try {
                    await global.PuenteAgenda.obtener(
                        "eliminar_evaluacion", Number(boton.dataset.borrarEvaluacion)
                    );
                    ESTADO.contexto.toast("Evaluación eliminada", asignatura.nombre, "info", 2400);
                    await recargar();
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo eliminar", String(error.message || error), "error");
                }
            });
        });

        panel.querySelector("[data-objetivo-panel]").addEventListener("input", (evento) => {
            const objetivo = Number(evento.target.value);
            ESTADO.objetivo = objetivo;
            const etiqueta = panel.querySelector("#panel-objetivo");
            if (etiqueta) {
                etiqueta.textContent = formatearNota(objetivo);
            }
            global.clearTimeout(ESTADO.temporizador);
            ESTADO.temporizador = global.setTimeout(async () => {
                try {
                    const nuevo = await global.PuenteAgenda.obtener(
                        "calcular_escenario", asignatura.id, objetivo
                    );
                    ESTADO.calculoPanel = nuevo;
                    const mensajeNuevo = mensajeCalculadora(nuevo, objetivo);
                    panel.querySelector("[data-mensaje-calculadora]").textContent = mensajeNuevo.texto;
                    panel.querySelector("[data-mensaje-calculadora]").parentElement.className =
                        `notas-calculadora__mensaje notas-tarjeta__mensaje--${mensajeNuevo.tono}`;
                } catch (error) {
                    ESTADO.contexto.toast("No se pudo recalcular", String(error.message || error), "error");
                }
            }, 160);
        });

        panel.querySelector("[data-editar-asignatura]").addEventListener("click", () => {
            cerrarDetalle();
            ESTADO.contexto.abrirModal("asignatura", { ...asignatura, id: asignatura.id });
        });

        const botonEliminar = panel.querySelector("[data-eliminar-asignatura]");
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
                await global.PuenteAgenda.obtener("eliminar_asignatura", asignatura.id);
                ESTADO.contexto.toast("Asignatura eliminada", asignatura.nombre, "info", 2600);
                ESTADO.asignaturaAbierta = null;
                cerrarDetalle();
                await recargar();
            } catch (error) {
                ESTADO.contexto.toast("No se pudo eliminar", String(error.message || error), "error");
            }
        });
    }

    /**
     * Fila de una evaluación dentro de la ficha.
     * @param {object} evaluacion Evaluación serializada.
     * @returns {string} HTML de la fila.
     */
    function filaEvaluacion(evaluacion) {
        const tipo = TIPOS_EVALUACION[evaluacion.tipo] || TIPOS_EVALUACION.examen;
        const nota = evaluacion.nota_sobre_diez ?? null;
        const fecha = evaluacion.fecha
            ? fechaCorta(evaluacion.fecha, { day: "numeric", month: "short" })
            : "";
        return `
            <div class="notas-evaluacion" data-evaluacion="${Number(evaluacion.id)}">
                <span class="notas-evaluacion__icono">${icono(tipo.icono)}</span>
                <div class="notas-evaluacion__texto">
                    <p class="notas-evaluacion__nombre">${escapar(evaluacion.nombre)}</p>
                    <p class="notas-evaluacion__meta">
                        ${escapar(tipo.etiqueta)} · ${formatearNota(evaluacion.peso)} %
                        ${fecha ? ` · ${escapar(fecha)}` : ""}
                    </p>
                </div>
                <span class="notas-evaluacion__nota tono-${tonoNota(nota)}">
                    ${formatearNota(nota)}
                </span>
                <button class="notas-evaluacion__accion" type="button"
                        data-editar-evaluacion="${Number(evaluacion.id)}"
                        aria-label="Editar evaluación">${icono("editar")}</button>
                <button class="notas-evaluacion__accion notas-evaluacion__accion--borrar" type="button"
                        data-borrar-evaluacion="${Number(evaluacion.id)}"
                        aria-label="Eliminar evaluación">${icono("basura")}</button>
            </div>`;
    }

    /**
     * Cierra la ficha lateral.
     * @param {boolean} [olvidar] Si debe limpiar la asignatura activa.
     * @param {boolean} [inmediato] Si debe retirar el panel sin transición.
     */
    function cerrarDetalle(olvidar = true, inmediato = false) {
        if (olvidar) {
            ESTADO.asignaturaAbierta = null;
        }
        if (!ESTADO.panel) {
            return;
        }
        const { panel, fondo } = ESTADO.panel;
        ESTADO.panel = null;
        panel.classList.remove("abierto");
        fondo.classList.remove("visible");
        if (inmediato) {
            panel.remove();
            fondo.remove();
            return;
        }
        global.setTimeout(() => {
            panel.remove();
            fondo.remove();
        }, 260);
    }

    /* ------------------------------------------------------------------
       Ciclo de vida
       ------------------------------------------------------------------ */
    /**
     * Monta la vista de asignaturas.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto de la aplicación.
     */
    async function montar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        await recargar();
    }

    /**
     * Actualiza la vista cuando cambian los datos globales.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto de la aplicación.
     */
    async function actualizar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        await recargar();
    }

    global.AgendaApp.registrarVista("asignaturas", { montar, actualizar });
})(window);
