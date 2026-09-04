import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://rmch.gov.bd/"
SEEDS = [
    "https://rmch.gov.bd/emergency-service/department-of-medicine/",
    "https://rmch.gov.bd/emergency-service/department-of-hematology/",
    "https://rmch.gov.bd/emergency-service/department-of-nose-ears-and-throat/",
    "https://rmch.gov.bd/emergency-service/department-of-gastroenterology-and-hepatology/",
    "https://rmch.gov.bd/outdoor/pathology-and-rt-pcr-lab/",
]

OUT = "data/doctors.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BangladeshHealthDatabase/1.0)"
}

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def is_doctor_name(text):
    text = clean(text).lower()
    prefixes = (
        "dr.", "dr ", "prof.", "prof ",
        "ডাঃ", "ডা.", "অধ্যাপক"
    )
    return text.startswith(prefixes)

def get_department(soup, url):
    h1 = soup.find("h1")
    if h1 and clean(h1.get_text(" ", strip=True)):
        return clean(h1.get_text(" ", strip=True))

    title = soup.find("title")
    if title:
        return clean(title.get_text(" ", strip=True)).replace(
            "Rajshahi Medical College Hospital", ""
        ).strip(" -|")

    return urlparse(url).path.strip("/").split("/")[-1].replace("-", " ").title()

def collect_page(url):
    print("Collecting:", url)

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print("ERROR:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    department = get_department(soup, url)
    doctors = []

    # টেবিল থেকে ডাক্তারদের তথ্য সংগ্রহ
    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        for row in rows:
            cells = [clean(x.get_text(" ", strip=True))
                     for x in row.find_all(["td", "th"])]

            if len(cells) < 2:
                continue

            # নাম খোঁজা
            name_index = None
            for i, cell in enumerate(cells):
                if is_doctor_name(cell):
                    name_index = i
                    break

            if name_index is None:
                continue

            name = cells[name_index]

            remaining = [
                c for i, c in enumerate(cells)
                if i != name_index and c
            ]

            designation = remaining[0] if remaining else ""
            qualification = ", ".join(remaining[1:]) if len(remaining) > 1 else ""

            doctors.append({
                "name": name,
                "designation": designation,
                "department": department,
                "specialty": "",
                "qualification": qualification,
                "workplace": "Rajshahi Medical College Hospital",
                "bmdc_reg_no": "",
                "professional_contact": "",
                "source": url,
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d")
            })

    return doctors


def deduplicate(items):
    unique = {}

    for d in items:
        key = (
            clean(d["name"]).lower(),
            clean(d["department"]).lower()
        )

        if key not in unique:
            unique[key] = d
        else:
            # তথ্য বেশি সম্পূর্ণ হলে সেটি রাখি
            old = unique[key]

            if len(d.get("qualification", "")) > len(old.get("qualification", "")):
                old["qualification"] = d["qualification"]

            if len(d.get("designation", "")) > len(old.get("designation", "")):
                old["designation"] = d["designation"]

    return list(unique.values())


all_doctors = []

for url in SEEDS:
    all_doctors.extend(collect_page(url))
    time.sleep(1)

all_doctors = deduplicate(all_doctors)

data = {
    "source": "Rajshahi Medical College Hospital official website",
    "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "count": len(all_doctors),
    "doctors": all_doctors
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print()
print("================================")
print("Doctor collection completed")
print("Doctors:", len(all_doctors))
print("Saved:", OUT)
print("================================")
