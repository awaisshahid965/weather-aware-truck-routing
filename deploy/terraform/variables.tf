variable "region" {
  description = "Your Oracle home region, where Always Free resources are available."
  type        = string
}

variable "oci_profile" {
  description = "Profile in ~/.oci/config containing the API signing credentials."
  type        = string
  default     = "DEFAULT"
}

variable "tenancy_ocid" {
  description = "Tenancy OCID, used to list availability domains."
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment for these resources; use your tenancy OCID for the root compartment."
  type        = string
}

variable "availability_domain_index" {
  description = "One-based availability domain index. Try another available domain if A1 capacity is exhausted."
  type        = number
  default     = 1
  validation {
    condition     = var.availability_domain_index >= 1 && floor(var.availability_domain_index) == var.availability_domain_index
    error_message = "Choose a positive integer availability domain index."
  }
}

variable "ssh_public_key_path" {
  description = "Local path to an existing OpenSSH PUBLIC key (.pub), not the private key or OCI API signing key."
  type        = string
  validation {
    condition     = can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+) ", trimspace(file(pathexpand(var.ssh_public_key_path)))))
    error_message = "Provide a readable OpenSSH public key file."
  }
}

variable "ssh_source_cidr" {
  description = "Your current public IPv4 address followed by /32; only this address can SSH into the VM."
  type        = string
  validation {
    condition     = can(cidrnetmask(var.ssh_source_cidr)) && endswith(var.ssh_source_cidr, "/32")
    error_message = "Use your single public IPv4 address with /32, not 0.0.0.0/0."
  }
}
