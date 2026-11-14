/**
 * ============================================================================
 *  UTILIDADES COMPARTIDAS · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Funciones puras de apoyo para todas las vistas: consultas seguras al DOM,
 *  escape de texto, formato de fechas en español, iconografía SVG en línea y
 *  pequeños ayudantes de renderizado. No depende de Qt: también funciona si
 *  el HTML se abre en un navegador para revisar el diseño.
 * ============================================================================
 */
(function (global) {
    "use strict";

    /* ------------------------------------------------------------------
       Iconografía (trazo de 24 px, estilo Lucide, color heredado)
       ------------------------------------------------------------------ */
    const TRAZOS = {
        inicio: '<path d="m3 10.5 9-7 9 7V20a1.5 1.5 0 0 1-1.5 1.5h-4.5v-6h-6v6H4.5A1.5 1.5 0 0 1 3 20Z"/>',
        calendario:
            '<rect x="3" y="4.5" width="18" height="16" rx="3"/><path d="M8 2.5v4M16 2.5v4M3 9.5h18"/><path d="M8 13.5h.01M12 13.5h.01M16 13.5h.01M8 17.5h.01M12 17.5h.01"/>',
        kanban:
            '<rect x="3" y="3.5" width="5.4" height="17" rx="1.8"/><rect x="10.3" y="3.5" width="5.4" height="11" rx="1.8"/><rect x="17.6" y="3.5" width="3.4" height="14" rx="1.6"/>',
        asignaturas:
            '<path d="M12 6.6C10.5 5.1 8.6 4.4 6 4.4c-1.2 0-2.3.2-3 .5v14c.7-.3 1.8-.5 3-.5 2.6 0 4.5.7 6 2.2 1.5-1.5 3.4-2.2 6-2.2 1.2 0 2.3.2 3 .5v-14c-.7-.3-1.8-.5-3-.5-2.6 0-4.5.7-6 2.2Z"/><path d="M12 6.6v14.4"/>',
        estudio:
            '<circle cx="12" cy="13.2" r="7.8"/><path d="M12 9.4v4.2l2.6 1.7M9 2.2h6M12 2.2v2.6"/>',
        analiticas:
            '<path d="M3.5 20.5V11M9.5 20.5V4M15.5 20.5v-6.5M21.5 20.5H2.5"/><path d="m4 7 5-3 6 4 5-5"/>',
        ajustes:
            '<path d="M4 7h9M18 7h2M4 17h2M11 17h9"/><circle cx="15.5" cy="7" r="2.3"/><circle cx="8.5" cy="17" r="2.3"/>',
        campana:
            '<path d="M18 9.2a6 6 0 1 0-12 0c0 4.8-2.2 6.1-2.2 6.1h16.4S18 14 18 9.2Z"/><path d="M10.2 19.6a2.1 2.1 0 0 0 3.6 0"/>',
        mas: '<path d="M12 5v14M5 12h14"/>',
        menos: '<path d="M5 12h14"/>',
        x: '<path d="M18 6 6 18M6 6l12 12"/>',
        check: '<path d="m4.8 12.6 4.8 4.8L19.4 7"/>',
        chevronIzquierda: '<path d="m14.6 5.8-6 6.2 6 6.2"/>',
        chevronDerecha: '<path d="m9.4 5.8 6 6.2-6 6.2"/>',
        chevronAbajo: '<path d="m5.8 9.4 6.2 6 6.2-6"/>',
        reloj: '<circle cx="12" cy="12" r="8.6"/><path d="M12 7.4V12l3 2.1"/>',
        rayo: '<path d="M13.2 2.4 4.6 13.4H11l-.9 8.2 8.9-11.2h-6.1Z"/>',
        fuego:
            '<path d="M12 22c4.2 0 7-2.7 7-6.6 0-2.8-1.5-5-3.4-7.1-.8-.9-1.7-2-2.2-3.3-.2-.7-1.1-.8-1.5-.2-1.3 2.1-1 4.1-.1 5.9-1-.4-1.8-1.2-2.3-2.3-.3-.6-1.1-.7-1.4-.1C7.2 9.8 5 12.3 5 15.4 5 19.3 7.8 22 12 22Z"/>',
        objetivo:
            '<circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="4.6"/><circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none"/>',
        libro:
            '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15.5H6.5A2.5 2.5 0 0 0 4 21Z"/><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20"/>',
        carpeta:
            '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2.4h7A2.5 2.5 0 0 1 21 9.9v7.6a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5Z"/>',
        editar:
            '<path d="M12.5 5.5 18.5 11.5M4 20l4.4-1 10.9-10.9a2.6 2.6 0 0 0-3.7-3.7L4.7 15.3Z"/>',
        basura:
            '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l.8 12.1A2 2 0 0 0 9.3 21h5.4a2 2 0 0 0 2-1.9L17.5 7"/><path d="M10 11v6M14 11v6"/>',
        enlace:
            '<path d="M10 13.5a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7L11.5 6.3"/><path d="M14 10.5a4 4 0 0 0-5.7 0L5.5 13.3a4 4 0 0 0 5.7 5.7l1.3-1.3"/>',
        ubicacion:
            '<path d="M12 21s7-5.7 7-11a7 7 0 1 0-14 0c0 5.3 7 11 7 11Z"/><circle cx="12" cy="10" r="2.6"/>',
        sincronizar:
            '<path d="M20 11a8 8 0 0 0-14.6-4.3M4 13a8 8 0 0 0 14.6 4.3"/><path d="M20 4v5h-5M4 20v-5h5"/>',
        descargar: '<path d="M12 3v12M7.5 10.5 12 15l4.5-4.5M4 20h16"/>',
        subir: '<path d="M12 16V4M7.5 8.5 12 4l4.5 4.5M4 20h16"/>',
        respaldo:
            '<ellipse cx="12" cy="5.6" rx="7.6" ry="2.8"/><path d="M4.4 5.6v6.2c0 1.5 3.4 2.8 7.6 2.8s7.6-1.3 7.6-2.8V5.6"/><path d="M4.4 11.8v6.2c0 1.5 3.4 2.8 7.6 2.8s7.6-1.3 7.6-2.8v-6.2"/>',
        salir:
            '<path d="M14 4h4.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H14"/><path d="M10 8.5 13.5 12 10 15.5M3.5 12h10"/>',
        buscar: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
        filtro: '<path d="M4 5h16l-6.2 7.4v6.1L10.2 21v-8.6Z"/>',
        puntos:
            '<circle cx="6" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
        sol:
            '<circle cx="12" cy="12" r="4.1"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"/>',
        luna: '<path d="M20.4 14.2A8.6 8.6 0 0 1 9.8 3.6a8.6 8.6 0 1 0 10.6 10.6Z"/>',
        alerta:
            '<path d="M10.3 4.2 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4.4M12 17h.01"/>',
        informacion:
            '<circle cx="12" cy="12" r="8.8"/><path d="M12 11v5M12 7.6h.01"/>',
        exito: '<circle cx="12" cy="12" r="8.8"/><path d="m8 12.2 2.6 2.6L16.2 9"/>',
        pausa: '<path d="M8.5 5v14M15.5 5v14"/>',
        reproducir: '<path d="M7 4.8 19 12 7 19.2Z"/>',
        detener: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
        reiniciar:
            '<path d="M4 4v6h6"/><path d="M4.6 10A8 8 0 1 1 12 20a8 8 0 0 1-6.9-4"/>',
        flechaArriba: '<path d="M12 19V5M6.5 10.5 12 5l5.5 5.5"/>',
        flechaDerecha: '<path d="M5 12h14M13 6l6 6-6 6"/>',
        grafico:
            '<path d="M3.5 20.5h17M6 20.5V9.5M11 20.5V4.5M16 20.5v-7M21 20.5V12"/>',
        trofeo:
            '<path d="M8 4h8v5.5a4 4 0 0 1-8 0Z"/><path d="M8 5.5H5.5A1.5 1.5 0 0 0 4 7c0 2.3 1.8 4.2 4.1 4.4M16 5.5h2.5A1.5 1.5 0 0 1 20 7c0 2.3-1.8 4.2-4.1 4.4M12 13.5V18M8.5 21h7M9.5 18h5"/>',
        capas:
            '<path d="m12 3 9 4.8-9 4.8-9-4.8Z"/><path d="m3 12 9 4.8 9-4.8M3 16.4l9 4.8 9-4.8"/>',
        nota: '<path d="M5 3.5h14v17H5Z"/><path d="M8.5 8h7M8.5 12h7M8.5 16h4"/>',
        etiqueta:
            '<path d="M20.5 13.2 13.3 20.4a2 2 0 0 1-2.8 0L3.5 13.4V3.5h9.9l7.1 7.1a1.8 1.8 0 0 1 0 2.6Z"/><circle cx="8.2" cy="8.2" r="1.3"/>',
        usuarios:
            '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 20c0-3.1 2.5-5.3 5.5-5.3s5.5 2.2 5.5 5.3"/><path d="M16 5.6a3.2 3.2 0 0 1 0 5.9M17.5 14.9c2 .4 3.5 2.3 3.5 5.1"/>',
        punto: '<circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/>'
    };

    /**
     * Devuelve el marcado SVG de un icono.
     * @param {string} nombre Clave del catálogo.
     * @param {string} [clase] Clases CSS adicionales.
     * @returns {string} SVG en línea listo para insertar.
     */
    function icono(nombre, clase = "") {
        const trazo = TRAZOS[nombre] || TRAZOS.punto;
        const clases = ["icono", clase].filter(Boolean).join(" ");
        return (
            `<svg class="${clases}" viewBox="0 0 24 24" fill="none" ` +
            `stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ` +
            `stroke-linejoin="round" aria-hidden="true">${trazo}</svg>`
        );
    }

    /* ------------------------------------------------------------------
       DOM
       ------------------------------------------------------------------ */
    /** @param {string} selector Selector CSS. */
    const $ = (selector, raiz = document) => raiz.querySelector(selector);
    /** @param {string} selector Selector CSS. */
    const $$ = (selector, raiz = document) => Array.from(raiz.querySelectorAll(selector));

    /**
     * Crea un elemento con atributos e hijos.
     * @param {string} etiqueta Nombre de la etiqueta HTML.
     * @param {object} [atributos] Atributos, `class`, `dataset` y manejadores `on`.
     * @param {(string|Node|Array)} [hijos] Contenido interno.
     * @returns {HTMLElement} Elemento creado.
     */
    function crear(etiqueta, atributos = {}, hijos = []) {
        const elemento = document.createElement(etiqueta);
        Object.entries(atributos).forEach(([clave, valor]) => {
            if (valor === undefined || valor === null || valor === false) {
                return;
            }
            if (clave === "class") {
                elemento.className = valor;
            } else if (clave === "dataset") {
                Object.assign(elemento.dataset, valor);
            } else if (clave === "html") {
                elemento.innerHTML = valor;
            } else if (clave === "texto") {
                elemento.textContent = valor;
            } else if (clave.startsWith("on") && typeof valor === "function") {
                elemento.addEventListener(clave.slice(2).toLowerCase(), valor);
            } else if (clave === "estilo" && typeof valor === "object") {
                Object.assign(elemento.style, valor);
            } else {
                elemento.setAttribute(clave, valor);
            }
        });
        (Array.isArray(hijos) ? hijos : [hijos]).forEach((hijo) => {
            if (hijo === null || hijo === undefined) {
                return;
            }
            elemento.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
        });
        return elemento;
    }

    /**
     * Escapa texto para insertarlo dentro de HTML.
     * @param {any} texto Valor a escapar.
     * @returns {string} Texto seguro.
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

    /* ------------------------------------------------------------------
       Fechas y números
       ------------------------------------------------------------------ */
    const dosDigitos = (numero) => String(numero).padStart(2, "0");

    /**
     * Convierte una fecha ISO local en objeto `Date` sin desfase de zona.
     * @param {string} iso Cadena `AAAA-MM-DDTHH:MM`.
     * @returns {Date|null} Fecha o `null` si no es válida.
     */
    function aFecha(iso) {
        if (!iso) {
            return null;
        }
        const fecha = new Date(iso);
        return Number.isNaN(fecha.getTime()) ? null : fecha;
    }

    /** @param {string} iso Fecha ISO. @returns {string} Hora `HH:MM`. */
    const horaCorta = (iso) => (iso && iso.length >= 16 ? iso.slice(11, 16) : "");

    /** @param {Date} fecha Fecha. @returns {string} Clave `AAAA-MM-DD` local. */
    function claveFecha(fecha = new Date()) {
        return `${fecha.getFullYear()}-${dosDigitos(fecha.getMonth() + 1)}-${dosDigitos(fecha.getDate())}`;
    }

    /** @returns {string} Fecha de hoy como `AAAA-MM-DD`. */
    const hoyIso = () => claveFecha(new Date());

    /**
     * Formatea una fecha ISO en español, por ejemplo «vie 14 nov».
     * @param {string} iso Fecha ISO.
     * @param {object} [opciones] Opciones de `Intl.DateTimeFormat`.
     * @returns {string} Fecha legible.
     */
    function fechaCorta(iso, opciones = { weekday: "short", day: "numeric", month: "short" }) {
        const fecha = aFecha(iso);
        if (!fecha) {
            return "";
        }
        return new Intl.DateTimeFormat("es-ES", opciones).format(fecha);
    }

    /**
     * Formatea una fecha ISO en formato largo, por ejemplo «viernes, 14 de noviembre».
     * @param {string} iso Fecha ISO.
     * @returns {string} Fecha legible.
     */
    function fechaLarga(iso) {
        return fechaCorta(iso, { weekday: "long", day: "numeric", month: "long" });
    }

    /**
     * Describe una fecha respecto a hoy: «Hoy», «Mañana» o fecha corta.
     * @param {string} iso Fecha ISO.
     * @returns {string} Etiqueta amable.
     */
    function fechaRelativa(iso) {
        if (!iso) {
            return "";
        }
        const clave = iso.slice(0, 10);
        const hoy = hoyIso();
        const manana = claveFecha(new Date(Date.now() + 86400000));
        const ayer = claveFecha(new Date(Date.now() - 86400000));
        if (clave === hoy) {
            return "Hoy";
        }
        if (clave === manana) {
            return "Mañana";
        }
        if (clave === ayer) {
            return "Ayer";
        }
        return fechaCorta(iso);
    }

    /**
     * Calcula los días que faltan hasta una fecha.
     * @param {string} iso Fecha objetivo.
     * @returns {number} Días completos (negativo si ya pasó).
     */
    function diasHasta(iso) {
        const fecha = aFecha(iso);
        if (!fecha) {
            return 0;
        }
        const inicioHoy = new Date();
        inicioHoy.setHours(0, 0, 0, 0);
        const inicioDestino = new Date(fecha);
        inicioDestino.setHours(0, 0, 0, 0);
        return Math.round((inicioDestino - inicioHoy) / 86400000);
    }

    /**
     * Convierte minutos en un texto «2 h 15 min».
     * @param {number} minutos Total de minutos.
     * @returns {string} Duración legible.
     */
    function duracion(minutos) {
        const total = Math.max(0, Math.round(Number(minutos) || 0));
        if (total < 60) {
            return `${total} min`;
        }
        const horas = Math.floor(total / 60);
        const resto = total % 60;
        return resto ? `${horas} h ${resto} min` : `${horas} h`;
    }

    /**
     * Devuelve el lunes de la semana de una fecha como objeto `Date`.
     * @param {Date} [fecha] Fecha de referencia.
     * @returns {Date} Lunes a las 00:00.
     */
    function lunesDe(fecha = new Date()) {
        const copia = new Date(fecha);
        const dia = (copia.getDay() + 6) % 7;
        copia.setDate(copia.getDate() - dia);
        copia.setHours(0, 0, 0, 0);
        return copia;
    }

    /** @param {number} valor Número. @param {number} minimo Límite. @param {number} maximo Límite. */
    const limitar = (valor, minimo, maximo) => Math.min(maximo, Math.max(minimo, valor));

    /* ------------------------------------------------------------------
       Dominio académico
       ------------------------------------------------------------------ */
    const ETIQUETAS_TIPO = {
        clase: "Clase",
        examen: "Examen",
        entrega: "Entrega",
        tarea: "Tarea",
        estudio: "Estudio"
    };

    const ETIQUETAS_PRIORIDAD = {
        baja: "Baja",
        media: "Media",
        alta: "Alta",
        critica: "Crítica"
    };

    const COLORES_PRIORIDAD = {
        baja: "var(--color-exito)",
        media: "var(--color-informacion)",
        alta: "var(--color-aviso)",
        critica: "var(--color-peligro)"
    };

    /**
     * Devuelve la etiqueta legible de un tipo de evento.
     * @param {string} tipo Identificador.
     * @returns {string} Etiqueta en español.
     */
    const etiquetaTipo = (tipo) => ETIQUETAS_TIPO[tipo] || "Evento";

    /**
     * Devuelve la etiqueta legible de una prioridad.
     * @param {string} prioridad Identificador.
     * @returns {string} Etiqueta en español.
     */
    const etiquetaPrioridad = (prioridad) =>
        ETIQUETAS_PRIORIDAD[prioridad] || "Media";

    /**
     * Construye el marcado de una insignia de prioridad.
     * @param {string} prioridad Identificador.
     * @param {string} [tipo] Tipo de evento alternativo.
     * @returns {string} HTML de la etiqueta.
     */
    function insigniaPrioridad(prioridad, tipo) {
        const clase = prioridad === "critica" ? "etiqueta--critica" : `etiqueta--${prioridad || "media"}`;
        const texto = tipo === "examen" ? "Examen" : etiquetaPrioridad(prioridad);
        return `<span class="etiqueta ${clase}">${escapar(texto)}</span>`;
    }

    /**
     * Calcula las iniciales de un nombre para el avatar.
     * @param {string} nombre Nombre completo.
     * @returns {string} Una o dos iniciales.
     */
    function iniciales(nombre) {
        const partes = String(nombre || "Estudiante").trim().split(/\s+/).filter(Boolean);
        if (!partes.length) {
            return "E";
        }
        if (partes.length === 1) {
            return partes[0].slice(0, 2).toUpperCase();
        }
        return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
    }

    /**
     * Genera un color estable a partir de un texto (para asignaturas sin color).
     * @param {string} texto Texto base.
     * @returns {string} Color HSL.
     */
    function colorDesdeTexto(texto) {
        let hash = 0;
        for (const caracter of String(texto || "")) {
            hash = (hash * 31 + caracter.charCodeAt(0)) % 360;
        }
        return `hsl(${hash} 72% 62%)`;
    }

    /**
     * Construye un estado vacío reutilizable.
     * @param {string} nombreIcono Icono del catálogo.
     * @param {string} titulo Título.
     * @param {string} texto Descripción.
     * @param {string} [accionHtml] Botón u acción opcional ya escapada.
     * @returns {string} HTML del estado vacío.
     */
    function vacio(nombreIcono, titulo, texto, accionHtml = "") {
        return `
            <div class="vacio">
                <span class="vacio__icono">${icono(nombreIcono)}</span>
                <div>
                    <p class="vacio__titulo">${escapar(titulo)}</p>
                    <p class="vacio__texto">${escapar(texto)}</p>
                </div>
                ${accionHtml}
            </div>`;
    }

    /**
     * Retrasa la ejecución de una función hasta que deje de llamarse.
     * @param {Function} funcion Función a ejecutar.
     * @param {number} [espera] Milisegundos de espera.
     * @returns {Function} Función con retardo.
     */
    function retrasar(funcion, espera = 180) {
        let temporizador = null;
        return (...argumentos) => {
            global.clearTimeout(temporizador);
            temporizador = global.setTimeout(() => funcion(...argumentos), espera);
        };
    }

    global.AgendaUtilidades = {
        icono,
        iconos: TRAZOS,
        $,
        $$,
        crear,
        escapar,
        dosDigitos,
        aFecha,
        horaCorta,
        claveFecha,
        hoyIso,
        fechaCorta,
        fechaLarga,
        fechaRelativa,
        diasHasta,
        duracion,
        lunesDe,
        limitar,
        etiquetaTipo,
        etiquetaPrioridad,
        insigniaPrioridad,
        iniciales,
        colorDesdeTexto,
        vacio,
        retrasar,
        COLORES_PRIORIDAD
    };
})(window);
