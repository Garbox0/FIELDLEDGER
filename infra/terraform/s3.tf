# S3 Bucket for Immutable Evidence Documents

resource "aws_s3_bucket" "documents" {
  bucket        = var.documents_bucket_name
  force_destroy = false

  tags = {
    Name        = var.documents_bucket_name
    Purpose     = "PrivateEvidenceStorage"
    Compliance  = "ImmutableAuditTrail"
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
