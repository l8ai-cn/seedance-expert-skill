# Spanish Vocabulary

Use this reference for Spanish Seedance prompt wording, role binding, and compact prompt compression. Binding is a separate typed step: the selected profile preserves an external opaque handle, derives an evidenced media ordinal, or uses structured roles with no token. Never translate provider syntax.

| Function | Spanish | English meaning |
|---|---|---|
| Request role | asignar la imagen inicial como primer fotograma | structured first-frame role; no invented prompt token |
| Request role | asignar la imagen final como fotograma final | structured last-frame role; no invented prompt token |
| Binding clause | `fija la identidad del personaje` | locks character identity |
| Binding clause | `solo controla el movimiento de cámara` | controls camera movement only |
| Binding clause | `solo marca el ritmo de la acción` | controls action rhythm only |
| Binding clause | `solo marca tempo y ambiente` | controls tempo and mood only |
| FirstLastFrame | `mantener el primer fotograma sin cambios` | keep first frame unchanged |
| FirstLastFrame | `usar el fotograma final como objetivo visual` | final frame is the target endpoint |
| FirstLastFrame | `movimiento continuo sin salto de montaje` | continuous motion, no jump cut |
| FirstLastFrame | `mantener el mismo personaje, vestuario y espacio` | preserve same character, wardrobe, and layout |
| Camera | `travelling de acercamiento lento` | slow push-in |
| Camera | `travelling de retroceso para revelar el espacio` | pull back to reveal space |
| Camera | `seguimiento lateral estable` | stable lateral tracking |
| Camera | `plano medio fijo` | locked medium shot |
| Camera | `primer plano macro` | macro close-up |
| Camera | `plano en contrapicado` | low-angle shot |
| Camera | `plano sobre el hombro` | over-the-shoulder shot |
| Camera | `cámara en mano con leve respiración` | handheld camera with slight breathing sway |
| Shot | `plano medio corto` | medium close-up |
| Shot | `plano general amplio` | wide establishing shot |
| Shot | `perfil de tres cuartos` | three-quarter profile |
| Lens | `24 mm angular con sensación de espacio` | 24mm wide spatial feel |
| Lens | `50 mm con perspectiva natural de retrato` | 50mm natural portrait feel |
| Lens | `lente macro para detalle de material` | macro lens for material detail |
| Lighting | `contraluz suave` | soft backlight |
| Lighting | `luz cálida práctica desde la izquierda` | warm practical light from left |
| Lighting | `luz de contorno fría de luna` | cool moon rim light |
| Lighting | `luz volumétrica atravesando niebla fina` | volumetric light through mist |
| Lighting | `asfalto mojado reflejando neón` | wet pavement reflects neon |
| Motion | `la niebla se dispersa alrededor de los pasos` | fog spreads around footsteps |
| Motion | `las gotas se unen y descienden` | droplets merge and slide down |
| Motion | `gira lentamente la cabeza y se detiene` | slow head turn and stop |
| Motion | `la tela se mueve de forma natural con el gesto` | fabric moves naturally with action |
| VFX | `partículas doradas se elevan y se disipan` | gold particles rise and dissipate |
| VFX | `arcos eléctricos azules recorren el borde` | blue arcs crawl along the edge |
| VFX | `un barrido de luz cruza la superficie del material` | light sweep crosses material surface |
| Audio | `una frase corta y clara` | one short clear spoken line |
| Audio | `sin música, solo ambiente bajo` | no music, low ambience only |
| Audio | `cámara fija durante el diálogo` | locked camera during dialogue |
| Audio | `los pasos siguen el pulso` | footsteps hit the beat |
| Text | `sin subtítulos, marcas de agua ni texto adicional` | no subtitles, watermarks, or extra text |
| Editing | `continuar el plano` | continue the shot |
| Editing | `extender cinco segundos` | extend by five seconds |
| Editing | `reemplazar solo el fragmento fallido` | replace only the failed segment |
| Constraint | `mantener logotipo, etiqueta, forma y color sin cambios` | preserve logo, label, shape, and color |
| Constraint | `solo cambian movimiento, luz y cámara` | change only motion, light, and camera |
| Constraint | `no copiar personas, lugar ni marcas` | do not copy people, place, or brands |
| Safety | `sustituir por un personaje original` | replace with an original character |
| Safety | `usar solo referencias autorizadas` | use only authorized references |
| Safety | `mantener la función creativa, no la identidad protegida` | preserve creative function, not protected identity |

## Compact Template

In a separate text segment after the typed binding, begin with punctuation: `: referencia autorizada; mantener [identidad/producto/rostro/logotipo] sin cambios. Solo cambia [acción/luz/cámara]. Cámara: [movimiento único]. Sonido: [señal].`

## Multimodal Template

Compile three typed bindings with these clauses: `fija el personaje original`; `solo controla el movimiento de cámara; no copiar persona, lugar ni marca`; `solo marca tempo y ambiente`.

## Dialogue Notes

Field-observed and under-tested for Spanish specifically as of 2026; test per surface, never promise results. Treat Spanish as the non-English/Mandarin tier.

- Keep to one short clear line, about one breath.
- For reliable Spanish voice, prefer a voice reference (attach the spoken line so the model lip-syncs to it) or plan a post-dub.

## Slop Traps

Consenso de la comunidad: los adjetivos de calidad abstractos desestabilizan la generación porque el modelo no sabe qué elemento enfatizar. Convierte cada palabra-sensación en los elementos físicos que la producen (verbo de cámara + velocidad + punto de vista, fuente de luz + dirección + comportamiento).

| Muletilla | Escribe en su lugar |
|---|---|
| `cinematográfico` | escala de plano, movimiento de cámara, fuente de luz y etalonaje: `plano general amplio, travelling lento, sol bajo, tonos teal y naranja` |
| `épico` | escala física: tamaño de la multitud, distancia a la cámara, altura de la estructura |
| `impresionante / asombroso` | el único contraste o revelación visible que lo justifica |
| `hermoso / precioso` | color, textura, material, comportamiento de la luz |
| `obra maestra / alta calidad / 8K` | eliminar; la calidad no se pide y la resolución es un ajuste |
| `espectacular` | el momento concreto: qué se mueve, qué se revela |
| `dramático` | puesta en escena, sombra, silencio o presión de cámara |
| `mágico` | comportamiento de partículas, fuente del brillo, trayectoria |
| `de ensueño` (solo) | qué lo hace onírico: `bruma fina, luz volumétrica, flotación lenta` |
| `dinámico` | el movimiento concreto, su velocidad y su punto final |
| `con mucha atmósfera` | los elementos físicos: `niebla fina, reflejos en el suelo mojado, ambiente bajo` |
| `profesional` | iluminación controlada del producto, fondo limpio, cámara estable |
