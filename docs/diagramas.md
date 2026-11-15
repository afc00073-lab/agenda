# Diagramas de comportamiento

Este documento complementa a [`arquitectura.md`](arquitectura.md) con los
diagramas de casos de uso, los flujos del motor de notificaciones y del
sincronizador iCalendar, y la secuencia completa de una interacción a través de
`QWebChannel`.

---

## 1. Casos de uso

Actores: **Estudiante** (actor principal), **Sistema operativo** (notificaciones,
bandeja, arranque) y **Servidor externo** (feed `.ics` de Moodle/Google/Outlook).

```mermaid
flowchart LR
    E(("👩‍🎓 Estudiante"))
    SO(("🖥️ Sistema<br/>operativo"))
    WEB(("☁️ Servidor<br/>ICS"))

    subgraph Agenda["Agenda Académica Inteligente"]
        CU1["Consultar panel de inicio"]
        CU2["Gestionar asignaturas"]
        CU3["Gestionar eventos y clases"]
        CU4["Arrastrar eventos en el calendario"]
        CU5["Mover tarjetas en el Kanban"]
        CU6["Gestionar subtareas"]
        CU7["Calcular nota actual y nota necesaria"]
        CU8["Registrar evaluación con peso"]
        CU9["Iniciar sesión Pomodoro"]
        CU10["Consultar analíticas"]
        CU11["Importar archivo .ics"]
        CU12["Suscribirse a URL .ics"]
        CU13["Recibir notificaciones nativas"]
        CU14["Posponer o descartar aviso"]
        CU15["Mostrar u ocultar el gadget"]
        CU16["Ajustar opacidad y posición del gadget"]
        CU17["Cambiar tema visual"]
        CU18["Exportar informe académico en Markdown"]
        CU19["Crear o restaurar respaldo"]
        CU20["Activar inicio automático"]
        CU21["Crear tarea desde la bandeja"]
        CU22["Completar tarea desde el gadget"]

        E --> CU1 & CU2 & CU3 & CU4 & CU5 & CU6 & CU7 & CU8
        E --> CU9 & CU10 & CU11 & CU12 & CU14 & CU15 & CU16
        E --> CU17 & CU18 & CU19 & CU20 & CU21 & CU22
        CU11 -.->|incluye| CU3
        CU12 -.->|incluye| CU3
        CU12 <-->|HTTP GET| WEB
        CU13 <-->|API nativa| SO
        CU20 -->|.desktop / registro| SO
        CU21 -->|menú contextual| SO
        CU16 -.->|extiende| CU15
        CU14 -.->|extiende| CU13
    end
```

### Resumen de actores y garantías

| Caso de uso | Precondición | Resultado observable |
| --- | --- | --- |
| Gestionar eventos | Asignatura existente (opcional) | Evento visible en calendario, inicio y gadget |
| Arrastrar evento | Evento en el rango visible | Nueva fecha persistida y vista refrescada |
| Calcular notas | Evaluaciones con peso | Nota media y nota necesaria por objetivo |
| Suscribirse a URL | URL `http(s)` válida | Eventos importados sin duplicados por `UID` |
| Notificar | Evento futuro con recordatorios | Aviso nativo + entrada en la campana |
| Respaldar | Base de datos abierta | ZIP con instantánea coherente verificable |

---

## 2. Flujo del motor de notificaciones y de la sincronización `.ics`

```mermaid
flowchart TD
    Inicio(["QTimer cada 30 s"]) --> Revisar["PlanificadorNotificaciones.revisar(ahora)"]

    Revisar --> Consultar["Consultar eventos de los próximos 7 días<br/>y notificaciones pendientes"]
    Consultar --> PorEvento{"¿Quedan eventos<br/>por evaluar?"}
    PorEvento -- No --> Resumen{"¿Hora del resumen<br/>matutino?"}
    PorEvento -- Sí --> Antelaciones["Leer recordatorios del evento<br/>(ej. 1440, 120, 15 min)"]
    Antelaciones --> Calcular["programada = inicio - antelación"]
    Calcular --> Vencido{"¿programada <= ahora<br/>y no enviada?"}
    Vencido -- No --> PorEvento
    Vencido -- Sí --> Crear["Crear notificación en SQLite"]
    Crear --> Notificar["NotificadorNativo.enviar(título, mensaje)"]
    Notificar --> Actualizar["Marcar enviada + emitir datosActualizados"]
    Actualizar --> SO["Centro de notificaciones del SO"]
    Actualizar --> PorEvento

    Resumen -- Sí --> ResumenEnviado{"¿Ya se envió hoy?"}
    ResumenEnviado -- Sí --> Fin(["Esperar siguiente ciclo"])
    ResumenEnviado -- No --> Construir["Construir resumen: clases y entregas"]
    Construir --> Notificar

    subgraph Sincro["Sincronización iCalendar"]
        S1(["Timer o acción manual"]) --> S2["Leer suscripciones activas"]
        S2 --> S3{"¿Toca sincronizar?"}
        S3 -- No --> S8(["Fin"])
        S3 -- Sí --> S4["Descargar URL o leer archivo<br/>(timeout 15 s)"]
        S4 --> S5["Desplegar líneas y parsear VEVENT"]
        S5 --> S6{"¿UID ya existe?"}
        S6 -- Sí --> S7["Actualizar campos del evento"]
        S6 -- No --> S9["Insertar evento con origen=ics"]
        S7 --> S10["Registrar última sincronización"]
        S9 --> S10
        S10 --> S11["Emitir datosActualizados"]
        S11 --> S8
        S4 -.->|error de red| E1["Notificar Toast de error<br/>sin borrar datos previos"]
        E1 --> S8
    end

    Fin --> S1
```

### Reglas del motor

1. **Idempotencia**: antes de enviar se comprueba la clave
   `(evento_id, programada_para)`; reiniciar la app no duplica avisos.
2. **Posponer**: `pospuesta_hasta` retrasa el envío sin perder el aviso original.
3. **Bajo consumo**: una consulta indexada cada 30 segundos; sin hilos extra.
4. **Resumen matutino**: una única notificación por día natural, después de la
   hora configurada.
5. **Sincronización segura**: si la descarga falla, se conservan los eventos
   anteriores y se informa del error con un aviso no bloqueante.

---

## 3. Secuencia `QWebChannel`: del clic en CSS/JS al gadget actualizado

Se muestra el caso «completar una tarea desde el gadget». La misma secuencia se
aplica a cualquier vista de la aplicación principal.

```mermaid
sequenceDiagram
    autonumber
    actor E as Estudiante
    participant G as gadget.html<br/>(JS + CSS)
    participant C as QWebChannel
    participant A as ApiPuente<br/>(Python)
    participant R as RepositorioEventos
    participant BD as SQLite (WAL)
    participant P as VentanaPrincipal<br/>(index.html)

    E->>G: Clic en la casilla de la tarea
    G->>G: Animación optimista: verificación + tachado
    G->>C: puente.completar_evento(id, true)
    C->>A: Invocación de ranura (JSON)
    A->>R: marcar_completado(id, completado=True)
    R->>BD: BEGIN IMMEDIATE · UPDATE eventos · COMMIT
    BD-->>R: Cambios confirmados (WAL)
    R-->>A: Evento actualizado (dict)
    A-->>C: Respuesta JSON
    C-->>G: Callback de JavaScript
    A->>A: emitir datosActualizados("evento")
    A-->>P: Señal Qt → JS (todas las vistas)
    P->>C: solicitar_panel_inicio() / listar_eventos()
    C->>A: Ranuras de consulta
    A->>R: Consultas de solo lectura (WAL)
    R->>BD: SELECT ...
    BD-->>R: Filas
    R-->>A: Listas serializables
    A-->>P: JSON
    P->>P: Re-render con transiciones CSS
    Note over G,P: El gadget y la ventana principal<br/>comparten la misma fuente de verdad
```

### Contrato del puente

- Todas las ranuras reciben y devuelven **cadenas JSON** para evitar
  incompatibilidades de tipos entre Qt y JavaScript.
- Los errores se devuelven como `{"ok": false, "error": "mensaje"}`; nunca se
  propaga una excepción Python a JavaScript.
- La señal `datosActualizados(categoria)` permite refrescos selectivos
  (`panel`, `evento`, `kanban`, `notas`, `gadget`, `configuracion`).
- La señal `notificacionRecibida(json)` alimenta la campana y los *toasts*.

---

## 4. Estados de una tarjeta Kanban

```mermaid
stateDiagram-v2
    [*] --> Pendiente: crear tarea
    Pendiente --> EnDesarrollo: arrastrar / iniciar
    EnDesarrollo --> Revision: arrastrar / terminar práctica
    Revision --> EnDesarrollo: correcciones
    Revision --> Entregado: validar y entregar
    Entregado --> Revision: reabrir entrega
    EnDesarrollo --> Pendiente: bloquear
    Entregado --> [*]: archivar
```

Cada transición es un `UPDATE eventos SET estado_kanban=?` validado en el
servicio; el arrastre visual solo confirma el cambio cuando SQLite lo acepta,
de modo que la interfaz nunca muestra un estado que no esté persistido.
