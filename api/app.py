import os
import json
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, HTTPException

app = FastAPI()

PASSKEY = os.getenv("API_PASSKEY")

RC_URL = os.getenv("RC_URL")
RTO_URL = os.getenv("RTO_URL")
CHALLAN_URL = os.getenv("CHALLAN_URL")


def get_next_data(url):

    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers, timeout=15)

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    script = soup.find("script", {"id": "__NEXT_DATA__"})

    if not script:
        return None

    return json.loads(script.string)


# ---------------- RC DETAILS ----------------

def get_rc_data(vehicle):

    data = get_next_data(RC_URL + vehicle)

    if not data:
        return {}

    page = data.get("props", {}).get("pageProps", {})
    vehicle_details = page.get("vehicleDetailsResponse", {})

    result = {}

    result["vehicle_number"] = vehicle
    result["make_model"] = vehicle_details.get("makeModel")
    result["owner_name"] = vehicle_details.get("ownerName")

    result["vehicle_class"] = vehicle_details.get("vehicleClass")
    result["fuel_type"] = vehicle_details.get("fuelType")
    result["fuel_norms"] = vehicle_details.get("fuelNorms")

    result["registration_date"] = vehicle_details.get("registrationDate")
    result["fitness_upto"] = vehicle_details.get("fitnessUpto")

    result["insurance_upto"] = vehicle_details.get("insuranceUpto")
    result["insurance_status"] = vehicle_details.get("insuranceStatus")

    result["rc_status"] = vehicle_details.get("rcStatus")
    result["unloaded_weight"] = vehicle_details.get("unladenWeight")
    result["number_of_seats"] = vehicle_details.get("seatCapacity")

    return result


# ---------------- RTO DETAILS ----------------

def get_rto_data(vehicle):

    data = get_next_data(RTO_URL + vehicle)

    if not data:
        return {}

    page = data.get("props", {}).get("pageProps", {})
    rto_details = page.get("rtoDetailsReponse", {})

    result = {}

    messages = (
        rto_details
        .get("webSections", [{}])[0]
        .get("messages", [])
    )

    for item in messages:

        title = item.get("title")
        value = item.get("subtitle")

        if title == "Number":
            result["rto_code"] = value

        elif title == "Registered RTO":
            result["address"] = value

        elif title == "State":
            result["state"] = value

    return result


# ---------------- CHALLAN ----------------

def get_challan(vehicle):

    data = get_next_data(CHALLAN_URL + vehicle)

    if not data:
        return {"challan_pending": None}

    page = data.get("props", {}).get("pageProps", {})

    challans = page.get("challanResponse", {}).get("pending", [])

    return {
        "challan_pending": len(challans) > 0,
        "challan_count": len(challans)
    }


# ---------------- MAIN API ----------------

@app.get("/api/vehicle")
def vehicle_lookup(number: str = Query(...), passkey: str = Query(...)):

    if passkey != PASSKEY:
        raise HTTPException(status_code=403, detail="Invalid passkey")

    rc = get_rc_data(number)
    rto = get_rto_data(number)
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
