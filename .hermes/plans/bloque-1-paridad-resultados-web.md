# Bloque 1 — Paridad de resultados web

## Alcance autorizado

Implementar Logro Diseño, tolerancias firmadas y coherencia de resultados en web/API/core. Preservar la API legacy, Streamlit, Electron y CLI. No hacer commit, push ni despliegue. Conservar los dos cambios preexistentes de anotaciones dH y su test.

## Decisiones

- Mantener el criterio actual de aprobación por perfil: el cambio de peor estado a puntaje >=70 requiere decisión explícita. Identificar el criterio actual en las etiquetas; no confundirlo con Logro Diseño.
- Logro Diseño es una métrica distinta del score geotécnico: reutilizar el cálculo existente de core (cresta 40, pata 30, berma 30 y crédito parcial).
- Ausencia de datos evaluables se representa como nulo/SIN DATOS, nunca cero medido ni cumplimiento.
- Filtros: AND entre sector, sección, cota y banco; OR dentro de cada dimensión; lista vacía significa todos; sector vacío es una identidad válida.

## Entregas cortas delegadas

1. API de tolerancias crest_toe_deviation: defaults, edición parcial, validación, persistencia y aislamiento por sesión.
2. Helper compartido de filtros, controles accesibles y tabla: sector/nivel/crestas/patas y filtro de banco.
3. Helper core y endpoint por sesión para Logro Diseño global, por elemento y por sector.
4. Adaptación de tipos y formulario de tolerancias web; traducciones y pruebas.
5. Integración de filtros y Logro Diseño en dashboard; traducciones y pruebas de estados sin datos/error.
6. Histogramas de altura, ángulo, cresta, pata y berma con tolerancias vigentes, asimétricas y umbral mínimo donde corresponda.
7. Completar columnas de derrame/berma efectiva a partir de datos reales disponibles y revisión agrupada por nivel, sin inventar magnitudes.
8. Verificación integrada y dos revisiones independientes de solo lectura.

Cada tarea tiene propiedad de archivos explícita. No ejecutar agentes que editen el mismo archivo simultáneamente. Cada cambio funcional se desarrolla en ciclos cortos de prueba fallida observada, implementación mínima y prueba aprobada.

## Criterios de aceptación

- GET/PUT settings conserva tolerancias nuevas y existentes, incluso para sesiones antiguas; cero/asimetría válidos y negativos/no finitos rechazados.
- Resumen de Logro Diseño coincide con core y conserva denominadores por elemento, crédito parcial y ausencia de datos; no importa UI desde core/API.
- Resumen, tabla y plano usan el mismo subconjunto filtrado; las exportaciones se abordarán en su bloque posterior sin afirmar que ya aplican todos estos filtros.
- Gráficos no usan bandas constantes que contradigan settings; berma utiliza mínimo, no banda simétrica.
- Tabla presenta sector, nivel, derrame, berma efectiva y desviaciones firmadas con unidades; los datos inexistentes permanecen nulos.
- Se conserva la identidad de bancos y las filas MISSING/EXTRA; no se altera matching ni geometría.
- UI en español con traducciones en español/inglés, tokens de tema y controles accesibles.
- Se mantiene explícita la diferencia entre score, estado de tolerancia y Logro Diseño.

## Verificación

- Pruebas focalizadas RED/GREEN por entrega y suites combinadas al integrar.
- Frontend: cobertura completa, tsc -b, ESLint y build.
- Backend: suite sin OpenBlast y pipeline en un entorno de datos aislado; documentar incompatibilidades reales y no ocultar fallos.
- Smoke de navegador aislado con datos sintéticos y API real: editar tolerancias, filtrar y revisar tabla, tarjetas y histogramas. No usar la sesión real del usuario.
- Revisar git diff --check, alcance del diff y conservación de cambios preexistentes.
- Dos revisores independientes: cumplimiento y calidad/seguridad. Resolver bloqueantes y repetir verificaciones afectadas.

## Estado

Entregas 1–7 implementadas e integradas localmente. Se preservan los cambios previos de dH, Streamlit y el criterio de peor estado por perfil. Sin commit, push ni despliegue.

Verificación del coordinador: frontend 585/585 en 66 archivos; cobertura obligatoria 100%; `tsc -b --force`, ESLint y build con PWA aprobados. Backend 2487/8 omitidas/11 advertencias aprobado también en la repetición final; pipeline sintético con Excel/Word aprobado. Dos revisiones independientes reportaron PASS en sus alcances.

Smoke corregido aprobado: 21/21 comprobaciones con API real y superficies sintéticas procesadas; repetición personal del coordinador y 6/6 comprobaciones adicionales de interacción real con filtro sin sector y escritura de un par distinto de tolerancias, con lectura posterior. Se inspeccionaron las capturas. Evidencia preservada en `data/qa-block1-final-evidence/`, ignorada por Git, con manifiesto de hashes.

Bloque 1 completado dentro del alcance acordado. La navegación del smoke es programática; no se certifican carga manual integral, archivos reales del usuario, suite completa de Playwright, PWA offline ni despliegue. Los demás bloques del plan de paridad siguen pendientes. Límites no bloqueantes del borrador local y de settings heredados registrados en `docs/HANDOFF.md`.
