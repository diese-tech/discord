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
  .scrap <turn>    — Secret vote to scrap (turn-based threshold)
  .afk @Player     — Start 5-min AFK countdown
  .cancelafk @P    — Cancel an active AFK check
  .quit @Player    — Log a quit/drop (tracks 3-drop policy)
  .sub @Old @New   — Substitute a player mid-session
  .remap <turn>    — Unanimous secret vote to remap (turn ≤10)
  .help            — Show all commands
"""

import discord
from website_sync import sync_match_report, sync_full_stats, sync_announcement
from leader_match import build_leader_index, match_leader, format_ambiguous
import random
import os
import asyncio
import json
import uuid
from pathlib import Path
from collections import defaultdict

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("DISCORD_TOKEN", "")
REPORTS_CHANNEL_ID = int(os.environ.get("REPORTS_CHANNEL_ID", "1487172746386345995"))
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
        ("0️⃣", "0"),
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
LEADER_INDEX = build_leader_index(ALL_LEADERS)

# ─────────────────────────────────────────────
# STATS STORAGE
# ─────────────────────────────────────────────
STATS_FILE   = Path("stats.json")
REPORTS_FILE = Path("reports.json")

def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

# stats[user_id] = {
#   "name": str, "rating": float, "rd": float, "vol": float,
#   "games": int, "wins": int, "cc_wins": int,
#   "leaders": {"LeaderName": {"games": int, "wins": int}}
# }
stats   = load_json(STATS_FILE,   {})
reports = load_json(REPORTS_FILE, {})  # report_id -> {players_in_order, channel_id, ts}

GLICKO_Q     = 173.7178   # 400 / ln(10)
GLICKO_START = {"rating": 1500.0, "rd": 350.0, "vol": 0.06}

def get_player(uid, name):
    uid = str(uid)
    if uid not in stats:
        stats[uid] = {**GLICKO_START, "name": name,
                      "games": 0, "wins": 0, "first_place": 0, "cc_wins": 0, "leaders": {}}
    else:
        stats[uid]["name"] = name  # keep name fresh
    return stats[uid]

def glicko2_update(player, opponents):
    """
    Update a single player's Glicko-2 rating.
    opponents = list of (opp_player_dict, score) where score=1 win, 0.5 draw, 0 loss
    """
    import math
    mu  = (player["rating"] - 1500) / GLICKO_Q
    phi = player["rd"] / GLICKO_Q
    sig = player["vol"]

    def g(rd):
        return 1 / math.sqrt(1 + 3 * (rd / GLICKO_Q)**2 / math.pi**2)

    def E(mu, mu_j, phi_j):
        return 1 / (1 + math.exp(-g(phi_j) * (mu - mu_j)))

    if not opponents:
        # No games — increase RD slightly (inactivity)
        phi_star = math.sqrt(phi**2 + sig**2)
        player["rd"] = min(phi_star * GLICKO_Q, 350.0)
        return

    v_inv = sum(g(o["rd"]/GLICKO_Q)**2 * E(mu,(o["rating"]-1500)/GLICKO_Q,o["rd"]/GLICKO_Q) *
                (1 - E(mu,(o["rating"]-1500)/GLICKO_Q,o["rd"]/GLICKO_Q))
                for o, s in opponents)
    v = 1 / v_inv if v_inv else 1

    delta = v * sum(g(o["rd"]/GLICKO_Q) * (s - E(mu,(o["rating"]-1500)/GLICKO_Q,o["rd"]/GLICKO_Q))
                    for o, s in opponents)

    # Iterative volatility update (Illinois algorithm)
    a = math.log(sig**2)
    tau = 0.5
    A = a
    B = None
    f = lambda x: (math.exp(x)*(delta**2 - phi**2 - v - math.exp(x)) /
                   (2*(phi**2 + v + math.exp(x))**2) - (x - a) / tau**2)
    if delta**2 > phi**2 + v:
        B = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        B = a - k * tau

    fA, fB = f(A), f(B)
    for _ in range(100):
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB < 0:
            A, fA = B, fB
        else:
            fA /= 2
        B, fB = C, fC
        if abs(B - A) < 1e-6:
            break
    new_sig = math.exp(A / 2)

    phi_star = math.sqrt(phi**2 + new_sig**2)
    new_phi  = 1 / math.sqrt(1/phi_star**2 + 1/v)
    new_mu   = mu + new_phi**2 * sum(g(o["rd"]/GLICKO_Q) *
                                     (s - E(mu,(o["rating"]-1500)/GLICKO_Q,o["rd"]/GLICKO_Q))
                                     for o, s in opponents)

    player["rating"] = new_mu * GLICKO_Q + 1500
    player["rd"]     = max(new_phi * GLICKO_Q, 30.0)
    player["vol"]    = new_sig

def process_report(ordered_ids, ordered_names, winner_id, is_cc, channel_id):
    """
    ordered_ids: list of user IDs from 1st to last place
    Treat as pairwise: higher placement beats lower placement.
    """
    n = len(ordered_ids)
    players_data = [get_player(uid, ordered_names[i]) for i, uid in enumerate(ordered_ids)]

    # Capture ratings before Glicko update
    ratings_before = {}
    for uid in ordered_ids:
        uid_s = str(uid)
        ratings_before[uid_s] = stats[uid_s]["rating"]

    # Build pairwise matchups for each player
    for i, uid in enumerate(ordered_ids):
        p = players_data[i]
        opps = []
        for j, opp_uid in enumerate(ordered_ids):
            if i == j:
                continue
            score = 1.0 if i < j else 0.0  # lower index = higher placement = win
            opps.append((players_data[j], score))
        glicko2_update(p, opps)

    # Update stats
    for i, uid in enumerate(ordered_ids):
        uid_s = str(uid)
        stats[uid_s]["games"] += 1

        # First place tracking (separate from wins)
        if i == 0:
            if "first_place" not in stats[uid_s]:
                stats[uid_s]["first_place"] = 0
            stats[uid_s]["first_place"] += 1
            if is_cc:
                stats[uid_s]["cc_wins"] += 1

        # Win = positive or neutral rating gain
        before = ratings_before.get(uid_s, 1500)
        after = stats[uid_s]["rating"]
        if after >= before:
            stats[uid_s]["wins"] += 1

    save_json(STATS_FILE, stats)

    # Store report
    report_id = str(uuid.uuid4())[:8].upper()
    reports[report_id] = {
        "ordered_ids":   [str(u) for u in ordered_ids],
        "ordered_names": ordered_names,
        "winner_id":     str(winner_id),
        "is_cc":         is_cc,
        "channel_id":    str(channel_id),
        "discord_msg_id": None
    }
    save_json(REPORTS_FILE, reports)

    return report_id


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
# RULES SUMMARY (for .rules command)
# ─────────────────────────────────────────────
RULES_TEXT = """
**⚔️  Competitive Civ 6 — Quick Rules**

**1. Setup**
• All games use BBG + BBG Expanded + BBM
• Settings are voted via the bot before each game
• Gold trading, strategics trading, and military alliances are always OFF
• All game modes (Heroes, Secret Societies, etc.) are disabled by default

**2. Conduct**
• Respect all players — harassment results in removal
• Do not leave without host approval
• No bug abuse or external tools

**3. CC Votes**
• Nominate a player to win — requires the session turn threshold to have passed
• The nominated player cannot vote for themselves
• Secret ballot via DM, 2-minute timer, group decides on tally

**4. Irrel Votes**
• Eligible if: bottom 2 by score OR lost 3/5 of their empire
• The nominated player cannot vote
• Same DM ballot mechanic as CC votes

**5. Victory**
• All victory conditions are enabled
• CC vote result = win for nominated player if group agrees
• Time-limit games go to highest score

**6. Reporting**
• Report results with: `.report @1st @2nd @3rd ...`
• Ratings use Glicko-2, starting at 1500
• Incorrect reports: ask an admin to run `.override <report_id>`

**7. Relobby**
• Requires 66% agreement
• Only for bugs, crashes, or desyncs in the first 10 turns
• Max 2 relobbies per session

Use `.leaderboard` for current standings. Full rulebook is pinned in this channel.
"""


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
# HELPER: early close for DM votes (cc/irrel/scrap/remap)
# ─────────────────────────────────────────────
async def try_early_close(vote_id, dm_msg_ids, voter_ids, notice, kind, target_name, needed=None, turn=None, session=None):
    """Cancel the timer and close the vote early if all players have voted."""
    if vote_id not in active_timed_votes:
        return
    all_voted = all(
        timed_vote_dm_data.get(dm_id, {}).get("voted", False)
        for dm_id in dm_msg_ids.values()
    )
    if not all_voted:
        return

    # Cancel the running timer
    active_timed_votes[vote_id].cancel()
    del active_timed_votes[vote_id]

    yay = nay = 0
    for pid, dm_id in dm_msg_ids.items():
        try:
            voter = await client.fetch_user(pid)
            dm_channel = voter.dm_channel or await voter.create_dm()
            dm_msg = await dm_channel.fetch_message(dm_id)
            for r in dm_msg.reactions:
                if str(r.emoji) == "👍":
                    async for u in r.users():
                        if u.id == pid: yay += 1
                if str(r.emoji) == "👎":
                    async for u in r.users():
                        if u.id == pid: nay += 1
            await dm_msg.edit(content="✅  This vote has closed early — all players voted!")
            await dm_msg.clear_reactions()
            timed_vote_dm_data.pop(dm_id, None)
        except Exception:
            pass

    if kind == "cc":
        result_str = f"🏆  **CC Vote — CLOSED (early)** — concede to **{target_name}**?\n👍 Yay: **{yay}**   👎 Nay: **{nay}**"
    elif kind == "irrel":
        result_str = f"⚪  **Irrel Vote — CLOSED (early)** — is **{target_name}** irrelevant?\n👍 Yay: **{yay}**   👎 Nay: **{nay}**"
    elif kind == "scrap":
        passed = needed and yay >= needed
        result = "✅  **SCRAP PASSED**" if passed else "❌  **Scrap failed**"
        result_str = f"🗑️  **Scrap Vote — CLOSED (early)** (Turn {turn})\n{result} — 👍 Yes: **{yay}**   👎 No: **{nay}**"
    elif kind == "remap":
        passed = yay == len(voter_ids) and nay == 0
        result = "✅  **REMAP PASSED** — relobby the game!" if passed else "❌  **Remap denied**"
        result_str = f"🗺️  **Remap Vote — CLOSED (early)** (Turn {turn})\n{result} — 👍 Agree: **{yay}**   👎 Deny: **{nay}**"
    else:
        result_str = f"Vote closed early. 👍 {yay}  👎 {nay}"

    try:
        await notice.edit(content=result_str)
    except Exception:
        pass

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

    # ── .report @1st [Leader] @2nd [Leader] ... ──
    elif cmd == "report":
        if len(message.mentions) < 2:
            await message.channel.send(
                "❌  Usage: `.report @1st [Leader] @2nd [Leader] ...`\n"
                "Tag players in finishing order. Leader names are optional.\n"
                "Example: `.report @Alice Hammurabi @Bob Gorgo @Carol`"
            )
            return

        raw = message.content[len(PREFIX) + len("report"):].strip()
        raw_ordered_ids = [int(uid) for uid in __import__('re').findall(r'<@!?(\d+)>', raw)]
        mention_lookup  = {m.id: m for m in message.mentions}
        ordered_members = [mention_lookup[uid] for uid in raw_ordered_ids if uid in mention_lookup]
        ordered_ids   = [m.id for m in ordered_members]
        ordered_names = [m.display_name for m in ordered_members]
        winner_id = ordered_ids[0]

        leader_picks = {}
        remaining = raw
        parse_errors = []
        for i, m in enumerate(message.mentions):
            mention_str = m.mention
            alt_str = f"<@!{m.id}>"
            idx = remaining.find(mention_str)
            if idx == -1:
                idx = remaining.find(alt_str)
                if idx != -1:
                    mention_str = alt_str
            if idx == -1:
                continue

            remaining = remaining[idx + len(mention_str):].strip()

            next_mention_idx = len(remaining)
            for nm in message.mentions[i+1:]:
                ni = remaining.find(nm.mention)
                ni2 = remaining.find(f"<@!{nm.id}>")
                if ni != -1:
                    next_mention_idx = min(next_mention_idx, ni)
                if ni2 != -1:
                    next_mention_idx = min(next_mention_idx, ni2)

            leader_text = remaining[:next_mention_idx].strip()

            if leader_text:
                result_type, result_data = match_leader(leader_text, LEADER_INDEX)
                if result_type == "exact":
                    leader_name, civ_name = result_data
                    leader_picks[str(m.id)] = {"leader": leader_name, "civ": civ_name}
                    p = get_player(m.id, m.display_name)
                    if leader_name not in p["leaders"]:
                        p["leaders"][leader_name] = {"games": 0, "wins": 0}
                    p["leaders"][leader_name]["games"] += 1
                    if m.id == winner_id:
                        p["leaders"][leader_name]["wins"] += 1
                elif result_type == "ambiguous":
                    parse_errors.append(
                        f"⚠️ **\"{leader_text}\"** is ambiguous for {m.display_name}. Did you mean:\n"
                        + format_ambiguous(result_data)
                    )
                else:
                    parse_errors.append(
                        f"⚠️ **\"{leader_text}\"** not found for {m.display_name}. Use `.leaders` to check."
                    )

        if parse_errors:
            await message.channel.send("\n".join(parse_errors) + "\n\n⚠️ Match recorded without those leaders.")

        if leader_picks:
            save_json(STATS_FILE, stats)

        is_cc = cid in drafts and hasattr(drafts.get(cid), 'players')
        report_id = process_report(ordered_ids, ordered_names, winner_id, is_cc, cid)

        asyncio.get_event_loop().create_task(
            sync_match_report(report_id, ordered_ids, ordered_names, winner_id, is_cc, stats, leader_picks)
        )

        winner_name = ordered_members[0].display_name
        placement_lines = "\n".join(
            f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else f'{i+1}.'} {m.display_name}"
            for i, m in enumerate(ordered_members)
        )
        reply = f"✅  Result recorded! **{winner_name}** wins. Report ID: `{report_id}`\n{placement_lines}"
        if leader_picks:
            pick_lines = []
            for pid in ordered_ids:
                pid_s = str(pid)
                pname = ordered_names[ordered_ids.index(pid)]
                if pid_s in leader_picks:
                    lp = leader_picks[pid_s]
                    pick_lines.append(f"  • {pname} — **{lp['leader']}** ({lp['civ']})")
                else:
                    pick_lines.append(f"  • {pname}")
            reply += "\n\n🏛️ **Leaders:**\n" + "\n".join(pick_lines)
        await message.channel.send(reply)

        # Post to #reports channel
        reports_channel = client.get_channel(REPORTS_CHANNEL_ID)
        if reports_channel:
            placement_text = "\n".join(
                f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else f'{i+1}.'} {ordered_names[i]}"
                for i in range(len(ordered_names))
            )
            report_msg = await reports_channel.send(
                f"📋  **Match Report** — ID: `{report_id}`\n{placement_text}"
            )
            reports[report_id]["discord_msg_id"] = report_msg.id
            save_json(REPORTS_FILE, reports)

# ── .override <report_id> @1st @2nd ... ────
    elif cmd == "override":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Admin only.")
            return
        parts2 = args.split()
        if not parts2 or not message.mentions:
            await message.channel.send("❌  Usage: `.override <report_id> @1st @2nd @3rd ...`")
            return
        report_id = parts2[0].upper()
        if report_id not in reports:
            await message.channel.send(f"❌  Report ID `{report_id}` not found.")
            return

        # Delete the bad report
        del reports[report_id]
        save_json(REPORTS_FILE, reports)

        # Reset all player ratings and replay every remaining report
        for uid_s in stats:
            stats[uid_s]["rating"] = 1500.0
            stats[uid_s]["rd"] = 350.0
            stats[uid_s]["vol"] = 0.06
            stats[uid_s]["games"] = 0
            stats[uid_s]["wins"] = 0
            stats[uid_s]["cc_wins"] = 0

        sorted_reports = sorted(reports.values(), key=lambda r: r.get("channel_id", ""))
        for r in sorted_reports:
            r_ids = [int(x) for x in r["ordered_ids"]]
            r_names = r["ordered_names"]
            r_data = [get_player(uid, r_names[i]) for i, uid in enumerate(r_ids)]
            for i, uid in enumerate(r_ids):
                p = r_data[i]
                opps = []
                for j, opp_uid in enumerate(r_ids):
                    if i == j:
                        continue
                    score = 1.0 if i < j else 0.0
                    opps.append((r_data[j], score))
                glicko2_update(p, opps)
            for i, uid in enumerate(r_ids):
                uid_s = str(uid)
                stats[uid_s]["games"] += 1
                if i == 0:
                    stats[uid_s]["wins"] += 1
                    if r.get("is_cc"):
                        stats[uid_s]["cc_wins"] += 1

        save_json(STATS_FILE, stats)

        # Now record the corrected result
        raw2 = message.content[len(PREFIX) + len("override"):].strip()
        raw_ordered_ids2 = [int(uid) for uid in __import__('re').findall(r'<@!?(\d+)>', raw2)]
        mention_lookup2  = {m.id: m for m in message.mentions}
        ordered_members2 = [mention_lookup2[uid] for uid in raw_ordered_ids2 if uid in mention_lookup2]
        ordered_ids   = [m.id for m in ordered_members2]
        ordered_names = [m.display_name for m in ordered_members2]
        winner_id     = ordered_ids[0]

        new_id = process_report(ordered_ids, ordered_names, winner_id, False, cid)

        # Edit the original report message in #reports channel
        reports_channel = client.get_channel(REPORTS_CHANNEL_ID)
        old_msg_id = reports.get(report_id, {}).get("discord_msg_id") if report_id in reports else None
        if reports_channel and old_msg_id:
            try:
                old_msg = await reports_channel.fetch_message(old_msg_id)
                new_placement = "\n".join(
                    f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else f'{i+1}.'} {ordered_names[i]}"
                    for i in range(len(ordered_names))
                )
                await old_msg.edit(content=
                    f"📋  **Match Report** — ID: `{new_id}` *(corrected from `{report_id}`)*\n{new_placement}"
                )
                reports[new_id]["discord_msg_id"] = old_msg_id
                save_json(REPORTS_FILE, reports)
            except Exception:
                pass

        await message.channel.send(
            f"✅  Report `{report_id}` overridden and all ratings recalculated.\n"
            f"New report ID: `{new_id}`"
        )
 # ── .resetseason ──────────────────────────
    elif cmd == "resetseason":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Admin only.")
            return

        # Confirmation check
        if args.lower() != "confirm":
            player_count = len(stats)
            report_count = len(reports)
            await message.channel.send(
                f"⚠️ **This will reset ALL ratings and match history.**\n"
                f"• {player_count} players reset to 1500\n"
                f"• {report_count} reports deleted\n\n"
                f"Type `.resetseason confirm` to proceed."
            )
            return

        # Reset all player ratings but keep their names
        for uid_s in stats:
            stats[uid_s]["rating"] = 1500.0
            stats[uid_s]["rd"] = 350.0
            stats[uid_s]["vol"] = 0.06
            stats[uid_s]["games"] = 0
            stats[uid_s]["wins"] = 0
            stats[uid_s]["cc_wins"] = 0
            stats[uid_s]["leaders"] = {}
            if "drops" in stats[uid_s]:
                stats[uid_s]["drops"] = 0

        # Clear all reports
        reports.clear()

        save_json(STATS_FILE, stats)
        save_json(REPORTS_FILE, reports)

        # Sync to website
        await sync_full_stats(stats)

        await message.channel.send(
            f"🔄 **Season reset complete!**\n"
            f"All ratings reset to 1500. Match history cleared.\n"
            f"Website synced."
        )
   # ── .announce <title> | <message> ─────────
    elif cmd == "announce":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Admin only.")
            return
        if "|" not in args:
            await message.channel.send("❌ Usage: `.announce Title Here | Your announcement message here`")
            return

        title, content = args.split("|", 1)
        title = title.strip()
        content = content.strip()

        if not title or not content:
            await message.channel.send("❌ Both title and message are required.\nUsage: `.announce Title | Message`")
            return

        # Check for pin flag
        is_pinned = False
        if content.endswith("--pin"):
            is_pinned = True
            content = content[:-5].strip()

        # Post to Discord channel
        await message.channel.send(
            f"📢 **{title}**\n\n{content}"
        )

        # Push to website
        success = await sync_announcement(title, content, is_pinned)
        if success:
            await message.channel.send("✅ Announcement posted to website.")
        else:
            await message.channel.send("⚠️ Posted in Discord but website sync failed.")
   # ── .sync ────────────────────────────────
    elif cmd == "sync":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Admin only.")
            return
        await message.channel.send("🔄 Syncing all stats to website...")
        success = await sync_full_stats(stats)
        if success:
            await message.channel.send("✅ Website synced!")
        else:
            await message.channel.send("❌ Sync failed. Check bot logs.")
    # ── .leaderboard ───────────────────────────
    elif cmd == "leaderboard":
        if not stats:
            await message.channel.send("📊  No games have been reported yet.")
            return

        sorted_players = sorted(
            stats.items(),
            key=lambda x: x[1].get("rating", 1500),
            reverse=True
        )

        lines = ["📊  **Leaderboard**\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, p) in enumerate(sorted_players):
            medal   = medals[i] if i < 3 else f"**{i+1}.**"
            games   = p.get("games", 0)
            wins    = p.get("wins", 0)
            cc_wins = p.get("cc_wins", 0)
            wr      = f"{round(wins/games*100)}%" if games > 0 else "—"
            rating  = round(p.get("rating", 1500))
            rd      = round(p.get("rd", 350))
            name    = p.get("name", str(uid))

            # Best leader by win rate (min 2 games)
            leaders = p.get("leaders", {})
            best_leader = "—"
            best_wr = 0
            most_played_leader = "—"
            most_played = 0
            for lname, ldata in leaders.items():
                lg, lw = ldata.get("games", 0), ldata.get("wins", 0)
                if lg > most_played:
                    most_played = lg
                    most_played_leader = lname
                if lg >= 2:
                    lwr = lw / lg
                    if lwr > best_wr:
                        best_wr = lwr
                        best_leader = f"{lname} ({round(lwr*100)}%)"

            first_place = p.get("first_place", 0)
            lines.append(
                f"{medal} **{name}** — {rating} ±{rd}\n"
                f"  GP: {games}  W: {wins}  1st: {first_place}  CC: {cc_wins}  WR: {wr}\n"
            )

        # Split into chunks if needed
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 2 > 1900:
                await message.channel.send(chunk)
                chunk = ""
            chunk += line + "\n"
        if chunk:
            await message.channel.send(chunk)

    # ── .rules ─────────────────────────────────
    elif cmd == "rules":
        await message.channel.send(RULES_TEXT)


    # ── .scrap ─────────────────────────────────
    elif cmd == "scrap":
        if cid not in drafts:
            await message.channel.send("❌  No active session found.")
            return
        session = drafts[cid]
        if uid not in session.players:
            await message.channel.send("❌  You must be in the session to call a scrap vote.")
            return

        # Determine threshold based on turn number
        try:
            turn = int(args) if args.strip().isdigit() else None
        except:
            turn = None

        if turn is None:
            await message.channel.send(
                "❌  Please include the current turn number: `.scrap <turn>`\ne.g. `.scrap 45`"
            )
            return

        if turn <= 20:
            threshold_label = "2/3 majority"
            needed = max(1, round(len(session.players) * 2 / 3))
        elif turn <= 50:
            threshold_label = "3/4 majority"
            needed = max(1, round(len(session.players) * 3 / 4))
        elif turn <= 70:
            threshold_label = "all but 1"
            needed = max(1, len(session.players) - 1)
        else:
            threshold_label = "unanimous"
            needed = len(session.players)

        voter_ids = list(session.players)
        notice = await message.channel.send(
            f"🗑️  **Scrap Vote** — called by **{uname}** on turn **{turn}**.\nThreshold: **{threshold_label}** ({needed}/{len(voter_ids)} votes needed).\nBallots sent via DM. ⏱️  2 minutes to vote."
        )

        failed = []
        dm_msg_ids = {}
        for pid in voter_ids:
            try:
                voter = await client.fetch_user(pid)
                dm = await voter.send(
                    f"🗑️  **Secret Scrap Vote** — end the game now? (Turn {turn})\nReact 👍 for Yes (scrap) or 👎 for No. You have **2 minutes**."
                )
                await dm.add_reaction("👍")
                await dm.add_reaction("👎")
                timed_vote_dm_data[dm.id] = {
                    "channel_id": cid, "vote_id": notice.id,
                    "user_id": pid, "kind": "scrap", "voted": False,
                }
                dm_msg_ids[pid] = dm.id
            except discord.Forbidden:
                failed.append(session.player_names.get(pid, str(pid)))

        if failed:
            await message.channel.send(f"⚠️  Could not DM: **{', '.join(failed)}**")

        async def scrap_timeout():
            await asyncio.sleep(120)
            if notice.id not in active_timed_votes:
                return
            del active_timed_votes[notice.id]

            yay = nay = 0
            voted = set()
            for pid, dm_id in dm_msg_ids.items():
                try:
                    voter = await client.fetch_user(pid)
                    dm_ch = voter.dm_channel or await voter.create_dm()
                    dm_msg = await dm_ch.fetch_message(dm_id)
                    for r in dm_msg.reactions:
                        if str(r.emoji) == "👍":
                            async for u in r.users():
                                if u.id == pid: yay += 1; voted.add(pid)
                        if str(r.emoji) == "👎":
                            async for u in r.users():
                                if u.id == pid: nay += 1; voted.add(pid)
                    await dm_msg.edit(content="✅  This scrap vote has closed.")
                    await dm_msg.clear_reactions()
                    timed_vote_dm_data.pop(dm_id, None)
                except Exception:
                    pass

            did_not_vote = [pid for pid in voter_ids if pid not in voted]
            dnv_str = ""
            if did_not_vote:
                names = ", ".join(session.player_names.get(p, str(p)) for p in did_not_vote)
                dnv_str = f"\n⚠️  Did not vote: **{names}**"

            passed = yay >= needed
            result = "✅  **SCRAP PASSED**" if passed else "❌  **Scrap failed**"
            try:
                await notice.edit(content=(
                    f"🗑️  **Scrap Vote — CLOSED** (Turn {turn}, needed {needed})\n{result} — 👍 Yes: **{yay}**   👎 No: **{nay}**{dnv_str}"
                ))
            except Exception:
                await message.channel.send(
                    f"🗑️  **Scrap Vote — CLOSED** (Turn {turn})\n{result} — 👍 Yes: **{yay}**   👎 No: **{nay}**{dnv_str}"
                )

        task = asyncio.create_task(scrap_timeout())
        active_timed_votes[notice.id] = task

    # ── .afk @player ───────────────────────────
    elif cmd == "afk":
        if not message.mentions:
            await message.channel.send("❌  Usage: `.afk @PlayerName`")
            return
        target = message.mentions[0]
        notice = await message.channel.send(
            f"⏳  **AFK Check** — **{target.display_name}** has been flagged as AFK by **{uname}**.\n**{target.mention}** — please respond in this channel within **5 minutes** or the host may kick you.\nGame should be paused now."
        )

        async def afk_timeout():
            await asyncio.sleep(300)
            if notice.id not in active_timed_votes:
                return
            del active_timed_votes[notice.id]
            try:
                await notice.edit(content=(
                    f"⏳  **AFK Check — EXPIRED** — **{target.display_name}** did not respond.\nHost may now kick **{target.mention}** at the start of the next turn.\nA kicked AFK player must be reported as a quitter."
                ))
            except Exception:
                await message.channel.send(
                    f"⏳  AFK timer expired for **{target.display_name}**. "
                    f"Host may kick at the start of the next turn."
                )

        task = asyncio.create_task(afk_timeout())
        active_timed_votes[notice.id] = task

    # ── .cancelafk ─────────────────────────────
    elif cmd == "cancelafk":
        # Allow player or host to cancel an active AFK timer
        if not message.mentions:
            await message.channel.send("❌  Usage: `.cancelafk @PlayerName`")
            return
        target = message.mentions[0]
        cancelled = False
        for msg_id, task in list(active_timed_votes.items()):
            # We can't easily match by target here, so we cancel all AFK notices
            # that mention the target. Best-effort lookup via channel messages.
            try:
                fetched = await message.channel.fetch_message(msg_id)
                if "AFK Check" in fetched.content and target.display_name in fetched.content:
                    task.cancel()
                    del active_timed_votes[msg_id]
                    await fetched.edit(content=f"✅  AFK check for **{target.display_name}** cancelled — they have returned.")
                    cancelled = True
                    break
            except Exception:
                pass
        if not cancelled:
            await message.channel.send(f"ℹ️  No active AFK check found for **{target.display_name}**.")

    # ── .quit @player ──────────────────────────
    elif cmd == "quit":
        if not message.mentions:
            await message.channel.send("❌  Usage: `.quit @PlayerName`")
            return
        target    = message.mentions[0]
        tid       = str(target.id)
        n_drops   = 0

        # Load drop counts from stats
        if tid not in stats:
            get_player(target.id, target.display_name)
        if "drops" not in stats[tid]:
            stats[tid]["drops"] = 0
        stats[tid]["drops"] += 1
        n_drops = stats[tid]["drops"]
        save_json(STATS_FILE, stats)

        # Remove from active session if present
        session = drafts.get(cid)
        if session and target.id in session.players:
            session.players.remove(target.id)
            session.player_count = len(session.players)

        suffix = ""
        if n_drops == 3:
            suffix = (f"\n⚠️  **{target.display_name}** has hit the **3-drop threshold**. Remaining players may vote to remove them from the game by secret majority vote.")
        elif n_drops > 3:
            suffix = f"\n⚠️  **{target.display_name}** has **{n_drops} drops** recorded this game."

        await message.channel.send(
            f"📋  **Quit logged** — **{target.display_name}** has left the game (drop #{n_drops}/3 penalty-free).{suffix}"
        )

    # ── .sub @old @new ─────────────────────────
    elif cmd == "sub":
        if len(message.mentions) < 2:
            await message.channel.send("❌  Usage: `.sub @OldPlayer @NewPlayer`")
            return
        old_player = message.mentions[0]
        new_player = message.mentions[1]
        session = drafts.get(cid)

        if session:
            if old_player.id not in session.players:
                await message.channel.send(f"❌  **{old_player.display_name}** is not in the current session.")
                return
            # Swap in session
            idx = session.players.index(old_player.id)
            session.players[idx] = new_player.id
            session.player_names[new_player.id] = new_player.display_name

            # Transfer assignments if draft has happened
            if old_player.id in session.assignments:
                session.assignments[new_player.id] = session.assignments.pop(old_player.id)
            if old_player.id in session.secret_picks:
                session.secret_picks[new_player.id] = session.secret_picks.pop(old_player.id)

        # Transfer stats record if exists
        old_id = str(old_player.id)
        new_id = str(new_player.id)
        if old_id in stats:
            # Ensure new player has a record
            get_player(new_player.id, new_player.display_name)
        save_json(STATS_FILE, stats)

        await message.channel.send(
            f"🔄  **Sub recorded** — **{old_player.display_name}** has been replaced by **{new_player.display_name}**.\nNote: The subbed-out player must wait **60 minutes** before joining a new game."
        )

    # ── .remap ─────────────────────────────────
    elif cmd == "remap":
        if cid not in drafts:
            await message.channel.send("❌  No active session found.")
            return
        session = drafts[cid]
        if uid not in session.players:
            await message.channel.send("❌  You must be in the session to request a remap.")
            return

        # Parse optional turn number
        try:
            turn = int(args) if args.strip().isdigit() else None
        except:
            turn = None

        if turn is None:
            await message.channel.send(
                "❌  Please include the current turn number: `.remap <turn>`\ne.g. `.remap 7`"
            )
            return

        if turn > 10:
            await message.channel.send(
                f"❌  Remap requests are only valid on or before **turn 10**. "
                f"Current turn is {turn}."
            )
            return

        voter_ids = [pid for pid in session.players if pid != uid]
        notice = await message.channel.send(
            f"🗺️  **Remap Request** — **{uname}** is requesting a remap (turn {turn}).\nThreshold: **Unanimous** ({len(voter_ids)} votes needed).\nBallots sent via DM. ⏱️  2 minutes to vote.\n\n📌  *Automatic remaps apply if: you cannot settle 3 cities within 5 tiles on Pangaea/Highlands/Seven Seas/Lakes, or 2 cities on other maps before Shipbuilding, or if spawn is off-coast/off-fresh-water.*"
        )

        failed = []
        dm_msg_ids = {}
        for pid in voter_ids:
            try:
                voter = await client.fetch_user(pid)
                dm = await voter.send(
                    f"🗺️  **Secret Remap Vote** — **{uname}** wants a remap (turn {turn}).\nReact 👍 to agree or 👎 to deny. **Unanimous** agreement required. 2 minutes."
                )
                await dm.add_reaction("👍")
                await dm.add_reaction("👎")
                timed_vote_dm_data[dm.id] = {
                    "channel_id": cid, "vote_id": notice.id,
                    "user_id": pid, "kind": "remap", "voted": False,
                }
                dm_msg_ids[pid] = dm.id
            except discord.Forbidden:
                failed.append(session.player_names.get(pid, str(pid)))

        if failed:
            await message.channel.send(f"⚠️  Could not DM: **{', '.join(failed)}**")

        async def remap_timeout():
            await asyncio.sleep(120)
            if notice.id not in active_timed_votes:
                return
            del active_timed_votes[notice.id]

            yay = nay = 0
            voted = set()
            for pid, dm_id in dm_msg_ids.items():
                try:
                    voter = await client.fetch_user(pid)
                    dm_ch = voter.dm_channel or await voter.create_dm()
                    dm_msg = await dm_ch.fetch_message(dm_id)
                    for r in dm_msg.reactions:
                        if str(r.emoji) == "👍":
                            async for u in r.users():
                                if u.id == pid: yay += 1; voted.add(pid)
                        if str(r.emoji) == "👎":
                            async for u in r.users():
                                if u.id == pid: nay += 1; voted.add(pid)
                    await dm_msg.edit(content="✅  This remap vote has closed.")
                    await dm_msg.clear_reactions()
                    timed_vote_dm_data.pop(dm_id, None)
                except Exception:
                    pass

            did_not_vote = [pid for pid in voter_ids if pid not in voted]
            dnv_str = ""
            if did_not_vote:
                names = ", ".join(session.player_names.get(p, str(p)) for p in did_not_vote)
                dnv_str = f"\n⚠️  Did not vote: **{names}**"

            passed = yay == len(voter_ids) and nay == 0
            result = "✅  **REMAP PASSED** — relobby the game!" if passed else "❌  **Remap denied**"
            try:
                await notice.edit(content=(
                    f"🗺️  **Remap Vote — CLOSED** (Turn {turn}, unanimous required)\n{result} — 👍 Agree: **{yay}**   👎 Deny: **{nay}**{dnv_str}"
                ))
            except Exception:
                await message.channel.send(
                    f"🗺️  **Remap Vote — CLOSED** (Turn {turn})\n{result} — 👍 Agree: **{yay}**   👎 Deny: **{nay}**{dnv_str}"
                )

        task = asyncio.create_task(remap_timeout())
        active_timed_votes[notice.id] = task


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
            "`.report @1st @2nd ...` — Report a game result in finishing order\n"
            "`.override <id> @1st @2nd ...` — Correct an incorrect report\n"
            "`.leaderboard` — Show the current Glicko-2 standings\n"
            "`.scrap <turn>` — Secret DM vote to scrap the game (turn-based threshold)\n"
            "`.afk @Player` — Start a 5-min AFK countdown for a player\n"
            "`.cancelafk @Player` — Cancel an active AFK check\n"
            "`.quit @Player` — Log a player quit/drop (tracks 3-drop policy)\n"
            "`.sub @Old @New` — Substitute one player for another\n"
            "`.remap <turn>` — Secret DM vote to remap (unanimous, turn ≤10)\n"
            "`.rules` — Post the quick rules summary\n"
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

    # ── DM vote reaction handler (cc/irrel/scrap/remap) ──
    in_secret_draft = any(msg_id in s.secret_dm_msgs for s in drafts.values())
    if msg_id in timed_vote_dm_data and not in_secret_draft:
        entry = timed_vote_dm_data[msg_id]
        if user.id == entry["user_id"] and str(reaction.emoji) in ("👍", "👎"):
            entry["voted"] = True
            vote_id   = entry["vote_id"]
            kind      = entry["kind"]
            # Find all dm_msg_ids for this vote by scanning timed_vote_dm_data
            dm_msg_ids = {
                e["user_id"]: mid
                for mid, e in timed_vote_dm_data.items()
                if e["vote_id"] == vote_id
            }
            voter_ids = list(dm_msg_ids.keys())
            # Fetch the notice message to pass to early close
            try:
                guild_channel = client.get_channel(entry["channel_id"])
                notice = await guild_channel.fetch_message(vote_id)
                await try_early_close(vote_id, dm_msg_ids, voter_ids, notice, kind, "", session=None)
            except Exception:
                pass
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
