# website_sync.py
# ─── WEBSITE SYNC MODULE ────────────────────────────────────────────────────
# Pushes player stats, match results, and leader picks to the Vercel website.
#
# Setup:
#   WEBSITE_SYNC_URL=https://your-site.vercel.app/api/sync
#   BOT_SYNC_SECRET=your-shared-secret-here

import os
import json
import asyncio
import aiohttp

SYNC_URL = os.environ.get("WEBSITE_SYNC_URL", "")
SYNC_SECRET = os.environ.get("BOT_SYNC_SECRET", "")


async def sync_match_report(report_id, ordered_ids, ordered_names, winner_id, is_cc, stats, leader_picks=None):
    """
    Push a match report to the website.
    
    Args:
        report_id: The report ID string
        ordered_ids: List of Discord user IDs in placement order
        ordered_names: List of display names in the same order
        winner_id: Discord user ID of the winner
        is_cc: Whether this was a CC win
        stats: The full stats dictionary
        leader_picks: Dict of {discord_id_str: {"leader": name, "civ": civ}} or None
    """
    if not SYNC_URL or not SYNC_SECRET:
        print("[WebSync] ⚠️ WEBSITE_SYNC_URL or BOT_SYNC_SECRET not set. Skipping sync.")
        return False

    try:
        ordered_players = []
        for i, uid in enumerate(ordered_ids):
            uid_s = str(uid)
            p = stats.get(uid_s, {})
            
            fav_civ = None
            if "leaders" in p and p["leaders"]:
                max_games = 0
                for leader, lstats in p["leaders"].items():
                    if lstats.get("games", 0) > max_games:
                        max_games = lstats["games"]
                        fav_civ = leader

            ordered_players.append({
                "id": uid_s,
                "name": p.get("name", ordered_names[i] if i < len(ordered_names) else f"Player_{uid_s[-4:]}"),
                "rating": p.get("rating", 1500),
                "rd": p.get("rd", 350),
                "games": p.get("games", 0),
                "wins": p.get("wins", 0),
                "cc_wins": p.get("cc_wins", 0),
		"first_place": p.get("first_place", 0),
                "favCiv": fav_civ,
            })

        all_players = {}
        for uid_s, p in stats.items():
            if p.get("games", 0) == 0:
                continue
            all_players[uid_s] = {
                "name": p.get("name", "Unknown"),
                "rating": p.get("rating", 1500),
                "rd": p.get("rd", 350),
                "games": p.get("games", 0),
                "wins": p.get("wins", 0),
                "cc_wins": p.get("cc_wins", 0),
                "first_place": p.get("first_place", 0),
                "firstPlace": p.get("first_place", 0),
                "leaders": p.get("leaders", {}),
            }

        payload = {
            "type": "match_report",
            "data": {
                "reportId": report_id,
                "orderedPlayers": ordered_players,
                "winnerId": str(winner_id),
                "isCC": is_cc,
                "allPlayers": all_players,
                "leaderPicks": leader_picks or {},
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                SYNC_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {SYNC_SECRET}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                result = await resp.json()
                if resp.status == 200:
                    print(f"[WebSync] ✅ Match {report_id} synced to website.")
                    return True
                else:
                    print(f"[WebSync] ❌ Sync failed ({resp.status}): {result}")
                    return False

    except asyncio.TimeoutError:
        print("[WebSync] ❌ Sync timed out (15s).")
        return False
    except Exception as e:
        print(f"[WebSync] ❌ Sync error: {e}")
        return False


async def sync_full_stats(stats):
    """Push ALL player stats to the website."""
    if not SYNC_URL or not SYNC_SECRET:
        print("[WebSync] ⚠️ WEBSITE_SYNC_URL or BOT_SYNC_SECRET not set. Skipping sync.")
        return False

    try:
        all_players = {}
        for uid_s, p in stats.items():
            if p.get("games", 0) == 0:
                continue
            all_players[uid_s] = {
                "name": p.get("name", "Unknown"),
                "rating": p.get("rating", 1500),
                "rd": p.get("rd", 350),
                "games": p.get("games", 0),
                "wins": p.get("wins", 0),
                "cc_wins": p.get("cc_wins", 0),
                "first_place": p.get("first_place", 0),
                "firstPlace": p.get("first_place", 0),
                "leaders": p.get("leaders", {}),
            }

        payload = {
            "type": "full_sync",
            "data": { "players": all_players }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                SYNC_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {SYNC_SECRET}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                result = await resp.json()
                if resp.status == 200:
                    print(f"[WebSync] ✅ Full sync complete: {result.get('playersUpdated', 0)} players.")
                    return True
                else:
                    print(f"[WebSync] ❌ Full sync failed ({resp.status}): {result}")
                    return False

    except Exception as e:
        print(f"[WebSync] ❌ Full sync error: {e}")
        return False


async def sync_announcement(title, content, is_pinned=False):
    """Push an announcement to the website."""
    if not SYNC_URL or not SYNC_SECRET:
        print("[WebSync] ⚠️ Not configured. Skipping.")
        return False

    base_url = SYNC_URL.rsplit("/api/", 1)[0]
    announce_url = f"{base_url}/api/announcements"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                announce_url,
                json={"title": title, "content": content, "isPinned": is_pinned},
                headers={
                    "Authorization": f"Bearer {SYNC_SECRET}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    print(f"[WebSync] ✅ Announcement posted: {title}")
                    return True
                else:
                    result = await resp.json()
                    print(f"[WebSync] ❌ Announcement failed ({resp.status}): {result}")
                    return False
    except Exception as e:
        print(f"[WebSync] ❌ Announcement error: {e}")
        return False
