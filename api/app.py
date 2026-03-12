import os
import json
import random
import requests
from fastapi import FastAPI, Query, HTTPException
from bs4 import BeautifulSoup

app = FastAPI()

PASSKEY = os.getenv("API_PASSKEY")

RC_URL = os.getenv("RC_URL", "")
RTO_URL = os.getenv("RTO_URL", "")
CHALLAN_URL = os.getenv("CHALLAN_URL", "")

COOKIE = os.getenv("CARINFO_COOKIE")


# ---------------- PROXY ----------------

def load_proxies():
    try:
        with open("proxies.txt") as f:
            return [p.strip() for p in f if p.strip()]
    except:
        return []

PROXIES = load_proxies()


def get_proxy():

    if not PROXIES:
        return None

    proxy = random.choice(PROXIES)

    return {
        "http": f"http://{proxy}",
        "https": f"http://{proxy}"
    }


# ---------------- REQUEST ----------------

def fetch_page(url):

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Cookie": COOKIE
    }
    

    try:

        r = requests.get(
            url,
            headers=headers,
            proxies=get_proxy(),
            timeout=20
        )

        return r.text

    except:
        return None


# ---------------- NEXT DATA PARSER ----------------

def get_next_data(url):

    html = fetch_page(url)

    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    script = soup.find("script", {"id": "__NEXT_DATA__"})

    if not script:
        return None

    return json.loads(script.string)


# ---------------- RC DETAILS ----------------

def get_rc(vehicle):

    data = get_next_data(RC_URL + vehicle)

    if not data:
        return {}

    props = data.get("props", {}).get("pageProps", {})

    vehicle_info = (
        props.get("vehicleDetails")
        or props.get("vehicle")
        or props.get("vehicleInfo")
        or {}
    )

    return {

        "vehicle_number": vehicle,

        "make_model": vehicle_info.get("makeModel"),
        "owner_name": vehicle_info.get("ownerName"),

        "vehicle_class": vehicle_info.get("vehicleClass"),
        "fuel_type": vehicle_info.get("fuelType"),
        "fuel_norms": vehicle_info.get("fuelNorms"),

        "registration_date": vehicle_info.get("registrationDate"),
        "fitness_upto": vehicle_info.get("fitnessUpto"),

        "insurance_upto": vehicle_info.get("insuranceUpto"),
        "insurance_status": vehicle_info.get("insuranceStatus"),

        "rc_status": vehicle_info.get("rcStatus"),
        "unloaded_weight": vehicle_info.get("unladenWeight"),
        "number_of_seats": vehicle_info.get("seatCapacity")

    }


# ---------------- CLEAN PHONE ----------------

def clean_phone(phone):

    if not phone:
        return None

    phone = phone.strip()

    phone = phone.replace("-", "")
    phone = phone.replace(" ", "")
    phone = phone.replace("(", "")
    phone = phone.replace(")", "")

    return phone


# ---------------- RTO DETAILS ----------------

def get_rto(vehicle):

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

        if title == "Number":
            result["rto_code"] = value

        elif title == "Registered RTO":
            result["address"] = value

        elif title == "State":
            result["state"] = value

        elif title == "RTO Phone number":
            result["phone"] = clean_phone(value)

    return result


# ---------------- CHALLAN DETAILS ----------------

def get_challan(vehicle):

    data = get_next_data(CHALLAN_URL + vehicle)

    if not data:
        return {
            "challan_pending": None,
            "challan_count": 0
        }

    try:

        challans = (
            data.get("props", {})
            .get("pageProps", {})
            .get("challans", [])
        )

        return {
            "challan_pending": len(challans) > 0,
            "challan_count": len(challans)
        }

    except:

        return {
            "challan_pending": False,
            "challan_count": 0
        }


# ---------------- MAIN API ----------------

@app.get("/api/vehicle")

def vehicle_lookup(
    number: str = Query(...),
    passkey: str = Query(...)
):

    if passkey != PASSKEY:
        raise HTTPException(status_code=403, detail="Invalid passkey")

    rc = get_rc(number)
    rto = get_rto(number)
    challan = get_challan(number)

    data = {}

    data.update(rc)
    data.update(rto)
    data.update(challan)

    return {

        "status": "success",
        "data": data,
        "developer": "@captainpapaj1"

    }
