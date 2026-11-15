/**
 * ============================================================================
 *  VISTA AJUSTES · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Centro de control de la agenda. Reúne en una sola pantalla:
 *
 *  * los tres temas visuales y los datos del estudiante;
 *  * preferencias de notificaciones, resumen matutino y sincronización;
 *  * suscripciones a calendarios iCalendar y sincronización manual;
 *  * copias de seguridad con creación, restauración y borrado;
 *  * arranque automático y la ruta de datos local;
 *  * previsualización y exportación del informe académico en Markdown.
 *
 *  Todos los controles funcionan con ratón o trackpad: no hay atajos.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { escapar, icono, fechaCorta, horaCorta } = U;

    const TEMAS = [
        {
            id: "cristal-medianoche",
            nombre: "Cristal Medianoche",
            descripcion: "Cristales azulados y acentos violeta para sesiones nocturnas.",
            clase: "tema-vista--medianoche"
        },
        {
            id: "noche-nordica",
            nombre: "Noche Nórdica",
            descripcion: "Verdes fríos y carbón profundo, descansado para la vista.",
            clase: "tema-vista--nordica"
        },
        {
            id: "luz-pura",
            nombre: "Luz Pura",
            descripcion: "Superficies claras y contraste alto para trabajar de día.",
            clase: "tema-vista--luz"
        }
    ];

    const AVISOS = [
        { minutos: 0, etiqueta: "En el momento" },
        { minutos: 15, etiqueta: "15 min" },
        { minutos: 60, etiqueta: "1 hora" },
        { minutos: 120, etiqueta: "2 horas" },
        { minutos: 1440, etiqueta: "1 día" },
        { minutos: 2880, etiqueta: "2 días" },
        { minutos: 10080, etiqueta: "1 semana" }
    ];

    const ESTADO = {
        configuracion: {},
        suscripciones: [],
        respaldos: [],
        sistema: null,
        informe: null,
        raiz: null,
        contexto: null,
        cargando: false
    };

    /* ------------------------------------------------------------------
       Formato
       ------------------------------------------------------------------ */
    /**
     * Convierte bytes a un tamaño legible.
     * @param {number} bytes Tamaño en bytes.
     * @returns {string} Texto como `1,4 MB`.
     */
    function tamano(bytes) {
        const valor = Number(bytes) || 0;
        if (valor < 1024) {
            return `${valor} B`;
        }
        if (valor < 1024 * 1024) {
            return `${(valor / 1024).toFixed(1).replace(".", ",")} KB`;
        }
        return `${(valor / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
    }

    /**
     * Normaliza un valor de configuración a booleano.
     * @param {*} valor Valor serializado.
     * @returns {boolean} Interpretación booleana.
     */
    const activo = (valor) => valor === true || valor === 1 || valor === "1" || valor === "true";

    /**
     * Convierte minutos de aviso en conjunto de números.
     * @param {string} texto Lista separada por comas.
     * @returns {Set<number>} Minutos activos.
     */
    function avisosActivos(texto) {
        return new Set(
            String(texto || "")
                .split(",")
                .map((valor) => Number(valor.trim()))
                .filter((valor) => Number.isFinite(valor) && valor >= 0)
        );
    }

    /* ------------------------------------------------------------------
       Render de Markdown
       ------------------------------------------------------------------ */
    /**
     * Aplica negritas, cursivas y código en línea a un texto ya escapado.
     * @param {string} texto Texto escapado.
     * @returns {string} HTML en línea.
     */
    function enLinea(texto) {
        return texto
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>")
            .replace(/_([^_]+)_/g, "<em>$1</em>");
    }

    /**
     * Convierte el Markdown generado por el informe en HTML seguro.
     * @param {string} texto Documento Markdown.
     * @returns {string} HTML listo para insertar.
     */
    function renderizarMarkdown(texto) {
        const lineas = String(texto || "").split(/\r?\n/);
        const salida = [];
        let lista = null;
        let tabla = null;

        const cerrarLista = () => {
            if (lista) {
                salida.push(`<ul>${lista.join("")}</ul>`);
                lista = null;
            }
        };
        const cerrarTabla = () => {
            if (!tabla) {
                return;
            }
            const [cabecera, ...filas] = tabla;
            salida.push(
                `<table class="ajustes-tabla"><thead><tr>${cabecera
                    .map((celda) => `<th>${enLinea(celda)}</th>`)
                    .join("")}</tr></thead><tbody>${filas
                    .map(
                        (fila) =>
                            `<tr>${fila.map((celda) => `<td>${enLinea(celda)}</td>`).join("")}</tr>`
                    )
                    .join("")}</tbody></table>`
            );
            tabla = null;
        };

        for (const linea of lineas) {
            const limpia = linea.trim();
            if (!limpia) {
                cerrarLista();
                cerrarTabla();
                continue;
            }
            if (limpia.startsWith("|")) {
                cerrarLista();
                const celdas = limpia
                    .replace(/^\|/, "")
                    .replace(/\|$/, "")
                    .split("|")
                    .map((celda) => escapar(celda.trim()));
                if (celdas.every((celda) => /^-{2,}$/.test(celda.replace(/:/g, "")))) {
                    continue;
                }
                tabla = tabla || [];
                tabla.push(celdas);
                continue;
            }
            cerrarTabla();
            if (/^---+$/.test(limpia)) {
                cerrarLista();
                salida.push("<hr>");
            } else if (limpia.startsWith("### ")) {
                cerrarLista();
                salida.push(`<h4>${enLinea(escapar(limpia.slice(4)))}</h4>`);
            } else if (limpia.startsWith("## ")) {
                cerrarLista();
                salida.push(`<h3>${enLinea(escapar(limpia.slice(3)))}</h3>`);
            } else if (limpia.startsWith("# ")) {
                cerrarLista();
                salida.push(`<h2>${enLinea(escapar(limpia.slice(2)))}</h2>`);
            } else if (limpia.startsWith("- ")) {
                lista = lista || [];
                lista.push(`<li>${enLinea(escapar(limpia.slice(2)))}</li>`);
            } else {
                cerrarLista();
                salida.push(`<p>${enLinea(escapar(limpia))}</p>`);
            }
        }
        cerrarLista();
        cerrarTabla();
        return salida.join("");
    }

    /* ------------------------------------------------------------------
       Plantillas
       ------------------------------------------------------------------ */
    /**
     * Tarjeta de tema visual con vista previa.
     * @param {object} tema Metadatos del tema.
     * @returns {string} HTML de la tarjeta.
     */
    function tarjetaTema(tema) {
        const seleccionado = ESTADO.configuracion.tema === tema.id;
        return `
            <button class="ajustes-tema ${tema.clase} ${seleccionado ? "activo" : ""}"
                    type="button" data-tema="${tema.id}" aria-pressed="${seleccionado}">
                <span class="ajustes-tema__vista" aria-hidden="true">
                    <i class="ajustes-tema__lateral"></i>
                    <i class="ajustes-tema__tarjeta"></i>
                    <i class="ajustes-tema__acento"></i>
                </span>
                <span class="ajustes-tema__texto">
                    <strong>${escapar(tema.nombre)}</strong>
                    <small>${escapar(tema.descripcion)}</small>
                </span>
                <span class="ajustes-tema__marca">${icono("check")}</span>
            </button>`;
    }

    /**
     * Interruptor de configuración booleana.
     * @param {string} clave Clave de configuración.
     * @param {string} etiqueta Texto visible.
     * @param {string} detalle Descripción breve.
     * @returns {string} HTML del interruptor.
     */
    function interruptor(clave, etiqueta, detalle) {
        const encendido = activo(ESTADO.configuracion[clave]);
        return `
            <button class="interruptor ${encendido ? "activo" : ""}" type="button"
                    role="switch" aria-checked="${encendido}" data-config="${clave}">
                <span class="interruptor__pista"><span class="interruptor__bolita"></span></span>
                <span class="interruptor__texto">
                    <strong>${escapar(etiqueta)}</strong>
                    <small>${escapar(detalle)}</small>
                </span>
            </button>`;
    }

    /** Sección de preferencias personales y visuales. */
    function seccionPersonal() {
        const objetivo = Number(ESTADO.configuracion.objetivo_academico || 5);
        return `
            <section class="tarjeta ajustes-panel ajustes-personal">
                <header class="ajustes-panel__cabecera">
                    <div>
                        <h2>${icono("sol")} Tu espacio</h2>
                        <p>Elige el tema y los datos que personalizan la agenda.</p>
                    </div>
                </header>

                <div class="ajustes-temas">
                    ${TEMAS.map(tarjetaTema).join("")}
                </div>

                <div class="ajustes-campos">
                    <label class="campo">
                        <span class="campo__etiqueta">Nombre del estudiante</span>
                        <input class="campo__control" type="text" maxlength="48"
                               value="${escapar(ESTADO.configuracion.nombre_estudiante || "Estudiante")}"
                               data-campo="nombre_estudiante">
                    </label>
                    <label class="campo">
                        <span class="campo__etiqueta">Objetivo académico</span>
                        <div class="ajustes-rango">
                            <input type="range" min="5" max="10" step="0.1"
                                   value="${objetivo}" data-rango="objetivo_academico">
                            <strong id="objetivo-academico-valor">${objetivo.toFixed(1)}</strong>
                        </div>
                    </label>
                </div>
            </section>`;
    }

    /** Sección de notificaciones y sincronización. */
    function seccionAvisos() {
        const activos = avisosActivos(ESTADO.configuracion.avisos_predeterminados);
        return `
            <section class="tarjeta ajustes-panel ajustes-avisos">
                <header class="ajustes-panel__cabecera">
                    <div>
                        <h2>${icono("campana")} Avisos y automatización</h2>
                        <p>Controla cuándo te avisa la agenda y con qué antelación.</p>
                    </div>
                </header>

                <div class="ajustes-interruptores">
                    ${interruptor("notificaciones_activas", "Notificaciones nativas", "Avisos del sistema para entregas y clases.")}
                    ${interruptor("resumen_matutino", "Resumen matutino", "Un recordatorio con el plan del día.")}
                    ${interruptor("sincronizacion_automatica", "Sincronización iCalendar", "Actualiza los calendarios suscritos.")}
                </div>

                <div class="ajustes-campos ajustes-campos--compactos">
                    <label class="campo">
                        <span class="campo__etiqueta">Hora del resumen</span>
                        <input class="campo__control" type="time"
                               value="${escapar(ESTADO.configuracion.hora_resumen_matutino || "08:00")}"
                               data-campo="hora_resumen_matutino">
                    </label>
                    <label class="campo">
                        <span class="campo__etiqueta">Frecuencia de sincronización</span>
                        <select class="campo__control" data-campo="minutos_sincronizacion">
                            ${[15, 30, 60, 120, 240].map((minutos) => `
                                <option value="${minutos}" ${Number(ESTADO.configuracion.minutos_sincronizacion) === minutos ? "selected" : ""}>
                                    Cada ${minutos < 60 ? `${minutos} minutos` : `${minutos / 60} hora${minutos > 60 ? "s" : ""}`}
                                </option>`).join("")}
                        </select>
                    </label>
                </div>

                <div class="ajustes-antelaciones">
                    <span class="campo__etiqueta">Antelación de los avisos</span>
                    <div class="ajustes-chips">
                        ${AVISOS.map((aviso) => `
                            <button class="ajustes-chip ${activos.has(aviso.minutos) ? "activo" : ""}"
                                    type="button" data-aviso="${aviso.minutos}"
                                    aria-pressed="${activos.has(aviso.minutos)}">
                                ${escapar(aviso.etiqueta)}
                            </button>`).join("")}
                    </div>
                </div>
            </section>`;
    }

    /**
     * Fila de una suscripción iCalendar.
     * @param {object} suscripcion Suscripción.
     * @returns {string} HTML de la fila.
     */
    function filaSuscripcion(suscripcion) {
        return `
            <div class="ajustes-feed ${suscripcion.activa ? "" : "inactivo"}"
                 data-suscripcion="${suscripcion.id}">
                <span class="ajustes-feed__icono">${icono("calendario")}</span>
                <div class="ajustes-feed__texto">
                    <strong>${escapar(suscripcion.nombre)}</strong>
                    <span title="${escapar(suscripcion.url)}">${escapar(suscripcion.url)}</span>
                    <small>
                        Cada ${suscripcion.frecuencia_minutos} min ·
                        ${suscripcion.ultima_sincronizacion
                            ? `sincronizado ${escapar(fechaCorta(suscripcion.ultima_sincronizacion))}`
                            : "sin sincronizar todavía"}
                    </small>
                </div>
                <div class="ajustes-feed__acciones">
                    <button class="boton boton--fantasma boton--pequeno" type="button"
                            data-sincronizar-feed="${suscripcion.id}"
                            data-tooltip="Sincronizar ahora">${icono("sincronizar")}</button>
                    <button class="boton boton--fantasma boton--pequeno" type="button"
                            data-alternar-feed="${suscripcion.id}"
                            data-activa="${suscripcion.activa ? "1" : "0"}"
                            data-tooltip="${suscripcion.activa ? "Pausar" : "Activar"}">
                        ${icono(suscripcion.activa ? "pausa" : "reproducir")}
                    </button>
                    <button class="boton boton--fantasma boton--pequeno" type="button"
                            data-eliminar-feed="${suscripcion.id}"
                            data-tooltip="Eliminar">${icono("basura")}</button>
                </div>
            </div>`;
    }

    /** Sección de calendarios iCalendar. */
    function seccionCalendarios() {
        return `
            <section class="tarjeta ajustes-panel ajustes-calendarios">
                <header class="ajustes-panel__cabecera">
                    <div>
                        <h2>${icono("enlace")} Calendarios iCalendar</h2>
                        <p>Importa un archivo .ics o suscríbete a un feed remoto.</p>
                    </div>
                    <button class="boton boton--fantasma boton--pequeno" type="button" data-importar-ics>
                        ${icono("subir")} Importar .ics
                    </button>
                </header>

                <div class="ajustes-feeds">
                    ${ESTADO.suscripciones.length
                        ? ESTADO.suscripciones.map(filaSuscripcion).join("")
                        : U.vacio("calendario", "Sin calendarios suscritos", "Añade un feed para mantener tus clases al día.")}
                </div>

                <form class="ajustes-alta" id="form-suscripcion" autocomplete="off">
                    <label class="campo">
                        <span class="campo__etiqueta">Nombre</span>
                        <input class="campo__control" name="nombre" type="text" required
                               maxlength="60" placeholder="Calendario de la facultad">
                    </label>
                    <label class="campo campo--ancho">
                        <span class="campo__etiqueta">URL del feed</span>
                        <input class="campo__control" name="url" type="url" required
                               placeholder="https://ejemplo.com/calendario.ics">
                    </label>
                    <label class="campo">
                        <span class="campo__etiqueta">Frecuencia</span>
                        <select class="campo__control" name="frecuencia_minutos">
                            <option value="30">Cada 30 minutos</option>
                            <option value="60" selected>Cada hora</option>
                            <option value="120">Cada 2 horas</option>
                            <option value="240">Cada 4 horas</option>
                            <option value="720">Cada 12 horas</option>
                        </select>
                    </label>
                    <button class="boton boton--primario" type="submit">
                        ${icono("mas")} Suscribirme
                    </button>
                </form>

                <div class="ajustes-panel__pie">
                    <button class="boton boton--fantasma boton--pequeno" type="button" data-sincronizar-todos>
                        ${icono("sincronizar")} Sincronizar todos los feeds
                    </button>
                </div>
            </section>`;
    }

    /**
     * Fila de un respaldo.
     * @param {object} respaldo Metadatos del ZIP.
     * @returns {string} HTML de la fila.
     */
    function filaRespaldo(respaldo) {
        return `
            <div class="ajustes-respaldo" data-respaldo="${escapar(respaldo.ruta)}">
                <span class="ajustes-respaldo__icono">${icono("respaldo")}</span>
                <div class="ajustes-respaldo__texto">
                    <strong>${escapar(respaldo.etiqueta === "manual" ? "Copia manual" : respaldo.etiqueta || "Copia manual")}</strong>
                    <span>${escapar(fechaCorta(respaldo.fecha))} · ${escapar(horaCorta(respaldo.fecha))}</span>
                    <small>${tamano(respaldo.tamano_bytes)} · esquema v${respaldo.version_esquema ?? "—"}</small>
                </div>
                <div class="ajustes-respaldo__acciones">
                    <button class="boton boton--fantasma boton--pequeno" type="button"
                            data-restaurar="${escapar(respaldo.ruta)}"
                            data-tooltip="Restaurar copia">${icono("reiniciar")}</button>
                    <button class="boton boton--fantasma boton--pequeno" type="button"
                            data-borrar-respaldo="${escapar(respaldo.ruta)}"
                            data-tooltip="Eliminar copia">${icono("basura")}</button>
                </div>
            </div>`;
    }

    /** Sección de respaldos. */
    function seccionRespaldos() {
        return `
            <section class="tarjeta ajustes-panel ajustes-respaldos">
                <header class="ajustes-panel__cabecera">
                    <div>
                        <h2>${icono("respaldo")} Copias de seguridad</h2>
                        <p>Instantáneas completas de tu base de datos SQLite.</p>
                    </div>
                    <div class="ajustes-panel__botones">
                        <button class="boton boton--fantasma boton--pequeno" type="button"
                                data-abrir-carpeta>${icono("carpeta")} Abrir carpeta</button>
                        <button class="boton boton--primario boton--pequeno" type="button" data-crear-respaldo>
                            ${icono("descargar")} Crear copia
                        </button>
                    </div>
                </header>

                <div class="ajustes-lista-respaldos">
                    ${ESTADO.respaldos.length
                        ? ESTADO.respaldos.slice(0, 6).map(filaRespaldo).join("")
                        : U.vacio("respaldo", "Todavía no hay copias", "Crea la primera para proteger tus datos.")}
                </div>

                <div class="ajustes-panel__pie">
                    <button class="boton boton--fantasma boton--pequeno" type="button" data-restaurar-archivo>
                        ${icono("subir")} Restaurar desde un archivo…
                    </button>
                    <span class="ajustes-nota">
                        ${icono("informacion")} La restauración reemplaza los datos actuales.
                    </span>
                </div>
            </section>`;
    }

    /** Sección de sistema. */
    function seccionSistema() {
        const sistema = ESTADO.sistema || {};
        return `
            <section class="tarjeta ajustes-panel ajustes-sistema">
                <header class="ajustes-panel__cabecera">
                    <div>
                        <h2>${icono("ajustes")} Sistema</h2>
                        <p>Integración con el escritorio y ubicación de los datos.</p>
                    </div>
                </header>

                <div class="ajustes-interruptores">
                    ${interruptor("inicio_automatico", "Iniciar con el sistema", "Abre la agenda al encender el equipo.")}
                </div>

                <dl class="ajustes-ficha">
                    <div><dt>Sistema operativo</dt><dd>${escapar(sistema.sistema || "—")}</dd></div>
                    <div><dt>Arranque automático</dt><dd>${sistema.activo ? "Activo" : "Desactivado"}</dd></div>
                    <div><dt>Carpeta de datos</dt><dd class="ajustes-ficha__ruta">${escapar(sistema.directorio_datos || "—")}</dd></div>
                    <div><dt>Archivo de arranque</dt><dd class="ajustes-ficha__ruta">${escapar(sistema.ruta || "—")}</dd></div>
                    <div><dt>Versión</dt><dd>1.0 · SQLite WAL</dd></div>
                </dl>
            </section>`;
    }

    /** Sección del informe académico. */
    function seccionInforme() {
        const informe = ESTADO.informe;
        if (!informe) {
            return `
                <section class="tarjeta ajustes-panel ajustes-informe">
                    <header class="ajustes-panel__cabecera">
                        <div>
                            <h2>${icono("nota")} Informe académico</h2>
                            <p>Resumen listo para guardar o imprimir.</p>
                        </div>
                    </header>
                    ${U.vacio("nota", "Generando informe…", "En unos segundos aparecerá aquí.")}
                </section>`;
        }
        return `
            <section class="tarjeta ajustes-panel ajustes-informe">
                <header class="ajustes-panel__cabecera">
                    <div>
                        <h2>${icono("nota")} Informe académico</h2>
                        <p>${escapar(informe.fecha)} · listo para guardar en Markdown.</p>
                    </div>
                    <div class="ajustes-panel__botones">
                        <button class="boton boton--fantasma boton--pequeno" type="button" data-refrescar-informe>
                            ${icono("reiniciar")} Actualizar
                        </button>
                        <button class="boton boton--primario boton--pequeno" type="button" data-guardar-informe>
                            ${icono("descargar")} Guardar .md
                        </button>
                    </div>
                </header>

                <div class="ajustes-informe__metricas">
                    ${informe.metricas.map((metrica) => `
                        <div class="ajustes-informe__metrica">
                            <span>${escapar(metrica.etiqueta)}</span>
                            <strong>${escapar(metrica.valor)}</strong>
                        </div>`).join("")}
                </div>

                <div class="ajustes-informe__documento">
                    ${renderizarMarkdown(informe.markdown)}
                </div>
            </section>`;
    }

    /** Plantilla completa de la vista. */
    function plantilla() {
        return `
            <div class="ajustes">
                <section class="ajustes-heroe">
                    <div>
                        <p class="ajustes-heroe__etiqueta">${icono("ajustes")} Centro de control</p>
                        <h2>Una agenda a tu manera</h2>
                        <p class="ajustes-heroe__detalle">
                            Temas, avisos, calendarios y copias de seguridad en un mismo lugar.
                        </p>
                    </div>
                    <div class="ajustes-heroe__insignias">
                        <span>${icono("check")} SQLite WAL</span>
                        <span>${icono("sincronizar")} iCalendar</span>
                        <span>${icono("campana")} Notificaciones nativas</span>
                    </div>
                </section>

                <div class="ajustes-rejilla">
                    ${seccionPersonal()}
                    ${seccionAvisos()}
                    ${seccionCalendarios()}
                    ${seccionRespaldos()}
                    ${seccionSistema()}
                    ${seccionInforme()}
                </div>
            </div>`;
    }

    /* ------------------------------------------------------------------
       Datos
       ------------------------------------------------------------------ */
    /** Descarga configuración, feeds, respaldos, sistema e informe. */
    async function cargar() {
        if (ESTADO.cargando) {
            return;
        }
        ESTADO.cargando = true;
        const resultados = await Promise.allSettled([
            global.PuenteAgenda.obtener("obtener_configuracion"),
            global.PuenteAgenda.obtener("listar_suscripciones"),
            global.PuenteAgenda.obtener("listar_respaldos"),
            global.PuenteAgenda.obtener("estado_inicio_automatico"),
            global.PuenteAgenda.obtener("generar_informe")
        ]);
        const [configuracion, suscripciones, respaldos, sistema, informe] = resultados;
        if (configuracion.status === "fulfilled") {
            ESTADO.configuracion = configuracion.value || {};
        }
        if (suscripciones.status === "fulfilled") {
            ESTADO.suscripciones = suscripciones.value || [];
        }
        if (respaldos.status === "fulfilled") {
            ESTADO.respaldos = respaldos.value || [];
        }
        if (sistema.status === "fulfilled") {
            ESTADO.sistema = sistema.value || null;
        }
        if (informe.status === "fulfilled") {
            ESTADO.informe = informe.value || null;
        }
        ESTADO.cargando = false;
    }

    /** Repinta toda la vista. */
    async function recargar() {
        if (!ESTADO.raiz) {
            return;
        }
        await cargar();
        ESTADO.raiz.innerHTML = plantilla();
        conectar();
    }

    /**
     * Persiste cambios de configuración y avisa del resultado.
     * @param {object} cambios Claves y valores a guardar.
     * @param {string} [mensaje] Texto del aviso de éxito.
     */
    async function guardarConfiguracion(cambios, mensaje = "") {
        try {
            ESTADO.configuracion = await global.PuenteAgenda.obtener(
                "guardar_configuracion", JSON.stringify(cambios)
            );
            ESTADO.contexto?.recargarDatos?.();
            if (mensaje) {
                ESTADO.contexto?.toast("Preferencia guardada", mensaje, "exito", 2200);
            }
        } catch (error) {
            ESTADO.contexto?.toast(
                "No se pudo guardar",
                String(error.message || error),
                "error"
            );
        }
    }

    /* ------------------------------------------------------------------
       Interacción
       ------------------------------------------------------------------ */
    /** Cambia el tema desde las tarjetas de la vista. */
    async function cambiarTema(tema) {
        if (ESTADO.configuracion.tema === tema) {
            return;
        }
        global.PuenteAgenda.aplicarTema(tema);
        ESTADO.configuracion.tema = tema;
        ESTADO.raiz?.querySelectorAll(".ajustes-tema[data-tema]").forEach((boton) => {
            const seleccionado = boton.dataset.tema === tema;
            boton.classList.toggle("activo", seleccionado);
            boton.setAttribute("aria-pressed", String(seleccionado));
        });
        await guardarConfiguracion({ tema });
        const nombres = Object.fromEntries(TEMAS.map((elemento) => [elemento.id, elemento.nombre]));
        ESTADO.contexto?.toast("Tema aplicado", nombres[tema] || tema, "exito", 2400);
    }

    /** Activa o desactiva un interruptor de configuración. */
    async function alternarInterruptor(boton) {
        const clave = boton.dataset.config;
        if (!clave) {
            return;
        }
        if (clave === "inicio_automatico") {
            try {
                const resultado = await global.PuenteAgenda.obtener("alternar_inicio_automatico");
                ESTADO.sistema = resultado;
                ESTADO.configuracion.inicio_automatico = resultado.activo ? "1" : "0";
                boton.classList.toggle("activo", Boolean(resultado.activo));
                boton.setAttribute("aria-checked", String(Boolean(resultado.activo)));
                ESTADO.contexto?.toast(
                    "Arranque automático",
                    resultado.activo ? "La agenda se abrirá al iniciar el sistema." : "Arranque desactivado.",
                    "exito",
                    2600
                );
            } catch (error) {
                ESTADO.contexto?.toast("No se pudo cambiar", String(error.message || error), "error");
            }
            return;
        }
        const encendido = !boton.classList.contains("activo");
        boton.classList.toggle("activo", encendido);
        boton.setAttribute("aria-checked", String(encendido));
        ESTADO.configuracion[clave] = encendido ? "1" : "0";
        await guardarConfiguracion({ [clave]: encendido ? "1" : "0" });
    }

    /** Guarda los avisos seleccionados como lista de minutos. */
    async function alternarAviso(boton) {
        boton.classList.toggle("activo");
        const activos = new Set(
            [...ESTADO.raiz.querySelectorAll("[data-aviso].activo")].map((elemento) =>
                Number(elemento.dataset.aviso)
            )
        );
        const lista = [...activos].sort((a, b) => b - a).join(",");
        boton.setAttribute("aria-pressed", String(boton.classList.contains("activo")));
        ESTADO.configuracion.avisos_predeterminados = lista;
        await guardarConfiguracion({ avisos_predeterminados: lista });
    }

    /** Crea una suscripción desde el formulario. */
    async function crearSuscripcion(evento) {
        evento.preventDefault();
        const formulario = evento.currentTarget;
        const datos = {
            nombre: formulario.elements.nombre.value.trim(),
            url: formulario.elements.url.value.trim(),
            frecuencia_minutos: Number(formulario.elements.frecuencia_minutos.value) || 60
        };
        if (!datos.nombre || !datos.url) {
            ESTADO.contexto?.toast("Faltan datos", "Indica un nombre y una URL válida.", "aviso");
            return;
        }
        try {
            await global.PuenteAgenda.obtener("crear_suscripcion", JSON.stringify(datos));
            ESTADO.contexto?.toast("Calendario añadido", datos.nombre, "exito", 2600);
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo añadir", String(error.message || error), "error");
        }
    }

    /** Sincroniza un feed concreto. */
    async function sincronizarFeed(identificador) {
        try {
            const resultado = await global.PuenteAgenda.obtener(
                "sincronizar_suscripcion", Number(identificador)
            );
            ESTADO.contexto?.toast(
                "Calendario sincronizado",
                `${(resultado?.creados || 0) + (resultado?.actualizados || 0)} evento(s) al día`,
                "exito",
                2800
            );
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo sincronizar", String(error.message || error), "error");
        }
    }

    /** Activa o pausa un feed. */
    async function alternarFeed(boton) {
        const identificador = Number(boton.dataset.alternarFeed);
        const activa = boton.dataset.activa !== "1";
        try {
            await global.PuenteAgenda.obtener(
                "actualizar_suscripcion", identificador, JSON.stringify({ activa })
            );
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo actualizar", String(error.message || error), "error");
        }
    }

    /** Elimina un feed. */
    async function eliminarFeed(identificador) {
        try {
            await global.PuenteAgenda.obtener("eliminar_suscripcion", Number(identificador));
            ESTADO.contexto?.toast("Calendario eliminado", "Los eventos importados se conservan.", "exito", 2600);
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo eliminar", String(error.message || error), "error");
        }
    }

    /** Crea un respaldo manual. */
    async function crearRespaldo(boton) {
        boton.disabled = true;
        try {
            const respaldo = await global.PuenteAgenda.obtener("crear_respaldo");
            ESTADO.contexto?.toast(
                "Copia creada",
                `${respaldo.nombre} · ${tamano(respaldo.tamano_bytes)}`,
                "exito",
                3200
            );
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo crear la copia", String(error.message || error), "error");
        } finally {
            boton.disabled = false;
        }
    }

    /** Restaura un respaldo con confirmación en dos pasos. */
    async function restaurarRespaldo(boton) {
        const ruta = boton.dataset.restaurar;
        if (boton.dataset.confirmar !== "1") {
            boton.dataset.confirmar = "1";
            boton.classList.add("boton--peligro");
            boton.dataset.tooltip = "Pulsa otra vez para confirmar";
            ESTADO.contexto?.toast(
                "Confirmar restauración",
                "Vuelve a pulsar el botón para reemplazar los datos actuales.",
                "aviso",
                3600
            );
            global.setTimeout(() => {
                if (boton.isConnected) {
                    boton.dataset.confirmar = "0";
                    boton.classList.remove("boton--peligro");
                    boton.dataset.tooltip = "Restaurar copia";
                }
            }, 6000);
            return;
        }
        boton.disabled = true;
        try {
            await global.PuenteAgenda.obtener("restaurar_respaldo", ruta);
            ESTADO.contexto?.toast("Copia restaurada", "Los datos se han recargado.", "exito", 3200);
            await ESTADO.contexto?.recargarDatos?.();
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo restaurar", String(error.message || error), "error");
        } finally {
            boton.disabled = false;
        }
    }

    /** Elimina un respaldo con confirmación en dos pasos. */
    async function eliminarRespaldo(boton) {
        const ruta = boton.dataset.borrarRespaldo;
        if (boton.dataset.confirmar !== "1") {
            boton.dataset.confirmar = "1";
            boton.classList.add("boton--peligro");
            ESTADO.contexto?.toast("Confirmar borrado", "Vuelve a pulsar para eliminar la copia.", "aviso", 3200);
            global.setTimeout(() => {
                if (boton.isConnected) {
                    boton.dataset.confirmar = "0";
                    boton.classList.remove("boton--peligro");
                }
            }, 6000);
            return;
        }
        try {
            await global.PuenteAgenda.obtener("eliminar_respaldo", ruta);
            ESTADO.contexto?.toast("Copia eliminada", "El archivo se ha borrado del disco.", "exito", 2600);
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo eliminar", String(error.message || error), "error");
        }
    }

    /** Importa un archivo .ics elegido con el selector nativo. */
    async function importarICS() {
        try {
            const resultado = await global.PuenteAgenda.obtener("elegir_e_importar_ics");
            if (resultado?.cancelado) {
                return;
            }
            ESTADO.contexto?.toast(
                "Calendario importado",
                `${resultado?.creados || 0} evento(s) añadidos · ${resultado?.actualizados || 0} actualizados`,
                "exito",
                3000
            );
            await ESTADO.contexto?.recargarDatos?.();
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo importar", String(error.message || error), "error");
        }
    }

    /** Sincroniza todos los feeds activos. */
    async function sincronizarTodos() {
        try {
            const resultados = await global.PuenteAgenda.obtener("sincronizar_todo_ics");
            const cambios = (resultados || []).reduce(
                (total, resultado) =>
                    total + (resultado?.creados || 0) + (resultado?.actualizados || 0),
                0
            );
            ESTADO.contexto?.toast(
                "Sincronización completada",
                `${cambios} evento(s) actualizados`,
                "exito",
                3000
            );
            await recargar();
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo sincronizar", String(error.message || error), "error");
        }
    }

    /** Regenera la previsualización del informe. */
    async function refrescarInforme() {
        try {
            ESTADO.informe = await global.PuenteAgenda.obtener("generar_informe");
            ESTADO.raiz.innerHTML = plantilla();
            conectar();
            ESTADO.contexto?.toast("Informe actualizado", "Datos recalculados con la información más reciente.", "exito", 2400);
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo generar", String(error.message || error), "error");
        }
    }

    /** Guarda el informe en disco. */
    async function guardarInforme() {
        try {
            const resultado = await global.PuenteAgenda.obtener("guardar_informe");
            if (resultado?.cancelado) {
                return;
            }
            ESTADO.contexto?.toast("Informe guardado", resultado.nombre || "informe_academico.md", "exito", 3200);
        } catch (error) {
            ESTADO.contexto?.toast("No se pudo guardar", String(error.message || error), "error");
        }
    }

    /** Conecta todos los controles de la vista. */
    function conectar() {
        const raiz = ESTADO.raiz;
        if (!raiz) {
            return;
        }

        raiz.querySelectorAll(".ajustes-tema[data-tema]").forEach((boton) => {
            boton.addEventListener("click", () => cambiarTema(boton.dataset.tema));
        });

        raiz.querySelectorAll("[data-config]").forEach((boton) => {
            boton.addEventListener("click", () => alternarInterruptor(boton));
        });

        raiz.querySelectorAll("[data-campo]").forEach((control) => {
            control.addEventListener("change", () => {
                const clave = control.dataset.campo;
                const valor = String(control.value ?? "").trim();
                ESTADO.configuracion[clave] = valor;
                guardarConfiguracion({ [clave]: valor });
            });
        });

        raiz.querySelector('[data-rango="objetivo_academico"]')?.addEventListener("input", (evento) => {
            const valor = Number(evento.target.value) || 5;
            const etiqueta = raiz.querySelector("#objetivo-academico-valor");
            if (etiqueta) {
                etiqueta.textContent = valor.toFixed(1);
            }
            ESTADO.configuracion.objetivo_academico = String(valor);
        });
        raiz.querySelector('[data-rango="objetivo_academico"]')?.addEventListener("change", (evento) => {
            guardarConfiguracion({
                objetivo_academico: String(Number(evento.target.value) || 5)
            });
        });

        raiz.querySelectorAll("[data-aviso]").forEach((boton) => {
            boton.addEventListener("click", () => alternarAviso(boton));
        });

        raiz.querySelector("#form-suscripcion")?.addEventListener("submit", crearSuscripcion);
        raiz.querySelectorAll("[data-sincronizar-feed]").forEach((boton) => {
            boton.addEventListener("click", () => sincronizarFeed(boton.dataset.sincronizarFeed));
        });
        raiz.querySelectorAll("[data-alternar-feed]").forEach((boton) => {
            boton.addEventListener("click", () => alternarFeed(boton));
        });
        raiz.querySelectorAll("[data-eliminar-feed]").forEach((boton) => {
            boton.addEventListener("click", () => eliminarFeed(boton.dataset.eliminarFeed));
        });
        raiz.querySelector("[data-importar-ics]")?.addEventListener("click", importarICS);
        raiz.querySelector("[data-sincronizar-todos]")?.addEventListener("click", sincronizarTodos);

        raiz.querySelector("[data-crear-respaldo]")?.addEventListener("click", (evento) =>
            crearRespaldo(evento.currentTarget)
        );
        raiz.querySelectorAll("[data-restaurar]").forEach((boton) => {
            boton.addEventListener("click", () => restaurarRespaldo(boton));
        });
        raiz.querySelectorAll("[data-borrar-respaldo]").forEach((boton) => {
            boton.addEventListener("click", () => eliminarRespaldo(boton));
        });
        raiz.querySelector("[data-restaurar-archivo]")?.addEventListener("click", async () => {
            try {
                const resultado = await global.PuenteAgenda.obtener("elegir_y_restaurar_respaldo");
                if (resultado?.cancelado) {
                    return;
                }
                ESTADO.contexto?.toast("Copia restaurada", "Los datos se han recargado.", "exito", 3200);
                await ESTADO.contexto?.recargarDatos?.();
                await recargar();
            } catch (error) {
                ESTADO.contexto?.toast("No se pudo restaurar", String(error.message || error), "error");
            }
        });
        raiz.querySelector("[data-abrir-carpeta]")?.addEventListener("click", async () => {
            try {
                await global.PuenteAgenda.obtener("abrir_carpeta_respaldos");
            } catch (error) {
                ESTADO.contexto?.toast("No se pudo abrir", String(error.message || error), "error");
            }
        });

        raiz.querySelector("[data-refrescar-informe]")?.addEventListener("click", refrescarInforme);
        raiz.querySelector("[data-guardar-informe]")?.addEventListener("click", guardarInforme);
    }

    /* ------------------------------------------------------------------
       Ciclo de vida
       ------------------------------------------------------------------ */
    /**
     * Monta la vista de ajustes.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto compartido.
     */
    async function montar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        await recargar();
    }

    /**
     * Refresca cuando cambian los datos globales.
     * @param {HTMLElement} raiz Contenedor.
     * @param {object} contexto Contexto compartido.
     */
    async function actualizar(raiz, contexto) {
        ESTADO.raiz = raiz;
        ESTADO.contexto = contexto;
        const activo = document.activeElement;
        const editando =
            activo &&
            raiz.contains(activo) &&
            ["INPUT", "TEXTAREA", "SELECT"].includes(activo.tagName);
        if (editando) {
            return;
        }
        await recargar();
    }

    global.AgendaApp.registrarVista("ajustes", { montar, actualizar });
})(window);
