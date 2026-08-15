# Estado del proyecto FieldLedger

Última verificación: 15 de agosto de 2026, 00:14 ART / 03:14 UTC.

Este es el punto de entrada para el relevo por parte de una futura IA o de un
ingeniero. Debe actualizarse después de cada checkpoint. Nunca colocar aquí
contraseñas, tokens, claves privadas ni contenidos de `.env`.

## Checkpoint actual

La interfaz web y el flujo real de mantenimiento respaldado por ledger están
funcionando en la Raspberry Pi:

```text
UI web en español -> FastAPI
Transacción de negocio en FastAPI
  -> datos PostgreSQL + outbox durable en un mismo commit
  -> worker del ledger
  -> Fabric Gateway privado en TypeScript
  -> Hyperledger Fabric 2.5.16
  -> endorsement de Org1 + Org2
  -> ID de transacción y número de bloque reales

Bytes del documento -> solo MinIO
SHA-256 del documento -> Fabric
Archivo del auditor -> nuevo SHA-256 -> consulta Fabric -> coincide/no coincide
```

No existe un camino de éxito blockchain falso o basado únicamente en la base
de datos. Los dobles de prueba existen solo en las pruebas unitarias. La
aceptación en vivo demostró que el PDF original verifica y una copia modificada
a nivel de bytes no.

## Inventario del despliegue activo

| Elemento | Valor |
|---|---|
| Host | Raspberry Pi dedicada; datos de acceso en `.local/DEPLOYMENT.md` |
| SSH | Inventario local privado, excluido de Git |
| Raíz del proyecto | `/home/pi/fieldledger` |
| Repositorio | `https://github.com/Garbox0/FIELDLEDGER.git`, rama `main` |
| API | `http://127.0.0.1:8095` |
| Interfaz | `http://127.0.0.1:8095/app/`, solo loopback/túnel SSH |
| Fabric | `2.5.16` LTS, canal `fieldledgerchannel` |
| Chaincode | `fieldledger` 1.0, secuencia 1 |
| Endorsement | `AND('Org1MSP.peer','Org2MSP.peer')` |
| Organizaciones | Org1/Operadora, Org2/Contratista, Org3/Auditor |
| Gateway | Node 24.18.0, Fabric Gateway 1.12.0, puerto 3000 solo en Docker |
| Base de datos | PostgreSQL 18.4, Alembic `20260814_0004` |
| Objetos | MinIO `fieldledger-documents` |
| Volúmenes de aplicación | `fieldledger_postgres-data`, `fieldledger_minio-data` |
| Backups primarios | `/home/pi/fieldledger/backups` en la SD |
| Último backup primario verificado | `postgres/minio-20260815T020558Z` más manifiesto SHA-256 |
| Runtime de Fabric | `/home/pi/fieldledger/.runtime/fabric-samples` |

Los contenedores principales son `fieldledger-api-1`,
`fieldledger-ledger-worker-1`, `fieldledger-postgres-1` y
`fieldledger-minio-1`. El gateway es `fieldledger-gateway-gateway-1`. Fabric
usa `orderer.example.com` y `peer0.org{1,2,3}.example.com`, además de los
contenedores de chaincode bajo demanda. Solo la API está publicada en el host
y únicamente sobre loopback.

## Evidencia objetiva

- Pruebas Python: `15 passed, 1 upstream warning`.
- Pruebas de chaincode: `2 passed`; pruebas de gateway: `2 passed`.
- Alembic: `No new upgrade operations detected.`
- El demo anterior al ledger fue reconciliado en los bloques 8 a 11; las cuatro
  filas de outbox quedaron `COMMITTED` en el primer intento.
- Conteo final de outbox: 16 `COMMITTED`, sin operaciones pendientes o fallidas.
- Último activo E2E: `E2E-6A7FC963`.
- Último evento E2E: `EVT-E2E-6A7FC963`.
- Último documento E2E: `c153892a-291b-44d4-b81d-11bd6acc4304`.
- SHA-256 E2E:
  `9150697ad94c2b3f718da872ec369a3924c33cc750453301c8b10cca4288aa78`.
- Los bloques Fabric 21 a 24 contienen el alta del activo, la propuesta, el
  hash documental y la aprobación. Cada ID devuelto fue un identificador real
  de Fabric de 64 caracteres hexadecimales.
- La evidencia original devolvió `verified=true`; la modificada devolvió
  `verified=false`.
- Los healthchecks de API y gateway quedaron saludables después de la prueba.
- La UI desplegada respondió HTTP 200 con CSP y `X-Frame-Options: DENY`; login
  real y `GET /api/v1/ledger/operations` devolvieron correctamente las 16
  operaciones. La inspección visual automatizada quedó pendiente porque el
  puente del navegador integrado no estuvo disponible en esta sesión.
- Auditorías del 2026-08-14: `pip-audit` y los dos `npm audit --omit=dev`
  informaron cero vulnerabilidades conocidas.
- Workflow CI agregado en `.github/workflows/ci.yml`: API Python, chaincode,
  gateway y auditorías de dependencias, con permisos de solo lectura.
- GitHub Actions run `31861229121`: API Python, chaincode y gateway aprobados;
  GitGuardian también aprobado. El primer run reveló que el entrypoint `pytest`
  no agregaba el working directory al path en GitHub; commit `d5b3275` lo
  corrigió usando `python -m pytest`. Las 15 pruebas pasaron en CI.
- Una repetición del bootstrap expuso y corrigió un error de detección del
  chaincode ya confirmado. El intento de aprobar nuevamente la secuencia 1
  quedó inválido en el bloque 20 (`ENDORSEMENT_POLICY_FAILURE`) y no cambió el
  world state. El script usa ahora el código de salida del comando oficial y
  una repetición posterior omitió correctamente el despliegue.

La única advertencia Python proviene de la transición del cliente de pruebas
FastAPI/Starlette de `httpx` a `httpx2`; no es una falla.

## Comportamiento implementado

- Login OAuth2 con contraseña, hashes Argon2, JWT HS256 con vencimiento y RBAC
  cargado desde la base de datos.
- CRUD de activos; el alta encola el registro correspondiente en Fabric.
- Propuestas de mantenimiento solo por contratista; revisión por
  operador/administrador; un rechazo exige motivo.
- Evidencia PDF/JPEG/PNG de hasta 10 MiB, validación por magic bytes, SHA-256,
  almacenamiento privado en MinIO y metadatos en PostgreSQL.
- `ledger_outbox` transaccional con IDs idempotentes, reintentos, estados reales
  `SUBMITTED/COMMITTED/FAILED`, IDs de transacción y números de bloque.
- Autorización del chaincode según el MSP cliente, no según un rol enviado por
  la API.
- Consultas del ledger para activos, eventos, hashes documentales, líneas de
  tiempo e historial.
- `POST /api/v1/documents/verify` siempre consulta Fabric cuando está habilitado.
- `/ready` verifica PostgreSQL, MinIO y Fabric Gateway.
- UI web responsive en español para login, activos, mantenimiento, evidencia,
  actividad del ledger y verificación; usa JavaScript nativo, `sessionStorage`
  para el JWT y no persiste contraseñas.
- `GET /api/v1/ledger/operations` expone a usuarios autenticados estado,
  transaction ID y bloque, sin payload ni errores internos.
- Headers CSP, anti-framing, `nosniff`, referrer y permissions policy sobre la UI.
- Backups con timestamp de PostgreSQL/MinIO, manifiestos SHA-256 y preflight
  que reserva al menos 10 GiB de la SD.

## Fuentes de verdad

- Aplicación en ejecución: `docker-compose.yml`.
- Bootstrap de Fabric: `blockchain/scripts/fabric-up.sh`.
- Chaincode: `blockchain/chaincode/fieldledger/src/fieldledger-contract.ts`.
- Gateway interno: `services/fabric-gateway/`.
- Outbox y worker: `apps/api/app/ledger.py`, `ledger_worker.py`.
- Reconciliación: `apps/api/app/reconcile_ledger.py`.
- Base de datos: `apps/api/app/models.py`, migración `20260814_0004`.
- Aceptación en vivo: `apps/api/app/e2e_ledger_smoke.py`.
- Interfaz web: `apps/api/app/static/`; se sirve desde `apps/api/app/main.py`.
- Operación: `docs/technical-guide.md`.
- Explicación no técnica: `docs/non-technical-guide.md`.
- Límites y decisiones: `docs/architecture.md`, `docs/adr/`.

El workspace de Windows es `D:\Proyectos\OilLedger`. El repositorio remoto es
`Garbox0/FIELDLEDGER`. La interfaz está en `agent/interfaz-web`: implementación
`a07c898`, corrección CI `d5b3275` y PR borrador `#1`. `main` conserva el
checkpoint inicial hasta la aceptación visual y el merge. Los archivos de la
interfaz ya están desplegados en la Pi. Preservar el trabajo del usuario: no
usar reset destructivo ni reescribir historia.

## Secretos e identidades

El `.env` de la Pi tiene permisos 600 e incluye secretos generados para
PostgreSQL, MinIO, JWT, usuarios demo y gateway interno. Nunca imprimirlo ni
copiarlo. Las claves privadas de Fabric están bajo el árbol ignorado
`.runtime` y se montan únicamente en el gateway.

Los usuarios demo comparten el `DEMO_PASSWORD` generado:

| Usuario | Rol de aplicación | Organización / identidad Fabric utilizada |
|---|---|---|
| `admin` | ADMIN | OperatorOrg / Org1MSP |
| `operator` | OPERATOR | OperatorOrg / Org1MSP |
| `contractor` | CONTRACTOR | ContractorOrg / Org2MSP |
| `auditor` | AUDITOR | AuditorOrg / Org3MSP |
| `viewer` | VIEWER | AuditorOrg; sin escrituras en el ledger |

La identidad JWT y la identidad X.509 de Fabric son dominios de confianza
separados de manera intencional.

## Decisión sobre el HDD y capacidad de la SD

El HDD conectado fue descartado. Registra sectores reasignados, pendientes e
irrecuperables, además de una prueba SMART extendida fallida. El modelo, serie
y datos de acceso del host están en el inventario local excluido de Git. Una
reescritura dirigida no pudo remapear el defecto. El escaneo de lectura desde
150 GiB hasta el final no encontró bloques defectuosos nuevos,
pero las primeras escrituras ext4 sobre esa región provocaron reinicios USB
repetidos y un `mkfs.ext4` bloqueado en el kernel.

El intento se detuvo, el dispositivo USB fue desvinculado, no se montó ningún
filesystem y no se agregó ninguna entrada a `fstab`. La GPT/partición parcial
no debe usarse. Una regla udev pone en cuarentena el puerto USB `2-2` después
de cada reinicio. Eliminar
`/etc/udev/rules.d/99-fieldledger-quarantine-hdd.rules` solo después de
desconectar físicamente o reemplazar el disco.

Todos los datos y backups activos permanecen en la SD. Última medición: 59 GiB
totales, 16 GiB usados y 41 GiB disponibles (28 %). `make storage-status`
informa el consumo de SD, backups, runtime Fabric y Docker. `make backup`
estima primero el espacio requerido y se niega a reducir el espacio libre por
debajo de 10 GiB. No existe retención automática que borre datos; revisar
explícitamente backups verificados antiguos si aparece la alerta de 15 GiB.

## Limitaciones conocidas

- La topología Fabric parte de `test-network` y es un consorcio de laboratorio
  en un único host, no un despliegue productivo distribuido.
- Las identidades `cryptogen` son de laboratorio; no existen CA productiva,
  HSM, rotación de certificados ni custodia independiente entre empresas.
- No existen todavía telemetría/MQTT, Prometheus/Grafana ni despliegue continuo.
- No están implementados revocación/refresh de JWT, rate limiting, TLS, OIDC,
  alta disponibilidad ni recuperación externa ante desastres.
- Se permite un documento primario por evento de mantenimiento.
- El hard-delete de un activo solo es posible antes de que tenga eventos; el
  producto debería incorporar un flujo auditable de baja.
- Este kernel no tiene memory cgroups; no se deben considerar efectivos los
  límites de memoria declarados en Docker.
- Los contenedores dinámicos del chaincode heredan los valores del builder.
  API, worker, gateway, peers y orderer tienen rotación JSON explícita de
  3 archivos de 10 MiB.

## Próximo paso exacto

Realizar una aceptación visual manual de la UI a través de túnel SSH y ejecutar
el relato completo cambiando entre operadora, contratista y auditor: alta,
propuesta, evidencia, aprobación, commit y verificación original/modificada.
Capturar luego dos o tres imágenes sin datos sensibles para el README/portfolio.
Corregir cualquier detalle visual encontrado antes de comenzar telemetría.

## Comandos para el relevo

```bash
cd /home/pi/fieldledger
make ledger-status
curl -fsS http://127.0.0.1:8095/health
curl -fsS http://127.0.0.1:8095/ready
make test
docker compose run --rm api alembic check
make ledger-smoke
make storage-status
```

Antes de modificar el esquema o el despliegue, ejecutar `make backup`.
Actualizar este documento con hechos observados, nunca con resultados
planificados o simulados.
