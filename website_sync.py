# website_sync.py
# ─── WEBSITE SYNC MODULE ────────────────────────────────────────────────────
# Add this file to the same directory as civ6_draft_bot.py
# It pushes player stats and match results to the Vercel website API.
#
# Setup:
#   1. Add to Railway environment variables:
#      WEBSITE_SYNC_URL=https://your-site.vercel.app/api/sync
#      BOT_SYNC_SECRET=your-shared-secret-here
#
#   2. Add to Vercel environment variables:
#      BOT_SYNC_SECRET=your-shared-secret-here  (same value)

import os
import json
import asyncio
import aiohttp

SYNC_URL = os.environ.get("WEBSITE_SYNC_URL", "")
SYNC_SECRET = os.environ.get("BOT_SYNC_SECRET", "")


async def sync_match_report(report_id, ordered_ids, ordered_names, winner_id, is_cc, stats):
    """
    Call this after every process_report() to push the match to the website.
    
    Args:
        report_id: The report ID string from process_report()
        ordered_ids: List of Discord user IDs in placement order (1st to last)
        ordered_names: List of display names in the same order
        winner_id: Discord user ID of the winner (1st place)
        is_cc: Whether this was a CC (concession) win
        stats: The full stats dictionary from the bot
    """
    if not SYNC_URL or not SYNC_SECRET:
        print("[WebSync] ⚠️ WEBSITE_SYNC_URL or BOT_SYNC_SECRET not set. Skipping sync.")
        return False

    try:
        # Build player data for players in this match
        ordered_players = []
        for i, uid in enumerate(ordered_ids):
            uid_s = str(uid)
            p = stats.get(uid_s, {})
            
            # Figure out most-played leader
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
                "favCiv": fav_civ,
            })

        # Also send ALL player stats for a full picture
        all_players = {}
        for uid_s, p in stats.items():
            all_players[uid_s] = {
                "name": p.get("name", "Unknown"),
                "rating": p.get("rating", 1500),
                "rd": p.get("rd", 350),
                "games": p.get("games", 0),
                "wins": p.get("wins", 0),
                "cc_wins": p.get("cc_wins", 0),
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
    """
    Push ALL player stats to the website. Use for daily reconciliation
    or manual .sync command.
    """
    if not SYNC_URL or not SYNC_SECRET:
        print("[WebSync] ⚠️ WEBSITE_SYNC_URL or BOT_SYNC_SECRET not set. Skipping sync.")
        return False

    try:
        all_players = {}
        for uid_s, p in stats.items():
            all_players[uid_s] = {
                "name": p.get("name", "Unknown"),
                "rating": p.get("rating", 1500),
                "rd": p.get("rd", 350),
                "games": p.get("games", 0),
                "wins": p.get("wins", 0),
                "cc_wins": p.get("cc_wins", 0),
                "leaders": p.get("leaders", {}),
            }

        payload = {
            "type": "full_sync",
            "data": {
                "players": all_players,
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
