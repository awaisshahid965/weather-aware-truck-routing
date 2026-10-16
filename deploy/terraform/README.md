# Oracle VM with Terraform

Creates a dedicated VCN, Internet Gateway, route table, security list, public
subnet, and Ubuntu 24.04 ARM VM. The VM has 2 OCPUs, 12 GB RAM, and a 50 GB Balanced
boot disk. Startup installs Docker Engine and Compose from Docker's official apt
repository. Only TCP 80/443 are public; SSH is allowed from your specified IPv4
address. No database, load balancer, NAT gateway, or paid DNS zone is created.

These sizes fit the [published Always Free limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
only when your account has the corresponding allowance available and you use your
home region. Existing resources count too. Terraform does not enforce your
account's total allowance or guarantee A1 capacity. Review existing compute and
storage usage before applying. Idle free instances can be reclaimed by Oracle.

## 1. Configure local Oracle authentication

In Oracle Console, open **Profile → User settings → API Keys → Add API Key**.
Generate a key pair, download the private key locally, and add its public key to
your account. Save the resulting configuration preview in `~/.oci/config` under
`[DEFAULT]`. Set `key_file` to the absolute path of the downloaded private key.
Keep the file outside the repository and restrict its permissions to your user.
Use your home region for the deployment. See [Oracle's API key instructions](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm)
and [provider authentication](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm).

The API key authorizes Terraform. The separate SSH key authorizes login to the VM.
Never supply either private key as a Terraform input or paste it into chat.

## 2. Supply deployment inputs

Install Terraform 1.6 or newer from [HashiCorp](https://developer.hashicorp.com/terraform/install).
From this directory:

```sh
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your home region, tenancy and compartment OCIDs, SSH
public key path, and your current public IPv4 address followed by `/32`.
For a root-compartment deployment, use the tenancy OCID for both OCID inputs.
The profile defaults to `DEFAULT`. If you have no SSH key, create a separate key
with `ssh-keygen -t ed25519 -f ~/.ssh/truck-routing` and supply its `.pub` path.
Do not overwrite an existing key. If your public IP changes later, update
`ssh_source_cidr` and apply the firewall update before reconnecting.

## 3. Validate, plan, and create

```sh
terraform init
terraform fmt -check
terraform validate
terraform plan -out=deployment.tfplan
```

Review the plan, including the exact shape, disk size, and firewall rules. Then:

```sh
terraform apply deployment.tfplan
terraform output -raw public_ip
```

Keep the local Terraform state: it tracks the resources for updates and removal.
State, variable values, and saved plans are gitignored. Commit the generated
`.terraform.lock.hcl` to retain the verified provider version and checksums.

An out-of-capacity error is an Oracle capacity limit, not a Terraform error. If
your home region has multiple availability domains, choose another valid
`availability_domain_index`, then run a new plan. A failed apply can leave the
network created; rerunning with the same state reuses it. Do not substitute a
paid shape merely to bypass the error.

## 4. Deploy the application

Terraform returning successfully means the VM exists; cloud-init may still be
installing Docker. Connect using the private key matching your public key:

```sh
ssh -i ~/.ssh/truck-routing ubuntu@PUBLIC_IP
sudo cloud-init status --wait
sudo test -f /var/lib/cloud/truck-routing-ready
sudo docker compose version
```

If startup fails, inspect `/var/log/cloud-init-output.log`. Cloud-init runs the
bootstrap script on first boot; editing it after creation does not automatically
rerun it on an existing VM.

Copy the application source to `/opt/truck-routing`, point your hostname's DNS at
the public IP, and follow the [production deployment guide](../README.md). Use
`sudo docker compose` on this VM. Transfer the HERE API key and Django secret
through SSH into a protected `.env.production`, outside Terraform. Application
secrets must not go into `user_data` or state. A free DNS hostname can be used;
DNS registration and app deployment are separate from this infrastructure stack.

Verify the public HTTPS health endpoint and run a real route search in the
browser before sharing the URL. If the VM is replaced, its ephemeral public IP
can change; update DNS and reconnect using the new output.

## Remove after the assessment

Run `terraform plan -destroy` to review the resources that would be removed.
Only when you want to delete this deployment, run `terraform destroy` and review
its confirmation. This removes the VM and its boot disk, including the deployed
app, secrets, and certificate data stored there. Keep your source separately.
