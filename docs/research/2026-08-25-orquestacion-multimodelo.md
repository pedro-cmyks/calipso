# Orquestación multi-modelo para Calipso

Síntesis de investigación — 25 de agosto de 2026.
Insumos: cinco barridos de literatura (papers 2023-2026), documentación de routers comerciales (OpenRouter, LiteLLM, Not Diamond, Martian, Azure Model Router) y panorama de modelos chinos a agosto de 2026.

Contexto: Calipso rutea con `dispatch.py` (suscripción Claude/Codex > API paga > Ollama local con qwen2.5) y puntúa aptitud con `capabilities.py`. Se está construyendo una economía interna donde cada modelo/proveedor tiene precio real y los departamentos de agentes compiten por presupuesto: el router elige la opción más barata que cumpla la aptitud requerida.

---

## 1. Mapa de patrones de orquestación y routing

La literatura converge en cuatro familias de mecanismos, más una capa transversal de evaluación. RouterBench (Martian, [arXiv 2403.12031](https://arxiv.org/abs/2403.12031)) formaliza la taxonomía: routers **predictivos** (deciden antes de generar) y **no predictivos** (cascada con verificación, y overgenerate-and-rank como cota superior).

### 1.1 Routing predictivo (decidir a priori, sin gastar)

| Sistema | Mecanismo | Resultado reportado |
|---|---|---|
| **RouteLLM** (LMSYS/Berkeley, [arXiv 2406.18665](https://arxiv.org/abs/2406.18665), [GitHub](https://github.com/lm-sys/routellm)) | 4 routers binarios fuerte/débil entrenados con preferencias de Chatbot Arena + juez GPT-4 (matrix factorization, BERT, LLM causal, similitud); umbral continuo costo/calidad | 95% de la calidad de GPT-4 con 26% de llamadas al caro (14% con augmentación); hasta 85% menos costo; overhead del router < 0.4%; transfiere a pares de modelos no vistos sin reentrenar |
| **Hybrid LLM** (Microsoft, [arXiv 2404.14618](https://arxiv.org/abs/2404.14618)) | Encoder DeBERTa que predice la **brecha de calidad** chico-grande, no la calidad absoluta; etiquetas blandas (10 muestras por modelo) | Hasta 40% menos llamadas al grande sin caída de calidad; 22% menos con solo 1% de caída |
| **Not Diamond** ([docs](https://docs.notdiamond.ai/docs/router-training-quickstart)) | Meta-modelo supervisado entrenado con (inputs propios + respuestas de cada candidato + scores de eval); regla "el barato gana si su calidad predicha empata" | Entrenamiento en minutos-horas; el conjunto ruteado supera a cada modelo individual |
| **Azure Model Router** ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router)) | LLM entrenado para rutear entre variantes full/mini/nano; se despliega como un deployment más | Dato contable clave: el routing se cobra aparte, $0.14/M tokens de input — el routing tiene precio de mercado explícito |
| **OpenRouter Auto Router** ([docs](https://openrouter.ai/docs/guides/routing/routers/auto-router)) | Clasificador ligero → ~30 tipos de tarea; ranking por gasto agregado de la comunidad en ese tipo (ventana móvil 7 días); `cost_tier` como banda, session stickiness, degradación elegante a default | Sin fee adicional; una request nunca muere por fallo del router |

### 1.2 Cascadas con verificación (decidir a posteriori)

| Sistema | Mecanismo | Resultado reportado |
|---|---|---|
| **FrugalGPT** (Stanford, [arXiv 2305.05176](https://arxiv.org/abs/2305.05176)) | Cascada ordenada por costo; scorer pequeño (estilo DistilBERT) puntúa g(q,a); si no supera un umbral **aprendido bajo restricción de presupuesto**, escala | Iguala a GPT-4 con hasta 98% menos costo (HEADLINES) o +4% de accuracy al mismo costo; ahorros 50-98% según dataset |
| **AutoMix** (CMU, [arXiv 2310.12963](https://arxiv.org/abs/2310.12963)) | El chico genera, se auto-verifica con prompt few-shot (confianza = prob. del siguiente token), un POMDP decide escalar (la señal es ruidosa) | >50% de reducción de costo a rendimiento comparable, en 5 modelos x 5 datasets; la auto-verificación no corrige la respuesta, pero sirve como señal de ruteo; métrica IBPC (beneficio incremental por unidad de costo) |

### 1.3 Ensembles y mezcla de modelos

| Sistema | Mecanismo | Resultado reportado |
|---|---|---|
| **Mixture-of-Agents** (Together/Duke, [arXiv 2406.04692](https://arxiv.org/abs/2406.04692)) | Capas de proposers que ven las salidas de la capa anterior + agregador final; fenómeno de "colaboratividad" (un LLM mejora viendo salidas ajenas, incluso de modelos peores) | Solo open source: 65.1% AlpacaEval 2.0 vs 57.5% de GPT-4o; MoA-Lite (2 capas) 59.3%, aún sobre GPT-4o. Costo: multiplica llamadas |
| **LLM-Blender** (AI2, [arXiv 2306.02561](https://arxiv.org/abs/2306.02561)) | PairRanker (comparación pareada con cross-attention, no nota absoluta) + GenFuser (fusiona top-K) | Rank medio 3.2 vs 3.9 del mejor modelo individual; top-3 en 68.6% de ejemplos vs 52.9% de Vicuna. Caro: llama a todo el pool |
| **More Agents Is All You Need** (Tencent, [arXiv 2402.05120](https://arxiv.org/abs/2402.05120)) | Muestrear N respuestas del mismo modelo y votar por mayoría | Llama2-13B con 40 muestras: 0.35 → 0.59 en GSM8K, supera a Llama2-70B single-shot (0.54); la ganancia crece con la dificultad relativa de la tarea |
| **Self-MoA** ([arXiv 2502.00674](https://arxiv.org/abs/2502.00674)) — contraevidencia | Agregar muestras del MEJOR modelo vs mezclar modelos distintos | Self-MoA +6.6% sobre MoA mixto en AlpacaEval 2.0; mezclar débiles con fuertes degrada por debajo del mejor modelo solo |

### 1.4 Orquestación de agentes (quién manda, quién escribe, quién verifica)

- **Orchestrator-workers de Anthropic** ([engineering blog](https://www.anthropic.com/engineering/built-multi-agent-research-system)): lead Opus + subagentes Sonnet en paralelo, cada delegación con 4 componentes obligatorios (objetivo, formato de salida, guía de herramientas, límites). Reglas de escalado embebidas: consulta simple = 1 agente / 3-10 tool calls; comparación = 2-4 subagentes; investigación compleja = 10+. Resultado: +90.2% sobre mono-agente, pero ~15x tokens; el uso de tokens explica el 80% de la varianza de rendimiento. Subir de modelo rinde más que duplicar tokens (Sonnet 4 > 2x tokens en Sonnet 3.7).
- **Criterios de admisión de Anthropic** ([blog](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)): multi-agente solo cuando (1) la subtarea genera >1000 tokens mayormente irrelevantes para la tarea principal, (2) hay paralelismo real de tareas independientes (aceptando 3-10x tokens), o (3) un agente acumula 20+ herramientas. Descomponer por fronteras de contexto, no por tipo de problema. Excepción que siempre funciona: subagentes de verificación (transfieren poco contexto).
- **Cognition/Devin** ([Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents)): los subagentes paralelos toman decisiones conflictivas que nadie negoció. Receta: escrituras en un solo hilo; los agentes extra aportan inteligencia (investigar, criticar, verificar), no acciones.
- **MAST** ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657), NeurIPS 2025): 1600+ trazas sobre 7 frameworks; los frameworks fallan 40-70% de las tareas. Fallos: diseño del sistema 43.8% (repetición de pasos 15.7%, ignorar terminación 12.4%), desalineación entre agentes 31.9%, verificación 24.5%. Intervención con mejor retorno medido: verificación contra el objetivo de alto nivel, +15.6% en ProgramDev. Conclusión: la robustez viene de mejor orquestación, no de modelos más grandes.
- **CrewAI jerárquico** ([Towards Data Science](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/)): el manager ejecuta TODAS las tareas en orden y la última pisa el resultado correcto (38s y 15.7k tokens para algo que necesitaba un especialista). El fix fue un manager custom con enrutado condicional explícito: -36% tokens. Advertencia directa contra delegar el routing a un framework.
- **LangGraph supervisor vs swarm** ([Focused.io](https://focused.io/lab/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture)): la precisión de enrutado cae tras 8-12 idas y vueltas (el historial desplaza el estado de la tarea). Recomendaciones: escribir el eval de routing_accuracy ANTES de añadir el segundo agente; límite de handoffs con guardia de recursión.
- **Presupuesto explícito**: BAMAS ([arXiv 2511.21572](https://arxiv.org/pdf/2511.21572)) selecciona el conjunto de LLMs con programación lineal entera bajo presupuesto y aprende la topología por refuerzo (30-50% menos costo quedando a 5-10% del ensemble sin restricción); ZEBRA reparte presupuesto monetario entre fases zero-shot. Los SDKs prácticos convergen en 5 capas: techo por petición, presupuesto rodante por sesión, tope mensual, routing por tier con degradación elegante, y circuit breakers.

### 1.5 Evaluación de routers

**RouterBench** ([arXiv 2403.12031](https://arxiv.org/abs/2403.12031)): 405,467 registros precomputados (query, respuesta de cada modelo, calidad, costo) que permiten evaluar cualquier política de ruteo offline, sin llamadas reales. Introduce el **Zero Router** (interpolación aleatoria barato/caro) como baseline de honestidad: si tu router no lo supera al mismo costo promedio, no aporta.

---

## 2. Qué mapea directo a Calipso

### 2.1 dispatch.py ya es una cascada FrugalGPT-style — con una pieza faltante

La regla de Calipso "la opción más barata que cumpla la aptitud requerida" es exactamente la formulación de FrugalGPT: una lista de modelos ordenada por costo con un criterio de suficiencia por etapa. La diferencia es **dónde** se decide:

- **Calipso hoy**: decisión **a priori** — `capabilities.py` predice aptitud antes de generar. Esto es la familia RouteLLM / Hybrid LLM / RouterBench-predictivo.
- **FrugalGPT/AutoMix**: decisión **a posteriori** — el barato responde primero y un verificador decide si escalar.

Son complementarios, no excluyentes, y la versión a posteriori es casi gratis para Calipso porque su primer escalón económico (qwen local en Ollama) cuesta cero dólares: dejar que qwen responda, auto-verificar con un prompt few-shot (AutoMix), y solo pagar API si la confianza no supera el umbral. AutoMix reporta >50% de ahorro con este esquema sin entrenar nada; FrugalGPT muestra que el umbral no se fija a mano sino que **se aprende por tarea contra un presupuesto** — que es literalmente lo que la economía de departamentos necesita: departamento pobre, umbral agresivo hacia lo local.

### 2.2 capabilities.py: de score absoluto a brecha esperada

Hybrid LLM da la reformulación semántica correcta: la pregunta del router no es "¿qué tan bueno es qwen en esto?" sino "**¿cuánto pierdo por no usar Claude aquí?**". Si `capabilities.py` puntúa brecha esperada contra el mejor modelo disponible, la decisión económica es directa: escalar solo cuando la brecha justifica el precio. Las etiquetas blandas del paper (muestrear varias respuestas y estimar la probabilidad de que el chico iguale al grande) son replicables en local con Ollama a costo cero en dólares.

X-MAS ([arXiv 2505.16997](https://arxiv.org/html/2505.16997)) añade la otra dimensión: no existe campeón universal — el scoring debería ser una matriz **función x dominio** (responder, juzgar, agregar, planificar x código, matemática, escritura...), no un score único por modelo. Con 27 modelos y 1.7M de evaluaciones: asignar el óptimo por función-dominio supera consistentemente a cualquier configuración homogénea (AgentVerse en AIME-2024: 20% → 50% mezclando razonadores y chatbots).

### 2.3 La economía interna tiene literatura y precio de mercado

- BAMAS demuestra que "elegir el conjunto de modelos bajo presupuesto" es un problema de optimización con solución conocida (ILP costo vs capacidad); `capabilities.py` ya tiene los scores, solo falta la columna de precio real por proveedor.
- Azure cobra el routing a $0.14/M tokens de input: el propio `dispatch.py` puede modelarse como un departamento con costo (en dinero ~cero si clasifica qwen local, pero no en latencia/energía).
- La métrica IBPC de AutoMix (beneficio incremental por unidad de costo) es la unidad contable natural: cada escalado debe justificar su delta de costo con delta de calidad.
- El límite de handoffs (LangGraph) es la versión en pasos del presupuesto en dólares: cada rebote entre departamentos descuenta, con circuit breaker al agotarse. MAST muestra que casi la mitad de los fallos multi-agente (repetición de pasos, no terminar) los atrapa gratis un supervisor con contador de pasos y tope de gasto — sin LLM.

### 2.4 Mecánica de router robable de los gateways comerciales

De **OpenRouter** ([provider routing](https://openrouter.ai/docs/features/provider-routing)):
- Ponderación **cuadrado-inverso del precio**: un proveedor a $1/M es 9x más probable que uno a $3/M. Una línea de código que da diversidad de proveedores sin renunciar al sesgo por barato — mejor que un argmin determinista que siempre pega al mismo modelo.
- Health-check trivial: priorizar proveedores sin fallos en los últimos 30 segundos (timestamp del último error por proveedor).
- Depriorizar sin excluir por latencia: encaja con Ollama local (lento pero nunca descartado).
- `cost_tier` como **banda** (no techo): cada departamento compra en su banda presupuestaria.
- Session stickiness y degradación elegante a un default fijo: el router nunca es causa de fallo.

De **LiteLLM** ([docs de routing](https://docs.litellm.ai/docs/routing)) — open source, embebible como librería:
- Cooldowns (`allowed_fails`/`cooldown_time`): un proveedor que falla sale de rotación N segundos — crítico con cuotas de suscripción Claude/Codex.
- Pre-call checks: no mandar 40k tokens a un modelo de 32k de contexto.
- `lowest_latency_buffer` para no saturar siempre al endpoint más rápido.
- Su `litellm_model_cost_map` es una tabla de precios reales mantenida, importable como fuente de precios para la economía.

### 2.5 Testear el router sin gastar

RouterBench da la metodología: loguear cada dispatch como (query, modelo elegido, respuesta, costo, resultado) y construir un mini-RouterBench propio. Cualquier cambio a `dispatch.py` o `capabilities.py` se reproduce offline contra ese log antes de desplegarlo. Dos evals mínimos: **routing_accuracy** (consultas etiquetadas con el destino correcto, escrito ANTES de complejizar el router) y el **Zero Router** como baseline de honestidad. Ese mismo log es, sin costo extra, el dataset de entrenamiento estilo Not Diamond / RouteLLM para cuando el scoring estático quiera evolucionar a clasificador entrenado — y RouteLLM demuestra que los routers entrenados transfieren a pares de modelos nuevos, importante porque el catálogo de Calipso cambia.

Señal de mercado a favor de la simplicidad: Martian, el pionero del routing por predicción sofisticada (interpretabilidad mecanicista para predecir comportamiento sin ejecutar, [TechCrunch](https://techcrunch.com/2023/11/15/martians-tool-automatically-switches-between-llms-to-reduce-costs/)), abandonó el negocio de routing hacia 2026; los gateways simples (OpenRouter, LiteLLM) prosperan. Heurísticas simples + precios reales rinden más que un predictor sofisticado.

---

## 3. La tesis de la diversidad de proveedores: evidencia y matices

Tesis de Pedro: combinar proveedores da diversidad de entrenamiento Y de políticas/reglas. La literatura la respalda con números, y le pone tres condiciones.

### 3.1 Evidencia a favor

1. **Jueces diversos baratos ganan al juez caro único** — PoLL (Cohere, [arXiv 2404.18796](https://arxiv.org/abs/2404.18796)): un panel de 3 modelos pequeños de familias disjuntas supera a GPT-4 como juez único en correlación con humanos, con >7x menos costo. Mecanismo: los sesgos de familias distintas no están correlacionados y se cancelan al agregar. La opción barata y diversa no es un compromiso: gana.
2. **El sesgo de auto-preferencia es real y crece con la capacidad** — Panickssery et al. (NeurIPS 2024, [arXiv 2404.13076](https://arxiv.org/abs/2404.13076)): los LLM reconocen sus propias salidas y las favorecen, con correlación lineal entre auto-reconocimiento y sesgo (evidencia causal vía fine-tuning). Regla de arquitectura: nunca dejar que un modelo (ni su familia) verifique salidas propias.
3. **El mecanismo es la distribución de entrenamiento, no el narcisismo de instancia** — Wataoka et al. ([arXiv 2410.21819](https://arxiv.org/abs/2410.21819)): los jueces puntúan más alto los textos de baja perplexity (parecidos a su distribución de entrenamiento) sin importar quién los generó. Consecuencia fina: dos modelos occidentales entrenados con datos similares comparten sesgo aunque sean de empresas distintas; Claude + Qwen/DeepSeek es diversidad real, dos americanos parecidos mucho menos.
4. **La diversidad escala donde las copias saturan** — [arXiv 2602.03794](https://arxiv.org/abs/2602.03794): 2 agentes diversos igualan o superan a 16 homogéneos; mezcla heterogénea hasta +14.28% absoluto sobre el mejor modelo individual con N=8. Argumento económico puro: gastar en un segundo modelo distinto compra más rendimiento que 8 llamadas al mismo. Su métrica K* (canales de información efectivos, sin etiquetas) permitiría no pagar dos veces por proveedores redundantes entre sí.
5. **El debate heterogéneo supera al homogéneo** — Du et al. ([arXiv 2305.14325](https://arxiv.org/abs/2305.14325)) + A-HMAD ([Springer 2025](https://link.springer.com/article/10.1007/s44443-025-00353-3)): factualidad en biografías 60% (un LLM) → 74% (debate homogéneo) → 80.6% (debate heterogéneo adaptativo). Además resiliencia: la mezcla absorbe a un agente degradado o de mala fe; el sistema homogéneo no tiene con qué contrastarlo.
6. **Las políticas de censura son complementarias, no redundantes** — [arXiv 2504.03803](https://arxiv.org/abs/2504.03803), 14 modelos de EEUU/Europa, China y Rusia en 6 idiomas: todos censuran, pero cada uno hacia su audiencia doméstica (DeepSeek/Qwen rehúsan más sobre figuras chinas; GigaChat/Yandex sobre rusas; Gemini con filtros más sobre EEUU). Los puntos ciegos apenas se solapan: mezclar esferas da cobertura casi completa. Para el router, un refusal detectado es señal barata y accionable de **reenrutar a un proveedor de otra esfera**, en vez de reintentar o escalar en precio.
7. **Colaboratividad de MoA**: un LLM genera mejores respuestas viendo salidas de otros modelos incluso peores que él — la diversidad aporta valor medible más allá de la redundancia.

### 3.2 Matices que acotan la tesis

1. **La diversidad solo paga entre modelos de calidad comparable** — Self-MoA ([arXiv 2502.00674](https://arxiv.org/abs/2502.00674)): mezclar débiles con fuertes degrada el resultado por debajo del mejor modelo solo; agregar muestras del mejor modelo gana en muchos escenarios. El guardarraíl es exactamente el umbral de aptitud de `capabilities.py`: **diversidad por encima del umbral sí; diversidad en lugar del umbral, no**. Nunca rellenar un ensemble con un modelo débil solo porque es barato o distinto.
2. **La diversidad tiene precio multiplicativo**: MoA y LLM-Blender multiplican llamadas por el número de agentes. La economía debe cobrarlo: ensembles solo en queries marcadas de alto valor, y la variante Lite (2 capas) captura el grueso de la ganancia.
3. **Tercera dimensión: jurisdicción del hosting** — la política de privacidad de DeepSeek primera parte declara almacenamiento en China y uso de inputs para entrenar ([análisis](https://lumichats.com/blog/free-chinese-ai-deepseek-kimi-privacy-risk-2026)); pero los mismos pesos abiertos se sirven desde infraestructura occidental, a veces más barato que la primera parte (GLM-5.2: $0.49/$1.54 vía OpenRouter vs $1.40/$4.40 de Zhipu). Se conserva la diversidad de entrenamiento sin mandar datos a China: un flag `sensible` en el request cambia de host sin cambiar de modelo.

---

## 4. Modelos chinos: precios, capacidades y qué corre local en 12GB

### 4.1 Cuadro de precios y aptitud (agosto 2026, USD por millón de tokens, primera parte salvo indicación)

| Modelo | Input / Output | Contexto | Pesos | Señales de aptitud | Nota |
|---|---|---|---|---|---|
| DeepSeek V4-Flash-0731 (284B/13B MoE) | $0.22 / $0.66 off-peak (cache hit $0.007/M); x2 en pico | 1M | MIT, 166.9 GB | Razonamiento integrado (no hubo R2 separado) | Ventanas peak/off-peak por franja UTC ([fuente](https://codersera.com/blog/deepseek-v4-complete-guide-2026/)) |
| DeepSeek V4-Pro-0813 (1.6T/49B) | ~$1.98/M output off-peak | 1M | MIT | SWE-bench Verified 96.4% en harness Vals (80.6% en llm-stats: ojo al harness); LiveCodeBench 93.5; Codeforces ELO 3206; SWE-bench Pro 55.4% | 2do detrás de Opus 5 (97.0) en Verified |
| Kimi K2.5 / K2.6 / K2.7 Code (Moonshot) | $0.60/$3.00; $0.95/$4.00 (cache hit $0.19/M en K2.7) | 256K | — | K2.6 empata a GPT-5.5 en SWE-bench Pro (58.6%); HLE con herramientas 54.0; Terminal-Bench 2.0: 66.7 | Batch API al 60% de tarifa ([pricing](https://benchlm.ai/moonshot/api-pricing)) |
| Kimi K3 (2.8T) | $3.00 / $15.00 (cache hit $0.30/M) | 1M | Publicados pero inhosteables para individuos | Apuesta premium de razonamiento largo | Batch excluido |
| GLM-5.2 (Zhipu, 753B/~40B) | $1.40/$4.40 primera parte; **$0.49/$1.54 vía OpenRouter** | 1M | Abiertos | SWE-bench Pro 62.1% (> GPT-5.5 58.6%); Terminal-Bench 2.1: 81.0 | Mismo peso, precio distinto por host ([fuente](https://www.morphllm.com/glm-5-2)) |
| GLM-5.3 | = API 5.2; hoy solo vía GLM Coding Plan (suscripción flat) | — | — | — | Mismo patrón "suscripción > API" de Calipso |
| Qwen3.8-Max (Alibaba) | $2.00 / $6.00 (cache $0.25/M) | — | Prometidos, aún cerrados | OSWorld-Verified 86.1, por delante de Claude Fable 5 (85.0) y GPT-5.6 (83.2) | Ya no compite por precio sino por tope de aptitud agéntica ([fuente](https://openrouter.ai/qwen/qwen3.8-max)) |
| Qwen3-Max (gen previa) | $0.86 / $3.44 | 262K | — | — | Alternativa barata dentro de la familia |
| MiniMax M3 (428B/23B MoE) | $0.30 / $1.20 (hasta 512K input; x2 encima) | 1M | Abiertos | SWE-bench Pro 59.0% (> GPT-5.5); ~80.5% Verified; multimodal texto/imagen/video | **Mejor ratio precio/aptitud del cuadro** ([fuente](https://openrouter.ai/minimax/minimax-m3)) |
| MiniMax M2.7 | $0.30 / $1.20 | 205K | — | ~50 en Intelligence Index de Artificial Analysis | — |

Lectura de mercado ([Dealroom](https://dealroom.co/news/136199-inside-chinas-ai-ecosystem-beyond-deepseek-zhipu-minimax-moonshot-byteda/)): la brecha de benchmarks en código se cerró (GLM-5.2 y MiniMax M3 sobre GPT-5.5 en SWE-bench Pro), la de precio no — input frontier occidental típicamente 5-15x más caro. Los occidentales conservan su prima en el último 5% de SWE-bench Pro y en consistencia en tareas muy largas (Opus 4.7: 64.3% Pro). El líder de precio/aptitud cambia cada 4-6 semanas: los precios de la economía interna necesitan revisión mensual. Para calibrar umbrales usar SWE-bench Pro, que separa mejor que Verified (ya saturado en 80-97%).

### 4.2 Local en 12GB (ROG Ally): "open weights" ya no implica "ejecutable"

La frontera abierta china NO cabe en el Ally: V4-Flash pesa 166.9 GB incluso en FP4+FP8 mixto; GLM-5.2 son 753B; M3, 428B; K3, 2.8T. Son dos atributos separados que la economía debe modelar por separado: pesos abiertos (hosteable por terceros, precio por host) vs ejecutable localmente (costo cero en dólares).

Techo práctico en 12GB ([fuente](https://www.promptquorum.com/local-llms)):
- **qwen3:14b Q4_K_M** (~9 GB, 20-40 tok/s) — el candidato para subir el escalón Ollama desde qwen2.5.
- **qwen3:8b Q4_K_M** (40+ tok/s) — si la RAM compartida del Ally aprieta con el sistema encendido.
- Q4_K_M reduce ~75% la memoria vs FP16 con pérdida menor. DSpark (decodificación especulativa de DeepSeek) no aplica: exige cargar el modelo base.
- A vigilar: el Qwen3.8-27B prometido por Alibaba (~15-16 GB en Q4, fuera de 12GB, pero el sucesor natural si hay ampliación de hardware).

---

## 5. Recomendaciones para el spec de mezcla multi-proveedor (en orden de impacto)

1. **Cascada verificada sobre el escalón local (AutoMix + FrugalGPT), sin entrenar nada.** Qwen local responde primero; un prompt de auto-verificación few-shot extrae confianza; `dispatch.py` solo paga API si no supera el umbral. Es la palanca de ahorro más grande con la fricción más baja (>50% de reducción reportada). La señal es ruidosa: empezar con umbral y márgenes conservadores, no con POMDP. El umbral es la perilla presupuestaria por departamento (FrugalGPT: se aprende contra el presupuesto, no se fija a mano). Referencia de éxito de RouteLLM: resolver ~75-85% de requests en local/barato sin pérdida perceptible.

2. **Loguear todo dispatch y construir el mini-RouterBench propio.** Registrar (query, candidatos, elegido, costo, resultado, ¿Pedro reintentó?) habilita tres cosas: replay offline de cualquier cambio al router sin gastar, el eval de routing_accuracy con baseline Zero Router, y el dataset gratis para entrenar después un router estilo RouteLLM/Not Diamond. Escribir el eval antes de complejizar el router.

3. **Añadir el escalón "API china barata" con precios por host, y actualizar el local.** MiniMax M3 ($0.30/$1.20, 59% SWE-bench Pro, además vision/video que qwen local no cubre) y DeepSeek V4-Flash ($0.22 off-peak, cache hit $0.007/M) como defaults de alta aptitud; GLM-5.2 vía OpenRouter ($0.49/$1.54) antes que primera parte. Subir Ollama a qwen3:14b (o 8b). Modelar precio por proveedor-de-hosting, no por modelo; importar el `litellm_model_cost_map` como fuente de precios; revisar mensualmente. La ventana off-peak de DeepSeek y el batch al 60% de Kimi son tarifas diferenciadas que la economía puede ofrecer a los departamentos: mitad de precio a cambio de latencia.

4. **Reformular `capabilities.py` como brecha esperada y matriz función x dominio.** La pregunta correcta es "cuánto pierdo por no usar el modelo caro aquí" (Hybrid LLM); escalar solo cuando la brecha justifica el precio. Scoring por función (responder, juzgar, agregar, planificar) x dominio (X-MAS), calibrado con SWE-bench Pro para código. Las etiquetas blandas se generan gratis muestreando en Ollama.

5. **Capa de fiabilidad estilo LiteLLM/OpenRouter en `dispatch.py`.** Cooldowns por proveedor (crítico con cuotas de suscripción), pre-call check de context window, health-check de últimos 30s, degradación elegante a default fijo (el router nunca es causa de fallo), y ponderación cuadrado-inverso del precio en vez de argmin — diversidad de proveedores de fábrica sin renunciar al sesgo por barato.

6. **Regla anti-auto-juicio + verificador con presupuesto propio.** Ningún modelo (ni su familia) verifica salidas propias (sesgo medible y creciente, Panickssery/Wataoka): si Claude genera, verifica un chino o el local, y viceversa. La verificación es la intervención con mejor retorno medido (+15.6%, MAST) y la excepción multi-agente que siempre funciona (Anthropic): merece línea de presupuesto propia. Para scoring/evaluación, jurado PoLL de 3 familias disjuntas baratas en vez de un juez frontier. Un refusal detectado reenruta a otra esfera política, no escala en precio.

7. **Escalón intermedio "qwen x N con votación", precio en latencia.** Para tareas verificables (matemática, código con tests) donde el local flaquea, N muestras + voto por mayoría es un escalón real entre single-shot local y API paga, con costo cero en dólares (More Agents: 13B con 40 muestras supera al 70B). El router lo ofrece como opción con precio en latencia/batería.

8. **Guardarraíles económicos de orquestación.** Presupuesto por departamento con circuit breaker; contador de pasos y límite de handoffs que descuentan del presupuesto (atrapa gratis casi la mitad de los fallos de MAST); criterio de admisión de Anthropic antes de multi-agente (frontera de contexto, paralelismo real, o 20+ herramientas — si no, un solo modelo bien prompteado); routing condicional explícito propio, nunca delegado a un framework (lección CrewAI); paralelizar solo departamentos de lectura, un único escritor (Cognition); reservar MoA-Lite/ensembles para queries de alto valor y solo entre modelos que superen el umbral de aptitud (Self-MoA: diversidad por encima del umbral, nunca en lugar del umbral).

9. **Flag de sensibilidad = dimensión de jurisdicción.** Requests con datos personales van a re-hosting US/EU de los mismos pesos chinos (o local); las no sensibles pueden usar primera parte china más barata con off-peak. Cambia el host, no el modelo: se conserva la diversidad de entrenamiento sin ceder los datos.

---

## Fuentes principales

Papers: [FrugalGPT 2305.05176](https://arxiv.org/abs/2305.05176) · [RouteLLM 2406.18665](https://arxiv.org/abs/2406.18665) · [Hybrid LLM 2404.14618](https://arxiv.org/abs/2404.14618) · [AutoMix 2310.12963](https://arxiv.org/abs/2310.12963) · [MoA 2406.04692](https://arxiv.org/abs/2406.04692) · [LLM-Blender 2306.02561](https://arxiv.org/abs/2306.02561) · [RouterBench 2403.12031](https://arxiv.org/abs/2403.12031) · [More Agents 2402.05120](https://arxiv.org/abs/2402.05120) · [MAST 2503.13657](https://arxiv.org/abs/2503.13657) · [BAMAS 2511.21572](https://arxiv.org/pdf/2511.21572) · [PoLL 2404.18796](https://arxiv.org/abs/2404.18796) · [Self-recognition 2404.13076](https://arxiv.org/abs/2404.13076) · [Self-preference 2410.21819](https://arxiv.org/abs/2410.21819) · [X-MAS 2505.16997](https://arxiv.org/html/2505.16997) · [Diversity scaling 2602.03794](https://arxiv.org/abs/2602.03794) · [Multiagent debate 2305.14325](https://arxiv.org/abs/2305.14325) · [A-HMAD](https://link.springer.com/article/10.1007/s44443-025-00353-3) · [Censura 2504.03803](https://arxiv.org/abs/2504.03803) · [Self-MoA 2502.00674](https://arxiv.org/abs/2502.00674)

Industria: [Anthropic multi-agent](https://www.anthropic.com/engineering/built-multi-agent-research-system) · [Anthropic when-to-multi-agent](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) · [Cognition](https://cognition.com/blog/dont-build-multi-agents) · [CrewAI fail](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/) · [LangGraph supervisor/swarm](https://focused.io/lab/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture) · [OpenRouter Auto Router](https://openrouter.ai/docs/guides/routing/routers/auto-router) · [OpenRouter provider routing](https://openrouter.ai/docs/features/provider-routing) · [LiteLLM routing](https://docs.litellm.ai/docs/routing) · [Not Diamond](https://docs.notdiamond.ai/docs/router-training-quickstart) · [Martian/TechCrunch](https://techcrunch.com/2023/11/15/martians-tool-automatically-switches-between-llms-to-reduce-costs/) · [Azure Model Router](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router) · [RouteLLM GitHub](https://github.com/lm-sys/routellm)

Modelos chinos: [DeepSeek V4 guía](https://codersera.com/blog/deepseek-v4-complete-guide-2026/) · [Moonshot pricing](https://benchlm.ai/moonshot/api-pricing) · [GLM-5.2](https://www.morphllm.com/glm-5-2) · [Qwen3.8-Max](https://openrouter.ai/qwen/qwen3.8-max) · [MiniMax M3](https://openrouter.ai/minimax/minimax-m3) · [Local en 12GB](https://www.promptquorum.com/local-llms) · [Privacidad China](https://lumichats.com/blog/free-chinese-ai-deepseek-kimi-privacy-risk-2026) · [Dealroom ecosistema chino](https://dealroom.co/news/136199-inside-chinas-ai-ecosystem-beyond-deepseek-zhipu-minimax-moonshot-byteda/)
