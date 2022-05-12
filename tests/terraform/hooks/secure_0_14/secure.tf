variable "string" {
  # This will fail if run with terraform >= 0.15
  type = "string"
}

terraform {
  required_version = ">= 0.14.11"
}
