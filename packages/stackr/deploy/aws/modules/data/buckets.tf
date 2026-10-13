# The S3 buckets (RFC-0004): Langfuse's events and media, the telemetry stores' blocks (Tempo,
# Loki and Pyroscope, each under its own prefix), backups, and the ALB's access logs. None is
# public, each is encrypted and versioned, and each refuses requests that don't use TLS. The
# access logs' bucket also lets ELB's log delivery write, for this account's load balancers only,
# under alb/.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  # ELB writes its logs with S3's own keys (SSE-S3), the only encryption it supports.
  access_logs_prefix = "alb"
}

# Bucket names are global: each gets a unique suffix after <name>-<role>-.
resource "aws_s3_bucket" "this" {
  for_each      = var.buckets
  bucket_prefix = "${var.name}-${each.key}-"
  force_destroy = var.force_destroy_buckets
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = var.buckets
  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id

  rule {
    id     = "tidy"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = var.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([{
      Sid       = "TLSOnly"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.this[each.key].arn, "${aws_s3_bucket.this[each.key].arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }], each.key != "access-logs" ? [] : [{
      Sid       = "ELBAccessLogs"
      Effect    = "Allow"
      Principal = { Service = "logdelivery.elasticloadbalancing.amazonaws.com" }
      Action    = "s3:PutObject"
      Resource  = "${aws_s3_bucket.this[each.key].arn}/${local.access_logs_prefix}/AWSLogs/${local.account}/*"
      Condition = {
        ArnLike = { "aws:SourceArn" = "arn:${data.aws_partition.current.partition}:elasticloadbalancing:${data.aws_region.current.region}:${local.account}:loadbalancer/*" }
      }
    }])
  })
  depends_on = [aws_s3_bucket_public_access_block.this]
}
