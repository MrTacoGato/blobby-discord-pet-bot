# Privacy Policy — Blobby

**Effective date:** June 7, 2026
**Last updated:** June 7, 2026

This Privacy Policy explains what the Blobby Discord application ("Blobby," "the bot," "we," "us") collects, why, and what choices you have. Blobby is a shared "server pet" bot. By adding Blobby to a server or interacting with it, you agree to this policy.

> Plain-language summary: Blobby stores only the minimum needed to run a shared pet — Discord IDs, game counters, streak dates, and timestamps. It reads messages to award passive XP **but does not store the text of your messages**. We don't sell your data and we don't show ads.

---

## 1. What we collect

Blobby stores the following, keyed by Discord **server (guild) ID** and **user ID**:

- **Identifiers:** your Discord user ID and the server's guild ID. We do **not** store usernames, email addresses, real names, or IP addresses.
- **Game state (per server):** the pet's stats, level, species, color, generation, the shared star pool, the shared collection, owned and equipped cosmetics, and coin balances.
- **Per-member activity:** your check-in streak and dates, accumulated XP contribution, coin balance, and the timestamps of your last passive-XP grant and last forage.
- **Purchase results (if you buy anything):** the cosmetic outcome of a purchase — e.g. a memorial entry, a supporter ("Caretaker") badge, or a gifted unlock — recorded so the perk persists. We store **who** unlocked a perk (your Discord ID) and **what** was unlocked. See §4.

## 2. Message content — read, not stored

Blobby uses Discord's **Message Content** intent so that ordinary chatting passively earns the pet XP. When you send a message in a server where Blobby is active, the bot checks timing to apply a rate-limited XP grant. **The text of your messages is never stored, logged, or transmitted anywhere.** Only a timestamp (when XP was last granted to you) and counters are saved.

## 3. Why we collect it

Solely to operate the game: to keep one shared pet alive across everyone's care, track the shared collection and economy, maintain streaks, and remember cosmetic unlocks. We do **not** use your data for advertising, profiling, or sale to third parties.

## 4. Purchases and payment data

Optional purchases (such as a Caretaker subscription, a Memorial keepsake, or gifting an unlock to your server) are made through **Discord's** in-app purchase system. **Payment is processed entirely by Discord and its payment processors — Blobby never sees or stores your card number, billing address, or other payment details.** Discord notifies the bot that an entitlement exists; we store only the resulting cosmetic record (the perk and the Discord ID it belongs to). Discord's handling of payment data is governed by [Discord's Privacy Policy](https://discord.com/privacy).

## 5. Where data is stored

Game data is stored in **Amazon Web Services (AWS) DynamoDB**. Access is restricted to the bot's operator. Data is transmitted over encrypted connections.

## 6. Data sharing

We do not sell, rent, or trade your data. We do not share it with third parties except:

- **Service providers** strictly necessary to run the bot (AWS for storage; Discord as the platform).
- **Legal requirements**, if compelled by valid legal process.

## 7. Retention and deletion

Game data persists while Blobby is in your server so the pet and collection survive restarts. You can have data removed:

- **Remove the bot** from a server to stop further collection for that server.
- **Request deletion** of a server's data, or your personal per-member record, by contacting us (see §10). We will delete it within a reasonable period.

Note: purchase/entitlement records held by **Discord** are subject to Discord's own retention policy, not ours.

## 8. Children's privacy

Blobby is not directed to children under 13 (or the minimum digital-consent age in your country). Use of Discord is subject to Discord's minimum-age requirements. We do not knowingly collect data from anyone below that age; if you believe we have, contact us and we will delete it.

## 9. Changes to this policy

We may update this policy as the bot evolves. Material changes will be reflected by updating the "Last updated" date above. Continued use after changes constitutes acceptance.

## 10. Contact

Questions or data-deletion requests: **blobbysupport@gmail.com**
Project repository: https://github.com/MrTacoGato/blobby-discord-pet-bot

---

*Blobby is an independent project and is not affiliated with or endorsed by Discord Inc.*
