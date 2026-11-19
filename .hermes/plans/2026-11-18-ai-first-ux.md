# Plan de mejoras AI-first · Conciliación Geotécnica

Base: rama `exterimental-UI` (`e5cc39e`) y evaluación visual de Astra 6.2. Meta: que el agente sugiera el siguiente paso apropiado sin desplazar las herramientas de análisis ni bloquear el trabajo manual.

| Etapa | Responsable | Cambios y condiciones de aceptación |
|---|---|---|
| 1. Compositor y carga (P1) | Luna A | Chat integrado con editor multilínea autoexpandible y fila de acciones separada. A 390 px se revisa el borrador completo; Enter envía en escritorio, Shift+Enter inserta una línea y la composición de teclado no dispara envíos; en móvil se puede usar el botón Enviar. Cargar Diseño o Topografía abre el cargador existente por rol, no carga ni analiza automáticamente. La primera carga no interrumpe el flujo móvil. |
| 2. Guía contextual (P1) | Luna A | Ofrecer una acción según el estado existente: superficie faltante, preparación de secciones/parámetros, procesamiento o resultados. Si el usuario eligió explícitamente un perfil, habilitar una pregunta contextual; si no, invitar a revisar incumplimientos. Las sugerencias llenan un borrador vacío sin enviar ni reemplazar texto escrito; la carga manual sigue disponible sin IA. |
| 3. Lectura de resultados (P2) | Luna B | Mejorar el encuadre inicial del plano solo cuando los datos dibujados aportan un foco válido; conservar extensión completa, escala, norte y controles. Distinguir cumplimiento con patrones en las líneas y su leyenda, sin reemplazar el color ni alterar estados. Rotular distancia y elevación en metros una vez en Perfiles. |
| 4. Integración y QA | Coordinación | Revisar el diff final, comprobar modelos de las sesiones, correr Vitest, TypeScript, lint y build. Abrir el producto a 390 y 1440 px. Verificar borrador largo, carga por rol con archivo real en sesión aislada, navegación manual, panel plegable y plano/perfiles. Registrar qué usa demo y qué usa datos reales. |

**Límites:** producto solo en `web/`. Sin modificar API, contratos, prompts del sistema, fórmulas, Streamlit ni carga manual. Sin modificar el chat flotante clásico. Sin commit, push ni despliegue. Conservar modificaciones previas de la rama. ES/EN para nuevos textos.

**Delegación:** agentes `gpt-6-luna` vía `openai-codex`, con paquetes separados para chat/flujo y resultados, más un paquete de QA. Se integraron las traducciones por bloques y se preservó el rediseño previo del chat.

## Resultado local

- El compositor integrado muestra un campo de 302 px de ancho a 390 × 844 px (antes: 125,3 px). Con fuentes cargadas, los 290 caracteres del borrador ocuparon 152 px de alto y se vieron completos, sin desbordar horizontalmente.
- En una sesión de prueba aislada se importaron Diseño y Topografía mediante sus CTA con dos STL de demostración: ambos devolvieron HTTP 200 y 3.600 vértices. Tras cada carga se mantuvo el borrador y, en móvil, el chat siguió visible. Se abrió el espacio de trabajo manual sin solicitudes de chat ni de análisis.
- Con la demo a 1440 × 960 px, «Revisar incumplimientos» preparó un borrador; los trazos coincidieron con la leyenda; el plano alternó entre zona evaluada y superficie completa; Perfiles mostró una única referencia de ejes en metros. En una copia de una sesión real con 85 registros se verificaron en solo lectura cuatro trazos y el score preexistente de 50,4/100.
- Suite web: 1.770 pruebas aprobadas; compilación TypeScript y build AI-first aprobados. Lint sin errores y con una advertencia preexistente en un test de tronadura. Sin commit, push ni despliegue.

## Validación en vivo con Strata

En el chat móvil de 390 × 844 px, `qwen3.8-flash-next-unsloth-ud-q4_k_xl` completó dos turnos en la misma conversación de una sesión aislada. Con la sesión vacía guio la carga de Diseño desde «Superficies» (3,7 s hasta el final de la respuesta); después de subir manualmente el STL de Diseño desde su botón, identificó que faltaba Topografía (5,8 s). En ambos turnos usó solo `get_workflow_state`, sin pedir aprobación ni ejecutar análisis. La API confirmó cero secciones y proceso en `idle` antes y después. La actividad arrancó plegada y se pudo abrir y cerrar con teclado. El botón «Cargar topografía» abrió el selector con el rol correcto, sin subir un archivo. Estas medidas corresponden a dos turnos observados, no a un benchmark. No hubo cambios de código en esta validación.
