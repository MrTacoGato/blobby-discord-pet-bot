"""
Pure pet logic. No Discord, no AWS in here -- just functions that operate on
a plain pet dict. This makes the rules easy to read, tweak, and unit-test.

A pet dict looks like:
    {
        "name": "Blobby" | None,     # None == nameless, awaiting /rename
        "species": "blob",
        "generation": 1,
        "color_index": 0,
        "alive": True,
        "level": 1,
        "xp": 0,
        "hunger": 100.0,             # 0..100
        "happiness": 100.0,          # 0..100
        "energy": 100.0,             # 0..100
        "stats_updated_at": <epoch>, # last time stats were "settled"
        "critical_since": None | <epoch>,
        "created_at": <epoch>,
    }
"""

import time

import config


def now() -> float:
    return time.time()


def _clamp(v: float) -> float:
    return max(config.MIN_STAT, min(config.MAX_STAT, v))


# --------------------------------------------------------------------------
# Creation / respawn
# --------------------------------------------------------------------------
def new_pet(name=None, generation=1, species=None, color_index=None) -> dict:
    """Create a pet. Species AND color are random unless explicitly supplied
    (they never are in normal play -- both are decided by the draw)."""
    t = now()
    if species is None:
        species = config.random_species(weighted=False)  # flat pick at birth
    if color_index is None:
        color_index = config.random_color_index(species)
    return {
        "name": name,
        "species": species,
        "generation": generation,
        "color_index": color_index,
        "alive": True,
        "level": 1,
        "xp": 0,
        "hunger": float(config.MAX_STAT),
        "happiness": float(config.MAX_STAT),
        "energy": float(config.MAX_STAT),
        "stats_updated_at": t,
        "critical_since": None,
        "created_at": t,
    }


def respawn(dead_pet: dict) -> dict:
    """Spawn the next generation: a brand-new pet whose species AND color are
    both rolled fresh at random. The newcomer is nameless on purpose so it
    prompts a /rename."""
    return new_pet(
        name=None,
        generation=dead_pet.get("generation", 1) + 1,
        # species + color_index left None -> randomized in new_pet
    )


# --------------------------------------------------------------------------
# Lazy decay + death detection
# --------------------------------------------------------------------------
def settle(pet: dict, t: float | None = None) -> dict:
    """
    Advance stats to the present based on elapsed time, then update the
    death state. Called on every read so we never need a cron job.

    Death is computed precisely (not just "are stats zero right now") so a
    pet that was abandoned while no one was looking is correctly found dead.
    """
    if t is None:
        t = now()
    if not pet.get("alive", True):
        return pet

    su = pet["stats_updated_at"]
    elapsed_h = max(0.0, (t - su) / 3600.0)
    h0, p0 = pet["hunger"], pet["happiness"]

    # When (in epoch time) each need would hit zero, given linear decay.
    hunger_zero_at = (
        su + (h0 / config.HUNGER_DECAY_PER_HOUR) * 3600
        if config.HUNGER_DECAY_PER_HOUR > 0
        else float("inf")
    )
    happy_zero_at = (
        su + (p0 / config.HAPPINESS_DECAY_PER_HOUR) * 3600
        if config.HAPPINESS_DECAY_PER_HOUR > 0
        else float("inf")
    )

    pet["hunger"] = _clamp(h0 - config.HUNGER_DECAY_PER_HOUR * elapsed_h)
    pet["happiness"] = _clamp(p0 - config.HAPPINESS_DECAY_PER_HOUR * elapsed_h)
    pet["energy"] = _clamp(pet["energy"] + config.ENERGY_REGEN_PER_HOUR * elapsed_h)
    pet["stats_updated_at"] = t

    # Death is OFF by default (config.DEATHS_ENABLED is False): Blobby can never
    # be lost. Stats still decay so care matters, but the pet stays alive.
    if config.DEATHS_ENABLED and pet["hunger"] <= 0 and pet["happiness"] <= 0:
        # Only set critical_since the first time both needs bottom out, then
        # let that clock run. (Don't recompute it every settle, or the grace
        # window keeps resetting and the pet never actually dies.)
        if pet.get("critical_since") is None:
            critical_start = max(hunger_zero_at, happy_zero_at)
            critical_start = min(max(critical_start, su), t)  # clamp to interval
            pet["critical_since"] = critical_start
        if t - pet["critical_since"] >= config.DEATH_GRACE_HOURS * 3600:
            pet["alive"] = False
    else:
        pet["critical_since"] = None

    return pet


def hours_until_death(pet: dict, t: float | None = None) -> float | None:
    """Estimate hours until death at the current trajectory (None if safe)."""
    if t is None:
        t = now()
    if not pet.get("alive", True):
        return 0.0
    if pet["hunger"] <= 0 and pet["happiness"] <= 0 and pet.get("critical_since"):
        remaining = config.DEATH_GRACE_HOURS * 3600 - (t - pet["critical_since"])
        return max(0.0, remaining / 3600.0)
    return None


# --------------------------------------------------------------------------
# Leveling
# --------------------------------------------------------------------------
def add_xp(pet: dict, amount: int) -> int:
    """Add XP and return how many levels were gained (0 if none)."""
    if not pet.get("alive", True):
        return 0
    pet["xp"] += amount
    gained = 0
    while pet["xp"] >= config.xp_to_next(pet["level"]):
        pet["xp"] -= config.xp_to_next(pet["level"])
        pet["level"] += 1
        gained += 1
    return gained


# --------------------------------------------------------------------------
# Care actions -> (ok, message, levels_gained)
# --------------------------------------------------------------------------
def feed(pet: dict):
    if not pet.get("alive", True):
        return False, "is no longer with us.", 0
    pet["hunger"] = _clamp(pet["hunger"] + config.FEED_HUNGER)
    return True, "munches happily.", add_xp(pet, config.XP_FEED)


def play(pet: dict):
    if not pet.get("alive", True):
        return False, "is no longer with us.", 0
    if pet["energy"] < config.PLAY_MIN_ENERGY:
        return False, "is too tired to play -- let it rest.", 0
    pet["happiness"] = _clamp(pet["happiness"] + config.PLAY_HAPPINESS)
    pet["energy"] = _clamp(pet["energy"] - config.PLAY_ENERGY_COST)
    return True, "is having a blast!", add_xp(pet, config.XP_PLAY)


def pet_action(pet: dict):
    if not pet.get("alive", True):
        return False, "is no longer with us.", 0
    pet["happiness"] = _clamp(pet["happiness"] + config.PET_HAPPINESS)
    return True, "leans into the pets.", add_xp(pet, config.XP_PET)


# --------------------------------------------------------------------------
# Daily check-in streak (operates on a user dict)
# --------------------------------------------------------------------------
def check_in(user: dict, today: str):
    """today is an ISO date string 'YYYY-MM-DD'. Returns (status, streak)."""
    last = user.get("last_checkin")
    if last == today:
        return "already", user.get("streak", 1)

    streak = user.get("streak", 0)
    if last is None:
        streak, status = 1, "first"
    else:
        # Did they check in yesterday?
        from datetime import date

        y, m, d = (int(x) for x in last.split("-"))
        ty, tm, td = (int(x) for x in today.split("-"))
        gap = (date(ty, tm, td) - date(y, m, d)).days
        if gap == 1:
            streak, status = streak + 1, "extended"
        else:
            streak, status = 1, "reset"

    user["last_checkin"] = today
    user["streak"] = streak
    return status, streak


# --------------------------------------------------------------------------
# Rendering helpers
# --------------------------------------------------------------------------
def color_of(pet: dict):
    name, value = config.color_for(pet["species"], pet.get("color_index", 0))
    return name, value


def display_name(pet: dict) -> str:
    return pet["name"] if pet.get("name") else f"a nameless {config.species_name(pet['species'])}"


def bar(value: float, segments: int = 12) -> str:
    value = _clamp(value)
    filled = round(value / 100 * segments)
    return "█" * filled + "░" * (segments - filled)


# --------------------------------------------------------------------------
# Shared server Collection (the gacha loop)
# --------------------------------------------------------------------------
# A collection dict is stored once per server and shared by everyone:
#     {
#         "discovered": ["blob:0", "frost:3", ...],  # "species:color_index"
#         "stars": 0,            # shared star pool
#         "wishes_made": 0,
#     }
# Everyone's /feed and /pet pour stars into the same pool, and any member can
# spend it with /wish. Discoveries belong to the whole server.

def new_collection() -> dict:
    return {"discovered": [], "stars": 0, "wishes_made": 0,
            "owned_items": [], "equipped": None}


def combo_key(species: str, color_index: int) -> str:
    return f"{species}:{color_index}"


def grant_stars(collection: dict, amount: int) -> int:
    collection["stars"] = collection.get("stars", 0) + amount
    return collection["stars"]


def is_discovered(collection: dict, species: str, color_index: int) -> bool:
    return combo_key(species, color_index) in collection.get("discovered", [])


def discover(collection: dict, species: str, color_index: int) -> bool:
    """Record a combo. Returns True if it was NEW, False if already known."""
    key = combo_key(species, color_index)
    found = collection.setdefault("discovered", [])
    if key in found:
        return False
    found.append(key)
    return True


def can_wish(collection: dict) -> bool:
    return collection.get("stars", 0) >= config.WISH_COST


def wish(collection: dict) -> dict:
    """Spend stars on one pull. Always returns a result dict:
        {"result": "broke"}                              -> not enough stars
        {"result": "new",  "species","color","color_index","found","total"}
        {"result": "dupe", "species","color","color_index","refund"}
    """
    if not can_wish(collection):
        return {"result": "broke", "need": config.WISH_COST,
                "have": collection.get("stars", 0)}

    collection["stars"] -= config.WISH_COST
    collection["wishes_made"] = collection.get("wishes_made", 0) + 1

    species = config.random_species(weighted=True)
    color_index = config.random_color_index(species)
    color_name, _ = config.color_for(species, color_index)

    if discover(collection, species, color_index):
        return {
            "result": "new", "species": species, "color": color_name,
            "color_index": color_index,
            "found": len(collection["discovered"]),
            "total": config.total_combos(),
        }
    collection["stars"] += config.DUPE_REFUND
    return {
        "result": "dupe", "species": species, "color": color_name,
        "color_index": color_index, "refund": config.DUPE_REFUND,
    }


def collection_progress(collection: dict):
    """Return (found, total, per_species) for display.
    per_species is a list of (species, found_in_species, total_in_species)."""
    found_keys = set(collection.get("discovered", []))
    per = []
    for name, spec in config.SPECIES.items():
        n = len(spec["colors"])
        got = sum(1 for ci in range(n) if combo_key(name, ci) in found_keys)
        per.append((name, got, n))
    return len(found_keys), config.total_combos(), per


# --------------------------------------------------------------------------
# Coins (per-user) + the cosmetic shop (shared wardrobe, deterministic)
# --------------------------------------------------------------------------
# Coins live on a USER# record (personal, earned via /checkin + /forage + level
# ups). Owned cosmetics + the single equipped item live on the shared COLLECTION
# record, so the whole server dresses the one pet. Buying spends the buyer's
# Coins; the item then belongs to the server. No randomness anywhere -- you buy
# the exact item you want.

def coins_of(user: dict) -> int:
    return user.get("coins", 0)


def grant_coins(user: dict, amount: int) -> int:
    user["coins"] = coins_of(user) + amount
    return user["coins"]


def daily_coins(streak: int) -> int:
    """Coins for a check-in on the given (1-based) streak day; loops weekly."""
    cal = config.COIN_CALENDAR
    return cal[(max(1, streak) - 1) % len(cal)]


def forage(user: dict, t: float | None = None):
    """Free coin trickle on a cooldown. Returns (ok, reward, wait_seconds)."""
    if t is None:
        t = now()
    remaining = config.FORAGE_COOLDOWN - (t - user.get("last_forage_ts", 0))
    if remaining > 0:
        return False, 0, int(remaining)
    user["last_forage_ts"] = t
    grant_coins(user, config.FORAGE_REWARD)
    return True, config.FORAGE_REWARD, 0


def owns_item(collection: dict, item_id: str) -> bool:
    return item_id in collection.get("owned_items", [])


def buy_item(user: dict, collection: dict, item_id: str) -> dict:
    """Spend the buyer's Coins to add a cosmetic to the shared wardrobe."""
    if item_id not in config.ITEMS:
        return {"result": "unknown"}
    if owns_item(collection, item_id):
        return {"result": "owned", "item": item_id}
    price = config.item_price(item_id)
    if coins_of(user) < price:
        return {"result": "broke", "need": price, "have": coins_of(user)}
    user["coins"] = coins_of(user) - price
    collection.setdefault("owned_items", []).append(item_id)
    return {"result": "bought", "item": item_id, "price": price}


def equip_item(collection: dict, item_id: str) -> dict:
    if item_id not in config.ITEMS:
        return {"result": "unknown"}
    if not owns_item(collection, item_id):
        return {"result": "unowned", "item": item_id}
    collection["equipped"] = item_id
    return {"result": "equipped", "item": item_id}


def unequip(collection: dict) -> dict:
    had = collection.get("equipped")
    collection["equipped"] = None
    return {"result": "unequipped", "item": had}


def shop_listing(collection: dict):
    """Rows for /shop: (item_id, name, emoji, rarity, price, owned)."""
    rows = []
    for item_id, spec in config.ITEMS.items():
        rows.append((item_id, spec["name"], spec.get("emoji", "•"),
                     spec["rarity"], config.item_price(item_id),
                     owns_item(collection, item_id)))
    return rows
