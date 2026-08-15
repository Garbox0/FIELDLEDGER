# ADR-005: usar blockchain solo ante una brecha de confianza entre organizaciones

- Estado: Aceptada
- Fecha: 2026-08-14

## Contexto

Una base de datos ya ofrece transacciones, restricciones, backups, consultas
eficientes y tablas de auditoría. Blockchain no es automáticamente una base
mejor. Su valor depende de que organizaciones sin confianza plena en un único
administrador necesiten avalar y conservar la misma evidencia.

## Decisión

PostgreSQL es la fuente de verdad operativa. Fabric se usa solo para hechos
compactos cuya alteración posterior por una parte debe ser detectable por las
otras: alta de activo, propuesta/decisión de mantenimiento, inspección, hash
documental y anclaje de lote de telemetría.

Usar solo PostgreSQL cuando:

- una organización controle a todos los escritores y auditores;
- logs de auditoría firmados satisfagan el requisito de gobierno;
- corrección o borrado sean más importantes que inmutabilidad;
- los participantes no operen identidades independientes del ledger; o
- disponibilidad y costo superen el valor del endorsement compartido.

## Consecuencias

- Cada escritura en Fabric puede justificarse en lugar de usar blockchain como
  una capa de marketing.
- La mayoría de consultas y workflows siguen siendo operaciones SQL simples.
- La plataforma debe reconciliar la base con commits asíncronos del ledger.
- Un despliegue puede desactivar el ledger si su modelo de confianza no lo exige.
