/**
 * ============================================================================
 *  NOTIFICACIONES INTERNAS · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Gestiona la campana de la barra superior y los avisos flotantes (*toasts*).
 *  Los avisos nativos los lanza Python; aquí se muestra el reflejo dentro de la
 *  aplicación para que el usuario pueda marcarlos como vistos o posponerlos.
 *
 *  Todo se maneja con el ratón: no se registra ningún atajo de teclado.
 * ============================================================================
 */
(function (global) {
    "use strict";

    const U = global.AgendaUtilidades;
    const { $, escapar, icono, horaCorta, fechaCorta, hoyIso } = U;

    const ESTADO = {
        iniciado: false,
        avisos: [],
        menuAbierto: false,
        topeToasts: 4,
        temporizadores: new WeakMap()
    };

    const NODOS = {
        contenedor: null,
        campana: null,
        insignia: null,
        menu: null,
        lista: null,
        botonMarcarTodas: null,
        botonVerTodas: null
    };

    const ICONOS_VARIANTE = {
        info: "informacion",
        exito: "exito",
        aviso: "alerta",
        error: "alerta"
    };

    /* ------------------------------------------------------------------
       Toasts
       ------------------------------------------------------------------ */
    /**
     * Muestra un aviso flotante autodestructivo.
     * @param {string} titulo Texto principal.
     * @param {string} [mensaje] Detalle opcional.
     * @param {string} [variante] `info`, `exito`, `aviso` o `error`.
     * @param {number} [duracion] Milisegundos visibles.
     */
    function toast(titulo, mensaje = "", variante = "info", duracion = 4600) {
        if (!NODOS.contenedor) {
            NODOS.contenedor = $("#toasts");
        }
        if (!NODOS.contenedor) {
            return;
        }

        const varianteSegura = ICONOS_VARIANTE[variante] ? variante : "info";
        const elemento = document.createElement("article");
        elemento.className = `toast toast--${varianteSegura}`;
        elemento.setAttribute("role", "status");
        elemento.style.setProperty("--duracion-toast", `${duracion}ms`);
        elemento.innerHTML = `
            <span class="toast__icono">${icono(ICONOS_VARIANTE[varianteSegura])}</span>
            <div class="toast__contenido">
                <p class="toast__titulo">${escapar(titulo)}</p>
                ${mensaje ? `<p class="toast__mensaje">${escapar(mensaje)}</p>` : ""}
            </div>
            <button class="toast__cerrar" type="button" aria-label="Cerrar aviso">
                ${icono("x")}
            </button>
            <span class="toast__progreso" aria-hidden="true"></span>`;

        const cerrar = () => retirarToast(elemento);
        elemento.querySelector(".toast__cerrar").addEventListener("click", cerrar);
        NODOS.contenedor.prepend(elemento);

        while (NODOS.contenedor.children.length > ESTADO.topeToasts) {
            retirarToast(NODOS.contenedor.lastElementChild, true);
        }
        const temporizador = global.setTimeout(cerrar, duracion);
        ESTADO.temporizadores.set(elemento, temporizador);
    }

    /**
     * Retira un toast con animación de salida.
     * @param {HTMLElement} elemento Toast a retirar.
     * @param {boolean} [inmediato] Si se elimina sin esperar la animación.
     */
    function retirarToast(elemento, inmediato = false) {
        if (!elemento || !elemento.parentElement) {
            return;
        }
        global.clearTimeout(ESTADO.temporizadores.get(elemento));
        if (inmediato) {
            elemento.remove();
            return;
        }
        elemento.classList.add("saliendo");
        global.setTimeout(() => elemento.remove(), 340);
    }

    /* ------------------------------------------------------------------
       Campana y menú desplegable
       ------------------------------------------------------------------ */
    /** Abre o cierra el menú de avisos. */
    function alternarMenu() {
        if (!NODOS.menu) {
            return;
        }
        ESTADO.menuAbierto = !ESTADO.menuAbierto;
        NODOS.menu.classList.toggle("oculto", !ESTADO.menuAbierto);
        NODOS.campana.classList.toggle("activo", ESTADO.menuAbierto);
        if (ESTADO.menuAbierto) {
            cargar();
        }
    }

    /** Cierra el menú si está abierto. */
    function cerrarMenu() {
        if (!ESTADO.menuAbierto) {
            return;
        }
        ESTADO.menuAbierto = false;
        NODOS.menu.classList.add("oculto");
        NODOS.campana.classList.remove("activo");
    }

    /**
     * Marca un aviso como visto y refresca la campana.
     * @param {number} identificador Identificador del aviso.
     */
    async function marcarVista(identificador) {
        try {
            await global.PuenteAgenda.llamar("marcar_notificacion_vista", identificador);
        } catch (error) {
            console.warn("[avisos] No se pudo marcar como visto", error);
        }
        ESTADO.avisos = ESTADO.avisos.map((aviso) =>
            aviso.id === identificador ? { ...aviso, vista: true } : aviso
        );
        renderizar();
    }

    /**
     * Pospone un aviso quince minutos.
     * @param {number} identificador Identificador del aviso.
     * @param {Event} [evento] Evento del clic para evitar la propagación.
     */
    async function posponer(identificador, evento) {
        if (evento) {
            evento.stopPropagation();
        }
        try {
            await global.PuenteAgenda.llamar("posponer_notificacion", identificador, 15);
            toast("Aviso pospuesto", "Volverá a aparecer dentro de 15 minutos.", "info", 3200);
        } catch (error) {
            toast("No se pudo posponer", String(error.message || error), "error");
        }
        await cargar();
    }

    /**
     * Construye el HTML de un aviso del menú.
     * @param {object} aviso Notificación serializada.
     * @returns {string} HTML del elemento.
     */
    function plantillaAviso(aviso) {
        const programada = aviso.programada_para || aviso.creada_en || "";
        const esHoy = programada.slice(0, 10) === hoyIso();
        const momento = esHoy ? horaCorta(programada) : fechaCorta(programada);
        const noVista = !aviso.vista;
        return `
            <div class="notificacion-item ${noVista ? "no-vista" : ""}"
                 data-id="${Number(aviso.id)}" role="button" tabindex="0">
                <span class="notificacion-item__icono">${icono(noVista ? "campana" : "check")}</span>
                <div style="min-width:0;flex:1">
                    <p class="notificacion-item__titulo">${escapar(aviso.titulo || "Recordatorio")}</p>
                    <p class="notificacion-item__mensaje">${escapar(aviso.mensaje || "")}</p>
                    <p class="notificacion-item__hora">${escapar(momento)}${noVista ? " · sin leer" : ""}</p>
                    <div class="notificacion-item__acciones">
                        ${noVista ? '<button class="boton boton--fantasma boton--pequeno" data-accion="vista" type="button">Marcar visto</button>' : ""}
                        <button class="boton boton--fantasma boton--pequeno" data-accion="posponer" type="button">Posponer 15 min</button>
                    </div>
                </div>
            </div>`;
    }

    /** Vuelve a pintar la lista de avisos y la insignia. */
    function renderizar() {
        if (!NODOS.lista) {
            return;
        }
        if (!ESTADO.avisos.length) {
            NODOS.lista.innerHTML = U.vacio(
                "campana",
                "Todo al día",
                "No hay recordatorios pendientes. Te avisaremos antes de cada entrega."
            );
        } else {
            NODOS.lista.innerHTML = ESTADO.avisos.map(plantillaAviso).join("");
            NODOS.lista.querySelectorAll(".notificacion-item").forEach((fila) => {
                const identificador = Number(fila.dataset.id);
                fila.addEventListener("click", () => marcarVista(identificador));
                const botonVista = fila.querySelector('[data-accion="vista"]');
                if (botonVista) {
                    botonVista.addEventListener("click", (evento) => {
                        evento.stopPropagation();
                        marcarVista(identificador);
                    });
                }
                fila.querySelector('[data-accion="posponer"]').addEventListener("click", (evento) =>
                    posponer(identificador, evento)
                );
            });
        }
        actualizarInsignia();
    }

    /** Actualiza el contador rojo de la campana. */
    function actualizarInsignia() {
        if (!NODOS.insignia) {
            return;
        }
        const total = ESTADO.avisos.filter((aviso) => !aviso.vista).length;
        NODOS.insignia.textContent = total > 99 ? "99+" : String(total);
        NODOS.insignia.classList.toggle("activa", total > 0);
        NODOS.campana.setAttribute(
            "aria-label",
            total ? `Avisos: ${total} sin leer` : "Avisos: todo al día"
        );
    }

    /**
     * Incorpora un aviso recibido en vivo (señal `notificacionRecibida`).
     * @param {object|string} aviso Notificación o JSON serializado.
     */
    function agregar(aviso) {
        let datos = aviso;
        if (typeof datos === "string") {
            try {
                datos = JSON.parse(datos);
            } catch (error) {
                return;
            }
        }
        if (!datos || typeof datos !== "object") {
            return;
        }
        const existente = ESTADO.avisos.some(
            (elemento) => elemento.id && datos.id && elemento.id === datos.id
        );
        if (!existente) {
            ESTADO.avisos.unshift({ vista: false, ...datos });
            ESTADO.avisos = ESTADO.avisos.slice(0, 30);
        }
        renderizar();
        toast(datos.titulo || "Nuevo aviso", datos.mensaje || "", "info", 6000);
    }

    /** Carga los avisos desde Python. */
    async function cargar() {
        try {
            const datos = await global.PuenteAgenda.obtener("listar_notificaciones", "");
            ESTADO.avisos = Array.isArray(datos) ? datos : [];
        } catch (error) {
            console.warn("[avisos] No se pudieron cargar", error);
        }
        renderizar();
    }

    /** Marca todos los avisos como vistos. */
    async function marcarTodas() {
        try {
            await global.PuenteAgenda.llamar("marcar_todas_notificaciones_vistas");
            ESTADO.avisos = ESTADO.avisos.map((aviso) => ({ ...aviso, vista: true }));
            renderizar();
            toast("Bandeja despejada", "Todos los avisos se marcaron como vistos.", "exito", 3200);
        } catch (error) {
            toast("No se pudo actualizar", String(error.message || error), "error");
        }
    }

    /* ------------------------------------------------------------------
       Arranque
       ------------------------------------------------------------------ */
    /** Conecta los nodos del documento y las señales del puente. */
    function iniciar() {
        if (ESTADO.iniciado) {
            return;
        }
        NODOS.contenedor = $("#toasts");
        NODOS.campana = $("#boton-campana");
        NODOS.insignia = $("#insignia-campana");
        NODOS.menu = $("#menu-notificaciones");
        NODOS.lista = $("#lista-notificaciones");
        NODOS.botonMarcarTodas = $("#marcar-todas-notificaciones");
        NODOS.botonVerTodas = $("#ver-todas-notificaciones");

        if (!NODOS.campana || !NODOS.menu) {
            return;
        }

        NODOS.campana.addEventListener("click", (evento) => {
            evento.stopPropagation();
            alternarMenu();
        });
        NODOS.menu.addEventListener("click", (evento) => evento.stopPropagation());
        NODOS.botonMarcarTodas?.addEventListener("click", marcarTodas);
        NODOS.botonVerTodas?.addEventListener("click", () => {
            cerrarMenu();
            global.AgendaApp?.navegarA("inicio", { ancla: "avisos" });
        });
        document.addEventListener("click", cerrarMenu);

        document.addEventListener("agenda:notificacionRecibida", (evento) =>
            agregar(evento.detail)
        );
        document.addEventListener("agenda:datosActualizados", (evento) => {
            if (["panel", "todo", "evento"].includes(evento.detail)) {
                cargar();
            }
        });

        ESTADO.iniciado = true;
        cargar();
    }

    global.NotificacionesInternas = {
        iniciar,
        cargar,
        renderizar,
        toast,
        agregar,
        alternarMenu,
        cerrarMenu,
        marcarTodas,
        estado: ESTADO
    };
})(window);
