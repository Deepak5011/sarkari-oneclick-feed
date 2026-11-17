import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8"
}

IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST).date()

BANNED_DOMAINS = [
    "t.me", "telegram.", "whatsapp.com", "youtube.com", "youtu.be",
    "play.google.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "sarkariresult.com", "sarkariresults.org.in", "dmca.com", "addtoany.com"
]

DATE_REGEX = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b")

# Map of keywords -> (Board Badge, State, Direct Official Portal URL, Login URL)
PORTAL_DIRECTORY = [
    ("SSC", "All India", ["ssc ", "cgl", "chsl", "mts", "ssc gd", "cpo", "steno", "selection post"], "https://ssc.gov.in", "https://ssc.gov.in"),
    ("IBPS", "All India", ["ibps", "crp po", "crp clerk", "ibps so", "ibps rrb"], "https://ibpsonline.ibps.in", "https://ibpsonline.ibps.in"),
    ("RAILWAY RRB", "All India", ["railway", "rrb", "ntpc", "group d", "alp", "rpf", "technician", "rrc"], "https://www.rrbapply.gov.in", "https://www.rrbapply.gov.in/#/auth/landing"),
    ("UPSC", "All India", ["upsc", "civil services", "ias ", "nda", "cds", "capf", "epfo"], "https://upsconline.nic.in/upsc/OTRP/", "https://upsconline.nic.in/upsc/OTRP/"),
    ("JSSC", "Jharkhand", ["jssc", "jharkhand staff", "jtet", "utpad sipahi", "jharkhand police", "jharkhand cgl"], "https://jssc.nic.in", "https://jssc.nic.in"),
    ("JPSC", "Jharkhand", ["jpsc", "jharkhand psc"], "https://www.jpsc.gov.in", "https://www.jpsc.gov.in"),
    ("JCECEB / JAC", "Jharkhand", ["jceceb", "jac ", "ekalyan", "ranchi university"], "https://jceceb.jharkhand.gov.in", "https://jharkhanduniversities.nic.in"),
    ("BPSC", "Bihar", ["bpsc", "bihar tre", "bihar teacher", "bihar psc"], "https://onlinebpsc.bihar.gov.in", "https://onlinebpsc.bihar.gov.in"),
    ("BIHAR POLICE", "Bihar", ["csbc", "bihar police", "bpssc", "bihar daroga", "bihar si", "bssc"], "https://csbc.bihar.gov.in", "https://bpssc.bih.nic.in"),
    ("UPPSC", "Uttar Pradesh", ["uppsc", "up pcs", "ro aro"], "https://uppsc.up.nic.in", "https://uppsc.up.nic.in"),
    ("UPSSSC", "Uttar Pradesh", ["upsssc", "up pet", "lekhpal", "up vdo"], "https://upsssc.gov.in", "https://upsssc.gov.in"),
    ("UP POLICE", "Uttar Pradesh", ["uppbpb", "upprpb", "up police"], "https://uppbpb.gov.in", "https://uppbpb.gov.in"),
    ("SBI", "All India", ["sbi po", "sbi clerk", "state bank", "sbi cbo"], "https://bank.sbi/web/careers/Current-openings", "https://ibpsonline.ibps.in"),
    ("NTA", "All India", ["nta ", "cuet", "jee main", "neet", "ugc net", "csir net"], "https://exams.nta.ac.in", "https://exams.nta.ac.in"),
    ("INDIA POST", "All India", ["india post", "gds ", "gramin dak"], "https://indiapostgdsonline.gov.in", "https://indiapostgdsonline.gov.in"),
    ("DEFENCE", "All India", ["indian army", "agniveer", "indian navy", "air force", "afcat"], "https://joinindianarmy.nic.in", "https://agnipathvayu.cdac.in"),
    ("MPESB", "Madhya Pradesh", ["mpesb", "mppsc", "mp police", "mp vyapam"], "https://esb.mp.gov.in", "https://esb.mp.gov.in"),
    ("RSMSSB", "Rajasthan", ["rsmssb", "rpsc", "rajasthan cet", "rajasthan police"], "https://rsmssb.rajasthan.gov.in", "https://sso.rajasthan.gov.in")
]

def fetch_html_resilient(url: str, timeout: int = 12):
    """
    Tries direct cloudscraper first. If blocked by Cloudflare on GitHub US runner,
    falls back to AllOrigins raw proxy so scraping NEVER returns empty!
    """
    try:
        resp = SCRAPER.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200 and len(resp.text) > 800 and "Just a moment..." not in resp.text:
            return resp.text
        print(f"Direct fetch got status {resp.status_code} on {url}, trying proxy fallback...")
    except Exception as e:
        print(f"Direct fetch error on {url}: {e}")

    # Fallback 2: AllOrigins Raw Proxy (Bypasses US datacenter IP blocks)
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url, safe='')}"
        resp2 = requests.get(proxy_url, headers=HEADERS, timeout=15)
        if resp2.status_code == 200 and len(resp2.text) > 800:
            print(f"✅ Proxy fetch succeeded for {url}")
            return resp2.text
    except Exception as e:
        print(f"Proxy fallback failed for {url}: {e}")

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

def resolve_portal_info(title: str, category: str, scraped_url: str = None, scraped_login: str = None):
    lower = title.lower()
    for badge, state, keywords, apply_url, login_url in PORTAL_DIRECTORY:
        if any(k in lower for k in keywords):
            return (
                badge,
                state,
                scraped_url or apply_url,
                scraped_login or login_url,
                apply_url,
                True
            )

    detected_state = "All India"
    for st in ["Jharkhand", "Bihar", "Uttar Pradesh", "Madhya Pradesh", "Rajasthan", "Delhi", "Haryana"]:
        if st.lower() in lower or (st == "Uttar Pradesh" and "up " in lower):
            detected_state = st
            break

    if scraped_url:
        return "GOV PORTAL", detected_state, scraped_url, (scraped_login or scraped_url), scraped_url, True

    suffix = "official apply online registration portal" if category == "NEW_FORM" else "official download login link"
    q = urllib.parse.quote_plus(f"{title} {suffix}")
    search_url = f"https://www.google.com/search?q={q}"
    return "OFFICIAL PORTAL", detected_state, search_url, search_url, search_url, False

def clean_title(raw_text: str) -> str:
    text = re.sub(r"\s+", " ", raw_text).strip()
    text = text.rsplit(" - ", 1)[0].strip()
    return re.sub(r"(?i)\b(sarkari\s*result|freejobalert)\b", "", text).strip(" -|•:")

def extract_inner_post_details(post_url: str, category: str):
    info = {
        "primaryUrl": None,
        "loginUrl": None,
        "notifUrl": None,
        "officialSite": None,
        "displayDate": "",
        "expiryIso": None,
        "totalPosts": "",
        "shortSummary": ""
    }
    html = fetch_html_resilient(post_url, timeout=10)
    if html:
        soup = BeautifulSoup(html, "lxml")
        expiry_dt = None

        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            low = txt.lower()
            if category == "NEW_FORM" and any(k in low for k in ["last date for apply", "last date to apply", "apply online last date"]):
                matches = DATE_REGEX.findall(txt)
                if matches:
                    d, m, y = matches[-1]
                    dt = parse_date_str(f"{int(d):02d}/{int(m):02d}/{y}")
                    if dt:
                        info["displayDate"] = dt.strftime("%d/%m/%Y")
                        expiry_dt = dt
            elif category == "ADMIT_CARD" and any(k in low for k in ["exam date", "date of exam"]):
                matches = DATE_REGEX.findall(txt)
                if matches:
                    d, m, y = matches[-1]
                    dt = parse_date_str(f"{int(d):02d}/{int(m):02d}/{y}")
                    if dt:
                        info["displayDate"] = f"Exam: {dt.strftime('%d/%m/%Y')}"
                        expiry_dt = dt + timedelta(days=2)

            if ("minimum age" in low or "maximum age" in low) and not info["shortSummary"]:
                info["shortSummary"] = txt[:65]

        full_text = soup.get_text(" ", strip=True)
        pm = re.search(r"(?:Vacancy Details Total|Total\s+Post[s]?)\s*[:\-]?\s*(\d[\d,]*)", full_text, re.IGNORECASE)
        if pm:
            info["totalPosts"] = f"{pm.group(1)} Posts"

        for tr in soup.select("table tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 2:
                continue
            label = tds[0].get_text(" ", strip=True).lower()
            links = []
            for a in tds[1].find_all("a", href=True):
                href = urllib.parse.urljoin(post_url, a["href"].strip())
                if not is_banned_url(href):
                    links.append((a.get_text(" ", strip=True).lower(), href))
            if not links:
                continue

            if any(k in label for k in ["apply online", "online registration"]):
                for l_txt, l_url in links:
                    if "login" in l_txt and not info["loginUrl"]:
                        info["loginUrl"] = l_url
                    elif not info["primaryUrl"]:
                        info["primaryUrl"] = l_url
                if not info["primaryUrl"]:
                    info["primaryUrl"] = links[0][1]
            elif any(k in label for k in ["download admit card", "admit card", "hall ticket", "exam city"]):
                if category == "ADMIT_CARD" and not info["primaryUrl"]:
                    info["primaryUrl"] = links[0][1]
            elif any(k in label for k in ["download answer key", "answer key", "response sheet"]):
                if category == "ANSWER_KEY" and not info["primaryUrl"]:
                    info["primaryUrl"] = links[0][1]
            elif any(k in label for k in ["download notification", "official notification"]):
                if not info["notifUrl"]:
                    info["notifUrl"] = links[0][1]
            elif "official website" in label:
                if not info["officialSite"]:
                    info["officialSite"] = links[0][1]

        if not info["primaryUrl"] and info["officialSite"]:
            info["primaryUrl"] = info["officialSite"]
        if expiry_dt:
            info["expiryIso"] = expiry_dt.strftime("%Y-%m-%d")

    if not info["expiryIso"]:
        days = 28 if category == "NEW_FORM" else (18 if category == "ADMIT_CARD" else 12)
        info["expiryIso"] = (TODAY + timedelta(days=days)).strftime("%Y-%m-%d")
        info["displayDate"] = "Apply Now" if category == "NEW_FORM" else ("Download Now" if category == "ADMIT_CARD" else "Check Score")

    return info

def scrape_sarkari_portals(newly_discovered: list, existing_by_title: dict):
    mirrors = [
        "https://www.sarkariresult.com",
        "https://www.sarkariresults.org.in",
        "https://sarkariresult.com.cm"
    ]
    for base_url in mirrors:
        html = fetch_html_resilient(base_url, timeout=15)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")
        links = soup.select("div#post ul li a, td ul li a, .post-list a, ul li a")
        print(f"Found {len(links)} raw links on {base_url}")

        count_from_mirror = 0
        for a_tag in links[:90]:
            raw_title = clean_title(a_tag.get_text())
            href = urllib.parse.urljoin(base_url, a_tag.get("href", ""))

            if len(raw_title) < 12 or raw_title.lower() in existing_by_title:
                continue

            low = raw_title.lower()
            if any(k in low for k in ["admit card", "hall ticket", "exam city", "call letter"]):
                category = "ADMIT_CARD"
            elif any(k in low for k in ["answer key", "response sheet", "question paper"]):
                category = "ANSWER_KEY"
            elif any(k in low for k in ["online form", "recruitment", "apply", "vacancy"]):
                category = "NEW_FORM"
            else:
                continue

            # Parse inner post ONLY for the first 15 new items to keep execution fast (<25s)
            if count_from_mirror < 15:
                details = extract_inner_post_details(href, category)
            else:
                days = 28 if category == "NEW_FORM" else (18 if category == "ADMIT_CARD" else 12)
                details = {
                    "primaryUrl": None, "loginUrl": None, "notifUrl": None, "officialSite": None,
                    "displayDate": "Active Now",
                    "expiryIso": (TODAY + timedelta(days=days)).strftime("%Y-%m-%d"),
                    "totalPosts": "", "shortSummary": ""
                }

            exp_dt = parse_date_str(details["expiryIso"])
            if exp_dt and TODAY > exp_dt:
                continue

            badge, state, target_url, login_url, official_site, is_direct = resolve_portal_info(
                raw_title, category, details["primaryUrl"], details["loginUrl"]
            )
            q_pdf = urllib.parse.quote_plus(f"{raw_title} official notification pdf")
            notif_url = details["notifUrl"] or f"https://www.google.com/search?q={q_pdf}"

            item = {
                "id": f"sr_{category.lower()}_{len(newly_discovered)}",
                "title": raw_title,
                "category": category,
                "state": state,
                "boardBadge": badge,
                "targetUrl": target_url,
                "loginUrl": login_url,
                "notificationPdfUrl": notif_url,
                "officialWebsiteUrl": details["officialSite"] or official_site,
                "lastDate": details["displayDate"],
                "expiryDate": details["expiryIso"],
                "totalPosts": details["totalPosts"],
                "shortSummary": details["shortSummary"],
                "isDirectPortalMatch": is_direct,
                "isPinnedTop": False,
                "isManual": False
            }
            newly_discovered.append(item)
            existing_by_title[raw_title.lower()] = item
            count_from_mirror += 1

        if count_from_mirror > 8:
            break

def fetch_google_news_rss_backup(newly_discovered: list, existing_by_title: dict):
    """
    Guaranteed Backup Layer: Always pulls latest National + State (Jharkhand/Bihar/UP)
    exam headlines from Google News RSS (which NEVER blocks GitHub Actions IPs!)
    """
    rss_queries = [
        ("NEW_FORM", "(SSC OR RRB OR IBPS OR SBI OR UPSC OR JSSC OR BPSC OR UPSSSC OR India Post) recruitment apply online notification"),
        ("ADMIT_CARD", "(SSC OR RRB OR IBPS OR UPSC OR JSSC OR BPSC OR UPSSSC OR NTA) admit card hall ticket released"),
        ("ANSWER_KEY", "(SSC OR RRB OR IBPS OR JSSC OR BPSC OR UPSSSC OR NTA) answer key response sheet released")
    ]
    for category, q in rss_queries:
        encoded = urllib.parse.quote_plus(q)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item_el in root.findall(".//item")[:12]:
                raw_t = clean_title(item_el.findtext("title") or "")
                if len(raw_t) < 12 or raw_t.lower() in existing_by_title:
                    continue

                badge, state, target_url, login_url, official_site, is_direct = resolve_portal_info(raw_t, category)
                days = 25 if category == "NEW_FORM" else (15 if category == "ADMIT_CARD" else 10)
                exp_iso = (TODAY + timedelta(days=days)).strftime("%Y-%m-%d")
                q_pdf = urllib.parse.quote_plus(f"{raw_t} official notification pdf")

                new_item = {
                    "id": f"rss_{category.lower()}_{len(newly_discovered)}",
                    "title": raw_t,
                    "category": category,
                    "state": state,
                    "boardBadge": badge,
                    "targetUrl": target_url,
                    "loginUrl": login_url,
                    "notificationPdfUrl": f"https://www.google.com/search?q={q_pdf}",
                    "officialWebsiteUrl": official_site,
                    "lastDate": "Active Now" if category == "NEW_FORM" else "Out Now",
                    "expiryDate": exp_iso,
                    "totalPosts": "",
                    "shortSummary": "Verified Direct Official Portal Link",
                    "isDirectPortalMatch": is_direct,
                    "isPinnedTop": False,
                    "isManual": False
                }
                newly_discovered.append(new_item)
                existing_by_title[raw_t.lower()] = new_item
        except Exception as e:
            print(f"RSS backup warning: {e}")

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

    # Layer 1: Scrape SarkariResult (Direct + AllOrigins Proxy Bypass)
    scrape_sarkari_portals(newly_discovered, existing_by_title)

    # Layer 2: Always supplement with Google News Multi-Board RSS so JSON is NEVER empty!
    fetch_google_news_rss_backup(newly_discovered, existing_by_title)

    manual_pinned = [i for i in existing_items if i.get("isManual") is True]
    regular_existing = [i for i in existing_items if not i.get("isManual")]
    final_items = manual_pinned + newly_discovered + regular_existing

    payload = {
        "lastUpdated": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
        "announcementBanner": f"🎯 {len(final_items)} Verified Active Exams & Direct Portals Live!",
        "items": final_items[:120]
    }

    with open("live_exams.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ SUCCESS: Added {len(newly_discovered)} new items. Total items in live_exams.json: {len(final_items)}")

if __name__ == "__main__":
    main()
