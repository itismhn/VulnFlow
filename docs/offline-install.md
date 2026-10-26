# Installing VulnFlow on a network without internet

VulnFlow runs as Docker images. To build those images you need internet: base images come from Docker Hub, and Python and npm packages come from their registries. The server you install on does not need internet. Prepare everything on a PC that has internet, copy one file over, and load it on the isolated server.

```
 Connected PC                    USB / file share                 Isolated server
 build images ──► vulnflow-offline.zip ───────────────────────► load images ──► run
```

## What you need

| Machine | Needs |
|---|---|
| Connected PC (Windows, macOS, or Linux) | Docker, a copy of this repository, and internet access |
| Isolated server | Docker with Compose v2, running **Linux containers** (see [Server requirements](#server-requirements)) |

The connected PC can have a different CPU from the server. For example, you can build on an Apple-silicon Mac for an x86 server. The build targets the server's platform, `linux/amd64` by default.

## Step 1: Build the bundle on the connected PC

### With `make` (macOS, Linux, Git Bash, or WSL)

```bash
git clone https://github.com/itismhn/VulnFlow.git
cd VulnFlow
make docker-bundle
```

This writes `dist/vulnflow-offline.zip`. For an ARM server, run `make docker-bundle PLATFORM=linux/arm64`.

### Without `make` (Windows PowerShell)

Run these from the repository folder:

```powershell
$platform = "linux/amd64"
$out = "dist\vulnflow-offline"
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$out\deploy" | Out-Null

docker build --platform $platform -t vulnflow-api:latest backend
docker build --platform $platform -t vulnflow-web:latest frontend
docker pull --platform $platform postgres:17-alpine
docker pull --platform $platform redis:7-alpine
docker save --platform $platform -o "$out\vulnflow-images.tar" vulnflow-api:latest vulnflow-web:latest postgres:17-alpine redis:7-alpine

# The server has no source code, so drop the "build:" lines and run the saved images only
(Get-Content deploy\docker-compose.yml) | Where-Object { $_ -notmatch '^\s*build: ' } | Set-Content "$out\deploy\docker-compose.yml" -Encoding ascii
Copy-Item .env.example, README.md, docs\offline-install.md $out
Compress-Archive -Path $out -DestinationPath dist\vulnflow-offline.zip
```

If Docker reports `unknown flag: --platform` on `docker save`, your Docker is older than 28. Remove `--platform $platform` from that one line.

### Behind a proxy

If the connected PC reaches the internet through a proxy, pass it to the build:

```bash
make docker-bundle BUILD_FLAGS="--build-arg HTTP_PROXY=http://proxy.example:3128 --build-arg HTTPS_PROXY=http://proxy.example:3128"
```

Without `make`, add the same `--build-arg` options to the two `docker build` commands. Docker itself also needs the proxy to pull images: configure it in Docker Desktop under **Settings → Resources → Proxies**.

### What is in the bundle

```
vulnflow-offline/
├── vulnflow-images.tar      all four images: api/worker, web, postgres, redis
├── deploy/docker-compose.yml   runs the images, never builds or downloads
├── .env.example             settings template
├── README.md
└── offline-install.md       this guide
```

The zip is several hundred MB. Don't commit it to Git; build it again whenever you need a new version.

## Step 2: Copy it to the isolated server

Copy `vulnflow-offline.zip` with a USB drive, a file share, or whatever transfer your organization allows.

You can confirm the file was not corrupted in transit by comparing checksums on both machines. The two values must match:

```bash
sha256sum vulnflow-offline.zip                      # Linux
shasum -a 256 vulnflow-offline.zip                  # macOS
```

```powershell
Get-FileHash vulnflow-offline.zip -Algorithm SHA256 # Windows
```

## Step 3: Install on the isolated server

Extract the zip and open a terminal in the `vulnflow-offline` folder.

### Linux server

```bash
docker load -i vulnflow-images.tar

cp .env.example .env
sed -i -e "s/^RM_SECRET_KEY=.*/RM_SECRET_KEY=$(openssl rand -hex 48)/" \
       -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" \
       -e "s/^RM_COOKIE_SECURE=.*/RM_COOKIE_SECURE=false/" .env

docker compose -f deploy/docker-compose.yml --env-file .env up -d --pull never
```

### Windows server (PowerShell)

```powershell
docker load -i vulnflow-images.tar

function New-Hex($bytes) { $b = [byte[]]::new($bytes); [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | ForEach-Object { $_.ToString('x2') }) }
(Get-Content .env.example) `
  -replace '^RM_SECRET_KEY=.*', "RM_SECRET_KEY=$(New-Hex 48)" `
  -replace '^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$(New-Hex 24)" `
  -replace '^RM_COOKIE_SECURE=.*', 'RM_COOKIE_SECURE=false' |
  Set-Content .env -Encoding ascii

docker compose -f deploy/docker-compose.yml --env-file .env up -d --pull never
```

`--pull never` makes Docker use only the loaded images. If one is missing, you get a clear error instead of a long wait for a download that can't succeed.

## Step 4: Sign in

Open `http://<server-address>:8080` and sign in as `admin` / `admin123`. You will be asked to choose a new password.

- To use another port, set `HTTP_PORT` in `.env` and run the `up` command again.
- Once the app is served over HTTPS, set `RM_COOKIE_SECURE=true` in `.env` and run the `up` command again.

Check that all containers are running and healthy:

```bash
docker compose -f deploy/docker-compose.yml --env-file .env ps
```

## Upgrading

1. On the connected PC, run `git pull` and then build a new bundle (Step 1).
2. Copy it to the server, extract it **over the old folder**, and keep your existing `.env`.
3. Run `docker load -i vulnflow-images.tar`.
4. Run the `up -d --pull never` command again. Database migrations run automatically, and your data volumes are kept.

Back up first (see below). To roll back, keep the previous `vulnflow-images.tar` and load it again. Rolling back after migrations have run can need the backup.

## Backups

```bash
docker compose -f deploy/docker-compose.yml --env-file .env exec -T db pg_dump -U report_manager -Fc -f /tmp/vulnflow.dump report_manager
docker compose -f deploy/docker-compose.yml --env-file .env cp db:/tmp/vulnflow.dump ./vulnflow.dump
```

Uploaded scans and generated reports are kept in the `report-manager_storage` Docker volume.

## Server requirements

All VulnFlow images are **Linux** images, so the server's Docker must run Linux containers:

- **Linux server:** Docker Engine with the Compose plugin. This is the simplest option.
- **Windows 10/11:** Docker Desktop in Linux-containers mode (the default).
- **Windows Server:** its built-in Docker Engine runs Windows containers only, and Docker Desktop is not supported there. Use WSL 2 (Windows Server 2022/2025) with Docker Engine inside the Linux distribution, or a Linux VM on Hyper-V.

Check with `docker version`: under `Server:`, `OS/Arch` must say `linux/amd64`, or `linux/arm64` for an ARM bundle.

Installing Docker on an offline server is a separate step. Download the Docker packages (or the WSL/Linux VM image) on the connected PC and copy them over the same way.

## Troubleshooting

| Problem | Fix |
|---|---|
| `unable to get image 'vulnflow-api:latest': request returned 500` | Docker can't reach a Linux engine. Start Docker Desktop, switch it to Linux containers, or see [Server requirements](#server-requirements) |
| `pull access denied` or a download timeout on `up` | An image is missing. Run `docker load -i vulnflow-images.tar` again, and always use `--pull never` |
| `exec format error` | The bundle was built for the wrong CPU. Rebuild with the right `PLATFORM` |
| `required variable POSTGRES_PASSWORD is missing` | Run the command from the `vulnflow-offline` folder and pass `--env-file .env` |
| Sign-in doesn't stick over `http://` | Set `RM_COOKIE_SECURE=false` in `.env` and run `up` again |
| Build fails with timeouts or `other side closed` on the connected PC | The PC needs a proxy to reach the internet. See [Behind a proxy](#behind-a-proxy) |
