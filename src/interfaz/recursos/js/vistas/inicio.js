/**
 * ============================================================================
 *  VISTA INICIO · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Resume el día en cuatro bloques: un héroe con el progreso y la cuenta atrás
 *  del próximo examen, los indicadores de la semana, la agenda de hoy con
 *  casillas para completar tareas y los próximos hitos académicos.
 *
 *  Solo se usa el ratón; ninguna acción depende del teclado.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { escapar, icono, horaCorta, fechaRelativa, diasHasta } = U;

    let temporizadorCuenta = null;

    /* ------------------------------------------------------------------
       Plantillas
       ------------------------------------------------------------------ */
    /**
     * Genera una tarjeta de indicador.
     * @param {object} datos Contenido del KPI.
     * @returns {string} HTML de la tarjeta.
     */
    function tarjetaKpi(datos) {
        return `
            <article class="tarjeta tarjeta--kpi">
                <div class="kpi__cabecera">
                    <span class="kpi__icono" style="--tono:${datos.tono || "var(--acento)"}">
                        ${icono(datos.icono)}
                    </span>
                    ${datos.insignia ? `<span class="kpi__insignia">${escapar(datos.insignia)}</span>` : ""}
                </div>
                <p class="kpi__valor">${escapar(datos.valor)}<span class="kpi__unidad">${escapar(datos.unidad || "")}</span></p>
                <p class="kpi__etiqueta">${escapar(datos.etiqueta)}</p>
                <p class="kpi__detalle">${escapar(datos.detalle || "")}</p>
            </article>`;
    }

    /**
     * Describe la cuenta atrás de un hito en lenguaje natural.
     * @param {string} iso Fecha del hito.
     * @returns {string} Texto como «faltan 3 días».
     */
    function textoCuentaAtras(iso) {
        if (!iso) {
            return "sin fecha";
        }
        const dias = diasHasta(iso);
        if (dias < 0) {
            return "fecha pasada";
        }
        if (dias === 0) {
            return "es hoy";
        }
        if (dias === 1) {
            return "mañana";
        }
        if (dias < 7) {
            return `faltan ${dias} días`;
        }
        return `faltan ${Math.ceil(dias / 7)} semanas`;
    }

    /**
     * Construye el bloque del próximo hito.
     * @param {object|null} hito Evento más cercano.
     * @returns {string} HTML del héroe derecho.
     */
    function bloqueHito(hito) {
        if (!hito) {
            return `
                <div class="heroe-hito heroe-hito--libre">
                    <span class="heroe-hito__icono">${icono("sol")}</span>
                    <p class="heroe-hito__etiqueta">Próximo hito</p>
                    <h2 class="heroe-hito__titulo">Sin exámenes a la vista</h2>
                    <p class="heroe-hito__detalle">Aprovecha para adelantar entregas o repasar apuntes.</p>
                    <button class="boton boton--fantasma boton--pequeno" type="button"
                            data-accion="ver-calendario">
                        ${icono("calendario")} Abrir calendario
                    </button>
                </div>`;
        }
        const color = hito.asignatura_color || "var(--acento)";
        const tipo = hito.tipo === "examen" ? "Examen" : "Entrega";
        const fecha = hito.fecha_inicio
            ? U.fechaCorta(hito.fecha_inicio, { weekday: "long", day: "numeric", month: "long" })
            : "Sin fecha";
        return `
            <div class="heroe-hito" style="--color-hito:${color}">
                <div class="heroe-hito__cabecera">
                    <span class="heroe-hito__etiqueta">${icono("objetivo")} Próximo ${tipo.toLowerCase()}</span>
                    <span class="etiqueta ${hito.prioridad === "critica" ? "etiqueta--critica" : "etiqueta--alta"}">
                        ${escapar(textoCuentaAtras(hito.fecha_inicio))}
                    </span>
                </div>
                <h2 class="heroe-hito__titulo">${escapar(hito.titulo)}</h2>
                <p class="heroe-hito__detalle">
                    ${escapar(hito.asignatura_nombre || "Sin asignatura")}
                    ${hito.ubicacion ? ` · ${escapar(hito.ubicacion)}` : ""}
                </p>
                <div class="heroe-hito__pie">
                    <span class="heroe-hito__fecha">${icono("reloj")} ${escapar(fecha)} · ${escapar(horaCorta(hito.fecha_inicio))}</span>
                    <span class="heroe-hito__cuenta" id="cuenta-hito" data-fecha="${escapar(hito.fecha_inicio || "")}">
                        ${escapar(textoCuentaAtras(hito.fecha_inicio))}
                    </span>
                </div>
            </div>`;
    }

    /**
     * Construye una fila de la agenda diaria.
     * @param {object} evento Evento del día.
     * @returns {string} HTML de la fila.
     */
    function filaAgenda(evento) {
        const color = evento.asignatura_color || U.colorDesdeTexto(evento.asignatura_nombre || evento.titulo);
        const detalle = [evento.asignatura_nombre, evento.ubicacion].filter(Boolean).join(" · ");
        return `
            <div class="linea-tiempo__fila ${evento.completado ? "tarea-completada" : ""}"
                 data-evento="${Number(evento.id)}" style="--color-evento:${color}">
                <div class="linea-tiempo__hora">
                    <span>${escapar(horaCorta(evento.fecha_inicio) || "Todo el día")}</span>
                </div>
                <div class="linea-tiempo__riel" aria-hidden="true">
                    <span class="linea-tiempo__punto"></span>
                </div>
                <div class="linea-tiempo__tarjeta">
                    <div class="linea-tiempo__cabecera">
                        <p class="linea-tiempo__titulo tarea__titulo">${escapar(evento.titulo)}</p>
                        ${U.insigniaPrioridad(evento.prioridad, evento.tipo)}
                    </div>
                    <p class="linea-tiempo__detalle">
                        ${escapar(U.etiquetaTipo(evento.tipo))}${detalle ? ` · ${escapar(detalle)}` : ""}
                    </p>
                </div>
                <button class="marca-verificacion ${evento.completado ? "activa" : ""}"
                        type="button" data-completar="${Number(evento.id)}"
                        data-estado="${evento.completado ? "1" : "0"}"
                        aria-label="${evento.completado ? "Marcar como pendiente" : "Marcar como completada"}">
                    ${icono("check")}
                </button>
            </div>`;
    }

    /**
     * Construye una fila de próximo examen o entrega.
     * @param {object} evento Evento futuro.
     * @returns {string} HTML de la fila.
     */
    function filaHito(evento) {
        const color = evento.asignatura_color || "var(--acento)";
        const dias = diasHasta(evento.fecha_inicio);
        const urgente = dias <= 3;
        return `
            <div class="fila-datos hito-fila" data-evento="${Number(evento.id)}">
                <span class="hito-fila__marca" style="background:${color}">
                    ${icono(evento.tipo === "examen" ? "nota" : "subir")}
                </span>
                <div class="fila-datos__principal">
                    <p class="fila-datos__titulo">${escapar(evento.titulo)}</p>
                    <p class="fila-datos__detalle">
                        ${escapar(evento.asignatura_nombre || "Sin asignatura")} ·
                        ${escapar(fechaRelativa(evento.fecha_inicio))}
                    </p>
                </div>
                <div class="fila-datos__meta">
                    <span class="etiqueta ${urgente ? "etiqueta--critica" : "etiqueta--media"}">
                        ${escapar(textoCuentaAtras(evento.fecha_inicio))}
                    </span>
                </div>
            </div>`;
    }

    /**
     * Construye una tarjeta compacta de asignatura.
     * @param {object} asignatura Asignatura.
     * @returns {string} HTML de la tarjeta.
     */
    function tarjetaAsignatura(asignatura) {
        const color = asignatura.color || "var(--acento)";
        return `
            <button class="asignatura-mini" type="button" data-asignatura="${Number(asignatura.id)}"
                    style="--color-asignatura:${color}">
                <span class="asignatura-mini__punto"></span>
                <span class="asignatura-mini__texto">
                    <span class="asignatura-mini__nombre">${escapar(asignatura.nombre)}</span>
                    <span class="asignatura-mini__detalle">
                        ${escapar(asignatura.codigo || "Sin código")} ·
                        ${escapar(asignatura.profesor || "Sin profesorado")}
                    </span>
                </span>
                <span class="asignatura-mini__creditos">${escapar(asignatura.creditos)} ECTS</span>
            </button>`;
    }

    /**
     * Genera el HTML completo de la vista.
     * @param {object} contexto Contexto de la aplicación.
     * @returns {string} HTML de la vista.
     */
    function plantilla(contexto) {
        const panel = contexto.panel;
        if (!panel) {
            return U.vacio(
                "inicio",
                "Estamos preparando tu panel",
                "En cuanto termine la carga verás aquí tu día completo."
            );
        }
        const kpis = panel.kpis || {};
        const progreso = U.limitar(Number(panel.progreso_dia) || 0, 0, 100);
        const circunferencia = 2 * Math.PI * 54;
        const desplazamiento = circunferencia * (1 - progreso / 100);
        const agenda = Array.isArray(panel.agenda_hoy) ? panel.agenda_hoy : [];
        const completadas = agenda.filter((evento) => evento.completado).length;
        const proximos = Array.isArray(panel.proximos_examenes) ? panel.proximos_examenes : [];
        const asignaturas = Array.isArray(panel.asignaturas) ? panel.asignaturas : [];
        const avisos = Array.isArray(panel.notificaciones) ? panel.notificaciones : [];

        const accionAgenda = agenda.length
            ? ""
            : `<button class="boton boton--fantasma boton--pequeno" type="button" data-accion="nueva-tarea">
                   ${icono("mas")} Añadir una tarea
               </button>`;

        return `
            <!-- Héroe: progreso del día y próximo hito -->
            <section class="inicio-heroe seccion">
                <div class="heroe-progreso">
                    <div class="heroe-progreso__anillo">
                        <svg viewBox="0 0 128 128" role="img" aria-label="Progreso del día: ${progreso}%">
                            <circle class="anillo-inicio__fondo" cx="64" cy="64" r="54"></circle>
                            <circle class="anillo-inicio__valor" cx="64" cy="64" r="54"
                                    style="stroke-dasharray:${circunferencia.toFixed(2)};stroke-dashoffset:${desplazamiento.toFixed(2)}"></circle>
                        </svg>
                        <div class="heroe-progreso__centro">
                            <span class="heroe-progreso__cifra">${progreso}<small>%</small></span>
                            <span class="heroe-progreso__texto">del día</span>
                        </div>
                    </div>
                    <div class="heroe-progreso__info">
                        <p class="heroe-progreso__etiqueta">${icono("rayo")} Tu jornada académica</p>
                        <h2 class="heroe-progreso__titulo">
                            ${completadas === agenda.length && agenda.length
                                ? "¡Día completado!"
                                : `${completadas} de ${agenda.length} bloques completados`}
                        </h2>
                        <p class="heroe-progreso__detalle">
                            ${agenda.length
                                ? "Marca cada bloque al terminarlo para actualizar tu progreso."
                                : "Hoy no hay bloques programados. Es un buen momento para planificar la semana."}
                        </p>
                        <div class="heroe-progreso__acciones">
                            <button class="boton boton--primario boton--pequeno" type="button" data-accion="nueva-tarea">
                                ${icono("mas")} Nueva tarea
                            </button>
                            <button class="boton boton--fantasma boton--pequeno" type="button" data-accion="ver-calendario">
                                ${icono("calendario")} Ver calendario
                            </button>
                            <button class="boton boton--fantasma boton--pequeno" type="button" data-accion="ir-estudio">
                                ${icono("reproducir")} Concentrarme
                            </button>
                        </div>
                    </div>
                </div>
                ${bloqueHito(panel.proximo_hito || proximos[0] || null)}
            </section>

            <!-- Indicadores semanales -->
            <section class="seccion">
                <div class="seccion__cabecera">
                    <div>
                        <h2 class="seccion__titulo">${icono("grafico")} La semana en cifras</h2>
                        <p class="seccion__descripcion">Datos calculados en tiempo real desde tu base SQLite.</p>
                    </div>
                </div>
                <div class="rejilla rejilla--kpis">
                    ${tarjetaKpi({
                        icono: "check",
                        valor: String(kpis.tareas_completadas_semana || 0),
                        etiqueta: "Tareas completadas",
                        detalle: "Esta semana",
                        tono: "var(--color-exito)"
                    })}
                    ${tarjetaKpi({
                        icono: "reloj",
                        valor: String(kpis.horas_estudio_semana || 0),
                        unidad: " h",
                        etiqueta: "Tiempo de estudio",
                        detalle: `${kpis.minutos_enfoque_hoy || 0} min registrados hoy`,
                        tono: "var(--acento)"
                    })}
                    ${tarjetaKpi({
                        icono: "alerta",
                        valor: String(kpis.entregas_proximas || 0),
                        etiqueta: "Entregas próximas",
                        detalle: "En los próximos 7 días",
                        tono: "var(--color-aviso)"
                    })}
                    ${tarjetaKpi({
                        icono: "campana",
                        valor: String(kpis.alertas_sin_ver || 0),
                        etiqueta: "Avisos sin leer",
                        detalle: kpis.alertas_sin_ver ? "Revisa la campana" : "Todo al día",
                        tono: "var(--color-peligro)"
                    })}
                </div>
            </section>

            <!-- Agenda del día y próximos hitos -->
            <section class="seccion rejilla rejilla--lateral">
                <article class="tarjeta">
                    <header class="tarjeta__cabecera">
                        <div>
                            <h2 class="tarjeta__titulo">${icono("calendario")} Agenda de hoy</h2>
                            <p class="tarjeta__subtitulo">${escapar(panel.fecha || "")}</p>
                        </div>
                        ${accionAgenda}
                    </header>
                    <div class="tarjeta__cuerpo">
                        ${agenda.length
                            ? `<div class="linea-tiempo">${agenda.map(filaAgenda).join("")}</div>`
                            : U.vacio(
                                "sol",
                                "Nada programado para hoy",
                                "Añade una tarea o consulta el calendario para ver la semana completa.",
                                '<button class="boton boton--primario boton--pequeno" type="button" data-accion="nueva-tarea">Crear tarea</button>'
                            )}
                    </div>
                </article>

                <article class="tarjeta">
                    <header class="tarjeta__cabecera">
                        <div>
                            <h2 class="tarjeta__titulo">${icono("objetivo")} Próximos hitos</h2>
                            <p class="tarjeta__subtitulo">Exámenes y entregas</p>
                        </div>
                    </header>
                    <div class="tarjeta__cuerpo">
                        ${proximos.length
                            ? `<div class="lista-hitos">${proximos.map(filaHito).join("")}</div>`
                            : U.vacio(
                                "trofeo",
                                "Sin hitos cercanos",
                                "Cuando añadas exámenes o entregas aparecerán aquí con su cuenta atrás."
                            )}
                    </div>
                </article>
            </section>

            <!-- Avisos recientes y asignaturas -->
            <section class="seccion rejilla rejilla--lateral" id="avisos">
                <article class="tarjeta">
                    <header class="tarjeta__cabecera">
                        <div>
                            <h2 class="tarjeta__titulo">${icono("campana")} Avisos recientes</h2>
                            <p class="tarjeta__subtitulo">Recordatorios generados por el planificador</p>
                        </div>
                        <button class="boton boton--fantasma boton--pequeno" type="button" data-accion="abrir-avisos">
                            ${icono("flechaDerecha")} Ver todos
                        </button>
                    </header>
                    <div class="tarjeta__cuerpo">
                        ${avisos.length
                            ? `<div class="lista-avisos">${avisos.slice(0, 5).map((aviso) => `
                                <div class="fila-datos">
                                    <span class="hito-fila__marca" style="background:var(--acento)">
                                        ${icono("campana")}
                                    </span>
                                    <div class="fila-datos__principal">
                                        <p class="fila-datos__titulo">${escapar(aviso.titulo)}</p>
                                        <p class="fila-datos__detalle">${escapar(aviso.mensaje || "")}</p>
                                    </div>
                                    <span class="fila-datos__meta texto-tenue" style="font-size:0.7rem">
                                        ${escapar(horaCorta(aviso.programada_para) || fechaRelativa(aviso.programada_para))}
                                    </span>
                                </div>`).join("")}</div>`
                            : U.vacio(
                                "check",
                                "Sin avisos pendientes",
                                "El planificador te avisará con antelación de cada entrega."
                            )}
                    </div>
                </article>

                <article class="tarjeta">
                    <header class="tarjeta__cabecera">
                        <div>
                            <h2 class="tarjeta__titulo">${icono("asignaturas")} Tus asignaturas</h2>
                            <p class="tarjeta__subtitulo">${asignaturas.length} materias activas</p>
                        </div>
                        <button class="boton boton--fantasma boton--pequeno" type="button" data-accion="nueva-asignatura">
                            ${icono("mas")} Añadir
                        </button>
                    </header>
                    <div class="tarjeta__cuerpo">
                        ${asignaturas.length
                            ? `<div class="lista-asignaturas-mini">${asignaturas.map(tarjetaAsignatura).join("")}</div>`
                            : U.vacio(
                                "libro",
                                "Sin asignaturas",
                                "Crea tu primera asignatura para organizar eventos y notas."
                            )}
                    </div>
                </article>
            </section>`;
    }

    /* ------------------------------------------------------------------
       Interacción
       ------------------------------------------------------------------ */
    /**
     * Conecta los botones de la vista con el contexto de la aplicación.
     * @param {HTMLElement} raiz Contenedor de la vista.
     * @param {object} contexto Contexto de la aplicación.
     */
    function conectar(raiz, contexto) {
        raiz.querySelectorAll("[data-accion]").forEach((boton) => {
            boton.addEventListener("click", () => {
                const accion = boton.dataset.accion;
                if (accion === "nueva-tarea") {
                    contexto.abrirModal("tarea");
                } else if (accion === "nueva-asignatura") {
                    contexto.abrirModal("asignatura");
                } else if (accion === "ver-calendario") {
                    contexto.navegarA("calendario");
                } else if (accion === "ir-estudio") {
                    contexto.navegarA("estudio");
                } else if (accion === "abrir-avisos") {
                    document.getElementById("boton-campana")?.click();
                }
            });
        });

        raiz.querySelectorAll("[data-completar]").forEach((boton) => {
            boton.addEventListener("click", async (evento) => {
                evento.stopPropagation();
                const identificador = Number(boton.dataset.completar);
                const completado = boton.dataset.estado === "1";
                boton.disabled = true;
                try {
                    await global.PuenteAgenda.obtener(
                        "completar_evento", identificador, !completado
                    );
                    contexto.toast(
                        completado ? "Tarea reabierta" : "¡Bloque completado!",
                        completado ? "Volvió a la lista de pendientes." : "Buen trabajo, sigue así.",
                        completado ? "info" : "exito",
                        2800
                    );
                    await contexto.recargarDatos(false);
                } catch (error) {
                    contexto.toast("No se pudo actualizar", String(error.message || error), "error");
                    boton.disabled = false;
                }
            });
        });

        raiz.querySelectorAll("[data-asignatura]").forEach((boton) => {
            boton.addEventListener("click", () => contexto.navegarA("asignaturas"));
        });

        raiz.querySelectorAll(".linea-tiempo__fila[data-evento]").forEach((fila) => {
            fila.addEventListener("click", () => {
                contexto.navegarA("calendario", { evento: Number(fila.dataset.evento) });
            });
        });
    }

    /** Actualiza la cuenta atrás del héroe una vez por minuto. */
    function iniciarCuentaAtras() {
        detenerCuentaAtras();
        temporizadorCuenta = global.setInterval(() => {
            const nodo = document.getElementById("cuenta-hito");
            if (!nodo) {
                return;
            }
            nodo.textContent = textoCuentaAtras(nodo.dataset.fecha);
        }, 60_000);
    }

    /** Detiene el temporizador de cuenta atrás. */
    function detenerCuentaAtras() {
        if (temporizadorCuenta) {
            global.clearInterval(temporizadorCuenta);
            temporizadorCuenta = null;
        }
    }

    /* ------------------------------------------------------------------
       Módulo de vista
       ------------------------------------------------------------------ */
    /**
     * Monta la vista Inicio.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto de la aplicación.
     */
    function montar(raiz, contexto) {
        raiz.innerHTML = plantilla(contexto);
        conectar(raiz, contexto);
        iniciarCuentaAtras();
    }

    /**
     * Refresca la vista conservando el punto de desplazamiento.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto de la aplicación.
     */
    function actualizar(raiz, contexto) {
        const desplazamiento = document.getElementById("contenido")?.scrollTop || 0;
        montar(raiz, contexto);
        const contenedor = document.getElementById("contenido");
        if (contenedor) {
            contenedor.scrollTop = desplazamiento;
        }
    }

    global.AgendaApp.registrarVista("inicio", { montar, actualizar });
})(window);
