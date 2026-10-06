# Deployment Guide (AWS)

How to take the Docker Compose stack and run it on AWS. Steps are in the order you run them.
Items marked **[TODO]** need code or Terraform that is not written yet.

## Target architecture

```
Internet ──► WAF (rate rules) ──► ALB (public subnets, HTTPS)
                                   ├── /        → ECS service: ui   (Streamlit, :8501)
                                   └── /chat,/health → ECS service: api (FastAPI, :8000)
                                                          │
            private subnets ─────────────────────────────┼──────────────────────────────┐
              ECS service: worker ◄── SQS ◄── S3 events   │                              │
                     │                                     ├─► RDS Postgres  (chat memory)│
                     └──────────► Qdrant Cloud ◄───────────┤─► Redis w/ vector search    │
                                                           │     (semantic cache, limits) │
                                                           └─► NAT ─► Portkey ─► Groq     │
            ──────────────────────────────────────────────────────────────────────────────┘
```

| Local (Compose) | AWS |
|---|---|
| `api`, `ui`, `worker` containers | ECS Fargate services |
| images built locally | ECR repositories |
| `postgres` | RDS for PostgreSQL 16 |
| `redis` (redis-stack) | MemoryDB or ElastiCache for Valkey, **with vector search enabled** |
| `DATA/` + `watcher` | S3 bucket + event notifications → SQS (watcher is not deployed) |
| Redis Stream `ingest:events` / `ingest:dlq` | SQS queue + SQS dead-letter queue |
| `.env` | Secrets Manager (secrets) + task-definition env vars (non-secrets) |
| `docker compose logs` | CloudWatch Logs |

---

## 0. Prerequisites

- AWS account, and an IAM user or SSO role with admin rights for the first deployment
- AWS CLI v2 (`aws configure` or `aws sso login`), Terraform ≥ 1.6, Docker
- Pick one region (for example `us-east-1`) and use it everywhere
- The local stack works: `docker compose up --build` passes the tests in section 8.4

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

## 1. Terraform remote state (one-time)

State must not live on your laptop. Create an S3 bucket for the state file, with versioning turned on:

```bash
aws s3api create-bucket --bucket rag-tfstate-$ACCOUNT_ID --region $AWS_REGION
aws s3api put-bucket-versioning --bucket rag-tfstate-$ACCOUNT_ID --versioning-configuration Status=Enabled
```

Use it in `terraform/backend.tf` with `use_lockfile = true` (S3-native locking).

## 2. Terraform layout **[TODO: write these files]**

```
terraform/
├── backend.tf          # remote state
├── providers.tf        # aws provider, default tags
├── variables.tf        # region, image tags, instance sizes
├── network.tf          # VPC, 2 public + 2 private subnets, NAT gateway, route tables
├── security.tf         # security groups (see step 4)
├── ecr.tf              # rag-backend, rag-ui repositories
├── secrets.tf          # Secrets Manager entries
├── rds.tf              # Postgres 16, private, encrypted, automated backups
├── redis.tf            # MemoryDB / ElastiCache with vector search
├── storage.tf          # S3 documents bucket, SQS queue + DLQ, S3→SQS notification
├── alb.tf              # ALB, HTTPS listener, target groups, path rules
├── ecs.tf              # cluster, task definitions, services, autoscaling
├── iam.tf              # task execution role + task roles
├── waf.tf              # rate-based rule on the ALB
└── outputs.tf          # ALB DNS name, ECR URLs
```

## 3. Networking

- A VPC with **2 public subnets** (ALB, NAT) and **2 private subnets** (ECS tasks, RDS, Redis), spread across 2 Availability Zones.
- A NAT gateway, so private tasks can reach Portkey, Groq and Qdrant Cloud without having public IPs.

## 4. Security groups (least privilege)

| SG | Inbound | From |
|---|---|---|
| `alb-sg` | 443 (and 80 → redirect) | `0.0.0.0/0` |
| `ui-sg` | 8501 | `alb-sg` |
| `api-sg` | 8000 | `alb-sg`, `ui-sg` |
| `worker-sg` | none | — |
| `rds-sg` | 5432 | `api-sg` only |
| `redis-sg` | 6379 | `api-sg`, `worker-sg` |

The API is never directly reachable from the internet. That is also what makes `--forwarded-allow-ips "*"` in the Dockerfile safe: only the ALB can send it requests.

## 5. Secrets

Store secrets in Secrets Manager; never put them in images or Terraform variables files:

```bash
aws secretsmanager create-secret --name rag/portkey-api-key   --secret-string '...'
aws secretsmanager create-secret --name rag/portkey-config-id --secret-string 'pc-...'
aws secretsmanager create-secret --name rag/qdrant-url        --secret-string 'https://...'
aws secretsmanager create-secret --name rag/qdrant-api-key    --secret-string '...'
```

RDS can manage its own master password in Secrets Manager (`manage_master_user_password = true`).
Build `DATABASE_URL` from it, either in an entrypoint script or by storing the full URL as a secret.

Non-secret settings go in the task definition as plain environment variables:
`GROQ_MODEL`, `QDRANT_COLLECTION`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `RERANK_*`, `CACHE_*`,
`RATE_LIMIT_PER_MINUTE`, `REDIS_URL`, `DEEPEVAL_TELEMETRY_OPT_OUT`.

## 6. Data stores

- **RDS Postgres 16:** `db.t4g.micro` for development, in private subnets, `storage_encrypted = true`, 7-day backups, not publicly accessible. On first API start, `PostgresSaver.setup()` creates the checkpoint tables automatically.
- **Redis:** the semantic cache needs `FT.*` vector search commands, which **plain ElastiCache Redis OSS does not provide**. Use MemoryDB, or ElastiCache for Valkey with vector search. Use a `rediss://` (TLS) URL in `REDIS_URL`.
- **Qdrant:** stays on Qdrant Cloud, with no change. To keep traffic off the internet, a later option is self-hosting it on ECS with EBS storage.

## 7. Build and push images

Fargate runs **x86_64** by default and Apple Silicon builds **arm64**, so build for the right platform:

```bash
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

TAG=$(git rev-parse --short HEAD)
REG=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker buildx build --platform linux/amd64 -t $REG/rag-backend:$TAG --push .
docker buildx build --platform linux/amd64 -f ui/Dockerfile -t $REG/rag-ui:$TAG --push .
```

Tag images with the git SHA, not `latest`, so every deployment can be traced to a commit and rolled back.
(Alternative: set `runtime_platform { cpu_architecture = "ARM64" }` in the task definitions and build `linux/arm64`, which is cheaper on Fargate.)

## 8. ECS services

| Service | Image / command | CPU / memory | Count | Load balancer |
|---|---|---|---|---|
| `api` | `rag-backend` (default CMD) | 1 vCPU / 2 GB | 2 (autoscale on CPU 60%) | ALB target group, health check `/health` |
| `ui` | `rag-ui` | 0.25 vCPU / 0.5 GB | 1 | ALB target group, path `/` |
| `worker` | `rag-backend`, `python -m ingestion.worker` | 1 vCPU / 2 GB | 1 (autoscale on queue depth) | none |

- The UI talks to the API through the internal address: set `API_URL` to the API's ECS Service Connect name or an internal ALB. Don't hairpin through the public ALB.
- Logs: `awslogs` log driver → CloudWatch log group `/ecs/rag-<service>`, retained for 14 days.
- Health-check grace period ≥ 120 s, because the API loads models and guardrails at startup.
- Task roles: the API needs `secretsmanager:GetSecretValue` (via the execution role). The worker also needs `s3:GetObject` and the SQS receive and delete permissions.

## 9. Ingestion on AWS

**Initial load (works today):** Qdrant is in the cloud, so the existing collection is already usable by the deployed API. To rebuild it, run the full ingestion once from your machine or as a one-off ECS task:

```bash
python -m ingestion.run_ingestion
```

**Event-driven (S3 → SQS → worker) [TODO: code change]:** the worker currently reads Redis Streams from a local folder. For AWS:

1. S3 bucket `rag-documents-<account>` with event notifications for `s3:ObjectCreated:*` and `s3:ObjectRemoved:*` → SQS queue.
2. SQS queue with visibility timeout ≥ the slowest file's processing time (for example 300 s), and a redrive policy with `maxReceiveCount = 3` → DLQ.
3. Add an SQS event source to `ingestion/worker.py`: `ReceiveMessage` → download the object from S3 (or use `HeadObject` to check it still exists) → `process()` → `DeleteMessage`. Keep `process()` and the "check the current state of the source" rule unchanged.
4. Upload documents with `aws s3 sync DATA/ s3://rag-documents-<account>/`.

## 10. Edge protection

- An ACM certificate and an HTTPS listener on the ALB; redirect HTTP to HTTPS.
- AWS WAF web ACL on the ALB: AWS managed common rules plus a **rate-based rule** (for example 300 requests per 5 min per IP). This is the outer layer; `services/rate_limit.py` is the per-minute inner layer.

## 11. Deploy

```bash
cd terraform
terraform init
terraform plan  -var "image_tag=$TAG" -out plan.tfplan
terraform apply plan.tfplan
terraform output alb_dns_name
```

## 12. Verify

1. `curl https://<alb>/health` returns `{"status":"ok"}`
2. Open `https://<alb>/` and ask "What is a Kubernetes CronJob?". You should get an answer with sources.
3. Ask a follow-up, run `aws ecs update-service --force-new-deployment` for the API, then ask another follow-up. The conversation should be remembered, because memory now lives in RDS.
4. Ask the same question in a new chat. `cached: true` means the semantic cache is working.
5. Send more than `RATE_LIMIT_PER_MINUTE` requests and confirm you get `429`.
6. Upload a file to S3 (after the [TODO] in step 9) and check the worker logs in CloudWatch.
7. Check Portkey logs: requests are tagged `app: agentic-rag`.

## 13. Monitoring and alarms

CloudWatch alarms → SNS email for:
- ALB `HTTPCode_Target_5XX_Count` > 5 in 5 min
- ALB `TargetResponseTime` p95 > 10 s
- ECS API CPU > 80% for 10 min
- SQS DLQ `ApproximateNumberOfMessagesVisible` > 0
- RDS `FreeStorageSpace` < 2 GB

## 14. CI/CD **[TODO]**

A GitHub Actions workflow on pushes to `main`:
1. `pip install -r requirements-dev.txt` → `python -m evals.collect && python -m evals.score` (fails the build if the eval gate fails)
2. Build and push both images tagged with the commit SHA (use GitHub OIDC → AWS role; no long-lived keys)
3. `terraform apply -var image_tag=<sha>`, or `aws ecs update-service --force-new-deployment`

## 15. Rollback

Re-deploy the previous image tag:
```bash
terraform apply -var "image_tag=<previous-sha>"
```
ECS deployment circuit breaker (`deployment_circuit_breaker { enable = true, rollback = true }`) rolls back automatically when new tasks fail their health checks.

## 16. Cost and teardown

Rough monthly cost for a small development setup: NAT gateway (~$32 plus data), ALB (~$16+), RDS `t4g.micro` (~$12), Redis node, and Fargate tasks.
The NAT gateway and ALB cost money even when idle, so **destroy the stack when you're not using it**:

```bash
cd terraform && terraform destroy -var "image_tag=$TAG"
```
