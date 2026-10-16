output "public_ip" {
  description = "VM public IP; use this for SSH and the website DNS record."
  value       = oci_core_instance.app.public_ip
}

output "instance_ocid" {
  value = oci_core_instance.app.id
}

output "ssh_user" {
  value = "ubuntu"
}
