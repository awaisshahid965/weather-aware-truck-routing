terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "9.10.0"
    }
  }
}

# Authentication comes from ~/.oci/config. Never put private keys in Terraform.
provider "oci" {
  region              = var.region
  config_file_profile = var.oci_profile
}
