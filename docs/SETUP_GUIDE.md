# Completing Milestones 1–2 — Detailed Guide

This walks you from an empty machine to a working **server pet** running in
your Discord server, with every feature verified. By the end you will have:

- The bot online in your server
- **Milestone 1:** a living pet with `/status`, `/feed`, `/play`, `/pet`,
  stats that decay slowly, and state stored in DynamoDB
- **Milestone 2:** passive XP from chatting, leveling, and `/checkin` streaks
- A confirmed **death → respawn** cycle (new color, new generation, `/rename`)

Estimated time: **30–60 minutes**, most of it one-time tool installation.

> Throughout, lines starting with `$` are commands to run. A ✅ marks a
> checkpoint — confirm it before moving on.

---

## Part 0 — Install the tools

You need four things. Skip any you already have.

**Python 3.10+**
```
$ python3 --version
```
If missing: macOS `brew install python`, Ubuntu `sudo apt install python3 python3-venv python3-pip`, Windows install from python.org (tick "Add to PATH").

**Git** (to keep the project under version control — good AWS-class habit)
```
$ git --version
```

**Docker** (runs a local copy of DynamoDB so you don't need AWS yet)
```
$ docker --version
```
If missing: install Docker Desktop (macOS/Windows) or `sudo apt install docker.io` (Linux), and make sure the Docker daemon is running.

**AWS CLI** (optional but recommended — lets you *see* the pet's data)
```
$ aws --version
```
If missing: follow AWS's "Install the AWS CLI" page for your OS.

✅ All four commands print a version.

---

## Part 1 — Get the code and set up Python

Put the project somewhere and enter it:
```
$ cd server-pet
```

Create an isolated Python environment and install dependencies:
```
$ python3 -m venv .venv
$ source .venv/bin/activate          # Windows: .venv\Scripts\activate
$ pip install -r requirements.txt
```

✅ Your prompt now shows `(.venv)` and `pip list` includes `discord.py`,
`boto3`, and `python-dotenv`.

> Re-activate the venv (`source .venv/bin/activate`) every time you open a new
> terminal for this project.

---

## Part 2 — Create the Discord application

This is the fiddliest part. Go slowly.

1. Open the **[Developer Portal](https://discord.com/developers/applications)**
   and click **New Application**. Name it (e.g. "Server Pet") and create it.

2. In the left sidebar, click **Bot**. If there's an **Add Bot** prompt, accept
   it. Then click **Reset Token** → **Yes, do it!** → **Copy**. This is your
   `DISCORD_TOKEN`. Paste it somewhere safe for a moment.
   - Treat this like a password. Anyone with it controls your bot. If it ever
     leaks, come back here and Reset Token to invalidate the old one.

3. Still on the **Bot** page, scroll to **Privileged Gateway Intents** and turn
   **Message Content Intent** ON, then save. The passive-XP feature reads
   message content, so the bot will refuse to start without this. (It's free
   for bots in fewer than 100 servers — no approval needed.)

4. Build the invite link. Go to **OAuth2 → URL Generator**:
   - Under **Scopes**, tick `bot` **and** `applications.commands`.
     (`applications.commands` is what makes slash commands appear — easy to
     forget.)
   - A **Bot Permissions** box appears. Tick **View Channels**,
     **Send Messages**, and **Embed Links**.
   - Copy the **Generated URL** at the bottom, open it in your browser, choose
     your server, and **Authorize**.

5. Turn on **Developer Mode** so you can copy IDs: Discord app →
   **User Settings → Advanced → Developer Mode** (toggle on). Now right-click
   your **server icon → Copy Server ID** and keep that number — it's your
   `DEV_GUILD_ID`.

✅ The bot appears in your server's member list (it'll show offline until you
run it), and you have a token + a server ID written down.

---

## Part 3 — Configure your environment

Copy the example file and fill it in:
```
$ cp .env.example .env
```

Open `.env` in an editor and set:
```
DISCORD_TOKEN=paste-your-token-here
DEV_GUILD_ID=paste-your-server-id-here
AWS_REGION=us-east-1
PET_TABLE=ServerPet
DYNAMODB_ENDPOINT=http://localhost:8000
```
Leave `DISCORD_TOKEN_PARAM` commented out (that's for the AWS deploy later).

✅ `.env` has a real token, a real server ID, and `DYNAMODB_ENDPOINT`
uncommented. (`.env` is git-ignored, so it won't be committed.)

---

## Part 4 — Start the local database

In a **separate terminal**, start DynamoDB Local:
```
$ docker run -p 8000:8000 amazon/dynamodb-local
```
Leave this running. It listens on port 8000.

> This stores data **in memory** — stopping the container wipes the pet, which
> is perfect for testing. To keep data between restarts instead, use:
> `docker run -p 8000:8000 -v "$(pwd)/dynamodb-data:/data" amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -dbPath /data`

✅ The terminal shows DynamoDB Local's startup banner and stays running.

---

## Part 5 — First launch

Back in your venv terminal:
```
$ python bot.py
```

On success you'll see:
```
Logged in as Server Pet#1234 — pet bot ready.
```
The bot creates the `ServerPet` table automatically on first run and syncs the
slash commands to your `DEV_GUILD_ID` instantly.

✅ The bot shows **online** in your server, and typing `/` in any channel
reveals `status`, `feed`, `play`, `pet`, `rename`, and `checkin`.

If anything went wrong here, jump to **Troubleshooting** (Part 10).

> To stop the bot, press `Ctrl+C`. Any time you edit `config.py` or the code,
> stop and re-run `python bot.py` to load the changes.

---

## Part 6 — Verify Milestone 1 (the pet and care)

In your server, run each command and confirm the result.

1. **`/status`** — the pet is born. You should see an embed titled
   "🐾 a nameless blob" with a **Level 1** bar and three full stat bars
   (hunger, happiness, energy) all at 100, footer "generation 1 · violet".

2. **`/rename Blobby`** — the embed updates and the title becomes
   "🐾 Blobby". Run `/status` again to confirm the name stuck.

3. **`/feed`** — the embed shows "you feed the pet. Blobby munches happily."
   Hunger was already 100 so it stays capped, but XP ticks up. Run it a few
   times and watch the **Level** XP bar fill.

4. **`/play`** — happiness goes up, **energy goes down** by 20 each time.
   Spam it ~5 times and you'll eventually get "is too tired to play — let it
   rest." That's energy hitting the floor; it recovers on its own over time.

5. **`/pet`** — happiness rises, small XP.

✅ Care commands change stats, the embed redraws each time, and you've seen the
"too tired" guard fire.

### See the data in DynamoDB

This is the satisfying AWS bit. In a third terminal, give the CLI dummy
credentials (DynamoDB Local ignores them but the CLI insists on having some):
```
$ export AWS_ACCESS_KEY_ID=local
$ export AWS_SECRET_ACCESS_KEY=local
$ export AWS_DEFAULT_REGION=us-east-1
$ aws dynamodb scan --table-name ServerPet --endpoint-url http://localhost:8000
```
You'll see one item with `sk = "PET"` holding `name`, `level`, `hunger`,
`happiness`, `energy`, `stats_updated_at`, `generation`, and `color_index`.

✅ The scan returns your pet item with the stats you'd expect.

### Confirm the slow, lazy decay

The pet decays in real time but slowly (hunger ~1.5/hour). To see it move
without waiting hours, you can fast-forward by backdating the timestamp. Grab
your server ID, then:
```
$ aws dynamodb update-item --table-name ServerPet \
    --endpoint-url http://localhost:8000 \
    --key '{"pk":{"S":"GUILD#YOUR_SERVER_ID"},"sk":{"S":"PET"}}' \
    --update-expression "SET stats_updated_at = stats_updated_at - :h" \
    --expression-attribute-values '{":h":{"N":"86400"}}'
```
That rewinds the "last settled" time by 86,400 seconds (one day). Now run
`/status` — hunger and happiness will have dropped by about a day's worth,
proving decay is computed on read.

✅ After the rewind, `/status` shows lower hunger/happiness.

---

## Part 7 — Verify Milestone 2 (XP and streaks)

**Passive XP from chatting:**
1. Send several normal messages in a channel the bot can see.
2. Each message grants the pet a little XP, but only **once per minute per
   person** (the anti-spam cooldown), so type slowly or with a friend.
3. When enough accumulates to cross a level, the bot posts
   "✨ all your chatting leveled Blobby up to **N**!" in that channel.

> Want to see a level-up fast? Lower the cooldown in `config.py`
> (`PASSIVE_XP_COOLDOWN = 1`) and bump `XP_PASSIVE = 40`, restart the bot, send
> a few messages, then **revert** those values.

✅ Chatting raises the pet's XP and a level-up message eventually appears.

**Daily check-in streak:**
1. Run **`/checkin`** — "first check-in! streak: **1** 🔥".
2. Run it again — "already checked in today. streak: **1**".

To verify the streak *extends* without waiting until tomorrow, backdate your
own check-in record (run `/checkin` once first so the record exists), using
your server ID and your user ID (right-click your name → Copy User ID):
```
$ aws dynamodb update-item --table-name ServerPet \
    --endpoint-url http://localhost:8000 \
    --key '{"pk":{"S":"GUILD#YOUR_SERVER_ID"},"sk":{"S":"USER#YOUR_USER_ID"}}' \
    --update-expression "SET last_checkin = :d" \
    --expression-attribute-values '{":d":{"S":"2020-01-01"}}'
```
That sets your last check-in far in the past. Run `/checkin` again — because
the gap is more than one day, you'll see "welcome back! streak restarted".
(To test the *extend* case specifically, set the date to literally yesterday.)

✅ `/checkin` returns first / already / reset states correctly.

---

## Part 8 — Test the death → respawn cycle on purpose

You don't want to wait five days, so temporarily make the pet fragile.

1. Stop the bot (`Ctrl+C`).
2. In **`config.py`**, set these three values for the test:
   ```python
   HUNGER_DECAY_PER_HOUR = 5000
   HAPPINESS_DECAY_PER_HOUR = 5000
   DEATH_GRACE_HOURS = 0
   ```
3. Restart: `$ python bot.py`
4. Wait ~10 seconds (so a little time elapses), then run **`/status`**.

The pet's hunger and happiness instantly bottom out, the zero-grace window
means it dies immediately, and the bot replies with the tombstone embed:
"🪦 a chapter ends…" announcing the death **and** a freshly hatched, nameless
pet **in a new color** (violet → teal) with **generation 2**.

5. Run **`/rename Blobby II`** to name the newborn.
6. **Revert `config.py`** to the original values (1.5, 1.0, 24) and restart the
   bot so your real pet is gentle again.

✅ You saw a death announcement, an automatic respawn in a different color with
an incremented generation, and successfully renamed the new pet.

---

## Part 9 — Inspecting and resetting

- **See everything stored:** the `aws dynamodb scan` command from Part 6.
- **Wipe and start fresh:** stop DynamoDB Local (`Ctrl+C` in its terminal) and
  re-run the `docker run` command — in-memory data is gone, and the next bot
  start recreates the table and a brand-new pet.
- **Delete just the pet** (keep user records):
  ```
  $ aws dynamodb delete-item --table-name ServerPet \
      --endpoint-url http://localhost:8000 \
      --key '{"pk":{"S":"GUILD#YOUR_SERVER_ID"},"sk":{"S":"PET"}}'
  ```

---

## Part 10 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `PrivilegedIntentsRequired` crash on startup | Message Content Intent not enabled | Turn it on in Developer Portal → Bot, save, restart |
| `LoginFailure: Improper token has been passed` | Wrong/blank token, or stray quotes/spaces in `.env` | Re-copy the token; no quotes around it in `.env` |
| Bot is online but `/` shows no commands | Missing `applications.commands` scope, or you didn't set `DEV_GUILD_ID` (global sync is slow) | Re-invite with the scope; set `DEV_GUILD_ID` and restart |
| `EndpointConnectionError` / `Could not connect to ... 8000` | DynamoDB Local isn't running or wrong endpoint | Start the `docker run` container; confirm `DYNAMODB_ENDPOINT=http://localhost:8000` |
| `Unable to locate credentials` | AWS CLI/boto3 has no creds (even Local needs placeholders) | Export the dummy `AWS_ACCESS_KEY_ID`/`SECRET` from Part 6 |
| Commands respond "application did not respond" | The bot process isn't running, or crashed | Check the `python bot.py` terminal for errors and restart |
| Edited `config.py` but nothing changed | The bot loads config at startup | Stop (`Ctrl+C`) and re-run `python bot.py` |

---

## Part 11 — Completion checklist

- [ ] Bot shows **online** in the server
- [ ] All six slash commands appear and respond
- [ ] `/status` shows the pet with stat bars and a color
- [ ] `/feed`, `/play`, `/pet` change stats; "too tired" guard works
- [ ] `/rename` changes the name
- [ ] The pet item is visible via `aws dynamodb scan`
- [ ] Backdating the timestamp shows decay on `/status`
- [ ] Chatting grants XP and produces a level-up message
- [ ] `/checkin` returns first / already / reset states
- [ ] Forced death produced a tombstone + a new-color, gen-2 respawn
- [ ] `config.py` reverted to gentle values afterward

If every box is ticked, milestones 1 and 2 are complete. 🎉

---

## Part 12 — What's next

- **Milestone 3** — deploy 24/7 on EC2 (see the README's AWS section; switch
  from `DISCORD_TOKEN` to the SSM `DISCORD_TOKEN_PARAM`).
- **Milestone 4** — the daily nudge via EventBridge → Lambda (the
  `nudges_enabled` flag is already in the data model).
- **Milestone 5** — S3-hosted gif animations per action.

Send me the pet's real name, species, and personality whenever you like and
I'll bake those in, and say the word for the milestone 4 build.
