# ADR-003: almacenar los documentos fuera de la blockchain

- Estado: Aceptada
- Fecha: 2026-08-14

## Contexto

Informes de inspección, fotografías y certificados son grandes, pueden contener
información sensible y requieren controles de ciclo de vida que una blockchain
no proporciona correctamente.

## Decisión

Guardar los bytes en MinIO privado, los metadatos en PostgreSQL y el digest
SHA-256 más las referencias de negocio en Fabric. La verificación calcula el
hash del archivo recibido y lo compara con el registro del ledger.

## Consecuencias

- Los documentos utilizan controles normales de acceso, backup y retención.
- Fabric permanece compacto y no revela el contenido documental.
- El ledger no repara la pérdida del objeto; los backups siguen siendo obligatorios.
- Un hash coincidente prueba integridad, no la veracidad de las afirmaciones.
