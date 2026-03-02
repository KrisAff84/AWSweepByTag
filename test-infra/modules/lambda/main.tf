resource "aws_security_group" "lambda" {
  name        = "test-lambda-sg"
  description = "Security group for test Lambda function"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # tags = merge(var.common_tags, {
  #   Name = "test-lambda-sg"
  # })
}

resource "aws_iam_role" "lambda" {
  name = "test-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/lambda.zip"

  source {
    content  = <<EOF
def handler(event, context):
    return {
        'statusCode': 200,
        'body': 'Hello from test Lambda!'
    }
EOF
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "test" {
  filename         = data.archive_file.lambda.output_path
  function_name    = "test-vpc-lambda"
  role             = aws_iam_role.lambda.arn
  handler          = "lambda_function.handler"
  source_code_hash = data.archive_file.lambda.output_base64sha256
  runtime          = "python3.12"

  vpc_config {
    subnet_ids         = [var.private_subnet_ids[0]]
    security_group_ids = [aws_security_group.lambda.id]
  }

  # tags = merge(var.common_tags, {
  #   Name = "test-vpc-lambda"
  # })
}
