/**
 * ============================================================================
 *  GADGET «PLAN DE HOY» · lógica de interfaz
 * ----------------------------------------------------------------------------
 *  Se ejecuta dentro de la ventana transparente de PySide6. Se comunica con
 *  Python mediante `PuenteAgenda`, renderiza el día, la cuenta atrás del
 *  próximo examen o entrega, las tareas y los controles de opacidad, bloqueo y
 *  vista compacta.
 *
 *  No se usa ningún atajo de teclado: todo se maneja con el ratón.
 * ============================================================================
 */
(function () {
    "use strict";

    const CIRCUNFERENCIA_ANILLO = 2 * Math.PI * 23;
    const COLORES_PRIORIDAD = {
        critica: "#ff5f7a",
        alta: "#ffc857",
        media: "#4aa8ff",
        baja: "#2dd4a8"
    };

    /** Estado en memoria del gadget. */
    const estado = {
        panel: null,
        configuracion: {},
        arrastrando: false,
        origenX: 0,
        origenY: 0,
        temporizadorOpacidad: null,
        temporizadorCuentaAtras: null
    };

    const nodos = {};

    /** Atajo seguro para consultar el DOM. */
    const $ = (identificador) => document.getElementById(identificador);

    /**
     * Escapa texto para insertarlo como HTML sin ejecutar etiquetas.
     * @param {string} texto Texto potencialmente inseguro.
     * @returns {string} Texto escapado.
     */
    function escapar(texto) {
        return String(texto ?? "").replace(/[&<>"']/g, (caracter) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        }[caracter]));
    }

    /**
     * Formatea una hora ISO (HH:MM) en formato local legible.
     * @param {string} iso Fecha y hora ISO.
     * @returns {string} Hora corta o cadena vacía.
     */
    function horaCorta(iso) {
        if (!iso || iso.length < 16) {
            return "";
        }
        return iso.slice(11, 16);
    }

    /**
     * Calcula los componentes de la cuenta atrás hasta un hito.
     * @param {string} iso Fecha ISO del examen o entrega.
     * @returns {{dias: number, horas: number, minutos: number, vencido: boolean, horasTotales: number}}
     */
    function calcularCuentaAtras(iso) {
        if (!iso) {
            return { dias: 0, horas: 0, minutos: 0, vencido: true, horasTotales: 0 };
        }
        const destino = new Date(iso);
        const diferencia = destino.getTime() - Date.now();
        const vencido = diferencia <= 0;
        const totalMinutos = Math.max(0, Math.floor(Math.abs(diferencia) / 60000));
        return {
            dias: Math.floor(totalMinutos / 1440),
            horas: Math.floor((totalMinutos % 1440) / 60),
            minutos: totalMinutos % 60,
            vencido,
            horasTotales: totalMinutos / 60
        };
    }

    /** Rellena con dos dígitos. */
    const dosDigitos = (numero) => String(numero).padStart(2, "0");

    // ------------------------------------------------------------------
    // Renderizado
    // ------------------------------------------------------------------
    /**
     * Aplica el estado visual configurado (tema, opacidad, bloqueo, compacto).
     * @param {object} configuracion Configuración recibida de Python.
     */
    function aplicarConfiguracion(configuracion) {
        if (!configuracion) {
            return;
        }
        estado.configuracion = { ...estado.configuracion, ...configuracion };

        if (configuracion.tema) {
            PuenteAgenda.aplicarTema(configuracion.tema);
        }

        if (typeof configuracion.opacidad === "number") {
            const porcentaje = Math.round(configuracion.opacidad * 100);
            document.documentElement.style.setProperty("--opacidad-gadget", configuracion.opacidad.toFixed(2));
            nodos.deslizador.value = String(porcentaje);
            nodos.valorOpacidad.textContent = `${porcentaje}%`;
            nodos.deslizador.style.setProperty("--porcentaje-opacidad", `${porcentaje}%`);
        }

        const bloqueado = Boolean(configuracion.bloqueado);
        nodos.gadget.classList.toggle("bloqueado", bloqueado);
        nodos.botonBloquear.classList.toggle("activo", bloqueado);
        nodos.botonBloquear.dataset.tooltip = bloqueado ? "Desbloquear posición" : "Bloquear posición";
        nodos.botonBloquear.innerHTML = bloqueado ? ICONO_CANDADO_CERRADO : ICONO_CANDADO_ABIERTO;

        const compacto = Boolean(configuracion.compacto);
        nodos.gadget.classList.toggle("compacto", compacto);
        nodos.botonCompacto.classList.toggle("activo", compacto);
        nodos.botonCompacto.dataset.tooltip = compacto ? "Vista detallada" : "Vista compacta";
    }

    /**
     * Pinta todos los datos del panel devueltos por Python.
     * @param {object} panel Datos del panel de inicio.
     */
    function renderizarPanel(panel) {
        if (!panel) {
            return;
        }
        estado.panel = panel;
        const nombre = panel.nombre_estudiante || "Estudiante";
        nodos.fecha.textContent = (panel.fecha || "").toUpperCase();
        nodos.saludo.textContent = `${panel.saludo || "Hola"}, ${nombre.split(" ")[0]}`;

        // ---- Progreso del día ----------------------------------------
        const progreso = Math.min(100, Math.max(0, Number(panel.progreso_dia) || 0));
        nodos.anilloTexto.textContent = `${progreso}%`;
        nodos.anilloValor.style.strokeDashoffset = String(
            CIRCUNFERENCIA_ANILLO * (1 - progreso / 100)
        );

        const eventosHoy = panel.agenda_hoy || [];
        const completadosHoy = eventosHoy.filter((evento) => evento.completado).length;
        nodos.progresoValor.textContent = `${completadosHoy} de ${eventosHoy.length} completado`;
        const proxima = eventosHoy.find((evento) => !evento.completado);
        nodos.progresoDetalle.textContent = proxima
            ? `Siguiente: ${proxima.titulo}${proxima.fecha_inicio ? " · " + horaCorta(proxima.fecha_inicio) : ""}`
            : "Todo al día. ¡Buen trabajo!";

        renderizarCuentaAtras(panel.proximo_hito);
        renderizarTareas(panel);
    }

    /**
     * Actualiza la tarjeta de cuenta atrás.
     * @param {object|null} hito Próximo examen o entrega.
     */
    function renderizarCuentaAtras(hito) {
        if (!hito) {
            nodos.hitoTitulo.textContent = "Sin exámenes ni entregas cercanas";
            nodos.hitoDias.textContent = "00";
            nodos.hitoHoras.textContent = "00";
            nodos.hitoMinutos.textContent = "00";
            nodos.hitoProgreso.style.width = "0%";
            return;
        }
        nodos.hitoTitulo.textContent = hito.titulo;
        actualizarTiemposCuentaAtras(hito);
    }

    /**
     * Recalcula los dígitos de días/horas/minutos sin volver a pedir datos.
     * @param {object} hito Hito con `fecha_inicio`.
     */
    function actualizarTiemposCuentaAtras(hito) {
        const cuenta = calcularCuentaAtras(hito.fecha_inicio);
        nodos.hitoDias.textContent = dosDigitos(cuenta.dias);
        nodos.hitoHoras.textContent = dosDigitos(cuenta.horas);
        nodos.hitoMinutos.textContent = dosDigitos(cuenta.minutos);
        // Horizonte visual de 14 días para la barra de proximidad.
        const avance = Math.min(100, Math.max(0, (1 - cuenta.horasTotales / (14 * 24)) * 100));
        nodos.hitoProgreso.style.width = `${avance.toFixed(1)}%`;
    }

    /**
     * Construye la lista interactiva de tareas del día.
     * @param {object} panel Datos del panel.
     */
    function renderizarTareas(panel) {
        const tareas = (panel.agenda_hoy || []).filter(
            (evento) => evento.tipo === "tarea" || evento.tipo === "entrega"
        );
        const pendientes = tareas.filter((tarea) => !tarea.completado);
        nodos.contadorTareas.textContent = `${pendientes.length} pendiente${pendientes.length === 1 ? "" : "s"}`;

        if (tareas.length === 0) {
            nodos.listaTareas.innerHTML = `
                <li class="gadget__vacio">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M20 6 9 17l-5-5"></path>
                    </svg>
                    <span>No hay tareas para hoy.</span>
                    <span>Disfruta del respiro.</span>
                </li>`;
            return;
        }

        nodos.listaTareas.innerHTML = tareas
            .map((tarea) => {
                const color = tarea.asignatura_color || COLORES_PRIORIDAD[tarea.prioridad] || "#8a8fa8";
                const meta = [tarea.asignatura_nombre, horaCorta(tarea.fecha_inicio)]
                    .filter(Boolean)
                    .join(" · ");
                return `
                    <li class="gadget__tarea ${tarea.completado ? "completada" : ""}" data-id="${tarea.id}">
                        <button class="marca-verificacion ${tarea.completado ? "activa" : ""}"
                                type="button" aria-label="Marcar como completada">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M20 6 9 17l-5-5"></path>
                            </svg>
                        </button>
                        <div class="gadget__tarea-texto">
                            <span class="gadget__tarea-titulo">${escapar(tarea.titulo)}</span>
                            <span class="gadget__tarea-meta">
                                <span class="gadget__tarea-color" style="background:${escapar(color)}"></span>
                                ${escapar(meta || "Sin asignatura")}
                            </span>
                        </div>
                    </li>`;
            })
            .join("");
    }

    // ------------------------------------------------------------------
    // Acciones
    // ------------------------------------------------------------------
    /**
     * Persiste un cambio de configuración del gadget.
     * @param {object} cambios Cambios a guardar.
     */
    async function guardarConfiguracion(cambios) {
        try {
            const resultado = await PuenteAgenda.obtener(
                "guardar_estado_gadget",
                JSON.stringify(cambios)
            );
            if (resultado) {
                aplicarConfiguracion(resultado);
            }
        } catch (error) {
            console.warn("[gadget] No se pudo guardar la configuración", error);
        }
    }

    /** Recarga los datos desde Python. */
    async function recargar() {
        try {
            const resultado = await PuenteAgenda.obtener("obtener_estado_gadget");
            if (!resultado) {
                return;
            }
            aplicarConfiguracion(resultado);
            renderizarPanel(resultado.panel);
        } catch (error) {
            console.warn("[gadget] Sin conexión con el backend", error);
            nodos.listaTareas.innerHTML = `
                <li class="gadget__vacio"><span>No se pudo conectar con la agenda.</span></li>`;
        }
    }

    /**
     * Completa una tarea desde el gadget con actualización optimista.
     * @param {number} id Identificador del evento.
     * @param {HTMLElement} fila Elemento de la lista.
     */
    async function completarTarea(id, fila) {
        if (!id || fila.dataset.procesando === "1") {
            return;
        }
        fila.dataset.procesando = "1";
        fila.classList.add("completada");
        const boton = fila.querySelector(".marca-verificacion");
        if (boton) {
            boton.classList.add("activa");
        }
        try {
            const resultado = await PuenteAgenda.llamar("completar_evento", Number(id), true);
            if (!resultado.ok) {
                throw new Error(resultado.error);
            }
            await recargar();
        } catch (error) {
            fila.classList.remove("completada");
            if (boton) {
                boton.classList.remove("activa");
            }
            fila.animate(
                [
                    { transform: "translateX(0)" },
                    { transform: "translateX(-4px)" },
                    { transform: "translateX(4px)" },
                    { transform: "translateX(0)" }
                ],
                { duration: 320, easing: "ease-in-out" }
            );
        } finally {
            delete fila.dataset.procesando;
        }
    }

    // ------------------------------------------------------------------
    // Arrastre de la ventana nativa
    // ------------------------------------------------------------------
    function iniciarArrastre(evento) {
        if (evento.button !== 0 || estado.configuracion.bloqueado) {
            return;
        }
        if (evento.target.closest("button, input, a")) {
            return;
        }
        evento.preventDefault();
        estado.arrastrando = true;
        estado.origenX = evento.screenX;
        estado.origenY = evento.screenY;
        document.body.style.cursor = "grabbing";
        PuenteAgenda.llamar("iniciar_arrastre_gadget").catch(() => {});
    }

    function moverArrastre(evento) {
        if (!estado.arrastrando) {
            return;
        }
        const deltaX = evento.screenX - estado.origenX;
        const deltaY = evento.screenY - estado.origenY;
        PuenteAgenda.llamar("mover_gadget", Math.round(deltaX), Math.round(deltaY)).catch(() => {});
    }

    function terminarArrastre() {
        if (!estado.arrastrando) {
            return;
        }
        estado.arrastrando = false;
        document.body.style.cursor = "";
        PuenteAgenda.llamar("soltar_gadget").catch(() => {});
    }

    // ------------------------------------------------------------------
    // Iconos de los controles
    // ------------------------------------------------------------------
    const ICONO_CANDADO_ABIERTO = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="11" width="14" height="10" rx="2"></rect>
            <path d="M8 11V7a4 4 0 0 1 7.5-2"></path>
        </svg>`;

    const ICONO_CANDADO_CERRADO = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="11" width="14" height="10" rx="2"></rect>
            <path d="M8 11V7a4 4 0 0 1 8 0v4"></path>
        </svg>`;

    // ------------------------------------------------------------------
    // Arranque
    // ------------------------------------------------------------------
    function cachearNodos() {
        nodos.gadget = $("gadget");
        nodos.fecha = $("gadget-fecha");
        nodos.saludo = $("gadget-saludo");
        nodos.anilloValor = $("anillo-valor");
        nodos.anilloTexto = $("anillo-texto");
        nodos.progresoValor = $("progreso-valor");
        nodos.progresoDetalle = $("progreso-detalle");
        nodos.hitoTitulo = $("hito-titulo");
        nodos.hitoDias = $("hito-dias");
        nodos.hitoHoras = $("hito-horas");
        nodos.hitoMinutos = $("hito-minutos");
        nodos.hitoProgreso = $("hito-progreso");
        nodos.listaTareas = $("lista-tareas");
        nodos.contadorTareas = $("contador-tareas");
        nodos.deslizador = $("control-opacidad");
        nodos.valorOpacidad = $("valor-opacidad");
        nodos.botonBloquear = $("btn-bloquear");
        nodos.botonCompacto = $("btn-compacto");
        nodos.anilloValor.style.strokeDasharray = String(CIRCUNFERENCIA_ANILLO);
    }

    function registrarEventos() {
        // El control deslizante actualiza la variable CSS al instante y guarda
        // con un pequeño retardo para no saturar el puente.
        nodos.deslizador.addEventListener("input", (evento) => {
            const porcentaje = Number(evento.target.value);
            const opacidad = porcentaje / 100;
            document.documentElement.style.setProperty("--opacidad-gadget", opacidad.toFixed(2));
            nodos.valorOpacidad.textContent = `${porcentaje}%`;
            nodos.deslizador.style.setProperty("--porcentaje-opacidad", `${porcentaje}%`);
            clearTimeout(estado.temporizadorOpacidad);
            estado.temporizadorOpacidad = setTimeout(() => {
                guardarConfiguracion({ opacidad });
            }, 160);
        });

        nodos.botonBloquear.addEventListener("click", () => {
            guardarConfiguracion({ bloqueado: !estado.configuracion.bloqueado });
        });

        nodos.botonCompacto.addEventListener("click", () => {
            guardarConfiguracion({ compacto: !estado.configuracion.compacto });
        });

        $("btn-abrir").addEventListener("click", () => {
            PuenteAgenda.llamar("abrir_agenda").catch(() => {});
        });

        $("btn-ocultar").addEventListener("click", () => {
            guardarConfiguracion({ visible: false });
        });

        // Completar tareas con delegación de eventos.
        nodos.listaTareas.addEventListener("click", (evento) => {
            const boton = evento.target.closest(".marca-verificacion");
            if (!boton) {
                return;
            }
            const fila = boton.closest(".gadget__tarea");
            completarTarea(Number(fila.dataset.id), fila);
        });

        // Arrastre de la ventana nativa mediante la cabecera.
        $("zona-arrastre").addEventListener("mousedown", iniciarArrastre);
        window.addEventListener("mousemove", moverArrastre);
        window.addEventListener("mouseup", terminarArrastre);
        window.addEventListener("blur", terminarArrastre);

        // Sincronización en tiempo real con la ventana principal.
        PuenteAgenda.al("datosActualizados", () => recargar());
        PuenteAgenda.al("gadgetConfigurado", (detalle) => {
            try {
                aplicarConfiguracion(JSON.parse(detalle));
            } catch (error) {
                console.warn("[gadget] Configuración inválida", error);
            }
        });
        PuenteAgenda.al("temaCambiado", (tema) => PuenteAgenda.aplicarTema(tema));
    }

    async function iniciar() {
        cachearNodos();
        registrarEventos();

        // Fecha provisional mientras llega la respuesta de Python.
        const ahora = new Date();
        nodos.fecha.textContent = ahora
            .toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" })
            .toUpperCase();
        nodos.saludo.textContent = ahora.getHours() < 13 ? "Buenos días" : "Buenas tardes";

        await PuenteAgenda.iniciar();
        await recargar();

        // La cuenta atrás se refresca localmente cada 30 segundos, sin IPC.
        estado.temporizadorCuentaAtras = setInterval(() => {
            if (estado.panel && estado.panel.proximo_hito) {
                actualizarTiemposCuentaAtras(estado.panel.proximo_hito);
            }
        }, 30000);
    }

    document.addEventListener("DOMContentLoaded", iniciar);
})();
