# ADR-002: mantener las lecturas de telemetría fuera de la cadena

- Estado: Aceptada
- Fecha: 2026-08-14

## Contexto

Los sensores generan datos a alta frecuencia. Registrar cada lectura en Fabric
aumentaría el tamaño del ledger, la latencia, la exposición de privacidad y el
costo operativo, además de empeorar las consultas normales de series temporales.

## Decisión

Persistir las lecturas en el almacén operativo. Serializar canónicamente lotes
acotados, calcular SHA-256 y anclar en Fabric solo la identidad del lote, rango
temporal, resumen, cantidad de muestras y hash. Una raíz Merkle queda como
optimización futura si se necesita probar lecturas individuales.

## Consecuencias

- La telemetría continúa siendo eficiente para ingesta y consulta.
- Un lote puede comprobarse contra alteraciones después del anclaje.
- El primer diseño prueba un lote completo, no cada lectura de forma independiente.
- La retención y los controles de acceso de la base siguen siendo esenciales.
