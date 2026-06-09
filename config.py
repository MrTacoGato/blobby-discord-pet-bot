"""
Central configuration and the engagement-tuning knobs.

If the pet ever feels like a chore instead of fun, this is the only file
you need to touch: the decay rates below are deliberately slow (measured in
DAYS, not hours). See the "death pacing" note at the bottom.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# --------------------------------------------------------------------------
# AWS / DynamoDB
# --------------------------------------------------------------------------
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("PET_TABLE", "ServerPet")

# For local development, run DynamoDB Local in Docker and point at it:
#   docker run -p 8000:8000 amazon/dynamodb-local
#   export DYNAMODB_ENDPOINT=http://localhost:8000
# In production (real DynamoDB) leave this unset.
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT") or None


# --------------------------------------------------------------------------
# Discord
# --------------------------------------------------------------------------
# Optional: a single guild (server) id for INSTANT slash-command sync while
# developing. Global sync can take up to an hour to propagate; guild sync is
# immediate. Leave unset for production.
DEV_GUILD_ID = os.environ.get("DEV_GUILD_ID") or None


def _load_token() -> str:
    """Prefer an env var locally; fall back to SSM Parameter Store in prod."""
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        return token
    param = os.environ.get("DISCORD_TOKEN_PARAM")
    if param:
        import boto3

        ssm = boto3.client("ssm", region_name=AWS_REGION)
        resp = ssm.get_parameter(Name=param, WithDecryption=True)
        return resp["Parameter"]["Value"]
    return ""


DISCORD_TOKEN = _load_token()


# --------------------------------------------------------------------------
# Engagement tuning  <-- the "fun, not a chore" knobs
# --------------------------------------------------------------------------
MAX_STAT = 100
MIN_STAT = 0

# Two needs decay over time; one resource (energy) recovers over time.
# Rates are PER HOUR and intentionally gentle so light, occasional care
# keeps the pet thriving. Starting from a full 100:
#   hunger    @ 1.5/hr  -> empty in ~2.8 days of zero care
#   happiness @ 1.0/hr  -> empty in ~4.2 days of zero care
HUNGER_DECAY_PER_HOUR = 1.5
HAPPINESS_DECAY_PER_HOUR = 1.0
ENERGY_REGEN_PER_HOUR = 4.0  # rests back to full in ~1 day

# Care action effects.
FEED_HUNGER = 30
PLAY_HAPPINESS = 25
PLAY_ENERGY_COST = 20
PLAY_MIN_ENERGY = 15  # too tired to play below this
PET_HAPPINESS = 15

# XP / leveling.
XP_FEED = 5
XP_PLAY = 8
XP_PET = 4
XP_PASSIVE = 2  # per qualifying chat message (rate-limited below)
PASSIVE_XP_COOLDOWN = 60  # seconds between passive-XP grants per member
# Don't post a level-up message in a channel more than once per this window, so
# a busy server can't make the bot spam announcements (anti-quarantine, #8).
LEVELUP_ANNOUNCE_COOLDOWN = 120  # seconds between level-up posts per channel


def xp_to_next(level: int) -> int:
    """XP required to advance FROM the given level to the next."""
    return level * 60


# --------------------------------------------------------------------------
# Death pacing
# --------------------------------------------------------------------------
# Neglect-death is ON, but very forgiving: there is NO manual "die" button.
# Blobby only passes if BOTH hunger AND happiness sit at zero continuously for
# DEATH_GRACE_HOURS. With the slow decay above (needs empty in ~3-4 days) plus a
# 15-day grace, the pet survives all normal life gaps and only dies after total
# abandonment -- in practice ~15 days with nobody in the server caring at all.
# When it does pass, the next generation hatches as a fresh RANDOM species+color
# and the shared Collection carries over untouched.
DEATHS_ENABLED = True
NEGLECT_DEATH_DAYS = 15  # total days with zero care before Blobby passes

# The engine counts the grace window only AFTER both needs hit zero. Happiness
# is the slowest need to empty, so we subtract that lead-in to make the total
# time-from-last-care land on exactly NEGLECT_DEATH_DAYS.
_happiness_empty_hours = MAX_STAT / HAPPINESS_DECAY_PER_HOUR  # 100h ≈ 4.2 days
DEATH_GRACE_HOURS = NEGLECT_DEATH_DAYS * 24 - _happiness_empty_hours  # = 260h


import random


# --------------------------------------------------------------------------
# Appearance -- species and color sets
# --------------------------------------------------------------------------
# The server's live pet has ONE species + color, picked at random at birth
# (players never choose it). Every species also exists as a collectible in
# the shared server Collection. Each species owns its OWN color set; these
# mirror the Game Boy Color sprite palettes in blobby_sprites.html. Values
# are Discord embed colors.
#
# "rarity" is a draw WEIGHT for wishes -- higher = pulled more often. Common
# species fill the album quickly; rare ones are the chase.
SPECIES = {
    "blob": {  # round classic
        "display": "Mosskin", "set": "verdant", "rarity": 5,
        "colors": [
            ("lime", 0x99D742), ("green", 0x42D742), ("teal", 0x42D78C),
            ("jade", 0x42D7BE), ("fern", 0x73D742),
        ],
    },
    "slime": {  # droplet
        "display": "Echo", "set": "tidal", "rarity": 5,
        "colors": [
            ("cyan", 0x42B2D7), ("azure", 0x4280D7), ("blue", 0x424ED7),
            ("indigo", 0x6742D7), ("cobalt", 0x4267D7),
        ],
    },
    "ember": {  # crystal
        "display": "Cinder", "set": "molten", "rarity": 5,
        "colors": [
            ("red", 0xD74742), ("vermilion", 0xD76E42), ("orange", 0xD78C42),
            ("amber", 0xD7AA42), ("ruby", 0xD75B42),
        ],
    },
    "spark": {  # antenna sprite
        "display": "Static", "set": "sunbeam", "rarity": 3,
        "colors": [
            ("gold", 0xD7B242), ("lemon", 0xD7CA42), ("honey", 0xD7A042),
            ("flax", 0xD7D742), ("marigold", 0xD7BE42),
        ],
    },
    "wisp": {  # ghost
        "display": "Phantom", "set": "spectral", "rarity": 3,
        "colors": [
            ("violet", 0xA542D7), ("orchid", 0xD742D7), ("fuchsia", 0xD742A5),
            ("rose", 0xD74273), ("plum", 0x8042D7),
        ],
    },
    "frost": {  # cloud (rare)
        "display": "Phosphor", "set": "glacier", "rarity": 2,
        "colors": [
            ("ice", 0x42CAD7), ("sky", 0x42B2D7), ("frost", 0x42A5D7),
            ("mint", 0x42D7C3), ("aqua", 0x42AFD7),
        ],
    },
}

SPECIES_NAMES = list(SPECIES.keys())


def species_name(species: str) -> str:
    """User-facing display name (e.g. 'Mosskin'); falls back to the key."""
    return SPECIES.get(species, {}).get("display", species.title())

DEAD_COLOR = 0x888780  # gray (legacy; unused while DEATHS_ENABLED is False)
EMBED_NEUTRAL = 0x5A5E52  # Game Boy bezel gray, used for the collection embed


def total_combos() -> int:
    """How many species x color collectibles exist in total."""
    return sum(len(s["colors"]) for s in SPECIES.values())


def random_species(weighted: bool = True) -> str:
    """Pick a species at random. Weighted by 'rarity' (the default, used by
    wishes); pass weighted=False for a flat pick (used at the pet's birth)."""
    if not weighted:
        return random.choice(SPECIES_NAMES)
    pool = []
    for name, spec in SPECIES.items():
        pool.extend([name] * spec.get("rarity", 1))
    return random.choice(pool)


def random_color_index(species: str) -> int:
    """Pick a random color slot within the given species' own color set."""
    return random.randrange(len(SPECIES[species]["colors"]))


def color_for(species: str, color_index: int):
    """Return (color_name, embed_value) for a species + color slot."""
    colors = SPECIES[species]["colors"]
    return colors[color_index % len(colors)]


# --------------------------------------------------------------------------
# Collection / wishes  (the shared, server-wide gacha loop)
# --------------------------------------------------------------------------
# Feeding and petting earn STARS into a single pool shared by everyone in the
# server. A wish spends stars to pull a random species+color into the shared
# Collection. A duplicate refunds part of the cost, so a pull is never wasted.
STAR_FEED = 3        # stars granted per /feed
STAR_PET = 2         # stars granted per /pet
WISH_COST = 15       # stars to make one wish
DUPE_REFUND = 5      # stars returned when a wish is a duplicate


# --------------------------------------------------------------------------
# Coins  (the per-user cosmetics currency -- earned, never bought)
# --------------------------------------------------------------------------
# Distinct from the shared STAR pool: Coins are personal, earned on a daily /
# engagement cadence, and spent on direct-purchase cosmetics. No randomness,
# no real money -- a clean, deterministic shop.
COIN_CALENDAR = [2, 3, 4, 5, 6, 8, 12]  # /checkin day 1->7 payout, then loops
FORAGE_REWARD = 2        # coins per /forage
FORAGE_COOLDOWN = 600    # seconds (10 min) between forages, per user
COIN_PER_LEVEL = 3       # coins to whoever pushes the pet to a new level


# --------------------------------------------------------------------------
# Cosmetic items  (a direct-purchase shop -- you buy the exact item, no pulls)
# --------------------------------------------------------------------------
# Rarity sets the PRICE (a save-up-for-it goal), not a draw chance. One item is
# equipped on the shared pet at a time. Visual layering on the sprite is a later
# phase -- for now items show as an emoji in /shop and /inventory.
ITEM_PRICE = {"common": 8, "uncommon": 20, "rare": 60, "legendary": 200}  # coins

ITEMS = {
    "party_hat":  {"name": "Party Hat",    "rarity": "common",    "emoji": "🎉"},
    "shades":     {"name": "8-Bit Shades", "rarity": "common",    "emoji": "🕶️"},
    "scarf":      {"name": "Cozy Scarf",   "rarity": "uncommon",  "emoji": "🧣"},
    "headphones": {"name": "Headphones",   "rarity": "uncommon",  "emoji": "🎧"},
    "crown":      {"name": "Tiny Crown",   "rarity": "rare",      "emoji": "👑"},
    "halo":       {"name": "Halo",         "rarity": "rare",      "emoji": "😇"},
    "star_aura":  {"name": "Star Aura",    "rarity": "legendary", "emoji": "✨"},
}


def item_price(item_id: str) -> int:
    """Coin price for an item, derived from its rarity."""
    return ITEM_PRICE[ITEMS[item_id]["rarity"]]


# --------------------------------------------------------------------------
# Monetization (Discord Premium Apps) -- INERT until SKU IDs are set.
#
# The shop above (`/shop`, `/buy`) is the FREE coins economy. This section is the
# *real-money* layer: deterministic, cosmetic, recognition-based offerings sold
# through Discord's in-app purchases. Nothing here is randomized or pay-to-win.
#
# It stays completely dormant until you create the SKUs in
# Dev Portal -> Monetization and paste their IDs into these env vars. With every
# SKU unset, MONETIZATION_ENABLED is False: no `/perks`, no `/hall`, no premium
# buttons -- the bot runs exactly as it does today. Flip it on one SKU at a time.
#
# See plans/MONETIZATION_PLAYBOOK.md (what/why) and plans/ELIGIBILITY_RUNBOOK.md.
# --------------------------------------------------------------------------
# Discord SKU snowflake IDs (strings). Leave unset to keep a feature dormant.
SKU_CARETAKER  = os.environ.get("SKU_CARETAKER")  or None   # Guild Subscription
SKU_MEMORIAL   = os.environ.get("SKU_MEMORIAL")   or None   # Durable (one-time)
SKU_GIFT_FROST = os.environ.get("SKU_GIFT_FROST") or None   # Durable (guild gift)

# Display catalog. Prices are display-only labels; Discord is the source of truth
# for actual pricing and entitlements. `sku_id=None` => that row is hidden.
SKUS = {
    "caretaker": {
        "sku_id": SKU_CARETAKER, "name": "Caretaker", "emoji": "🕯️",
        "price": "$4.99/mo",
        "blurb": "Support the server's pet: a supporter badge on /status, a place "
                 "in /hall, and a say in the pet's name and color.",
    },
    "memorial": {
        "sku_id": SKU_MEMORIAL, "name": "Memorial", "emoji": "🪦",
        "price": "$2.49",
        "blurb": "A permanent framed tribute in /hall to the generation that "
                 "passed. A keepsake -- never a revive.",
    },
    "gift_frost": {
        "sku_id": SKU_GIFT_FROST, "name": "Gift the Frost character", "emoji": "🎁",
        "price": "$3.99",
        "blurb": "A visible thank-you to the whole server -- 'gifted the Frost "
                 "character to everyone.'",
    },
}

# True once at least one SKU id is configured. Gates all monetization surface.
MONETIZATION_ENABLED = any(s["sku_id"] for s in SKUS.values())


def sku(key: str):
    """Configured Discord SKU id for a catalog key, or None if it's dormant."""
    return SKUS.get(key, {}).get("sku_id")
