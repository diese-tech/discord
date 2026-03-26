# leader_match.py
# ─── LEADER NAME MATCHING ───────────────────────────────────────────────────
# Fuzzy matching for leader names with ambiguity detection.
# Place this file next to civ6_draft_bot.py

def build_leader_index(all_leaders):
    """
    Build search indexes from the ALL_LEADERS list.
    all_leaders: list of (leader_name, civ_name) tuples
    """
    index = {
        "exact": {},       # lowercase full name -> (leader, civ)
        "first_name": {},  # lowercase first name -> [(leader, civ), ...]
        "last_name": {},   # lowercase last name -> [(leader, civ), ...]
        "keywords": {},    # any significant word -> [(leader, civ), ...]
        "parenthetical": {},  # text inside parens -> [(leader, civ), ...]
    }

    for leader, civ in all_leaders:
        lower = leader.lower()
        entry = (leader, civ)

        # Exact full name
        index["exact"][lower] = entry

        # Split name parts
        # Handle parenthetical variants like "Teddy Roosevelt (Bull Moose)"
        base_name = leader.split("(")[0].strip()
        paren_part = ""
        if "(" in leader and ")" in leader:
            paren_part = leader.split("(")[1].split(")")[0].strip()

        parts = base_name.split()

        # First name
        if parts:
            fn = parts[0].lower()
            index["first_name"].setdefault(fn, []).append(entry)

        # Last name (if multi-word)
        if len(parts) > 1:
            ln = parts[-1].lower()
            index["last_name"].setdefault(ln, []).append(entry)

        # All name parts as keywords
        for part in parts:
            kw = part.lower()
            if len(kw) > 2:  # skip tiny words like "de", "II"
                index["keywords"].setdefault(kw, []).append(entry)

        # Parenthetical variant
        if paren_part:
            index["parenthetical"][paren_part.lower()] = entry
            # Also index individual words in parens
            for word in paren_part.split():
                kw = word.lower()
                if len(kw) > 2:
                    index["keywords"].setdefault(kw, []).append(entry)

        # Civ name as keyword
        civ_lower = civ.lower()
        index["keywords"].setdefault(civ_lower, []).append(entry)

    return index


def match_leader(query, leader_index):
    """
    Match a query string to a leader.
    
    Returns:
        ("exact", (leader, civ))     - single match found
        ("ambiguous", [(leader, civ), ...])  - multiple possible matches
        ("none", [])                 - no match found
    """
    q = query.strip().lower()
    if not q:
        return ("none", [])

    # 1. Exact full name match
    if q in leader_index["exact"]:
        return ("exact", leader_index["exact"][q])

    # 2. Exact parenthetical match (e.g. "bull moose", "vizier", "rough rider")
    if q in leader_index["parenthetical"]:
        return ("exact", leader_index["parenthetical"][q])

    # 3. Check if query matches "CivName LeaderName" pattern (e.g. "china kublai khan")
    for full_name, entry in leader_index["exact"].items():
        civ_leader = f"{entry[1].lower()} {entry[0].lower()}"
        if q == civ_leader or q == full_name:
            return ("exact", entry)

    # 4. Multi-word partial: check if all query words appear in a leader's full string
    query_words = q.split()
    if len(query_words) >= 2:
        candidates = []
        for full_name, entry in leader_index["exact"].items():
            full_str = f"{entry[1]} {entry[0]}".lower()
            if all(w in full_str for w in query_words):
                candidates.append(entry)
        if len(candidates) == 1:
            return ("exact", candidates[0])
        if len(candidates) > 1:
            return ("ambiguous", candidates)

    # 5. Single word: try first name, last name, keyword
    if len(query_words) == 1:
        word = query_words[0]

        # Check first name
        first_matches = leader_index["first_name"].get(word, [])
        if len(first_matches) == 1:
            return ("exact", first_matches[0])

        # Check last name
        last_matches = leader_index["last_name"].get(word, [])
        if len(last_matches) == 1:
            return ("exact", last_matches[0])

        # Check keywords
        kw_matches = leader_index["keywords"].get(word, [])
        if len(kw_matches) == 1:
            return ("exact", kw_matches[0])

        # Combine all partial matches, deduplicate
        all_matches = {}
        for entry in first_matches + last_matches + kw_matches:
            all_matches[entry[0]] = entry
        unique = list(all_matches.values())

        if len(unique) == 1:
            return ("exact", unique[0])
        if len(unique) > 1:
            return ("ambiguous", unique)

    # 6. Substring match as last resort
    candidates = []
    for full_name, entry in leader_index["exact"].items():
        if q in full_name or q in entry[1].lower():
            candidates.append(entry)
    
    if len(candidates) == 1:
        return ("exact", candidates[0])
    if len(candidates) > 1:
        return ("ambiguous", candidates)

    return ("none", [])


def format_ambiguous(matches):
    """Format ambiguous matches into a readable Discord message."""
    lines = [f"  • **{leader}** ({civ})" for leader, civ in matches[:8]]
    return "\n".join(lines)
