import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("data/doctors.json")

# প্রতিটি পেজের সাথে সঠিক Department
SEEDS = [
    (
        "https://rmch.gov.bd/emergency-service/department-of-medicine/",
        "Medicine"
    ),
    (
        "https://rmch.gov.bd/emergency-service/department-of-hematology/",
        "Hematology"
    ),
    (
        "https://rmch.gov.bd/emergency-service/department-of-nose-ears-and-throat/",
        "ENT"
    ),
    (
        "https://rmch.gov.bd/emergency-service/department-of-gastroenterology-and-hepatology/",
        "Gastroenterology & Hepatology"
    ),
    (
        "https://rmch.gov.bd/outdoor/pathology-and-rt-pcr-lab/",
        "Pathology & RT-PCR"
    ),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BangladeshHealthDatabase/1.0)"
}


def clean(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_phone(text):
    """মোবাইল নম্বর শনাক্ত করে"""
    t = text.strip()
    digits = re.sub(r"\D", "", t)

    if len(digits) >= 10 and len(digits) <= 14:
        return True

    return False


def looks_like_doctor_table(headers):
    h = " ".join(headers).lower()

    doctor_words = [
        "doctor",
        "doctors name",
        "doctors",
        "নাম",
        "পদবী",
        "পদবি",
        "degree",
        "ডিগ্রী",
        "ডিগ্রি"
    ]

    return any(word.lower() in h for word in doctor_words)


def split_designation_qualification(text):
    """
    বাংলা/ইংরেজি combined পদবী ও ডিগ্রি আলাদা করে।
    """

    text = clean(text)

    if not text:
        return "", ""

    # পরিচিত পদবীগুলো আগে শনাক্ত করা হবে
    designation_patterns = [
        "সহযোগী অধ্যাপক ও বিভাগীয় প্রধান",
        "সহকারী অধ্যাপক ও বিভাগীয় প্রধান",
        "সহকারী অধ্যাপক ও বিভাগীয় প্রধান",
        "সহযোগী অধ্যাপক ও বিভাগীয় প্রধান",
        "অধ্যাপক ও বিভাগীয় প্রধান",
        "সহকারী অধ্যাপক",
        "সহযোগী অধ্যাপক",
        "অধ্যাপক",
        "সহকারী রেজিষ্ট্রার",
        "সহকারী রেজিস্ট্রার",
        "রেজিষ্ট্রার",
        "রেজিস্ট্রার",
        "ইমারজেন্সি মেডিকেল অফিসার",
        "মেডিকেল অফিসার",
        "আইএমও",
        "IMO",
        "MO",
        "MO:",
        "MO.",
        "RP:",
        "আরএস",
    ]

    # সবচেয়ে দীর্ঘ pattern আগে
    designation_patterns.sort(key=len, reverse=True)

    lower_text = text.lower()

    for pattern in designation_patterns:
        p = pattern.lower()

        if lower_text.startswith(p):
            designation = clean(text[:len(pattern)])
            qualification = clean(text[len(pattern):])

            # RP:/MO: ইত্যাদির পরে qualification থাকলে রাখব
            return designation, qualification

    # কমা/semicolon থাকলে প্রথম অংশ designation
    parts = re.split(r"\s*[,;]\s*", text)

    if len(parts) >= 2:
        first = clean(parts[0])
        rest = clean(", ".join(parts[1:]))

        degree_words = [
            "এমবিবিএস", "বিডিএস", "এফসিপিএস", "এমডি",
            "এমএস", "এমসিপিএস", "পিএইচডি",
            "MBBS", "BDS", "FCPS", "MD", "MS",
            "MRCP", "FRCP", "MCPS", "PhD"
        ]

        if any(x.lower() in first.lower() for x in degree_words):
            return "", clean(first + ", " + rest)

        return first, rest

    # Degree-এর জায়গা থেকে split
    degree_pattern = (
        r"(এমবিবিএস|বিডিএস|এফসিপিএস|এমডি|এমএস|এমসিপিএস|পিএইচডি|"
        r"MBBS|BDS|FCPS|MD|MS|MRCP|FRCP|MCPS|PhD)"
    )

    m = re.search(degree_pattern, text, re.I)

    if m:
        designation = clean(text[:m.start()])
        qualification = clean(text[m.start():])

        if designation:
            return designation, qualification

    # কিছু ডিগ্রি designation-এর পরে থাকে
    special_degree = re.search(
        r"(ডি\.এল\.ও|DLO|D\.L\.O|এমপিএইচ|MPH|এমআরসিপি|MRCP)",
        text,
        re.I
    )

    if special_degree:
        before = clean(text[:special_degree.start()])
        after = clean(text[special_degree.start():])

        if before:
            return before, after

    return "", text


def parse_table(table, department, source):
    rows = table.find_all("tr")

    if not rows:
        return []

    header_cells = rows[0].find_all(["th", "td"])
    headers = [clean(x.get_text(" ", strip=True)) for x in header_cells]

    if not looks_like_doctor_table(headers):
        return []

    header_lower = [x.lower() for x in headers]

    name_index = None
    designation_index = None
    degree_index = None

    for i, h in enumerate(header_lower):

        if (
            "doctor" in h
            or "name" in h
            or h in ["নাম", "ডাক্তারদের নাম"]
        ):
            if name_index is None:
                name_index = i

        if "designation" in h or "পদবী" in h or "পদবি" in h:
            designation_index = i

        if (
            "degree" in h
            or "qualification" in h
            or "ডিগ্রী" in h
            or "ডিগ্রি" in h
        ):
            degree_index = i

    # কিছু টেবিলে "নাম" + "পদবী ও ডিগ্রী" থাকে
    combined_index = None

    for i, h in enumerate(header_lower):
        if "পদবী" in h or "পদবি" in h:
            if "ডিগ" in h:
                combined_index = i
                break

    if name_index is None:
        return []

    doctors = []

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])

        if not cells:
            continue

        values = [
            clean(c.get_text(" ", strip=True))
            for c in cells
        ]

        # পর্যাপ্ত data না থাকলে বাদ
        if name_index >= len(values):
            continue

        name = values[name_index]

        if not name:
            continue

        # Serial number যেন name না হয়
        if re.fullmatch(r"[\d০-৯.()\- ]+", name):
            continue

        # শুধু প্রকৃত ডাক্তারদের record রাখব
        # Official RMCH doctor tables-এ সাধারণত Dr./ডাঃ থাকে।
        doctor_name = name.lower()

        if not (
            doctor_name.startswith("dr.")
            or doctor_name.startswith("dr ")
            or doctor_name.startswith("ডাঃ")
            or doctor_name.startswith("ডা.")
            or doctor_name.startswith("অধ্যাপক ডাঃ")
        ):
            continue

        designation = ""
        qualification = ""

        # English table
        if designation_index is not None and designation_index < len(values):
            designation = values[designation_index]

        if degree_index is not None and degree_index < len(values):
            qualification = values[degree_index]

        # Bengali combined field
        if combined_index is not None and combined_index < len(values):
            designation, qualification = split_designation_qualification(
                values[combined_index]
            )

        # Mobile নম্বর যেন qualification-এ ঢুকে না যায়
        if is_phone(qualification):
            qualification = ""

        if is_phone(designation):
            designation = ""

        # কিছু ক্ষেত্রে designation + degree একই cell-এ এসেছে।
        if designation and qualification:
            pass

        elif designation and not qualification:
            d, q = split_designation_qualification(designation)

            if d and q:
                designation = d
                qualification = q

        # আবার কিছু Bengali table-এ degree field-এ
        # "সহকারী অধ্যাপক ডি.এল.ও (ইএনটি)"-এর মতো
        # পুরো তথ্য একসাথে চলে আসে।
        elif qualification:
            d, q = split_designation_qualification(qualification)

            if d and q:
                designation = d
                qualification = q

        # ভুলভাবে qualification-এ চলে যাওয়া বিভাগীয় প্রধান ঠিক করা
        if qualification.startswith("ও বিভাগীয় প্রধান"):
            designation = clean(
                designation + " ও বিভাগীয় প্রধান"
            )
            qualification = clean(
                qualification[len("ও বিভাগীয় প্রধান"):]
            )

        if qualification.startswith("ও বিভাগীয প্রধান"):
            designation = clean(
                designation + " ও বিভাগীয় প্রধান"
            )
            qualification = clean(
                qualification[len("ও বিভাগীয প্রধান"):]
            )

        # খুব সন্দেহজনক record বাদ
        if len(name) < 3:
            continue

        # Nurse / cleaner / staff ইত্যাদি বাদ
        bad_words = [
            "nurse",
            "staff nurse",
            "cleaner",
            "ward boy",
            "aya",
            "আয়া",
            "নার্স",
            "সিস্টার",
            "ক্লিনার",
            "ওয়ার্ড বয়",
            "ওয়ার্ডবয়",
        ]

        combined_text = (
            name + " " + designation + " " + qualification
        ).lower()

        if any(word.lower() in combined_text for word in bad_words):
            continue

        doctors.append({
            "name": name,
            "designation": designation,
            "department": department,
            "specialty": "",
            "qualification": qualification,
            "workplace": "Rajshahi Medical College Hospital",
            "bmdc_reg_no": "",
            "professional_contact": "",
            "source": source,
            "last_updated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        })

    return doctors


def collect(url, department):
    print(f"Collecting: {url}")
    print(f"Department: {department}")

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

    except Exception as e:
        print("ERROR:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    all_doctors = []

    for table in soup.find_all("table"):
        doctors = parse_table(
            table,
            department,
            url
        )

        all_doctors.extend(doctors)

    return all_doctors


def main():

    all_doctors = []

    for url, department in SEEDS:
        doctors = collect(url, department)
        all_doctors.extend(doctors)

        print("Found:", len(doctors))
        print()

    # duplicate বাদ
    unique = {}

    for doctor in all_doctors:

        key = (
            clean(doctor["name"]).lower(),
            doctor["department"]
        )

        if key not in unique:
            unique[key] = doctor

    all_doctors = list(unique.values())

    all_doctors.sort(
        key=lambda x: (
            x["department"],
            x["name"]
        )
    )

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    data = {
        "title": "Bangladesh Doctor Database",
        "description": "Doctors collected from official Rajshahi Medical College Hospital websites",
        "last_updated": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "count": len(all_doctors),
        "doctors": all_doctors
    }

    with open(
        OUT,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("================================")
    print("Doctor database updated")
    print("Doctors:", len(all_doctors))
    print("Saved:", OUT)
    print("================================")


if __name__ == "__main__":
    main()
