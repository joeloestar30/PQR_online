# Oracle Cloud Always Free Deployment

This path runs the PQR web app and background worker on one Oracle Cloud Always Free VM, while keeping the database in Supabase PostgreSQL.

## Recommended Shape

Use an Always Free eligible Ubuntu VM:

```text
Image: Ubuntu
Shape: VM.Standard.A1.Flex
OCPUs: 1 or 2
Memory: 6 GB to 12 GB
```

Oracle's Always Free documentation currently lists Ampere A1 Compute allowance for `VM.Standard.A1.Flex` as 1,500 OCPU hours and 9,000 GB hours per month, equivalent to 2 OCPUs and 12 GB memory for Always Free tenancies.

## Create the VM

1. Open Oracle Cloud Console.
2. Go to Compute -> Instances -> Create instance.
3. Choose an Always Free eligible Ubuntu image.
4. Choose shape `VM.Standard.A1.Flex`.
5. Set 1 OCPU / 6 GB RAM for a conservative start, or 2 OCPUs / 12 GB RAM if available.
6. Add or generate an SSH key and save the private key safely.
7. Create the instance.

## Open Network Access

In the VM's VCN/subnet security list or network security group, add ingress rules:

```text
Port 22: your IP only, for SSH
Port 80: 0.0.0.0/0, for HTTP
Port 443: 0.0.0.0/0, for HTTPS later
```

Ubuntu images on Oracle Cloud may also require host firewall/iptables changes for ports 80 and 443.

## Install PQR

SSH into the VM:

```bash
ssh -i path/to/private_key ubuntu@YOUR_ORACLE_PUBLIC_IP
```

Run the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/joeloestar30/PQR_online/main/pqr_web_app/deploy/oracle/install_ubuntu.sh -o install_ubuntu.sh
sudo bash install_ubuntu.sh
```

Edit the environment file:

```bash
sudo nano /etc/pqr/pqr.env
```

Set real values for:

```text
SECRET_KEY
DATABASE_URL
PQR_ADMIN_PASSWORD
PQR_ADMIN_EMAIL
GOOGLE_SERVICE_ACCOUNT_JSON
PQR_GOOGLE_SHEET_ID
```

Restart services:

```bash
sudo systemctl restart pqr-web pqr-worker
sudo systemctl status pqr-web pqr-worker --no-pager
```

Open:

```text
http://YOUR_ORACLE_PUBLIC_IP
```

## Logs

```bash
sudo journalctl -u pqr-web -f
sudo journalctl -u pqr-worker -f
```

## Updating the App

```bash
cd /opt/pqr/PQR_online
sudo git pull --ff-only
sudo chown -R pqr:pqr /opt/pqr
sudo -u pqr /opt/pqr/PQR_online/pqr_web_app/.venv/bin/pip install -r /opt/pqr/PQR_online/pqr_web_app/requirements.txt
sudo systemctl restart pqr-web pqr-worker
```

## HTTPS Later

After you point a domain name to the Oracle public IP, install Certbot and issue a Let's Encrypt certificate for the domain. Keep port 80 open for renewal checks.

