provider "aws" {
    region = "us-east-1"
}

resource "aws_security_group_rule" "example" {
    # fails tfscan check AWS006
    type        = "ingress"
    cidr_blocks = ["0.0.0.0/0"]
    description = "This is an example insecure rule for tfsec testing"
}
