# Porton del abismo v2 -- el indice refinado PASA

**Fecha:** 2026-09-07. **Decision que lo disparo:** Pedro eligio "refinar el indice y re-medir" tras el NO PASA del porton v1 (`consulta_abismo_resultados.md`). **Veredicto: la variante "dura" PASA las cinco compuertas a N=6 y quedo aterrizada en `calipso/abismo/contrato.py` (byte-identica a lo medido).**

## Protocolo

- **Banco v2** (commit `7af62b7`): 30 items (18 positivos 6/6/6, 12 negativos). Cambios vs v1: `pro-cual` reemplazado por `pro-ultimo` (el item viejo pedia un ranking que ninguna fuente sabe contestar: su 0/6 era diseno, no modelo) y dos negativos nuevos (`neg-codigo2`, `neg-este-chat`) para que el techo de espurias no descanse en un solo item.
- **Variantes:** cuatro lentes disenadas desde la evidencia del v1 (la falla dominante era CONFABULACION confiada, no formato), cada una medida con su propio cache (la clave del cache no sabe de contratos). Screening a N=2, ganadora a N=6 completo.
- Modelo qwen2.5:7b, temp 0, num_ctx 4096. Identidad del system fija; solo cambia el bloque del contrato.

## La tabla (banco v2; screening N=2, ganadora N=6)

| Contrato | chars | memoria | proyecto | chats | espurias | ruteo | Veredicto |
|---|---|---|---|---|---|---|---|
| linea base (v1, 534c) | 534 | 17% | 50% | 67% | 8% | 100% | NO PASA legibles |
| **dura (N=6 FINAL)** | 598 | **83% (30/36)** | **100% (36/36)** | **100% (36/36)** | **8% (6/72)** | **94% (96/102)** | **PASA x5** |
| gatillo-posicional | 596 | 100% | 67% | 100% | **67%** | 88% | NO PASA (marca todo) |
| ejemplo-dentista | 598 | 83% | 100% | 100% | 8% | 88% | NO PASA ruteo (borde) |
| larga (sin techo, 897c) | 897 | 67% | 100% | 83% | 4% | 97% | NO PASA memoria |

Latencia de la ganadora: mediana 3074 ms por llamada, max 11977 ms.

## Que aprendio el proyecto

1. **Nombrar el error exacto funciona en este 7b, por segunda vez.** La variante ganadora abre negando la fuente inventada ("No sabes nada de Pedro fuera de este prompt"), nombra el peor error con todas las letras y prohibe la formula literal que el cache v1 mas mostro ("segun mis registros"). Es el mismo molde del juez de privacidad ("ante la duda, MARCALO" -> "ante la duda, CONSULTA"). Memoria pasa de 17% a 83% sin mover las espurias.
2. **El gatillo binario sobre-dispara.** "Si SI: lo PRIMERO que escribis es la marca" + "ante la duda, MARCA" llevo las espurias de 8% a 67%: el modelo marco hasta en "buen dia". La prohibicion (dura) calibra mejor que la obligacion (gatillo).
3. **El techo de 600 NO era la restriccion.** La variante de 897 chars rindio PEOR en memoria (67%) que la de 598. El presupuesto del indice queda como esta; no hay que tocar el spec.
4. **El few-shot quedo al borde del ruteo** (88% vs piso 90): el ejemplo unico sesgo levemente el ruteo hacia la fuente del ejemplo. No vale el costo.
5. El punto flojo restante de la ganadora: memoria queda EXACTO en el piso (30/36; los 6 sin-marca se concentran en items de sintesis tipo "armame un regalo con lo que te dije"), y el ruteo 94% pierde 6 marcas que eligen memoria donde se esperaba chats -- ambiguedad real entre fuentes vecinas, no error grosero. Con techo, no con urgencia: el cableado 1b puede arrancar.

## Evidencia

- Cache crudo de la ganadora (30 items x 6 corridas): `experimentos/consulta_abismo_cache_dura_n6.jsonl` (archivado junto al resultado; la leccion del review 1a de no dejar la evidencia en /tmp).
- Las cuatro variantes: `experimentos/variantes/*.txt`. La ganadora quedo generada por `contrato.bloque_contrato` byte-identica para el caso medido (verificado con assert en la suite... en el smoke del aterrizaje; el caso de recorte con muchos nombres agrega una cola honesta que el caso medido no toca).
- Corridas de screening (N=2): caches y reportes en /tmp de la sesion (`abismo_b2_*.{jsonl,md}`), efimeros a proposito -- la ganadora es la unica evidencia que el repo carga.

## Que sigue

El porton estaba definido en el spec seccion 12 como la compuerta del plan 1b (el cableado a ws_chat: filtro compuesto, estado del turno, reentrada sintetica, senal de pondering, UIs y pulso). **Con estas cinco compuertas en verde, el 1b queda desbloqueado.**
