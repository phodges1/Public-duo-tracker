"""
iPhone Duo in-store stock tracker.
Checks Apple Store pickup availability near your ZIP code and sends a
push notification (via the free ntfy app) when stock appears.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

# iPhone Duo 512GB, US models (from Apple model numbers on retail listings)
PARTS = {
    "MK1H4LL/A": "iPhone Duo 512GB Night Sky",
    "MK1G4LL/A": "iPhone Duo 512GB Star White",
}

ZIP_CODE = os.environ.get("ZIP_CODE", "").strip()
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
MAX_MILES = float(os.environ.get("MAX_MILES", "40"))
STATE_FILE = "state.json"
BUY_URL = "https://www.apple.com/shop/buy-iphone/iphone-duo"


def notify(title, message, priority="high", tags="iphone"):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set; would have sent:", title, message)
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Tags": tags, "Click": BUY_URL},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def fetch_availability():
    params = {"pl": "true", "mts.0": "regular", "location": ZIP_CODE}
    for i, part in enumerate(PARTS):
        params[f"parts.{i}"] = part
    url = "https://www.apple.com/shop/fulfillment-messages?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "Accept": "application/json",
        "Referer": BUY_URL,
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def parse_miles(text):
    try:
        return float(str(text).split()[0].replace(",", ""))
    except (ValueError, IndexError):
        return 0.0


def find_in_stock(data):
    """Return a sorted list of 'Model at Store (distance)' strings."""
    hits = []
    stores = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
    for store in stores:
        distance = store.get("storeDistanceWithUnit", "")
        if parse_miles(distance) > MAX_MILES:
            continue
        for part, info in (store.get("partsAvailability") or {}).items():
            if part in PARTS and info.get("pickupDisplay") == "available":
                hits.append(f"{PARTS[part]} at {store.get('storeName', 'Apple Store')} ({distance})")
    return sorted(hits)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": [], "error_alerted": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    if not ZIP_CODE:
        sys.exit("Set the ZIP_CODE secret first.")

    state = load_state()

    if os.environ.get("TEST_ALERT") == "true":
        notify("Tracker is working ✅", f"Watching Apple Stores within {MAX_MILES:.0f} mi of {ZIP_CODE}.",
               priority="default", tags="white_check_mark")

    try:
        data = fetch_availability()
    except Exception as e:  # network error, Apple blocking, etc.
        print("Check failed:", e)
        if not state.get("error_alerted"):
            notify("Tracker can't reach Apple ⚠️",
                   f"Stock checks are failing ({e}). I'll keep trying and won't repeat this alert.",
                   priority="default", tags="warning")
            state["error_alerted"] = True
            save_state(state)
        return

    state["error_alerted"] = False
    hits = find_in_stock(data)
    new = [h for h in hits if h not in state.get("seen", [])]

    print("In stock:", hits or "nothing nearby")
    if new:
        notify("iPhone Duo in stock! 📱", "\n".join(new) + "\n\nTap to open Apple's store and reserve pickup.",
               priority="urgent", tags="iphone,rotating_light")

    state["seen"] = hits  # so it re-alerts if stock sells out and comes back
    save_state(state)


if __name__ == "__main__":
    main()
