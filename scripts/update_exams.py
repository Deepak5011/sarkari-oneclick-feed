import concurrent.futures
import hashlib
import html as html_lib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import cloudscraper
    SCRAPER = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
except Exception:
    SCRAPER = requests.Session() if requests else None

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
    "sarkariresult.com", "sarkariresults.org.in", "sarkariresult.com.cm",
    "dmca.com", "addtoany.com", "google.com/search", "google.co.in/search"
]

# Non-exam clutter keywords to exclude (certificates, scholarships, voter/pan cards)
NON_EXAM_CLUTTER_KEYWORDS = [
    "income, cast", "caste certificate", "residential certificate", "scholarship",
    "pan card", "aadhar card", "voter id", "driving licence", "ration card",
    "ayushman card", "eshram card", "abaa card", "ccc online form"
]

DATE_REGEX = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b")
DOMAIN_IN_TEXT_REGEX = re.compile(
    r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)+\.(?:gov\.in|nic\.in|org\.in|ac\.in|org|com|in))\b",
    re.IGNORECASE
)
POSTS_IN_TEXT_REGEX = re.compile(
    r"\b(\d[\d,]*)\s*(?:posts?|vacancies|vacancy)\b",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# AUTHORITATIVE DIRECT OFFICIAL PORTAL DIRECTORY (Ordered Most-Specific First)
# Format: (Board Badge, State, Keywords, Apply/Target URL, Login URL, Notice/Official URL)
# ---------------------------------------------------------------------------
PORTAL_DIRECTORY = [
    # --- UTTAR PRADESH BOARDS ---
    ("UPSSSC", "Uttar Pradesh", ["upsssc", "up pet", "up lekhpal", "up vdo", "cane supervisor", "havildar instructor"],
     "https://upsssc.gov.in/AllNotifications.aspx", "https://upsssc.gov.in/Online_App/Candidate_Login.aspx", "https://upsssc.gov.in/NoticeBoard.aspx"),
    ("UPESSC", "Uttar Pradesh", ["upessc", "uphesc", "up tgt", "up pgt", "up principal", "up headmaster", "up assistant professor", "up special tet"],
     "https://apply.upessc.org/login", "https://apply.upessc.org/login", "https://upessc.up.gov.in/"),
    ("UPPSC", "Uttar Pradesh", ["uppsc", "up pcs", "ro / aro", "ro aro"],
     "https://uppsc.up.nic.in/CandidatePages/Notifications.aspx", "https://uppsc.up.nic.in/CandidatePages/OTR_App/Candidate_Login.aspx", "https://uppsc.up.nic.in/"),
    ("UP POLICE", "Uttar Pradesh", ["uppbpb", "upprpb", "up police"],
     "https://uppbpb.gov.in/", "https://uppbpb.gov.in/", "https://uppbpb.gov.in/"),
    ("UP ANGANWADI", "Uttar Pradesh", ["up anganwadi", "anganwadi bharti"],
     "https://upanganwadibharti.in/", "https://upanganwadibharti.in/", "https://upanganwadibharti.in/"),
    ("ALLAHABAD HC", "Uttar Pradesh", ["allahabad hc", "allahabad high court"],
     "https://exams.nta.ac.in/AHC/", "https://exams.nta.ac.in/AHC/", "https://www.allahabadhighcourt.in/calendar/itemWiseList.jsp?group=7"),

    # --- JHARKHAND BOARDS (Updated to jssc.jharkhand.gov.in & jpsc.jharkhand.gov.in) ---
    ("JSSC", "Jharkhand", ["jssc", "jharkhand staff", "jtet", "utpad sipahi", "jharkhand police", "jharkhand cgl", "jgglcce", "pgttce", "jcce"],
     "https://jssc.jharkhand.gov.in/user/login", "https://jssc.jharkhand.gov.in/user/login", "https://jssc.jharkhand.gov.in/"),
    ("JPSC", "Jharkhand", ["jpsc", "jharkhand psc", "jharkhand civil services"],
     "https://jpsc.jharkhand.gov.in/", "https://jpsc.jharkhand.gov.in/", "https://jpsc.jharkhand.gov.in/"),
    ("JCECEB / JAC", "Jharkhand", ["jceceb", "jac ", "ekalyan", "ranchi university"],
     "https://jceceb.jharkhand.gov.in/", "https://jharkhanduniversities.nic.in/", "https://jceceb.jharkhand.gov.in/"),

    # --- BIHAR BOARDS ---
    ("BIHAR VIDHAN SABHA", "Bihar", ["bihar vidhan sabha"],
     "https://vidhansabha.bih.nic.in/", "https://vidhansabha.bih.nic.in/", "https://vidhansabha.bih.nic.in/"),
    ("BPSC", "Bihar", ["bpsc", "bihar tre", "bihar teacher", "bihar psc", "bihar apo"],
     "https://onlinebpsc.bihar.gov.in/", "https://onlinebpsc.bihar.gov.in/", "https://www.bpsc.bih.nic.in/"),
    ("BSSC", "Bihar", ["bssc", "bihar ssc", "bihar inter level", "blet", "bihar library"],
     "https://bssc.bihar.gov.in/NoticeBoard.htm", "https://bssc.bihar.gov.in/NoticeBoard.htm", "https://bssc.bihar.gov.in/NoticeBoard.htm"),
    ("BIHAR POLICE", "Bihar", ["csbc", "bihar police", "bpssc", "bihar daroga", "bihar si", "btsc"],
     "https://csbc.bihar.gov.in/", "https://bpssc.bih.nic.in/", "https://csbc.bihar.gov.in/"),

    # --- DELHI, MP, RAJASTHAN & OTHER STATE BOARDS ---
    ("DSSSB", "All India", ["dsssb"],
     "https://dsssbonline.nic.in/", "https://dsssbonline.nic.in/", "https://dsssb.delhi.gov.in/current-vacancies"),
    ("MP HIGH COURT", "Madhya Pradesh", ["mphc", "mp high court"],
     "https://cdn.digialm.com//EForms/configuredHtml/772/101789/login.html", "https://cdn.digialm.com//EForms/configuredHtml/772/101789/login.html", "https://mphc.gov.in/recruitment-result"),
    ("MPESB", "Madhya Pradesh", ["mpesb", "mppsc", "mp police", "mp vyapam", "subedar"],
     "https://esb.mp.gov.in/", "https://esb.mp.gov.in/", "https://esb.mp.gov.in/"),
    ("RSSB / RPSC", "Rajasthan", ["rsmssb", "rssb", "rpsc", "rajasthan cet", "rajasthan police", "rajasthan state eligibility"],
     "https://sso.rajasthan.gov.in/", "https://sso.rajasthan.gov.in/", "https://rssb.rajasthan.gov.in/advertisements"),
    ("UKPSC", "All India", ["ukpsc", "uttarakhand psc"],
     "https://pscuk.net.in/", "https://pscuk.net.in/", "https://psc.uk.gov.in/candidate-corner/recruitment"),
    ("GSSSB", "All India", ["gsssb", "ojas", "gujarat"],
     "https://ojas.gujarat.gov.in/", "https://ojas.gujarat.gov.in/", "https://gsssb.gujarat.gov.in/"),
    ("HPRCA", "All India", ["hprca", "hp patwari", "himachal"],
     "https://hprca.hp.gov.in/", "https://hprca.hp.gov.in/", "https://hprca.hp.gov.in/"),
    ("OPSC", "All India", ["opsc", "odisha psc"],
     "https://www.opsc.gov.in/", "https://www.opsc.gov.in/", "https://www.opsc.gov.in/"),
    ("CSPDCL", "All India", ["cspdcl", "cspc", "chhattisgarh state power"],
     "https://cspc.co.in/cspc/en/recruitment", "https://cspc.co.in/cspc/en/recruitment", "https://cspc.co.in/cspc/en/recruitment"),
    ("KERALA HC", "All India", ["kerala high court"],
     "https://hckrecruitment.keralacourts.in/", "https://hckrecruitment.keralacourts.in/", "https://hckrecruitment.keralacourts.in/"),
    ("MANIPUR AGRI", "All India", ["manipur agriculture"],
     "https://agrimanipur.mn.gov.in/", "https://agrimanipur.mn.gov.in/", "https://agrimanipur.mn.gov.in/"),
    ("AAU ASSAM", "All India", ["aau recruitment", "assam agricultural"],
     "http://www.aau.ac.in/recruitment", "http://www.aau.ac.in/recruitment", "http://www.aau.ac.in/recruitment"),
    ("ASSAM SLRC", "All India", ["assam slrc", "seba"],
     "https://site.sebaonline.org/", "https://site.sebaonline.org/", "https://site.sebaonline.org/"),

    # --- DEFENCE, PARAMILITARY & PSU BOARDS ---
    ("WCL COAL INDIA", "All India", ["wcl ", "western coalfields", "coal india", "secl", "ncl "],
     "https://www.westerncoal.in/?q=node/326", "https://www.westerncoal.in/", "https://www.westerncoal.in/?q=node/326"),
    ("AFMS", "All India", ["afms", "armed forces medical"],
     "https://amcsscentry.gov.in/", "https://amcsscentry.gov.in/", "https://amcsscentry.gov.in/"),
    ("IAF AFCAT", "All India", ["afcat", "air force"],
     "https://afcat.cdac.in/afcatreg/candidate/login", "https://afcat.cdac.in/afcatreg/candidate/login", "https://afcat.cdac.in/AFCAT/"),
    ("COAST GUARD", "All India", ["coast guard", "cgept"],
     "https://cgept.parikshasaarthi.in/candidate/login", "https://cgept.parikshasaarthi.in/candidate/login", "https://joinindiancoastguard.cdac.in/"),
    ("ASSAM RIFLES", "All India", ["assam rifles"],
     "https://www.assamrifles.gov.in/onlineapp/", "https://www.assamrifles.gov.in/onlineapp/", "https://www.assamrifles.gov.in/english/recruitment.aspx"),
    ("BSF", "All India", ["bsf"],
     "https://rectt.bsf.gov.in/", "https://rectt.bsf.gov.in/", "https://rectt.bsf.gov.in/"),
    ("DEFENCE", "All India", ["indian army", "agniveer", "indian navy"],
     "https://joinindianarmy.nic.in/", "https://joinindianarmy.nic.in/", "https://joinindianarmy.nic.in/"),
    ("PGCIL", "All India", ["pgcil", "powergrid"],
     "https://www.powergrid.in/en/job-opportunities-0", "https://careers.powergrid.in/", "https://www.powergrid.in/en/job-opportunities-0"),
    ("BHEL", "All India", ["bhel"],
     "https://careers.bhel.in/", "https://careers.bhel.in/", "https://careers.bhel.in/"),
    ("ISRO", "All India", ["isro", "ursc", "icrb"],
     "https://www.isro.gov.in/Careers.html", "https://www.isro.gov.in/Careers.html", "https://www.isro.gov.in/Careers.html"),
    ("SJVN", "All India", ["sjvn"],
     "https://sjvn.nic.in/current-jobs/70", "https://sjvn.nic.in/current-jobs/70", "https://sjvn.nic.in/current-jobs/70"),
    ("ASRB ICAR", "All India", ["asrb", "icar"],
     "https://www.asrb.org.in/", "https://www.asrb.org.in/", "https://www.asrb.org.in/vacancy-notification"),
    ("NICL", "All India", ["nicl", "national insurance"],
     "https://nationalinsurance.nic.co.in/en/recruitment", "https://nationalinsurance.nic.co.in/en/recruitment", "https://nationalinsurance.nic.co.in/en/recruitment"),
    ("EXIM BANK", "All India", ["exim bank"],
     "https://www.eximbankindia.in/careers", "https://ibpsonline.ibps.in/", "https://www.eximbankindia.in/careers"),
    ("SUPREME COURT", "All India", ["supreme court"],
     "https://www.sci.gov.in/recruitments/", "https://cdn3.digialm.com/EForms/configuredHtml/32912/100521/login.html", "https://www.sci.gov.in/recruitments/"),

    # --- NATIONAL EXAMS (CTET, CAT, AIBE, NTA, INDIA POST) ---
    ("CBSE CTET", "All India", ["ctet"],
     "https://ctet.nic.in/", "https://ctet.nic.in/", "https://ctet.nic.in/"),
    ("IIM CAT", "All India", ["iim cat", "cat admit card"],
     "https://iimcat.ac.in/", "https://iimcat.ac.in/", "https://iimcat.ac.in/"),
    ("BCI AIBE", "All India", ["aibe", "allindiabarexamination"],
     "https://www.allindiabarexamination.com/", "https://www.allindiabarexamination.com/", "https://www.allindiabarexamination.com/"),
    ("NTA", "All India", ["nta ", "cuet", "jee main", "neet", "ugc net", "csir net"],
     "https://exams.nta.ac.in/", "https://exams.nta.ac.in/", "https://exams.nta.ac.in/"),
    ("INDIA POST", "All India", ["india post", "gds ", "gramin dak"],
     "https://indiapostgdsonline.gov.in/", "https://indiapostgdsonline.gov.in/", "https://indiapostgdsonline.gov.in/"),

    # --- BANKING & RAILWAYS ---
    ("SBI", "All India", ["sbi po", "sbi clerk", "state bank", "sbi cbo", "sbi "],
     "https://bank.sbi/web/careers/Current-openings", "https://bank.sbi/web/careers/Current-openings", "https://bank.sbi/web/careers/Current-openings"),
    ("IBPS", "All India", ["ibps", "crp po", "crp clerk", "ibps so", "ibps rrb"],
     "https://ibpsonline.ibps.in/", "https://ibpsonline.ibps.in/", "https://www.ibps.in/"),
    ("RAILWAY RRC NR", "All India", ["rrc nr"],
     "https://www.rrcnr.org/", "https://www.rrcnr.org/", "https://www.rrcnr.org/"),
    ("RAILWAY RRC NWR", "All India", ["rrc nwr"],
     "https://www.rrcjaipur.in/", "https://www.rrcjaipur.in/", "https://www.rrcjaipur.in/"),
    ("RAILWAY RRC CR", "All India", ["rrc cr"],
     "https://www.rrccr.com/Home/Home", "https://www.rrccr.com/Home/Home", "https://www.rrccr.com/Home/Home"),
    ("RAILWAY RRB", "All India", ["railway", "rrb", "ntpc", "group d", "alp", "rpf", "technician", "rrc", "station master", "paramedical", "section controller"],
     "https://www.rrbapply.gov.in/#/auth/landing", "https://www.rrbapply.gov.in/#/auth/landing", "https://indianrailways.gov.in/railwayboard/view_section.jsp?lang=0&id=0,7,1281"),

    # --- UPSC & SSC (Checked after state/departmental boards) ---
    ("UPSC", "All India", ["upsc", "civil services", "ias ", "ifs ", "nda", "cds", "capf", "epfo"],
     "https://upsconline.nic.in/upsc/OTRP/", "https://upsconline.nic.in/upsc/OTRP/", "https://upsc.gov.in/examinations/active-exams"),
    ("SSC", "All India", ["ssc", "cgl", "chsl", "ssc gd", "ssc cpo", "ssc je", "ssc mts", "steno", "selection post"],
     "https://ssc.gov.in/login", "https://ssc.gov.in/login", "https://ssc.gov.in/portal/notices"),
]


def make_stable_id(category: str, title: str) -> str:
    """Generates a deterministic, collision-free ID from category and normalized title."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:36]
    short_hash = hashlib.md5(title.lower().encode("utf-8")).hexdigest()[:6]
    return f"{category.lower()}_{slug}_{short_hash}"


def canonical_exam_signature(title: str, category: str) -> str:
    """
    Creates a normalized signature for fuzzy deduplication so 4 news sites reporting
    on 'RRB ALP Answer Key 2026' don't create 4 duplicate cards.
    """
    stop_words = {
        "out", "released", "download", "direct", "link", "here", "check", "now",
        "online", "form", "recruitment", "notification", "pdf", "hall", "ticket",
        "admit", "card", "answer", "key", "response", "sheet", "exam", "date",
        "active", "soon", "expected", "at", "for", "and", "the", "in", "of", "to"
    }
    words = re.findall(r"[a-z0-9]+", title.lower())
    core = [w for w in words if w not in stop_words and not w.isdigit() and len(w) > 1]
    return f"{category}:{'_'.join(core[:4])}"


def extract_posts_from_text(text: str) -> str:
    """Extracts post count from title or summary text like '(17,735 Posts)' or '514 Vacancies'."""
    m = POSTS_IN_TEXT_REGEX.search(text or "")
    if m:
        raw_num = m.group(1).replace(",", "")
        if raw_num.isdigit() and int(raw_num) > 0:
            return f"{int(raw_num):,} Posts"
    return ""


def http_get_text(url: str, timeout: int = 12) -> str:
    if SCRAPER is not None:
        resp = SCRAPER.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
        return ""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_html_resilient(url: str, timeout: int = 12):
    try:
        text = http_get_text(url, timeout=timeout)
        if text and len(text) > 800 and "Just a moment..." not in text:
            return text
    except Exception:
        pass

    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url, safe='')}"
        text2 = http_get_text(proxy_url, timeout=15)
        if text2 and len(text2) > 800:
            return text2
    except Exception:
        pass
    return None


def parse_date_str(d_str: str):
    try:
        if "-" in d_str and d_str.startswith("20"):
            return datetime.strptime(d_str, "%Y-%m-%d").date()
        return datetime.strptime(d_str.replace("-", "/"), "%d/%m/%Y").date()
    except Exception:
        return None


def is_banned_or_search_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return True
    u = url.strip().lower()
    if not u.startswith("http"):
        return True
    return any(b in u for b in BANNED_DOMAINS)


def build_strict_gov_search_url(title: str, board_badge: str = "") -> str:
    """
    Builds a strict government-domain-only Google search URL (site:gov.in OR site:nic.in OR site:ac.in)
    so users never land on private ad-filled blogs when a deep link is missing or unknown.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if board_badge and board_badge not in ("GOV PORTAL", "OFFICIAL PORTAL") and board_badge.lower() not in cleaned.lower():
        query_base = f"{board_badge} {cleaned}"
    else:
        query_base = cleaned
    full_query = f"{query_base} (site:gov.in OR site:nic.in OR site:ac.in)"
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(full_query)}"


def check_deep_link_not_404(url: str, timeout: int = 6) -> bool:
    """
    Checks whether an ephemeral deep link returns a hard 404/410 Not Found error.
    Timeouts or 403/405 firewall blocks from .gov.in servers are treated as reachable
    so valid Indian government portals aren't falsely discarded from foreign GitHub runners.
    """
    if not url or not url.startswith("http"):
        return False
    try:
        if SCRAPER is not None:
            resp = SCRAPER.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if resp.status_code in (404, 410):
                return False
            if resp.status_code == 405:
                resp_get = SCRAPER.get(url, headers=HEADERS, timeout=timeout, stream=True)
                status = resp_get.status_code
                resp_get.close()
                if status in (404, 410):
                    return False
            return True
        req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status not in (404, 410)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return False
        return True
    except Exception:
        return True


def extract_domain_from_title(title: str):
    m = DOMAIN_IN_TEXT_REGEX.search(title or "")
    if m:
        dom = m.group(1).lower()
        if "google." not in dom and "sarkari" not in dom:
            return f"https://{dom}/"
    return None


def resolve_portal_info(
    title: str,
    category: str,
    scraped_url: str = None,
    scraped_login: str = None,
    scraped_notif: str = None,
    scraped_official: str = None
):
    lower = (title or "").lower()
    clean_primary = scraped_url if not is_banned_or_search_url(scraped_url) else None
    clean_login = scraped_login if not is_banned_or_search_url(scraped_login) else None
    clean_notif = scraped_notif if not is_banned_or_search_url(scraped_notif) else None
    clean_official = scraped_official if not is_banned_or_search_url(scraped_official) else None
    title_domain_url = extract_domain_from_title(title)

    if clean_primary and "drive.google.com" in clean_primary and not clean_notif:
        clean_notif = clean_primary
        clean_primary = None

    for badge, state, keywords, apply_url, login_url, notice_url in PORTAL_DIRECTORY:
        if any(k in lower for k in keywords):
            if badge != "SSC":
                if clean_primary and "ssc.gov.in" in clean_primary:
                    clean_primary = None
                if clean_login and "ssc.gov.in" in clean_login:
                    clean_login = None
                if clean_official and "ssc.gov.in" in clean_official:
                    clean_official = None
            if badge != "UPSC":
                if clean_primary and "upsconline.nic.in" in clean_primary:
                    clean_primary = None
                if clean_login and "upsconline.nic.in" in clean_login:
                    clean_login = None
            if badge in ("JSSC", "JPSC"):
                if clean_primary and ("jssc.nic.in" in clean_primary or "www.jpsc.gov.in" in clean_primary):
                    clean_primary = None
                if clean_login and ("jssc.nic.in" in clean_login or "www.jpsc.gov.in" in clean_login):
                    clean_login = None
                if clean_notif and ("jssc.nic.in" in clean_notif or "www.jpsc.gov.in" in clean_notif):
                    clean_notif = None
                if clean_official and ("jssc.nic.in" in clean_official or "www.jpsc.gov.in" in clean_official):
                    clean_official = None

            final_target = clean_primary or title_domain_url or apply_url
            final_login = clean_login or title_domain_url or login_url or final_target
            final_notif = clean_notif or notice_url or clean_official or final_target
            final_official = clean_official or title_domain_url or notice_url or apply_url

            # Rescue hard 404/410 deep links automatically using verified board portals
            if clean_primary and final_target == clean_primary and not check_deep_link_not_404(final_target):
                print(f"⚠️ Rescued 404 deep link for '{title[:40]}': {final_target} -> {apply_url}")
                final_target = apply_url

            return badge, state, final_target, final_login, final_notif, final_official, True

    detected_state = "All India"
    for st in ["Jharkhand", "Bihar", "Uttar Pradesh", "Madhya Pradesh", "Rajasthan", "Delhi", "Haryana"]:
        if st.lower() in lower or (st == "Uttar Pradesh" and "up " in lower):
            detected_state = st
            break

    strict_gov_search = build_strict_gov_search_url(title)
    direct_candidate = clean_primary or clean_official or title_domain_url

    if direct_candidate and check_deep_link_not_404(direct_candidate):
        final_target = direct_candidate
        final_login = clean_login or final_target
        final_notif = clean_notif or clean_official or final_target
        final_official = clean_official or title_domain_url or final_target
        return "GOV PORTAL", detected_state, final_target, final_login, final_notif, final_official, True

    # Unknown board & no working direct portal link -> strict .gov.in / .nic.in rescue search
    return "GOV PORTAL", detected_state, strict_gov_search, strict_gov_search, strict_gov_search, strict_gov_search, False


def clean_title(raw_text: str) -> str:
    text = re.sub(r"\s+", " ", raw_text).strip()
    text = text.rsplit(" - ", 1)[0].strip()
    text = re.split(r"(?i)\s*(?:;\s*check\b|:\s*check\b|:\s*download\b|,\s*check\b)", text)[0].strip()
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
    if html and BeautifulSoup is not None:
        soup = BeautifulSoup(html, "lxml")
        expiry_dt = None
        age_text = ""
        qual_text = ""

        for li in soup.select("li"):
            txt = li.get_text(" ", strip=True)
            low = txt.lower()
            if category == "NEW_FORM" and any(k in low for k in ["last date for apply", "last date to apply", "apply online last date", "last date :"]):
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
            if ("minimum age" in low or "maximum age" in low) and not age_text:
                age_text = txt[:55]
            if any(q in low for q in ["bachelor degree", "10+2", "class 10th", "master degree", "diploma", "b.tech", "iti "]) and not qual_text:
                qual_text = txt[:55]

        info["shortSummary"] = " · ".join(filter(None, [qual_text, age_text]))[:85]

        full_text = soup.get_text(" ", strip=True)
        pm = re.search(
            r"(?:Vacancy Details Total|Total\s+Post[s]?|Total\s+Vacanc(?:y|ies))\s*[:\-]?\s*(\d[\d,]*)",
            full_text,
            re.IGNORECASE
        )
        if pm:
            raw_num = pm.group(1).replace(",", "")
            if raw_num.isdigit() and int(raw_num) > 0:
                info["totalPosts"] = f"{int(raw_num):,} Posts"

        for tr in soup.select("table tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 2:
                continue
            label = tds[0].get_text(" ", strip=True).lower()
            links = []
            for a in tds[1].find_all("a", href=True):
                href = urllib.parse.urljoin(post_url, a["href"].strip())
                if not is_banned_or_search_url(href):
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


def sanitize_existing_item(item: dict) -> dict:
    title = clean_title(item.get("title", ""))
    category = item.get("category", "NEW_FORM")
    badge, state, target_url, login_url, notif_url, official_site, is_direct = resolve_portal_info(
        title,
        category,
        scraped_url=item.get("targetUrl"),
        scraped_login=item.get("loginUrl"),
        scraped_notif=item.get("notificationPdfUrl"),
        scraped_official=item.get("officialWebsiteUrl")
    )
    item["id"] = make_stable_id(category, title)
    item["title"] = title
    item["boardBadge"] = badge
    item["state"] = state
    item["targetUrl"] = target_url
    item["loginUrl"] = login_url
    item["notificationPdfUrl"] = notif_url
    item["officialWebsiteUrl"] = official_site
    item["govSearchUrl"] = build_strict_gov_search_url(title, badge)
    if not item.get("totalPosts"):
        item["totalPosts"] = extract_posts_from_text(title)
    item["isDirectPortalMatch"] = is_direct
    return item


def scrape_sarkari_portals(newly_discovered: list, existing_by_title: dict, seen_signatures: set):
    if BeautifulSoup is None:
        return
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

        candidates = []
        seen_titles = set(existing_by_title.keys())
        for a_tag in links[:260]:
            raw_title = clean_title(a_tag.get_text())
            href = urllib.parse.urljoin(base_url, a_tag.get("href", ""))
            low = raw_title.lower()
            if len(raw_title) < 12 or low in seen_titles:
                continue
            if any(clutter in low for clutter in NON_EXAM_CLUTTER_KEYWORDS):
                continue

            if any(k in low for k in ["admit card", "hall ticket", "exam city", "call letter"]):
                category = "ADMIT_CARD"
            elif any(k in low for k in ["answer key", "response sheet", "question paper"]):
                category = "ANSWER_KEY"
            elif any(k in low for k in ["online form", "recruitment", "apply", "vacancy"]):
                category = "NEW_FORM"
            else:
                continue

            sig = canonical_exam_signature(raw_title, category)
            if sig in seen_signatures:
                continue

            seen_titles.add(low)
            seen_signatures.add(sig)
            candidates.append((raw_title, href, category))
            if len(candidates) >= 60:
                break

        if not candidates:
            continue

        details_by_href = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            future_map = {
                executor.submit(extract_inner_post_details, href, cat): (raw_title, href, cat)
                for raw_title, href, cat in candidates
            }
            for future in concurrent.futures.as_completed(future_map):
                _, href, cat = future_map[future]
                try:
                    details_by_href[href] = future.result()
                except Exception:
                    days = 28 if cat == "NEW_FORM" else (18 if cat == "ADMIT_CARD" else 12)
                    details_by_href[href] = {
                        "primaryUrl": None, "loginUrl": None, "notifUrl": None, "officialSite": None,
                        "displayDate": "Active Now",
                        "expiryIso": (TODAY + timedelta(days=days)).strftime("%Y-%m-%d"),
                        "totalPosts": "", "shortSummary": ""
                    }

        count_from_mirror = 0
        for raw_title, href, category in candidates:
            details = details_by_href.get(href, {})
            exp_dt = parse_date_str(details.get("expiryIso", ""))
            if exp_dt and TODAY > exp_dt:
                continue

            badge, state, target_url, login_url, notif_url, official_site, is_direct = resolve_portal_info(
                raw_title,
                category,
                scraped_url=details.get("primaryUrl"),
                scraped_login=details.get("loginUrl"),
                scraped_notif=details.get("notifUrl"),
                scraped_official=details.get("officialSite")
            )

            posts_str = details.get("totalPosts") or extract_posts_from_text(raw_title)

            item = {
                "id": make_stable_id(category, raw_title),
                "title": raw_title,
                "category": category,
                "state": state,
                "boardBadge": badge,
                "targetUrl": target_url,
                "loginUrl": login_url,
                "notificationPdfUrl": notif_url,
                "officialWebsiteUrl": official_site,
                "govSearchUrl": build_strict_gov_search_url(raw_title, badge),
                "lastDate": details.get("displayDate") or "Active Now",
                "expiryDate": details.get("expiryIso"),
                "totalPosts": posts_str,
                "shortSummary": details.get("shortSummary") or (f"Verified Direct Portal ({badge})" if is_direct else "Official .gov.in / .nic.in Lookup"),
                "isDirectPortalMatch": is_direct,
                "isPinnedTop": False,
                "isManual": False
            }
            newly_discovered.append(item)
            existing_by_title[raw_title.lower()] = item
            count_from_mirror += 1

        if count_from_mirror > 8:
            break


def fetch_google_news_rss_backup(newly_discovered: list, existing_by_title: dict, seen_signatures: set):
    rss_queries = [
        ("NEW_FORM", "(SSC OR RRB OR IBPS OR SBI OR UPSC OR JSSC OR JPSC OR BPSC OR UPSSSC) recruitment apply online notification"),
        ("ADMIT_CARD", "(SSC OR RRB OR IBPS OR UPSC OR JSSC OR JPSC OR BPSC OR UPSSSC) admit card hall ticket released"),
        ("ANSWER_KEY", "(SSC OR RRB OR IBPS OR JSSC OR JPSC OR BPSC OR UPSSSC) answer key response sheet released")
    ]
    for category, q in rss_queries:
        encoded = urllib.parse.quote_plus(q)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            xml_text = http_get_text(rss_url, timeout=10)
            if not xml_text:
                continue
            root = ET.fromstring(xml_text.encode("utf-8"))
            for item_el in root.findall(".//item")[:8]:
                raw_t = clean_title(item_el.findtext("title") or "")
                low = raw_t.lower()
                if len(raw_t) < 12 or low in existing_by_title:
                    continue

                sig = canonical_exam_signature(raw_t, category)
                if sig in seen_signatures:
                    continue

                badge, state, target_url, login_url, notif_url, official_site, is_direct = resolve_portal_info(
                    raw_t, category
                )
                if not is_direct:
                    continue

                seen_signatures.add(sig)
                days = 25 if category == "NEW_FORM" else (15 if category == "ADMIT_CARD" else 10)
                exp_iso = (TODAY + timedelta(days=days)).strftime("%Y-%m-%d")

                new_item = {
                    "id": make_stable_id(category, raw_t),
                    "title": raw_t,
                    "category": category,
                    "state": state,
                    "boardBadge": badge,
                    "targetUrl": target_url,
                    "loginUrl": login_url,
                    "notificationPdfUrl": notif_url,
                    "officialWebsiteUrl": official_site,
                    "govSearchUrl": build_strict_gov_search_url(raw_t, badge),
                    "lastDate": "Active Now" if category == "NEW_FORM" else "Out Now",
                    "expiryDate": exp_iso,
                    "totalPosts": extract_posts_from_text(raw_t),
                    "shortSummary": f"Direct Official Portal ({badge})",
                    "isDirectPortalMatch": is_direct,
                    "isPinnedTop": False,
                    "isManual": False
                }
                newly_discovered.append(new_item)
                existing_by_title[low] = new_item
        except Exception as e:
            print(f"RSS backup warning: {e}")


def main():
    existing_items = []
    seen_signatures = set()

    try:
        with open("live_exams.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("items", []):
                low_t = (item.get("title") or "").lower()
                if any(clutter in low_t for clutter in NON_EXAM_CLUTTER_KEYWORDS):
                    continue
                exp_dt = parse_date_str(item.get("expiryDate", ""))
                if exp_dt is None or TODAY <= exp_dt:
                    cleaned = sanitize_existing_item(item)
                    sig = canonical_exam_signature(cleaned["title"], cleaned["category"])
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        existing_items.append(cleaned)
    except Exception:
        pass

    existing_by_title = {item["title"].lower(): item for item in existing_items}
    newly_discovered = []

    scrape_sarkari_portals(newly_discovered, existing_by_title, seen_signatures)
    fetch_google_news_rss_backup(newly_discovered, existing_by_title, seen_signatures)

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

    print(f"✅ SUCCESS: Added {len(newly_discovered)} new items. Total deduplicated items: {len(final_items)}")


if __name__ == "__main__":
    main()
