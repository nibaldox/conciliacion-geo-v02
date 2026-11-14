# Rediseño de informes — estado al 14 de noviembre de 2026

Snapshot escrito al cerrar la ola 4. Los SHA de commits son estables; el resto describe el estado en ese momento.

## Ubicación y Git

- Worktree: `/home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02-informes`, rama `feat/report-redesign`, sin push.
- Checkout principal `../46-conciliacion-geo-v02` sigue en main `c229d6f`; solo contiene el plan sin seguimiento.
- Commits locales autorizados por el usuario, sobre `c229d6f`:
  - `6cbdc1e` rampa e inter-rampa; `e4eebaf` alerta de cara contra el diseño; `ba0833d` persistencia del mapa de calor; `1a2dd70` áreas y volúmenes; `d5d0e16` cotas nominales, filtros, modelo y dashboard.
  - `9ec1017` modelo del informe (deltas, puntaje de banco, advertencias de cota filtradas, textos compartidos); `15564fd` figuras y planta con relieve; `6e011de` páginas apaisadas de perfiles con miniplano y tabla al pie; `38586c3` exportaciones web por audiencia y enrutamiento API; `221fe65` selector de cotas por sector en el panel web.
- No hay autorización de push, PR ni merge.

## Qué entregan las exportaciones web

- PDF ejecutivo: tablero, comparación entre sectores (solo con 2 o más), análisis, excavación, mapa de calor y conclusiones; 4 a 5 páginas en la sesión real.
- Word técnico: índice visible, resumen, criterios, análisis, mapa de calor apaisado, perfiles 3×2 con miniplano y tabla al pie (obligatoria; más de 8 filas pasa a la página siguiente), anexos A (bancos), B (tronadura con bloque de auditoría) y C (excavación por sección). Un capítulo de perfiles por sector cuando hay varios.
- Excel analítico: Léeme, Resumen, Bancos, Secciones, Sector-Nivel, Tronadura y Pozos; funciona sin mallas.
- ZIP: perfiles recortados a la cota, planta, matriz y LEEME; respeta filtros.
- Todas las rutas usan el mismo `ReportData` filtrado. El mapa de calor persistido se reutiliza solo si su clave coincide y es de pared completa, restringido a las secciones y ventanas de cota del informe; nunca se recalcula al exportar.

## Verificación de cierre

- Revisión adversarial de dos lentes (`deleg_d711e145`) y correcciones W4; revisión independiente de cierre (`deleg_906f82f6`): lente de datos aprobada; el único pendiente de presentación (B9) quedó corregido con regresión.
- Gates finales sobre los bytes commiteados: backend 4.508 aprobadas, 7 omitidas, 0 fallas; `test_pipeline.py` OK; web 1.684/1.684, `tsc -b`, lint y build sin errores; cobertura del dominio de perfiles 100 %. Commits intermedios verificados en un worktree desprendido.
- Evidencia: `/home/xodla/.hermes/profiles/conciliacion/cache/scratch/report-redesign-w3/` (`W4-final/`, `W4-final-B9/`, `commits/`).

## Pendiente

- Revisión del usuario en el navegador con sus datos.
- Reprocesar la sesión real: los resultados guardados no coinciden con el código actual en 67 de 96 secciones; decisión del usuario pendiente.
- Limitaciones conocidas: la ruta multisector solo está probada con datos sintéticos (la sesión real tiene un sector); el caso «No construido» en páginas de perfiles está cubierto por pruebas, no por un render real.

## Plan y recursos

- Plan: `/home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02/.hermes/plans/2026-11-13_rediseno-informes-opcion-b.md` (decisiones D1–D17, contratos C1–C11).
- Briefs y mockups: `/home/xodla/.hermes/profiles/conciliacion/cache/scratch/report-review-20261113/{briefs,mock}/`.

## Seguridad de datos

- Trabajar solo sobre copias `.backup` de la BD de QA (sesión `bcb6791e-2823-4d21-857c-7286d26ed0b2`). Nunca uvicorn ni el lifespan de FastAPI sobre una copia con datos reales: al apagar, `cleanup_old_sessions` borra las sesiones antiguas. Usar `TestClient(app)` sin `with`.
- Para revisión en navegador existe un puente fuera del repo: `scratch/report-redesign-w3/runtime/` (`bridge.py`, `ARRANQUE.md`), que reenvía HTTP a `TestClient` sin lifespan sobre su propia copia.
- Pruebas con `CONCILIACION_DATA_DIR` vacío y memoria limitada (4G focalizadas, 6G suite completa, `MemorySwapMax=0`). `soffice` siempre con `--outdir`.
