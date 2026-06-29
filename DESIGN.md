# DESIGN.md — Identidad visual de Calipso

> Documento de referencia para cualquier sesión que toque la UI.
> Toda decisión visual deriva de aquí. Si no está en este documento, pregunta antes de inventar.

---

## Visión

Calipso no es un IDE ni un chat. Es un **cockpit personal** — el tablero de control que Pedro usa todos los días, que lo conoce, que tiene memoria activa y goals vivos. La UI debe sentirse como una herramienta que alguien *habita*, no como una demo de producto SaaS.

El tono visual: **instrumental, íntimo, preciso**. Como el tablero de un avión bien diseñado: cada indicador tiene su lugar, nada sobra, y quien lo opera siente que está al mando.

---

## Paleta

El riesgo deliberado: **ámbar como acento primario**, no azul. El azul/cyan es el default de toda herramienta dev (VS Code, GitHub, Linear). El ámbar es el color de los displays de cabina, los relojes analógicos de misión, los terminales de control real. Cálido, preciso, personal.

```css
:root {
  /* Fondos */
  --void:     #08090B;   /* fondo raíz — negro casi puro con tinte cálido sutil */
  --surface:  #0F1117;   /* superficie primaria */
  --elevated: #161922;   /* paneles, drawers, tarjetas */
  --border:   #1E2330;   /* divisores, bordes */

  /* Texto */
  --bright:   #E8EDF5;   /* headings, texto importante */
  --text:     #B8C2D8;   /* cuerpo — blanco apagado con temperatura cálida */
  --muted:    #4A5268;   /* texto secundario, hints, labels */

  /* Acentos */
  --amber:     #F0A030;  /* acento primario — identidad de Calipso */
  --amber-dim: #3D2800;  /* fondo de estados amber (hover, activo, focus) */
  --amber-glow: rgba(240, 160, 48, 0.15); /* halo/glow para el pulso */
  --frost:     #5B8FA8;  /* acento secundario frío — contrasta con ámbar */
  --frost-dim: #162330;  /* fondo de estados frost */

  /* Semánticos */
  --success:  #4CAF84;
  --danger:   #E05C5C;
  --warning:  #D49B3A;   /* ámbar oscuro, no el primario */
}
```

**Reglas de uso:**
- `--amber` solo para: acción primaria, estado activo, el elemento que merece atención inmediata. No para decoración.
- `--frost` para: estados secundarios, enlaces inline, indicadores de info pasiva.
- Nunca usar `--amber` y `--frost` juntos en el mismo componente — uno siempre cede al otro.
- Los fondos son siempre de la familia `--void / --surface / --elevated`. Nada más.

---

## Tipografía

```
Display / UI:   Plus Jakarta Sans  (Google Fonts)
                — Personalidad moderna, no estéril. Usada para headings,
                  labels del header, nombres de panel.

Mono / código:  JetBrains Mono     (Google Fonts o bundled)
                — Mejores ligaduras de su clase. Monaco editor + cualquier
                  dato numérico, path, timestamp, código inline.

Fallback stack: system-ui, -apple-system, sans-serif
```

### Escala tipográfica

| Token       | Size  | Weight | Uso                                      |
|-------------|-------|--------|------------------------------------------|
| `--t-data`  | 11px  | 400    | chips, badges, timestamps, metadatos     |
| `--t-ui`    | 13px  | 400    | labels, botones pequeños, items de lista |
| `--t-body`  | 15px  | 400    | cuerpo de chat, descripciones            |
| `--t-sub`   | 17px  | 600    | subtítulos de panel, nombres de sección  |
| `--t-head`  | 22px  | 700    | títulos de drawer, pantalla vacía        |

**Reglas tipográficas:**
- Los nombres de panel y el header usan Plus Jakarta Sans en weight 600, sentence case.
- Timestamps, versiones, rutas de archivo: siempre JetBrains Mono.
- Nunca mezclar ambas familias en la misma línea de texto.
- Line-height de 1.5 para cuerpo, 1.2 para headings.

---

## Elemento firma: el Pulso Ámbar

Cuando Calipso está procesando (esperando respuesta del modelo), un punto ámbar en el header **pulsa suavemente** — no un spinner, un latido. 

```css
@keyframes calipso-pulse {
  0%, 100% { opacity: 0.4; transform: scale(1);    box-shadow: 0 0 0   0 var(--amber-glow); }
  50%       { opacity: 1.0; transform: scale(1.15); box-shadow: 0 0 8px 4px var(--amber-glow); }
}

.calipso-alive {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--amber);
  animation: calipso-pulse 1.8s ease-in-out infinite;
}
```

Este punto está siempre visible en el header, junto al nombre "Calipso". En reposo: ámbar estático al 40% de opacidad. Procesando: pulso vivo. Error: rojo estático. Es el único elemento animado que existe sin trigger de usuario — todo lo demás se mueve solo si el usuario interactúa.

---

## Layout

```
┌─────────────────────────────────────────────────────────────┐
│ ● Calipso  calipso  Proyecto  Chats  Cambios  ...    listo  │  ← Header: 42px, --void bg
├──────────────────────────────────────────────────────────────│
│ [goal bar — 1 línea si hay meta activa, 0px si no]          │  ← colapsa cuando no hay meta
├────────┬──────────────────────────────┬─────────────────────┤
│        │                              │                     │
│ Explor │     Editor Monaco            │   Chat / Panel      │
│ ador   │     (fondo --void)           │   (fondo --surface) │
│        │                              │                     │
│ 220px  │     flex-grow: 1            │   380px mín         │
│ fijo   │                              │                     │
│        │                              │                     │
└────────┴──────────────────────────────┴─────────────────────┘
```

**Reglas de layout:**
- El explorador colapsa a 0 (icono only) si el panel de chat necesita espacio en pantallas < 1200px.
- Los drawers (Config, Plugins, Memoria, etc.) se abren como **overlay lateral derecho**, no empujan el layout. Ancho máximo 480px, con backdrop semi-transparente.
- La Goal Bar usa `--amber` como color de borde izquierdo (4px), fondo `--elevated`. Es el único elemento de la UI que tiene `--amber` estructuralmente — refuerza que las metas son lo más importante después del chat.
- Nada de sombras grandes (`box-shadow` masivo) — si algo necesita elevación, usa un borde `1px solid var(--border)` más claro.

### Espaciado

```
--space-xs:  4px
--space-sm:  8px
--space-md:  12px
--space-lg:  20px
--space-xl:  32px
```

Regla: los elementos interactivos tienen al menos 32px de touch target. El padding interno de botones es siempre `6px 14px` para size normal, `4px 10px` para size small.

---

## Componentes

### Botones

```
Primario:  bg --amber, text #000, border none, border-radius 6px
           hover: brightness(1.1)
           
Secundario: bg transparent, border 1px --border, text --text
            hover: border-color --amber, color --amber

Peligro:   bg transparent, border 1px --danger, text --danger
           hover: bg --danger, text #fff
```

Sin gradientes. Sin sombras grandes. La jerarquía viene del color y el peso, no de efectos.

### Chips / Badges

```
Instalado:  border 1px --frost, text --frost, bg transparent, border-radius 999px
Activo:     border 1px --amber, text --amber, bg --amber-dim, border-radius 999px
Error:      border 1px --danger, text --danger, bg transparent
```

### Items de lista (side-item)

```
padding: 8px 12px
border: 1px solid --border
border-radius: 6px
background: transparent

hover:
  border-color: --border (más claro)
  background: --elevated
```

### Input / Textarea

```
background: --void
border: 1px solid --border
border-radius: 6px
color: --bright
padding: 8px 12px

focus:
  border-color: --amber
  outline: none
  box-shadow: 0 0 0 2px var(--amber-dim)
```

---

## Movimiento

Principio: **una animación útil, no decorativa**. 

| Elemento | Animación | Duración |
|---|---|---|
| Pulso ámbar (procesando) | scale + opacity + glow | 1.8s infinite ease-in-out |
| Drawers (abrir/cerrar) | translateX desde la derecha | 180ms ease-out |
| Aparición de mensajes en chat | fadeIn + translateY(4px) | 120ms ease-out |
| Botones: hover | background-color transition | 100ms |
| Modales | opacity + scale(0.97→1) | 140ms ease-out |

Sin bounces, sin springs exagerados, sin parallax. La UI es una herramienta — se mueve cuando ayuda a entender qué pasó, no para impresionar.

Respetar `prefers-reduced-motion`: todo excepto el pulso ámbar (que puede ir a opacity sola, sin scale).

---

## Voz / Copy

- **Sentence case siempre.** "Buscar en catálogo" no "Buscar En Catálogo".
- Los botones dicen lo que hacen: "Instalar", "Actualizar ahora", "Cerrar". No "OK", no "Submit".
- Los estados vacíos son invitaciones: "No hay metas activas — escribe `meta: ...` para crear una."
- Los errores explican y dirigen: "Calipso no encontró claude en PATH. Instálalo con `npm i -g @anthropic-ai/claude-code`."
- Calipso habla en primera persona cuando comunica su estado: "Estoy pensando…", "Listo." — no "Procesando…", no "Done."

---

## Lo que NO es Calipso

- ❌ Gradientes en botones o fondos de sección.
- ❌ Border-radius > 10px en contenedores grandes (se ve SaaS genérico).
- ❌ Más de dos familias tipográficas.
- ❌ Sombras que imitan papel (esa estética es de light mode).
- ❌ Íconos decorativos sin función. Si hay un ícono, hace algo o comunica un estado.
- ❌ Colores saturados múltiples en la misma pantalla. El ámbar es el único color que grita — todo lo demás susurra.
- ❌ Texto en `--amber` para párrafos o labels normales — solo para lo que merece atención inmediata.

---

## Checklist de implementación

Cuando toques la UI, antes de commitear:

- [ ] ¿Los colores vienen de las variables de este doc?
- [ ] ¿La acción primaria de la pantalla usa `--amber`?
- [ ] ¿Hay algún color inventado que no está en la paleta?
- [ ] ¿Los textos informativos usan `--muted` o `--text` según importancia?
- [ ] ¿El focus de teclado es visible (ring ámbar)?
- [ ] ¿Respeta `prefers-reduced-motion`?

---

*Última actualización: 2026-06-29*
