/**
 * ============================================================================
 *  PUENTE QWebChannel · Agenda Académica Inteligente
 * ----------------------------------------------------------------------------
 *  Envoltorio común para las dos ventanas web (aplicación principal y gadget).
 *  Convierte las ranuras Qt en promesas de JavaScript y reemite las señales de
 *  Python como eventos DOM (`agenda:datosActualizados`, etc.), de modo que cada
 *  vista se suscribe sin conocer los detalles de QWebChannel.
 *
 *  Todas las respuestas del backend son cadenas JSON con la forma:
 *      { ok: true, datos: ..., mensaje: "" }  |  { ok: false, error: "..." }
 * ============================================================================
 */
(function (global) {
    "use strict";

    /** Estado interno de la conexión con Python. */
    const estado = {
        puente: null,
        conectado: false,
        iniciado: false,
        promesa: null
    };

    /** Señales que Python expone y que reemitimos como eventos DOM. */
    const SENALES = [
        "datosActualizados",
        "gadgetConfigurado",
        "pomodoroActualizado",
        "notificacionRecibida",
        "solicitudNavegacion",
        "solicitudModal",
        "temaCambiado"
    ];

    /**
     * Conecta las señales Qt con eventos del documento.
     * @param {object} puente Objeto Python registrado en el canal.
     */
    function conectarSenales(puente) {
        SENALES.forEach((nombre) => {
            const senal = puente[nombre];
            if (senal && typeof senal.connect === "function") {
                senal.connect((valor) => {
                    document.dispatchEvent(
                        new CustomEvent(`agenda:${nombre}`, { detail: valor })
                    );
                });
            }
        });
    }

    /**
     * Inicializa QWebChannel una sola vez. Si la página se abre fuera de Qt
     * (por ejemplo, en un navegador para revisar el diseño), se resuelve con
     * `null` y la interfaz muestra su estado vacío sin romperse.
     * @returns {Promise<object|null>} Promesa con el objeto puente.
     */
    function iniciar() {
        if (estado.promesa) {
            return estado.promesa;
        }
        estado.promesa = new Promise((resolver) => {
            const disponible =
                typeof global.QWebChannel !== "undefined" &&
                typeof global.qt !== "undefined" &&
                global.qt.webChannelTransport;

            if (!disponible) {
                console.warn("[puente] QWebChannel no disponible: modo sin conexión");
                resolver(null);
                return;
            }

            new global.QWebChannel(global.qt.webChannelTransport, (canal) => {
                const puente = canal.objects && canal.objects.puente;
                if (!puente) {
                    console.error("[puente] El objeto 'puente' no está registrado");
                    resolver(null);
                    return;
                }
                estado.puente = puente;
                estado.conectado = true;
                conectarSenales(puente);
                document.dispatchEvent(new CustomEvent("agenda:conectado"));
                resolver(puente);
            });
        });
        estado.iniciado = true;
        return estado.promesa;
    }

    /**
     * Invoca una ranura de Python y devuelve su respuesta ya parseada.
     * @param {string} metodo Nombre de la ranura (por ejemplo, "crear_evento").
     * @param {...any} argumentos Argumentos esperados por la ranura.
     * @returns {Promise<object>} Respuesta JSON convertida a objeto.
     */
    function llamar(metodo, ...argumentos) {
        return iniciar().then((puente) => {
            if (!puente || typeof puente[metodo] !== "function") {
                return Promise.reject(
                    new Error(`El método «${metodo}» no está disponible en el puente`)
                );
            }
            return new Promise((resolver, rechazar) => {
                try {
                    puente[metodo](...argumentos, (respuesta) => {
                        try {
                            resolver(typeof respuesta === "string" ? JSON.parse(respuesta) : respuesta);
                        } catch (error) {
                            console.error("[puente] Respuesta no válida", error, respuesta);
                            resolver({ ok: false, error: "Respuesta no válida del backend" });
                        }
                    });
                } catch (error) {
                    rechazar(error);
                }
            });
        });
    }

    /**
     * Ejecuta una llamada y extrae directamente el campo `datos`.
     * Lanza un error legible si el backend responde `ok: false`.
     * @param {string} metodo Ranura a invocar.
     * @param {...any} argumentos Argumentos de la ranura.
     * @returns {Promise<any>} Contenido de `datos`.
     */
    async function obtener(metodo, ...argumentos) {
        const respuesta = await llamar(metodo, ...argumentos);
        if (!respuesta || respuesta.ok === false) {
            throw new Error((respuesta && respuesta.error) || "Operación no completada");
        }
        return respuesta.datos;
    }

    /**
     * Suscribe una función a una señal reemitida por el puente.
     * @param {string} nombre Nombre de la señal sin el prefijo `agenda:`.
     * @param {(detalle: any) => void} manejador Función receptora.
     * @returns {() => void} Función para cancelar la suscripción.
     */
    function al(nombre, manejador) {
        const escucha = (evento) => manejador(evento.detail);
        document.addEventListener(`agenda:${nombre}`, escucha);
        return () => document.removeEventListener(`agenda:${nombre}`, escucha);
    }

    /**
     * Aplica un tema cambiando el atributo del documento. Las transiciones CSS
     * se encargan del fundido de colores.
     * @param {string} tema Identificador del tema.
     */
    function aplicarTema(tema) {
        if (!tema) {
            return;
        }
        document.documentElement.dataset.tema = tema;
        document.dispatchEvent(new CustomEvent("agenda:temaAplicado", { detail: tema }));
    }

    global.PuenteAgenda = { iniciar, llamar, obtener, al, aplicarTema, estado };
})(window);
