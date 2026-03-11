import os
import re
import requests
from fastapi import FastAPI, HTTPException, Query

app = FastAPI()

PASSKEY = os.getenv("API_PASSKEY")
BASE_URL = os.getenv("CARINFO_BASE")
API_PATH = os.getenv("CARINFO_PATH")


def get_build_id():
    try:
        r = requests.get(BASE_URL)
        html = r.text

        match = re.search(r'"buildId":"(.*?)"', html)

        if match:
            return match.group(1)

    except:
        return None


def clean_vehicle_data(data):

    try:
        messages = data["pageProps"]["rtoDetailsReponse"]["webSections"][0]["messages"]

        result = {
            "rto_code": None,
            "address": None,
            "state": None,
            "phone": None
        }

        for item in messages:

            title = item["title"]
            value = item["subtitle"]

            if title == "Number":
                result["rto_code"] = value

            elif title == "Registered RTO":
                result["address"] = value

            elif title == "State":
                result["state"] = value

            elif title == "RTO Phone number":
                result["phone"] = value

        return result

    except:
        return None


@app.get("/api/vehicle")
def vehicle_lookup(number: str = Query(...), passkey: str = Query(...)):

    if passkey != PASSKEY:
        raise HTTPException(status_code=403, detail="Invalid passkey")

    build_id = get_build_id()

    if not build_id:
        raise HTTPException(status_code=500, detail="Build ID detection failed")

    url = BASE_URL + API_PATH.format(build=build_id, vehicle=number)

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        return {
            "vehicle_number": number,
            "status": "not_found",
            "message": "No vehicle data available",
            "developer": "@captainpapaj1"
        }

    data = r.json()

    cleaned = clean_vehicle_data(data)

    if not cleaned:
        return {
            "vehicle_number": number,
            "status": "not_found",
            "message": "No vehicle data available",
            "developer": "@captainpapaj1"
        }

    return {
        "vehicle_number": number,
        "status": "success",
        "data": cleaned,
        "developer": "@captainpapaj1"
    }
