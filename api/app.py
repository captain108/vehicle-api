import os
import json
import time
import random
import threading
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup
import pytz

# ============================================================
# CONFIG
# ============================================================

app = FastAPI(title="Unified Lookup API", version="2.0.0")

PASSKEY       = os.getenv("API_PASSKEY", "pak_captain123")
RC_URL        = os.getenv("RC_URL", "https://www.carinfo.app/rc-details/")
RTO_URL       = os.getenv("RTO_URL", "https://www.carinfo.app/rto-vehicle-registration-detail/")
CHALLAN_URL   = os.getenv("CHALLAN_URL", "https://www.carinfo.app/e-challan-check/")
COOKIE        = os.getenv("CARINFO_COOKIE", "")
SELF_URL      = os.getenv("SELF_URL", "")
OWNER         = "@captainpapaj1"

CACHE = {}
CACHE_TTL = 300


# ============================================================
# RESPONSE BUILDER
# ============================================================

def ist_now():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%d-%m-%Y %I:%M:%S %p")


def build_response(data, cached=False, success=True):
    return {
        "success": success,
        "cached": cached,
        "owner": OWNER,
        "ist_time": ist_now(),
        "data": data
    }


def cache_get(key):
    item = CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if time.time() - ts > CACHE_TTL:
        CACHE.pop(key, None)
        return None
    return payload


def cache_set(key, payload):
    CACHE[key] = (time.time(), payload)


# ============================================================
# PROXY
# ============================================================

def load_proxies():
    try:
        with open("proxies.txt") as f:
            return [p.strip() for p in f if p.strip()]
    except Exception:
        return []


PROXIES = load_proxies()


def get_proxy():
    if not PROXIES:
        return None
    proxy = random.choice(PROXIES)
    return {"http": f"http://{proxy}", "https": f"http://{proxy}"}


# ============================================================
# FETCH
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-IN,en;q=0.9",
}


def fetch_page(url):
    headers = dict(HEADERS)
    if COOKIE:
        headers["Cookie"] = COOKIE
    try:
        r = requests.get(url, headers=headers, proxies=get_proxy(), timeout=25)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:
        return None


# ============================================================
# HELPERS
# ============================================================

def clean_phone(phone):
    if not phone:
        return None
    phone = phone.strip()
    for ch in ["-", " ", "(", ")", "\t", "\n"]:
        phone = phone.replace(ch, "")
    return phone


def class_contains(soup, tag, substring):
    """Find first element whose class contains substring."""
    for el in soup.find_all(tag):
        classes = el.get("class") or []
        if any(substring in c for c in classes):
            return el
    return None


# ============================================================
# RC SCRAPER (HTML based)
# ============================================================

def get_rc(vehicle):
    html = fetch_page(RC_URL + vehicle)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    result = {"vehicle_number": vehicle}

    # --- Make & Model ---
    el = class_contains(soup, "p", "vehicalModel")
    if el:
        result["make_model"] = el.get_text(strip=True)

    # --- Owner Name ---
    el = class_contains(soup, "p", "ownerName")
    if el:
        result["owner_name"] = el.get_text(strip=True)

    # --- Insurance Expiry (from banner text) ---
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if "Insurance Expired on" in text:
            # "🚨 Insurance Expired on 09-Aug-2025"
            try:
                result["insurance_upto"] = text.split("on")[-1].strip()
            except Exception:
                pass
            result["insurance_status"] = "Expired"
            break

    # --- RTO section (it's on the RC page too) ---
    rto_items = soup.find_all("div", class_=lambda c: c and "detailItem" in c)
    for item in rto_items:
        label_el = item.find("p", class_=lambda c: c and "itemText" in c)
        value_el = item.find("p", class_=lambda c: c and "itemSubTitle" in c)
        if not label_el or not value_el:
            continue

        label = label_el.get_text(strip=True)
        value = value_el.get_text(strip=True)

        if label == "Number":
            result["rto_code"] = value
        elif label == "Registered RTO":
            result["address"] = value
        elif label == "State":
            result["state"] = value
        elif label == "RTO Phone number":
            result["phone"] = clean_phone(value)
        elif label == "Website":
            result["website"] = value

    return result


# ============================================================
# RTO SCRAPER (dedicated RTO page)
# ============================================================

def get_rto(vehicle):
    html = fetch_page(RTO_URL + vehicle)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    result = {}

    rto_items = soup.find_all("div", class_=lambda c: c and "detailItem" in c)
    for item in rto_items:
        label_el = item.find("p", class_=lambda c: c and "itemText" in c)
        value_el = item.find("p", class_=lambda c: c and "itemSubTitle" in c)
        if not label_el or not value_el:
            continue

        label = label_el.get_text(strip=True)
        value = value_el.get_text(strip=True)

        if label == "Number":
            result["rto_code"] = value
        elif label == "Registered RTO":
            result["address"] = value
        elif label == "State":
            result["state"] = value
        elif label == "RTO Phone number":
            result["phone"] = clean_phone(value)
        elif label == "Website":
            result["website"] = value

    return result


# ============================================================
# CHALLAN SCRAPER
# ============================================================

def get_challan(vehicle):
    html = fetch_page(CHALLAN_URL + vehicle)
    if not html:
        return {"challan_pending": None, "challan_count": 0, "challans": []}

    soup = BeautifulSoup(html, "html.parser")

    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return {"challan_pending": None, "challan_count": 0, "challans": []}

    try:
        data = json.loads(script.string)
    except Exception:
        return {"challan_pending": None, "challan_count": 0, "challans": []}

    try:
        props = data.get("props", {}).get("pageProps", {})
        disc = props.get("challanDiscovery", {}) or {}
        dd = disc.get("discoveryData", {}) or {}
        tabs = dd.get("tabsData", []) or []

        pending = 0
        for t in tabs:
            if t.get("tabId") == "PENDING":
                pending = t.get("totalChallans", 0)
                break

        return {
            "challan_pending": pending > 0,
            "challan_count": pending,
            "challans": []
        }
    except Exception:
        return {"challan_pending": False, "challan_count": 0, "challans": []}


# ============================================================
# TYPE HANDLERS
# ============================================================

def handle_veh(query):
    vehicle = query.strip().upper().replace(" ", "")

    cache_key = f"veh:{vehicle}"
    cached = cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    rc = get_rc(vehicle)
    rto = get_rto(vehicle)
    challan = get_challan(vehicle)

    if not rc and not rto and not challan.get("challan_count"):
        return build_response({
            "type": "veh",
            "query": vehicle,
            "status": "ᴅᴀᴛᴀ ɴᴏᴛ ꜰᴏᴜɴᴅ ❌"
        }, success=False)

    merged = {"type": "veh", "query": vehicle, "status": "ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ ✅"}
    merged.update(rc)
    merged.update(rto)
    merged.update(challan)

    payload = build_response(merged, cached=False, success=True)
    cache_set(cache_key, payload)
    return payload


def handle_external(kind, query):
    endpoints = {
        "tgid":   f"https://num-user-rinm.onrender.com/api/{PASSKEY}/tgid/{query}",
        "number": f"https://num-user-rinm.onrender.com/api/{PASSKEY}/number/{query}",
    }
    url = endpoints.get(kind)
    if not url:
        return build_response({"type": kind, "query": query,
                               "status": "ᴜɴᴋɴᴏᴡɴ ᴛʏᴘᴇ ❌"}, success=False)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        return r.json()
    except Exception:
        return build_response({"type": kind, "query": query,
                               "status": "ᴇʀʀᴏʀ ❌"}, success=False)


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Unified Lookup API",
        "types": ["tgid", "number", "veh"],
        "usage": "/api/{passkey}/{type}/{query}",
        "example": f"/api/{PASSKEY}/veh/MH04KF1234",
        "owner": OWNER,
        "ist_time": ist_now(),
    }


@app.get("/health")
def health():
    return {"status": "healthy", "ist_time": ist_now()}


@app.get("/api/{passkey}/{type}/{query}")
def lookup(passkey: str, type: str, query: str):
    if passkey != PASSKEY:
        raise HTTPException(status_code=403, detail="Invalid passkey")

    type = type.lower()
    if type == "veh":
        return handle_veh(query)
    elif type in ("tgid", "number"):
        return handle_external(type, query)
    else:
        raise HTTPException(status_code=400,
                            detail="Unknown type. Use: tgid, number, veh")


# ============================================================
# KEEP ALIVE
# ============================================================

def keep_alive_loop():
    if not SELF_URL:
        return
    while True:
        try:
            requests.get(SELF_URL, timeout=10)
        except Exception:
            pass
        time.sleep(840)


@app.on_event("startup")
def start_keepalive():
    if SELF_URL:
        threading.Thread(target=keep_alive_loop, daemon=True).start()


# ============================================================
# ERROR HANDLER
# ============================================================

@app.exception_handler(HTTPException)
async def custom_http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=build_response({"status": exc.detail}, success=False)
    )
