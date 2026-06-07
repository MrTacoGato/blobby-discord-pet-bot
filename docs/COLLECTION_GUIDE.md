# Milestone 3 — The Shared Server Collection (Detailed Guide)

This builds the **collection game** on top of the living pet from Milestones
1–2. By the end your server will have:

- **Three actions only:** `/feed`, `/pet`, and `/wish`.
- A **shared star pool**: every member's `/feed` and `/pet` pour ⭐ into one
  server-wide bank.
- **`/wish`**: spend ⭐ to pull a random **species × color** into a shared
  **Collection** of **30** collectibles (6 species × 5 colors).
- **`/collection`**: the whole server's album, with per-species progress.
- **Pixel-art sprites**: every species × color is a real PNG attached to the
  `/status`, `/wish`, and death embeds.
- Rarity: common species fill the book fast; `frost` is the chase.
- **Gentle neglect-death.** No manual "die" button — Blobby only passes after
  **15 days with zero care from anyone**, then a fresh random pet hatches and
  the collection carries over untouched.

Built for a friend-sized server of **up to ~10 people** collecting together.

Estimated time: **25–45 minutes**. All of it is editing five files you
already have (plus generating the sprite art once), then restarting.

> Throughout, lines starting with `$` are commands to run. A ✅ marks a
> checkpoint — confirm it before moving on. This guide assumes Milestones 1–2
> are working (bot runs locally against DynamoDB Local). If not, finish
> `SETUP_GUIDE.md` first.

---

## Part 0 — What changes, and the data model

You'll touch five files:

| File | Change |
|---|---|
| `config.py` | 6 species with their own color sets + rarity, the gacha knobs (`STAR_FEED`, `STAR_PET`, `WISH_COST`, `DUPE_REFUND`), and the **15-day** neglect-death pacing. |
| `pet.py` | Gate death behind `DEATHS_ENABLED`; add the collection logic (`new_collection`, `grant_stars`, `wish`, `discover`, `collection_progress`). |
| `storage.py` | Read/write one **shared** collection record per server. |
| `sprites.py` | **New file.** Renders each species × color to a PNG in `sprites/`. |
| `bot.py` | Award stars on feed/pet, add `/wish` and `/collection`, drop `/play`, attach sprite PNGs, keep the death→respawn flow. |

**The shared record.** The pet already lives at `sk = "PET"` under
`pk = "GUILD#<id>"`. The collection is a **second server-level item** at the
same partition:

```
pk = "GUILD#<guild_id>"
sk = "COLLECTION"
{
  "discovered": ["blob:0", "frost:3", ...],   # "species:color_index" keys
  "stars": 0,                                   # shared pool, everyone adds/spends
  "wishes_made": 0
}
```

Because it's keyed by **guild**, not by user, it is shared by everyone in the
server automatically — exactly what we want for up to 10 collectors.

✅ You understand: pet = `sk "PET"`, collection = `sk "COLLECTION"`, both
per-server.

---

## Part 1 — `config.py`: species, color sets, and the knobs

Replace the old **Appearance** / death section with the expanded species table
and the new gacha knobs. The important pieces:

```python
# Gentle neglect-death: no "die" button, dies only after 15 days of zero care.
# The engine counts its grace window AFTER both needs hit zero, so we subtract
# the slowest need's empty time to make the total land on exactly 15 days.
DEATHS_ENABLED = True
NEGLECT_DEATH_DAYS = 15
_happiness_empty_hours = MAX_STAT / HAPPINESS_DECAY_PER_HOUR  # 100h ≈ 4.2 days
DEATH_GRACE_HOURS = NEGLECT_DEATH_DAYS * 24 - _happiness_empty_hours  # = 260h

import random

# 6 species, each with its OWN color set. "rarity" is a wish draw WEIGHT
# (higher = pulled more often). Values are Discord embed colors.
SPECIES = {
    "blob":  {"set": "verdant", "rarity": 5, "colors": [
        ("lime", 0x99D742), ("green", 0x42D742), ("teal", 0x42D78C),
        ("jade", 0x42D7BE), ("fern", 0x73D742)]},
    "slime": {"set": "tidal", "rarity": 5, "colors": [
        ("cyan", 0x42B2D7), ("azure", 0x4280D7), ("blue", 0x424ED7),
        ("indigo", 0x6742D7), ("cobalt", 0x4267D7)]},
    "ember": {"set": "molten", "rarity": 5, "colors": [
        ("red", 0xD74742), ("vermilion", 0xD76E42), ("orange", 0xD78C42),
        ("amber", 0xD7AA42), ("ruby", 0xD75B42)]},
    "spark": {"set": "sunbeam", "rarity": 3, "colors": [
        ("gold", 0xD7B242), ("lemon", 0xD7CA42), ("honey", 0xD7A042),
        ("flax", 0xD7D742), ("marigold", 0xD7BE42)]},
    "wisp":  {"set": "spectral", "rarity": 3, "colors": [
        ("violet", 0xA542D7), ("orchid", 0xD742D7), ("fuchsia", 0xD742A5),
        ("rose", 0xD74273), ("plum", 0x8042D7)]},
    "frost": {"set": "glacier", "rarity": 2, "colors": [
        ("ice", 0x42CAD7), ("sky", 0x42B2D7), ("frost", 0x42A5D7),
        ("mint", 0x42D7C3), ("aqua", 0x42AFD7)]},
}
SPECIES_NAMES = list(SPECIES.keys())

def total_combos() -> int:
    return sum(len(s["colors"]) for s in SPECIES.values())

def random_species(weighted: bool = True) -> str:
    if not weighted:
        return random.choice(SPECIES_NAMES)
    pool = []
    for name, spec in SPECIES.items():
        pool.extend([name] * spec.get("rarity", 1))
    return random.choice(pool)

def random_color_index(species: str) -> int:
    return random.randrange(len(SPECIES[species]["colors"]))

def color_for(species: str, color_index: int):
    colors = SPECIES[species]["colors"]
    return colors[color_index % len(colors)]

# --- The gacha knobs (tune these freely) ---
STAR_FEED = 3       # ⭐ per /feed
STAR_PET = 2        # ⭐ per /pet
WISH_COST = 15      # ⭐ per wish
DUPE_REFUND = 5     # ⭐ back when a wish is a duplicate
EMBED_NEUTRAL = 0x5A5E52
```

> The color set mirrors the Game Boy palettes in `blobby_sprites.html`, so the
> in-Discord embed color of, say, an `azure slime` matches the sprite preview.

✅ `python -c "import config; print(config.total_combos(), config.SPECIES_NAMES)"`
prints `30 ['blob', 'slime', 'ember', 'spark', 'wisp', 'frost']`.

---

## Part 2 — `pet.py`: gate death, add the collection

**(a) Gate the death block** behind the config flag so the 15-day pacing is the
single source of truth (and you can flip deaths off entirely by setting
`DEATHS_ENABLED = False`):

```python
    if config.DEATHS_ENABLED and pet["hunger"] <= 0 and pet["happiness"] <= 0:
        ...  # (the original critical_since / grace-window logic)
    else:
        pet["critical_since"] = None
```

`respawn()` already rolls a brand-new random species + color, so when a pet
passes the next generation is a surprise — and because the collection lives in
its own record, **it carries over untouched** across a death.

Also make birth use a **flat** species pick (every species equally likely as
the live pet), while wishes stay weighted:

```python
    species = config.random_species(weighted=False)  # in new_pet()
```

**(b) Add the collection logic** at the bottom of `pet.py`:

```python
def new_collection() -> dict:
    return {"discovered": [], "stars": 0, "wishes_made": 0}

def combo_key(species, color_index): return f"{species}:{color_index}"

def grant_stars(collection, amount):
    collection["stars"] = collection.get("stars", 0) + amount
    return collection["stars"]

def discover(collection, species, color_index) -> bool:
    key = combo_key(species, color_index)
    found = collection.setdefault("discovered", [])
    if key in found:
        return False
    found.append(key)
    return True

def can_wish(collection) -> bool:
    return collection.get("stars", 0) >= config.WISH_COST

def wish(collection) -> dict:
    if not can_wish(collection):
        return {"result": "broke", "need": config.WISH_COST,
                "have": collection.get("stars", 0)}
    collection["stars"] -= config.WISH_COST
    collection["wishes_made"] = collection.get("wishes_made", 0) + 1
    species = config.random_species(weighted=True)
    color_index = config.random_color_index(species)
    color_name, _ = config.color_for(species, color_index)
    if discover(collection, species, color_index):
        return {"result": "new", "species": species, "color": color_name,
                "color_index": color_index,
                "found": len(collection["discovered"]), "total": config.total_combos()}
    collection["stars"] += config.DUPE_REFUND
    return {"result": "dupe", "species": species, "color": color_name,
            "color_index": color_index, "refund": config.DUPE_REFUND}

def collection_progress(collection):
    found = set(collection.get("discovered", []))
    per = []
    for name, spec in config.SPECIES.items():
        n = len(spec["colors"])
        got = sum(1 for ci in range(n) if combo_key(name, ci) in found)
        per.append((name, got, n))
    return len(found), config.total_combos(), per
```

✅ Quick logic check (no Discord/AWS needed):
```
$ python -c "
import pet, config
c = pet.new_collection(); pet.grant_stars(c, 100)
seen=set()
while pet.can_wish(c): seen.add(pet.wish(c).get('species'))
print('drew species:', seen, '| stars left:', c['stars'])"
```
It prints some species and a leftover star count below 15.

---

## Part 3 — `storage.py`: the shared record

Add a key helper and load/save functions next to the pet ones:

```python
def _collection_key(guild_id: int):
    return {"pk": f"GUILD#{guild_id}", "sk": "COLLECTION"}

def load_collection(guild_id: int):
    resp = _get_table().get_item(Key=_collection_key(guild_id))
    item = resp.get("Item")
    return _from_dynamo(item) if item else None

def save_collection(guild_id: int, collection: dict):
    item = {**_collection_key(guild_id), **collection}
    _get_table().put_item(Item=_to_dynamo(item))
```

No new table — it reuses `ServerPet` with a different `sk`.

✅ `python -c "import storage"` imports without error.

---

## Part 4 — `bot.py`: stars, `/wish`, `/collection`, drop `/play`

**(a) Storage glue + a refresher** for the collection:

```python
async def _load_collection(gid):
    return await asyncio.to_thread(storage.load_collection, gid)

async def _save_collection(gid, collection):
    await asyncio.to_thread(storage.save_collection, gid, collection)

async def refresh_collection(gid):
    coll = await _load_collection(gid)
    if coll is None:
        coll = petlib.new_collection()
        await _save_collection(gid, coll)
    return coll
```

**(b) Award stars on care.** Give `_respond_with_action` a `stars=` argument; on
a successful action, grant to the shared pool and save:

```python
    if ok and stars:
        petlib.grant_stars(collection, stars)
        await _save_collection(gid, collection)
```

Then wire the care commands (and **remove the old `/play` command**):

```python
@bot.tree.command(name="feed", description="Feed the server pet (earns ⭐)")
async def feed(interaction):
    await _respond_with_action(interaction, petlib.feed, "feeds the pet", stars=config.STAR_FEED)

@bot.tree.command(name="pet", description="Pet the server pet (earns ⭐)")
async def pet_cmd(interaction):
    await _respond_with_action(interaction, petlib.pet_action, "pets the pet", stars=config.STAR_PET)
```

**(c) The two new commands:**

```python
@bot.tree.command(name="wish", description="Spend the server's ⭐ on a collection pull")
async def wish(interaction):
    await interaction.response.defer()
    gid = interaction.guild_id
    collection = await refresh_collection(gid)
    result = petlib.wish(collection)
    await _save_collection(gid, collection)
    await interaction.followup.send(embed=wish_embed(result))

@bot.tree.command(name="collection", description="See the server's shared Blob collection")
async def collection_cmd(interaction):
    await interaction.response.defer()
    collection = await refresh_collection(interaction.guild_id)
    await interaction.followup.send(embed=collection_embed(collection))
```

**(d) Attach the sprite PNG.** A tiny helper turns a combo into a Discord file,
and the embeds set it as a thumbnail (`/status`, death) or full image (`/wish`):

```python
import sprites

def sprite_file(species, color_index, as_name="sprite.png"):
    try:
        return discord.File(sprites.sprite_path(species, color_index), filename=as_name)
    except (FileNotFoundError, OSError):
        return None  # art not built yet — embed still works, just no picture
```

Each embed builder returns `(embed, file)`; the embed calls
`e.set_thumbnail(url="attachment://sprite.png")` (or `set_image` for `/wish`),
and the command sends both: `await interaction.followup.send(embed=e, file=f)`.

**(e) Keep death → respawn, and seed the collection.** `refresh_pet` returns
`(pet, death_event)`. On death it spawns a fresh random pet, and a
`_seed_collection` helper records the live pet's own combo as discovered:

```python
async def _seed_collection(gid, pet):
    coll = await refresh_collection(gid)
    if petlib.discover(coll, pet["species"], pet["color_index"]):
        await _save_collection(gid, coll)
```

`wish_embed`, `collection_embed`, and `death_embed` bodies are all in your
`bot.py`.

✅ `python -m py_compile bot.py config.py pet.py storage.py sprites.py` prints
nothing (success).

---

## Part 4b — Bake the sprite art

`sprites.py` renders each species × color to a transparent PNG using the same
pixel grids and ramps as `blobby_sprites.html`. You only need Pillow to *build*
the art — the bot just attaches the finished files.

```
$ pip install Pillow
$ python sprites.py
```
This writes 30 files into `sprites/` (e.g. `blob_0_lime.png`,
`frost_2_frost.png`). Re-run it any time you tweak a shape or color.

> The bot loads these by path at send time, so Pillow is **not** needed to run
> the bot — only to regenerate art. Commit the `sprites/` folder so a deploy has
> the images.

✅ `ls sprites | wc -l` prints `30`, and opening any PNG shows a Game Boy blob
on a transparent background.

---

## Part 5 — Restart and re-sync

```
$ python bot.py
```
On a guild sync (`DEV_GUILD_ID` set) the command list updates instantly.

✅ Typing `/` shows `status`, `feed`, `pet`, `wish`, `collection`, `rename`,
`checkin` — and **no** `play`.

---

## Part 6 — Verify the collection loop

1. **`/status`** — the pet shows its **pixel sprite** as a thumbnail, its bars,
   plus two new lines: **✨ server stars** and **📖 collection** (e.g.
   `1/30 found` — the live pet's own combo seeds the album).

2. **`/feed`** a few times — each reply ends with `(+3 ⭐)` and the server star
   count climbs. **`/pet`** gives `(+2 ⭐)`.

3. **`/wish`** once you have ≥ 15 ⭐ — the reply shows the **pulled sprite as a
   full image** and is either:
   - 🎉 **NEW! a `<color> <species>`** with an updated `found/total`, or
   - ✨ **duplicate** with **+5 ⭐ refunded**.

4. Spam `/wish` until you hit a duplicate and confirm the **refund** lands
   (stars drop by 15, then come back up by 5).

5. **`/wish`** with under 15 ⭐ — you get the friendly "not enough stars"
   message, no crash.

6. **`/collection`** — the album embed lists all six species with `got/5` bars
   and the star pool in the footer.

✅ Sprites render in the embeds, stars accrue from care, wishes pull
collectibles, dupes refund, and the album reflects what you've found.

### Confirm the 15-day neglect-death (and that it's hard to trigger)

There's no "die" button; death only comes from ~15 days of total neglect. To
prove the timing without waiting, backdate the pet's clock and bottom out its
needs. First, **just under** the threshold — 14 days:
```
$ aws dynamodb update-item --table-name ServerPet \
    --endpoint-url http://localhost:8000 \
    --key '{"pk":{"S":"GUILD#YOUR_SERVER_ID"},"sk":{"S":"PET"}}' \
    --update-expression "SET stats_updated_at = stats_updated_at - :h" \
    --expression-attribute-values '{":h":{"N":"1209600"}}'   # 14 days
```
`/status` shows a **⚠️ neglected** warning ("will pass in ~1d without care") but
the pet is still alive. Now push past 15 days (rewind another 2 days):
```
$ aws dynamodb update-item --table-name ServerPet \
    --endpoint-url http://localhost:8000 \
    --key '{"pk":{"S":"GUILD#YOUR_SERVER_ID"},"sk":{"S":"PET"}}' \
    --update-expression "SET stats_updated_at = stats_updated_at - :h" \
    --expression-attribute-values '{":h":{"N":"172800"}}'    # +2 days
```
`/status` now returns the 🪦 tombstone: the old pet passed and a fresh **random**
species + color hatched at the next generation (rename it with `/rename`).

✅ Survives 14 days of neglect with a warning; passes just after 15 — and the
collection still shows everything you'd found.

---

## Part 7 — Test the *shared* pool with up to 10 people

The pool and album are server-level, so this needs no per-user setup:

1. Have **two or more members** each run `/feed` and `/pet`. Watch the **same**
   ✨ server-stars number rise no matter who acts.
2. One member runs `/wish`; another runs `/collection` — they see the **same**
   updated album. Discoveries are shared instantly.
3. With ~10 people each doing a handful of care actions a day, the pool funds
   several wishes daily; a full 30/30 album is a **multi-week shared goal**
   (see the pacing note in Part 9).

> There's no per-user lock on wishing — anyone can spend the shared pool. If you
> later want only certain roles to wish, gate the `/wish` command on a Discord
> role; the data model doesn't need to change.

✅ Two accounts see one shared star count and one shared album.

---

## Part 8 — Inspect the shared record in DynamoDB

```
$ aws dynamodb get-item --table-name ServerPet \
    --endpoint-url http://localhost:8000 \
    --key '{"pk":{"S":"GUILD#YOUR_SERVER_ID"},"sk":{"S":"COLLECTION"}}'
```
You'll see `stars`, `wishes_made`, and a `discovered` list of
`"species:color_index"` strings.

✅ The `COLLECTION` item reflects your stars and discoveries.

---

## Part 9 — Tuning for your server size

All knobs live in `config.py`. Defaults are tuned for a ~10-person server.

| Knob | Default | Raise it to… | Lower it to… |
|---|---|---|---|
| `STAR_FEED` / `STAR_PET` | 3 / 2 | hand out stars faster (more wishes) | slow the economy |
| `WISH_COST` | 15 | make wishes feel rarer/bigger | let people pull constantly |
| `DUPE_REFUND` | 5 | soften dupes (closer to free re-rolls) | make dupes sting a little |
| `rarity` (per species) | 5/5/5/3/3/2 | make a species more common | make it the chase |
| color count per species | 5 | grow the album (more to collect) | shrink it |

**Pacing math.** With the defaults, ~30 wishes worth of *new* pulls plus
duplicates means a 10-person server casually doing care actions completes the
album in roughly **2–4 weeks** — enough to stay a goal without feeling endless.
Bigger server? Raise `WISH_COST` or add colors. Tiny server? Lower `WISH_COST`
or raise the star grants.

> After editing `config.py`, stop (`Ctrl+C`) and re-run `python bot.py` — config
> loads at startup.

---

## Part 10 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/wish` says "not enough stars" immediately | Fresh server, empty pool | `/feed` and `/pet` a few times first |
| `/play` still appears | Old command still registered / stale guild cache | Remove the `/play` command, restart; if it lingers, re-invite or wait for re-sync |
| Stars don't go up on `/feed` | `stars=` not passed to `_respond_with_action`, or save skipped | Confirm `stars=config.STAR_FEED` and the `grant_stars` + `_save_collection` lines |
| Embeds have no picture | `sprites/` empty, or `sprites.py` not run | `pip install Pillow && python sprites.py`; confirm `sprites/` has 30 PNGs. (Embeds still send fine without art.) |
| `ModuleNotFoundError: PIL` when running the bot | You imported `render`/`build_all` at runtime | The bot only needs `sprites.sprite_path` (no Pillow). Don't call the renderer at runtime |
| Pet dies too fast / too slow | Wrong `NEGLECT_DEATH_DAYS`, or decay rates changed | Set `NEGLECT_DEATH_DAYS`; the grace auto-adjusts. To disable death entirely set `DEATHS_ENABLED = False` |
| `KeyError: 'COLLECTION'`-ish / `NoneType` on wish | First wish before the record exists | Use `refresh_collection` (creates an empty one) — never `load_collection` directly |
| Everyone sees a *different* album | Accidentally keyed by user (`USER#...`) instead of guild | The collection `sk` must be the literal `"COLLECTION"`, partition `GUILD#<id>` |
| Embed color looks wrong | Color int typo | Colors are `0xRRGGBB`; compare against `config.SPECIES` |

---

## Part 11 — Completion checklist

- [ ] `python sprites.py` produced 30 PNGs in `sprites/`
- [ ] `/` shows `feed`, `pet`, `wish`, `collection` — and no `play`
- [ ] `/status` shows the pet's sprite thumbnail
- [ ] `/feed` and `/pet` add ⭐ to a shared, server-wide pool
- [ ] `/wish` pulls a random species × color with its sprite image; `found/total` updates
- [ ] Duplicates refund `DUPE_REFUND` ⭐
- [ ] `/wish` with too few stars gives a friendly message, no crash
- [ ] `/collection` shows all 6 species with per-species progress
- [ ] Pet survives 14 days of neglect (with a warning) but passes just after 15
- [ ] After a death, the collection still shows everything found
- [ ] Two accounts see the *same* stars and the *same* album
- [ ] The `COLLECTION` item is visible via `aws dynamodb get-item`
- [ ] `config.py` knobs tuned to your server's size

If every box is ticked, the shared collection is live. 🎉

---

## Part 12 — What's next

- **Composite album image.** `/collection` is text bars today; render a single
  contact-sheet PNG (found in color, missing as dark silhouettes) by composing
  the `sprites/` files with Pillow at request time.
- **Animated sprites.** Export 2–3 frame GIFs (a little squash/bounce) per combo
  and attach those instead of static PNGs.
- **Leaderboards.** You already store `xp_contributed` per user — add a
  `stars_contributed` counter for a "top collectors" board.
- **Seasonal species.** Add a limited-time species with its own color set and a
  higher rarity for events; remove it after.

Say the word and I'll build the composite `/collection` image or the animated
sprites next.
