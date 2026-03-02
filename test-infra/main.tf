terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  profile = "kris84"
  region  = var.aws_region
}

module "vpc" {
  source = "./modules/vpc"
  count  = var.enable_vpc ? 1 : 0

  vpc_cidr            = var.vpc_cidr
  availability_zones  = var.availability_zones
  common_tags         = var.common_tags
}

module "lambda" {
  source = "./modules/lambda"
  count  = var.enable_lambda && var.enable_vpc ? 1 : 0

  vpc_id             = module.vpc[0].vpc_id
  private_subnet_ids = module.vpc[0].private_subnet_ids
  common_tags        = var.common_tags
}
