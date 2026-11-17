# Single-host Docker deployment with Terraform

This example builds the image from the checkout and manages an API, read-only viewer, one Celery worker, one scheduler, Redis, a private Docker network and a persistent data volume. It does not provision a VM, DNS or TLS. Point the Docker provider at your intended host using its normal configuration. Keep SQLite and its shared volume on one host.

```sh
terraform init
cp terraform.tfvars.example terraform.tfvars
# Edit the nonsecret origins/addresses and the existing secret-file paths.
terraform plan
terraform apply
```

The example publishes only to host loopback by default. Put a trusted HTTPS proxy in front of the owner and viewer ports, set their external base URLs and configure OIDC's exact callback. Use `listen_address` only when your networking plan requires a different interface. `api_port` / `viewer_port` set both listener and published ports; use those variables rather than overriding the equivalent environment keys.

`environment` contains deployment settings; see [the environment reference](../../docs/configuration.md). `secret_files` maps variable names without `_FILE` to existing absolute files on the Docker host. Bind mounts are read-only. Contents never pass through Terraform expressions; files must be readable by the image's uid 10001. If you put passwords directly in `environment`, Terraform will store them in state, even if a variable is marked sensitive.

First-admin bootstrap runs only on an empty users table. Remove the bootstrap password mount after successful initialization; keep OIDC/SMTP secret mounts for the services using them. The data volume also stores the generated encryption key for settings configured through the UI. Back it up with the database.

The volume has `prevent_destroy=true`: an ordinary destroy will stop with a protection error rather than delete your tickets. Explicitly change that lifecycle rule only if you intend to remove the data. No infrastructure was applied as part of the repository preparation; this example is validated configuration for your deployment agent to adapt.
