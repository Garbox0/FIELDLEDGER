variable "aws_region" {
  description = "AWS region for all infrastructure resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "cluster_name" {
  description = "Name of the Amazon EKS cluster"
  type        = string
  default     = "fieldledger-eks"
}

variable "kubernetes_version" {
  description = "Kubernetes control plane version"
  type        = string
  default     = "1.30"
}

variable "vpc_cidr" {
  description = "CIDR block for the FieldLedger VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones to use for high availability"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "node_instance_types" {
  description = "EC2 instance types for EKS managed node group"
  type        = list(string)
  default     = ["t3.medium", "t3a.medium"]
}

variable "node_min_size" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum number of worker nodes during auto-scaling"
  type        = number
  default     = 10
}

variable "node_desired_size" {
  description = "Desired baseline number of worker nodes"
  type        = number
  default     = 3
}

variable "enable_rds_postgres" {
  description = "Deploy Amazon RDS PostgreSQL Multi-AZ instance (set to false for in-cluster Postgres)"
  type        = bool
  default     = true
}

variable "rds_instance_class" {
  description = "RDS PostgreSQL DB instance class"
  type        = string
  default     = "db.t4g.medium"
}

variable "rds_allocated_storage" {
  description = "Allocated storage in GB for RDS PostgreSQL"
  type        = number
  default     = 50
}

variable "rds_db_name" {
  description = "Database name for FieldLedger"
  type        = string
  default     = "fieldledger"
}

variable "rds_master_username" {
  description = "Master username for PostgreSQL"
  type        = string
  default     = "fieldledger_admin"
}

variable "documents_bucket_name" {
  description = "S3 bucket name for immutable evidence storage"
  type        = string
  default     = "fieldledger-evidence-documents-prod"
}
