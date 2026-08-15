# ADR-006: no registrar cada evento de la aplicación en el ledger

- Estado: Aceptada
- Fecha: 2026-08-14

## Contexto

Cambios de UI, borradores, señales de salud, telemetría cruda y otros eventos
rutinarios no siempre aportan integridad entre organizaciones. Registrarlos
inflaría el ledger y acoplaría la disponibilidad normal de la aplicación a Fabric.

## Decisión

Un evento solo es elegible para el ledger si cumple todas estas condiciones:

1. Tiene relevancia durable de negocio o cumplimiento.
2. Más de una organización se beneficia de verificarlo independientemente.
3. Existe una representación compacta y determinista.
4. La inmutabilidad es compatible con obligaciones de corrección y privacidad.

Todo lo demás queda fuera de la cadena. Las correcciones de hechos elegibles
son eventos nuevos; nunca sobrescriben historial.

## Consecuencias

- El volumen y acoplamiento operacional del ledger se mantienen acotados.
- La política de selección debe revisarse con referentes del dominio.
- Los logs de aplicación cubren los eventos de seguridad y operación off-chain.
- No aparecer en Fabric no implica falta de importancia, sino que la base es el
  control apropiado.
