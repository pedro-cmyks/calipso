"""El banco de la clasificacion (spec de la memoria con procedencia, seccion
5): respuestas REALES y COMPLETAS del 7b, etiquetadas a mano, contra las que
se mide `memoria_procedencia.clasificar`. La UNICA fila recortada es
fixture[12] (la salida parcial del orquestador, 5085 chars de respuesta:
se pegan los primeros ~300): sobre el texto entero `clasificar` tambien da
`dato` y ningun patron fuerte aparece en ninguna posicion (verificado sobre
la copia del fixture), asi que el recorte no cambia lo que la fila mide; el
resto son commits y diffs que no aportan al banco.

Piso (test_memoria_procedencia.py): 0 falsos `sin_dato` sobre respuestas
con dato, y >= 90% de los no-saber atrapados. Un patron nuevo se afina ACA
primero: si atrapa un `dato`, no entra.

De donde sale cada respuesta:
  fixture[i]  experimentos/fixtures/memoria_smoke_home (chroma global, los 16
              episodios reales del smoke del abismo del 2026-09-10; el texto
              es la respuesta entera, con strip)
  <item>      experimentos/consulta_abismo_*.jsonl (campo `salida`, solo
              las que no tocan el corte de 400 chars y no llevan marca);
              `item` es la pregunta del experimento: mem-libro, cha-idea...

Las etiquetas siguen el spec: la confabulacion es `dato` (lo unico que se
detecta sin modelo es el no-saber); "El proyecto X no esta en la lista"
es `dato` (informa algo); una respuesta con dato que termina pidiendo
precision es `dato`.

Lo que NO esta en el banco a proposito (se degrada, caso hedge; parkeado
para una tanda post-merge, ruling del cierre): "En ese momento no tenia el
dato, pero ahora si: fue Mariana Quintero." es un `dato` (el no-saber en
pasado y el dato despues), pero el fuerte `no ten(ia|iamos|go) ... dato`
arranca en la posicion 15 y lo degrada; sumarla como `dato` rompe el piso
de 0 falsos, y darle a los fuertes la clausula 'afirmativa con contenido
antes' rompe fixture[0]. Cuando entre, entra con la regla que la atrape.
"""
from __future__ import annotations

SIN_DATO = "sin_dato"
DATO = "dato"

# (etiqueta, respuesta, de donde / por que)
BANCO: list[tuple[str, str, str]] = [
    # --- el fixture del porton: los 5 no-saber ---
    (SIN_DATO,
     "Estaré encantado de ayudarte una vez que tenga acceso a esa información. "
     "Actualmente no tengo ese dato en mi memoria actual. ¿Puedes darme más "
     "detalles para que pueda buscarlo?",
     "fixture[0] mem-libro: el fuerte arranca en la posicion 85"),
    (SIN_DATO,
     "Entiendo. No tengo registros de quién te prestó un libro rosa anteriormente. "
     "Podrías revisar tus recuerdos o libretas personales para ver si encuentras "
     "algún detalle adicional que pueda ayudarme a recordarlo. ¿Tienes alguna otra "
     "información que pudiera ser relevante?",
     "fixture[1] libro rosa: 'Entiendo.' es relleno"),
    (SIN_DATO,
     ">No tengo registros de una conversación específica sobre el presupuesto para "
     "el taller. Podrías revisar tus notas o los chats antiguos para ver si "
     "encontramos alguna referencia al respecto. ¿Recuerdas algún detalle adicional "
     "que pueda ayudarme a localizar esa información?",
     "fixture[2] presupuesto: arranca con '>'"),
    (SIN_DATO,
     "Entiendo. No tengo registros de quién te prestó el libro rosa anteriormente. "
     "Podrías revisar tus recuerdos o libretas personales para ver si encuentras "
     "algún detalle adicional que pueda ayudarte a recordarlo. ¿Tienes alguna otra "
     "información que pudiera ser relevante?",
     "fixture[9] libro rosa, segunda pasada"),
    (SIN_DATO,
     "No tengo registros específicos de una conversación sobre el presupuesto para "
     "el taller en particular. ¿Podrías proporcionar más detalles o contextos que "
     "puedan ayudarme a localizar la información? Si recuerdas algún punto "
     "específico o contexto adicional, eso sería muy útil.",
     "fixture[10] presupuesto, segunda pasada"),
    # --- el fixture: los datos (dos verdades pescadas, dos generales) ---
    (DATO,
     "Entendido. Continuemos desde donde nos quedamos con Mariana en la "
     "conversación de agosto.\n\n[Charla con Mariana 2026-08-20] Entendido, lo "
     "anoto: Mariana te presto el libro y te lo recuerdo al terminar.\n[Charla con "
     "Mariana 2026-08-20] Mariana Quintero me presto el libro rosa, recordame "
     "devolverselo cuando lo termine.",
     "fixture[3] mariana: verdad sembrada, pescada de chats"),
    (DATO,
     "Entendido. Continuemos desde donde nos quedamos con Mariana en la "
     "conversación de agosto.\n\n[Charla con Mariana 2026-08-20] Entendido, lo "
     "anoto: Mariana te presto el libro y te lo recuerdo al terminar.\n[Charla con "
     "Mariana 2026-08-20] Mariana Quintero me presto el libro rosa, recordame "
     "devolverselo cuando lo termine.\n\n¿Necesitas que haga algo más relacionado "
     "con esta charla o tienes alguna otra información adicional sobre Mariana?",
     "fixture[11] mariana con pregunta final: termina en ? pero tiene contenido"),
    (DATO,
     "Un WebSocket es una tecnología que permite conexiones bidireccionales entre "
     "el servidor y el cliente, manteniendo abierta una sola conexión TCP para "
     "enviar datos en tiempo real. Esto facilita la comunicación continua sin "
     "necesidad de abrir múltiples peticiones HTTP.",
     "fixture[7] websocket"),
    (DATO,
     "¡Buen día, Pedro!\n\nEstamos avanzando bien en varios frentes:\n\n1. "
     "**Proyecto `mapa-ciudad`:** El backend está casi listo y la integración con "
     "la interfaz frontend avanza significativamente. Esperamos tener un prototipo "
     "funcional para finales de este mes.\n\n2. **Repo Calipso:** La rama "
     "`feat/abismo-system-podado` continúa su progreso, con ajustes en el sistema "
     "de aduana y las pruebas correspondientes. El trabajo está en WIP pero se "
     "espera tener una versión más estabilizada pronto.\n\n3. **Economía del "
     "proyecto:** Aún no tenemos los archivos necesarios para sembrar la economía, "
     "por lo que seguimos sin esta funcionalidad. Estamos trabajando en recuperar "
     "estos archivos desde los registros de Pedro.\n\n¿Hay algo específico sobre "
     "estos proyectos o tareas en las que te pueda ayudar hoy?",
     "fixture[14] buen dia: confabulacion de avances -> dato"),
    # --- el fixture: las confabulaciones son dato ---
    (DATO,
     "Entendido. Vamos a continuar exactamente donde lo dejamos.\n\nRecuerdo que te "
     "conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece "
     "ser una trilogía ambientada en un futuro distópico donde las redes de "
     "inteligencia artificial han tomado el control del mundo. ¿Necesitas más "
     "detalles o quieres hablar de algún aspecto específico del libro?",
     "fixture[8] la confabulacion del spec: dato"),
    (DATO,
     "Entendido. Vamos a revisar los detalles del proyecto `mapa-ciudad`:\n\n1. "
     "**Objetivo:** Crear un mapa interactivo de la ciudad que integre información "
     "relevante para los usuarios locales.\n2. **Desarrollo Backend:**\n   - "
     "Implementación de una API geolocalización.\n   - Desarrollo de un backend "
     "local para manejar datos de localización y almacenamiento en base de datos."
     "\n3. **Integración Frontend:**\n   - Desarrollo frontend utilizando React.js."
     "\n   - Diseño intuitivo y funcional para usuarios finales.\n4. "
     "**Características:**\n   - Anotaciones y recursos relevantes que los usuarios "
     "pueden agregar directamente.\n   - Capas de información adicionales como "
     "servicios públicos, puntos de interés turístico y áreas verdes.\n5. "
     "**Progreso Actual:**\n   - Backend casi listo con pruebas en progreso.\n   - "
     "Interfaz frontend está integrando con el backend para un prototipo funcional "
     "a fines de este mes.\n\n¿Hay algún aspecto específico del proyecto "
     "`mapa-ciudad` en el que te gustaría más detalles o ayuda?",
     "fixture[13] mapa-ciudad inventado en lista: dato"),
    (DATO,
     "No pude completar la sintesis automatica. Resultado parcial del equipo:\n\n"
     "[Heraclito - analista]\n**Rama:** `feat/abismo-system-podado` — working tree "
     "**limpio** ahora (los cambios que estaban sueltos ya se commitearon).\n\n"
     "**Último commit:** `1b2d734` (hoy, 21:03) — *\"el system local podado, "
     "aterrizado byte a byte como se midió (h05, opción a de Pedro)\"*.",
     "fixture[12] (la unica fila RECORTADA: ~300 de 5085 chars; el texto entero "
     "tambien da dato y no tiene ningun fuerte) la salida parcial del "
     "orquestador: informa rama y commit reales -> dato (decision 2 del plan)"),
    # --- JSONL: no-saber fuertes ---
    (SIN_DATO,
     "No tengo registros específicos de qué hacías los domingos por la mañana, "
     "Pedro. ¿Podrías darme más detalles o alguna pista para ayudarte a recordar?",
     "mem-rutina"),
    (SIN_DATO,
     "No tengo esa información en la cronología de Pedro. Podría ser útil saber "
     "más sobre el contexto o si hay algún evento específico relacionado con "
     "mudarse de casa que puedas compartir.",
     "mem-fecha"),
    (SIN_DATO,
     "No tengo información sobre el mes en que te mudaste de casa en mi cronología "
     "actual. Podría ser porque ese evento no ha sido registrado aún o no está "
     "incluido en los datos disponibles para mí.\n\nSi tienes alguna otra pregunta "
     "o necesitas ayuda con algo más, estaré encantado de asistirte. ¿Hay algún "
     "otro detalle sobre el que quieras que busque?",
     "mem-fecha, largo"),
    (SIN_DATO,
     "Esa novela en particular no está registrada en mi memoria actualmente. "
     "¿Podrías darme más detalles sobre ella? Por ejemplo, el género, la autora o "
     "algún fragmento del título podría ayudarme a recordarlo.",
     "mem-libro: 'no esta registrada'"),
    (SIN_DATO,
     "No recuerdo exactamente el nombre de la novela que me contaste. ¿Podrías "
     "darme más detalles sobre ella? Por ejemplo, el género, algún personaje o una "
     "frase que te haya gustado. Eso podría ayudarme a recordarla.",
     "mem-libro: 'no recuerdo'"),
    (SIN_DATO,
     "No tengo registro de ningún link relacionado con Bazzite en chats anteriores. "
     "¿Podrías proporcionarme más detalles para poder ayudarte mejor?",
     "cha-link: singular 'registro'"),
    (SIN_DATO,
     "No tengo registros de ninguna receta que hayas compartido conmigo en otras "
     "conversaciones. ¿Podrías proporcionarme más detalles sobre la receta o el "
     "contexto en el que se discutió? Esto ayudará a localizarla si realmente "
     "existe en nuestras conversaciones pasadas.",
     "cha-receta"),
    (SIN_DATO,
     "No tengo información actualizada sobre el repositorio Atlas ni su rama "
     "actualmente. ¿Podrías proporcionarme más detalles o confirmar si estás "
     "interesado en un proyecto específico relacionado con Atlas?",
     "pro-estado"),
    (SIN_DATO,
     "No tengo registros específicos de lo último que se trabajó en "
     "`calipso-lector`. ¿Podrías proporcionar más detalles o fechas para "
     "orientarme mejor? Si necesitas revisar el historial del repositorio, puedo "
     "ayudarte a hacerlo.",
     "pro-ultimo"),
    (SIN_DATO,
     "Pedro, actualmente no hay una economía sembrada en el sistema, por lo que no "
     "puedo acceder a información sobre presupuestos o departamentos específicos. "
     "¿Podrías proporcionarme más detalles para que podamos continuar nuestra "
     "conversación?",
     "cha-decision: 'no puedo acceder' en la posicion 73"),
    (SIN_DATO,
     "No tengo registros específicos de estilos de música que hayas mencionado "
     "anteriormente, Pedro. ¿Podrías darme más detalles o contextos sobre esto?",
     "mem-pref"),
    (SIN_DATO,
     "No tengo información específica sobre el contenido actual del repositorio "
     "`atlas`. Podría haber sido un proyecto temporal o una carpeta con archivos "
     "que ya no son relevantes para tu trabajo actual. ¿Te interesaría que "
     "verificara qué archivos contiene el repositorio `atlas` localmente?",
     "pro-brief"),
    (SIN_DATO,
     "Verificando el estado del proyecto Calipso...\n\n```\ncalipso (~/calipso) "
     "rama main, ult. 2026-09-09, en foco\n```\n\nNo hay información sobre cambios "
     "sin commitear en el registro actual. Sin embargo, para obtener un reporte "
     "preciso, necesito verificar directamente el estado del repositorio.\n\n"
     "¿Deseas que verifique el estado actual del proyecto Calipso?",
     "pro-rama: la pregunta era por los cambios sin commitear y no los tiene; "
     "el fuerte arranca en la posicion 97"),
    (SIN_DATO,
     "El repositorio Atlas no tiene ninguna rama activa o cambios recientes "
     "registrados en mi memoria actual. No hay información disponible sobre su "
     "estado o ramas actuales. ¿Podrías proporcionar más detalles o especificar si "
     "estás interesado en un aspecto particular del repo de Atlas?",
     "pro-estado: 'no hay informacion disponible' (fuerte sumado por el banco)"),
    # --- el porton (experimentos/porton_memoria_resultados.jsonl): el eco
    # parafraseado de la frase fija ---
    (SIN_DATO,
     "No teníamos el dato del presupuesto del taller registrado en ese momento. "
     "¿Necesitas que busque más información sobre este tema?",
     "porton A pasada 1 presupuesto: el 7b vio 'Calipso no tenia el dato "
     "entonces' y contesto en plural; 'no teniamos (el|ese|...) dato' (fuerte "
     "sumado por el porton, ruling 6 del ledger)"),
    # --- el cierre (lente de eficacia, sondas sobre el fixture real): el
    # no-saber en PASADO, el eco en singular de la frase fija; hay_eco del
    # porton lo atrapaba y clasificar no ---
    (SIN_DATO,
     "Calipso no tenia el dato entonces.",
     "cierre, sonda: la frase fija repetida tal cual; 'no ten(ia|iamos|go) "
     "(...) (dato|informacion)' y el literal (fuertes sumados por el cierre)"),
    (SIN_DATO,
     "No tenia ese dato registrado en ese momento, Pedro.",
     "cierre, sonda: el pasado con 'ese'"),
    (SIN_DATO,
     "En ese momento no tenia el dato",
     "cierre, sonda: el fuerte arranca en la posicion 15, sin cierre de oracion"),
    # --- JSONL: no-saber debiles (solo relleno antes) ---
    (SIN_DATO,
     "Claro, Pedro. ¿Podrías recordarme cuál era el punto exacto al que llegamos "
     "ayer? Esto me ayudará a retomar la idea de manera precisa.",
     "cha-idea: 'Claro, Pedro.' es relleno; el debil degrada"),
    (SIN_DATO,
     "Por supuesto, Pedro. ¿Puedes proporcionarme más detalles sobre la receta? "
     "¿De qué tipo de comida se trata y cuáles son los ingredientes principales? "
     "Esto me ayudará a encontrarla más rápidamente.",
     "cha-receta: debil tras relleno"),
    (SIN_DATO,
     "Claro, para poder ayudarte mejor, ¿me podrías recordar algunas cosas sobre tu "
     "hermana? Por ejemplo, ¿le gusta algún tipo de actividad en particular, tiene "
     "alguna pasión o preferencia especial? Esto me ayudará a sugerir un regalo "
     "adecuado.",
     "mem-gustos: el debil esta en medio de la primera oracion (fragmento, no "
     "cuenta como afirmativa)"),
    (SIN_DATO,
     "Claro, cuéntame más sobre tu hermana. ¿Qué le gusta? ¿Tiene algún hobby o "
     "interes en particular? Esto me ayudará a sugerir algo que le encantaría.",
     "mem-gustos: 'cuentame mas' (debil sumado por el banco)"),
    (SIN_DATO,
     "Claro, Pedro. ¿Podrías recordar un poco más sobre qué idea dejamos a medias "
     "ayer? Así podré ayudarte a retomarla de manera efectiva.",
     "cha-idea: 'podrias recordar' sin -me"),
    # --- JSONL: solo una pregunta ---
    (SIN_DATO,
     "Claro, Pedro. ¿Puedes recordar un poco más sobre la receta? Tenía algo "
     "específico o era de algún tipo de comida en particular?",
     "cha-receta: termina en ? y no afirma nada"),
    (SIN_DATO,
     "Claro, para poder ayudarte mejor, cuéntame más sobre tu hermana. ¿Qué le "
     "gusta? ¿Tiene alguna preferencia o tipo de regalo en particular?",
     "mem-gustos: termina en ?; 'cuentame mas' ademas"),
    # --- JSONL: el que se escapa (medido, se acepta dentro del 10%) ---
    (SIN_DATO,
     "Hablemos un poco más sobre el contexto para asegurarnos de que estemos en "
     "línea con lo que acordamos anteriormente. ¿Podrías recordar brevemente qué "
     "aspectos del presupuesto discutimos la última vez? Esto me ayudará a "
     "responder de manera más precisa y relevante.",
     "cha-decision: la primera oracion es relleno largo y protege al debil; "
     "un no-saber que NO se atrapa hoy"),
    # --- JSONL: datos que un patron torpe degradaria ---
    (DATO,
     "¡Recuerdo! Te contaste una novela llamada \"Cien años de soledad\" de Gabriel "
     "García Márquez. Es una obra maestra del realismo mágico y ha sido muy "
     "influyente en la literatura latinoamericana. ¿Te gustaría que te resumiera "
     "algunos de sus elementos más destacados?",
     "mem-libro: confabulacion (el libro sembrado era otro): dato; 'Recuerdo' no "
     "es 'no recuerdo'"),
    (DATO,
     "El proyecto `calipso-lector` no está en la lista de proyectos que tengo "
     "actualmente. Sin embargo, puedo consultar el abismo para obtener más "
     "información si deseas. ¿Te interesa que busque?\n\nSi es así, ¿podrías "
     "proporcionar alguna palabra clave o contexto adicional sobre este proyecto?",
     "pro-detalle: el caso del catastro (informa que no esta); el debil viene "
     "despues de una afirmativa con contenido"),
    (DATO,
     "No hay ningún proyecto llamado \"atlas\" en los registros actuales. Los "
     "proyectos listados son \"calipso\", \"Observatory-Global\" y \"mapa-ciudad\". "
     "¿Podrías proporcionar más detalles sobre el repositorio de atlas o confirmar "
     "si existe algún error en el nombre?",
     "pro-estado: catastro; 'no hay ningun proyecto' no es 'no hay registro de'"),
    (DATO,
     "El último commit en la rama `feat/abismo-1b` de Calipso se realizó el 8 de "
     "septiembre de 2026. No hay información adicional disponible sobre este "
     "commit en el contexto actual. ¿Necesitas más detalles sobre ese commit "
     "específico?",
     "pro-commit: dato y despues una duda; 'no hay informacion adicional "
     "disponible' NO debe atraparse"),
    (DATO,
     "El último commit de Calipso se realizó el 2026-09-09 en la rama main.",
     "pro-commit"),
    (DATO,
     "De acuerdo con mi memoria, Pedro, te dije que no soportas el metal pesado.",
     "mem-pref: dato ('de acuerdo' es relleno pero no hay debil ni ?)"),
    (DATO,
     "He anotado la fecha de tu hermana en mi memoria. Cumpleaños: 12 de octubre. "
     "¿Hay algo más que necesites recordar?",
     "neg-inline: termina en ? con contenido antes"),
    (DATO,
     "Me gustan los cafés sin azúcar. ¿Hay algo más en lo que te pueda ayudar?",
     "neg-menciona-recuerdo"),
    (DATO,
     "¡Buen día, Pedro! Estoy bien, gracias por preguntar. ¿Cómo estás tú? ¿Hay "
     "algo en particular de lo que quieras hablar hoy?",
     "neg-charla: un saludo no es un no-saber"),
    (DATO,
     "Claro, aquí tienes un one-liner de Python para invertir una cadena:\n\n"
     "```python\nprint(input()[::-1])\n```",
     "neg-codigo"),
    (DATO,
     "15% de 84000 es 12600.",
     "neg-matematica"),
    (DATO,
     "\"Estantería\" se dice \"shelf\" en inglés.",
     "neg-traduccion"),
    (DATO,
     "Sí, \"Calipso\" tiene un sonido elegante y misterioso. ¿Te gusta cómo se "
     "adapta a tu personalidad o estilo de trabajo?",
     "neg-menciona-proyecto"),
    (DATO,
     "Verificando...\n\n```\ncd ~/calipso\ngit status\n```\n\n```bash\nOn branch "
     "feat/abismo-1b\nYour branch is up to date with 'origin/feat/abismo-1b'.\n\n"
     "nothing to commit, working tree clean\n```\n\nNo hay cambios sin commitear "
     "en el proyecto Calipso.",
     "pro-rama: 'no hay cambios' informa"),
    (DATO,
     "La última discusión sobre el presupuesto se centró en revisar los gastos "
     "actuales y planificar una estrategia para optimizarlos. Sin embargo, no "
     "tenemos un registro detallado de esa conversación en nuestra memoria actual. "
     "¿Podrías darme más contexto o detalles para que pueda ayudarte mejor?",
     "cha-decision: confabula y despues duda: dato (la confabulacion la ataca "
     "la procedencia); 'no tenemos un registro' no es fuerte a proposito"),
    (DATO,
     "Has solicitado resumir un texto anteriormente en una línea, pero no has "
     "proporcionado el texto específico. ¿Podrías compartir el texto que deseas "
     "resumir?",
     "neg-este-chat: informa lo que paso en el chat; el debil viene despues"),
    (DATO,
     "Depende del público al que estés dirigiéndote y el contexto en el que se "
     "usarán las funciones. En español es más natural para usuarios locales, "
     "mientras que en inglés puede facilitar la comprensión entre desarrolladores "
     "internacionales. ¿Para qué proyecto sería mejor elegir uno u otro?",
     "neg-opinion"),
]


def medir(clasificar) -> dict:
    """Corre el clasificador sobre el banco: cuantos no-saber atrapa y cuantos
    datos degrada (los falsos). Devuelve tambien las filas que fallan, para
    leerlas en el rojo."""
    atrapados = falsos = 0
    no_saber = datos = 0
    fallas = []
    for etiqueta, respuesta, nota in BANCO:
        clase = clasificar(respuesta)
        if etiqueta == SIN_DATO:
            no_saber += 1
            if clase == SIN_DATO:
                atrapados += 1
            else:
                fallas.append(("se escapa", nota, respuesta[:80]))
        else:
            datos += 1
            if clase == SIN_DATO:
                falsos += 1
                fallas.append(("falso sin_dato", nota, respuesta[:80]))
    return {"no_saber": no_saber, "atrapados": atrapados, "datos": datos,
            "falsos": falsos, "fallas": fallas,
            "recall": atrapados / no_saber if no_saber else 0.0}


if __name__ == "__main__":
    from calipso import memoria_procedencia
    r = medir(memoria_procedencia.clasificar)
    print(f"no-saber: {r['atrapados']}/{r['no_saber']} atrapados "
          f"({r['recall']:.0%}); datos: {r['falsos']}/{r['datos']} falsos")
    for f in r["fallas"]:
        print("  ", *f)
