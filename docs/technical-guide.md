# Guía técnica de FieldLedger

Esta guía describe el sistema de laboratorio desplegado, su operación y sus
límites de confianza. Los componentes todavía planificados se identifican de
forma explícita.

## Arquitectura en ejecución

```text
127.0.0.1:8095
       |
    UI web
       |
    FastAPI ----------------------> PostgreSQL
       |                               |
       +---------------------------> MinIO
       |                               bytes de documentos
       +-- misma transacción DB --> ledger_outbox
                                       |
                                  ledger-worker
                                       |
                              Fabric Gateway (privado)
                                       |
                         canal Fabric fieldledgerchannel
                         peer Org1 + peer Org2 + peer Org3
```

PostgreSQL es la fuente operativa inmediata. Fabric es la fuente compartida de
integridad para hechos seleccionados. MinIO almacena los bytes; Fabric guarda
los hashes documentales, nunca los documentos completos.

## Línea base fijada del ledger

| Componente | Versión / identidad |
|---|---|
| Hyperledger Fabric | 2.5.16 LTS |
| `fabric-samples` oficial | commit `05edea01d4cf24dd4087bd3750c36e690dc4d6ff` |
| Builder Node de Fabric | 2.5.8, etiquetado localmente como 2.5 |
| Canal | `fieldledgerchannel` |
| Chaincode | `fieldledger` 1.0, secuencia 1 |
| Node.js | 24.18.0 LTS |
| Fabric Gateway Node SDK | 1.12.0 |
| Chaincode API/shim | 2.5.8 |
| TypeScript | 7.0.2 |

El bootstrap reutiliza la red oficial de pruebas de Fabric como una topología
reproducible de laboratorio en un único host. No es una red productiva.

Correspondencia de organizaciones:

| Organización de negocio | MSP | Nodo / identidad cliente de Fabric |
|---|---|---|
| OperatorOrg | Org1MSP | `peer0.org1.example.com`, User1 de Org1 |
| ContractorOrg | Org2MSP | `peer0.org2.example.com`, User1 de Org2 |
| AuditorOrg | Org3MSP | `peer0.org3.example.com`, User1 de Org3 |

Las mutaciones requieren endorsement de los peers de operadora y contratista:

```text
AND('Org1MSP.peer','Org2MSP.peer')
```

Org3 pertenece al canal y puede consultar con identidad independiente, pero no
es obligatoria para avalar escrituras operativas en este MVP.

Referencias oficiales utilizadas:

- [Instalación y versiones de Fabric](https://hyperledger-fabric.readthedocs.io/en/latest/install.html)
- [Notas de Fabric 2.5 LTS](https://hyperledger-fabric.readthedocs.io/en/release-2.5/whatsnew.html)
- [Uso y advertencias de test-network](https://hyperledger-fabric.readthedocs.io/en/release-2.5/test_network.html)
- [Ciclo de vida del chaincode](https://hyperledger-fabric.readthedocs.io/en/release-2.5/chaincode_lifecycle.html)
- [API Node de Fabric Gateway](https://hyperledger.github.io/fabric-gateway/main/api/node/interfaces/Contract.html)
- [Calendario de versiones de Node.js](https://nodejs.org/en/about/previous-releases)

## Autenticación y autorización

FastAPI utiliza login OAuth2 por formulario de contraseña. Las contraseñas se
guardan con Argon2. Los JWT solo contienen el nombre de usuario y el
vencimiento; en cada solicitud protegida la API vuelve a cargar el rol y el
estado activo desde PostgreSQL.

| Operación | ADMIN | OPERATOR | CONTRACTOR | AUDITOR | VIEWER |
|---|:---:|:---:|:---:|:---:|:---:|
| Leer activos/eventos/metadatos documentales | sí | sí | sí | sí | sí |
| Crear/editar/eliminar un activo elegible | sí | sí | no | no | no |
| Proponer mantenimiento | no | no | sí | no | no |
| Subir evidencia a un evento propuesto | sí | sí | sí | sí | no |
| Aprobar/rechazar mantenimiento | sí | sí | no | no | no |
| Verificar un documento contra Fabric | sí | sí | no | sí | no |

El chaincode aplica reglas organizacionales de manera independiente a partir
del MSP del certificado: Org1 crea activos y revisa; Org2 propone eventos; todos
los MSP conocidos pueden registrar o consultar evidencia. No confía en un rol
enviado por FastAPI.

Las claves JWT de aplicación y las claves privadas de Fabric son distintas. El
árbol de identidades ignorado `.runtime` se monta como solo lectura únicamente
en el gateway interno.

Cada usuario demo puede tener su propia variable
`DEMO_<USUARIO>_PASSWORD`; `DEMO_PASSWORD` queda como fallback para instalaciones
anteriores. `make seed` actualiza el hash Argon2 si la contraseña configurada
cambió y nunca imprime el valor.

Con `PUBLIC_DEMO_VIEWER=true`, `POST /api/v1/auth/demo` entrega una sesión para
`viewer` sin contraseña. Ese rol solo lee activos, eventos, estados y metadatos;
no descarga los bytes de MinIO, verifica archivos ni escribe datos. Los fallos
de login normal se limitan por IP con una ventana en memoria. Esta implementación
alcanza para el proceso único de la Pi; un despliegue replicado necesita un
contador compartido o una regla equivalente en el proxy.

## Outbox transaccional

El alta de activos, la propuesta de eventos, el registro de evidencia y la
revisión agregan una fila a `ledger_outbox` en el mismo commit de PostgreSQL que
el cambio de negocio. El worker procesa las filas en orden de creación:

```text
PENDING -> SUBMITTED -> COMMITTED
                     -> FAILED -> reintento
```

Cada operación tiene un ID determinista, por ejemplo `asset:A-1:create` o
`event:E-1:review`. El chaincode guarda ese ID y un digest del payload. Una
repetición idéntica es segura; reutilizar el ID con otros datos se rechaza.

Al confirmar, la outbox guarda el ID real de transacción Fabric y el número de
bloque. También actualiza campos de conveniencia de eventos y documentos para
las lecturas de API. Una caída de gateway o peer activa reintentos
exponenciales acotados; nunca inventa una transacción ni marca un commit local
como confirmado en blockchain.

Los registros anteriores a Fabric se encolan de forma idempotente con:

```bash
make ledger-reconcile
```

## Datos y funciones del chaincode

Hechos compactos registrados:

- ID, tipo, nombre, sitio, serie opcional y organización creadora del activo;
- ID de evento/activo, tipo, descripción, ejecutor, fecha y organización;
- aprobación/rechazo, revisor, organización, fecha y motivo opcional;
- ID de documento/activo/evento, SHA-256, MIME, tamaño, usuario y organización;
- IDs de transacción y timestamps de Fabric.

Funciones implementadas:

```text
CreateAsset       ProposeEvent       ReviewEvent       RegisterDocument
GetAsset          GetEvent           GetDocumentByHash
GetAssetTimeline  GetAssetHistory    GetEventHistory   GetLedgerInfo
```

Los documentos completos, contraseñas, JWT, claves de MinIO y telemetría cruda
no ingresan al ledger.

## Verificación documental

`POST /api/v1/documents/verify` admite PDF/JPEG/PNG de hasta 10 MiB. La API
valida la firma del archivo, calcula el SHA-256 de los bytes recibidos y pide al
gateway que evalúe `GetDocumentByHash` usando la identidad de AuditorOrg.

- `verified=true`: Fabric contiene ese hash exacto y devuelve sus metadatos.
- `verified=false`, `HASH_NOT_REGISTERED`: Fabric no contiene el hash.
- HTTP 502: no fue posible consultar Fabric; no hay fallback de éxito local.

SHA-256 prueba igualdad byte a byte con la evidencia registrada. No cifra el
archivo ni prueba que su contenido sea verdadero.

## Interfaz web y seguridad del navegador

FastAPI sirve `apps/api/app/static/` bajo `/app/`. La implementación usa HTML,
CSS y JavaScript nativos para evitar un toolchain, dependencias y contenedor
adicionales sobre la Raspberry Pi.

- El JWT vive en `sessionStorage` y desaparece al cerrar la pestaña; la
  contraseña nunca se almacena.
- La autorización efectiva siempre pertenece al backend. Ocultar botones por
  rol es solo una ayuda de UX.
- Los datos dinámicos se insertan como `textContent`, no como HTML ejecutable.
- CSP permite recursos y conexiones del mismo origen, sin scripts inline.
- `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` y
  `Permissions-Policy` se aplican sobre `/` y `/app`.
- No hay CORS ni puerto nuevo porque UI y API comparten origen.
- En modo público aparece `Explorar en modo lectura`; `/docs`, `/redoc` y
  `/openapi.json` quedan deshabilitados.

`GET /api/v1/ledger/operations` devuelve las últimas operaciones autenticadas
con estado, intentos, transaction ID y bloque. No expone payload ni error
interno de la outbox.

## Rutas de la API

```text
POST   /api/v1/auth/login
GET    /api/v1/auth/demo
POST   /api/v1/auth/demo
GET    /api/v1/auth/me

POST   /api/v1/assets
GET    /api/v1/assets
GET    /api/v1/assets/{asset_id}
PATCH  /api/v1/assets/{asset_id}
DELETE /api/v1/assets/{asset_id}

POST   /api/v1/assets/{asset_id}/maintenance
GET    /api/v1/assets/{asset_id}/events
GET    /api/v1/events/{event_id}
POST   /api/v1/events/{event_id}/approve
POST   /api/v1/events/{event_id}/reject

POST   /api/v1/events/{event_id}/documents
GET    /api/v1/documents/{document_id}
POST   /api/v1/documents/verify

GET    /api/v1/ledger/operations

GET    /health
GET    /ready
```

`/health` indica que el proceso está vivo. Con `LEDGER_ENABLED=true`, `/ready`
requiere PostgreSQL, MinIO y una consulta exitosa a Fabric a través del gateway.

## Primer inicio y operación habitual

Requisitos en un host Linux ARM64: Docker Engine/Compose v2, Bash, Git, curl,
tar, Python 3, jq, OpenSSL y Make.

```bash
make bootstrap       # crear .env una vez; luego solo agrega valores faltantes
make ledger-up       # Fabric -> gateway -> migración -> API/worker
make seed            # identidades demo idempotentes
make ledger-status
curl -fsS http://127.0.0.1:8095/ready
```

Abrir `http://127.0.0.1:8095/app/`. Desde otra máquina utilizar un túnel SSH:

```bash
ssh -L 8095:127.0.0.1:8095 usuario@host-raspberry
```

Para la publicación remota se reserva `fieldledger.aerosftp.com` en un túnel
Cloudflare independiente. La configuración de la Pi debe incluir:

```dotenv
PUBLIC_DEMO_VIEWER=true
TRUSTED_HOSTS=fieldledger.aerosftp.com,127.0.0.1,localhost,api
TRUST_CF_CONNECTING_IP=true
LOGIN_RATE_LIMIT_ATTEMPTS=10
LOGIN_RATE_LIMIT_WINDOW_SECONDS=60
```

El token de `cloudflared` es un secreto operativo: se guarda en la unidad de
systemd creada por Cloudflare y nunca en Git, `.env` ni esta documentación.

`fabric-up.sh` clona el commit fijado de samples en `.runtime`, descarga el
archivo binario ARM64 exacto de Fabric, fija las imágenes Docker, compila y
prueba el chaincode, crea el canal de tres organizaciones y confirma el
contrato. No destruye automáticamente un ledger funcional.

Comandos útiles:

```bash
make test
make migrate
docker compose run --rm api alembic check
make ledger-reconcile
make ledger-smoke
make ledger-status
make logs
make backup
```

Las pruebas unitarias fuerzan `LEDGER_ENABLED=false` para no depender de
infraestructura externa; la prueba específica de verificación habilita un
doble controlado. `make ledger-smoke` sigue siendo la aceptación real de Fabric.

GitHub Actions ejecuta en cada PR y push a `main` las 17 pruebas Python, las
pruebas de chaincode/gateway y las auditorías `pip-audit`/`npm audit`. El
workflow tiene permisos de repositorio de solo lectura y no usa secretos.

`make ledger-smoke` crea un activo, evento y evidencia de laboratorio con
nombres únicos, espera los cuatro commits reales, verifica el PDF original,
rechaza una copia modificada e imprime los IDs de transacción y bloques. Deja
los registros de auditoría de forma intencional.

## Secuencia de despliegue

La raíz en la Pi es `/home/pi/fieldledger`.

```bash
cd /home/pi/fieldledger
make backup
docker compose config --quiet
make test
make fabric-up
make gateway-up
make migrate
docker compose run --rm api alembic check
make ledger-reconcile
docker compose up -d --build
make ledger-smoke
make ledger-status
```

No ejecutar `down` de la red oficial de pruebas sobre el laboratorio activo
salvo que se haya pedido explícitamente un reset destructivo y exista un backup
utilizable.

## Política de backups y HDD

`make backup` genera un dump de PostgreSQL, un archivo consistente del volumen
MinIO y un manifiesto SHA-256 bajo `./backups`. MinIO se detiene brevemente para
capturar el volumen y un trap garantiza su reinicio. Antes de escribir, el
script estima el tamaño de base y objetos y se niega a dejar menos de 10 GiB
libres en la SD.

`make storage-status` informa filesystem, backups, runtime ignorado de Fabric y
uso de Docker; advierte por debajo de 15 GiB. La retención es manual para no
borrar evidencia o backups sin una decisión explícita.

El HDD conectado fue descartado. Sus errores físicos no pudieron remapearse y
`mkfs.ext4` provocó reinicios USB incluso sobre una región que había superado
un escaneo de lectura de 69 minutos. Está desvinculado, desmontado, ausente de
`fstab` y bloqueado por
`/etc/udev/rules.d/99-fieldledger-quarantine-hdd.rules`. Retirar esa regla solo
después de desconectar físicamente o reemplazar el dispositivo.

## Red y límite de seguridad

- API: solo loopback del host, `127.0.0.1:8095`.
- Gateway: solo redes Docker; ningún puerto del host.
- PostgreSQL/MinIO: únicamente la red interna de datos.
- Puertos Fabric: loopback para herramientas administrativas locales.
- No existe forwarding del router. La única ruta pública prevista es
  `fieldledger.aerosftp.com` mediante Cloudflare Tunnel hacia la API en
  loopback.
- Las solicitudes al gateway requieren un bearer token generado y comparado en
  tiempo constante.
- API y gateway usan raíz de solo lectura, `no-new-privileges` y filesystems
  temporales acotados.
- Los servicios principales tienen rotación de logs Docker.

El kernel de esta Pi no expone memory cgroups, por lo que Docker informa que
descarta los límites de memoria. Observar directamente el uso de disco y RAM.

## Resolución de problemas

### La outbox permanece en PENDING o FAILED

```bash
make ledger-status
docker compose logs --tail=150 ledger-worker
docker logs --tail=150 fieldledger-gateway-gateway-1
docker ps --filter label=service=hyperledger-fabric
```

No editar estados ni fabricar IDs de transacción. Restaurar la dependencia y
permitir que el worker reintente el mismo ID de operación.

### `/ready` devuelve 503

```bash
docker compose ps
docker inspect --format='{{.State.Health.Status}}' fieldledger-gateway-gateway-1
docker compose exec -T postgres pg_isready -U fieldledger -d fieldledger
```

Revisar logs de API, gateway, peer, orderer, PostgreSQL y MinIO sin imprimir
`.env` ni claves privadas de certificados.

### La verificación devuelve 502

Fabric no estuvo disponible o devolvió una respuesta inválida. Un 502 es
deliberadamente distinto de `verified=false`: este último representa una
consulta exitosa sin un hash coincidente.

### Recuperación después de reiniciar

Aplicación, gateway, orderer y peers usan `unless-stopped`. El worker reintenta
de forma segura. Si la red está incompleta, ejecutar `make fabric-up`, luego
`make gateway-up` y finalmente `docker compose up -d`; las operaciones de
bootstrap son idempotentes para el checkpoint fijado.

## Brechas para producción

La red actual utiliza un único host físico e identidades `cryptogen`. Producción
requiere infraestructura independiente por organización, Fabric CA o un ciclo
de vida equivalente, TLS de ingreso, secretos administrados/HSM,
backup/restore del estado del ledger, alta disponibilidad, observabilidad,
OIDC, rate limiting distribuido, políticas formales y revisión de seguridad. La red oficial
de pruebas nunca debe presentarse como producción.
