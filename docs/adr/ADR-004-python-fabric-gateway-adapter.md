# ADR-004: aislar el acceso a Fabric detrás de un gateway TypeScript

- Estado: Aceptada
- Fecha: 2026-08-14

## Contexto

Python es el lenguaje del servicio de negocio, mientras la integración de
aplicaciones mantenida por Fabric es más sólida mediante su Gateway SDK para
Node.js/TypeScript. Integrarlo directamente en FastAPI mezclaría identidades,
certificados, ciclo de vida del SDK y lógica de negocio.

## Decisión

Crear un único servicio interno `fabric-gateway` en TypeScript. FastAPI llama a
su pequeña API HTTP interna. Solo el gateway monta perfiles de conexión,
certificados y claves privadas de Fabric.

## Consecuencias

- FastAPI se mantiene enfocado en Python y las actualizaciones Fabric se aíslan.
- Los secretos Fabric tienen un límite de exposición menor.
- Hay un salto de red y un servicio adicional que observar.
- El gateway no se publica en el host ni autoriza usuarios finales; FastAPI
  autoriza antes de enviar la operación.
