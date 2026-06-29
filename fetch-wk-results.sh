#!/bin/bash
# WK Pool 2026 - Uitslagen ophalen en naar Firebase sturen
# Gebruik: bash fetch-wk-results.sh <POOL_CODE> <API_KEY>
#
# Haalt uitslagen op van football-data.org voor groepswedstrijden EN knockout-wedstrijden.
# Draai dit na elke speeldag of knockout-ronde.

POOL_CODE="${1:-PY9MPU}"
API_KEY="${2:-147ac635bed041fd9732f7336ceb3fac}"
DB_URL="https://wkpool-2026-default-rtdb.europe-west1.firebasedatabase.app"

echo "=== WK Pool 2026 - Uitslagen ophalen ==="
echo "Pool: $POOL_CODE"
echo ""

# --- 1. Haal bestaande knockoutDefs op uit Firebase ---
KODEFS=$(curl -s "${DB_URL}/pools/${POOL_CODE}/knockoutDefs.json")
echo "Knockout-definities opgehaald."

# --- 2. Haal afgelopen wedstrijden op ---
echo "Wedstrijden ophalen van football-data.org..."
MATCHES=$(curl -s -H "X-Auth-Token: $API_KEY" \
  "https://api.football-data.org/v4/competitions/WC/matches?status=FINISHED")

COUNT=$(echo "$MATCHES" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('resultSet',{}).get('count',0))" 2>/dev/null || echo "0")
echo "Aantal afgelopen wedstrijden: $COUNT"

if [ "$COUNT" = "0" ]; then
  echo "Nog geen uitslagen beschikbaar."
  exit 0
fi

# --- 3. Verwerk alle wedstrijden (groep + knockout) via Python ---
RESULTS=$(echo "$MATCHES" | KO_DEFS="$KODEFS" python3 -c "
import sys, json, os

data = json.load(sys.stdin)
ko_defs_raw = os.environ.get('KO_DEFS', '{}')
try:
    ko_defs = json.loads(ko_defs_raw)
except:
    ko_defs = {}

# --- Groepsfase mapping ---
groups = {
    'A':['Mexico','South Africa','South Korea','Czechia'],
    'B':['Canada','Bosnia and Herzegovina','Qatar','Switzerland'],
    'C':['Brazil','Haiti','Morocco','Scotland'],
    'D':['USA','Australia','Paraguay','Turkiye'],
    'E':['Germany','Ecuador','Curacao','Ivory Coast'],
    'F':['Japan','Netherlands','Sweden','Tunisia'],
    'G':['Belgium','Egypt','Iran','New Zealand'],
    'H':['Spain','Uruguay','Saudi Arabia','Cape Verde'],
    'I':['France','Senegal','Norway','Iraq'],
    'J':['Argentina','Algeria','Austria','Jordan'],
    'K':['Portugal','Colombia','DR Congo','Uzbekistan'],
    'L':['England','Croatia','Ghana','Panama']
}

name_map = {
    'Korea Republic':'South Korea','Republic of Korea':'South Korea',
    'Tuerkiye':'Turkiye','Turkey':'Turkiye','T\\u00fcrkiye':'Turkiye',
    \\\"C\\u00f4te d'Ivoire\\\":'Ivory Coast','Cote d Ivoire':'Ivory Coast',
    'Bosnia-Herzegovina':'Bosnia and Herzegovina',
    'United States':'USA','United States of America':'USA',
    'Cabo Verde':'Cape Verde','Cape Verde Islands':'Cape Verde',
    'Congo DR':'DR Congo','Democratic Republic of Congo':'DR Congo',
    'Curacao':'Curacao','Cura\\u00e7ao':'Curacao',
    'IR Iran':'Iran','Iran, Islamic Republic of':'Iran',
    'Czech Republic':'Czechia',
    'Saudi-Arabien':'Saudi Arabia'
}

all_teams = [t for teams in groups.values() for t in teams]

def map_name(n):
    if n in name_map: return name_map[n]
    if n in all_teams: return n
    lower = n.lower() if n else ''
    for t in all_teams:
        if t.lower() == lower: return t
        if lower and (t.lower() in lower or lower in t.lower()): return t
    return n

def get_group_matches(teams):
    m = []
    for i in range(len(teams)):
        for j in range(i+1, len(teams)):
            m.append((teams[i], teams[j]))
    return m

# --- Knockout mapping ---
def find_ko_key(home, away):
    for round_name in ['R32','R16','QF','SF','TP','FI']:
        if round_name not in ko_defs: continue
        for k, m in ko_defs[round_name].items():
            if not isinstance(m, dict): continue
            if (m.get('home') == home and m.get('away') == away):
                return f'{round_name}_{k}'
            if (m.get('home') == away and m.get('away') == home):
                return f'{round_name}_{k}'  # reversed
    return None

results = {}
for match in data.get('matches', []):
    stage = match.get('stage','')
    home_raw = match.get('homeTeam',{})
    away_raw = match.get('awayTeam',{})
    home = map_name(home_raw.get('name','') or home_raw.get('shortName',''))
    away = map_name(away_raw.get('name','') or away_raw.get('shortName',''))
    
    score = match.get('score',{})
    ft = score.get('fullTime',{})
    hs = ft.get('home')
    aws = ft.get('away')
    if hs is None or aws is None:
        # Probeer regularTime als fallback (voor knockout na verlenging)
        rt = score.get('regularTime',{})
        if rt.get('home') is not None and rt.get('away') is not None:
            hs = rt['home']
            aws = rt['away']
        else:
            continue

    # 1. Probeer groepsfase mapping
    found_group = False
    for letter, teams in groups.items():
        for i, (mh, ma) in enumerate(get_group_matches(teams)):
            if mh == home and ma == away:
                results[f'{letter}_{i}'] = f'{hs}-{aws}'
                found_group = True
            elif mh == away and ma == home:
                results[f'{letter}_{i}'] = f'{aws}-{hs}'
                found_group = True

    # 2. Probeer knockout mapping (alleen als niet in groepsfase gevonden)
    if not found_group:
        ko_key = find_ko_key(home, away)
        if ko_key:
            results[ko_key] = f'{hs}-{aws}'

print(json.dumps(results))
")

echo ""
echo "Verwerkte uitslagen:"
echo "$RESULTS" | python3 -m json.tool 2>/dev/null || echo "$RESULTS"
echo ""

# --- 4. Opslaan naar Firebase ---
COUNT_RESULTS=$(echo "$RESULTS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))" 2>/dev/null || echo "0")

if [ "$COUNT_RESULTS" -gt 0 ]; then
  echo "Opslaan naar Firebase ($COUNT_RESULTS uitslagen)..."
  curl -s -X PATCH \
    "${DB_URL}/pools/${POOL_CODE}/results.json" \
    -d "$RESULTS" \
    -H "Content-Type: application/json"
  echo ""
  echo "=== Klaar! $COUNT_RESULTS uitslagen opgeslagen voor pool $POOL_CODE ==="
else
  echo "=== Geen nieuwe uitslagen gevonden ==="
fi
