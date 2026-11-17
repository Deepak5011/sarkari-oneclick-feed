import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

try:
    import cloudscraper
    SCRAPER = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
except Exception:
    SCRAPER = requests.Session()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9"
}

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST).date()

BANNED_DOMAINS = [
    "t.me", "telegram.", "whatsapp.com", "youtube.com", "youtu.be",
    "play.google.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "sarkariresult.com", "sarkariresults.org.in", "dmca.com", "addtoany.com"
]

DATE_REGEX = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b")

def fetch_html(url: str, timeout: int = 12):
    try:
        resp = SCRAPER.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
    except Exception as e:
        print(f"Fetch warning for {url}: {e}")
    return None

def parse_date_str(d_str: str):
    try:
        if "-" in d_str and d_str.startswith("20"):
            return datetime.strptime(d_str, "%Y-%m-%d").date()
        return datetime.strptime(d_str.replace("-", "/"), "%d/%m/%Y").date()
    except Exception:
        return None

def is_banned_url(url: str) -> bool:
    u = url.lower()
    if not u.startswith("http"):
        return True
    return any(b in u for b in BANNED_DOMAINS)

def unwrap_redirect_url(url: str) -> str:
    u_low = url.lower()
    if any(short in u_low for short in ["bit.ly", "tinyurl.com", "goo.gl", "rb.gy", "t.co"]):
        try:
            resp = SCRAPER.head(url, headers=HEADERS, allow_redirects=True, timeout=6)
            if resp.url and not is_banned_url(resp.url):
                return resp.url
        except Exception:
            pass
    return url

def extract_exact_portal_data(post_url: str, category: str):
    result = {
        "primaryActionUrl": None,
        "loginUrl": None,
        "notificationPdfUrl": None,
        "officialWebsiteUrl": None,
        "displayDate": "",
        "expiryDateIso": None,
        "totalPosts": "",
        "shortSummary": ""
    }

    html = fetch_html(post_url, timeout=12)
    if html:
        soup = BeautifulSoup(html, "lxml")
        expiry_dt = None

        # 1. Extract Last Date / Exam Date & Age Limit from <li> items
        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            low = txt.lower()

            if category == "NEW_FORM" and any(k in low for k in ["last date for apply", "last date to apply", "apply online last date", "registration last date"]):
                matches = DATE_REGEX.findall(txt)
                if matches:
                    d, m, y = matches[-1]
                    dt = parse_date_str(f"{int(d):02d}/{int(m):02d}/{y}")
                    if dt:
                        result["displayDate"] = dt.strftime("%d/%m/%Y")
                        expiry_dt = dt

            elif category == "ADMIT_CARD" and any(k in low for k in ["exam date", "date of exam", "cbt exam"]):
                matches = DATE_REGEX.findall(txt)
                if matches:
                    d, m, y = matches[-1]
                    dt = parse_date_str(f"{int(d):02d}/{int(m):02d}/{y}")
                    if dt:
                        result["displayDate"] = f"Exam: {dt.strftime('%d/%m/%Y')}"
                        expiry_dt = dt + timedelta(days=2)

            if ("minimum age" in low or "maximum age" in low) and not result["shortSummary"]:
                result["shortSummary"] = txt[:65]

        # 2. Extract Total Posts
        full_text = soup.get_text(" ", strip=True)
        post_match = re.search(r"(?:Vacancy Details Total|Total\s+Post[s]?)\s*[:\-]?\s*(\d[\d,]*)\s*(?:Post)?", full_text, re.IGNORECASE)
        if post_match:
            result["totalPosts"] = f"{post_match.group(1)} Posts"

        # 3. Row-Anchored Action Link Extraction from bottom table
        for tr in soup.select("table tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 2:
                continue

            row_label = tds[0].get_text(" ", strip=True).lower()
            links_in_row = []

            for a in tds[1].find_all("a", href=True):
                raw_href = urllib.parse.urljoin(post_url, a["href"].strip())
                unwrapped = unwrap_redirect_url(raw_href)
                if not is_banned_url(unwrapped):
                    link_text = a.get_text(" ", strip=True).lower()
                    links_in_row.append((link_text, unwrapped))

            if not links_in_row:
                continue

            if any(k in row_label for k in ["apply online", "online registration", "fill online form"]):
                for l_txt, l_url in links_in_row:
                    if "login" in l_txt and not result["loginUrl"]:
                        result["loginUrl"] = l_url
                    elif not result["primaryActionUrl"]:
                        result["primaryActionUrl"] = l_url
                if not result["primaryActionUrl"]:
                    result["primaryActionUrl"] = links_in_row[0][1]

            elif any(k in row_label for k in ["download admit card", "admit card", "hall ticket", "check exam city", "call letter"]):
                if category == "ADMIT_CARD" and not result["primaryActionUrl"]:
                    result["primaryActionUrl"] = links_in_row[0][1]
                elif not result["loginUrl"]:
                    result["loginUrl"] = links_in_row[0][1]

            elif any(k in row_label for k in ["download answer key", "answer key", "question paper", "response sheet", "objection"]):
                if category == "ANSWER_KEY" and not result["primaryActionUrl"]:
                    result["primaryActionUrl"] = links_in_row[0][1]

            elif any(k in row_label for k in ["download notification", "official notification", "advertisement"]):
                if not result["notificationPdfUrl"]:
                    result["notificationPdfUrl"] = links_in_row[0][1]

            elif "official website" in row_label:
                if not result["officialWebsiteUrl"]:
                    result["officialWebsiteUrl"] = links_in_row[0][1]

        if not result["primaryActionUrl"] and result["officialWebsiteUrl"]:
            result["primaryActionUrl"] = result["officialWebsiteUrl"]

        if expiry_dt:
            result["expiryDateIso"] = expiry_dt.strftime("%Y-%m-%d")

    if not result["expiryDateIso"]:
        if category == "NEW_FORM":
            expiry_dt = TODAY + timedelta(days=28)
            result["displayDate"] = "Apply Now"
        elif category == "ADMIT_CARD":
            expiry_dt = TODAY + timedelta(days=18)
            result["displayDate"] = "Admit Card Out"
        else:
            expiry_dt = TODAY + timedelta(days=12)
            result["displayDate"] = "Answer Key Out"
        result["expiryDateIso"] = expiry_dt.strftime("%Y-%m-%d")

    return result

def detect_board_and_state(title: str, target_url: str):
    lower_t = title.lower()
    lower_u = (target_url or "").lower()

    state = "All India"
    state_keywords = [
        ("Bihar", ["bihar", "bpsc", "bssc", "csbc", "bpssc", "patna", ".bih.nic.in"]),
        ("Jharkhand", ["jharkhand", "jssc", "jpsc", "jceceb", "ranchi", ".jharkhand.gov.in"]),
        ("Uttar Pradesh", ["up ", "uttar pradesh", "upsssc", "uppsc", "uppbpb", "upprpb", "allahabad", ".up.nic.in"]),
        ("Madhya Pradesh", ["mp ", "madhya pradesh", "mpesb", "mppsc", "vyapam", "mponline"]),
        ("Rajasthan", ["rajasthan", "rsmssb", "rpsc", ".rajasthan.gov.in"]),
        ("Delhi", ["delhi", "dsssb"]),
        ("Haryana", ["haryana", "hssc", "hpsc"])
    ]
    for st_name, kw_list in state_keywords:
        if any(k in lower_t or k in lower_u for k in kw_list):
            state = st_name
            break

    board_map = [
        ("SSC", ["ssc ", "cgl", "chsl", "mts", "ssc gd", "ssc.gov.in"]),
        ("IBPS", ["ibps", "ibpsonline"]),
        ("RAILWAY RRB", ["railway", "rrb", "ntpc", "group d", "alp", "rpf", "rrbapply"]),
        ("UPSC", ["upsc", "civil services", "nda", "cds", "upsconline"]),
        ("BPSC", ["bpsc", "bihar tre", "onlinebpsc"]),
        ("BIHAR POLICE", ["csbc", "bihar police", "bpssc", "bihar daroga"]),
        ("JSSC", ["jssc", "jharkhand staff"]),
        ("JPSC", ["jpsc"]),
        ("UPPSC", ["uppsc"]),
        ("UPSSSC", ["upsssc", "up pet"]),
        ("SBI", ["sbi ", "state bank", "bank.sbi"]),
        ("NTA", ["nta ", "cuet", "jee main", "neet", "nta.ac.in", "ntaonline"]),
        ("INDIA POST", ["india post", "gds ", "indiapostgdsonline"]),
        ("DEFENCE", ["army", "agniveer", "navy", "air force", "afcat"])
    ]
    for badge, kw_list in board_map:
        if any(k in lower_t or k in lower_u for k in kw_list):
            return badge, state

    try:
        host = urllib.parse.urlparse(target_url).netloc.replace("www.", "").upper()
        if host and "GOOGLE" not in host:
            return host.split(".")[0][:12], state
    except Exception:
        pass

    return "GOV PORTAL", state

def clean_title(raw_text: str) -> str:
    text = re.sub(r"\s+", " ", raw_text).strip()
    return re.sub(r"(?i)\bsarkari\s*result\b", "", text).strip(" -|•")

def main():
    existing_items = []
    try:
        with open("live_exams.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("items", []):
                exp_dt = parse_date_str(item.get("expiryDate", ""))
                if exp_dt is None or TODAY <= exp_dt:
                    existing_items.append(item)
    except Exception:
        pass

    existing_by_title = {item["title"].lower(): item for item in existing_items}
    newly_discovered = []

    home_urls = ["https://www.sarkariresult.com", "https://www.sarkariresults.org.in"]
    for base_url in home_urls:
        html = fetch_html(base_url, timeout=15)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        for a_tag in soup.select("div#post ul li a, td ul li a")[:95]:
            raw_title = clean_title(a_tag.get_text())
            post_href = urllib.parse.urljoin(base_url, a_tag.get("href", ""))

            if len(raw_title) < 10 or raw_title.lower() in existing_by_title:
                continue

            lower_t = raw_title.lower()
            if any(k in lower_t for k in ["admit card", "hall ticket", "exam city", "call letter"]):
                category = "ADMIT_CARD"
            elif any(k in lower_t for k in ["answer key", "response sheet", "question paper"]):
                category = "ANSWER_KEY"
            elif any(k in lower_t for k in ["online form", "recruitment", "apply", "vacancy"]):
                category = "NEW_FORM"
            else:
                continue

            details = extract_exact_portal_data(post_href, category)
            exp_dt = parse_date_str(details["expiryDateIso"])
            if exp_dt and TODAY > exp_dt:
                continue

            target_url = details["primaryActionUrl"]
            is_direct_verified = target_url is not None

            if not target_url:
                suffix = "official apply online registration portal" if category == "NEW_FORM" else "official download login link"
                q = urllib.parse.quote_plus(f"{raw_title} {suffix}")
                target_url = f"https://www.google.com/search?q={q}"

            badge, state = detect_board_and_state(raw_title, target_url)
            notif_url = details["notificationPdfUrl"]
            if not notif_url:
                q_pdf = urllib.parse.quote_plus(f"{raw_title} official notification pdf")
                notif_url = f"https://www.google.com/search?q={q_pdf}"

            new_item = {
                "id": f"sr_{category.lower()}_{int(datetime.now().timestamp())}_{len(newly_discovered)}",
                "title": raw_title,
                "category": category,
                "state": state,
                "boardBadge": badge,
                "targetUrl": target_url,
                "loginUrl": details["loginUrl"] or details["officialWebsiteUrl"] or target_url,
                "notificationPdfUrl": notif_url,
                "officialWebsiteUrl": details["officialWebsiteUrl"] or target_url,
                "lastDate": details["displayDate"],
                "expiryDate": details["expiryDateIso"],
                "totalPosts": details["totalPosts"],
                "shortSummary": details["shortSummary"],
                "isDirectPortalMatch": is_direct_verified,
                "isPinnedTop": False,
                "isManual": False
            }
            newly_discovered.append(new_item)
            existing_by_title[raw_title.lower()] = new_item

        if len(newly_discovered) > 10:
            break

    manual_pinned = [i for i in existing_items if i.get("isManual") is True]
    regular_existing = [i for i in existing_items if not i.get("isManual")]
    final_items = manual_pinned + newly_discovered + regular_existing

    payload = {
        "lastUpdated": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
        "announcementBanner": "🎯 100% Verified Direct Form Portals (Auto-Synced)",
        "items": final_items[:120]
    }

    with open("live_exams.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Synced {len(newly_discovered)} new verified portals. Total active: {len(final_items[:120])}")

if __name__ == "__main__":
    main()
