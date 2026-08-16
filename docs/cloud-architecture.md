# Arquitectura Cloud: Kubernetes (EKS) & Terraform (IaC) en FieldLedger

Este documento describe la arquitectura cloud empresarial, el aprovisionamiento mediante Infraestructura como Código (**Terraform**) y la orquestación de contenedores (**Kubernetes**) de **FieldLedger**. Está diseñado tanto como guía de implementación técnica como material de estudio para entrevistas DevOps y presentaciones comerciales a clientes de la industria de Oil & Gas.

---

## 1. Diagrama de Arquitectura en AWS (EKS)

```text
                                  [ INTERNET / CLOUDFLARE ]
                                              │
                                              ▼ :443 TLS
                               [ AWS Application Load Balancer ]
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    │                      AWS VPC                      │
                    │                                                   │
                    │   [ EKS Cluster v1.30 · Namespace: fieldledger ]   │
                    │   ┌───────────────────────────────────────────┐   │
                    │   │ Ingress Controller (NGINX / AWS ALB)      │   │
                    │   └─────────────────────┬─────────────────────┘   │
                    │                         │                         │
                    │         ┌───────────────┴───────────────┐         │
                    │         │                               │         │
                    │         ▼                               ▼         │
                    │   [ FastAPI Pods ]                [ Gateway Pod ] │
                    │   (HPA: 2 a 10 pods)              (Bridge Node.js)│
                    │         │                               │         │
                    │         ├──────────────┐                │ (gRPC)  │
                    │         ▼              ▼                ▼         │
                    │   [ Outbox Worker ] [ MinIO / S3 ] [ Fabric Peers]│
                    │   (Durable Queue)   (Evidencias)   (Org1 & Org2)  │
                    │         │                                         │
                    │         ▼                                         │
                    │   [ Amazon RDS PostgreSQL (Multi-AZ) ]            │
                    └───────────────────────────────────────────────────┘
```

---

## 2. Componentes de Infraestructura (Terraform)

El código fuente en [`infra/terraform/`](../../infra/terraform/) permite aprovisionar todo el entorno cloud con un solo comando:

| Archivo | Rol en la infraestructura |
|---|---|
| [`versions.tf`](../../infra/terraform/versions.tf) | Configuración de Terraform v1.5+, proveedores AWS, Kubernetes y Helm. |
| [`variables.tf`](../../infra/terraform/variables.tf) | Parámetros configurables (región, CIDRs, tipos de instancia, tamaño de clúster). |
| [`vpc.tf`](../../infra/terraform/vpc.tf) | VPC Multi-AZ con subredes públicas (ALB), privadas (EKS Nodes) y de base de datos (RDS), con NAT Gateways y tags `kubernetes.io/role/elb`. |
| [`eks.tf`](../../infra/terraform/eks.tf) | Clúster AWS EKS v1.30 con Managed Node Groups (`t3.medium`/`m5.large`) y auto-scaling de 2 a 10 nodos. |
| [`iam.tf`](../../infra/terraform/iam.tf) | Roles IAM para el control plane, worker nodes y **IRSA (IAM Roles for Service Accounts)** para acceso a S3 sin contraseñas estáticas. |
| [`s3.tf`](../../infra/terraform/s3.tf) | Bucket S3 para custodia de evidencias documentales con cifrado AES-256 (KMS), versionado y bloqueo de acceso público. |
| [`rds.tf`](../../infra/terraform/rds.tf) | Instancia Amazon RDS PostgreSQL 16 Multi-AZ con snapshots automáticos y protección contra borrado accidental. |
| [`outputs.tf`](../../infra/terraform/outputs.tf) | Endpoints, ARNs y comando listo para conectar `kubectl`: `aws eks update-kubeconfig`. |

### Despliegue con Terraform:
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply -auto-approve
```

---

## 3. Orquestación con Kubernetes (`infra/k8s/`)

Los manifiestos en [`infra/k8s/`](../../infra/k8s/) implementan las mejores prácticas de Kubernetes empresarial:

```text
infra/k8s/
├── namespace.yaml               # Aislamiento de recursos en namespace 'fieldledger'
├── configmap.yaml               # Variables de configuración desacopladas
├── secrets.yaml.example         # Plantilla para secretos (JWT, DB pass, MinIO keys)
├── postgres-statefulset.yaml    # PostgreSQL con PersistentVolumeClaim (PVC 20Gi)
├── minio-statefulset.yaml       # MinIO Object Storage con PVC 50Gi
├── gateway-deployment.yaml      # Bridge gRPC hacia Hyperledger Fabric
├── api-deployment.yaml          # FastAPI con RollingUpdate, initContainers y Probes
├── api-hpa.yaml                 # Escalado automático horizontal (2 a 10 pods)
├── worker-deployment.yaml       # Worker outbox transaccional (Singleton)
├── ingress.yaml                 # Enrutamiento Layer 7 con TLS (Cert-Manager)
└── kustomization.yaml           # Bundle Kustomize para despliegue unificado
```

### Despliegue en el clúster:
```bash
# 1. Configurar secretos
cp infra/k8s/secrets.yaml.example infra/k8s/secrets.yaml
# (Editar secrets.yaml con las credenciales correspondientes)

# 2. Desplegar todo el stack con Kustomize
kubectl apply -k infra/k8s/

# 3. Verificar estado de Pods y Servicios
kubectl get pods,svc,hpa -n fieldledger
```

---

## 4. Guía DevOps para Entrevistas Técnicas & Pitch a Clientes

### Pregunta 1: ¿Por qué migrar de Docker Compose a Kubernetes?
- **Docker Compose** es para entornos locales o de un solo servidor (como un prototipo en Raspberry Pi). Si el servidor físico falla, todo el sistema se cae (*Single Point of Failure*).
- **Kubernetes** distribuye la carga entre decenas de servidores:
  - **Auto-healing**: Si un Pod de FastAPI crashea o un nodo EC2 muere, K8s lo reinicia o reprograma en otro nodo en segundos.
  - **Zero-Downtime Rolling Updates**: Los despliegues cambian versiones sin cortar peticiones activas (`maxSurge: 1, maxUnavailable: 0`).
  - **Auto-scaling (HPA)**: Ante picos de ingesta de telemetría IoT de cientos de pozos, el clúster crea automáticamente más réplicas de la API.

---

### Pregunta 2: ¿EKS vs ECS en AWS? ¿Cuál elegir y por qué?
- **AWS ECS (Elastic Container Service)**:
  - *Ventajas*: Muy fácil de configurar, menor costo inicial de gestión, integración nativa profunda con AWS.
  - *Desventajas*: **Vendor lock-in** total (no podés mover tus definiciones de tareas a Azure, GCP ni a servidores on-premise).
- **AWS EKS (Elastic Kubernetes Service)**:
  - *Ventajas*: **Estándar de la industria**. Mismo código YAML en AWS, Google Cloud (GKE), Azure (AKS) o nubes privadas de empresas petroleras (OpenShift/Rancher). Ecosistema inmenso (Helm, Kustomize, ArgoCD, Prometheus, Cert-Manager, Istio).
  - *Desventajas*: Mayor curva de aprendizaje y costo fijo del control plane de AWS (~$73/mes por clúster).
- *Conclusión para clientes*: En empresas de Oil & Gas multinacionales, **EKS es la opción preferida** por cumplimiento de portabilidad multicloud y compatibilidad corporativa.

---

### Pregunta 3: ¿Cómo manejan la seguridad y credenciales en K8s?
- **IRSA (IAM Roles for Service Accounts)**: En lugar de guardar credenciales de AWS dentro del contenedor, el Pod asume un rol IAM mediante OIDC federado con AWS STS. Si el contenedor es comprometido, no hay claves estáticas que robar.
- **Health Probes**: `livenessProbe` para reiniciar pods congelados y `readinessProbe` para evitar enviar tráfico a un pod hasta que la base de datos y el ledger estén listos.
- **Resource Requests & Limits**: Se definen límites de CPU y Memoria en cada pod para evitar que un proceso hambriento ahogue a los demás (*Noisy Neighbor Problem*).
