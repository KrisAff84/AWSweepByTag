# Test Infrastructure

Terraform configuration for testing AWS resource deletion with awsweepbytag.

## Usage

```bash
# Initialize
terraform init

# Plan
terraform plan

# Apply
terraform apply

# Destroy
terraform destroy
```

## Toggle Resources

Edit `terraform.tfvars` to enable/disable resources:

```hcl
enable_vpc    = true
enable_lambda = true
```

## Resources Created

All resources are tagged with `Delete: true` for testing deletion.

- VPC with DNS support
- 2 public subnets
- 2 private subnets
- Internet Gateway
- NAT Gateway with Elastic IP
- Public and private route tables
- Lambda function in private subnet with security group
