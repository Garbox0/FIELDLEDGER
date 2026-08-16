output = {
  cluster_id             = aws_eks_cluster.main.id
  cluster_endpoint       = aws_eks_cluster.main.endpoint
  cluster_name           = aws_eks_cluster.main.name
  cluster_security_group = aws_security_group.cluster.id
  vpc_id                 = aws_vpc.main.id
  public_subnet_ids      = aws_subnet.public[*].id
  private_subnet_ids     = aws_subnet.private[*].id
  s3_documents_bucket    = aws_s3_bucket.documents.id
  s3_documents_arn       = aws_s3_bucket.documents.arn
  rds_endpoint           = var.enable_rds_postgres ? aws_db_instance.postgres[0].endpoint : "In-Cluster"
  kubeconfig_command     = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}
