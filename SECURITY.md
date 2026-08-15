# Seguridad de FieldLedger

## Alcance

FieldLedger es un prototipo de laboratorio y portfolio. No debe conectarse a
equipos de campo ni exponerse directamente a Internet. La topología Fabric
actual comparte una Raspberry Pi y no representa aislamiento productivo entre
organizaciones.

## Qué no debe entrar en Git

- `.env` o cualquier archivo con contraseñas, tokens o connection strings;
- `.runtime/`, certificados o claves privadas de Fabric;
- `.local/`, IPs internas, inventario de hosts o números de serie;
- backups, dumps, evidencia real, logs o datos personales;
- JWT, cookies, credenciales demo reales o capturas que los muestren.

`.gitignore` y `.dockerignore` cubren estos caminos, pero deben revisarse antes
de cada publicación. `.env.example` contiene únicamente marcadores.

## Exposición de red

La API/UI se vincula a `127.0.0.1`; PostgreSQL, MinIO y Fabric Gateway no
publican puertos. Para una demostración remota usar un túnel SSH autenticado,
no port forwarding del router, Funnel ni un proxy público improvisado.

Antes de cualquier despliegue accesible por terceros se requieren, como mínimo,
TLS, OIDC o IAM equivalente, rate limiting, gestión de secretos, certificados
productivos, observabilidad, backups externos probados y revisión de seguridad.

## Dependencias

Las versiones están fijadas para reproducibilidad. El 14 de agosto de 2026 se
ejecutaron `pip-audit` sobre la API y `npm audit --omit=dev` sobre chaincode y
gateway: no informaron vulnerabilidades conocidas. Este resultado envejece;
el workflow CI repite los tres controles en cada PR y push a `main`.

## Si un secreto se filtra

No alcanza con borrar el archivo del último commit. Revocar o rotar de inmediato
las credenciales afectadas —PostgreSQL, MinIO, JWT, usuarios demo y token del
gateway— y regenerar identidades Fabric si se expuso `.runtime`. Después revisar
todo el historial Git y los logs de acceso.

## Reporte de vulnerabilidades

No publicar credenciales ni detalles explotables en un issue. Informar de forma
privada al propietario del repositorio mediante GitHub Security Advisories antes
de una divulgación pública.
