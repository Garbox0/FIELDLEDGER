# Amazon RDS PostgreSQL Multi-AZ Instance

resource "aws_db_subnet_group" "rds" {
  count       = var.enable_rds_postgres ? 1 : 0
  name        = "fieldledger-rds-subnet-group-${var.environment}"
  subnet_ids  = aws_subnet.database[*].id
  description = "Subnet group for FieldLedger PostgreSQL database"

  tags = {
    Name = "fieldledger-rds-subnet-group"
  }
}

resource "random_password" "rds_password" {
  count   = var.enable_rds_postgres ? 1 : 0
  length  = 24
  special = false
}

resource "aws_security_group" "rds" {
  count       = var.enable_rds_postgres ? 1 : 0
  name        = "fieldledger-rds-sg-${var.environment}"
  description = "Controls access to FieldLedger RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Allow inbound PostgreSQL from EKS worker nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.cluster.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "fieldledger-rds-sg"
  }
}

resource "aws_db_instance" "postgres" {
  count                  = var.enable_rds_postgres ? 1 : 0
  identifier             = "fieldledger-postgres-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = var.rds_instance_class
  allocated_storage      = var.rds_allocated_storage
  max_allocated_storage  = 200
  storage_type           = "gp3"
  db_name                = var.rds_db_name
  username               = var.rds_master_username
  password               = random_password.rds_password[0].result
  db_subnet_group_name   = aws_db_subnet_group.rds[0].name
  vpc_security_group_ids = [aws_security_group.rds[0].id]

  multi_az                = var.environment == "prod" ? true : false
  publicly_accessible     = false
  skip_final_snapshot     = var.environment == "prod" ? false : true
  final_snapshot_identifier = "fieldledger-postgres-final-snapshot"
  backup_retention_period = 14
  deletion_protection     = var.environment == "prod" ? true : false

  tags = {
    Name = "fieldledger-postgres"
  }
}
