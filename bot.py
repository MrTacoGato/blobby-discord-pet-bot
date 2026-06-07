"""
The Discord-facing layer: slash commands, the passive-XP message listener,
the shared server Collection (the gacha loop), and the gentle death/respawn
cycle. Run with:  python bot.py

Actions are FEED, PET, and WISH. Feeding and petting earn STARS into a single
pool shared by the whole server; WISH spends stars to pull a random
species+color into the shared Collection. There is no manual "die" button --
Blobby only passes after ~15 days of total neglect (config.DEATH_GRACE_HOURS),
after which a fresh random pet hatches and the collection carries over.

Sprites: each species+color is a pre-baked animated glow GIF in sprites/ (run
sprites.py to generate). The bot just attaches the right file to status / wish /
death embeds; Pillow + numpy are dev-only, never imported at runtime.
"""

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import config
import pet as petlib
import sprites
import storage


intents = discord.Intents.default()
intents.message_content = True  # privileged: enable it in the Dev Portal too
bot = commands.Bot(command_prefix="!", intents=intents)  # prefix unused


# --------------------------------------------------------------------------
# Storage glue (runs sync boto3 off the event loop)
# --------------------------------------------------------------------------
async def _load_pet(gid):
    return await asyncio.to_thread(storage.load_pet, gid)


async def _save_pet(gid, pet):
    await asyncio.to_thread(storage.save_pet, gid, pet)


async def _load_user(gid, uid):
    return await asyncio.to_thread(storage.load_user, gid, uid)


async def _save_user(gid, uid, user):
    await asyncio.to_thread(storage.save_user, gid, uid, user)


async def _load_collection(gid):
    return await asyncio.to_thread(storage.load_collection, gid)


async def _save_collection(gid, collection):
    await asyncio.to_thread(storage.save_collection, gid, collection)


async def refresh_collection(gid):
    """Load the shared collection, creating an empty one on first use."""
    coll = await _load_collection(gid)
    if coll is None:
        coll = petlib.new_collection()
        await _save_collection(gid, coll)
    return coll


async def _seed_collection(gid, pet):
    """Make sure the live pet's own combo counts as discovered."""
    coll = await refresh_collection(gid)
    if petlib.discover(coll, pet["species"], pet["color_index"]):
        await _save_collection(gid, coll)


async def refresh_pet(gid):
    """Load the pet, settle its stats, and persist.

    Returns (pet, death_event). If the pet died since we last looked, a fresh
    random generation is spawned/saved and death_event = (dead_pet, new_pet).
    The newborn's combo is seeded into the shared collection.
    """
    pet = await _load_pet(gid)
    if pet is None:
        pet = petlib.new_pet(name=None)
        await _save_pet(gid, pet)
        await _seed_collection(gid, pet)
        return pet, None

    was_alive = pet.get("alive", True)
    petlib.settle(pet)

    if was_alive and not pet["alive"]:
        dead = dict(pet)
        new = petlib.respawn(dead)
        await _save_pet(gid, new)
        await _seed_collection(gid, new)
        return new, (dead, new)

    await _save_pet(gid, pet)
    return pet, None


# --------------------------------------------------------------------------
# Sprite attachments
# --------------------------------------------------------------------------
def sprite_file(species, color_index, as_name="sprite.gif", item_id=None):
    """A discord.File for a combo's glow GIF -- dressed if a cosmetic is equipped,
    otherwise the plain glow. None if the art isn't built yet."""
    candidates = []
    if item_id:
        candidates.append(sprites.dressed_path(species, color_index, item_id))
    candidates.append(sprites.anim_path(species, color_index))
    for path in candidates:
        try:
            return discord.File(path, filename=as_name)
        except (FileNotFoundError, OSError):
            continue
    return None


async def _ensure_look(pet, collection):
    """If the pet has an equipped cosmetic, make sure its dressed GIF is cached
    (composited off the event loop so it never blocks)."""
    item_id = collection.get("equipped") if collection else None
    if item_id and item_id in config.ITEMS:
        await asyncio.to_thread(sprites.ensure_dressed,
                                pet["species"], pet["color_index"], item_id)


# --------------------------------------------------------------------------
# Embeds  (each returns (embed, file) so the caller can attach the sprite)
# --------------------------------------------------------------------------
def pet_embed(pet, collection=None):
    _, color = petlib.color_of(pet)
    e = discord.Embed(title=f"🐾 {petlib.display_name(pet)}", color=discord.Color(color))
    e.add_field(
        name=f"Level {pet['level']}",
        value=f"`{petlib.bar(pet['xp'] / config.xp_to_next(pet['level']) * 100)}`  "
        f"{int(pet['xp'])}/{config.xp_to_next(pet['level'])} xp",
        inline=False,
    )
    e.add_field(name="🍎 hunger", value=f"`{petlib.bar(pet['hunger'])}` {round(pet['hunger'])}", inline=False)
    e.add_field(name="😊 happiness", value=f"`{petlib.bar(pet['happiness'])}` {round(pet['happiness'])}", inline=False)

    warn = petlib.hours_until_death(pet)
    if warn is not None:
        days = warn / 24.0
        when = f"~{round(days)}d" if days >= 1 else f"~{round(warn)}h"
        e.add_field(name="⚠️ neglected", value=f"will pass in {when} without care", inline=False)

    if collection is not None:
        found, total, _ = petlib.collection_progress(collection)
        e.add_field(name="✨ server stars", value=f"{collection.get('stars', 0)} ⭐", inline=True)
        e.add_field(name="📖 collection", value=f"{found}/{total} found", inline=True)

    color_name, _ = petlib.color_of(pet)
    equipped = collection.get("equipped") if collection else None
    f = sprite_file(pet["species"], pet["color_index"], item_id=equipped)
    if f is not None:
        e.set_thumbnail(url="attachment://sprite.gif")
    e.set_footer(text=f"generation {pet['generation']} · {pet['species']} · {color_name}")
    return e, f


def wish_embed(result):
    if result["result"] == "broke":
        e = discord.Embed(
            title="🎁 not enough stars",
            description=(
                f"A wish costs **{result['need']} ⭐** but the server only has "
                f"**{result['have']} ⭐**.\nFeed and pet Blobby to earn more!"
            ),
            color=discord.Color(config.EMBED_NEUTRAL),
        )
        return e, None

    _, color = config.color_for(result["species"], result["color_index"])
    label = f"{result['color']} {result['species']}"
    if result["result"] == "new":
        e = discord.Embed(
            title=f"🎉 NEW! a {label}",
            description=(
                f"The wish revealed a **{label}** — added to the server collection!\n"
                f"**{result['found']}/{result['total']}** collected."
            ),
            color=discord.Color(color),
        )
    else:  # dupe
        e = discord.Embed(
            title=f"✨ duplicate {label}",
            description=(
                f"You already have a **{label}**. Refunded **{result['refund']} ⭐** "
                f"back to the server pool."
            ),
            color=discord.Color(color),
        )
    f = sprite_file(result["species"], result["color_index"], as_name="wish.gif")
    if f is not None:
        e.set_image(url="attachment://wish.gif")
    return e, f


def death_embed(dead, new):
    e = discord.Embed(
        title="🪦 a chapter ends...",
        description=(
            f"**{petlib.display_name(dead)}** (gen {dead['generation']}, lvl {dead['level']}) "
            f"passed away after ~15 days with no care at all.\n\n"
            f"A new **{new['species']}** has hatched, glowing a fresh "
            f"**{petlib.color_of(new)[0]}**. Give it a name with `/rename`.\n"
            f"*(Your collection is safe — it carries over.)*"
        ),
        color=discord.Color(config.DEAD_COLOR),
    )
    f = sprite_file(new["species"], new["color_index"])
    if f is not None:
        e.set_thumbnail(url="attachment://sprite.gif")
    e.set_footer(text=f"now on generation {new['generation']}")
    return e, f


def collection_embed(collection):
    found, total, per = petlib.collection_progress(collection)
    e = discord.Embed(
        title="📖 Server Collection",
        description=f"`{petlib.bar(found / total * 100)}`  **{found}/{total}** collected",
        color=discord.Color(config.EMBED_NEUTRAL),
    )
    for name, got, n in per:
        sset = config.SPECIES[name]["set"]
        rarity = config.SPECIES[name].get("rarity", 1)
        tag = "★ rare" if rarity <= 2 else ("· uncommon" if rarity <= 3 else "")
        e.add_field(
            name=f"{name}  ({sset}) {tag}".strip(),
            value=f"`{petlib.bar(got / n * 100, segments=n)}` {got}/{n}",
            inline=False,
        )
    e.set_footer(text=f"{collection.get('stars', 0)} ⭐ in the pool · {collection.get('wishes_made', 0)} wishes made")
    return e


# --------------------------------------------------------------------------
# Slash commands
# --------------------------------------------------------------------------
async def _respond_with_action(interaction, action_fn, verb, stars=0):
    await interaction.response.defer()
    gid = interaction.guild_id
    pet, death = await refresh_pet(gid)
    if death:
        e, f = death_embed(*death)
        await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)
        return

    collection = await refresh_collection(gid)
    ok, msg, levels = action_fn(pet)
    await _save_pet(gid, pet)

    if ok and stars:
        petlib.grant_stars(collection, stars)
        await _save_collection(gid, collection)

    await _ensure_look(pet, collection)
    e, f = pet_embed(pet, collection)
    if ok:
        e.description = f"**{interaction.user.display_name}** {verb}. {petlib.display_name(pet)} {msg}"
        if stars:
            e.description += f"  (+{stars} ⭐)"
        if levels:
            e.description += f"\n🎉 leveled up to **{pet['level']}**!"
    else:
        e.description = f"{petlib.display_name(pet)} {msg}"
    await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)


@bot.tree.command(name="status", description="Check on the server pet")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = interaction.guild_id
    pet, death = await refresh_pet(gid)
    if death:
        e, f = death_embed(*death)
        await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)
        return
    collection = await refresh_collection(gid)
    await _ensure_look(pet, collection)
    e, f = pet_embed(pet, collection)
    await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)


@bot.tree.command(name="feed", description="Feed the server pet (earns ⭐)")
async def feed(interaction: discord.Interaction):
    await _respond_with_action(interaction, petlib.feed, "feeds the pet", stars=config.STAR_FEED)


@bot.tree.command(name="pet", description="Pet the server pet (earns ⭐)")
async def pet_cmd(interaction: discord.Interaction):
    await _respond_with_action(interaction, petlib.pet_action, "pets the pet", stars=config.STAR_PET)


@bot.tree.command(name="wish", description="Spend the server's ⭐ on a collection pull")
async def wish(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = interaction.guild_id
    collection = await refresh_collection(gid)
    result = petlib.wish(collection)
    await _save_collection(gid, collection)
    e, f = wish_embed(result)
    await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)


@bot.tree.command(name="collection", description="See the server's shared Blob collection")
async def collection_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    collection = await refresh_collection(interaction.guild_id)
    await interaction.followup.send(embed=collection_embed(collection))


@bot.tree.command(name="rename", description="Rename the server pet")
@app_commands.describe(name="The pet's new name (max 32 characters)")
async def rename(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    name = name.strip()[:32]
    if not name:
        await interaction.followup.send("That name is empty — try again.")
        return
    gid = interaction.guild_id
    pet, death = await refresh_pet(gid)
    if death:
        pet["name"] = name  # name the newborn
        await _save_pet(gid, pet)
        e, f = death_embed(*death)
        await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)
        return
    collection = await refresh_collection(gid)
    old = petlib.display_name(pet)
    pet["name"] = name
    await _save_pet(gid, pet)
    await _ensure_look(pet, collection)
    e, f = pet_embed(pet, collection)
    e.description = f"{old} is now known as **{name}**."
    await interaction.followup.send(embed=e, file=f) if f else await interaction.followup.send(embed=e)


@bot.tree.command(name="checkin", description="Daily check-in -- build a streak and earn 🪙")
async def checkin(interaction: discord.Interaction):
    await interaction.response.defer()
    gid, uid = interaction.guild_id, interaction.user.id
    user = await _load_user(gid, uid) or storage.new_user()
    today = datetime.now(timezone.utc).date().isoformat()
    statuskey, streak = petlib.check_in(user, today)
    earned = 0
    if statuskey != "already":
        earned = petlib.daily_coins(streak)
        petlib.grant_coins(user, earned)
    await _save_user(gid, uid, user)

    bonus = f"  (+{earned} 🪙)" if earned else ""
    blurbs = {
        "first": f"first check-in! streak: **{streak}** 🔥{bonus}",
        "extended": f"nice — streak is now **{streak}** 🔥{bonus}",
        "already": f"already checked in today. streak: **{streak}** 🔥",
        "reset": f"welcome back! streak restarted at **{streak}**{bonus}",
    }
    await interaction.followup.send(
        f"{blurbs[statuskey]}  ·  balance: **{petlib.coins_of(user)}** 🪙")


# --------------------------------------------------------------------------
# Coins economy + the cosmetic shop  (Phase 1: direct purchase, no art layer)
# --------------------------------------------------------------------------
def shop_embed(collection, user):
    e = discord.Embed(
        title="🛍️ Cosmetic Shop",
        description=(f"Your balance: **{petlib.coins_of(user)}** 🪙\n"
                     "Buy with `/buy` — you get the exact item, no surprises."),
        color=discord.Color(config.EMBED_NEUTRAL),
    )
    by_rarity = {}
    for item_id, name, emoji, rarity, price, owned in petlib.shop_listing(collection):
        by_rarity.setdefault(rarity, []).append(
            f"{emoji} **{name}** — {price} 🪙" + ("  ✅" if owned else ""))
    for rarity in ("common", "uncommon", "rare", "legendary"):
        if rarity in by_rarity:
            e.add_field(name=rarity.capitalize(), value="\n".join(by_rarity[rarity]), inline=False)
    e.set_footer(text="Earn 🪙 with /checkin and /forage")
    return e


async def _item_autocomplete(interaction: discord.Interaction, current: str):
    cur = current.lower()
    out = []
    for item_id, spec in config.ITEMS.items():
        if cur in item_id or cur in spec["name"].lower():
            out.append(app_commands.Choice(
                name=f"{spec['name']} ({config.item_price(item_id)} coins)", value=item_id))
    return out[:25]


@bot.tree.command(name="forage", description="Forage for 🪙 (once every 10 min)")
async def forage_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    gid, uid = interaction.guild_id, interaction.user.id
    user = await _load_user(gid, uid) or storage.new_user()
    ok, reward, wait = petlib.forage(user)
    if ok:
        await _save_user(gid, uid, user)
        await interaction.followup.send(
            f"🍃 you foraged **+{reward} 🪙**!  ·  balance: **{petlib.coins_of(user)}** 🪙")
    else:
        mins = wait // 60 + 1
        await interaction.followup.send(
            f"🍃 nothing to forage yet — check back in ~{mins} min.  ·  "
            f"balance: **{petlib.coins_of(user)}** 🪙")


@bot.tree.command(name="shop", description="Browse cosmetics to buy with 🪙")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()
    gid, uid = interaction.guild_id, interaction.user.id
    collection = await refresh_collection(gid)
    user = await _load_user(gid, uid) or storage.new_user()
    await interaction.followup.send(embed=shop_embed(collection, user))


@bot.tree.command(name="buy", description="Buy a cosmetic with 🪙")
@app_commands.describe(item="Which item to buy")
@app_commands.autocomplete(item=_item_autocomplete)
async def buy(interaction: discord.Interaction, item: str):
    await interaction.response.defer()
    gid, uid = interaction.guild_id, interaction.user.id
    collection = await refresh_collection(gid)
    user = await _load_user(gid, uid) or storage.new_user()
    result = petlib.buy_item(user, collection, item)
    if result["result"] == "bought":
        await _save_user(gid, uid, user)
        await _save_collection(gid, collection)
        spec = config.ITEMS[item]
        await interaction.followup.send(
            f"{spec['emoji']} bought **{spec['name']}** for {result['price']} 🪙! "
            f"Equip it with `/equip`.  ·  balance: **{petlib.coins_of(user)}** 🪙")
    elif result["result"] == "owned":
        await interaction.followup.send("the server already owns that one — `/equip` it any time.")
    elif result["result"] == "broke":
        await interaction.followup.send(
            f"not enough 🪙 — that's **{result['need']}**, you have **{result['have']}**. "
            f"Earn more with `/checkin` and `/forage`.")
    else:
        await interaction.followup.send("hmm, I don't know that item — check `/shop`.")


@bot.tree.command(name="inventory", description="See owned cosmetics and your 🪙")
async def inventory(interaction: discord.Interaction):
    await interaction.response.defer()
    gid, uid = interaction.guild_id, interaction.user.id
    collection = await refresh_collection(gid)
    user = await _load_user(gid, uid) or storage.new_user()
    owned = collection.get("owned_items", [])
    equipped = collection.get("equipped")
    e = discord.Embed(
        title="🎒 Server Wardrobe",
        description=f"Your balance: **{petlib.coins_of(user)}** 🪙",
        color=discord.Color(config.EMBED_NEUTRAL),
    )
    if owned:
        lines = []
        for item_id in owned:
            spec = config.ITEMS.get(item_id, {"name": item_id, "emoji": "•"})
            tag = "  ⬅️ equipped" if item_id == equipped else ""
            lines.append(f"{spec.get('emoji', '•')} **{spec['name']}**{tag}")
        e.add_field(name=f"Owned ({len(owned)}/{len(config.ITEMS)})",
                    value="\n".join(lines), inline=False)
    else:
        e.add_field(name="Owned", value="nothing yet — visit `/shop`!", inline=False)
    wearing = config.ITEMS.get(equipped, {}).get("name", "nothing") if equipped else "nothing"
    e.set_footer(text=f"Blobby is wearing: {wearing}")
    await interaction.followup.send(embed=e)


@bot.tree.command(name="equip", description="Dress Blobby in an owned cosmetic")
@app_commands.describe(item="Which owned item to equip")
@app_commands.autocomplete(item=_item_autocomplete)
async def equip(interaction: discord.Interaction, item: str):
    await interaction.response.defer()
    gid = interaction.guild_id
    collection = await refresh_collection(gid)
    result = petlib.equip_item(collection, item)
    if result["result"] == "equipped":
        await _save_collection(gid, collection)
        pet, _ = await refresh_pet(gid)
        await asyncio.to_thread(sprites.ensure_dressed, pet["species"], pet["color_index"], item)
        spec = config.ITEMS[item]
        await interaction.followup.send(
            f"{spec['emoji']} Blobby is now wearing the **{spec['name']}**! See `/status`.")
    elif result["result"] == "unowned":
        await interaction.followup.send("the server doesn't own that yet — `/buy` it first.")
    else:
        await interaction.followup.send("hmm, I don't know that item — check `/shop`.")


@bot.tree.command(name="unequip", description="Take off Blobby's cosmetic")
async def unequip_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = interaction.guild_id
    collection = await refresh_collection(gid)
    petlib.unequip(collection)
    await _save_collection(gid, collection)
    await interaction.followup.send("Blobby is fresh-faced again. 🫧")


# --------------------------------------------------------------------------
# Passive XP from chatting (rate-limited so it can't be farmed)
# --------------------------------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return
    await bot.process_commands(message)

    gid, uid = message.guild.id, message.author.id
    user = await _load_user(gid, uid) or storage.new_user()
    if petlib.now() - user.get("last_xp_ts", 0) < config.PASSIVE_XP_COOLDOWN:
        return

    pet = await _load_pet(gid)
    if not pet or not pet.get("alive", True):
        return

    levels = petlib.add_xp(pet, config.XP_PASSIVE)
    user["xp_contributed"] = user.get("xp_contributed", 0) + config.XP_PASSIVE
    user["last_xp_ts"] = petlib.now()
    coins = levels * config.COIN_PER_LEVEL if levels else 0
    if coins:
        petlib.grant_coins(user, coins)
    await _save_pet(gid, pet)
    await _save_user(gid, uid, user)

    if levels:
        try:
            await message.channel.send(
                f"✨ all your chatting leveled **{petlib.display_name(pet)}** up to "
                f"**{pet['level']}** — you earned **+{coins} 🪙**!"
            )
        except discord.HTTPException:
            pass


# --------------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------------
@bot.event
async def setup_hook():
    await asyncio.to_thread(storage.ensure_table)
    if config.DEV_GUILD_ID:
        guild = discord.Object(id=int(config.DEV_GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} — pet bot ready.")


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "No Discord token. Set DISCORD_TOKEN (local) or DISCORD_TOKEN_PARAM (SSM)."
        )
    bot.run(config.DISCORD_TOKEN)
