import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime, timezone

BASE_URL = "https://hrm.dghs.gov.bd/public/facility-registry/reports/organization-list"

PARAMS = {
    "alias_columns_csv": "Id,Name,Name (Bangla),Code,Agency,Type,Division,District,City Corporation,Upazila,Paurasava,Union,Private",
    "columns_csv": "id,name,name_bn,code,facility_agency_name,facility_type_name,division_name,district_name,city_corporation_name,upazila_name,paurasava_name,union_name,is_private",
    "is_active": "1",
    "submit": "Run"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 HealthDatabaseUpdater/1.0"
}

OUTPUT = "data/health-data.json"


def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def get_table_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")

    if not table:
        return []

    rows = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])

        values = [
            clean(cell.get_text(" ", strip=True))
            for cell in cells
        ]

        if values:
            rows.append(values)

    return rows


def collect_page(page):

    params = dict(PARAMS)
    params["page"] = page

    print(f"Collecting page {page}...")

    for attempt in range(3):

        try:
            response = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                timeout=60
            )

            response.raise_for_status()

            rows = get_table_rows(response.text)

            if rows:
                return rows

            print("No table found.")

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")

        time.sleep(3)

    return []


def convert_rows(rows):

    if not rows:
        return []

    header = rows[0]
    data = []

    for row in rows[1:]:

        if len(row) < len(header):
            continue

        item = dict(zip(header, row))

        data.append({
            "id": item.get("Id", ""),
            "name": item.get("Name", ""),
            "name_bn": item.get("Name (Bangla)", ""),
            "code": item.get("Code", ""),
            "agency": item.get("Agency", ""),
            "type": item.get("Type", ""),
            "division": item.get("Division", ""),
            "district": item.get("District", ""),
            "city": item.get("City Corporation", ""),
            "upazila": item.get("Upazila", ""),
            "paurasava": item.get("Paurasava", ""),
            "union": item.get("Union", ""),
            "private": item.get("Private", ""),
            "source": "DGHS Facility Registry",
            "lastUpdated": datetime.now(timezone.utc).isoformat()
        })

    return data


def main():

    facilities = []

    MAX_PAGES = 2000

    for page in range(1, MAX_PAGES + 1):

        rows = collect_page(page)

        page_data = convert_rows(rows)

        if not page_data:
            print(f"Stopping at page {page}.")
            break

        facilities.extend(page_data)

        print(
            f"Page {page}: {len(page_data)} records | "
            f"Total: {len(facilities)}"
        )

        time.sleep(2)

    unique = {}

    for item in facilities:
        if item["id"]:
            unique[item["id"]] = item

    facilities = list(unique.values())

    database = {
        "version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "source": "DGHS Facility Registry",
        "facilities": facilities,
        "doctors": []
    }

    os.makedirs("data", exist_ok=True)

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            database,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("================================")
    print("DATABASE CREATED SUCCESSFULLY")
    print("Facilities:", len(facilities))
    print("File:", OUTPUT)
    print("================================")


if __name__ == "__main__":
    main()
