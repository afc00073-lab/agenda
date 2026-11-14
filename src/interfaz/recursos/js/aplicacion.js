/**
 * ============================================================================
 *  APLICACIÓN PRINCIPAL · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Controlador de la ventana web: arranca el puente con Python, carga el estado
 *  inicial, gestiona la navegación entre las seis vistas, el cambio de tema, la
 *  barra lateral colapsable, los modales de creación y los avisos internos.
 *
 *  Cada vista se registra con `AgendaApp.registrarVista(id, modulo)`. Un módulo
 *  solo necesita exponer `montar(raiz, contexto)` y, opcionalmente,
 *  `actualizar(raiz, contexto)`.
 *
 *  No hay ningún atajo de teclado: toda la interacción es con ratón o panel
 *  táctil, tal como exige el diseño de la aplicación.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { $, $$, escapar, icono } = U;

    /** Metadatos de las vistas. */
    const VISTAS = {
        inicio: {
            titulo: "Inicio",
            descripcion: "Tu día de un vistazo",
            icono: "inicio"
        },
        calendario: {
            titulo: "Calendario",
            descripcion: "Semana, mes y agenda diaria",
            icono: "calendario"
        },
        kanban: {
            titulo: "Tablero Kanban",
            descripcion: "Del pendiente a la entrega, paso a paso",
            icono: "kanban"
        },
        asignaturas: {
            titulo: "Asignaturas y notas",
            descripcion: "Tus materias, evaluaciones y media ponderada",
            icono: "asignaturas"
        },
        estudio: {
            titulo: "Pomodoro",
            descripcion: "Bloques de concentración con descansos",
            icono: "estudio"
        },
        analiticas: {
            titulo: "Analíticas",
            descripcion: "Constancia, carga de trabajo y tendencias",
            icono: "analiticas"
        },
        ajustes: {
            titulo: "Ajustes",
            descripcion: "Temas, avisos, respaldos y calendarios",
            icono: "ajustes"
        }
    };

    /** Paleta de colores disponible para las asignaturas. */
    const PALETA = [
        "#7c6cff", "#28c8a0", "#ff7a59", "#ffc857",
        "#4aa8ff", "#ff5c8a", "#9b8cff", "#3ddc97"
    ];

    const ESTADO = {
        configuracion: {},
        asignaturas: [],
        panel: null,
        tema: "cristal-medianoche",
        vista: "inicio",
        conectado: false,
        datosListos: false,
        modulos: {},
        cargaEnCurso: null,
        ultimaActualizacion: 0,
        modalAbierto: false
    };

    const NODOS = {
        aplicacion: null,
        barraLateral: null,
        contenedor: null,
        titulo: null,
        subtitulo: null,
        modal: null,
        avatar: null,
        contadorHoy: null,
        contadorKanban: null,
        enfoqueValor: null,
        enfoqueDetalle: null
    };

    /* ==================================================================
       Arranque
       ================================================================== */
    /** Punto de entrada: prepara el documento y carga el estado inicial. */
    function iniciar() {
        NODOS.aplicacion = $("#aplicacion");
        NODOS.barraLateral = $("#barra-lateral");
        NODOS.contenedor = $("#vista-contenedor");
        NODOS.titulo = $("#titulo-vista");
        NODOS.subtitulo = $("#subtitulo-vista");
        NODOS.modal = $("#contenedor-modal");
        NODOS.avatar = $("#avatar-estudiante");
        NODOS.contadorHoy = $("#contador-hoy");
        NODOS.contadorKanban = $("#contador-kanban");
        NODOS.enfoqueValor = $("#enfoque-valor");
        NODOS.enfoqueDetalle = $("#enfoque-detalle");

        conectarNavegacion();
        conectarTemas();
        conectarBarraLateral();
        conectarAcciones();
        conectarSenales();
        conectarBotonesGlobales();

        global.NotificacionesInternas.iniciar();
        cargarInicial();
    }

    /** Conecta los enlaces de navegación. */
    function conectarNavegacion() {
        $$(".navegacion__enlace[data-vista]").forEach((boton) => {
            boton.addEventListener("click", () => navegarA(boton.dataset.vista));
        });
    }

    /** Conecta el selector de temas y aplica el guardado. */
    function conectarTemas() {
        $$(".selector-tema__opcion").forEach((opcion) => {
            opcion.addEventListener("click", () => cambiarTema(opcion.dataset.temaOpcion));
        });
    }

    /** Restaura y controla el estado colapsado de la barra lateral. */
    function conectarBarraLateral() {
        const boton = $("#boton-colapsar");
        if (!boton) {
            return;
        }
        let colapsada = false;
        try {
            colapsada = global.localStorage.getItem("agenda:barra-colapsada") === "1";
        } catch (error) {
            colapsada = false;
        }
        NODOS.barraLateral.classList.toggle("colapsada", colapsada);
        actualizarBotonColapsar(colapsada);

        boton.addEventListener("click", () => {
            const activa = NODOS.barraLateral.classList.toggle("colapsada");
            actualizarBotonColapsar(activa);
            try {
                global.localStorage.setItem("agenda:barra-colapsada", activa ? "1" : "0");
            } catch (error) {
                /* almacenamiento no disponible: no es crítico */
            }
        });
    }

    /** Ajusta la etiqueta accesible del botón de colapso. */
    function actualizarBotonColapsar(colapsada) {
        const boton = $("#boton-colapsar");
        if (boton) {
            boton.dataset.tooltip = colapsada ? "Expandir menú" : "Colapsar menú";
            boton.setAttribute(
                "aria-label",
                colapsada ? "Expandir barra lateral" : "Colapsar barra lateral"
            );
        }
    }

    /** Conecta los botones de acción de la cabecera. */
    function conectarAcciones() {
        $("#boton-nueva-tarea")?.addEventListener("click", () => abrirModal("tarea"));
        NODOS.avatar?.addEventListener("click", () => navegarA("ajustes"));
    }

    /** Conecta las señales que Python reemite como eventos DOM. */
    function conectarSenales() {
        document.addEventListener("agenda:datosActualizados", (evento) => {
            programarRecarga(evento.detail);
        });
        document.addEventListener("agenda:solicitudNavegacion", (evento) => {
            navegarA(evento.detail || "inicio");
        });
        document.addEventListener("agenda:solicitudModal", (evento) => {
            abrirModal(evento.detail || "tarea");
        });
        document.addEventListener("agenda:temaCambiado", (evento) => {
            aplicarTema(evento.detail);
        });
        document.addEventListener("agenda:temaExterno", (evento) => {
            aplicarTema(evento.detail);
        });
    }

    /** Botones genéricos presentes en varias vistas. */
    function conectarBotonesGlobales() {
        document.addEventListener("click", (evento) => {
            const disparador = evento.target.closest("[data-accion-global]");
            if (!disparador) {
                return;
            }
            const accion = disparador.dataset.accionGlobal;
            if (accion === "nueva-tarea") {
                abrirModal("tarea");
            } else if (accion === "nuevo-evento") {
                abrirModal("evento");
            } else if (accion === "nueva-asignatura") {
                abrirModal("asignatura");
            } else if (accion === "ir-calendario") {
                navegarA("calendario");
            } else if (accion === "ir-kanban") {
                navegarA("kanban");
            } else if (accion === "ir-estudio") {
                navegarA("estudio");
            }
        });
    }

    /* ==================================================================
       Carga de datos
       ================================================================== */
    /** Solicita el estado inicial completo y lo aplica. */
    async function cargarInicial() {
        try {
            const datos = await global.PuenteAgenda.obtener("obtener_inicializacion");
            ESTADO.conectado = true;
            aplicarEstadoInicial(datos);
            ESTADO.datosListos = true;
            renderizarVista();
        } catch (error) {
            console.error("[app] No se pudo cargar el estado inicial", error);
            ESTADO.datosListos = true;
            mostrarSinConexion(error);
        }
    }

    /**
     * Aplica el paquete de inicialización enviado por Python.
     * @param {object} datos Estado inicial.
     */
    function aplicarEstadoInicial(datos) {
        ESTADO.configuracion = datos.configuracion || {};
        ESTADO.asignaturas = datos.asignaturas || [];
        ESTADO.panel = datos.panel || null;
        ESTADO.tema = ESTADO.configuracion.tema || datos.gadget?.tema || "cristal-medianoche";

        aplicarTema(ESTADO.tema, false);
        actualizarCabecera();
        actualizarResumen();
        actualizarContadores();
        actualizarEnfoque();
        actualizarPerfil();
    }

    /** Vuelve a pedir los datos que alimentan todas las vistas. */
    async function recargarDatos(silencioso = true) {
        if (ESTADO.cargaEnCurso) {
            return ESTADO.cargaEnCurso;
        }
        ESTADO.cargaEnCurso = (async () => {
            try {
                const [panel, asignaturas] = await Promise.all([
                    global.PuenteAgenda.obtener("obtener_panel_inicio"),
                    global.PuenteAgenda.obtener("listar_asignaturas")
                ]);
                ESTADO.panel = panel;
                ESTADO.asignaturas = asignaturas || [];
                ESTADO.ultimaActualizacion = Date.now();
                actualizarCabecera();
                actualizarResumen();
                actualizarContadores();
                actualizarEnfoque();
                actualizarPerfil();
                const modulo = ESTADO.modulos[ESTADO.vista];
                if (modulo) {
                    if (typeof modulo.actualizar === "function" && NODOS.contenedor.firstElementChild) {
                        await modulo.actualizar(NODOS.contenedor.firstElementChild, contexto());
                    } else {
                        renderizarVista();
                    }
                }
            } catch (error) {
                if (!silencioso) {
                    toast("No se pudieron actualizar los datos", String(error.message || error), "error");
                }
            } finally {
                ESTADO.cargaEnCurso = null;
            }
        })();
        return ESTADO.cargaEnCurso;
    }

    /** Recarga con un pequeño retardo para agrupar ráfagas de cambios. */
    const programarRecarga = U.retrasar(() => recargarDatos(true), 220);

    /* ==================================================================
       Navegación
       ================================================================== */
    /**
     * Cambia de vista.
     * @param {string} identificador Identificador de la vista.
     * @param {object} [opciones] Opciones para la vista (por ejemplo, un ancla).
     */
    function navegarA(identificador, opciones = {}) {
        const destino = VISTAS[identificador] ? identificador : "inicio";
        ESTADO.vista = destino;

        $$(".navegacion__enlace[data-vista]").forEach((boton) => {
            const activa = boton.dataset.vista === destino;
            boton.classList.toggle("activo", activa);
            if (activa) {
                boton.setAttribute("aria-current", "page");
            } else {
                boton.removeAttribute("aria-current");
            }
        });

        actualizarCabecera();
        renderizarVista(opciones);

        if (opciones.ancla) {
            global.setTimeout(() => {
                const ancla = document.getElementById(opciones.ancla);
                ancla?.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 120);
        }
        $("#contenido")?.scrollTo({ top: 0, behavior: "smooth" });
    }

    /** Dibuja la vista activa dentro del contenedor principal. */
    function renderizarVista(opciones = {}) {
        if (!NODOS.contenedor) {
            return;
        }
        const modulo = ESTADO.modulos[ESTADO.vista];
        NODOS.contenedor.innerHTML = "";
        if (!modulo || typeof modulo.montar !== "function") {
            NODOS.contenedor.innerHTML = vistaEnPreparacion();
            return;
        }
        const raiz = document.createElement("section");
        raiz.className = "vista activa";
        raiz.dataset.vista = ESTADO.vista;
        NODOS.contenedor.append(raiz);
        try {
            modulo.montar(raiz, contexto(opciones));
        } catch (error) {
            console.error(`[app] Error al montar la vista ${ESTADO.vista}`, error);
            raiz.innerHTML = U.vacio(
                "alerta",
                "No se pudo abrir esta vista",
                String(error.message || error),
                '<button class="boton boton--primario" data-accion-global="nueva-tarea" type="button">Crear una tarea</button>'
            );
        }
    }

    /**
     * Registra un módulo de vista.
     * @param {string} identificador Identificador de la vista.
     * @param {{montar: Function, actualizar?: Function}} modulo Módulo de vista.
     */
    function registrarVista(identificador, modulo) {
        ESTADO.modulos[identificador] = modulo;
        if (ESTADO.datosListos && ESTADO.vista === identificador) {
            renderizarVista();
        }
        global.setTimeout(() => {
            if (
                ESTADO.vista === identificador &&
                NODOS.contenedor &&
                !NODOS.contenedor.firstElementChild?.dataset.vista
            ) {
                renderizarVista();
            }
        }, 0);
    }

    /** Contexto que recibe cada vista. */
    function contexto(opciones = {}) {
        return {
            ...opciones,
            configuracion: ESTADO.configuracion,
            asignaturas: ESTADO.asignaturas,
            panel: ESTADO.panel,
            tema: ESTADO.tema,
            conectado: ESTADO.conectado,
            utilidades: U,
            navegarA,
            abrirModal,
            toast,
            recargarDatos,
            actualizarContadores,
            actualizarCabecera
        };
    }

    /* ==================================================================
       Cabecera y resumen lateral
       ================================================================== */
    /** Actualiza el título y el subtítulo según la vista y el panel. */
    function actualizarCabecera() {
        if (!NODOS.titulo) {
            return;
        }
        const panel = ESTADO.panel;
        if (ESTADO.vista === "inicio" && panel) {
            NODOS.titulo.textContent = `${panel.saludo || "Hola"}, ${panel.nombre_estudiante || "Estudiante"}`;
            NODOS.subtitulo.textContent = panel.fecha || U.fechaLarga(new Date());
        } else {
            const vista = VISTAS[ESTADO.vista] || VISTAS.inicio;
            NODOS.titulo.textContent = vista.titulo;
            NODOS.subtitulo.textContent = vista.descripcion;
        }
    }

    /** Muestra la fecha y el número de tareas pendientes de hoy. */
    function actualizarResumen() {
        if (!ESTADO.panel || ESTADO.vista !== "inicio") {
            return;
        }
        const pendientes = (ESTADO.panel.tareas_hoy || []).length;
        const fecha = ESTADO.panel.fecha || U.fechaLarga(new Date());
        const sufijo = pendientes
            ? `${pendientes} tarea${pendientes === 1 ? "" : "s"} para hoy`
            : "Todo al día";
        NODOS.subtitulo.textContent = `${fecha} · ${sufijo}`;
    }

    /** Refleja el nombre del estudiante en el avatar. */
    function actualizarPerfil() {
        const nombre = ESTADO.configuracion.nombre_estudiante || "Estudiante";
        if (NODOS.avatar) {
            NODOS.avatar.textContent = U.iniciales(nombre);
            NODOS.avatar.dataset.tooltip = `${nombre} · abrir ajustes`;
        }
    }

    /** Sincroniza los contadores de la barra lateral. */
    function actualizarContadores(extra = {}) {
        const hoy = ESTADO.panel?.agenda_hoy?.length ?? 0;
        if (NODOS.contadorHoy) {
            NODOS.contadorHoy.textContent = String(hoy);
            NODOS.contadorHoy.classList.toggle("oculto", hoy === 0);
        }
        if (NODOS.contadorKanban) {
            const totalKanban = extra.kanban ?? ESTADO.panel?.kpis?.tareas_kanban;
            if (typeof totalKanban === "number") {
                NODOS.contadorKanban.textContent = String(totalKanban);
                NODOS.contadorKanban.classList.toggle("oculto", totalKanban === 0);
            }
        }
    }

    /** Actualiza la tarjeta de enfoque semanal. */
    function actualizarEnfoque() {
        if (!NODOS.enfoqueValor || !ESTADO.panel) {
            return;
        }
        const kpis = ESTADO.panel.kpis || {};
        NODOS.enfoqueValor.textContent = U.duracion((kpis.horas_estudio_semana || 0) * 60);
        const minutosHoy = kpis.minutos_enfoque_hoy || 0;
        const tareas = kpis.tareas_completadas_semana || 0;
        NODOS.enfoqueDetalle.textContent = minutosHoy
            ? `Hoy: ${U.duracion(minutosHoy)} · ${tareas} tarea(s) esta semana.`
            : `${tareas} tarea(s) completadas esta semana.`;
    }

    /* ==================================================================
       Temas
       ================================================================== */
    /**
     * Aplica un tema visual y lo persiste.
     * @param {string} tema Identificador del tema.
     * @param {boolean} [persistir] Si se avisa a Python del cambio.
     */
    function aplicarTema(tema, persistir = true) {
        const valido = ["cristal-medianoche", "noche-nordica", "luz-pura"].includes(tema)
            ? tema
            : "cristal-medianoche";
        ESTADO.tema = valido;
        global.PuenteAgenda.aplicarTema(valido);
        $$(".selector-tema__opcion").forEach((opcion) => {
            opcion.classList.toggle("activa", opcion.dataset.temaOpcion === valido);
        });
        if (persistir) {
            global.PuenteAgenda.llamar("cambiar_tema", valido).catch((error) =>
                console.warn("[app] No se pudo guardar el tema", error)
            );
        }
    }

    /**
     * Cambia el tema desde el selector y muestra un aviso discreto.
     * @param {string} tema Identificador del tema.
     */
    function cambiarTema(tema) {
        if (tema === ESTADO.tema) {
            return;
        }
        aplicarTema(tema);
        const nombres = {
            "cristal-medianoche": "Cristal Medianoche",
            "noche-nordica": "Noche Nórdica",
            "luz-pura": "Luz Pura"
        };
        toast("Tema aplicado", nombres[tema] || tema, "exito", 2600);
    }

    /* ==================================================================
       Modales
       ================================================================== */
    /**
     * Abre un modal de creación.
     * @param {string} tipo `tarea`, `evento`, `asignatura` o `evaluacion`.
     * @param {object} [datos] Valores iniciales.
     */
    function abrirModal(tipo, datos = {}) {
        if (ESTADO.modalAbierto) {
            cerrarModal();
        }
        const definiciones = {
            tarea: {
                titulo: datos.id ? "Editar tarea" : "Nueva tarea",
                descripcion: "Añádela al tablero Kanban y recibe un recordatorio antes de la entrega.",
                icono: "check",
                ancho: false,
                contenido: formularioTarea(datos),
                guardar: datos.id ? "Guardar cambios" : "Crear tarea",
                alGuardar: guardarTarea
            },
            evento: {
                titulo: datos.id ? "Editar evento" : "Nuevo evento",
                descripcion: "Clases, exámenes, entregas o bloques de estudio con fecha y hora.",
                icono: "calendario",
                ancho: true,
                contenido: formularioEvento(datos),
                guardar: datos.id ? "Guardar cambios" : "Crear evento",
                alGuardar: guardarEvento
            },
            asignatura: {
                titulo: datos.id ? "Editar asignatura" : "Nueva asignatura",
                descripcion: "Cada materia agrupa sus eventos, evaluaciones y nota media.",
                icono: "asignaturas",
                ancho: false,
                contenido: formularioAsignatura(datos),
                guardar: datos.id ? "Guardar cambios" : "Crear asignatura",
                alGuardar: guardarAsignatura
            }
        };
        const definicion = definiciones[tipo];
        if (!definicion) {
            toast(
                "Formulario no disponible",
                "Esta acción se habilitará en la vista correspondiente.",
                "aviso"
            );
            return;
        }
        construirModal(tipo, definicion);
        const formulario = $("#form-modal");
        if (formulario && datos.id) {
            formulario.dataset.registroId = String(datos.id);
        }
    }

    /**
     * Monta el marcado del modal y conecta sus acciones.
     * @param {string} tipo Identificador del formulario.
     * @param {object} definicion Configuración del modal.
     */
    function construirModal(tipo, definicion) {
        const fondo = document.createElement("div");
        fondo.className = "modal-fondo";
        fondo.id = "modal-fondo";
        fondo.innerHTML = `
            <div class="modal ${definicion.ancho ? "modal--ancho" : ""}" role="dialog"
                 aria-modal="true" aria-labelledby="modal-titulo">
                <header class="modal__cabecera">
                    <span class="modal__icono">${icono(definicion.icono)}</span>
                    <div>
                        <h2 class="modal__titulo" id="modal-titulo">${escapar(definicion.titulo)}</h2>
                        <p class="modal__descripcion">${escapar(definicion.descripcion)}</p>
                    </div>
                    <button class="modal__cerrar" type="button" data-cerrar-modal aria-label="Cerrar">
                        ${icono("x")}
                    </button>
                </header>
                <form id="form-modal" novalidate>
                    <div class="modal__cuerpo">${definicion.contenido}</div>
                    <footer class="modal__pie">
                        <button class="boton boton--fantasma" type="button" data-cerrar-modal>Cancelar</button>
                        <button class="boton boton--primario" type="submit" id="boton-guardar-modal">
                            ${icono("check")}${escapar(definicion.guardar)}
                        </button>
                    </footer>
                </form>
            </div>`;

        NODOS.modal.append(fondo);
        requestAnimationFrame(() => fondo.classList.add("visible"));
        ESTADO.modalAbierto = true;

        fondo.addEventListener("click", (evento) => {
            if (evento.target === fondo) {
                cerrarModal();
            }
        });
        $$("[data-cerrar-modal]", fondo).forEach((boton) =>
            boton.addEventListener("click", cerrarModal)
        );

        const formulario = $("#form-modal", fondo);
        formulario.addEventListener("submit", async (evento) => {
            evento.preventDefault();
            const boton = $("#boton-guardar-modal", fondo);
            boton.disabled = true;
            try {
                const resultado = await definicion.alGuardar(formulario, tipo);
                if (resultado !== false) {
                    cerrarModal();
                }
            } catch (error) {
                toast("No se pudo guardar", String(error.message || error), "error");
            } finally {
                boton.disabled = false;
            }
        });

        // Selección de color dentro de los formularios que la incluyan.
        $$(".selector-color__opcion", fondo).forEach((opcion) => {
            opcion.addEventListener("click", () => {
                $$(".selector-color__opcion", fondo).forEach((elemento) =>
                    elemento.classList.remove("activa")
                );
                opcion.classList.add("activa");
                const entrada = $("#color-asignatura", fondo);
                if (entrada) {
                    entrada.value = opcion.dataset.color;
                }
            });
        });

        global.setTimeout(() => {
            const primero = $("input:not([type=hidden]), select, textarea", fondo);
            primero?.focus();
        }, 60);
    }

    /** Cierra el modal abierto con una transición breve. */
    function cerrarModal() {
        const fondo = $("#modal-fondo");
        if (!fondo) {
            ESTADO.modalAbierto = false;
            return;
        }
        fondo.classList.add("cerrando");
        global.setTimeout(() => {
            fondo.remove();
            ESTADO.modalAbierto = false;
        }, 180);
    }

    /* ------------------------------------------------------------------
       Formularios
       ------------------------------------------------------------------ */
    /**
     * Genera el HTML de un campo de formulario.
     * @param {object} opciones Configuración del campo.
     * @returns {string} HTML del campo.
     */
    function campo(opciones) {
        const {
            id,
            etiqueta,
            tipo = "text",
            valor = "",
            requerido = false,
            ancho = false,
            ayuda = "",
            placeholder = "",
            opciones: lista = null,
            minimo,
            maximo,
            paso
        } = opciones;
        let control;
        if (lista) {
            control = `<select class="campo__control" id="${id}" name="${id}" ${requerido ? "required" : ""}>
                ${lista.map((elemento) => {
                    const seleccionado = String(elemento.valor) === String(valor) ? "selected" : "";
                    return `<option value="${escapar(elemento.valor)}" ${seleccionado}>${escapar(elemento.etiqueta)}</option>`;
                }).join("")}
            </select>`;
        } else if (tipo === "textarea") {
            control = `<textarea class="campo__control" id="${id}" name="${id}"
                placeholder="${escapar(placeholder)}" ${requerido ? "required" : ""}>${escapar(valor)}</textarea>`;
        } else {
            const atributos = [
                `type="${tipo}"`,
                `class="campo__control"`,
                `id="${id}"`,
                `name="${id}"`,
                `value="${escapar(valor)}"`,
                `placeholder="${escapar(placeholder)}"`,
                requerido ? "required" : "",
                minimo !== undefined ? `min="${minimo}"` : "",
                maximo !== undefined ? `max="${maximo}"` : "",
                paso !== undefined ? `step="${paso}"` : ""
            ].filter(Boolean).join(" ");
            control = `<input ${atributos}>`;
        }
        return `
            <label class="campo ${ancho ? "campo--ancho-completo" : ""}" for="${id}">
                <span class="campo__etiqueta">${escapar(etiqueta)}${requerido ? " *" : ""}</span>
                ${control}
                ${ayuda ? `<span class="campo__ayuda">${escapar(ayuda)}</span>` : ""}
            </label>`;
    }

    /** Opciones de asignaturas para los selectores. */
    function opcionesAsignaturas(valor = "") {
        return [
            { valor: "", etiqueta: "Sin asignatura" },
            ...ESTADO.asignaturas.map((asignatura) => ({
                valor: String(asignatura.id),
                etiqueta: asignatura.nombre
            }))
        ].map((elemento) => ({
            ...elemento,
            valor: elemento.valor === String(valor || "") ? String(valor || "") : elemento.valor
        }));
    }

    /** Opciones de prioridad. */
    const OPCIONES_PRIORIDAD = [
        { valor: "baja", etiqueta: "Baja" },
        { valor: "media", etiqueta: "Media" },
        { valor: "alta", etiqueta: "Alta" },
        { valor: "critica", etiqueta: "Crítica" }
    ];

    /** Devuelve la fecha de hoy y una hora razonable para nuevos eventos. */
    function valoresTemporales() {
        const ahora = new Date();
        const siguiente = new Date(ahora.getTime() + 60 * 60 * 1000);
        return {
            fecha: U.claveFecha(ahora),
            hora: `${U.dosDigitos(siguiente.getHours())}:00`,
            horaFin: `${U.dosDigitos((siguiente.getHours() + 1) % 24)}:00`
        };
    }

    /** Formulario de tarea. */
    function formularioTarea(datos = {}) {
        const temporales = valoresTemporales();
        return `
            <div class="formulario formulario--dos-columnas">
                ${campo({ id: "titulo", etiqueta: "Título", valor: datos.titulo || "", requerido: true, ancho: true, placeholder: "Entregar práctica de estadística" })}
                ${campo({ id: "asignatura_id", etiqueta: "Asignatura", valor: datos.asignatura_id || "", opciones: opcionesAsignaturas(datos.asignatura_id) })}
                ${campo({ id: "prioridad", etiqueta: "Prioridad", valor: datos.prioridad || "media", opciones: OPCIONES_PRIORIDAD })}
                ${campo({ id: "fecha", etiqueta: "Fecha límite", tipo: "date", valor: datos.fecha || temporales.fecha, requerido: true })}
                ${campo({ id: "hora", etiqueta: "Hora", tipo: "time", valor: datos.hora || temporales.hora, requerido: true })}
                ${campo({ id: "descripcion", etiqueta: "Notas", tipo: "textarea", valor: datos.descripcion || "", ancho: true, placeholder: "Detalles, enlaces o criterios de entrega" })}
            </div>`;
    }

    /** Formulario de evento académico. */
    function formularioEvento(datos = {}) {
        const temporales = valoresTemporales();
        return `
            <div class="formulario formulario--dos-columnas">
                ${campo({
                    id: "tipo",
                    etiqueta: "Tipo de evento",
                    valor: datos.tipo || "clase",
                    opciones: [
                        { valor: "clase", etiqueta: "Clase" },
                        { valor: "examen", etiqueta: "Examen" },
                        { valor: "entrega", etiqueta: "Entrega" },
                        { valor: "estudio", etiqueta: "Sesión de estudio" }
                    ]
                })}
                ${campo({ id: "titulo", etiqueta: "Título", valor: datos.titulo || "", requerido: true, placeholder: "Examen parcial de Álgebra" })}
                ${campo({ id: "asignatura_id", etiqueta: "Asignatura", valor: datos.asignatura_id || "", opciones: opcionesAsignaturas(datos.asignatura_id) })}
                ${campo({ id: "prioridad", etiqueta: "Prioridad", valor: datos.prioridad || "media", opciones: OPCIONES_PRIORIDAD })}
                ${campo({ id: "fecha", etiqueta: "Fecha de inicio", tipo: "date", valor: datos.fecha || temporales.fecha, requerido: true })}
                ${campo({ id: "hora", etiqueta: "Hora de inicio", tipo: "time", valor: datos.hora || datos.fecha_inicio?.slice(11, 16) || temporales.hora, requerido: true })}
                ${campo({ id: "fecha_fin", etiqueta: "Fecha de fin (opcional)", tipo: "date", valor: datos.fecha_fin || "" })}
                ${campo({ id: "hora_fin", etiqueta: "Hora de fin (opcional)", tipo: "time", valor: datos.hora_fin || "" })}
                ${campo({ id: "ubicacion", etiqueta: "Aula o enlace", valor: datos.ubicacion || "", ancho: true, placeholder: "Aula 3.2 · https://aula virtual" })}
                ${campo({ id: "descripcion", etiqueta: "Descripción", tipo: "textarea", valor: datos.descripcion || "", ancho: true })}
            </div>`;
    }

    /** Formulario de asignatura con selector de color. */
    function formularioAsignatura(datos = {}) {
        const color = datos.color || PALETA[0];
        return `
            <div class="formulario formulario--dos-columnas">
                ${campo({ id: "nombre", etiqueta: "Nombre", valor: datos.nombre || "", requerido: true, ancho: true, placeholder: "Cálculo II" })}
                ${campo({ id: "codigo", etiqueta: "Código", valor: datos.codigo || "", placeholder: "MAT-204" })}
                ${campo({ id: "creditos", etiqueta: "Créditos ECTS", tipo: "number", valor: datos.creditos || 6, minimo: 0, maximo: 60, paso: 0.5 })}
                ${campo({ id: "profesor", etiqueta: "Profesorado", valor: datos.profesor || "" })}
                ${campo({ id: "aula", etiqueta: "Aula habitual", valor: datos.aula || "" })}
                <div class="campo campo--ancho-completo">
                    <span class="campo__etiqueta">Color de la asignatura</span>
                    <input type="hidden" id="color-asignatura" name="color" value="${escapar(color)}">
                    <div class="selector-color">
                        ${PALETA.map((tono) => `
                            <button class="selector-color__opcion ${tono === color ? "activa" : ""}"
                                    type="button" data-color="${tono}" aria-label="Elegir color ${tono}"
                                    style="background:${tono}"></button>`).join("")}
                    </div>
                </div>
            </div>`;
    }

    /* ------------------------------------------------------------------
       Guardado
       ------------------------------------------------------------------ */
    /** Recoge el valor de un control del formulario. */
    const valor = (formulario, nombre) =>
        (formulario.elements[nombre]?.value ?? "").toString().trim();

    /** Guarda una tarea nueva. */
    async function guardarTarea(formulario) {
        const titulo = valor(formulario, "titulo");
        if (!titulo) {
            toast("Falta el título", "Escribe un nombre para la tarea.", "aviso");
            return false;
        }
        const fecha = valor(formulario, "fecha");
        const hora = valor(formulario, "hora") || "23:59";
        const datos = {
            titulo,
            tipo: "tarea",
            fecha_inicio: `${fecha}T${hora}`,
            fecha_fin: `${fecha}T${hora}`,
            asignatura_id: valor(formulario, "asignatura_id") || null,
            prioridad: valor(formulario, "prioridad") || "media",
            descripcion: valor(formulario, "descripcion")
        };
        const identificador = formulario.dataset.registroId;
        if (identificador) {
            await global.PuenteAgenda.obtener(
                "actualizar_evento", Number(identificador), JSON.stringify(datos)
            );
            toast("Tarea actualizada", titulo, "exito");
        } else {
            datos.estado_kanban = "pendiente";
            datos.recordatorios = [120, 15];
            await global.PuenteAgenda.obtener("crear_evento", JSON.stringify(datos));
            toast("Tarea creada", titulo, "exito");
        }
        await recargarDatos(false);
        return true;
    }

    /** Guarda un evento nuevo. */
    async function guardarEvento(formulario) {
        const titulo = valor(formulario, "titulo");
        if (!titulo) {
            toast("Falta el título", "Escribe un nombre para el evento.", "aviso");
            return false;
        }
        const fecha = valor(formulario, "fecha");
        const hora = valor(formulario, "hora") || "08:00";
        const fechaFin = valor(formulario, "fecha_fin") || fecha;
        const horaFin = valor(formulario, "hora_fin") || hora;
        const datos = {
            titulo,
            tipo: valor(formulario, "tipo") || "clase",
            fecha_inicio: `${fecha}T${hora}`,
            fecha_fin: `${fechaFin}T${horaFin}`,
            asignatura_id: valor(formulario, "asignatura_id") || null,
            ubicacion: valor(formulario, "ubicacion"),
            prioridad: valor(formulario, "prioridad") || "media",
            descripcion: valor(formulario, "descripcion")
        };
        const identificador = formulario.dataset.registroId;
        if (identificador) {
            await global.PuenteAgenda.obtener(
                "actualizar_evento", Number(identificador), JSON.stringify(datos)
            );
            toast("Evento actualizado", titulo, "exito");
        } else {
            await global.PuenteAgenda.obtener("crear_evento", JSON.stringify(datos));
            toast("Evento creado", `${titulo} · ${U.fechaCorta(fecha)}`, "exito");
        }
        await recargarDatos(false);
        return true;
    }

    /** Guarda una asignatura nueva. */
    async function guardarAsignatura(formulario) {
        const nombre = valor(formulario, "nombre");
        if (!nombre) {
            toast("Falta el nombre", "Escribe el nombre de la asignatura.", "aviso");
            return false;
        }
        const datos = {
            nombre,
            codigo: valor(formulario, "codigo"),
            creditos: Number(valor(formulario, "creditos")) || 6,
            profesor: valor(formulario, "profesor"),
            aula: valor(formulario, "aula"),
            color: valor(formulario, "color") || PALETA[0]
        };
        const identificador = formulario.dataset.registroId;
        if (identificador) {
            await global.PuenteAgenda.obtener(
                "actualizar_asignatura", Number(identificador), JSON.stringify(datos)
            );
            toast("Asignatura actualizada", nombre, "exito");
        } else {
            await global.PuenteAgenda.obtener("crear_asignatura", JSON.stringify(datos));
            toast("Asignatura creada", nombre, "exito");
        }
        await recargarDatos(false);
        return true;
    }

    /* ==================================================================
       Utilidades expuestas
       ================================================================== */
    /** Aviso interno flexible: acepta un objeto de Python o argumentos. */
    function toast(titulo, mensaje, variante) {
        if (titulo && typeof titulo === "object") {
            const datos = titulo;
            return global.NotificacionesInternas.toast(
                datos.titulo || "Aviso",
                datos.mensaje || "",
                datos.variante || "info",
                datos.duracion || 4600
            );
        }
        return global.NotificacionesInternas.toast(titulo, mensaje, variante);
    }

    /** Vista de respaldo cuando una sección aún no está conectada. */
    function vistaEnPreparacion() {
        const vista = VISTAS[ESTADO.vista] || VISTAS.inicio;
        return `
            <div class="seccion">
                <div class="tarjeta">
                    <div class="tarjeta__cuerpo">
                        ${U.vacio(
                            vista.icono,
                            `${vista.titulo} está tomando forma`,
                            "El módulo de esta vista se conectará en la siguiente iteración del proyecto."
                        )}
                    </div>
                </div>
            </div>`;
    }

    /** Mensaje controlado cuando la página se abre sin Python. */
    function mostrarSinConexion(error) {
        if (NODOS.contenedor) {
            NODOS.contenedor.innerHTML = `
                <div class="seccion">
                    <div class="tarjeta">
                        <div class="tarjeta__cuerpo">
                            ${U.vacio(
                                "informacion",
                                "Modo de diseño sin conexión",
                                "Abre la aplicación con «python main.py» para cargar tus datos académicos."
                            )}
                        </div>
                    </div>
                </div>`;
        }
        NODOS.titulo.textContent = "Agenda Académica Inteligente";
        NODOS.subtitulo.textContent = "Vista previa del diseño · sin conexión con el backend";
        console.warn("[app] Sin puente QWebChannel", error);
    }

    /* Exposición pública que consume Python y cada vista. */
    global.AgendaApp = {
        iniciar,
        navegarA,
        abrirModal,
        cerrarModal,
        toast,
        registrarVista,
        recargarDatos,
        actualizarContadores,
        actualizarCabecera,
        aplicarTema,
        contexto,
        estado: ESTADO,
        vistas: VISTAS,
        paleta: PALETA
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})(window);
