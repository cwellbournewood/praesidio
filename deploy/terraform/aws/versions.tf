terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # State backend — uncomment and configure for your environment.
  # backend "s3" {
  #   bucket         = "my-tf-state"
  #   key            = "section/aws/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "tf-lock"
  #   encrypt        = true
  # }
}
