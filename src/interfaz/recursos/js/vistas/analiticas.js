/**
 * ============================================================================
 *  VISTA ANALÍTICAS · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Informe visual del estudio y del rendimiento académico:
 *
 *  * Serie temporal de minutos estudiados con gráfico SVG y área degradada.
 *  * Reparto del tiempo por asignatura en un anillo construido con CSS.
 *  * Mapa de calor de ocho semanas, franjas horarias y estado de las tareas.
 *  * Consejo dinámico según la constancia y las entregas pendientes.
 *
 *  Se puede cambiar el periodo (7, 14 o 30 días) con botones de ratón.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { escapar, icono, limitar, fechaCorta } = U;

    const ESTADO = {
        dias: 14,
        datos: null,
        raiz: null,
        contexto: null,
        cargando: false
    };

    const PALETA_REPARTO = ["#7c6cff", "#34e2c4", "#4aa8ff", "#ffc857", "#ff5f7a", "#b07cff"];

    /* ------------------------------------------------------------------
       Formato
       ------------------------------------------------------------------ */
    /**
     * Convierte minutos en un texto de horas legible.
     * @param {number} minutos Minutos.
     * @returns {string} Texto como `12 h 30 min`.
     */
    function horas(minutos) {
        const total = Math.max(0, Math.round(Number(minutos) || 0));
        const h = Math.floor(total / 60);
        const m = total % 60;
        if (!h) {
            return `${m} min`;
        }
        return m ? `${h} h ${m} min` : `${h} h`;
    }

    /* ------------------------------------------------------------------
       Gráfico SVG
       ------------------------------------------------------------------ */
    /**
     * Construye el gráfico de área de la serie diaria.
     * @param {object[]} serie Puntos con `minutos` y `etiqueta`.
     * @returns {string} SVG listo para insertar.
     */
    function graficoSerie(serie) {
        if (!serie.length) {
            return U.vacio("grafico", "Sin datos todavía", "Estudia un bloque para empezar la serie.");
        }
        const ancho = 760;
        const alto = 250;
        const margenIzquierda = 34;
        const margenDerecha = 16;
        const margenSuperior = 18;
        const margenInferior = 34;
        const anchoUtil = ancho - margenIzquierda - margenDerecha;
        const altoUtil = alto - margenSuperior - margenInferior;
        const maximo = Math.max(60, ...serie.map((punto) => Number(punto.minutos) || 0));
        const paso = serie.length > 1 ? anchoUtil / (serie.length - 1) : 0;

        const puntos = serie.map((punto, indice) => {
            const x = margenIzquierda + indice * paso;
            const y = margenSuperior + altoUtil - ((Number(punto.minutos) || 0) / maximo) * altoUtil;
            return { x, y, ...punto };
        });
        const linea = puntos
            .map((punto, indice) => `${indice === 0 ? "M" : "L"}${punto.x.toFixed(1)} ${punto.y.toFixed(1)}`)
            .join(" ");
        const area = `${linea} L${puntos.at(-1).x.toFixed(1)} ${margenSuperior + altoUtil} L${puntos[0].x.toFixed(1)} ${margenSuperior + altoUtil} Z`;

        const guias = [0, 0.25, 0.5, 0.75, 1].map((fraccion) => {
            const y = margenSuperior + altoUtil * fraccion;
            const valor = Math.round(maximo * (1 - fraccion));
            return `
                <line x1="${margenIzquierda}" y1="${y}" x2="${ancho - margenDerecha}" y2="${y}"
                      stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="3 5"/>
                <text x="${margenIzquierda - 8}" y="${y + 4}" text-anchor="end"
                      fill="currentColor" fill-opacity="0.4" font-size="10">${valor}</text>`;
        }).join("");

        const etiquetas = serie.map((punto, indice) => {
            const mostrar = serie.length <= 14 || indice % 3 === 0 || indice === serie.length - 1;
            if (!mostrar) {
                return "";
            }
            const x = margenIzquierda + indice * paso;
            return `<text x="${x}" y="${alto - 12}" text-anchor="middle"
                          fill="currentColor" fill-opacity="0.42" font-size="10">${escapar(punto.etiqueta.split(" ")[1] || "")}</text>`;
        }).join("");

        const circulos = puntos.map((punto) => `
            <g class="analiticas-punto">
                <circle cx="${punto.x}" cy="${punto.y}" r="9" fill="transparent">
                    <title>${escapar(punto.etiqueta)}: ${horas(punto.minutos)}</title>
                </circle>
                <circle cx="${punto.x}" cy="${punto.y}" r="3.4"
                        fill="var(--acento-secundario)" stroke="var(--fondo-secundario)" stroke-width="2"/>
            </g>`).join("");

        return `
            <svg class="analiticas-grafico" viewBox="0 0 ${ancho} ${alto}"
                 role="img" aria-label="Minutos de estudio por día">
                <defs>
                    <linearGradient id="area-estudio" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="var(--acento)" stop-opacity="0.38"/>
                        <stop offset="100%" stop-color="var(--acento)" stop-opacity="0"/>
                    </linearGradient>
                    <linearGradient id="linea-estudio" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stop-color="var(--acento)"/>
                        <stop offset="60%" stop-color="var(--color-informacion)"/>
                        <stop offset="100%" stop-color="var(--acento-secundario)"/>
                    </linearGradient>
                </defs>
                ${guias}
                <path d="${area}" fill="url(#area-estudio)"/>
                <path d="${linea}" fill="none" stroke="url(#linea-estudio)" stroke-width="2.6"
                      stroke-linecap="round" stroke-linejoin="round"/>
                ${circulos}
                ${etiquetas}
            </svg>`;
    }

    /* ------------------------------------------------------------------
       Anillo por asignatura
       ------------------------------------------------------------------ */
    /**
     * Genera el degradado cónico del reparto por asignatura.
     * @param {object[]} reparto Asignaturas con porcentaje.
     * @returns {string} Valor CSS para `background`.
     */
    function conico(reparto) {
        if (!reparto.length) {
            return "conic-gradient(color-mix(in srgb, var(--texto-primario) 8%, transparent) 0 100%)";
        }
        let acumulado = 0;
        const paradas = reparto.map((elemento, indice) => {
            const desde = acumulado;
            acumulado += Number(elemento.porcentaje) || 0;
            const color = elemento.color && elemento.color !== "#8a8fa8"
                ? elemento.color
                : PALETA_REPARTO[indice % PALETA_REPARTO.length];
            return `${color} ${desde}% ${acumulado}%`;
        });
        if (acumulado < 100) {
            paradas.push(`color-mix(in srgb, var(--texto-primario) 8%, transparent) ${acumulado}% 100%`);
        }
        return `conic-gradient(${paradas.join(", ")})`;
    }

    /**
     * Tarjeta de reparto por asignatura.
     * @returns {string} HTML de la tarjeta.
     */
    function tarjetaReparto() {
        const reparto = ESTADO.datos?.por_asignatura || [];
        const total = ESTADO.datos?.kpis?.total_minutos || 0;
        const valorCentro = total >= 60 ? (total / 60).toFixed(1) : total;
        const unidadCentro = total >= 60 ? "horas" : "minutos";
        return `
            <section class="tarjeta analiticas-panel analiticas-reparto">
                <header class="analiticas-panel__cabecera">
                    <div>
                        <h2>${icono("capas")} Reparto por asignatura</h2>
                        <p>Dónde se va tu tiempo de estudio.</p>
                    </div>
                </header>
                <div class="analiticas-reparto__cuerpo">
                    <div class="analiticas-donut" style="--reparto:${conico(reparto)}">
                        <div class="analiticas-donut__centro">
                            <strong>${valorCentro}</strong>
                            <span>${unidadCentro}</span>
                        </div>
                    </div>
                    <div class="analiticas-leyenda">
                        ${reparto.length ? reparto.slice(0, 6).map((elemento, indice) => `
                            <div class="analiticas-leyenda__fila">
                                <span class="analiticas-leyenda__punto"
                                      style="background:${elemento.color && elemento.color !== "#8a8fa8" ? elemento.color : PALETA_REPARTO[indice % PALETA_REPARTO.length]}"></span>
                                <span class="analiticas-leyenda__nombre" title="${escapar(elemento.asignatura)}">${escapar(elemento.asignatura)}</span>
                                <span class="analiticas-leyenda__valor">${horas(elemento.minutos)}</span>
                            </div>`).join("") : `
                            <p class="analiticas-vacio">Aún no hay sesiones asociadas a asignaturas.</p>`}
                    </div>
                </div>
            </section>`;
    }

    /* ------------------------------------------------------------------
       Mapa de calor y franjas
       ------------------------------------------------------------------ */
    /** Tarjeta del mapa de calor de ocho semanas. */
    function tarjetaMapaCalor() {
        const celdas = ESTADO.datos?.mapa_calor || [];
        return `
            <section class="tarjeta analiticas-panel analiticas-calor">
                <header class="analiticas-panel__cabecera">
                    <div>
                        <h2>${icono("fuego")} Constancia de las últimas 8 semanas</h2>
                        <p>Cada cuadro es un día; más intensidad, más minutos.</p>
                    </div>
                    <div class="analiticas-calor__escala">
                        <span>Menos</span>
                        ${[0, 1, 2, 3, 4].map((nivel) => `<i class="nivel-${nivel}"></i>`).join("")}
                        <span>Más</span>
                    </div>
                </header>
                <div class="analiticas-calor__cuerpo">
                    <div class="analiticas-calor__dias">
                        <span>Lun</span><span></span><span>Mié</span><span></span><span>Vie</span><span></span><span>Dom</span>
                    </div>
                    <div class="analiticas-calor__rejilla">
                        ${celdas.map((celda) => `
                            <button class="analiticas-celda nivel-${celda.nivel}" type="button"
                                    title="${escapar(celda.dia)} · ${horas(celda.minutos)}"
                                    aria-label="${escapar(celda.dia)}: ${horas(celda.minutos)}"></button>`).join("")}
                    </div>
                </div>
            </section>`;
    }

    /** Tarjeta de franjas horarias. */
    function tarjetaFranjas() {
        const franjas = ESTADO.datos?.franjas || [];
        const maximo = Math.max(1, ...franjas.map((franja) => franja.minutos));
        return `
            <section class="tarjeta analiticas-panel analiticas-franjas">
                <header class="analiticas-panel__cabecera">
                    <div>
                        <h2>${icono("reloj")} Momento del día</h2>
                        <p>Cuándo rindes mejor.</p>
                    </div>
                </header>
                <div class="analiticas-franjas__cuerpo">
                    ${franjas.map((franja) => `
                        <div class="analiticas-franja">
                            <div class="analiticas-franja__barra">
                                <span style="height:${Math.max(4, (franja.minutos / maximo) * 100)}%"></span>
                            </div>
                            <strong>${escapar(franja.etiqueta.slice(0, 3))}</strong>
                            <small>${horas(franja.minutos)}</small>
                        </div>`).join("")}
                </div>
            </section>`;
    }

    /* ------------------------------------------------------------------
       Estado académico
       ------------------------------------------------------------------ */
    /** Tarjeta de tareas y entregas. */
    function tarjetaAcademico() {
        const academico = ESTADO.datos?.academico || {};
        const tasa = limitar(Number(academico.tasa) || 0, 0, 100);
        return `
            <section class="tarjeta analiticas-panel analiticas-academico">
                <header class="analiticas-panel__cabecera">
                    <div>
                        <h2>${icono("check")} Pulso académico</h2>
                        <p>Tareas, entregas y exámenes.</p>
                    </div>
                </header>
                <div class="analiticas-academico__tasa">
                    <div class="analiticas-academico__anillo" style="--tasa:${tasa}%">
                        <strong>${tasa}%</strong>
                    </div>
                    <div>
                        <p class="analiticas-academico__titulo">${academico.completadas || 0} de ${academico.total || 0} cerradas</p>
                        <p class="analiticas-academico__detalle">${academico.pendientes || 0} pendientes · ${academico.vencidas || 0} vencidas</p>
                    </div>
                </div>
                <div class="analiticas-academico__filas">
                    <div><span>Completadas</span><strong class="tono-sobresaliente">${academico.completadas || 0}</strong></div>
                    <div><span>Pendientes</span><strong class="tono-aprobada">${academico.pendientes || 0}</strong></div>
                    <div><span>Vencidas</span><strong class="tono-suspensa">${academico.vencidas || 0}</strong></div>
                    <div><span>Asignaturas</span><strong>${academico.asignaturas || 0}</strong></div>
                </div>
            </section>`;
    }

    /* ------------------------------------------------------------------
       Plantilla general
       ------------------------------------------------------------------ */
    /** Plantilla completa. */
    function plantilla() {
        const kpis = ESTADO.datos?.kpis || {};
        const variacion = Number(kpis.variacion_semanal) || 0;
        const mejor = kpis.mejor_dia || { etiqueta: "—", minutos: 0 };
        const modos = ESTADO.datos?.modos || [];
        return `
            <div class="analiticas">
                <section class="analiticas-heroe">
                    <div class="analiticas-heroe__principal">
                        <p class="analiticas-heroe__etiqueta">${icono("analiticas")} Informe de estudio</p>
                        <h2 class="analiticas-heroe__cifra">${horas(kpis.total_minutos || 0)}</h2>
                        <p class="analiticas-heroe__detalle">
                            en los últimos ${ESTADO.dias} días ·
                            <span class="${variacion >= 0 ? "tono-sobresaliente" : "tono-suspensa"}">
                                ${variacion >= 0 ? "+" : ""}${variacion}% frente a la semana anterior
                            </span>
                        </p>
                        <div class="analiticas-heroe__insignias">
                            <span>${icono("fuego")} Racha de ${kpis.racha || 0} días</span>
                            <span>${icono("trofeo")} Mejor día: ${escapar(mejor.etiqueta)} · ${horas(mejor.minutos)}</span>
                            <span>${icono("rayo")} ${kpis.sesiones || 0} bloques</span>
                        </div>
                    </div>
                    <div class="analiticas-periodo" role="group" aria-label="Periodo del informe">
                        ${[7, 14, 30].map((dias) => `
                            <button class="segmentado__opcion ${ESTADO.dias === dias ? "activo" : ""}"
                                    type="button" data-periodo="${dias}">
                                ${dias} días
                            </button>`).join("")}
                    </div>
                </section>

                <div class="analiticas-kpis">
                    ${[
                        { icono: "reloj", valor: horas(kpis.total_minutos || 0), etiqueta: "Tiempo estudiado", tono: "var(--color-informacion)" },
                        { icono: "grafico", valor: `${kpis.media_diaria || 0} min`, etiqueta: "Media diaria", tono: "var(--acento)" },
                        { icono: "fuego", valor: `${kpis.racha || 0} días`, etiqueta: "Racha actual", tono: "var(--color-aviso)" },
                        { icono: "objetivo", valor: `${kpis.promedio_sesion || 0} min`, etiqueta: "Sesión media", tono: "var(--color-exito)" }
                    ].map((kpi) => `
                        <article class="analiticas-kpi">
                            <span class="analiticas-kpi__icono" style="--tono:${kpi.tono}">${icono(kpi.icono)}</span>
                            <div>
                                <p class="analiticas-kpi__valor">${escapar(kpi.valor)}</p>
                                <p class="analiticas-kpi__etiqueta">${escapar(kpi.etiqueta)}</p>
                            </div>
                        </article>`).join("")}
                </div>

                <div class="analiticas-rejilla">
                    <section class="tarjeta analiticas-panel analiticas-serie">
                        <header class="analiticas-panel__cabecera">
                            <div>
                                <h2>${icono("grafico")} Ritmo de estudio</h2>
                                <p>Minutos concentrados cada día del periodo.</p>
                            </div>
                            <span class="analiticas-panel__insignia">${ESTADO.datos?.periodo?.desde || ""} → ${ESTADO.datos?.periodo?.hasta || ""}</span>
                        </header>
                        ${graficoSerie(ESTADO.datos?.por_dia || [])}
                    </section>
                    ${tarjetaReparto()}
                    ${tarjetaMapaCalor()}
                    ${tarjetaFranjas()}
                    ${tarjetaAcademico()}
                </div>

                <section class="analiticas-consejo">
                    <span class="analiticas-consejo__icono">${icono("rayo")}</span>
                    <div>
                        <h3>Recomendación de la semana</h3>
                        <p>${escapar(ESTADO.datos?.consejo || "Registra tus primeras sesiones para recibir recomendaciones.")}</p>
                    </div>
                    <div class="analiticas-consejo__modos">
                        ${modos.length ? modos.map((modo) => `
                            <span class="etiqueta etiqueta--media">${escapar(modo.modo)} · ${modo.sesiones}</span>`).join("") : ""}
                    </div>
                </section>
            </div>`;
    }

    /* ------------------------------------------------------------------
       Datos e interacción
       ------------------------------------------------------------------ */
    /** Descarga el informe. */
    async function cargar() {
        if (ESTADO.cargando) {
            return;
        }
        ESTADO.cargando = true;
        try {
            ESTADO.datos = await global.PuenteAgenda.obtener("obtener_analiticas", ESTADO.dias);
        } catch (error) {
            ESTADO.contexto.toast("No se pudieron cargar las analíticas", String(error.message || error), "error");
        } finally {
            ESTADO.cargando = false;
        }
    }

    /** Repinta la vista. */
    async function recargar() {
        if (!ESTADO.raiz) {
            return;
        }
        await cargar();
        ESTADO.raiz.innerHTML = plantilla();
        conectar();
    }

    /** Conecta los botones de periodo. */
    function conectar() {
        ESTADO.raiz?.querySelectorAll("[data-periodo]").forEach((boton) => {
            boton.addEventListener("click", async () => {
                ESTADO.dias = Number(boton.dataset.periodo) || 14;
                await recargar();
            });
        });
    }

    /* ------------------------------------------------------------------
       Ciclo de vida
       ------------------------------------------------------------------ */
    /**
     * Monta la vista de analíticas.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto.
     */
    async function montar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        await recargar();
    }

    /**
     * Refresca cuando cambian los datos globales.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto.
     */
    async function actualizar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        await recargar();
    }

    global.AgendaApp.registrarVista("analiticas", { montar, actualizar });
})(window);
