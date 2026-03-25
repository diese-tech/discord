"""
Civ 6 BBG Draft Bot
====================
A Discord bot for running Civilization 6 leader drafts in competitive multiplayer.

SETUP INSTRUCTIONS:
1. Install dependencies:
       pip install discord.py

2. Create a Discord bot at https://discord.com/developers/applications
   - Enable "Message Content Intent" under Bot > Privileged Gateway Intents
   - Copy your bot token

3. Set your bot token as an environment variable named DISCORD_TOKEN
   (On Railway: add it under your project's Variables tab)
   (Locally: set it in your terminal before running, e.g. export DISCORD_TOKEN=yourtoken)

4. Invite the bot to your server with these permissions:
   - Send Messages
   - Read Message History
   - Add Reactions

5. Run:
       python civ6_draft_bot.py

COMMANDS:
  .draft <number_of_players>   — Start a new draft lobby
  .join                        — Join the current lobby
  .vote                        — Vote for secret draft (majority wins)
  .ban <Leader Name>           — Nominate a leader for a ban vote
  .startdraft                  — Host only: begin the draft once all players joined
  .canceldraft                 — Host only: cancel the current draft
  .leaders                     — List all leaders in the pool
  .help                        — Show all commands
"""

import discord
import random
import os
from collections import defaultdict

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("DISCORD_TOKEN", "")
PREFIX = "."


# ─────────────────────────────────────────────
# FULL LEADER POOL
# Base game + Rise & Fall + Gathering Storm +
# New Frontier Pass + BBG Expanded mod leaders
# Source: https://civ6bbg.github.io/en_US/leaders_7.2.html
# ─────────────────────────────────────────────
ALL_LEADERS = [
    # ── AMERICA ──
    ("Abraham Lincoln",                   "America"),
    ("Teddy Roosevelt (Bull Moose)",       "America"),
    ("Teddy Roosevelt (Rough Rider)",      "America"),
    # ── ARABIA ──
    ("Saladin (Vizier)",                   "Arabia"),
    ("Saladin (Sultan)",                   "Arabia"),
    # ── AUSTRALIA ──
    ("John Curtin",                        "Australia"),
    # ── AZTEC ──
    ("Montezuma",                          "Aztec"),
    # ── BABYLON ──
    ("Hammurabi",                          "Babylon"),
    # ── BRAZIL ──
    ("Pedro II",                           "Brazil"),
    # ── BYZANTIUM ──
    ("Basil II",                           "Byzantium"),
    ("Theodora",                           "Byzantium"),
    # ── CANADA ──
    ("Wilfrid Laurier",                    "Canada"),
    # ── CHINA ──
    ("Kublai Khan (China)",                "China"),
    ("Qin Shi Huang (Mandate of Heaven)",  "China"),
    ("Qin Shi Huang (Unifier)",            "China"),
    ("Wu Zetian",                          "China"),
    ("Yongle",                             "China"),
    # ── CREE ──
    ("Poundmaker",                         "Cree"),
    # ── EGYPT ──
    ("Cleopatra (Egyptian)",               "Egypt"),
    ("Cleopatra (Ptolemaic)",              "Egypt"),
    ("Ramses II",                          "Egypt"),
    # ── ENGLAND ──
    ("Eleanor of Aquitaine (England)",     "England"),
    ("Elizabeth I",                        "England"),
    ("Victoria (Age of Empire)",           "England"),
    ("Victoria (Age of Steam)",            "England"),
    # ── ETHIOPIA ──
    ("Menelik II",                         "Ethiopia"),
    # ── FRANCE ──
    ("Catherine de Medici (Black Queen)",  "France"),
    ("Catherine de Medici (Magnificence)", "France"),
    ("Eleanor of Aquitaine (France)",      "France"),
    # ── GAUL ──
    ("Ambiorix",                           "Gaul"),
    ("Vercingetorix",                      "Gaul"),        # BBG Expanded
    # ── GEORGIA ──
    ("Tamar",                              "Georgia"),
    # ── GERMANY ──
    ("Frederick Barbarossa",               "Germany"),
    ("Ludwig II",                          "Germany"),
    # ── GRAN COLOMBIA ──
    ("Simón Bolívar",                      "Gran Colombia"),
    # ── GREECE ──
    ("Gorgo",                              "Greece"),
    ("Pericles",                           "Greece"),
    # ── HUNGARY ──
    ("Matthias Corvinus",                  "Hungary"),
    # ── INCA ──
    ("Pachacuti",                          "Inca"),
    # ── INDIA ──
    ("Chandragupta",                       "India"),
    ("Gandhi",                             "India"),
    # ── INDONESIA ──
    ("Gitarja",                            "Indonesia"),
    # ── JAPAN ──
    ("Hojo Tokimune",                      "Japan"),
    ("Tokugawa",                           "Japan"),
    # ── KHMER ──
    ("Jayavarman VII",                     "Khmer"),
    # ── KONGO ──
    ("Mvemba a Nzinga",                    "Kongo"),
    ("Nzinga Mbande",                      "Kongo"),
    # ── KOREA ──
    ("Sejong",                             "Korea"),
    ("Seondeok",                           "Korea"),
    # ── MACEDON ──
    ("Alexander",                          "Macedon"),
    ("Olympias",                           "Macedon"),     # BBG Expanded
    # ── MALI ──
    ("Mansa Musa",                         "Mali"),
    ("Sundiata Keita",                     "Mali"),
    # ── MĀORI ──
    ("Kupe",                               "Māori"),
    # ── MAPUCHE ──
    ("Lautaro",                            "Mapuche"),
    # ── MAYA ──
    ("Lady Six Sky",                       "Maya"),
    ("Te' K'inich II",                     "Maya"),        # BBG Expanded
    # ── MONGOLIA ──
    ("Genghis Khan",                       "Mongolia"),
    ("Kublai Khan (Mongolia)",             "Mongolia"),
    # ── NETHERLANDS ──
    ("Wilhelmina",                         "Netherlands"),
    # ── NORWAY ──
    ("Harald Hardrada (Varangian)",        "Norway"),
    ("Harald Hardrada (Konge)",            "Norway"),
    # ── NUBIA ──
    ("Amanitore",                          "Nubia"),
    # ── OTTOMANS ──
    ("Suleiman (Kanuni)",                  "Ottomans"),
    ("Suleiman (Muhteşem)",                "Ottomans"),
    # ── PERSIA ──
    ("Cyrus",                              "Persia"),
    ("Nader Shah",                         "Persia"),
    # ── PHOENICIA ──
    ("Dido",                               "Phoenicia"),
    ("Ahiram",                             "Phoenicia"),   # BBG Expanded
    # ── POLAND ──
    ("Jadwiga",                            "Poland"),
    # ── PORTUGAL ──
    ("João III",                           "Portugal"),
    # ── ROME ──
    ("Julius Caesar",                      "Rome"),
    ("Trajan",                             "Rome"),
    # ── RUSSIA ──
    ("Peter",                              "Russia"),
    # ── SCOTLAND ──
    ("Robert the Bruce",                   "Scotland"),
    # ── SCYTHIA ──
    ("Tomyris",                            "Scythia"),
    # ── SPAIN ──
    ("Philip II",                          "Spain"),
    # ── SUMERIA ──
    ("Gilgamesh",                          "Sumeria"),
    # ── SWAHILI ──
    ("Al-Hasan ibn Sulaiman",              "Swahili"),     # BBG Expanded
    # ── SWEDEN ──
    ("Kristina",                           "Sweden"),
    # ── TEOTIHUACÁN ──
    ("Spearthrower Owl",                   "Teotihuacán"), # BBG Expanded
    # ── THULE ──
    ("Kiviuq",                             "Thule"),       # BBG Expanded
    # ── TIBET ──
    ("Trisong Detsen",                     "Tibet"),       # BBG Expanded
    # ── VIETNAM ──
    ("Bà Triệu",                           "Vietnam"),
    # ── ZULU ──
    ("Shaka",                              "Zulu"),
]

# ─────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)

# ─────────────────────────────────────────────
# DRAFT STATE  (one active draft per channel)
# ─────────────────────────────────────────────
drafts = {}   # channel_id -> DraftSession

class DraftSession:
    def __init__(self, host_id, host_name, player_count, channel_id):
        self.host_id       = host_id
        self.host_name     = host_name
        self.player_count  = player_count
        self.channel_id    = channel_id

        self.players       = [host_id]
        self.player_names  = {host_id: host_name}

        self.banned_leaders    = set()
        self.ban_nominations   = {}
        self.secret_votes      = set()
        self.is_secret         = False
        self.assignments       = {}
        self.started           = False

    def is_host(self, user_id):
        return user_id == self.host_id

    def add_player(self, user_id, user_name):
        if user_id not in self.players:
            self.players.append(user_id)
            self.player_names[user_id] = user_name
            return True
        return False

    def is_full(self):
        return len(self.players) >= self.player_count

    def available_pool(self):
        return [(l, c) for (l, c) in ALL_LEADERS if l not in self.banned_leaders]

    def run_draft(self):
        pool = self.available_pool()
        random.shuffle(pool)
        n = len(self.players)
        per_player = len(pool) // n
        for i, uid in enumerate(self.players):
            self.assignments[uid] = pool[i * per_player:(i + 1) * per_player]
        self.started = True
        self.is_secret = len(self.secret_votes) > (len(self.players) / 2)

    def ban_vote_result(self, leader_key):
        votes = len(self.ban_nominations.get(leader_key, set()))
        needed = max(2, (len(self.players) // 2) + 1)
        return votes >= needed

    def format_leader_key(self, name):
        name_lower = name.lower()
        for (l, c) in ALL_LEADERS:
            if l.lower() == name_lower:
                return l
        return None


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def format_assignment(leaders):
    return "\n".join(f"  • **{l}** ({c})" for l, c in leaders)


# ─────────────────────────────────────────────
# EVENT: on_ready
# ─────────────────────────────────────────────
@client.event
async def on_ready():
    if not BOT_TOKEN:
        raise ValueError(
            "No DISCORD_TOKEN found. Set it as an environment variable:\n"
            "  export DISCORD_TOKEN=your_token_here\n"
            "Or add it to your Railway project's Variables tab."
        )
    print(f"✅  Logged in as {client.user} (ID: {client.user.id})")
    print(f"    Leader pool: {len(ALL_LEADERS)} leaders")
    print("    Ready to draft!")


# ─────────────────────────────────────────────
# EVENT: on_message
# ─────────────────────────────────────────────
@client.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.content.startswith(PREFIX):
        return

    parts   = message.content[len(PREFIX):].strip().split(None, 1)
    cmd     = parts[0].lower() if parts else ""
    args    = parts[1].strip() if len(parts) > 1 else ""
    cid     = message.channel.id
    uid     = message.author.id
    uname   = message.author.display_name

    # ── .draft <n> ────────────────────────────
    if cmd == "draft":
        if cid in drafts and not drafts[cid].started:
            await message.channel.send(
                "⚠️  A draft is already open! Use `.canceldraft` to cancel it first."
            )
            return
        try:
            n = int(args)
            if n < 2 or n > 12:
                raise ValueError
        except ValueError:
            await message.channel.send("❌  Usage: `.draft <2-12>`  (e.g. `.draft 6`)")
            return

        session = DraftSession(uid, uname, n, cid)
        drafts[cid] = session
        await message.channel.send(
            f"🏛️  **Civ 6 Draft Lobby** opened by **{uname}**!\n"
            f"👥  Waiting for **{n}** players.\n\n"
            f"• `.join` — join the lobby\n"
            f"• `.vote` — vote for a secret draft\n"
            f"• `.ban <Leader Name>` — nominate a leader for a ban vote\n"
            f"• `.startdraft` — host starts the draft\n"
        )

    # ── .join ──────────────────────────────────
    elif cmd == "join":
        if cid not in drafts:
            await message.channel.send("❌  No draft lobby open. Use `.draft <n>` to start one.")
            return
        session = drafts[cid]
        if session.started:
            await message.channel.send("❌  The draft has already started.")
            return
        added = session.add_player(uid, uname)
        if not added:
            await message.channel.send(f"ℹ️  {uname} is already in the lobby.")
            return
        count = len(session.players)
        await message.channel.send(
            f"✅  **{uname}** joined! ({count}/{session.player_count} players)"
        )
        if session.is_full():
            await message.channel.send(
                f"🎉  Lobby full! **{session.host_name}**, type `.startdraft` to begin."
            )

    # ── .vote ──────────────────────────────────
    elif cmd == "vote":
        if cid not in drafts:
            await message.channel.send("❌  No draft lobby open.")
            return
        session = drafts[cid]
        if uid not in session.players:
            await message.channel.send("❌  You must join the lobby first (`.join`).")
            return
        if session.started:
            await message.channel.send("❌  Voting must happen before the draft starts.")
            return
        session.secret_votes.add(uid)
        yes = len(session.secret_votes)
        needed = (len(session.players) // 2) + 1
        await message.channel.send(
            f"🤫  **{uname}** voted for a **secret draft**. ({yes}/{needed} needed for majority)"
        )

    # ── .ban <leader> ──────────────────────────
    elif cmd == "ban":
        if cid not in drafts:
            await message.channel.send("❌  No draft lobby open.")
            return
        session = drafts[cid]
        if uid not in session.players:
            await message.channel.send("❌  You must join the lobby first (`.join`).")
            return
        if session.started:
            await message.channel.send("❌  Bans must happen before the draft starts.")
            return
        if not args:
            await message.channel.send("❌  Usage: `.ban <Leader Name>`  (e.g. `.ban Montezuma`)")
            return
        canonical = session.format_leader_key(args)
        if not canonical:
            await message.channel.send(
                f"❌  Leader **{args}** not found. Use `.leaders` to see all leaders."
            )
            return
        if canonical in session.banned_leaders:
            await message.channel.send(f"ℹ️  **{canonical}** is already banned.")
            return
        if canonical not in session.ban_nominations:
            session.ban_nominations[canonical] = set()
        session.ban_nominations[canonical].add(uid)
        votes  = len(session.ban_nominations[canonical])
        needed = max(2, (len(session.players) // 2) + 1)
        if session.ban_vote_result(canonical):
            session.banned_leaders.add(canonical)
            await message.channel.send(
                f"🚫  **{canonical}** has been **banned** from the draft! "
                f"({votes}/{needed} votes — majority reached)"
            )
        else:
            await message.channel.send(
                f"🗳️  **{uname}** nominated **{canonical}** for a ban. "
                f"({votes}/{needed} votes needed)"
            )

    # ── .startdraft ────────────────────────────
    elif cmd == "startdraft":
        if cid not in drafts:
            await message.channel.send("❌  No draft lobby open. Use `.draft <n>` first.")
            return
        session = drafts[cid]
        if not session.is_host(uid):
            await message.channel.send("❌  Only the host can start the draft.")
            return
        if session.started:
            await message.channel.send("❌  The draft has already started.")
            return
        if len(session.players) < 2:
            await message.channel.send("❌  Need at least 2 players to start.")
            return

        session.run_draft()
        ban_list = (", ".join(f"**{b}**" for b in sorted(session.banned_leaders))
                    if session.banned_leaders else "none")
        vote_summary = "🤫 Secret draft voted in!" if session.is_secret else "📢 Public draft"
        await message.channel.send(
            f"🎲  **Draft starting!**\n"
            f"{vote_summary}\n"
            f"🚫 Banned leaders: {ban_list}\n"
            f"🃏 Each player receives **{len(list(session.assignments.values())[0])}** leaders.\n"
        )

        if session.is_secret:
            failed = []
            for pid in session.players:
                pleads = session.assignments[pid]
                try:
                    user = await client.fetch_user(pid)
                    await user.send(
                        f"🏛️  **Your Civ 6 Draft Leaders** (secret draft — don't share!):\n"
                        f"{format_assignment(pleads)}"
                    )
                except discord.Forbidden:
                    failed.append(session.player_names[pid])
            await message.channel.send(
                "📬  Leaders sent to each player via DM!\n"
                + (f"⚠️  Could not DM: {', '.join(failed)} — check DM settings." if failed else "")
            )
        else:
            result_lines = []
            for pid in session.players:
                pname  = session.player_names[pid]
                pleads = session.assignments[pid]
                result_lines.append(f"**{pname}**:\n{format_assignment(pleads)}")
            await message.channel.send(
                "🏛️  **Draft Results:**\n\n" + "\n\n".join(result_lines)
            )

        del drafts[cid]

    # ── .canceldraft ───────────────────────────
    elif cmd == "canceldraft":
        if cid not in drafts:
            await message.channel.send("❌  No active draft to cancel.")
            return
        session = drafts[cid]
        if not session.is_host(uid):
            await message.channel.send("❌  Only the host can cancel the draft.")
            return
        del drafts[cid]
        await message.channel.send("🗑️  Draft has been cancelled.")

    # ── .leaders ───────────────────────────────
    elif cmd == "leaders":
        pool = ALL_LEADERS
        if cid in drafts:
            session = drafts[cid]
            pool    = session.available_pool()
            prefix  = f"📋  **Available leaders** ({len(pool)} in pool, {len(session.banned_leaders)} banned):\n"
        else:
            prefix  = f"📋  **Full leader pool** ({len(pool)} leaders):\n"

        by_civ = defaultdict(list)
        for l, c in pool:
            by_civ[c].append(l)

        lines = []
        for civ in sorted(by_civ):
            lines.append(f"**{civ}**: {', '.join(by_civ[civ])}")

        chunk = prefix
        for line in lines:
            if len(chunk) + len(line) + 1 > 1950:
                await message.channel.send(chunk)
                chunk = ""
            chunk += line + "\n"
        if chunk:
            await message.channel.send(chunk)

    # ── .help ──────────────────────────────────
    elif cmd == "help":
        await message.channel.send(
            "**🏛️  Civ 6 Draft Bot — Commands**\n\n"
            "`.draft <n>` — Open a lobby for *n* players\n"
            "`.join` — Join the open lobby\n"
            "`.vote` — Vote for a secret draft (leaders sent by DM)\n"
            "`.ban <Leader Name>` — Nominate a leader to be banned (majority auto-bans)\n"
            "`.startdraft` — Host: start the draft with current players\n"
            "`.canceldraft` — Host: cancel the current draft\n"
            "`.leaders` — Show all leaders in the current pool\n"
            "`.help` — Show this message\n"
        )


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
client.run(BOT_TOKEN)
