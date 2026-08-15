# ADR-007: usar la red oficial de Fabric solo como topología de laboratorio

- Estado: Aceptada para uso de laboratorio
- Fecha: 2026-08-14

## Contexto

El hito en Raspberry Pi debe probar endorsement, commit, historial y
verificación reales sin fingir que un host constituye un consorcio productivo.
Construir la operación productiva antes de validar el camino de negocio
agregaría complejidad sin mejorar la prueba del prototipo.

## Decisión

Fijar la red oficial `fabric-samples` en el commit
`05edea01d4cf24dd4087bd3750c36e690dc4d6ff`. Ejecutar Fabric 2.5.16 LTS con
Org1 como OperatorOrg, Org2 como ContractorOrg y el flujo oficial addOrg3 como
AuditorOrg. Vincular puertos administrativos a loopback, mantener privado el
gateway y exigir endorsement de Org1 más Org2.

Usar identidades `cryptogen` únicamente para este laboratorio. Nunca describir
esta topología como lista para producción.

## Consecuencias

- Se puede probar el camino real API-ledger en ARM64 con herramientas oficiales.
- Todas las organizaciones comparten un dominio físico y administrativo de falla.
- Las claves de laboratorio no tienen enrolamiento, rotación, revocación, HSM
  ni custodia organizacional productiva.
- Una fase productiva debe reemplazar esta topología con nodos independientes,
  autoridades certificantes o ciclo equivalente, gobierno, HA, observabilidad,
  backup/restore y revisión de seguridad.
