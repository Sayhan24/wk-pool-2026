#!/usr/bin/env python3
"""
WK 2026 - Groepstanden + Knockout-bracket bepalen en naar Firebase pushen.
Gebruik: python setup-knockout.py [--push]
  --push   Schrijf de knockoutDefs direct naar Firebase
"""

import json, sys, os

# --- Config ---
FIREBASE_DB = "https://wkpool-2026-default-rtdb.europe-west1.firebasedatabase.app"
POOL_CODE = "PY9MPU"
MATCH_SCHEDULE_JSON = "wk-knockout-schedule.json"

RESULTS = {
    "A_0":"2-0","A_1":"1-0","A_2":"3-0","A_3":"1-0","A_4":"1-1","A_5":"2-1",
    "B_0":"1-1","B_1":"6-0","B_2":"1-2","B_3":"3-1","B_4":"1-4","B_5":"1-1",
    "C_0":"3-0","C_1":"1-1","C_2":"3-0","C_3":"2-4","C_4":"0-1","C_5":"1-0",
    "D_0":"2-0","D_1":"4-1","D_2":"2-3","D_3":"0-0","D_4":"2-0","D_5":"1-0",
    "E_0":"1-2","E_1":"7-1","E_2":"2-1","E_3":"0-0","E_4":"0-1","E_5":"0-2",
    "F_0":"2-2","F_1":"1-1","F_2":"4-0","F_3":"5-1","F_4":"3-1","F_5":"5-1",
    "G_0":"1-1","G_1":"0-0","G_2":"5-1","G_3":"1-1","G_4":"3-1","G_5":"2-2",
    "H_0":"1-0","H_1":"4-0","H_2":"0-0","H_3":"1-1","H_4":"2-2","H_5":"0-0",
    "I_0":"3-1","I_1":"4-1","I_2":"3-0","I_3":"2-3","I_4":"5-0","I_5":"4-1",
    "J_0":"3-0","J_1":"2-0","J_2":"3-1","J_3":"3-3","J_4":"2-1","J_5":"3-1",
    "K_0":"0-0","K_1":"1-1","K_2":"5-0","K_3":"1-0","K_4":"3-1","K_5":"3-1",
    "L_0":"4-2","L_1":"0-0","L_2":"2-0","L_3":"2-1","L_4":"1-0","L_5":"1-0"
}

GROUPS = {
    "A": ["Mexico","South Africa","South Korea","Czechia"],
    "B": ["Canada","Bosnia and Herzegovina","Qatar","Switzerland"],
    "C": ["Brazil","Haiti","Morocco","Scotland"],
    "D": ["USA","Australia","Paraguay","Turkiye"],
    "E": ["Germany","Ecuador","Curacao","Ivory Coast"],
    "F": ["Japan","Netherlands","Sweden","Tunisia"],
    "G": ["Belgium","Egypt","Iran","New Zealand"],
    "H": ["Spain","Uruguay","Saudi Arabia","Cape Verde"],
    "I": ["France","Senegal","Norway","Iraq"],
    "J": ["Argentina","Algeria","Austria","Jordan"],
    "K": ["Portugal","Colombia","DR Congo","Uzbekistan"],
    "L": ["England","Croatia","Ghana","Panama"]
}

# Official 2026 World Cup R32 bracket mapping (based on FIFA match schedule)
# Each slot: (home_position, away_position, match_desc)
# 3rd place slots specify which groups the 3rd place team can come from
R32_BRACKET = [
    # Match 0-7: Left/top half
    (0, "group_winner", "A", "best_third_cdfh", "1A vs best 3e C/D/F/H"),
    (1, "group_winner", "B", "best_third_aefi", "1B vs best 3e A/E/F/I"),
    (2, "group_winner", "C", "best_third_abf", "1C vs best 3e A/B/F"),
    (3, "group_winner", "D", "best_third_beil", "1D vs best 3e B/E/I/L"),
    (4, "runner_up", "A", "runner_up", "B", "2A vs 2B"),
    (5, "group_winner", "F", "runner_up", "C", "1F vs 2C"),
    (6, "group_winner", "E", "runner_up", "D", "1E vs 2D"),
    (7, "runner_up", "F", "runner_up", "E", "2F vs 2E"),

    # Match 8-15: Right/bottom half
    (8, "group_winner", "G", "best_third_ijkl", "1G vs best 3e I/J/K/L"),
    (9, "group_winner", "H", "best_third_cghj", "1H vs best 3e C/G/H/J"),
    (10, "group_winner", "I", "best_third_ghkl", "1I vs best 3e G/H/K/L"),
    (11, "group_winner", "J", "best_third_adhl", "1J vs best 3e A/D/H/L"),
    (12, "runner_up", "G", "runner_up", "H", "2G vs 2H"),
    (13, "group_winner", "L", "runner_up", "I", "1L vs 2I"),
    (14, "group_winner", "K", "runner_up", "J", "1K vs 2J"),
    (15, "runner_up", "K", "runner_up", "L", "2K vs 2L"),
]


def get_matches(teams):
    m = []
    for i in range(len(teams)):
        for j in range(i+1, len(teams)):
            m.append((teams[i], teams[j]))
    return m


def calculate_standings():
    all_standings = {}
    all_third_place = []

    for letter, teams in GROUPS.items():
        stats = {t: {"pts": 0, "gf": 0, "ga": 0, "gd": 0} for t in teams}
        matches = get_matches(teams)

        for i, (home, away) in enumerate(matches):
            key = f"{letter}_{i}"
            result = RESULTS.get(key, "?-?")
            try:
                hs, aws = map(int, result.split("-"))
                stats[home]["gf"] += hs
                stats[home]["ga"] += aws
                stats[away]["gf"] += aws
                stats[away]["ga"] += hs
                if hs > aws:
                    stats[home]["pts"] += 3
                elif aws > hs:
                    stats[away]["pts"] += 3
                else:
                    stats[home]["pts"] += 1
                    stats[away]["pts"] += 1
            except:
                pass

        for t in teams:
            stats[t]["gd"] = stats[t]["gf"] - stats[t]["ga"]

        sorted_teams = sorted(teams, key=lambda t: (
            stats[t]["pts"], stats[t]["gd"], stats[t]["gf"]
        ), reverse=True)

        standing = []
        for pos, team in enumerate(sorted_teams):
            s = stats[team]
            standing.append({"team": team, "pos": pos+1, "pts": s["pts"], "gd": s["gd"], "gf": s["gf"], "ga": s["ga"]})

        all_standings[letter] = standing
        third = standing[2]
        all_third_place.append({
            "team": third["team"], "group": letter,
            "pts": third["pts"], "gd": third["gd"], "gf": third["gf"], "ga": third["ga"]
        })

    # Best 8 third-place teams
    third_sorted = sorted(all_third_place, key=lambda x: (x["pts"], x["gd"], x["gf"]), reverse=True)
    best_thirds = {t["group"]: t for t in third_sorted[:8]}

    return all_standings, best_thirds


def pick_best_third(best_thirds, group_list):
    """Pick the best third-place team from the given groups (that hasn't been picked yet)."""
    candidates = []
    for g in group_list:
        if g in best_thirds:
            candidates.append(best_thirds[g])
    if not candidates:
        return None
    # Sort by pts, gd, gf
    candidates.sort(key=lambda x: (x["pts"], x["gd"], x["gf"]), reverse=True)
    return candidates[0]


def build_knockout_defs(standings, best_thirds):
    """Build knockout match definitions from standings."""
    knockout_defs = {"R32": {}}

    # Make a mutable copy of best_thirds so we can remove picked teams
    available_thirds = dict(best_thirds)

    for match_idx, slot in enumerate(R32_BRACKET):
        home_team = None
        away_team = None
        idx, home_type, home_group = slot[0], slot[1], slot[2]

        # Determine home team
        if home_type == "group_winner":
            home_team = standings[home_group][0]["team"]
        elif home_type == "runner_up":
            home_team = standings[home_group][1]["team"]

        # Determine away team
        away_type = slot[3]
        if away_type == "runner_up":
            away_group = slot[4]
            away_team = standings[away_group][1]["team"]
        else:
            # best_third_XXXX
            third_groups = {
                "best_third_cdfh": ["C","D","F","H"],
                "best_third_aefi": ["A","E","F","I"],
                "best_third_abf": ["A","B","F"],
                "best_third_beil": ["B","E","I","L"],
                "best_third_ijkl": ["I","J","K","L"],
                "best_third_cghj": ["C","G","H","J"],
                "best_third_ghkl": ["G","H","K","L"],
                "best_third_adhl": ["A","D","H","L"],
            }
            groups = third_groups.get(away_type, [])
            picked = pick_best_third(available_thirds, groups)

            # Fallback: if no third-place teams left from specified groups,
            # pick best remaining third-place team (avoid same group as home_team)
            if not picked and available_thirds:
                home_group_letter = None
                for g, teams in GROUPS.items():
                    if home_team in teams:
                        home_group_letter = g
                        break
                candidates = [(g, t) for g, t in available_thirds.items() if g != home_group_letter]
                if candidates:
                    candidates.sort(key=lambda x: (x[1]["pts"], x[1]["gd"], x[1]["gf"]), reverse=True)
                    picked = candidates[0][1]

            if picked:
                away_team = picked["team"]
                del available_thirds[picked["group"]]

        if home_team and away_team:
            knockout_defs["R32"][str(match_idx)] = {"home": home_team, "away": away_team}

    # Empty KO rounds for later filling
    knockout_defs["R16"] = {}
    knockout_defs["QF"] = {}
    knockout_defs["SF"] = {}
    knockout_defs["TP"] = {}
    knockout_defs["FI"] = {}

    return knockout_defs


def print_bracket(knockout_defs):
    print("\n" + "=" * 70)
    print("R32 - RONDE VAN 32")
    print("=" * 70)
    r32 = knockout_defs["R32"]
    for i in sorted(r32.keys(), key=int):
        m = r32[i]
        print(f"  Wedstrijd {int(i)+1}: {m['home']} vs {m['away']}")

    print(f"\n{len(r32)} van de 16 wedstrijden ingevuld")
    if len(r32) < 16:
        print("NB: Sommige wedstrijden konden niet worden ingevuld (teams niet in bracket-mapping)")


def push_to_firebase(knockout_defs):
    """Write knockoutDefs to Firebase using curl."""
    import subprocess
    url = f"{FIREBASE_DB}/pools/{POOL_CODE}/knockoutDefs.json"
    data = json.dumps(knockout_defs)
    result = subprocess.run([
        "curl", "-s", "-X", "PUT", url,
        "-d", data,
        "-H", "Content-Type: application/json"
    ], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"\nKnockout-definities gepusht naar Firebase pool '{POOL_CODE}'")
        print(f"Response: {result.stdout.strip()}")
    else:
        print(f"\nFout bij pushen naar Firebase: {result.stderr}")


if __name__ == "__main__":
    print("WK 2026 - Knockout-bracket genereren...")
    standings, best_thirds = calculate_standings()

    # Print standings summary
    print("\nGroepswinnaars:")
    for g in sorted(GROUPS.keys()):
        print(f"  Groep {g}: {standings[g][0]['team']} ({standings[g][0]['pts']}pt)")
    print("\nTweede plaatsen:")
    for g in sorted(GROUPS.keys()):
        print(f"  Groep {g}: {standings[g][1]['team']} ({standings[g][1]['pts']}pt)")
    print("\nBeste derde plaatsen:")
    for g, t in sorted(best_thirds.items()):
        print(f"  Groep {g}: {t['team']} ({t['pts']}pt, GD {t['gd']})")

    knockout_defs = build_knockout_defs(standings, best_thirds)
    print_bracket(knockout_defs)

    # Save locally
    with open(MATCH_SCHEDULE_JSON, "w", encoding="utf-8") as f:
        json.dump(knockout_defs, f, indent=2, ensure_ascii=False)
    print(f"\nKnockout-definities opgeslagen in: {MATCH_SCHEDULE_JSON}")

    if "--push" in sys.argv:
        push_to_firebase(knockout_defs)
