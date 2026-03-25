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
   (Locally: export DISCORD_TOKEN=yourtoken)

4. Invite the bot with permissions: Send Messages, Read Message History, Add Reactions

5. Run:
       python civ6_draft_bot.py

FLOW:
  .draft <n>       — Host opens a lobby for n players
  .join            — Players join the lobby
  .vote            — Host kicks off the settings + ban vote (all lines post at once)
  .closevote       — Host closes voting and tallies all results
  .ban <Leader>    — Nominate a civ leader for a ban (majority auto-bans)
  .startdraft      — Host starts the leader draft after voting is done
  .trade @Player   — Offer to swap your full leader list with another player
  .canceldraft     — Host cancels the current session
  .leaders         — Show the current leader pool
  .help            — Show all commands
"""

import discord
import random
import os
import asyncio
from collections import defaultdict

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("DISCORD_TOKEN", "")
PREFIX = "."

if not BOT_TOKEN:
    raise ValueError(
        "No DISCORD_TOKEN found. Set it as an environment variable:\n"
        "  export DISCORD_TOKEN=your_token_here\n"
        "Or add it to your Railway project's Variables tab."
    )

# ─────────────────────────────────────────────
# SETTINGS DEFINITIONS
# Each setting: (label, [(emoji, option_text), ...])
# For settings with many options we use letter emojis.
# ─────────────────────────────────────────────
SETTINGS = [
    ("🤝 Official Friends/Allies", [
        ("0️⃣", "0"),
        ("1️⃣", "1"),
        ("2️⃣", "2"),
        ("♾️", "Infinite"),
    ]),
    ("🏛️ BYC Mode (Capitals Only)", [
        ("🔴", "Maximum"),
        ("🟡", "Balanced"),
        ("🟢", "Off"),
    ]),
    ("⏱️ Game Duration", [
        ("2️⃣", "2 Hours"),
        ("4️⃣", "4 Hours"),
        ("6️⃣", "6 Hours"),
        ("♾️", "Unlimited"),
    ]),
    ("🗺️ Map", [
        ("🅰️", "Pangaea"),
        ("🅱️", "7 Seas"),
        ("🇨", "Highlands"),
        ("🇩", "Highlands (Rich)"),
        ("🇪", "Lakes"),
        ("🇫", "Inland Sea"),
        ("🇬", "Primordial"),
        ("🇭", "Tilted Axis"),
        ("🇮", "Tilted Axis Wraparound"),
        ("🇯", "Continents"),
        ("🇰", "Continents & Islands"),
        ("🇱", "Small Continents"),
        ("🇲", "Wetlands"),
        ("🇳", "Fractal"),
        ("🇴", "Splintered Fractal"),
        ("🇵", "Island Plates"),
        ("🇶", "Terra"),
    ]),
    ("🌊 Sea Level", [
        ("⬇️", "Low"),
        ("➡️", "Standard"),
        ("⬆️", "High"),
    ]),
    ("🌋 Disasters", [
        ("1️⃣", "1"),
        ("2️⃣", "2"),
        ("3️⃣", "3"),
        ("4️⃣", "4"),
    ]),
    ("⚔️ Barbarians Mode", [
        ("🚫", "No Barbs"),
        ("🟢", "Normal"),
        ("🤝", "Civilized"),
        ("💀", "Raging"),
    ]),
    ("🗳️ CC Voting", [
        ("⏪", "20 Turns Earlier"),
        ("◀️", "10 Turns Earlier"),
        ("⏺️", "Standard"),
        ("▶️", "10 Turns Later"),
        ("⏩", "20 Turns Later"),
    ]),
    ("🎲 Draft Mode", [
        ("📢", "Public"),
        ("🤫", "Secret"),
    ]),
]

# These settings are fixed and not voted on — posted after .closevote
STATIC_SETTINGS = [
    ("💰 Gold Trading",        "Not Allowed"),
    ("💎 Luxuries Trading",    "Allowed"),
    ("⚙️ Strategics Trading",  "Not Allowed"),
    ("🤜 Military Alliance",   "Not Allowed"),
    ("⏲️ Timer",               "Competitive"),
    ("🌾 Resources",           "Abundant"),
    ("🪨 Strategics",          "Abundant"),
]

# Full natural wonder list (BBG 7.3 + BBM additions)
ALL_WONDERS = [
    "Barringer Crater", "Bermuda Triangle", "Bioluminescent Bay",
    "Cerro de Potosi", "Chocolate Hills", "Cliffs of Dover",
    "Crater Lake", "Dallol", "Dead Sea", "Delicate Arch",
    "Mato Tipila", "Mount Everest", "Eye of the Sahara",
    "Eyjafjallajökull", "Fountain of Youth", "Galápagos Islands",
    "Giant's Causeway", "Rock of Gibraltar", "Gobustan",
    "Grand Mesa", "Great Barrier Reef", "Hạ Long Bay", "Ik-Kil",
    "Mount Kailash", "Mount Kilimanjaro", "Krakatoa", "Lake Retba",
    "Lake Victoria", "Lençóis Maranhenses", "Lysefjord", "Matterhorn",
    "Mosi-oa-Tunya", "Motlatse Canyon", "Namib Sand Sea", "Old Faithful",
    "Lakes of Ounianga", "Païtiti", "Pamukkale", "Pantanal", "Piopiotahi",
    "Mount Roraima", "Salar de Uyuni", "Mount Sinai", "Sri Pada",
    "Torres del Paine", "Tsingy de Bemaraha", "Ubsunur Hollow", "Uluru",
    "Mount Vesuvius", "Vredefort Dome", "Sahara el Beyda", "Wulingyuan",
    "Yosemite", "Zhangye Danxia",
]

# ─────────────────────────────────────────────
# FULL LEADER POOL
# Base game + Rise & Fall + Gathering Storm +
# New Frontier Pass + BBG Expanded mod leaders
# ─────────────────────────────────────────────
ALL_LEADERS = [
    ("Abraham Lincoln",                   "America"),
    ("Teddy Roosevelt (Bull Moose)",       "America"),
    ("Teddy Roosevelt (Rough Rider)",      "America"),
    ("Saladin (Vizier)",                   "Arabia"),
    ("Saladin (Sultan)",                   "Arabia"),
    ("John Curtin",                        "Australia"),
    ("Montezuma",                          "Aztec"),
    ("Hammurabi",                          "Babylon"),
    ("Pedro II",                           "Brazil"),
    ("Basil II",                           "Byzantium"),
    ("Theodora",                           "Byzantium"),
    ("Wilfrid Laurier",                    "Canada"),
    ("Kublai Khan (China)",                "China"),
    ("Qin Shi Huang (Mandate of Heaven)",  "China"),
    ("Qin Shi Huang (Unifier)",            "China"),
    ("Wu Zetian",                          "China"),
    ("Yongle",                             "China"),
    ("Poundmaker",                         "Cree"),
    ("Cleopatra (Egyptian)",               "Egypt"),
    ("Cleopatra (Ptolemaic)",              "Egypt"),
    ("Ramses II",                          "Egypt"),
    ("Eleanor of Aquitaine (England)",     "England"),
    ("Elizabeth I",                        "England"),
    ("Victoria (Age of Empire)",           "England"),
    ("Victoria (Age of Steam)",            "England"),
    ("Menelik II",                         "Ethiopia"),
    ("Catherine de Medici (Black Queen)",  "France"),
    ("Catherine de Medici (Magnificence)", "France"),
    ("Eleanor of Aquitaine (France)",      "France"),
    ("Ambiorix",                           "Gaul"),
    ("Vercingetorix",                      "Gaul"),
    ("Tamar",                              "Georgia"),
    ("Frederick Barbarossa",               "Germany"),
    ("Ludwig II",                          "Germany"),
    ("Simón Bolívar",                      "Gran Colombia"),
    ("Gorgo",                              "Greece"),
    ("Pericles",                           "Greece"),
    ("Matthias Corvinus",                  "Hungary"),
    ("Pachacuti",                          "Inca"),
    ("Chandragupta",                       "India"),
    ("Gandhi",                             "India"),
    ("Gitarja",                            "Indonesia"),
    ("Hojo Tokimune",                      "Japan"),
    ("Tokugawa",                           "Japan"),
    ("Jayavarman VII",                     "Khmer"),
    ("Mvemba a Nzinga",                    "Kongo"),
    ("Nzinga Mbande",                      "Kongo"),
    ("Sejong",                             "Korea"),
    ("Seondeok",                           "Korea"),
    ("Alexander",                          "Macedon"),
    ("Olympias",                           "Macedon"),
    ("Mansa Musa",                         "Mali"),
    ("Sundiata Keita",                     "Mali"),
    ("Kupe",                               "Māori"),
    ("Lautaro",                            "Mapuche"),
    ("Lady Six Sky",                       "Maya"),
    ("Te' K'inich II",                     "Maya"),
    ("Genghis Khan",                       "Mongolia"),
    ("Kublai Khan (Mongolia)",             "Mongolia"),
    ("Wilhelmina",                         "Netherlands"),
    ("Harald Hardrada (Varangian)",        "Norway"),
    ("Harald Hardrada (Konge)",            "Norway"),
    ("Amanitore",                          "Nubia"),
    ("Suleiman (Kanuni)",                  "Ottomans"),
    ("Suleiman (Muhteşem)",                "Ottomans"),
    ("Cyrus",                              "Persia"),
    ("Nader Shah",                         "Persia"),
    ("Dido",                               "Phoenicia"),
    ("Ahiram",                             "Phoenicia"),
    ("Jadwiga",                            "Poland"),
    ("João III",                           "Portugal"),
    ("Julius Caesar",                      "Rome"),
    ("Trajan",                             "Rome"),
    ("Peter",                              "Russia"),
    ("Robert the Bruce",                   "Scotland"),
    ("Tomyris",                            "Scythia"),
    ("Philip II",                          "Spain"),
    ("Gilgamesh",                          "Sumeria"),
    ("Al-Hasan ibn Sulaiman",              "Swahili"),
    ("Kristina",                           "Sweden"),
    ("Spearthrower Owl",                   "Teotihuacán"),
    ("Kiviuq",                             "Thule"),
    ("Trisong Detsen",                     "Tibet"),
    ("Bà Triệu",                           "Vietnam"),
    ("Shaka",                              "Zulu"),
]

# ─────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.voice_states = True
client = discord.Client(intents=intents)

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
drafts        = {}   # channel_id -> DraftSession
pending_trades = {}    # message_id -> TradeOffer
active_timed_votes = {}  # channel_msg_id -> timer task
timed_vote_dm_data = {}  # dm_msg_id -> {channel_id, vote_id, user_id, kind}

# ─────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────
class DraftSession:
    def __init__(self, host_id, host_name, player_count, channel_id):
        self.host_id        = host_id
        self.host_name      = host_name
        self.player_count   = player_count
        self.channel_id     = channel_id

        self.players        = [host_id]
        self.player_names   = {host_id: host_name}

        # Leader ban system
        self.banned_leaders   = set()
        self.ban_nominations  = {}

        # Wonder ban system
        self.banned_wonders   = set()
        self.wonder_nominations = {}

        # Settings vote
        self.voting_open      = False
        self.vote_messages    = {}   # message_id -> (setting_label, [(emoji, option)])
        self.vote_results     = {}   # setting_label -> winning option text
        self.ready_message_id = None # message_id of the ready-check message
        self.ready_confirmed  = set() # user IDs who have reacted ✅

        # Draft
        self.assignments      = {}
        self.started          = False
        self.is_secret        = False

        # Secret draft pick tracking
        self.secret_channel_id  = None   # channel to post results in
        self.secret_picks       = {}     # user_id -> (leader, civ)
        self.secret_dm_msgs     = {}     # dm_msg_id -> user_id
        self.secret_dm_leaders  = {}     # user_id -> [(leader, civ), ...]  (their pool)

    def is_host(self, uid): return uid == self.host_id

    def add_player(self, uid, uname):
        if uid not in self.players:
            self.players.append(uid)
            self.player_names[uid] = uname
            return True
        return False

    def is_full(self): return len(self.players) >= self.player_count

    def available_pool(self):
        return [(l, c) for (l, c) in ALL_LEADERS if l not in self.banned_leaders]

    def run_draft(self):
        pool = self.available_pool()
        random.shuffle(pool)
        n = len(self.players)
        per_player = min(10, len(pool) // n)
        for i, uid in enumerate(self.players):
            self.assignments[uid] = pool[i * per_player:(i + 1) * per_player]
        self.started = True

    def ban_vote_result(self, key, nominations_dict):
        votes  = len(nominations_dict.get(key, set()))
        needed = max(2, (len(self.players) // 2) + 1)
        return votes >= needed

    def find_leader(self, name):
        name_lower = name.lower()
        for (l, c) in ALL_LEADERS:
            if l.lower() == name_lower:
                return l
        return None

    def find_wonder(self, name):
        name_lower = name.lower()
        for w in ALL_WONDERS:
            if w.lower() == name_lower:
                return w
        return None


class TradeOffer:
    def __init__(self, channel_id, sender_id, receiver_id):
        self.channel_id  = channel_id
        self.sender_id   = sender_id
        self.receiver_id = receiver_id


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def format_assignment(leaders):
    return "\n".join(f"  • **{l}** ({c})" for l, c in leaders)

def majority_winner(reaction_counts, options):
    """Given {emoji: count}, return the option text with the most votes."""
    best_emoji = max(reaction_counts, key=lambda e: reaction_counts[e], default=None)
    if best_emoji is None:
        return "No votes"
    for emoji, text in options:
        if emoji == best_emoji:
            return text
    return "No votes"


# ─────────────────────────────────────────────
# HELPER: run the leader draft for a session
# ─────────────────────────────────────────────
async def run_draft_for_session(session, channel):
    NUMBER_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    session.run_draft()
    ban_list     = (", ".join(f"**{b}**" for b in sorted(session.banned_leaders))
                    if session.banned_leaders else "none")
    vote_summary = "🤫 Secret draft!" if session.is_secret else "📢 Public draft"
    await channel.send(
        f"🎲  **Leader Draft starting!**\n"
        f"{vote_summary}\n"
        f"🚫 Banned leaders: {ban_list}\n"
        f"🃏 Each player receives **{len(list(session.assignments.values())[0])}** leaders to choose from.\n"
    )

    if session.is_secret:
        session.secret_channel_id = channel.id
        failed = []
        for pid in session.players:
            pleads = session.assignments[pid]
            try:
                user = await client.fetch_user(pid)
                lines    = [f"{NUMBER_EMOJIS[i]}  **{l}** ({c})" for i, (l, c) in enumerate(pleads)]
                list_str = "\n".join(lines)
                dm = await user.send(
                    f"🏛️  **Secret Draft — Pick Your Leader!**\n"
                    f"React with the number of your chosen leader.\n\n"
                    f"{list_str}"
                )
                for i in range(len(pleads)):
                    await dm.add_reaction(NUMBER_EMOJIS[i])
                session.secret_dm_msgs[dm.id]  = pid
                session.secret_dm_leaders[pid] = pleads
            except discord.Forbidden:
                failed.append(session.player_names[pid])
        await channel.send(
            f"🤫  Leaders sent to each player via DM. Results posted here once everyone picks.\n"
            + (f"⚠️  Could not DM: {', '.join(failed)}" if failed else "")
        )
        # Session stays alive until all picks are in
    else:
        await channel.send("🏛️  **Draft Results** — each player picks one leader:\n\u200b")
        for pid in session.players:
            pname  = session.player_names[pid]
            pleads = session.assignments[pid]
            await channel.send(f"**{pname}** — pick one:\n{format_assignment(pleads)}")
        drafts.pop(channel.id, None)


# ─────────────────────────────────────────────
# HELPER: tally votes, edit messages, run draft
# ─────────────────────────────────────────────
async def close_vote(session, channel):
    session.voting_open = False

    for msg_id, (label, options) in session.vote_messages.items():
        try:
            fetched = await channel.fetch_message(msg_id)
            counts  = {}
            for reaction in fetched.reactions:
                counts[str(reaction.emoji)] = max(0, reaction.count - 1)
            winner = majority_winner(counts, options)

            if label == "🎲 Draft Mode":
                session.is_secret = (winner == "Secret")

            session.vote_results[label] = winner
            await fetched.edit(content=f"**{label}**\n✅  **{winner}**")
            await fetched.clear_reactions()
        except Exception:
            pass

    # Edit ready-check message
    if session.ready_message_id:
        try:
            ready_msg = await channel.fetch_message(session.ready_message_id)
            await ready_msg.edit(content="✅  **All players ready — vote closed!**")
            await ready_msg.clear_reactions()
        except Exception:
            pass

    static_lines = "\n".join(f"{label}: **{value}**" for label, value in STATIC_SETTINGS)
    await channel.send(f"📌  **Fixed Settings:**\n{static_lines}")

    # Automatically run the draft
    await run_draft_for_session(session, channel)



@client.event
async def on_ready():
    print(f"✅  Logged in as {client.user} (ID: {client.user.id})")
    print(f"    Leader pool: {len(ALL_LEADERS)} leaders | {len(ALL_WONDERS)} wonders")
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

    parts = message.content[len(PREFIX):].strip().split(None, 1)
    cmd   = parts[0].lower() if parts else ""
    args  = parts[1].strip() if len(parts) > 1 else ""
    cid   = message.channel.id
    uid   = message.author.id
    uname = message.author.display_name

    # ── .vote [@exclude ...] ───────────────────
    if cmd == "vote":
        if cid in drafts and not drafts[cid].started:
            await message.channel.send("⚠️  A session is already running! Use `.canceldraft` first.")
            return
        if cid in drafts and drafts[cid].voting_open:
            await message.channel.send("⚠️  Voting is already open!")
            return

        # ── Step 1: detect players from voice channel ──
        excluded_ids  = {m.id for m in message.mentions}
        voice_members = []
        host_member   = message.guild.get_member(uid) if message.guild else None
        if host_member and host_member.voice and host_member.voice.channel:
            vc = host_member.voice.channel
            voice_members = [
                m for m in vc.members
                if not m.bot and m.id not in excluded_ids
            ]

        if not voice_members or len(voice_members) < 2:
            await message.channel.send(
                "❌  You need to be in a voice channel with at least 2 players.\n"
                "Use `.vote @skip` to exclude players in the call."
            )
            return

        # ── Step 2: create session and auto-join everyone ──
        session = DraftSession(uid, uname, len(voice_members), cid)
        session.players      = []
        session.player_names = {}
        for m in voice_members:
            session.add_player(m.id, m.display_name)
        session.player_count = len(session.players)
        drafts[cid] = session
        session.voting_open = True

        player_list = "\n".join(f"  • {session.player_names[p]}" for p in session.players)
        excl_note   = (f"\n*(Excluded: {', '.join(m.mention for m in message.mentions)})*"
                       if excluded_ids else "")
        await message.channel.send(
            f"🏛️  **Civ 6 Draft Lobby** opened by **{uname}**!\n"
            f"🎙️  **{len(session.players)} players** from **{vc.name}**:{excl_note}\n"
            f"{player_list}\n\n"
            f"🗳️  **Settings Vote is now open!**\n"
            f"React to each setting below. Most reactions wins.\n"
            f"Use `.ban <Leader>` and `.wban <Wonder>` to nominate bans.\n"
            f"React ➕ to the ready check at the bottom when you're done voting.\n"
            f"─────────────────────────────────────"
        )

        for label, options in SETTINGS:
            option_lines = "  ".join(f"{e} {o}" for e, o in options)
            msg = await message.channel.send(f"**{label}**\n{option_lines}")
            for emoji, _ in options:
                try:
                    await msg.add_reaction(emoji)
                except Exception:
                    pass
            session.vote_messages[msg.id] = (label, options)

        # Wonder ban list
        chunk = "**🌟 Wonder Bans** — `.wban <Wonder Name>` to nominate:\n"
        for w in sorted(ALL_WONDERS):
            line = f"• {w}\n"
            if len(chunk) + len(line) > 1900:
                await message.channel.send(chunk)
                chunk = ""
            chunk += line
        await message.channel.send(chunk)

        # Civ ban section
        await message.channel.send(
            "**🚫 Civ Bans** — `.ban <Leader Name>` to nominate. Use `.leaders` for the full list."
        )

        # Ready-check message — tags all players, auto-closes when all react ➕
        mentions = " ".join(f"<@{pid}>" for pid in session.players)
        ready_msg = await message.channel.send(
            f"✋  **Ready Check** — react ➕ when you're done voting!\n{mentions}"
        )
        await ready_msg.add_reaction("➕")
        session.ready_message_id = ready_msg.id

    # ── .closevote ─────────────────────────────
    elif cmd == "closevote":
        if cid not in drafts:
            await message.channel.send("❌  No lobby open.")
            return
        session = drafts[cid]
        if not session.is_host(uid):
            await message.channel.send("❌  Only the host can close voting.")
            return
        if not session.voting_open:
            await message.channel.send("❌  No vote is currently open.")
            return

        await close_vote(session, message.channel)
        return

    # ── .ban <leader> ──────────────────────────
    elif cmd == "ban":
        if cid not in drafts:
            await message.channel.send("❌  No lobby open.")
            return
        session = drafts[cid]
        if uid not in session.players:
            await message.channel.send("❌  You must join the lobby first.")
            return
        if session.started:
            await message.channel.send("❌  Bans must happen before the draft starts.")
            return
        if not args:
            await message.channel.send("❌  Usage: `.ban <Leader Name>`")
            return
        canonical = session.find_leader(args)
        if not canonical:
            await message.channel.send(f"❌  **{args}** not found. Use `.leaders` to see all leaders.")
            return
        if canonical in session.banned_leaders:
            await message.channel.send(f"ℹ️  **{canonical}** is already banned.")
            return
        if canonical not in session.ban_nominations:
            session.ban_nominations[canonical] = set()
        session.ban_nominations[canonical].add(uid)
        votes  = len(session.ban_nominations[canonical])
        needed = max(2, (len(session.players) // 2) + 1)
        if session.ban_vote_result(canonical, session.ban_nominations):
            session.banned_leaders.add(canonical)
            await message.channel.send(
                f"🚫  **{canonical}** has been **banned**! ({votes}/{needed} votes)"
            )
        else:
            await message.channel.send(
                f"🗳️  **{uname}** nominated **{canonical}** for a ban. ({votes}/{needed} votes needed)"
            )

    # ── .wban <wonder> ─────────────────────────
    elif cmd == "wban":
        if cid not in drafts:
            await message.channel.send("❌  No lobby open.")
            return
        session = drafts[cid]
        if uid not in session.players:
            await message.channel.send("❌  You must join the lobby first.")
            return
        if session.started:
            await message.channel.send("❌  Bans must happen before the draft starts.")
            return
        if not args:
            await message.channel.send("❌  Usage: `.wban <Wonder Name>`")
            return
        canonical = session.find_wonder(args)
        if not canonical:
            await message.channel.send(f"❌  **{args}** not found. Check the wonder list above.")
            return
        if canonical in session.banned_wonders:
            await message.channel.send(f"ℹ️  **{canonical}** is already banned.")
            return
        if canonical not in session.wonder_nominations:
            session.wonder_nominations[canonical] = set()
        session.wonder_nominations[canonical].add(uid)
        votes  = len(session.wonder_nominations[canonical])
        needed = max(2, (len(session.players) // 2) + 1)
        if session.ban_vote_result(canonical, session.wonder_nominations):
            session.banned_wonders.add(canonical)
            await message.channel.send(
                f"🌟  **{canonical}** has been **banned**! ({votes}/{needed} votes)"
            )
        else:
            await message.channel.send(
                f"🗳️  **{uname}** nominated wonder **{canonical}** for a ban. ({votes}/{needed} needed)"
            )


    # ── .trade @user ───────────────────────────
    elif cmd == "trade":
        if cid not in drafts:
            await message.channel.send("❌  No active draft found.")
            return
        session = drafts[cid]
        if uid not in session.assignments:
            await message.channel.send("❌  You don't have a draft assignment yet.")
            return
        if not message.mentions:
            await message.channel.send("❌  Usage: `.trade @PlayerName`")
            return
        target = message.mentions[0]
        tid    = target.id
        if tid == uid:
            await message.channel.send("❌  You can't trade with yourself.")
            return
        if tid not in session.assignments:
            await message.channel.send(f"❌  **{target.display_name}** doesn't have a draft assignment.")
            return

        sender_list   = format_assignment(session.assignments[uid])
        receiver_list = format_assignment(session.assignments[tid])
        offer_msg = await message.channel.send(
            f"🔀  **Trade Offer!**\n"
            f"**{uname}** wants to swap their entire list with **{target.display_name}**.\n\n"
            f"**{uname}'s leaders:**\n{sender_list}\n\n"
            f"**{target.display_name}'s leaders:**\n{receiver_list}\n\n"
            f"{target.mention} — react ✅ to accept or ❌ to decline."
        )
        await offer_msg.add_reaction("✅")
        await offer_msg.add_reaction("❌")
        pending_trades[offer_msg.id] = TradeOffer(cid, uid, tid)

    # ── .cc @player ────────────────────────────
    elif cmd == "cc":
        if not message.mentions:
            await message.channel.send("❌  Usage: `.cc @PlayerName`")
            return
        target = message.mentions[0]
        if cid not in drafts:
            await message.channel.send("❌  No active session found.")
            return
        session = drafts[cid]
        if target.id not in session.players:
            await message.channel.send(f"❌  **{target.display_name}** is not in the current session.")
            return

        # Eligible voters: everyone except the CC target
        voter_ids = [pid for pid in session.players if pid != target.id]
        vote_id   = vote_msg_id = None

        # Post public notice (no reactions)
        notice = await message.channel.send(
            f"🏆  **CC Vote** started by **{uname}** — concede to **{target.display_name}**?\nBallots sent via DM. **{target.display_name}** cannot vote.\n⏱️  2 minutes to vote."
        )
        vote_id = notice.id

        # DM each eligible voter
        failed = []
        dm_msg_ids = {}  # user_id -> dm_msg_id
        for pid in voter_ids:
            try:
                voter = await client.fetch_user(pid)
                dm = await voter.send(
                    f"🏆  **Secret CC Vote** — concede the game to **{target.display_name}**?\nReact 👍 for Yay or 👎 for Nay. You have **2 minutes**."
                )
                await dm.add_reaction("👍")
                await dm.add_reaction("👎")
                timed_vote_dm_data[dm.id] = {
                    "channel_id": cid,
                    "vote_id": notice.id,
                    "user_id": pid,
                    "kind": "cc",
                    "voted": False,
                }
                dm_msg_ids[pid] = dm.id
            except discord.Forbidden:
                failed.append(pid)

        if failed:
            names = ", ".join(session.player_names.get(pid, str(pid)) for pid in failed)
            await message.channel.send(f"⚠️  Could not DM: **{names}** — their votes won't be counted.")

        async def cc_timeout():
            await asyncio.sleep(120)
            if notice.id not in active_timed_votes:
                return
            del active_timed_votes[notice.id]

            yay = nay = 0
            voted = set()
            for pid, dm_id in dm_msg_ids.items():
                entry = timed_vote_dm_data.get(dm_id)
                if entry and entry["voted"]:
                    voted.add(pid)
                # Clean up dm data
                timed_vote_dm_data.pop(dm_id, None)

            # Re-fetch DM messages to count reactions
            for pid, dm_id in dm_msg_ids.items():
                try:
                    voter = await client.fetch_user(pid)
                    dm_channel = voter.dm_channel or await voter.create_dm()
                    dm_msg = await dm_channel.fetch_message(dm_id)
                    for r in dm_msg.reactions:
                        if str(r.emoji) == "👍":
                            async for u in r.users():
                                if u.id == pid:
                                    yay += 1
                                    voted.add(pid)
                        if str(r.emoji) == "👎":
                            async for u in r.users():
                                if u.id == pid:
                                    nay += 1
                                    voted.add(pid)
                    await dm_msg.edit(content="✅  This CC vote has closed. Thank you for voting!")
                    await dm_msg.clear_reactions()
                except Exception:
                    pass

            did_not_vote = [pid for pid in voter_ids if pid not in voted]
            dnv_str = ""
            if did_not_vote:
                names = ", ".join(session.player_names.get(p, str(p)) for p in did_not_vote)
                dnv_str = f"\n⚠️  Did not vote: **{names}**"

            try:
                await notice.edit(content=(
                    f"🏆  **CC Vote — CLOSED** — concede to **{target.display_name}**?\n"
                    f"👍 Yay: **{yay}**   👎 Nay: **{nay}**{dnv_str}"
                ))
            except Exception:
                await message.channel.send(
                    f"🏆  **CC Vote — CLOSED** — concede to **{target.display_name}**?\n"
                    f"👍 Yay: **{yay}**   👎 Nay: **{nay}**{dnv_str}"
                )

        task = asyncio.create_task(cc_timeout())
        active_timed_votes[notice.id] = task

    # ── .irrel @player ─────────────────────────
    elif cmd == "irrel":
        if not message.mentions:
            await message.channel.send("❌  Usage: `.irrel @PlayerName`")
            return
        target = message.mentions[0]
        if target.id == uid:
            await message.channel.send("❌  You can't call an irrel vote on yourself.")
            return
        if cid not in drafts:
            await message.channel.send("❌  No active session found.")
            return
        session = drafts[cid]
        if target.id not in session.players:
            await message.channel.send(f"❌  **{target.display_name}** is not in the current session.")
            return

        # Eligible voters: everyone except the irrel target
        voter_ids = [pid for pid in session.players if pid != target.id]

        notice = await message.channel.send(
            f"⚪  **Irrel Vote** started by **{uname}** — is **{target.display_name}** irrelevant?\nBallots sent via DM. **{target.display_name}** cannot vote.\n⏱️  2 minutes to vote."
        )

        failed = []
        dm_msg_ids = {}
        for pid in voter_ids:
            try:
                voter = await client.fetch_user(pid)
                dm = await voter.send(
                    f"⚪  **Secret Irrel Vote** — is **{target.display_name}** irrelevant?\nReact 👍 for Yay or 👎 for Nay. You have **2 minutes**."
                )
                await dm.add_reaction("👍")
                await dm.add_reaction("👎")
                timed_vote_dm_data[dm.id] = {
                    "channel_id": cid,
                    "vote_id": notice.id,
                    "user_id": pid,
                    "kind": "irrel",
                    "voted": False,
                }
                dm_msg_ids[pid] = dm.id
            except discord.Forbidden:
                failed.append(pid)

        if failed:
            names = ", ".join(session.player_names.get(pid, str(pid)) for pid in failed)
            await message.channel.send(f"⚠️  Could not DM: **{names}** — their votes won't be counted.")

        async def irrel_timeout():
            await asyncio.sleep(120)
            if notice.id not in active_timed_votes:
                return
            del active_timed_votes[notice.id]

            yay = nay = 0
            voted = set()

            for pid, dm_id in dm_msg_ids.items():
                try:
                    voter = await client.fetch_user(pid)
                    dm_channel = voter.dm_channel or await voter.create_dm()
                    dm_msg = await dm_channel.fetch_message(dm_id)
                    for r in dm_msg.reactions:
                        if str(r.emoji) == "👍":
                            async for u in r.users():
                                if u.id == pid:
                                    yay += 1
                                    voted.add(pid)
                        if str(r.emoji) == "👎":
                            async for u in r.users():
                                if u.id == pid:
                                    nay += 1
                                    voted.add(pid)
                    await dm_msg.edit(content="✅  This irrel vote has closed. Thank you for voting!")
                    await dm_msg.clear_reactions()
                    timed_vote_dm_data.pop(dm_id, None)
                except Exception:
                    pass

            did_not_vote = [pid for pid in voter_ids if pid not in voted]
            dnv_str = ""
            if did_not_vote:
                names = ", ".join(session.player_names.get(p, str(p)) for p in did_not_vote)
                dnv_str = f"\n⚠️  Did not vote: **{names}**"

            try:
                await notice.edit(content=(
                    f"⚪  **Irrel Vote — CLOSED** — is **{target.display_name}** irrelevant?\n"
                    f"👍 Yay: **{yay}**   👎 Nay: **{nay}**{dnv_str}"
                ))
            except Exception:
                await message.channel.send(
                    f"⚪  **Irrel Vote — CLOSED** — is **{target.display_name}** irrelevant?\n"
                    f"👍 Yay: **{yay}**   👎 Nay: **{nay}**{dnv_str}"
                )

        task = asyncio.create_task(irrel_timeout())
        active_timed_votes[notice.id] = task

        # ── .canceldraft ───────────────────────────
    elif cmd == "canceldraft":
        if cid not in drafts:
            await message.channel.send("❌  No active session to cancel.")
            return
        session = drafts[cid]
        if not session.is_host(uid):
            await message.channel.send("❌  Only the host can cancel the draft.")
            return
        del drafts[cid]
        await message.channel.send("🗑️  Draft cancelled.")

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
        lines = [f"**{civ}**: {', '.join(by_civ[civ])}" for civ in sorted(by_civ)]
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
            "`.vote` — Start a session: detect players from voice + open settings votes\n"
            "`.vote @skip` — Same but exclude tagged players\n"
            "`.ban <Leader>` — Nominate a leader to ban (majority auto-bans)\n"
            "`.wban <Wonder>` — Nominate a natural wonder to ban\n"
            "`.closevote` — Host: tally all votes and post final settings\n"
            "`.trade @Player` — Offer to swap your full leader list\n"
            "`.cc @Player` — Start a 2-min vote to concede the game to a player\n"
            "`.irrel @Player` — Start a 2-min vote to mark a player as irrelevant\n"
            "`.canceldraft` — Host: cancel the current session\n"
            "`.leaders` — Show all leaders in the current pool\n"
            "`.help` — Show this message\n"
        )


# ─────────────────────────────────────────────
# EVENT: on_reaction_add — trade responses
# ─────────────────────────────────────────────
@client.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    msg_id  = reaction.message.id
    channel = reaction.message.channel

    # ── Secret draft pick handler ──
    NUMBER_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    for cid, session in list(drafts.items()):
        if msg_id in session.secret_dm_msgs:
            picker_id = session.secret_dm_msgs[msg_id]
            if user.id != picker_id:
                return  # ignore reactions from anyone else
            emoji = str(reaction.emoji)
            if emoji in NUMBER_EMOJIS:
                idx = NUMBER_EMOJIS.index(emoji)
                leaders = session.secret_dm_leaders.get(picker_id, [])
                if idx < len(leaders):
                    session.secret_picks[picker_id] = leaders[idx]
                    # Edit the DM to confirm the pick and lock it
                    try:
                        pick_name = leaders[idx][0]
                        dm_msg = reaction.message
                        await dm_msg.edit(
                            content=f"✅  You picked **{pick_name}**! Your selection has been locked in."
                        )
                        await dm_msg.clear_reactions()
                    except Exception:
                        pass

                    # Check if everyone has picked
                    if set(session.secret_picks.keys()) == set(session.players):
                        channel = client.get_channel(session.secret_channel_id)
                        if channel:
                            await channel.send("🏛️  **Secret Draft Results — all players have picked!**\n\u200b")
                            for pid in session.players:
                                pname = session.player_names[pid]
                                pick  = session.secret_picks[pid]
                                await channel.send(f"**{pname}** picked: **{pick[0]}** ({pick[1]})")
                        del drafts[cid]
            return

    # ── Ready-check handler ──
    for cid, session in drafts.items():
        if msg_id == session.ready_message_id and session.voting_open:
            if str(reaction.emoji) == "➕" and user.id in session.players:
                session.ready_confirmed.add(user.id)

                # Edit the message to remove the user's mention
                remaining = [pid for pid in session.players if pid not in session.ready_confirmed]
                if remaining:
                    mentions = " ".join(f"<@{pid}>" for pid in remaining)
                    try:
                        ready_msg = await channel.fetch_message(msg_id)
                        await ready_msg.edit(
                            content=f"✋  **Ready Check** — react ➕ when you're done voting!\n{mentions}"
                        )
                    except Exception:
                        pass
                else:
                    # Everyone is ready — auto-close the vote
                    await close_vote(session, channel)
            return

    # ── Trade offer handler ──
    if msg_id not in pending_trades:
        return

    trade   = pending_trades[msg_id]
    if user.id != trade.receiver_id:
        return

    channel = reaction.message.channel
    session = drafts.get(trade.channel_id)

    if str(reaction.emoji) == "✅":
        if session and trade.sender_id in session.assignments and trade.receiver_id in session.assignments:
            session.assignments[trade.sender_id], session.assignments[trade.receiver_id] = (
                session.assignments[trade.receiver_id],
                session.assignments[trade.sender_id]
            )
            sname = session.player_names.get(trade.sender_id, "Player")
            rname = session.player_names.get(trade.receiver_id, "Player")
            await channel.send(
                f"✅  **Trade complete!** {sname} and {rname} swapped lists.\n\n"
                f"**{sname}'s new leaders:**\n{format_assignment(session.assignments[trade.sender_id])}\n\n"
                f"**{rname}'s new leaders:**\n{format_assignment(session.assignments[trade.receiver_id])}"
            )
        else:
            await channel.send("❌  Trade failed — draft session no longer active.")
    elif str(reaction.emoji) == "❌":
        rname = session.player_names.get(trade.receiver_id, "Player") if session else "Player"
        await channel.send(f"❌  **{rname}** declined the trade.")

    del pending_trades[msg_id]


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
client.run(BOT_TOKEN)
