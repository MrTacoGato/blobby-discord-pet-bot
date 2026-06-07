# 🐾 Blobby — A Discord Server Pet Bot

A Tamagotchi-style **shared pet** that an entire Discord server raises together. Everyone's care adds up into one creature and one shared collection — feed it, play with it, collect 30 pixel-art species, and keep it alive. Built in Python on `discord.py` with persistent state in AWS DynamoDB.

<p align="center">
  <img src="sprites/blob_0_lime.png" width="72" alt="blob">
  <img src="sprites/slime_1_azure.png" width="72" alt="slime">
  <img src="sprites/ember_0_red.png" width="72" alt="ember">
  <img src="sprites/spark_0_gold.png" width="72" alt="spark">
  <img src="sprites/wisp_0_violet.png" width="72" alt="wisp">
  <img src="sprites/frost_2_frost.png" width="72" alt="frost">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/discord.py-2.3%2B-5865F2?logo=discord&logoColor=white" alt="discord.py 2.3+">
  <img src="https://img.shields.io/badge/AWS-DynamoDB-FF9900?logo=amazondynamodb&logoColor=white" alt="AWS DynamoDB">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker ready">
  <img src="https://img.shields.io/badge/License-MIT-3DA639.svg" alt="License: MIT">
</p>

---

## Highlights

- **One pet, one server.** A single living creature is shared by everyone in the guild — not per-user. Care is collaborative; so are the rewards.
- **A shared gacha collection.** `/feed` and `/pet` pour ⭐ into one server-wide pool; `/wish` spends stars to pull a random species × color into a shared album of **30** collectibles, with rarity weights and duplicate refunds.
- **Stateless, "settle-on-read" decay.** Needs decay from a single timestamp computed at read time — no cron, no background scheduler. The bot can restart or sleep for a week and the pet's state is always correct.
- **Gentle, forgiving death.** No "die" button. Blobby only passes after ~15 days of *total* neglect, then a fresh random pet hatches and the collection carries over untouched.
- **Pre-baked pixel art.** 30 Game Boy-style sprites are rendered once with Pillow and committed; the bot just attaches the PNGs at runtime (no image library in the hot path).
- **Production-minded.** Single-table DynamoDB, async-safe AWS calls, Dockerized, and 12-factor secrets (env locally, AWS SSM Parameter Store in production).

## How it plays

| Command | What it does |
|---|---|
| `/status` | Show the pet card — name, level, hunger, happiness, the server star pool, and collection progress |
| `/feed` | Feed it 🍎 — raises **hunger**, earns **+3 ⭐** for the server |
| `/pet` | Pet it 🫳 — raises **happiness**, earns **+2 ⭐** |
| `/wish` | Spend **15 ⭐** to pull a random new species × color into the shared collection ✨ |
| `/collection` | See the shared album with per-species progress |
| `/rename <name>` | Rename the pet (≤ 32 characters) |
| `/checkin` | Daily check-in to build a personal streak 🔥 |
| *(just chatting)* | Talking in the server passively earns the pet **XP** — rate-limited to once per minute per person |

There are **6 species × 5 colors = 30** collectibles. Some species are rarer than others (`frost` is the chase). A full deck is a multi-week shared goal for a ~10-person server. The full player-facing walkthrough lives in [`docs/PLAYER_GUIDE.md`](docs/PLAYER_GUIDE.md).

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.10+ |
| Discord | [`discord.py`](https://discordpy.readthedocs.io/) 2.3+ (slash commands via `app_commands`, message-content intent for passive XP) |
| Persistence | AWS DynamoDB (single-table) via `boto3`; works against **DynamoDB Local** for development |
| Art | Pillow — renders 16×16 pixel grids into transparent PNGs |
| Config / secrets | `python-dotenv` locally; AWS SSM Parameter Store in production |
| Packaging | Docker (`python:3.12-slim`) |

## Architecture

The code is split into three layers with a deliberately **pure, dependency-light core**:

```
bot.py        Discord I/O — slash commands, the passive-XP listener, and embed/sprite assembly
  └── pet.py      Pure game logic — stat decay, leveling, the gacha loop, death/respawn (no Discord, no AWS)
        └── storage.py   Persistence — a thin boto3 wrapper over a single DynamoDB table
config.py     Every tuning knob in one place — species, colors, decay rates, economy, death pacing
```

A few design decisions worth calling out:

**Settle-on-read state.** Rather than ticking stats on a timer, every read "settles" the pet: it reads `stats_updated_at`, computes elapsed time, applies the gentle per-hour decay, and writes back. State is therefore correct after any downtime, and the service is effectively stateless between calls.

**Single-table DynamoDB.** All data lives in one table partitioned by guild:

| `pk` | `sk` | Item |
|---|---|---|
| `GUILD#<id>` | `PET` | the living pet (stats, level, species, generation) |
| `GUILD#<id>` | `USER#<id>` | per-member streak and XP contribution |
| `GUILD#<id>` | `COLLECTION` | the shared star pool + discovered species list |

Keying the collection by **guild** (not user) is what makes the album and star pool shared automatically. The table is created on first run (`storage.ensure_table`).

**Async-safe AWS.** `boto3` is synchronous, so every call is dispatched with `asyncio.to_thread(...)` to keep the Discord event loop responsive.

**Sprites as build artifacts.** `sprites.py` bakes all 30 species × color PNGs from the same pixel grids and Game Boy palettes as [`docs/blobby_sprites.html`](docs/blobby_sprites.html). They're committed to `sprites/`, so Pillow is a **dev-only** dependency — the running bot never imports it.

## Project structure

```
.
├── bot.py                 # Discord layer: commands, listeners, embeds
├── pet.py                 # Pure game logic: decay, XP, gacha, death/respawn
├── storage.py             # DynamoDB persistence (boto3, single-table)
├── config.py              # All tuning knobs (species, rates, economy, pacing)
├── sprites.py             # Pixel-art renderer (Pillow) → bakes sprites/*.png
├── sprites/               # 30 pre-rendered species × color PNGs (committed)
├── requirements.txt       # Runtime deps: discord.py, boto3, python-dotenv
├── requirements-dev.txt   # Pillow — only to regenerate sprite art
├── Dockerfile             # Container image for deployment
├── .env.example           # Copy to .env and fill in your token + server ID
└── docs/
    ├── PLAYER_GUIDE.md        # For server members: how to play
    ├── SETUP_GUIDE.md         # Milestones 1–2: zero → running locally
    ├── COLLECTION_GUIDE.md    # Milestone 3: the shared collection / gacha
    ├── DEPLOY_GUIDE.md        # Run it 24/7 on AWS
    └── blobby_sprites.html    # Sprite palette / preview (design tool)
```

## Quickstart (local)

You'll need **Python 3.10+** and **Docker** (for a local DynamoDB). Full step-by-step instructions — including creating the Discord application and inviting the bot — are in [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md).

```bash
# 1. Clone
git clone https://github.com/MrTacoGato/blobby-discord-pet-bot.git
cd blobby-discord-pet-bot

# 2. Create a virtual environment and install runtime deps
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure your secrets
cp .env.example .env               # then paste your bot token + dev server ID

# 4. Start DynamoDB Local in a separate terminal
docker run -p 8000:8000 amazon/dynamodb-local
#   → then uncomment DYNAMODB_ENDPOINT=http://localhost:8000 in .env

# 5. Run the bot
python bot.py
```

On success you'll see `Logged in as … — pet bot ready.`, the bot shows **online** in your server, and typing `/` reveals its commands.

> Regenerating the art is optional and only needed if you change a shape or color:
> `pip install -r requirements-dev.txt && python sprites.py` writes all 30 PNGs into `sprites/`.

## Configuration

Everything tunable lives at the top of [`config.py`](config.py). The defaults are tuned for a friend-sized (~10-person) server.

| Knob | Default | Controls |
|---|---|---|
| `HUNGER_DECAY_PER_HOUR` / `HAPPINESS_DECAY_PER_HOUR` | `1.5` / `1.0` | How fast needs drop (per hour — days to empty) |
| `FEED_HUNGER` / `PLAY_HAPPINESS` / `PET_HAPPINESS` | `30` / `25` / `15` | How much each care action restores |
| `STAR_FEED` / `STAR_PET` | `3` / `2` | Stars earned per care action |
| `WISH_COST` / `DUPE_REFUND` | `15` / `5` | The gacha economy |
| `NEGLECT_DEATH_DAYS` | `15` | Days of total neglect before the pet passes (grace auto-adjusts) |
| `DEATHS_ENABLED` | `True` | Flip to `False` to disable death entirely |
| `rarity` (per species) | `5/5/5/3/3/2` | Wish draw weights — lower is rarer (`frost` is the chase) |
| `XP_FEED` / `XP_PLAY` / `XP_PET` / `XP_PASSIVE` | `5` / `8` / `4` / `2` | XP granted per action |

## Deployment

The bot is container-ready and designed to run 24/7 against real DynamoDB. In production, swap the local `DISCORD_TOKEN` for an SSM Parameter Store reference (`DISCORD_TOKEN_PARAM`) so the secret never lives on disk. The full AWS walkthrough (EC2 + DynamoDB + SSM) is in [`docs/DEPLOY_GUIDE.md`](docs/DEPLOY_GUIDE.md).

```bash
docker build -t blobby .
docker run --env-file .env blobby
```

## Roadmap

- **Composite collection image** — render `/collection` as a single contact sheet (found in color, missing as dark silhouettes).
- **Animated sprites** — 2–3 frame GIFs with a little squash-and-bounce per action.
- **Leaderboards** — a "top collectors" board (per-user XP contribution is already tracked).
- **Seasonal species** — limited-time creatures with their own palettes for events.
- **Daily nudge** — EventBridge → Lambda reminder when the pet is getting hungry.

## Documentation

- [Player Guide](docs/PLAYER_GUIDE.md) — for server members
- [Setup Guide](docs/SETUP_GUIDE.md) — local development, milestones 1–2
- [Collection Guide](docs/COLLECTION_GUIDE.md) — the shared gacha, milestone 3
- [Deploy Guide](docs/DEPLOY_GUIDE.md) — running 24/7 on AWS

## License

Released under the [MIT License](LICENSE).
