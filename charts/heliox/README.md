# Heliox Helm Chart

GPU cost visibility and optimization for ML infrastructure teams.

Self-host Heliox on any Kubernetes cluster (EKS, GKE, AKS) with a single `helm install`.

---

## Quick Install

```bash
# 1. Add the Heliox chart repository
helm repo add heliox https://heliox-ai.github.io/heliox
helm repo update

# 2. Generate required secrets
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

# 3. Install
helm upgrade --install heliox heliox/heliox \
  --namespace heliox \
  --create-namespace \
  --set secrets.secretKey="$SECRET_KEY" \
  --set secrets.databasePassword="$DB_PASSWORD" \
  --set secrets.encryptionKey="$ENCRYPTION_KEY" \
  --set postgresql.external.host="your-rds-endpoint.rds.amazonaws.com" \
  --set config.redisUrl="rediss://your-elasticache.cache.amazonaws.com:6379" \
  --set redis.enabled=false \
  --set config.corsOrigins="https://your-domain.com" \
  --set config.apiBaseUrl="https://your-domain.com" \
  --set ingress.hosts[0].host="your-domain.com" \
  --set ingress.tls[0].hosts[0]="your-domain.com" \
  -f values-production.yaml
```

---

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Ingress   │───▶│  API (x2-10) │───▶│  PostgreSQL │
│  (nginx /   │    │  FastAPI     │    │  (RDS /     │
│   ALB)      │    │  Uvicorn     │    │   bundled)  │
└─────────────┘    └──────┬───────┘    └─────────────┘
                          │
                   ┌──────▼───────┐    ┌─────────────┐
                   │   Worker     │───▶│    Redis     │
                   │ (Celery x2-8)│    │ (ElastiCache │
                   └──────┬───────┘    │  / bundled) │
                          │            └─────────────┘
                   ┌──────▼───────┐
                   │  Beat (x1)   │
                   │ Celery Beat  │
                   └─────────────┘

GPU Nodes:
┌─────────────────────────────────────────┐
│  Agent DaemonSet (one pod per GPU node) │
│  Collects: GPU util, memory, job tags   │
└─────────────────────────────────────────┘
```

---

## Configuration Reference

### Core secrets (`secrets.*`)

| Value | Required | Description |
|-------|----------|-------------|
| `secrets.secretKey` | **Yes** | JWT signing key. `openssl rand -hex 32` |
| `secrets.databasePassword` | **Yes** | PostgreSQL password |
| `secrets.encryptionKey` | **Yes (prod)** | Fernet key for OAuth token encryption |
| `secrets.redisPassword` | No | Redis password (when auth enabled) |
| `secrets.stripeSecretKey` | No | Stripe secret key (`sk_live_...`) |
| `secrets.stripeWebhookSecret` | No | Stripe webhook secret (`whsec_...`) |
| `secrets.googleClientId` | No | Google OAuth client ID |
| `secrets.googleClientSecret` | No | Google OAuth client secret |
| `secrets.sentryDsn` | No | Sentry DSN for error monitoring |
| `secrets.resendApiKey` | No | Resend API key for email alerts |
| `secrets.slackWebhookUrl` | No | Slack Incoming Webhook URL |
| `secrets.existingSecret` | No | Use a pre-existing Kubernetes Secret instead |

### API (`api.*`)

| Value | Default | Description |
|-------|---------|-------------|
| `api.replicaCount` | `2` | Replicas when autoscaling disabled |
| `api.image.repository` | `ghcr.io/heliox-ai/heliox` | Container image |
| `api.image.tag` | `latest` | Pin to a release tag in production |
| `api.autoscaling.enabled` | `true` | Enable HPA |
| `api.autoscaling.minReplicas` | `2` | HPA minimum |
| `api.autoscaling.maxReplicas` | `10` | HPA maximum |
| `api.service.type` | `ClusterIP` | Service type |

### Config (`config.*`)

| Value | Default | Description |
|-------|---------|-------------|
| `config.env` | `production` | App environment (dev/staging/production) |
| `config.corsOrigins` | `""` | Comma-separated allowed CORS origins |
| `config.apiBaseUrl` | `https://heliox.example.com` | Public API base URL |
| `config.redisUrl` | `""` | External Redis URL (when `redis.enabled=false`) |
| `config.multiTenant` | `true` | Enable multi-tenant isolation |
| `config.timezone` | `UTC` | Timezone for scheduled tasks |
| `config.authCookieSecure` | `true` | Set Secure flag on auth cookie |

### Agent (`agent.*`)

| Value | Default | Description |
|-------|---------|-------------|
| `agent.enabled` | `true` | Deploy DaemonSet on GPU nodes |
| `agent.apiEndpoint` | `""` | Heliox API URL the agent reports to |
| `agent.apiKey` | `""` | Team API key for authentication |
| `agent.existingSecret` | `""` | Pre-existing Secret with `api_key` key |
| `agent.interval` | `60` | Polling interval in seconds |
| `agent.nodeSelector` | `{accelerator: "true"}` | Only schedule on GPU nodes |

---

## Connecting External RDS

```yaml
# values-production.yaml
postgresql:
  enabled: false
  external:
    host: "heliox.cluster-xxxx.us-east-1.rds.amazonaws.com"
    port: 5432
    database: heliox
    username: heliox

secrets:
  databasePassword: ""  # set via --set or CI secret
```

The chart assembles `DATABASE_URL` automatically from these values at deploy time.

---

## Connecting External ElastiCache

```yaml
# values-production.yaml
redis:
  enabled: false

config:
  # TLS-enabled clusters (recommended):
  redisUrl: "rediss://heliox-prod.xxxx.ng.0001.use1.cache.amazonaws.com:6379"
  # Non-TLS:
  # redisUrl: "redis://heliox-prod.xxxx.ng.0001.use1.cache.amazonaws.com:6379"
```

---

## Using an Existing Secret

To avoid passing secrets as Helm values (e.g. when using Vault or External Secrets Operator):

```bash
# Create the secret manually
kubectl create secret generic heliox-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=DATABASE_PASSWORD="$DB_PASS" \
  --from-literal=INTEGRATIONS_ENCRYPTION_KEY="$FERNET_KEY" \
  -n heliox

# Tell Helm to use it
helm upgrade --install heliox heliox/heliox \
  --set secrets.existingSecret=heliox-secrets \
  -n heliox
```

---

## Upgrading

```bash
helm repo update
helm upgrade heliox heliox/heliox \
  -n heliox \
  -f values-production.yaml \
  --set secrets.secretKey="$SECRET_KEY" \
  --set secrets.databasePassword="$DB_PASSWORD" \
  --set secrets.encryptionKey="$ENCRYPTION_KEY"
```

Migrations run automatically as a `pre-upgrade` Helm hook before any pods restart.

---

## Troubleshooting

### Pods stuck in `Init` state
The API and worker pods run an init container waiting for the migration Job.
Check migration status:
```bash
kubectl logs -n heliox job/heliox-migrations
kubectl describe job heliox-migrations -n heliox
```

### `SECRET_KEY must be at least 32 characters`
The app validates the secret key on startup. Generate one correctly:
```bash
openssl rand -hex 32
```

### `INTEGRATIONS_ENCRYPTION_KEY` validation error
Must be a valid Fernet key (URL-safe base64, 32 bytes):
```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

### Agent not reporting metrics
```bash
# Check agent is scheduled on GPU nodes
kubectl get pods -n heliox -l app.kubernetes.io/component=agent -o wide

# Check agent logs
kubectl logs -n heliox -l app.kubernetes.io/component=agent -f

# Verify node has the accelerator label
kubectl get nodes --show-labels | grep accelerator
```

### 503 from ingress immediately after deploy
Wait for the readiness probe (10s interval) to pass:
```bash
kubectl get pods -n heliox -w
kubectl describe pod -n heliox -l app.kubernetes.io/component=api
```

### Beat running multiple replicas
Celery Beat **must** run as a single instance. The chart uses `strategy.type: Recreate` and `replicas: 1` to enforce this. Do not override beat replicas.

---

## Uninstall

```bash
helm uninstall heliox -n heliox
# Secrets are preserved by default (helm.sh/resource-policy: keep)
# To also delete secrets:
kubectl delete secret heliox-heliox-secrets -n heliox
```
