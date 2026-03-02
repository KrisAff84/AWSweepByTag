output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.test.arn
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.test.function_name
}
