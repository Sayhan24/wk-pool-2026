"""
Firebase helper - anonymous auth + push data.
Gebruikt door setup-knockout.py, advance-knockout.py en fetch-wk-results.sh.
"""
import json, subprocess, sys

FIREBASE_API_KEY = "AIzaSyB86dXNn5MkRSzWvRAk4CcWK9kjP-at2Ik"
FIREBASE_DB = "https://wkpool-2026-default-rtdb.europe-west1.firebasedatabase.app"

def get_id_token():
    """Get a Firebase ID token via anonymous sign-in."""
    script = f"""
    const https = require('https');
    const data = JSON.stringify({{returnSecureToken: true}});
    const req = https.request({{
      hostname: 'identitytoolkit.googleapis.com',
      path: '/v1/accounts:signUp?key={FIREBASE_API_KEY}',
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}}
    }}, res => {{
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {{
        try {{
          const auth = JSON.parse(body);
          if (auth.idToken) console.log(auth.idToken);
          else {{ console.error('AUTH_FAIL:' + body); process.exit(1); }}
        }} catch(e) {{ console.error('PARSE_FAIL:' + e.message); process.exit(1); }}
      }});
    }});
    req.write(data);
    req.end();
    """
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        print(f"  Auth error: {result.stderr}", file=sys.stderr)
        return None
    token = result.stdout.strip()
    if not token or len(token) < 20:
        print(f"  Invalid token: {token[:50]}...", file=sys.stderr)
        return None
    return token


def firebase_put(path, data_dict):
    """Write data to Firebase Realtime Database using anonymous auth."""
    import urllib.request

    token = get_id_token()
    if not token:
        return False

    json_data = json.dumps(data_dict).encode('utf-8')
    url = f"{FIREBASE_DB}{path}.json?auth={token}"

    req = urllib.request.Request(url, data=json_data, method='PUT',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8')
            if 'error' in body.lower():
                print(f"  Firebase error: {body}", file=sys.stderr)
                return False
            return True
    except Exception as e:
        print(f"  Request failed: {e}", file=sys.stderr)
        return False


def firebase_patch(path, data_dict):
    """PATCH data to Firebase (merge, doesn't delete other keys at path)."""
    import urllib.request

    token = get_id_token()
    if not token:
        return False

    json_data = json.dumps(data_dict).encode('utf-8')
    url = f"{FIREBASE_DB}{path}.json?auth={token}"

    req = urllib.request.Request(url, data=json_data, method='PATCH',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8')
            if 'error' in body.lower():
                print(f"  Firebase error: {body}", file=sys.stderr)
                return False
            return True
    except Exception as e:
        print(f"  Request failed: {e}", file=sys.stderr)
        return False


def firebase_get(path):
    """GET data from Firebase."""
    import urllib.request
    url = f"{FIREBASE_DB}{path}.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except:
        return {}


if __name__ == "__main__":
    # Quick test
    print("Testing Firebase auth...")
    token = get_id_token()
    if token:
        print(f"  Token OK: {token[:20]}...")
    else:
        print("  Auth failed!")
