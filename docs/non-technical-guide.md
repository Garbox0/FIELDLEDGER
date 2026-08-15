# FieldLedger: guía de explicación no técnica

Esta guía sirve para contar el proyecto a gerentes, auditores o entrevistadores
sin entrar de inmediato en el código y sin atribuirle funciones que todavía no
tiene.

## Explicación en una frase

> FieldLedger guarda el trabajo diario en una aplicación convencional y usa
> una blockchain privada para que operadora, contratista y auditor puedan
> comprobar los hitos importantes y la integridad de los documentos.

## El problema que resuelve

Un equipo de Oil & Gas puede pertenecer a una empresa, ser mantenido por otra y
auditado por una tercera. Cada una puede tener una base, informe, correo o PDF
distinto. Cuando las copias no coinciden, demostrar qué se entregó y qué se
aceptó resulta lento.

FieldLedger les da un mismo flujo de trabajo. Los pasos acordados también se
registran en un ledger que una sola de las partes no puede reescribir por su
cuenta.

## Por qué no se coloca todo en blockchain

Cada tecnología tiene una función:

| Componente | Analogía sencilla | Qué contiene |
|---|---|---|
| PostgreSQL | Archivador de trabajo | usuarios, activos, eventos, estados y metadatos consultables |
| MinIO | Archivo privado de evidencia | PDF e imágenes completas |
| Hyperledger Fabric | Libro notarial compartido | IDs, decisiones, fechas, hashes e historial de transacciones |
| Gateway/worker | Mensajero seguro | reintenta hechos aprobados hasta que el ledger los confirma |

Los documentos grandes y las lecturas frecuentes de sensores no pertenecen al
ledger: son privados, costosos de replicar y más fáciles de administrar en
sistemas específicos. Fabric se usa solo donde organizaciones separadas
necesitan evidencia conjunta.

Si una sola empresa confiable controlara a todos los escritores, podría bastar
una base bien auditada. La blockchain se justifica por el límite de confianza
entre organizaciones, no por moda.

## Organizaciones y responsabilidades

| Participante | Responsabilidad |
|---|---|
| OperatorOrg / Operadora | Posee u opera el activo y acepta o rechaza trabajos. |
| ContractorOrg / Contratista | Ejecuta y propone el mantenimiento. |
| AuditorOrg / Auditor | Comprueba de manera independiente el historial y los hashes. |
| Viewer | Lee información sin modificarla. |
| Admin | Opera la aplicación de laboratorio; no reemplaza el gobierno empresarial. |

La contratista no puede aprobar su propia propuesta. En el ledger, la creación
y revisión usan el certificado de OperatorOrg; la propuesta usa el de
ContractorOrg.

## Cómo explicar cada sección del producto

### Login e identidad

El login prueba qué usuario de la aplicación está actuando. Las contraseñas se
protegen con Argon2 y el usuario recibe un token firmado de corta duración.
Fabric usa una segunda identidad por certificado, correspondiente a la
organización. Así una contraseña web no es también una clave de blockchain.

### Activos

Un activo es el equipo cuyo historial importa: válvula, bomba, compresor, pozo,
sensor o tramo de ducto. La aplicación guarda detalles operativos útiles; el
ledger ancla su identidad compacta.

La sección responde: “¿Qué equipo es, dónde está y a qué registro común se
refieren todas las partes?”.

### Mantenimiento

La contratista describe el trabajo y presenta un evento `PROPOSED`. La
operadora toma la decisión independiente: `APPROVED` o `REJECTED`. Un rechazo
requiere motivo.

La base ofrece un flujo inmediato. Una cola durable entrega propuesta y
decisión a Fabric en orden. Una caída temporal no pierde el registro ni produce
un falso éxito de blockchain.

### Documentos y SHA-256

El informe completo permanece en MinIO privado. FieldLedger calcula una huella
SHA-256 a partir de cada byte y registra esa huella en Fabric.

Modificar un solo byte cambia la huella. Para verificar, el auditor sube una
copia; FieldLedger vuelve a calcularla y consulta si ese valor exacto fue
registrado.

SHA-256 no cifra el archivo ni prueba que sus afirmaciones sean verdaderas.
Prueba que el archivo revisado coincide byte por byte con aquel cuya huella
ingresó al ledger compartido.

### Estado del ledger e ID de transacción

| Estado | Significado |
|---|---|
| `PENDING` | Encolado de forma segura en PostgreSQL; todavía no enviado. |
| `SUBMITTED` | Fabric lo está procesando. |
| `COMMITTED` | Fabric confirmó una transacción y bloque reales. |
| `FAILED` | El intento falló y el worker lo reintentará. |

Un ID de 64 caracteres y el número de bloque son evidencia devuelta por la red
real. FieldLedger nunca presenta `PENDING` o `FAILED` como “en blockchain”.

### Hyperledger Fabric

Fabric es una blockchain permisionada: participan organizaciones conocidas e
identificadas por certificados. No hay moneda, token, minería, gas ni proof of
work.

El canal de laboratorio incluye operadora, contratista y auditor. Toda
escritura requiere el endorsement de operadora y contratista. El auditor
pertenece al canal y puede verificar registros de manera independiente.

### Raspberry Pi

La Pi es un host de laboratorio dedicado. Ejecuta API, base, archivo de
evidencia, worker, gateway, tres peers y orderer en contenedores aislados. Solo
la API se vincula al loopback local; no se publicó nada automáticamente.

El HDD tiene defectos físicos. Aunque una región posterior superó un escaneo de
lectura, al formatearla se produjeron reinicios USB. Por eso fue descartado y
puesto en cuarentena por software hasta su reemplazo. Todos los datos quedan en
la SD saludable, con controles previos a backups y umbrales visibles de 10/15
GiB.

### Interfaz web

La interfaz reúne el flujo completo en español: login, activos, propuestas,
evidencia, decisiones, estado del ledger y verificación. Cada rol ve las
acciones que le corresponden, pero la seguridad real se vuelve a comprobar en
la API; ocultar un botón no concede ni reemplaza permisos.

No se agregó un framework de frontend. HTML, CSS y JavaScript nativos alcanzan
para las pantallas actuales y agregan menos carga a la Pi.

## Guion de la demo

El recorrido es el siguiente:

1. Una operadora da de alta una válvula identificada de forma única.
2. Una contratista propone mantenimiento preventivo.
3. La contratista sube un informe PDF.
4. FieldLedger valida el archivo y calcula SHA-256.
5. El PDF va a MinIO; la transacción y su huella se encolan juntas.
6. La operadora aprueba el evento.
7. El worker registra activo, propuesta, huella y decisión en Fabric.
8. Cada operación recibe ID de transacción y número de bloque reales.
9. El auditor carga el PDF original y obtiene `verified=true`.
10. El auditor carga una copia modificada y obtiene `verified=false`.

La última aceptación de Fabric utilizó los bloques 21 a 24. La interfaz web ya
está desplegada y conectada al backend; queda realizar la aceptación visual
manual del relato completo y capturar material de portfolio sin datos sensibles.

## Cómo presentarlo en una entrevista

### Pitch de 30 segundos

> Construí FieldLedger para probar un flujo de mantenimiento entre una
> operadora, una contratista y un auditor. La aplicación corre en una Raspberry
> Pi con FastAPI, PostgreSQL y MinIO. Los documentos quedan privados y Fabric
> registra sus huellas y los cambios de estado. Si la red se demora, una outbox
> conserva la operación y la reintenta. Los IDs de transacción y los bloques que
> se ven en la demo son reales.

### Qué muestra de tu trabajo

- análisis de dominio y separación entre datos operativos y evidencia;
- backend Python, modelado SQL, migraciones y autorización por roles;
- integración blockchain empresarial y chaincode TypeScript;
- consistencia distribuida, idempotencia, reintentos y estados observables;
- almacenamiento de objetos e integridad criptográfica;
- Docker, operación Linux/ARM64, seguridad básica, backups y diagnóstico;
- documentación de límites, fallas encontradas y tareas pendientes.

### Cómo ofrecerlo a una petrolera

No conviene presentarlo como “una blockchain lista para instalar”. El punto de
partida sería elegir un problema pequeño que hoy obligue a comparar planillas,
correos o PDFs: por ejemplo, inspecciones de válvulas, certificados de
mantenimiento o aceptación de trabajos entre empresas.

Antes de armar un piloto habría que:

1. identificar las organizaciones y quién avala cada hito;
2. medir cuánto cuesta hoy reconciliar evidencia o resolver disputas;
3. seleccionar pocos hechos que realmente requieren verificación compartida;
4. definir privacidad, retención, regulación y sistemas existentes;
5. ejecutar un piloto sin control directo sobre equipos de campo;
6. evaluar resultados antes de diseñar infraestructura productiva.

La prueba tiene sentido si permite medir menos tiempo comparando versiones,
aprobaciones más claras o menos discusiones sobre qué archivo se entregó. La
blockchain por sí sola no es el resultado.

## Respuestas a preguntas habituales

### “¿Qué impide que una empresa cambie el historial?”

PostgreSQL sigue siendo editable para la operación normal, pero ciertos hechos
también se confirman en Fabric. Las escrituras requieren el aval de peers de
operadora y contratista. Una corrección posterior genera nueva historia en
lugar de reemplazar silenciosamente la transacción anterior.

### “¿Qué ocurre si la blockchain se cae?”

La transacción de negocio y la intención de entrega se guardan juntas en
PostgreSQL. El worker reintenta la misma operación idempotente. El usuario ve
un estado pendiente o fallido hasta que Fabric confirma.

### “¿El auditor puede leer el PDF confidencial desde blockchain?”

No. Fabric conserva la huella y un contexto compacto, no el archivo. El acceso
al documento sigue controlado por la aplicación y el object storage.

### “¿Es un proyecto de criptomonedas?”

No. Fabric es un ledger empresarial permisionado. FieldLedger no tiene token,
wallet, minería, precio de mercado ni red pública de consenso.

### “¿Está listo para producción?”

No. Es un prototipo de laboratorio funcional y apto para portfolio. La
integración real con el ledger está probada, pero la topología usa un único
host, la red oficial de pruebas e identidades de laboratorio.

Producción todavía requiere infraestructura independiente por organización,
ciclo de vida de certificados/HSM, TLS, OIDC, rate limiting, gestión de
secretos, alta disponibilidad, recuperación externa, observabilidad, gobierno
formal y revisión de seguridad.

## Implementado versus próximo

Implementado y verificado:

- despliegue dedicado en Raspberry Pi;
- login, roles, activos y propuesta/revisión de mantenimiento;
- evidencia privada y SHA-256;
- red Fabric de tres organizaciones y contrato TypeScript;
- cola durable de reintentos y gateway privado;
- IDs, bloques, historial y verificación de evidencia reales;
- pruebas automatizadas, control de migraciones, backups y healthchecks.

Pendiente:

- aceptación visual, capturas y video breve del flujo web;
- telemetría MQTT y anclaje por lotes;
- Prometheus/Grafana y despliegue continuo;
- IAM empresarial, certificados productivos, HA y gobierno multi-host.

Estado actual: el flujo de integridad funciona de punta a punta. La interfaz
todavía necesita una aceptación visual completa y el despliegue no tiene las
condiciones operativas de un sistema de producción.
