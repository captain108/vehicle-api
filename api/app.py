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
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html"
        }

        r = requests.get(BASE_URL, headers=headers, timeout=10)

        print("Homepage status:", r.status_code)

        if r.status_code != 200:
            return None

        html = r.text

        match = re.search(r'"buildId":"([^"]+)"', html)

        if match:
            return match.group(1)

        print("Build ID not found")
        return None

    except Exception as e:
        print("Build ID error:", e)
        return None


def clean_vehicle_data(data):

    try:

        messages = (
            data.get("pageProps", {})
            .get("rtoDetailsReponse", {})
            .get("webSections", [{}])[0]
            .get("messages", [])
        )

        result = {
            "rto_code": None,
            "address": None,
            "state": None,
            "phone": None
        }

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
                result["phone"] = value

        return result

    except Exception as e:
        print("Parsing error:", e)
        return None


@app.get("/api/vehicle")
def vehicle_lookup(number: str = Query(...), passkey: str = Query(...)):

    if passkey != PASSKEY:
        raise HTTPException(status_code=403, detail="Invalid passkey")

    build_id = get_build_id()

    if not build_id:
        return {
            "status": "error",
            "message": "Build ID detection failed",
            "developer": "@captainpapaj1"
        }

    url = BASE_URL + API_PATH.format(build=build_id, vehicle=number)

    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        print("API status:", r.status_code)

        if r.status_code != 200:
            return {
                "vehicle_number": number,
                "status": "not_found",
                "developer": "@captainpapaj1"
            }

        data = r.json()

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "developer": "@captainpapaj1"
        }

    cleaned = clean_vehicle_data(data)

    if not cleaned:
        return {
            "vehicle_number": number,
            "status": "not_found",
            "developer": "@captainpapaj1"
        }

    return {
        "vehicle_number": number,
        "status": "success",
        "data": cleaned,
        "developer": "@captainpapaj1"
    }
