# Guía de Operación: Kubernetes (K3s) en Raspberry Pi 5 / 4

Esta guía documenta la instalación, configuración del kernel y operación del clúster de **Kubernetes (K3s v1.36)** ejecutándose en la Raspberry Pi de **FieldLedger**.

---

## 1. Estado del Clúster en la Raspberry Pi

```bash
$ kubectl get nodes -o wide
NAME              STATUS   ROLES           AGE   VERSION        INTERNAL-IP     CONTAINER-RUNTIME
judicia-scraper   Ready    control-plane   10m   v1.36.3+k3s1   192.168.0.179   containerd://2.3.2-k3s2
```

### Servicios del Sistema Incluidos:
- **CoreDNS**: Resolución interna de nombres DNS entre microservicios (`*.svc.cluster.local`).
- **Local-Path-Provisioner**: Aprovisionamiento dinámico de volúmenes persistentes (`PersistentVolumeClaim`).
- **Metrics-Server**: Monitoreo de CPU/RAM en tiempo real para `kubectl top` y autoscaling (HPA).
- **Traefik Ingress Controller**: Enrutador Layer 7 HTTP/HTTPS integrado.

---

## 2. Configuración Requerida en el Kernel de Raspberry Pi

Kubernetes requiere que los controladores de memoria de cgroups estén habilitados en el arranque de Linux para limitar recursos de contenedores.

En `/boot/firmware/cmdline.txt`, se agregaron al final de la línea:
```text
cgroup_memory=1 cgroup_enable=memory
```
*(Se preservó una copia de seguridad en `/boot/firmware/cmdline.txt.bak`).*

---

## 3. Comandos de Control del Servicio K3s

K3s corre como un servicio `systemd` nativo sin interferir con Docker:

```bash
# Ver estado del servicio
sudo systemctl status k3s

# Reiniciar Kubernetes
sudo systemctl restart k3s

# Detener Kubernetes temporalmente para liberar memoria
sudo systemctl stop k3s

# Iniciar Kubernetes
sudo systemctl start k3s
```

---

## 4. Cheat Sheet de `kubectl` para Operaciones Diarias

### Inspección del Clúster:
```bash
# Ver nodos y su estado
kubectl get nodes

# Ver consumo de CPU y RAM de cada nodo en tiempo real
kubectl top nodes

# Ver consumo de CPU y RAM de cada Pod
kubectl top pods -A
```

### Gestión de Workloads:
```bash
# Ver todos los pods en todos los namespaces
kubectl get pods -A

# Ver pods del namespace de FieldLedger
kubectl get pods -n fieldledger

# Ver logs en vivo de un Pod específico
kubectl logs -f <nombre-del-pod> -n fieldledger

# Entrar a la terminal interactiva de un contenedor en K8s
kubectl exec -it <nombre-del-pod> -n fieldledger -- /bin/sh

# Describir un Pod para diagnosticar problemas de arranque
kubectl describe pod <nombre-del-pod> -n fieldledger
```

---

## 5. Despliegue de FieldLedger en K3s

Para desplegar la aplicación completa con los manifiestos de [`infra/k8s/`](../../infra/k8s/):

```bash
cd /home/pi/fieldledger

# 1. Crear el secreto a partir de la plantilla
cp infra/k8s/secrets.yaml.example infra/k8s/secrets.yaml
# (Configurar credenciales si es necesario)

# 2. Desplegar todo el stack mediante Kustomize
kubectl apply -k infra/k8s/

# 3. Monitorear el despliegue
kubectl get pods,svc,pvc -n fieldledger -w

# 4. Eliminar el despliegue si se desea limpiar
kubectl delete -k infra/k8s/
```

---

## 6. Justificación Técnica para Entrevistas y Clientes (Edge Computing en Oil & Gas)

Cuando te pregunten sobre la elección de arquitectura en entrevistas o ante clientes:

> *"En la industria de Oil & Gas (como en yacimientos remotos de Vaca Muerta), la conectividad satelital puede ser intermitente. Implementamos un modelo híbrido: **Edge Computing con K3s** en hardware industrial/ARM en campo para procesamiento local de telemetría de pozos e ingesta ininterrumpida de evidencias, junto con **AWS EKS** en la nube central para auditorías globales y escalabilidad corporativa."*
