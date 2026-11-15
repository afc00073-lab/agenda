/**
 * ============================================================================
 *  VISTA POMODORO · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Un temporizador de concentración con anillo SVG, tres modos de trabajo,
 *  selección de asignatura, notas de sesión y un resumen del día.
 *
 *  El reloj real vive en Python: `tick_pomodoro` avanza cada segundo y emite
 *  `pomodoroActualizado`. La vista solo pinta el estado recibido, de modo que
 *  el temporizador sigue funcionando aunque se cambie de pestaña.
 *
 *  Sin atajos de teclado: todos los controles son botones, deslizadores y
 *  selectores manejables con el ratón.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { escapar, icono, horaCorta, fechaCorta, limitar } = U;

    const MODOS = {
        "25/5": { trabajo: 25, descanso: 5, etiqueta: "Enfoque clásico" },
        "50/10": { trabajo: 50, descanso: 10, etiqueta: "Sesión profunda" },
        personalizado: { trabajo: 40, descanso: 8, etiqueta: "A tu medida" }
    };

    const ESTADO = {
        modo: "25/5",
        trabajo: 25,
        descanso: 5,
        estado: null,
        analiticas: null,
        sesiones: [],
        raiz: null,
        contexto: null,
        suscrito: false,
        cargando: false
    };

    /* ------------------------------------------------------------------
       Formato
       ------------------------------------------------------------------ */
    /**
     * Convierte segundos a formato `MM:SS`.
     * @param {number} segundos Segundos restantes.
     * @returns {string} Texto del reloj.
     */
    function reloj(segundos) {
        const total = Math.max(0, Math.round(Number(segundos) || 0));
        return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
    }

    /**
     * Describe el tipo de fase.
     * @param {string} fase `trabajo` o `descanso`.
     * @returns {string} Etiqueta legible.
     */
    const etiquetaFase = (fase) => (fase === "descanso" ? "Descanso" : "Concentración");

    /**
     * Resume la duración de una sesión.
     * @param {number} minutos Minutos.
     * @returns {string} Texto como `25 min`.
     */
    const duracion = (minutos) => `${Number(minutos) || 0} min`;

    /* ------------------------------------------------------------------
       Plantillas
       ------------------------------------------------------------------ */
    /** Opciones de asignatura para el selector. */
    function opcionesAsignaturas() {
        const asignaturas = ESTADO.contexto?.asignaturas || [];
        return [
            '<option value="">Sin asignatura</option>',
            ...asignaturas.map(
                (asignatura) =>
                    `<option value="${asignatura.id}">${escapar(asignatura.nombre)}</option>`
            )
        ].join("");
    }

    /**
     * Anillo SVG del temporizador.
     * @param {object|null} estado Estado actual.
     * @returns {string} HTML del anillo.
     */
    function anillo(estado) {
        const activo = Boolean(estado?.activo);
        const progreso = activo ? limitar(Number(estado.progreso) || 0, 0, 1) : 0;
        const circunferencia = 2 * Math.PI * 96;
        const desplazamiento = circunferencia * (1 - progreso);
        const descanso = estado?.fase === "descanso";
        return `
            <div class="pomodoro__anillo ${descanso ? "pomodoro__anillo--descanso" : ""}">
                <svg viewBox="0 0 220 220" role="img" aria-label="Progreso del temporizador">
                    <defs>
                        <linearGradient id="gradiente-pomodoro" x1="0" y1="0" x2="1" y2="1">
                            <stop offset="0%" stop-color="var(--acento)"/>
                            <stop offset="60%" stop-color="var(--color-informacion)"/>
                            <stop offset="100%" stop-color="var(--acento-secundario)"/>
                        </linearGradient>
                        <linearGradient id="gradiente-descanso" x1="0" y1="0" x2="1" y2="1">
                            <stop offset="0%" stop-color="var(--acento-secundario)"/>
                            <stop offset="100%" stop-color="var(--color-aviso)"/>
                        </linearGradient>
                    </defs>
                    <circle class="pomodoro__pista" cx="110" cy="110" r="96"/>
                    <circle class="pomodoro__progreso" cx="110" cy="110" r="96"
                            stroke="${descanso ? "url(#gradiente-descanso)" : "url(#gradiente-pomodoro)"}"
                            stroke-dasharray="${circunferencia.toFixed(2)}"
                            stroke-dashoffset="${desplazamiento.toFixed(2)}"
                            transform="rotate(-90 110 110)"/>
                </svg>
                <div class="pomodoro__centro">
                    <span class="pomodoro__fase">
                        <span class="pomodoro__punto"></span>
                        ${activo ? escapar(etiquetaFase(estado.fase)) : "Listo para empezar"}
                    </span>
                    <strong class="pomodoro__tiempo" id="pomodoro-tiempo">
                        ${reloj(activo ? estado.restante_segundos : ESTADO.trabajo * 60)}
                    </strong>
                    <small class="pomodoro__detalle" id="pomodoro-detalle">
                        ${activo
                            ? `${estado.ciclos_completados} ciclos · ${escapar(estado.modo)}`
                            : `${ESTADO.trabajo} min de trabajo · ${ESTADO.descanso} min de descanso`}
                    </small>
                </div>
            </div>`;
    }

    /**
     * Controles principales bajo el reloj.
     * @param {object|null} estado Estado actual.
     * @returns {string} HTML de los botones.
     */
    function controles(estado) {
        if (!estado?.activo) {
            return `
                <div class="pomodoro__controles">
                    <button class="boton boton--primario pomodoro__iniciar" type="button" data-iniciar>
                        ${icono("reproducir")} Iniciar concentración
                    </button>
                </div>`;
        }
        return `
            <div class="pomodoro__controles">
                <button class="boton boton--primario" type="button" data-pausa>
                    ${icono(estado.pausado ? "reproducir" : "pausa")}
                    ${estado.pausado ? "Reanudar" : "Pausar"}
                </button>
                <button class="boton boton--peligro" type="button" data-finalizar>
                    ${icono("detener")} Terminar
                </button>
            </div>`;
    }

    /** Panel de configuración de la sesión. */
    function configuracion() {
        return `
            <aside class="estudio-config">
                <div class="estudio-config__cabecera">
                    <span class="estudio-config__icono">${icono("estudio")}</span>
                    <div>
                        <h2>Prepara el bloque</h2>
                        <p>Elige ritmo, materia y objetivo.</p>
                    </div>
                </div>

                <div class="estudio-config__campo">
                    <span class="estudio-config__etiqueta">Ritmo de trabajo</span>
                    <div class="segmentado segmentado--modos">
                        ${Object.entries(MODOS).map(([clave, modo]) => `
                            <button class="segmentado__opcion ${ESTADO.modo === clave ? "activo" : ""}"
                                    type="button" data-modo="${clave}">
                                ${clave === "personalizado" ? "A medida" : clave}
                                <small>${escapar(modo.etiqueta)}</small>
                            </button>`).join("")}
                    </div>
                </div>

                <div class="estudio-config__duraciones ${ESTADO.modo === "personalizado" ? "visible" : ""}"
                     data-duraciones>
                    <label class="campo">
                        <span class="campo__etiqueta">Minutos de trabajo</span>
                        <input class="campo__control" type="number" min="5" max="90" step="5"
                               value="${ESTADO.trabajo}" data-trabajo>
                    </label>
                    <label class="campo">
                        <span class="campo__etiqueta">Minutos de descanso</span>
                        <input class="campo__control" type="number" min="1" max="30" step="1"
                               value="${ESTADO.descanso}" data-descanso>
                    </label>
                </div>

                <label class="campo estudio-config__campo">
                    <span class="campo__etiqueta">Asignatura</span>
                    <select class="campo__control" data-asignatura>
                        ${opcionesAsignaturas()}
                    </select>
                </label>

                <label class="campo estudio-config__campo">
                    <span class="campo__etiqueta">¿Qué vas a conseguir?</span>
                    <textarea class="campo__control" rows="2" data-notas
                              placeholder="Terminar los ejercicios 4 y 5…"></textarea>
                </label>

                <p class="estudio-config__ayuda">
                    ${icono("informacion")}
                    El temporizador sigue activo aunque cambies de vista.
                </p>
            </aside>`;
    }

    /**
     * Tarjeta de indicador.
     * @param {object} datos Contenido.
     * @returns {string} HTML.
     */
    function metrica(datos) {
        return `
            <article class="estudio-metrica">
                <span class="estudio-metrica__icono" style="--tono:${datos.tono || "var(--acento)"}">
                    ${icono(datos.icono)}
                </span>
                <div>
                    <p class="estudio-metrica__valor">${escapar(datos.valor)}</p>
                    <p class="estudio-metrica__etiqueta">${escapar(datos.etiqueta)}</p>
                </div>
            </article>`;
    }

    /**
     * Fila de una sesión reciente.
     * @param {object} sesion Sesión.
     * @returns {string} HTML.
     */
    function filaSesion(sesion) {
        const color = sesion.asignatura_color || "var(--acento)";
        return `
            <div class="estudio-sesion" style="--color-sesion:${color}">
                <span class="estudio-sesion__punto"></span>
                <div class="estudio-sesion__texto">
                    <p>${escapar(sesion.asignatura_nombre || "Estudio libre")}</p>
                    <span>${escapar(fechaCorta(sesion.inicio, { weekday: "short", day: "numeric", month: "short" }))}
                        · ${escapar(horaCorta(sesion.inicio))} · ${escapar(sesion.modo)}</span>
                </div>
                <span class="estudio-sesion__duracion">${duracion(sesion.duracion_minutos)}</span>
                ${sesion.completada
                    ? `<span class="estudio-sesion__check">${icono("check")}</span>`
                    : `<span class="estudio-sesion__parcial">Parcial</span>`}
            </div>`;
    }

    /** Plantilla completa. */
    function plantilla() {
        const hoy = ESTADO.analiticas?.por_dia?.at(-1);
        const kpis = ESTADO.analiticas?.kpis || {};
        const estado = ESTADO.estado;
        return `
            <div class="estudio">
                <div class="estudio-heroe">
                    <section class="pomodoro">
                        ${anillo(estado)}
                        ${controles(estado)}
                        <div class="pomodoro__ciclos">
                            ${Array.from({ length: 4 }, (_, indice) => `
                                <span class="pomodoro__ciclo ${(estado?.ciclos_completados || 0) > indice ? "completado" : ""}"></span>`).join("")}
                            <small>${estado?.ciclos_completados || 0} ciclos hoy</small>
                        </div>
                    </section>
                    ${configuracion()}
                </div>

                <div class="estudio-metricas">
                    ${metrica({ icono: "reloj", valor: `${hoy?.minutos || 0} min`, etiqueta: "Estudio hoy", tono: "var(--color-informacion)" })}
                    ${metrica({ icono: "fuego", valor: String(kpis.racha || 0), etiqueta: "Días de racha", tono: "var(--color-aviso)" })}
                    ${metrica({ icono: "trofeo", valor: String(kpis.sesiones || 0), etiqueta: "Sesiones esta semana", tono: "var(--color-exito)" })}
                    ${metrica({ icono: "rayo", valor: `${kpis.promedio_sesion || 0} min`, etiqueta: "Duración media", tono: "var(--acento)" })}
                </div>

                <div class="estudio-grid">
                    <section class="tarjeta estudio-panel">
                        <header class="estudio-panel__cabecera">
                            <div>
                                <h2>${icono("reloj")} Sesiones recientes</h2>
                                <p>Tu historial de concentración.</p>
                            </div>
                            <span class="estudio-panel__insignia">${ESTADO.sesiones.length} bloques</span>
                        </header>
                        <div class="estudio-sesiones">
                            ${ESTADO.sesiones.length
                                ? ESTADO.sesiones.map(filaSesion).join("")
                                : U.vacio("estudio", "Aún no hay sesiones", "Inicia tu primer bloque Pomodoro para verlo aquí.")}
                        </div>
                    </section>

                    <section class="tarjeta estudio-ritual">
                        <header class="estudio-panel__cabecera">
                            <div>
                                <h2>${icono("objetivo")} Ritual de concentración</h2>
                                <p>Pequeños gestos que multiplican el foco.</p>
                            </div>
                        </header>
                        <ol class="estudio-ritual__lista">
                            <li>
                                <span class="estudio-ritual__numero">01</span>
                                <div><strong>Silencia el ruido</strong><p>Cierra pestañas y deja el móvil fuera de la mesa.</p></div>
                            </li>
                            <li>
                                <span class="estudio-ritual__numero">02</span>
                                <div><strong>Define una victoria</strong><p>Escribe en las notas qué quieres terminar al acabar.</p></div>
                            </li>
                            <li>
                                <span class="estudio-ritual__numero">03</span>
                                <div><strong>Respeta el descanso</strong><p>Levántate, mira lejos y vuelve con la mente despejada.</p></div>
                            </li>
                        </ol>
                    </section>
                </div>
            </div>`;
    }

    /* ------------------------------------------------------------------
       Datos y estado
       ------------------------------------------------------------------ */
    /** Recarga analíticas y sesiones recientes. */
    async function cargarResumenes() {
        try {
            const [analiticas, sesiones] = await Promise.all([
                global.PuenteAgenda.obtener("obtener_analiticas", 7),
                global.PuenteAgenda.obtener("listar_sesiones", 8)
            ]);
            ESTADO.analiticas = analiticas;
            ESTADO.sesiones = sesiones || [];
        } catch (error) {
            ESTADO.contexto.toast("No se pudo cargar el resumen", String(error.message || error), "error");
        }
    }

    /** Consulta el estado actual del temporizador. */
    async function cargarEstado() {
        try {
            ESTADO.estado = await global.PuenteAgenda.obtener("estado_pomodoro");
        } catch (error) {
            ESTADO.estado = null;
        }
    }

    /** Repinta solo el reloj y los controles para no perder la configuración. */
    function pintarTemporizador() {
        const raiz = ESTADO.raiz;
        if (!raiz || !raiz.isConnected) {
            return;
        }
        const pomodoro = raiz.querySelector(".pomodoro");
        if (!pomodoro) {
            return;
        }
        pomodoro.innerHTML = `
            ${anillo(ESTADO.estado)}
            ${controles(ESTADO.estado)}
            <div class="pomodoro__ciclos">
                ${Array.from({ length: 4 }, (_, indice) => `
                    <span class="pomodoro__ciclo ${(ESTADO.estado?.ciclos_completados || 0) > indice ? "completado" : ""}"></span>`).join("")}
                <small>${ESTADO.estado?.ciclos_completados || 0} ciclos hoy</small>
            </div>`;
        conectarTemporizador();
    }

    /** Vuelve a pintar toda la vista. */
    async function recargar() {
        if (!ESTADO.raiz) {
            return;
        }
        await Promise.all([cargarEstado(), cargarResumenes()]);
        ESTADO.raiz.innerHTML = plantilla();
        conectar();
    }

    /* ------------------------------------------------------------------
       Interacción
       ------------------------------------------------------------------ */
    /** Conecta los botones del temporizador. */
    function conectarTemporizador() {
        const pomodoro = ESTADO.raiz?.querySelector(".pomodoro");
        if (!pomodoro) {
            return;
        }
        pomodoro.querySelector("[data-iniciar]")?.addEventListener("click", iniciar);
        pomodoro.querySelector("[data-pausa]")?.addEventListener("click", alternarPausa);
        pomodoro.querySelector("[data-finalizar]")?.addEventListener("click", finalizar);
    }

    /** Conecta todos los controles de la vista. */
    function conectar() {
        const raiz = ESTADO.raiz;
        if (!raiz) {
            return;
        }
        conectarTemporizador();

        raiz.querySelectorAll("[data-modo]").forEach((boton) => {
            boton.addEventListener("click", () => {
                ESTADO.modo = boton.dataset.modo;
                const modo = MODOS[ESTADO.modo];
                ESTADO.trabajo = modo.trabajo;
                ESTADO.descanso = modo.descanso;
                raiz.querySelectorAll("[data-modo]").forEach((elemento) =>
                    elemento.classList.toggle("activo", elemento === boton)
                );
                raiz.querySelector("[data-duraciones]")?.classList.toggle(
                    "visible", ESTADO.modo === "personalizado"
                );
                const entradaTrabajo = raiz.querySelector("[data-trabajo]");
                const entradaDescanso = raiz.querySelector("[data-descanso]");
                if (entradaTrabajo) {
                    entradaTrabajo.value = ESTADO.trabajo;
                }
                if (entradaDescanso) {
                    entradaDescanso.value = ESTADO.descanso;
                }
                const detalle = raiz.querySelector("#pomodoro-detalle");
                if (detalle && !ESTADO.estado?.activo) {
                    detalle.textContent = `${ESTADO.trabajo} min de trabajo · ${ESTADO.descanso} min de descanso`;
                }
                const tiempo = raiz.querySelector("#pomodoro-tiempo");
                if (tiempo && !ESTADO.estado?.activo) {
                    tiempo.textContent = reloj(ESTADO.trabajo * 60);
                }
            });
        });

        raiz.querySelector("[data-trabajo]")?.addEventListener("change", (evento) => {
            ESTADO.trabajo = limitar(Number(evento.target.value) || 25, 5, 90);
            evento.target.value = ESTADO.trabajo;
        });
        raiz.querySelector("[data-descanso]")?.addEventListener("change", (evento) => {
            ESTADO.descanso = limitar(Number(evento.target.value) || 5, 1, 30);
            evento.target.value = ESTADO.descanso;
        });
    }

    /** Arranca una sesión. */
    async function iniciar() {
        const raiz = ESTADO.raiz;
        const datos = {
            asignatura_id: raiz.querySelector("[data-asignatura]")?.value || null,
            modo: ESTADO.modo,
            duracion_trabajo: ESTADO.modo === "personalizado" ? ESTADO.trabajo : null,
            duracion_descanso: ESTADO.modo === "personalizado" ? ESTADO.descanso : null,
            notas: raiz.querySelector("[data-notas]")?.value || ""
        };
        try {
            ESTADO.estado = await global.PuenteAgenda.obtener(
                "iniciar_pomodoro", JSON.stringify(datos)
            );
            pintarTemporizador();
            ESTADO.contexto.toast("Sesión iniciada", `${ESTADO.trabajo} minutos de concentración`, "exito", 2400);
        } catch (error) {
            ESTADO.contexto.toast("No se pudo iniciar", String(error.message || error), "error");
        }
    }

    /** Pausa o reanuda la sesión. */
    async function alternarPausa() {
        try {
            ESTADO.estado = await global.PuenteAgenda.obtener("alternar_pausa_pomodoro");
            pintarTemporizador();
        } catch (error) {
            ESTADO.contexto.toast("No se pudo cambiar la pausa", String(error.message || error), "error");
        }
    }

    /** Termina la sesión y guarda el tiempo efectivo. */
    async function finalizar() {
        try {
            const resultado = await global.PuenteAgenda.obtener("finalizar_pomodoro");
            ESTADO.estado = resultado?.estado || null;
            if (resultado?.sesion) {
                ESTADO.contexto.toast(
                    "Sesión guardada",
                    `${resultado.sesion.duracion_minutos} minutos registrados`,
                    "exito",
                    3000
                );
            }
            await recargar();
        } catch (error) {
            ESTADO.contexto.toast("No se pudo terminar", String(error.message || error), "error");
        }
    }

    /** Reacciona a los ticks enviados por Python. */
    function alActualizarPomodoro(detalle) {
        if (!ESTADO.raiz?.isConnected) {
            return;
        }
        try {
            ESTADO.estado = typeof detalle === "string" ? JSON.parse(detalle) : detalle;
        } catch (error) {
            return;
        }
        if (ESTADO.estado?.sesion_guardada) {
            ESTADO.contexto?.toast(
                "Bloque completado",
                "Es momento de descansar unos minutos.",
                "exito",
                3600
            );
            cargarResumenes().then(() => {
                if (ESTADO.raiz?.isConnected) {
                    ESTADO.raiz.innerHTML = plantilla();
                    conectar();
                }
            });
            return;
        }
        pintarTemporizador();
    }

    /* ------------------------------------------------------------------
       Ciclo de vida
       ------------------------------------------------------------------ */
    /**
     * Monta la vista de estudio.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto.
     */
    async function montar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        if (!ESTADO.suscrito) {
            global.PuenteAgenda.al("pomodoroActualizado", alActualizarPomodoro);
            ESTADO.suscrito = true;
        }
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
        if (ESTADO.estado?.activo) {
            pintarTemporizador();
        } else {
            await recargar();
        }
    }

    global.AgendaApp.registrarVista("estudio", { montar, actualizar });
})(window);
