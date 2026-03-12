import os
import json
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query

app = FastAPI()

PASSKEY = os.getenv("API_PASSKEY")
BASE_URL = os.getenv("CARINFO_BASE")


def fetch_vehicle_data(vehicle_number):

    url = f"{BASE_URL}/{vehicle_number}"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:

        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        script = soup.find("script", {"id": "__NEXT_DATA__"})

        if not script:
            return None

        data = json.loads(script.string)

        page = data.get("props", {}).get("pageProps", {})

        # -------- VEHICLE TOP INFO --------

        vehicle_info = page.get("vehicleDetailsResponse", {})

        make_model = vehicle_info.get("makeModel")
        owner_name = vehicle_info.get("ownerName")

        # -------- RTO DETAILS --------

        messages = (
            page
            .get("rtoDetailsReponse", {})
            .get("webSections", [{}])[0]
            .get("messages", [])
        )

        result = {
            "make_model": make_model,
            "owner_name": owner_name,
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
                result["phone"] = value.replace("-", "").replace(" ", "")

        return result

    except Exception as e:
        print("Scraping error:", e)
        return None


@app.get("/api/vehicle")
def vehicle_lookup(number: str = Query(...), passkey: str = Query(...)):

    if passkey != PASSKEY:
        raise HTTPException(status_code=403, detail="Invalid passkey")

    data = fetch_vehicle_data(number)

    if not data:
        return {
            "vehicle_number": number,
            "status": "not_found",
            "developer": "@captainpapaj1"
        }

    return {
        "vehicle_number": number,
        "status": "success",
        "data": data,
        "developer": "@captainpapaj1"
    }
