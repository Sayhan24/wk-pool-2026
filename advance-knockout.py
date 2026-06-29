#!/usr/bin/env python3
"""
WK 2026 - Knockout-progressie automatisch bijwerken.
Leest uitslagen uit Firebase, bepaalt winnaars per ronde,
en vult de volgende ronde in met de juiste teams.

Gebruik: python advance-knockout.py [--push]
  --push   Schrijf de bijgewerkte knockoutDefs naar Firebase
  --check  Alleen checken, geen wijzigingen (default)
"""

import json, sys, subprocess

FIREBASE_DB = "https://wkpool-2026-default-rtdb.europe-west1.firebasedatabase.app"
POOL_CODE = "PY9MPU"

# --- Knockout bracket progression (2026 World Cup) ---
# R32 winners advance to R16 according to this tree:
R32_TO_R16 = {
    # R16_0: winner R32_0 vs winner R32_1
    "R16_0": ["R32_0", "R32_1"],
    "R16_1": ["R32_2", "R32_3"],
    "R16_2": ["R32_4", "R32_5"],
    "R16_3": ["R32_6", "R32_7"],
    "R16_4": ["R32_8", "R32_9"],
    "R16_5": ["R32_10", "R32_11"],
    "R16_6": ["R32_12", "R32_13"],
    "R16_7": ["R32_14", "R32_15"],
}

R16_TO_QF = {
    "QF_0": ["R16_0", "R16_1"],
    "QF_1": ["R16_2", "R16_3"],
    "QF_2": ["R16_4", "R16_5"],
    "QF_3": ["R16_6", "R16_7"],
}

QF_TO_SF = {
    "SF_0": ["QF_0", "QF_1"],
    "SF_1": ["QF_2", "QF_3"],
}

SF_TO_FINAL = {
    "FI_0": ["SF_0", "SF_1"],  # winners
    "TP_0": ["SF_0", "SF_1"],  # losers
}

# Round order from first to last
ROUND_ORDER = ["R32", "R16", "QF", "SF", "TP", "FI"]


def fetch_firebase(path):
    """Fetch data from Firebase REST API."""
    url = f"{FIREBASE_DB}/{path}.json"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout) or {}
    except:
        return {}


def get_winner(home_team, away_team, result_str):
    """Determine winner from a result string like '2-1'."""
    if not result_str:
        return None
    try:
        h, a = map(int, result_str.split("-"))
        if h > a:
            return home_team
        elif a > h:
            return away_team
        # Draw: in knockout, this shouldn't normally happen
        # but if it does, assume home wins (or we could look at extra time)
        return None
    except:
        return None


def get_loser(home_team, away_team, result_str):
    """Determine loser from a result string."""
    winner = get_winner(home_team, away_team, result_str)
    if winner is None:
        return None
    return away_team if winner == home_team else home_team


def process_knockout():
    """Main logic: fetch data, advance rounds, output updates."""
    print("=" * 60)
    print("WK 2026 - Knockout Progressie")
    print("=" * 60)

    # Fetch data
    local_only = "--local" in sys.argv

    if local_only:
        print("\n[1] Lezen lokale bestanden (--local)...")
        try:
            with open("wk-knockout-schedule.json", "r") as f:
                knockout_defs = json.load(f)
        except:
            knockout_defs = {}
        results = fetch_firebase(f"pools/{POOL_CODE}/results")
        print(f"  knockoutDefs lokaal geladen, results uit Firebase")
    else:
        print("\n[1] Ophalen knockoutDefs en results uit Firebase...")
        pool_data = fetch_firebase(f"pools/{POOL_CODE}")
        knockout_defs = pool_data.get("knockoutDefs", {})
        results = pool_data.get("results", {})

    if not knockout_defs:
        print("  FOUT: Geen knockoutDefs gevonden in Firebase!")
        print("  Voer eerst: python setup-knockout.py --push")
        return None

    print(f"  Results gevonden: {len(results)} uitslagen")

    # Check which rounds are defined and which are complete
    print("\n[2] Status per ronde:")
    updates = {}  # {round_id: {match_key: {home, away}}}
    all_changes = []

    for round_id in ROUND_ORDER:
        round_matches = knockout_defs.get(round_id, {})
        if not round_matches:
            continue

        # Handle both array (from REST API) and dict (from SDK/local)
        if isinstance(round_matches, list):
            match_items = [(str(i), m) for i, m in enumerate(round_matches)]
        else:
            match_items = list(round_matches.items())

        total = len(match_items)
        completed = 0
        winners = {}

        for match_key, match_def in match_items:
            if not isinstance(match_def, dict):
                continue
            home = match_def.get("home", "")
            away = match_def.get("away", "")
            if not home or not away:
                continue

            result_key = f"{round_id}_{match_key}"
            result = results.get(result_key, "")
            if result:
                completed += 1
                winner = get_winner(home, away, result)
                loser = get_loser(home, away, result)
                if winner:
                    winners[match_key] = {"winner": winner, "loser": loser}

        status = "COMPLEET" if completed == total else f"{completed}/{total}"
        print(f"  {round_id}: {status}")

        # If round is complete, determine next round matchups
        if completed == total and round_id in ["R32", "R16", "QF", "SF"]:
            next_round_map = {
                "R32": ("R16", R32_TO_R16),
                "R16": ("QF", R16_TO_QF),
                "QF": ("SF", QF_TO_SF),
                "SF": ("FI", SF_TO_FINAL),
            }

            if round_id in next_round_map:
                next_round, mapping = next_round_map[round_id]

                # For SF → FI + TP
                if round_id == "SF":
                    fi_updates = {}
                    tp_updates = {}

                    for target_key, sources in SF_TO_FINAL.items():
                        if target_key.startswith("FI_"):
                            source_keys = [f"SF_{s.split('_')[1]}" for s in sources]
                            w1 = winners.get(source_keys[0], {}).get("winner")
                            w2 = winners.get(source_keys[1], {}).get("winner")
                            if w1 and w2:
                                fi_updates[target_key] = {"home": w1, "away": w2}
                            else:
                                print(f"  !! Kan {target_key} niet vullen: winnaars onbekend")

                        elif target_key.startswith("TP_"):
                            source_keys = [f"SF_{s.split('_')[1]}" for s in sources]
                            l1 = winners.get(source_keys[0], {}).get("loser")
                            l2 = winners.get(source_keys[1], {}).get("loser")
                            if l1 and l2:
                                tp_updates[target_key] = {"home": l1, "away": l2}
                            else:
                                print(f"  !! Kan {target_key} niet vullen: verliezers onbekend")

                    if fi_updates or tp_updates:
                        updates.setdefault("FI", {}).update(fi_updates)
                        updates.setdefault("TP", {}).update(tp_updates)

                else:
                    round_updates = {}
                    for target_key, source_keys in mapping.items():
                        winners_list = []
                        for sk in source_keys:
                            w = winners.get(sk, {}).get("winner")
                            if w:
                                winners_list.append(w)

                        if len(winners_list) == 2:
                            round_updates[target_key] = {
                                "home": winners_list[0],
                                "away": winners_list[1]
                            }
                        else:
                            print(f"  !! Kan {target_key} niet vullen: {len(winners_list)}/2 winnaars bekend ({winners_list})")

                    if round_updates:
                        updates.setdefault(next_round, {}).update(round_updates)

    # Print proposed updates
    if not updates:
        print("\n[3] Geen nieuwe ronden om te vullen (nog geen complete ronde).")
        return None

    print("\n[3] Nieuwe wedstrijden om toe te voegen:")
    for round_id in ["R16", "QF", "SF", "TP", "FI"]:
        if round_id in updates:
            for key, match in sorted(updates[round_id].items()):
                print(f"  {round_id}_{key}: {match['home']} vs {match['away']}")

    return updates


def push_updates(updates):
    """Write updates to Firebase knockoutDefs using anonymous auth."""
    from firebase_helper import firebase_get, firebase_put

    print("\n  Pushen naar Firebase...")

    # Fetch current knockoutDefs
    current = firebase_get(f"pools/{POOL_CODE}/knockoutDefs")

    # Merge updates (handle both array and dict formats)
    for round_id, round_updates in updates.items():
        if round_id not in current:
            current[round_id] = {}
        elif isinstance(current[round_id], list):
            # Convert array to dict for merging
            current[round_id] = {str(i): m for i, m in enumerate(current[round_id])}
        for key, match in round_updates.items():
            current[round_id][key] = match

    if firebase_put(f"/pools/{POOL_CODE}/knockoutDefs", current):
        print(f"  ✅ KnockoutDefs bijgewerkt in Firebase!")
    else:
        print(f"  ❌ Pushen mislukt. Gebruik console-advance.js als fallback.")


def generate_console_snippet(updates):
    """Generate browser console snippet as fallback."""
    lines = [
        "// === KOPIEER DIT EN PLAK IN DE BROWSER CONSOLE VAN DE WK POOL APP ===",
        "// Werkt de knockout-bracket bij naar de volgende ronde",
        "",
    ]
    for round_id in ["R16", "QF", "SF", "TP", "FI"]:
        if round_id in updates:
            for key, match in sorted(updates[round_id].items()):
                home = match["home"]
                away = match["away"]
                path = f"pools/{POOL_CODE}/knockoutDefs/{round_id}/{key}"
                data = json.dumps({"home": home, "away": away})
                lines.append(f"db.ref('{path}').set({data});")
                lines.append(f"console.log('{round_id}_{key}: {home} vs {away}');")

    lines.append("console.log('✅ Knockout-bracket bijgewerkt! Herlaad de pagina.');")
    return "\n".join(lines)


if __name__ == "__main__":
    updates = process_knockout()

    if updates is None:
        sys.exit(0)

    if "--push" in sys.argv:
        push_updates(updates)
    else:
        print("\n[4] Gebruik --push om naar Firebase te schrijven:")
        print("  python advance-knockout.py --push")
        print("  Of plak de console-snippet in je browser (F12 -> Console).")

        snippet = generate_console_snippet(updates)
        with open("console-advance.js", "w", encoding="utf-8") as f:
            f.write(snippet)
        print("\n  Console snippet opgeslagen in: console-advance.js")
