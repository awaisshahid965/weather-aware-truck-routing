locals {
  name = "weather-truck-routing"
}

data "oci_identity_availability_domains" "available" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  state                    = "AVAILABLE"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_vcn" "app" {
  compartment_id = var.compartment_ocid
  display_name   = local.name
  cidr_blocks    = ["10.42.0.0/16"]
  dns_label      = "truckrouting"
}

resource "oci_core_internet_gateway" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = local.name
  enabled        = true
}

resource "oci_core_route_table" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = local.name
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.app.id
  }
}

resource "oci_core_security_list" "app" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.app.id
  display_name   = local.name

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    description = "Package downloads, DNS, certificates, and routing/weather APIs"
  }

  ingress_security_rules {
    protocol    = "6"
    source      = var.ssh_source_cidr
    description = "SSH from the deployment computer only"
    tcp_options {
      min = 22
      max = 22
    }
  }

  dynamic "ingress_security_rules" {
    for_each = toset([80, 443])
    content {
      protocol    = "6"
      source      = "0.0.0.0/0"
      description = "Public website"
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }

  ingress_security_rules {
    protocol    = "1"
    source      = "0.0.0.0/0"
    description = "Path MTU discovery"
    icmp_options {
      type = 3
      code = 4
    }
  }
}

resource "oci_core_subnet" "app" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.app.id
  display_name               = local.name
  cidr_block                 = "10.42.1.0/24"
  dns_label                  = "public"
  route_table_id             = oci_core_route_table.app.id
  security_list_ids          = [oci_core_security_list.app.id]
  prohibit_public_ip_on_vnic = false
}

# Fixed size deliberately stays within the published A1 free allowance for an
# otherwise unused tenancy. Terraform cannot guarantee account-wide free usage.
resource "oci_core_instance" "app" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.available.availability_domains[var.availability_domain_index - 1].name
  display_name        = local.name
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu.images[0].id
    boot_volume_size_in_gbs = 50
    boot_volume_vpus_per_gb = 10
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.app.id
    assign_public_ip = true
    hostname_label   = "truckrouting"
  }

  metadata = {
    ssh_authorized_keys = trimspace(file(pathexpand(var.ssh_public_key_path)))
    user_data           = filebase64("${path.module}/bootstrap.sh")
  }

  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }

  lifecycle {
    # A newly published Ubuntu image must not replace a running reviewer demo.
    ignore_changes = [source_details[0].source_id]
  }
}
