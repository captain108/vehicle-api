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

app = FastAPI(title="Unified Lookup API", version="1.0.0")

PASSKEY       = os.getenv("API_PASSKEY", "pak_captain123")
RC_URL        = os.getenv("RC_URL", "")
RTO_URL       = os.getenv("RTO_URL", "")
CHALLAN_URL   = os.getenv("CHALLAN_URL", "")
COOKIE        = os.getenv("CARINFO_COOKIE", "")
SELF_URL      = os.getenv("SELF_URL", "")  # e.g. https://num-user-rinm.onrender.com/
OWNER         = "@captainpapaj1"

# In-memory cache: { key: (timestamp, payload) }
CACHE = {}
CACHE_TTL = 300  # 5 minutes


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
# HTTP FETCH
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
}


def fetch_page(url):
    headers = dict(HEADERS)
    if COOKIE:
        headers["Cookie"] = COOKIE

    try:
        r = requests.get(url, headers=headers, proxies=get_proxy(), timeout=20)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:
        return None


def get_next_data(url):
    html = fetch_page(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return None

    try:
        return json.loads(script.string)
    except Exception:
        return None


# ============================================================
# RC / RTO / CHALLAN SCRAPERS
# ============================================================

def clean_phone(phone):
    if not phone:
        return None
    phone = phone.strip()
    for ch in ["-", " ", "(", ")", "\t", "\n"]:
        phone = phone.replace(ch, "")
    return phone


def get_rc(vehicle):
    if not RC_URL:
        return {}

    data = get_next_data(RC_URL + vehicle)
    if not data:
        return {}

    props = data.get("props", {}).get("pageProps", {})
    v = (
        props.get("vehicleDetails")
        or props.get("vehicle")
        or props.get("vehicleInfo")
        or {}
    )

    return {
        "vehicle_number": vehicle,
        "make_model": v.get("makeModel"),
        "owner_name": v.get("ownerName"),
        "vehicle_class": v.get("vehicleClass"),
        "fuel_type": v.get("fuelType"),
        "fuel_norms": v.get("fuelNorms"),
        "registration_date": v.get("registrationDate"),
        "fitness_upto": v.get("fitnessUpto"),
        "insurance_upto": v.get("insuranceUpto"),
        "insurance_status": v.get("insuranceStatus"),
        "rc_status": v.get("rcStatus"),
        "unloaded_weight": v.get("unladenWeight"),
        "number_of_seats": v.get("seatCapacity"),
    }


def get_rto(vehicle):
    if not RTO_URL:
        return {}

    data = get_next_data(RTO_URL + vehicle)
    if not data:
        return {}

    messages = (
        data.get("props", {})
        .get("pageProps", {})
        .get("rtoDetailsReponse", {})
        .get("webSections", [{}])[0]
        .get("messages", [])
    )

    result = {}
    for item in messages:
        title = item.get("title")
        value = item.get("subtitle")
        if not title or not value:
            continue

        if title == "Number":
            result["rto_code"] = value
        elif title == "Registered RTO":
            result["address"] = value
        elif title == "State":
            result["state"] = value
        elif title == "RTO Phone number":
            result["phone"] = clean_phone(value)
        elif title == "Website":
            result["website"] = value

    return result


def get_challan(vehicle):
    if not CHALLAN_URL:
        return {"challan_pending": None, "challan_count": 0, "challans": []}

    data = get_next_data(CHALLAN_URL + vehicle)
    if not data:
        return {"challan_pending": None, "challan_count": 0, "challans": []}

    try:
        challans = (
            data.get("props", {})
            .get("pageProps", {})
            .get("challans", [])
        )
        simplified = [{
            "challan_number": c.get("challanNumber") or c.get("challan_no"),
            "date": c.get("date") or c.get("challanDate"),
            "amount": c.get("amount") or c.get("fineAmount"),
            "status": c.get("status"),
            "offence": c.get("offence") or c.get("violation"),
        } for c in challans]

        return {
            "challan_pending": len(challans) > 0,
            "challan_count": len(challans),
            "challans": simplified,
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
        payload = build_response({
            "type": "veh",
            "query": vehicle,
            "status": "ᴅᴀᴛᴀ ɴᴏᴛ ꜰᴏᴜɴᴅ ❌"
        }, success=False)
        return payload

    merged = {"type": "veh", "query": vehicle, "status": "ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ ✅"}
    merged.update(rc)
    merged.update(rto)
    merged.update(challan)

    payload = build_response(merged, cached=False, success=True)
    cache_set(cache_key, payload)
    return payload


def handle_external(kind, query):
    """
    Placeholder for tgid/number lookups.
    Replace the URL below with your real data source.
    """
    endpoints = {
        "tgid":   f"https://num-user-rinm.onrender.com/api/{PASSKEY}/tgid/{query}",
        "number": f"https://num-user-rinm.onrender.com/api/{PASSKEY}/number/{query}",
    }
    url = endpoints.get(kind)
    if not url:
        return build_response({
            "type": kind, "query": query, "status": "ᴜɴᴋɴᴏᴡɴ ᴛʏᴘᴇ ❌"
        }, success=False)

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        return r.json()
    except Exception:
        return build_response({
            "type": kind, "query": query, "status": "ᴇʀʀᴏʀ ❌"
        }, success=False)


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
        raise HTTPException(
            status_code=400,
            detail="Unknown type. Use: tgid, number, veh"
        )


# ============================================================
# KEEP-ALIVE (Render free tier)
# ============================================================

def keep_alive_loop():
    if not SELF_URL:
        return
    while True:
        try:
            requests.get(SELF_URL, timeout=10)
        except Exception:
            pass
        time.sleep(840)  # 14 minutes


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
        content=build_response(
            {"status": exc.detail},
            success=False
        )
    )
    
