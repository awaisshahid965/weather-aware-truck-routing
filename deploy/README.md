# Production deployment

This guide puts the app on one Oracle Cloud VM, with HTTPS.

## What runs on the VM

```text
Browser ──HTTPS──► Caddy (ports 80, 443)
                     ├─ /api/* and /healthz ──► backend  (Django, port 8000)
                     └─ everything else ─────► frontend (Next.js, port 3000)
```

- [Caddy](https://caddyserver.com/) gets a free HTTPS certificate from Let's Encrypt and renews it. It also compresses responses.
- Only Caddy is open to the internet. The backend and frontend talk to Caddy inside Docker.
- The browser and the API share one address, so no CORS setup is needed.
- The files are [`compose.production.yaml`](../compose.production.yaml), [`Caddyfile`](Caddyfile) and [`.env.production.example`](../.env.production.example).

## What you need

- An Oracle Cloud account, with an API key in `~/.oci/config`.
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.6 or newer.
- A HERE API key.
- A web address (a hostname). Step 3 shows two free ways to get one.

## 1. Create the VM

Follow [`terraform/README.md`](terraform/README.md). In short:

1. Make an SSH key: `ssh-keygen -t ed25519 -f ~/.ssh/truck-routing`
2. Find your public IP: `curl -4 ifconfig.me`
3. In `deploy/terraform`, copy `terraform.tfvars.example` to `terraform.tfvars` and fill it in.
4. Run `terraform init`, then `terraform plan -out=deployment.tfplan`, then `terraform apply deployment.tfplan`.
5. Write down the IP from `terraform output -raw public_ip`.

## 2. Wait for the VM to finish its setup

The VM installs Docker on its first start. Log in and wait:

```sh
ssh -i ~/.ssh/truck-routing ubuntu@YOUR_IP
sudo cloud-init status --wait
```

Wait until it says `done`. If it says `error`, read `/var/log/cloud-init-output.log`.

## 3. Get a web address

HTTPS needs a name, not just an IP. Point a name at your VM's IP. Two free options:

- **sslip.io.** No sign-up. If your IP is `1.2.3.4`, your address is `1-2-3-4.sslip.io`.
- **DuckDNS.** Sign in at [duckdns.org](https://www.duckdns.org/), choose a name, and enter your IP.

Check that the name points to your VM. This should print your IP:

```sh
getent hosts YOUR_ADDRESS
```

## 4. Download the code

On the VM:

```sh
git clone https://github.com/awaisshahid965/weather-aware-truck-routing.git /opt/truck-routing
cd /opt/truck-routing
```

## 5. Add your secrets

Make the file, and lock it so only you can read it:

```sh
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Fill in three values:

| Name | Value |
|---|---|
| `APP_DOMAIN` | Your address from step 3. No `https://`, no slash. |
| `DJANGO_SECRET_KEY` | A new random value. Make one with `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `HERE_API_KEY` | Your HERE key. |

Never commit this file. Git already ignores it.

## 6. Start the app

```sh
sudo docker compose --env-file .env.production -f compose.production.yaml up --build -d --wait
```

The first build takes several minutes. Later builds are faster.

Every `docker compose` command needs both `--env-file .env.production` and `-f compose.production.yaml`. Without the env file, Compose stops with "Set APP_DOMAIN in .env.production", even for `ps` or `logs`.

## 7. Check that it works

1. Open `https://YOUR_ADDRESS/healthz`. It should show `{"status": "ok"}`.
2. Open `https://YOUR_ADDRESS`. Plan Pittsburgh → Cleveland. You should see 3 routes, the map and the heatmap.
3. Plan Dallas → Houston. You should see 2 routes and a notice saying only 2 were found.
4. Try it on a phone too.

## Update the app later

On the VM:

```sh
cd /opt/truck-routing
git pull
sudo docker compose --env-file .env.production -f compose.production.yaml up --build -d --wait
```

## When something goes wrong

Start by looking at the containers and their logs:

```sh
cd /opt/truck-routing
sudo docker compose --env-file .env.production -f compose.production.yaml ps
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 proxy
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 backend
```

| Problem | What to do |
|---|---|
| The browser can't connect at all. | Check that `APP_DOMAIN` points to the VM (step 3). Check that ports 80 and 443 are open: Terraform opens them, and the VM's setup allows them. |
| The browser warns about the certificate. | Read the `proxy` log. Caddy needs the address to point at the VM before it can get a certificate. If sslip.io fails, use DuckDNS. |
| The backend keeps restarting. | Read the `backend` log. The startup check stops the app when a setting is unsafe or missing, such as an empty `DJANGO_SECRET_KEY`. |
| Planning a trip fails with a provider error. | Check `HERE_API_KEY` in `.env.production`, then run the step 6 command again. |
| SSH stops working. | Your home IP has probably changed. Update `ssh_source_cidr` in `terraform.tfvars` and run `terraform apply` again. |
| `terraform apply` says "Out of host capacity". | Oracle has no free ARM machines right now. Try again later. |

## Good to know

- **Oracle can stop free VMs that sit idle.** Open the site before you share the link.
- **Open-Meteo's free API is for non-commercial use.** A demo or assessment is fine. A business would need its paid plan.
- **Restarts are automatic.** The containers start again after a VM reboot.
- **Daily limits keep the HERE bill at $0.** The site allows 125 route plans and 600 place searches a day, then says "try again after midnight UTC". This keeps a month inside HERE's free allowance. Your own local testing uses the same HERE key, so it counts toward HERE's allowance too. A redeploy starts the day's counts again, so don't redeploy many times in one day.

## Remove everything

When you no longer need the site, run this in `deploy/terraform`:

```sh
terraform destroy
```

This deletes the VM and everything on it, including the secrets and the certificate. Your code stays on GitHub.
