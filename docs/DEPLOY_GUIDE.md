# Blobby — Discord + Terminal + AWS Deploy Guide

A complete, copy-paste setup for the **Blobby server-pet bot**: from a blank Discord
app to a 24/7 bot running on **AWS Fargate** with **DynamoDB** storage and the token
in **SSM Parameter Store**. Goal: **live in your Discord today.**

> Stack: Python 3.12 · discord.py · DynamoDB · ECS Fargate · ECR · SSM · CloudWatch.
> Assumes you already have **Python 3.12**, **Docker Desktop**, and the **AWS CLI** configured.

---

## What you'll end up with

```
Discord  ──websocket──▶  Blobby bot (container on ECS Fargate, 1 task, always on)
                               │
                               ├─ reads token  ──▶  SSM Parameter Store (SecureString)
                               └─ reads/writes ──▶  DynamoDB table "ServerPet"
                         logs ──▶ CloudWatch Logs
```

The bot makes an **outbound** connection to Discord — there is **no inbound traffic**,
so you need **no load balancer and no open ports**. That keeps the AWS setup small.

---

## Part 0 — Decisions & trade-offs (why this shape)

Skim this; it explains the choices baked into the commands below.

**Compute: ECS Fargate (chosen) vs EC2 vs Lambda.**
- *Fargate* — serverless containers, no server to patch, perfect for one always-on
  long-lived process like a gateway bot. Costs ~**$9–12/mo** for the tiny size below.
  **Chosen** because a Discord gateway bot must hold a persistent websocket, which
  rules Lambda out, and Fargate is far less ops than EC2.
- *EC2* — cheaper at scale and you can run several bots on one box, but you own OS
  patching, restarts, and the auto-restart logic. More work for one bot.
- *Lambda* — great for webhook/HTTP interaction bots, but **cannot** hold the
  persistent gateway connection your passive-XP listener needs. Not viable here.

**Storage: DynamoDB (already coded).** `storage.py` is single-table DynamoDB.
Pay-per-request billing means near-zero cost at friend-server scale. No change needed.

**Secret: SSM Parameter Store (SecureString).** Your `config.py` already supports
`DISCORD_TOKEN_PARAM`. Free for standard parameters; simpler than Secrets Manager
(which charges per secret). The container fetches the token at startup via its IAM role.

**Unintended-consequence checklist (read once):**
- *Apple-Silicon Mac?* Fargate runs **x86_64** by default. You **must** build the
  image for `linux/amd64` (Part 6) or the task will crash-loop with an `exec format error`.
- *Networking:* a Fargate task in a public subnet needs **`assignPublicIp=ENABLED`**
  to reach Discord, otherwise it has no route to the internet and silently fails to connect.
- *Startup permission:* the bot calls `ensure_table()` on boot, which runs
  `dynamodb:ListTables`. The task's IAM role **must** allow it (included below) or the
  bot dies before it logs in.
- *Token in git:* your repo had a real token in an example file. **Reset it** (Part 1,
  Step 3) — anyone with the old one can control your bot.

---

## Part 1 — Discord Developer Portal

### Step 1 — Create the application
1. Go to **https://discord.com/developers/applications** → **New Application**.
2. Name it `Blobby` (or anything) → **Create**.

### Step 2 — Add the bot user & token
1. Left sidebar → **Bot**.
2. Click **Reset Token** → **Yes, do it** → **Copy** the token. Save it somewhere safe
   for a minute — you'll paste it into `.env` (local test) and SSM (AWS).
   > This is also Step 3 of the security fix: resetting **invalidates the old leaked
   > token**. Do it even if you think you never shared it.

### Step 3 — Enable the privileged intent (required)
Still on the **Bot** page, scroll to **Privileged Gateway Intents**:
- ✅ **MESSAGE CONTENT INTENT** → toggle **ON** → **Save Changes**.

This is mandatory — `bot.py` sets `intents.message_content = True` for the passive-XP
listener. Without it the bot fails to start with a `PrivilegedIntentsRequired` error.
(You can leave Presence and Server Members intents OFF.)

### Step 4 — Generate the invite link & add the bot to your server
1. Left sidebar → **OAuth2** → **URL Generator**.
2. **Scopes:** check **`bot`** and **`applications.commands`**.
3. **Bot Permissions** (appears below): check
   - View Channels
   - Send Messages
   - Embed Links
   - Attach Files  *(needed for the sprite PNGs)*
   - Read Message History
   - Use Slash Commands
4. Copy the **Generated URL** at the bottom, open it in a browser, pick your test
   server, **Authorize**, solve the captcha. Blobby now appears (offline) in your member list.

### Step 5 — Grab your server (guild) ID for instant command sync
1. In Discord: **User Settings → Advanced → Developer Mode → ON**.
2. Right-click your **server icon** → **Copy Server ID**.

Save this number — it's `DEV_GUILD_ID`. With it set, slash commands appear **instantly**.
Without it, global sync can take **up to ~1 hour** to show up.

---

## Part 2 — Prep the code (terminal)

Your files have already been cleaned up for deploy:
- `bot.py` → **`bot.py`**  (the Dockerfile runs `python bot.py`)
- `requirements_1.txt` → **`requirements.txt`**
- `Dockerfile_1` → **`Dockerfile`**
- `.dockerignore` and `.gitignore` added (keeps `.env`, `.venv`, caches out of the image)
- The leaked token in `.env.example` was scrubbed (still **reset it** in Part 1).

`cd` into the code folder for everything below:

```bash
cd "/Users/noelcoronado/Documents/Discord Feature Project/Bot Code"
```

Sanity-check the layout (you should see `bot.py`, `config.py`, `pet.py`, `sprites.py`,
`storage.py`, `requirements.txt`, `Dockerfile`, and a `sprites/` folder with 30 PNGs):

```bash
ls -1
ls sprites | wc -l   # expect 30
```

---

## Part 3 — 5-minute local smoke test (do this before deploying)

You picked a full AWS deploy — but running it locally for two minutes first proves the
**Discord half works** before you spend time on AWS. If it talks to Discord locally,
any later problem is an AWS problem, which is much faster to diagnose. Skip to Part 4 if
you'd rather go straight to the cloud.

```bash
# 1) Virtual env + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) Free local DynamoDB in Docker (no AWS cost)
docker run -d --name blobby-ddb -p 8000:8000 amazon/dynamodb-local

# 3) Create your .env  (paste your real token + guild id)
cat > .env <<'EOF'
DISCORD_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
DEV_GUILD_ID=PASTE_YOUR_SERVER_ID_HERE
AWS_REGION=us-east-1
PET_TABLE=ServerPet
DYNAMODB_ENDPOINT=http://localhost:8000
EOF
#  ^ open .env and replace the two PASTE_... values

# 4) Run it
python bot.py
```

You should see `Logged in as Blobby#... — pet bot ready.` and Blobby flips **online**
in Discord. In your server, type `/status` — the pet card appears. Try `/feed`, `/pet`,
`/wish`, `/collection`. Send a few normal chat messages to earn passive XP.

Stop the test when happy:
```bash
# Ctrl-C to stop the bot, then:
docker rm -f blobby-ddb
deactivate
```
> The local `.env` line `DYNAMODB_ENDPOINT=...` is **local-only**. We will **not** set
> it in AWS — leaving it unset makes the bot talk to real DynamoDB.

---

## Part 4 — AWS, Step 1: set shell variables

Everything below uses these. Set them once per terminal session. Replace the guild ID.

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TABLE_NAME=ServerPet
export PARAM_NAME=/server-pet/discord-token
export ECR_REPO=blobby-bot
export CLUSTER=blobby-cluster
export SERVICE=blobby-svc
export DEV_GUILD_ID=PASTE_YOUR_SERVER_ID_HERE     # the number from Part 1, Step 5
echo "Account: $ACCOUNT_ID  Region: $AWS_REGION"
```

---

## Part 5 — AWS, Step 2: create the DynamoDB table

The bot can self-create it, but creating it explicitly is cleaner for production:

```bash
aws dynamodb create-table \
  --table-name "$TABLE_NAME" \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region "$AWS_REGION"

aws dynamodb wait table-exists --table-name "$TABLE_NAME" --region "$AWS_REGION"
echo "Table ready."
```

This matches `storage.py` exactly: partition key `pk`, sort key `sk`, on-demand billing.

---

## Part 6 — AWS, Step 3: store the token in SSM Parameter Store

```bash
aws ssm put-parameter \
  --name "$PARAM_NAME" \
  --value "PASTE_YOUR_BOT_TOKEN_HERE" \
  --type SecureString \
  --region "$AWS_REGION"
```

> Replace `PASTE_YOUR_BOT_TOKEN_HERE` with the real token. SecureString encrypts it with
> the AWS-managed key `alias/aws/ssm`. The container reads it via `DISCORD_TOKEN_PARAM`.
> To rotate later: reset the token in Discord, then re-run with `--overwrite` added.

---

## Part 7 — AWS, Step 4: build the image & push to ECR

```bash
# Create the registry repo (ignore error if it already exists)
aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" || true

# Authenticate Docker to ECR
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Build for x86_64 (REQUIRED on Apple Silicon — Fargate default arch is amd64)
docker buildx build --platform linux/amd64 \
  -t "$ECR_REPO:latest" --load .

# Tag + push
docker tag "$ECR_REPO:latest" "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
```

> On an Intel Mac the `--platform linux/amd64` flag is harmless. On Apple Silicon it is
> essential — without it the task fails with `exec /usr/local/bin/python: exec format error`.

---

## Part 8 — AWS, Step 5: IAM roles

Two roles: an **execution role** (lets ECS pull the image and write logs) and a **task
role** (what your code is allowed to do at runtime — DynamoDB + SSM).

### 8a — Execution role

```bash
cat > /tmp/ecs-trust.json <<'EOF'
{ "Version": "2012-10-17",
  "Statement": [{ "Effect": "Allow",
    "Principal": { "Service": "ecs-tasks.amazonaws.com" },
    "Action": "sts:AssumeRole" }] }
EOF

aws iam create-role --role-name blobby-exec-role \
  --assume-role-policy-document file:///tmp/ecs-trust.json || true

aws iam attach-role-policy --role-name blobby-exec-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

### 8b — Task role (runtime permissions)

```bash
aws iam create-role --role-name blobby-task-role \
  --assume-role-policy-document file:///tmp/ecs-trust.json || true

cat > /tmp/blobby-task-policy.json <<EOF
{ "Version": "2012-10-17",
  "Statement": [
    { "Sid": "DDBItems", "Effect": "Allow",
      "Action": ["dynamodb:GetItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:Query"],
      "Resource": "arn:aws:dynamodb:$AWS_REGION:$ACCOUNT_ID:table/$TABLE_NAME" },
    { "Sid": "DDBList", "Effect": "Allow",
      "Action": ["dynamodb:ListTables","dynamodb:DescribeTable"],
      "Resource": "*" },
    { "Sid": "ReadToken", "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:$AWS_REGION:$ACCOUNT_ID:parameter$PARAM_NAME" },
    { "Sid": "DecryptToken", "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "*",
      "Condition": { "StringEquals": { "kms:ViaService": "ssm.$AWS_REGION.amazonaws.com" } } }
  ] }
EOF

aws iam put-role-policy --role-name blobby-task-role \
  --policy-name blobby-task-policy \
  --policy-document file:///tmp/blobby-task-policy.json
```

> `dynamodb:ListTables` is on `*` because that action doesn't support resource scoping,
> and the bot's `ensure_table()` calls it on every startup. Item operations are scoped to
> your one table. `kms:Decrypt` is fenced to SSM only. If you'd rather the bot create the
> table itself, also add `dynamodb:CreateTable` on the table ARN.

---

## Part 9 — AWS, Step 6: networking lookup

Grab a default-VPC public subnet and its default security group (default SG allows all
outbound, which is all this bot needs):

```bash
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION")

export SUBNET_ID=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  --query 'Subnets[0].SubnetId' --output text --region "$AWS_REGION")

export SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=vpc-id,Values=$VPC_ID Name=group-name,Values=default \
  --query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION")

echo "VPC=$VPC_ID  Subnet=$SUBNET_ID  SG=$SG_ID"
```

> If your account has no default VPC, substitute any **public** subnet (one with a route
> to an internet gateway). A private subnet only works if it has a NAT gateway.

---

## Part 10 — AWS, Step 7: log group, cluster, task definition, service

### 10a — Log group + cluster
```bash
aws logs create-log-group --log-group-name /ecs/blobby --region "$AWS_REGION" || true
aws ecs create-cluster --cluster-name "$CLUSTER" --region "$AWS_REGION"
```

### 10b — Register the task definition
```bash
cat > /tmp/blobby-taskdef.json <<EOF
{
  "family": "blobby",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "runtimePlatform": { "cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX" },
  "executionRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/blobby-exec-role",
  "taskRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/blobby-task-role",
  "containerDefinitions": [
    {
      "name": "blobby",
      "image": "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest",
      "essential": true,
      "environment": [
        { "name": "AWS_REGION", "value": "$AWS_REGION" },
        { "name": "PET_TABLE", "value": "$TABLE_NAME" },
        { "name": "DEV_GUILD_ID", "value": "$DEV_GUILD_ID" },
        { "name": "DISCORD_TOKEN_PARAM", "value": "$PARAM_NAME" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/blobby",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "blobby"
        }
      }
    }
  ]
}
EOF

aws ecs register-task-definition --cli-input-json file:///tmp/blobby-taskdef.json \
  --region "$AWS_REGION"
```

> Note: there is **no** `DISCORD_TOKEN` and **no** `DYNAMODB_ENDPOINT` here. The bot
> fetches the token from SSM and uses real DynamoDB. Keeping `DEV_GUILD_ID` set means your
> slash commands stay instant in your test server.

### 10c — Create the service (1 always-on task, public IP for outbound)
```bash
aws ecs create-service \
  --cluster "$CLUSTER" \
  --service-name "$SERVICE" \
  --task-definition blobby \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --region "$AWS_REGION"
```

`desired-count 1` + Fargate = ECS keeps exactly one Blobby running and **auto-restarts**
it if it ever crashes. `assignPublicIp=ENABLED` is what gives the task internet access to
reach Discord.

---

## Part 11 — Verify it's live

Watch the logs until you see the ready line:

```bash
aws logs tail /ecs/blobby --follow --region "$AWS_REGION"
```

Expected: `Logged in as Blobby#... — pet bot ready.` Blobby goes **online** in Discord.

Then in your server, run through the full command set:

| Command | What it does |
|---|---|
| `/status` | Show the pet card (level, hunger, happiness, server stars, collection) |
| `/feed` | Feed Blobby → +3 ⭐ to the server pool, raises hunger, earns XP |
| `/pet` | Pet Blobby → +2 ⭐, raises happiness, earns XP |
| `/wish` | Spend 15 ⭐ on a random species+color pull into the shared collection |
| `/collection` | View the server's shared collection progress |
| `/rename <name>` | Rename the pet (max 32 chars) |
| `/checkin` | Daily check-in to build your personal streak |
| *(just chat)* | Sending messages grants passive XP (rate-limited to once/min per member) |

If commands don't appear instantly, confirm `DEV_GUILD_ID` matches the server you're in.

---

## Part 12 — Updating the bot later (redeploy)

After editing code, rebuild, push, and force a fresh task:

```bash
docker buildx build --platform linux/amd64 -t "$ECR_REPO:latest" --load .
docker tag "$ECR_REPO:latest" "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"

aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --force-new-deployment --region "$AWS_REGION"
```

---

## Part 13 — Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Task starts then stops; log says `exec format error` | Image built for arm64. Rebuild with `--platform linux/amd64` (Part 7). |
| `PrivilegedIntentsRequired` in logs | Message Content Intent is off — enable it (Part 1, Step 3). |
| Crashes at startup mentioning `ListTables`/AccessDenied | Task role missing `dynamodb:ListTables` — re-apply the policy (Part 8b). |
| `ParameterNotFound` / can't read token | `PARAM_NAME` mismatch, or `ssm:GetParameter`/`kms:Decrypt` missing in task role. |
| Bot never reaches "Logged in", no obvious error | Task has no internet route. Confirm `assignPublicIp=ENABLED` and a public subnet (Part 9–10c). |
| Slash commands don't show up | `DEV_GUILD_ID` wrong/empty, or you're testing in a different server. Global sync also takes up to ~1h. |
| Bot online but ignores chat for XP | Message Content Intent off, or the per-member 60s passive-XP cooldown. |
| Image push denied | Re-run the `aws ecr get-login-password ... | docker login` step (Part 7). |

Check current service/task state any time:
```bash
aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].{running:runningCount,desired:desiredCount,events:events[0].message}' \
  --region "$AWS_REGION"
```

---

## Part 14 — Cost & teardown

**Rough monthly cost** (one 0.25 vCPU / 0.5 GB Fargate task, always on):
- Fargate: ~**$9–12/mo**
- DynamoDB (on-demand, friend-server traffic): **cents**
- SSM standard parameter, CloudWatch Logs, ECR storage: **~free** at this size

**Tear everything down** when you're done testing:
```bash
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --desired-count 0 --region "$AWS_REGION"
aws ecs delete-service  --cluster "$CLUSTER" --service "$SERVICE" --force --region "$AWS_REGION"
aws ecs delete-cluster  --cluster "$CLUSTER" --region "$AWS_REGION"
aws ecr delete-repository --repository-name "$ECR_REPO" --force --region "$AWS_REGION"
aws logs delete-log-group --log-group-name /ecs/blobby --region "$AWS_REGION"
aws dynamodb delete-table --table-name "$TABLE_NAME" --region "$AWS_REGION"   # deletes all pet data
aws ssm delete-parameter --name "$PARAM_NAME" --region "$AWS_REGION"
# IAM roles:
aws iam delete-role-policy --role-name blobby-task-role --policy-name blobby-task-policy
aws iam delete-role --role-name blobby-task-role
aws iam detach-role-policy --role-name blobby-exec-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name blobby-exec-role
```

---

## Quick reference — fastest path to "live today"

1. **Discord portal:** create app → Bot → Reset Token → enable Message Content Intent →
   OAuth2 URL (`bot` + `applications.commands`) → invite → copy Server ID.
2. **Local smoke test** (Part 3): `.venv`, `pip install`, DynamoDB Local in Docker, `python bot.py`, confirm `/status` works.
3. **AWS** (Parts 4–10): set vars → create table → put token in SSM → build `--platform linux/amd64` & push to ECR → create IAM roles → register task def → create service.
4. **Verify** (Part 11): `aws logs tail /ecs/blobby --follow` → run the slash commands.
