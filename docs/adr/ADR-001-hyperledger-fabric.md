# ADR-001: utilizar Hyperledger Fabric como ledger compartido

- Estado: Aceptada
- Fecha: 2026-08-14

## Contexto

Operadora, contratista y auditor necesitan un registro gobernado en conjunto
para ciertas acciones de integridad de activos. El caso requiere participantes
conocidos, autorización por organización, políticas de endorsement e historial.
No necesita una criptomoneda pública ni consenso anónimo.

## Decisión

Utilizar Hyperledger Fabric como ledger permisionado. Modelar `OperatorOrg`,
`ContractorOrg` y `AuditorOrg`, y codificar reglas sensibles a la organización
en el chaincode. Las identidades Fabric se usan únicamente dentro del límite
gateway/red.

## Consecuencias

- Las políticas de endorsement expresan gobierno entre organizaciones.
- Fabric agrega complejidad de certificados, red, chaincode y operación.
- No existe token, minería, proof of work ni dependencia de una cadena pública.
- Si una organización confiable controla a todos los escritores, PostgreSQL es
  la solución preferida por ser más simple; ver ADR-005.
