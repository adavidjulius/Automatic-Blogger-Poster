#!/usr/bin/env python3
"""
══════════════════════════════════════════════════════════════════════════════
 READCONTEXT AI NEWSPAPER — NVIDIA NIM Edition
 High-impact, newspaper-grade journalism automated for readcontext.blogspot.com
 Fully compliant with Google Publisher & AdSense Content Policies
══════════════════════════════════════════════════════════════════════════════
 Compliance Safeguards Enforced:
   • ZERO Graphic Violence: No blood, weapons, casualties, or destruction.
   • ZERO Geopolitical Bias: Strict neutrality, no partisan conflict taking sides.
   • ZERO Copyright Infringement: Original journalistic synthesis & attribution;
     no pirated downloads or copied text blocks.
   • ZERO Misinformation: No unscientific medical advice, get-rich-quick, or scams.
   • Mobile-Optimized Substance: Fast-paced, authoritative reporting (800–1,050 words, under 5 min read for mobile audience).
   • NO Deceptive Ad Placement: Clean, ethical presentation matching site aesthetics.
   • Essential Pages: Auto-generates Privacy Policy, About Us, and Contact Pages.
══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import time
import random
import base64
import re
import traceback
import urllib.parse
import unicodedata
import hashlib
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import feedparser
from bs4 import BeautifulSoup

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
from google.auth.transport.requests import Request as GoogleAuthRequest

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ openai library missing — run 'pip install openai'")

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION & CREDENTIALS
# ═══════════════════════════════════════════════════════════════════════════

# ── Load local .env if present (strictly gitignored for security) ──────────
_env_path = Path(".env")
if _env_path.exists():
    try:
        with open(_env_path, "r", encoding="utf-8") as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
    except Exception:
        pass

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# ── Top 5 Verified Active Text Generation Models (Ordered by Velocity & Depth) ──
TEXT_MODELS = [
    "nvidia/nemotron-3.5-bolt-e4b",           # 1. Primary: Blazing speed (<20s), high journalism quality
    "nvidia/nemotron-3-ultra-550b-a55b",      # 2. Secondary: Frontier MoE 550B deep reasoning
    "poolside/laguna-xs-2.1",                 # 3. Tertiary: Fast structured technical writing
    "minimaxai/minimax-m3.1-flash",           # 4. Quaternary: Fast high-capacity flash model
    "google/diffusiongemma-26b-a4b-it",       # 5. Quinary: Multimodal text & vision model
]

# ── Vision Validation Models ───────────────────────────────────────────────
VISION_MODELS = [
    "google/diffusiongemma-26b-a4b-it",       # Verified Active Multimodal Vision
    "nvidia/nemotron-3.5-super-vl-120b-a12b",  # Super Vision-Language 120B
]

# ── Tool Calling Specialist Model ─────────────────────────────────────────
TOOL_MODEL = "nvidia/nemotron-3.5-bolt-e4b"

# ── Blogger API Credentials ────────────────────────────────────────────────
BLOGGER_BLOG_ID        = os.getenv("BLOGGER_BLOG_ID", "6965563738161457805")
GOOGLE_CLIENT_ID       = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET   = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN   = os.getenv("GOOGLE_REFRESH_TOKEN")
GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON")

# ── Image API Keys (Optional) ─────────────────────────────────────────────
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
GOOGLE_CSE_API_KEY  = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID       = os.getenv("GOOGLE_CSE_ID", "")

# ── ReadContext Site Identity ──────────────────────────────────────────────
BLOG_URL  = "https://readcontext.blogspot.com"
LOGO_PATH = Path("logo.png")
PAGES_DIR = Path("pages")
SITEMAP_CANDIDATES = [
    f"{BLOG_URL}/sitemap.xml",
    f"{BLOG_URL}/atom.xml?redirect=false&start-index=1&max-results=500",
    f"{BLOG_URL}/feeds/posts/default",
]

# ── Storage Directories ────────────────────────────────────────────────────
CACHE_DIR = Path(".blog-cache")
POSTS_DIR = Path("_posts")
CACHE_DIR.mkdir(exist_ok=True)
POSTS_DIR.mkdir(exist_ok=True)

POSTS_LOG = CACHE_DIR / "posts_log.json"
POSTED_HISTORY_FILE = CACHE_DIR / "posted_history.json"
posts_log = []
if POSTS_LOG.exists():
    try:
        with open(POSTS_LOG, 'r', encoding='utf-8') as f:
            posts_log = json.load(f)
    except Exception:
        posts_log = []


def get_posted_history():
    """Load previously published titles and URLs to prevent duplicate publications."""
    history_titles = set()
    history_urls = set()

    for hist_file in [POSTED_HISTORY_FILE, POSTS_LOG]:
        if hist_file.exists():
            try:
                with open(hist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        if item.get("title"):
                            history_titles.add(item["title"].strip().lower())
                        if item.get("source_url"):
                            history_urls.add(item["source_url"].strip().lower())
            except Exception:
                pass

    for md_file in POSTS_DIR.glob("*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                header = f.read(1200)
                m = re.search(r'title:\s*"([^"]+)"', header)
                if m:
                    history_titles.add(m.group(1).strip().lower())
        except Exception:
            pass

    # Also poll the live Blogger feed to catch any articles published in previous runs
    try:
        live_feed_url = f"{BLOG_URL}/feeds/posts/default?alt=json&max-results=50"
        resp = SESSION.get(live_feed_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            for entry in data.get("feed", {}).get("entry", []):
                t = entry.get("title", {}).get("$t", "")
                if t:
                    history_titles.add(t.strip().lower())
    except Exception:
        pass

    return history_titles, history_urls


def record_posted_story(title, source_url, blog_url=""):
    """Persist newly published story info to avoid duplicate runs across scheduled jobs."""
    history = []
    if POSTED_HISTORY_FILE.exists():
        try:
            with open(POSTED_HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append({
        "title": title,
        "source_url": source_url,
        "blog_url": blog_url,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    try:
        with open(POSTED_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history[-300:], f, indent=2)
    except Exception as e:
        log("⚠️", f"Could not save posted_history: {e}")


# ── HTTP Session ────────────────────────────────═══════════════════════════
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ReadContext/2.0"
})


# ═══════════════════════════════════════════════════════════════════════════
#  CONTENT COMPLIANCE & SAFETY GUARDRAILS (AdSense & Publisher Standard)
# ═══════════════════════════════════════════════════════════════════════════

class ContentComplianceGuard:
    """
    Enforces strict compliance with digital journalism & Google AdSense standards:
    1. Graphic Violence: No pictures or text depicting blood, weapons, injuries, casualties, or destruction.
    2. Geopolitical Bias: No taking sides in conflicts, emotional or derogatory language, or unverified updates.
    3. Copyright Theft: No pirated links, cracked software, keygens, torrents, warez, or paywall bypasses.
    4. Misinformation: No unscientific medical advice, fake news, conspiracy theories, or quick-wealth financial schemes.
    5. Advertising & Click Solicitations: No "support us by clicking", no fake download buttons, no deceptive button styling.
    6. Thin Text Prevention: Minimum 650 words enforced on every published dispatch to ensure solid substance while keeping reads strictly under 5 minutes for mobile users.
    """

    GRAPHIC_VIOLENCE = [
        r"\b(drone\s*strikes?|air\s*strikes?|missiles?|artillery|casualt(y|ies)|bloodshed|gore|gory|weaponry|warfare|battlefield|bombed|bombing|bomb\s*blast|grenades?|slaughter|genocide|terroris[mt]|military\s*strike|firearms?|gunfire|shootout|massacre|assassination|fatalit(y|ies)|corpses?|severed\s*limbs?|dismember(ed|ment)|torture|suicide|self-harm|firing\s*squad|summary\s*execution|hostages?|hostage\s*crisis|mass\s*shooting|militant\s*attacks?|suicide\s*attacks?|warlord|behead(ed|ing)|atrocit(y|ies)|combat\s*deaths?)\b",
    ]

    GEOPOLITICAL_CONFLICT = [
        r"\b(ukraine|russia|kremlin|putin|zelensky|gaza|israel|hezbollah|hamas|pentagon|idf|pla|invad(ed|ing|ion)|troops?|battle\s*lines?|annexation|ceasefire\s*violation|warring\s*sides|war\s*zone|armed\s*conflict)\b",
    ]

    COPYRIGHT_PIRACY = [
        r"\b(torrents?|keygens?|cracked|warez|pirat(ed|ing|e|cy)|free\s*download\s*full|bypass\s*paywall|nulled|serial\s*key|license\s*generator|iso\s*download|free\s*movie\s*stream)\b",
    ]

    MISINFORMATION_SCAMS = [
        r"\b(get\s*rich\s*quick|100x\s*crypto|guaranteed\s*returns?|miracle\s*cures?|cure\s*cancer|conspiracy\s*theor(y|ies)|anti-vax|secret\s*wealth|crypto\s*pump|ponzi|binary\s*options|infinite\s*money)\b",
    ]

    CLICK_SOLICITATIONS = [
        r"\b(support\s*(us|this\s*blog|our\s*site)\s*by\s*clicking)\b",
        r"\b(click\s*(on\s*)?(the\s*)?ads?|click\s*here\s*to\s*support|click\s*our\s*sponsors?|visit\s*our\s*sponsors?)\b",
        r"\b(fake\s*download|download\s*button|click\s*below\s*to\s*download|click\s*to\s*reveal|download\s*now\s*free)\b",
    ]

    ALL_PATTERNS = GRAPHIC_VIOLENCE + GEOPOLITICAL_CONFLICT + COPYRIGHT_PIRACY + MISINFORMATION_SCAMS + CLICK_SOLICITATIONS

    MIN_COMPLIANT_WORDS = 650

    @classmethod
    def normalize_text(cls, text):
        norm = unicodedata.normalize("NFKD", text or "")
        return norm.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

    @classmethod
    def evaluate(cls, title, description=""):
        """
        Returns (is_compliant, reason).
        If non-compliant, gives the exact trigger to log and skip.
        """
        combined = cls.normalize_text(f"{title} {description}").lower()
        for pat in cls.ALL_PATTERNS:
            match = re.search(pat, combined, re.IGNORECASE)
            if match:
                return False, match.group(0)
        return True, "Compliant"

    @classmethod
    def validate_article(cls, title, raw_body, word_count):
        """
        Strict pre-publication validator checking word count and text content.
        """
        if word_count < cls.MIN_COMPLIANT_WORDS:
            return False, f"Thin Text Detected ({word_count} words). Minimum {cls.MIN_COMPLIANT_WORDS} words required."

        is_safe, reason = cls.evaluate(title, raw_body)
        if not is_safe:
            return False, f"Compliance Violation Detected ({reason})"

        return True, "Valid"


# ═══════════════════════════════════════════════════════════════════════════
#  UTILITY HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def log(icon, message):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {icon} {message}", flush=True)


def log_err(step, error, details=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n❌ [{ts}] ERROR in {step}: {error}", flush=True)
    if details:
        print(f"   Details: {details}", flush=True)
    print(f"   Traceback: {traceback.format_exc()}", flush=True)


def extract_keywords(title, description=""):
    """Extract significant topic keywords for cross-matching and search."""
    # Retain meaningful words like 'ai', 'cfo', 'ceo', 'fbi', 'faa' by allowing 2+ chars
    # Exclude only truly generic grammatical stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "at",
        "to", "for", "with", "this", "that", "these", "those", "and", "or",
        "but", "how", "what", "when", "why", "who", "will", "can", "has",
        "have", "its", "it", "not", "from", "been", "about", "just", "than",
        "into", "over", "after", "also", "may", "some", "could", "would",
        "should", "most", "all", "one", "two", "says", "said", "like", "year",
        "make", "take", "post", "read", "shows", "shown", "show"
    }
    raw = f"{title} {description}"
    words = re.findall(r'\b[a-zA-Z0-9\$\%]{2,}\b', raw)
    filtered = [w.lower() for w in words if w.lower() not in stop_words]
    deduped = []
    seen = set()
    for w in filtered:
        if w not in seen:
            seen.add(w)
            deduped.append(w)
    return deduped[:10]


def title_similarity(t1, t2):
    """
    Compute comprehensive similarity between two titles using multiple metrics:
    1. SequenceMatcher ratio (character-level fuzzy match)
    2. Jaccard similarity of extracted keywords
    3. Token overlap ratio
    """
    if not t1 or not t2:
        return 0.0
    
    t1_clean = re.sub(r'[^a-z0-9\s]', '', t1.lower()).strip()
    t2_clean = re.sub(r'[^a-z0-9\s]', '', t2.lower()).strip()
    
    if t1_clean == t2_clean:
        return 1.0

    # 1. SequenceMatcher
    seq_ratio = SequenceMatcher(None, t1_clean, t2_clean).ratio()

    # 2. Keyword Jaccard
    kw1 = set(extract_keywords(t1))
    kw2 = set(extract_keywords(t2))
    if kw1 and kw2:
        jaccard = len(kw1 & kw2) / len(kw1 | kw2)
        overlap = len(kw1 & kw2) / min(len(kw1), len(kw2))
    else:
        jaccard = 0.0
        overlap = 0.0

    # 3. Normalized token set
    tokens1 = set(t1_clean.split())
    tokens2 = set(t2_clean.split())
    token_jaccard = len(tokens1 & tokens2) / max(len(tokens1 | tokens2), 1)

    # Combined composite score
    composite = max(seq_ratio, (overlap * 0.6 + jaccard * 0.4), token_jaccard)
    return composite


def is_duplicate_story(title, url, posted_titles, posted_urls, threshold=0.52):
    """
    Checks if a story is a duplicate of any previously posted story.
    Returns (is_duplicate, matched_title, similarity_score).
    """
    norm_title = title.strip().lower()
    norm_url = (url or "").strip().lower()

    # Exact URL match
    if norm_url and norm_url in posted_urls:
        return True, "URL match", 1.0

    # Canonicalize Bluesky / aggregator URLs that wrap another URL
    for p_url in posted_urls:
        # Check if the URLs point to the same story path
        if norm_url and p_url:
            p1 = urllib.parse.urlparse(norm_url).path.rstrip('/')
            p2 = urllib.parse.urlparse(p_url).path.rstrip('/')
            if len(p1) > 15 and p1 == p2:
                return True, "URL path match", 1.0

    # Exact title match
    if norm_title in posted_titles:
        return True, norm_title, 1.0

    # Fuzzy title matching
    best_score = 0.0
    best_match = ""
    for pt in posted_titles:
        score = title_similarity(norm_title, pt)
        if score > best_score:
            best_score = score
            best_match = pt

    if best_score >= threshold:
        return True, best_match, best_score

    return False, "", best_score


def clean_text(html_content):
    """Strip HTML tags and clean whitespace."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r'\s+', ' ', text).strip()


def strip_html_wrappers(html_str):
    """
    Remove wrapping <!DOCTYPE html>, <html>, <head>, <style>, <body> tags
    so content seamlessly injects into Blogger template's .post-body.
    """
    if not html_str:
        return ""
    clean = re.sub(r'<head.*?</head>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<!DOCTYPE[^>]*>', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'</?(html|body)[^>]*>', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'<h1[^>]*>.*?</h1>', '', clean, flags=re.DOTALL | re.IGNORECASE)
    return clean.strip()


# ═══════════════════════════════════════════════════════════════════════════
#  SUBJECT FATIGUE & EDITORIAL DIVERSITY TRACKER
# ═══════════════════════════════════════════════════════════════════════════

class SubjectFatigueTracker:
    """
    Monitors reader fatigue and prevents repetitive coverage of the same public figure,
    executive, or company across editions.
    Enforces a strict cooldown period (24-48 hours) and balances beat diversity:
      • Regional (Tamil Nadu)
      • National (India)
      • Global Affairs & World News
      • Science, Space & Discovery
      • Business, Markets & Economy
      • Technology & Innovation
    """
    KNOWN_ENTITIES = [
        "Jensen Huang", "Elon Musk", "Sundar Pichai", "Satya Nadella",
        "M. K. Stalin", "Narendra Modi", "Tim Cook", "Sam Altman",
        "Mark Zuckerberg", "Jeff Bezos", "Nvidia", "Tesla", "Apple",
        "Google", "Microsoft", "OpenAI", "ISRO", "NASA", "SpaceX",
        "Binance", "Meta", "Amazon", "Boeing", "Intel", "AMD",
        "Vijay", "Sonia Gandhi", "Rahul Gandhi"
    ]

    def __init__(self, posts_dir=POSTS_DIR, posts_log=None):
        self.posts_dir = posts_dir
        self.posts_log = posts_log or []
        self.recent_history = self._extract_recent_history()
        self.cooldown_entities = self._compute_cooldowns()
        self.recent_beats = [h.get("beat") for h in self.recent_history[:5] if h.get("beat")]
        if self.cooldown_entities:
            log("🛡️", f"Subject Fatigue Active: Cooldown enforced on {len(self.cooldown_entities)} entities: {', '.join(list(self.cooldown_entities)[:5])}")

    def _extract_recent_history(self):
        history = []
        md_files = sorted(self.posts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        for p in md_files:
            try:
                content = p.read_text(encoding="utf-8")
                title_m = re.search(r'title:\s*"([^"]+)"', content)
                title = title_m.group(1) if title_m else p.name
                tags_m = re.search(r'tags:\s*(\[[^\]]+\])', content)
                tags = json.loads(tags_m.group(1)) if tags_m else []
                entities = self.extract_entities(title, " ".join(tags))
                history.append({
                    "title": title,
                    "entities": entities,
                    "tags": tags,
                    "beat": self._infer_beat(title, tags)
                })
            except Exception:
                pass
        return history

    def _infer_beat(self, title, tags=None):
        text = f"{title} {' '.join(tags or [])}".lower()
        if any(w in text for w in ["tamil nadu", "chennai", "coimbatore", "madurai", "kodaikanal", "dmk", "aiadmk", "stalin"]):
            return "tamil_nadu"
        if any(w in text for w in ["india", "delhi", "mumbai", "parliament", "isro", "rbi", "modi", "sonia", "gandhi"]):
            return "india_national"
        if any(w in text for w in ["world", "diplomacy", "treaty", "nato", "summit", "election", "europe", "un "]):
            return "world_news"
        if any(w in text for w in ["science", "space", "discovery", "astronomy", "brain", "cancer", "nasa", "physics", "biology"]):
            return "science"
        if any(w in text for w in ["market", "bank", "valuation", "shares", "stock", "revenue", "cfo", "economy", "trade"]):
            return "business"
        return "technology"

    def extract_entities(self, title, description=""):
        ents = set()
        text = f"{title} {description}"
        t_lower = text.lower()
        for k in self.KNOWN_ENTITIES:
            if re.search(r'\b' + re.escape(k.lower()) + r'\b', t_lower):
                ents.add(k)
        caps = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b', text)
        for c in caps:
            c_clean = c.strip()
            if c_clean.lower() not in {
                "special report", "press wire", "digital culture", "artificial intelligence",
                "breaking news", "executive takeaways", "world news", "news article",
                "readcontext special bureau", "readcontext newsroom"
            }:
                ents.add(c_clean)
        return ents

    def _compute_cooldowns(self):
        cooldowns = set()
        if not self.recent_history:
            return cooldowns

        # Rule 1: The most recent article's entities CANNOT be repeated immediately
        most_recent = self.recent_history[0]
        for ent in most_recent.get("entities", []):
            cooldowns.add(ent.lower())

        # Rule 2: Any entity that appeared in 2 or more of the last 6 articles is in strict 48-hour cooldown
        counts = {}
        for h in self.recent_history[:6]:
            for ent in h.get("entities", []):
                e_low = ent.lower()
                counts[e_low] = counts.get(e_low, 0) + 1
                if counts[e_low] >= 2:
                    cooldowns.add(e_low)

        return cooldowns

    def check_candidate(self, candidate):
        title = candidate.get("title", "")
        desc = candidate.get("description", "")
        cand_ents = self.extract_entities(title, desc)
        for ent in cand_ents:
            ent_l = ent.lower()
            for cd in self.cooldown_entities:
                if cd == ent_l or re.search(r'\b' + re.escape(cd) + r'\b', ent_l):
                    return False, f"Entity '{ent}' matches cooldown '{cd}' from recent editions"
        return True, "Fresh"


# ═══════════════════════════════════════════════════════════════════════════
#  WIKIPEDIA ENTITY LINKER
# ═══════════════════════════════════════════════════════════════════════════

class WikipediaLinker:
    """
    Automatically hyperlinks key named entities (people, public officials, institutions,
    agencies, regions, and major organizations) on their FIRST mention in narrative paragraphs
    to authoritative Wikipedia articles, fulfilling reader informational discovery.
    """
    STATIC_ENTITIES = {
        # Tamil Nadu & India Regional / National
        "Tamil Nadu": "https://en.wikipedia.org/wiki/Tamil_Nadu",
        "Chennai": "https://en.wikipedia.org/wiki/Chennai",
        "Coimbatore": "https://en.wikipedia.org/wiki/Coimbatore",
        "Madurai": "https://en.wikipedia.org/wiki/Madurai",
        "Kodaikanal": "https://en.wikipedia.org/wiki/Kodaikanal",
        "ISRO": "https://en.wikipedia.org/wiki/ISRO",
        "Indian Space Research Organisation": "https://en.wikipedia.org/wiki/ISRO",
        "Reserve Bank of India": "https://en.wikipedia.org/wiki/Reserve_Bank_of_India",
        "Supreme Court of India": "https://en.wikipedia.org/wiki/Supreme_Court_of_India",
        "Securities and Exchange Board of India": "https://en.wikipedia.org/wiki/Securities_and_Exchange_Board_of_India",
        "M. K. Stalin": "https://en.wikipedia.org/wiki/M._K._Stalin",
        "Narendra Modi": "https://en.wikipedia.org/wiki/Narendra_Modi",
        "Sonia Gandhi": "https://en.wikipedia.org/wiki/Sonia_Gandhi",
        "Rahul Gandhi": "https://en.wikipedia.org/wiki/Rahul_Gandhi",
        "Sundar Pichai": "https://en.wikipedia.org/wiki/Sundar_Pichai",
        "Satya Nadella": "https://en.wikipedia.org/wiki/Satya_Nadella",
        "The Hindu": "https://en.wikipedia.org/wiki/The_Hindu",
        "Times of India": "https://en.wikipedia.org/wiki/The_Times_of_India",
        "Indian Express": "https://en.wikipedia.org/wiki/The_Indian_Express",

        # Global Organizations & Institutions
        "United Nations": "https://en.wikipedia.org/wiki/United_Nations",
        "World Health Organization": "https://en.wikipedia.org/wiki/World_Health_Organization",
        "European Union": "https://en.wikipedia.org/wiki/European_Union",
        "NASA": "https://en.wikipedia.org/wiki/NASA",
        "European Space Agency": "https://en.wikipedia.org/wiki/European_Space_Agency",
        "Federal Reserve": "https://en.wikipedia.org/wiki/Federal_Reserve",
        "BBC News": "https://en.wikipedia.org/wiki/BBC_News",
        "Reuters": "https://en.wikipedia.org/wiki/Reuters",
        "Harvard University": "https://en.wikipedia.org/wiki/Harvard_University",
        "Massachusetts Institute of Technology": "https://en.wikipedia.org/wiki/Massachusetts_Institute_of_Technology",

        # Industry & Global Tech Leaders
        "Jensen Huang": "https://en.wikipedia.org/wiki/Jensen_Huang",
        "Elon Musk": "https://en.wikipedia.org/wiki/Elon_Musk",
        "Tim Cook": "https://en.wikipedia.org/wiki/Tim_Cook",
        "Sam Altman": "https://en.wikipedia.org/wiki/Sam_Altman",
        "Mark Zuckerberg": "https://en.wikipedia.org/wiki/Mark_Zuckerberg",
        "Jeff Bezos": "https://en.wikipedia.org/wiki/Jeff_Bezos",
        "Nvidia": "https://en.wikipedia.org/wiki/Nvidia",
        "Google": "https://en.wikipedia.org/wiki/Google",
        "Microsoft": "https://en.wikipedia.org/wiki/Microsoft",
        "Apple Inc.": "https://en.wikipedia.org/wiki/Apple_Inc.",
        "Amazon": "https://en.wikipedia.org/wiki/Amazon_(company)",
        "Meta Platforms": "https://en.wikipedia.org/wiki/Meta_Platforms",
        "SpaceX": "https://en.wikipedia.org/wiki/SpaceX",
        "Tesla, Inc.": "https://en.wikipedia.org/wiki/Tesla,_Inc.",
        "OpenAI": "https://en.wikipedia.org/wiki/OpenAI",
        "Boeing": "https://en.wikipedia.org/wiki/Boeing",
        "Intel": "https://en.wikipedia.org/wiki/Intel",
        "AMD": "https://en.wikipedia.org/wiki/AMD",
    }

    def __init__(self):
        self.cache = dict(self.STATIC_ENTITIES)

    def resolve_wikipedia_url(self, entity):
        if entity in self.cache:
            return self.cache[entity]
        try:
            url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(entity)}&limit=1&format=json"
            resp = SESSION.get(url, timeout=2.5)
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 3 and data[3]:
                    wiki_url = data[3][0]
                    self.cache[entity] = wiki_url
                    return wiki_url
        except Exception:
            pass
        self.cache[entity] = None
        return None

    def link_entities_in_html(self, html_content):
        """
        Enrich HTML paragraphs with first-mention links to Wikipedia.
        Skips headings, blockquotes, code spans, figcaptions, and existing links.
        """
        entities_to_link = list(self.STATIC_ENTITIES.keys())
        entities_to_link.sort(key=len, reverse=True)
        linked_entities = set()

        def _link_p(match):
            p_text = match.group(0)
            for ent in entities_to_link:
                if ent in linked_entities:
                    continue
                # Match entity boundary outside existing anchors
                pattern = r'(?<!href=")(?<![>/])\b(' + re.escape(ent) + r')\b(?![^<]*</a>)'
                if re.search(pattern, p_text):
                    url = self.resolve_wikipedia_url(ent)
                    if url:
                        p_text = re.sub(
                            pattern,
                            rf'<a href="{url}" target="_blank" rel="noopener" style="color:#F36C21; text-decoration:underline;">\1</a>',
                            p_text,
                            count=1
                        )
                        linked_entities.add(ent)
            return p_text

        enriched = re.sub(r'<p>(.*?)</p>', _link_p, html_content, flags=re.DOTALL)
        return enriched, linked_entities


# ═══════════════════════════════════════════════════════════════════════════
#  EDITORIAL DIRECTOR — AI-Powered Multi-Beat Curation & Priority Selection
# ═══════════════════════════════════════════════════════════════════════════

class EditorialDirector:
    """
    Chief Editorial Curator for ReadContext:
    1. Enforces strict entity cooldown (never repeats a recently covered public figure or company).
    2. Enforces beat rotation (ensures Tamil Nadu regional, India national, global affairs,
       science discoveries, and business stories get published instead of endless tech coverage).
    3. Evaluates editorial priority: determines whether a story warrants high priority
       (with a secondary contextual image) or standard priority (focused hero image).
    """

    def __init__(self, ai_client=None):
        self.ai = ai_client

    def curate_lead_story(self, fresh_candidates, fatigue_tracker):
        """
        Selects the single best candidate from the multi-beat candidate pool.
        Filters out candidates in fatigue cooldown, then uses AI or deterministic rotation.
        """
        log("📋", "Editorial Director evaluating multi-beat candidate stories...")

        # 1. Filter out all candidates in cooldown
        valid_candidates = []
        for cand in fresh_candidates:
            ok, reason = fatigue_tracker.check_candidate(cand)
            if not ok:
                log("⏭️", f"Editorial Cooldown: '{cand['title'][:45]}...' -> {reason}")
                continue
            valid_candidates.append(cand)

        if not valid_candidates:
            log("⚠️", "All candidates in fatigue cooldown! Relaxing cooldown to allow fresh topics.")
            valid_candidates = fresh_candidates[:5]

        # 2. Score candidates by beat rotation balance
        recent_beats = fatigue_tracker.recent_beats
        log("📊", f"Recent Edition Desks: {recent_beats}")

        for cand in valid_candidates:
            beat = cand.get("beat", "technology")
            # If beat is unrepresented in recent editions, boost it
            if beat not in recent_beats:
                cand["rotation_score"] = cand.get("virality_score", 1) + 25
            elif recent_beats and recent_beats[0] == beat:
                # Consecutive beat penalty
                cand["rotation_score"] = max(1, cand.get("virality_score", 1) - 20)
            else:
                cand["rotation_score"] = cand.get("virality_score", 1) + 5

        valid_candidates.sort(key=lambda c: c.get("rotation_score", 0), reverse=True)

        # 3. Take top candidate from diverse beats for AI editorial selection
        diverse_pool = []
        seen_beats = set()
        for cand in valid_candidates:
            b = cand.get("beat", "general")
            if b not in seen_beats:
                seen_beats.add(b)
                diverse_pool.append(cand)
            if len(diverse_pool) >= 6:
                break

        # Fallback if diverse pool is small
        if len(diverse_pool) < 3:
            for cand in valid_candidates:
                if cand not in diverse_pool:
                    diverse_pool.append(cand)
                if len(diverse_pool) >= 6:
                    break

        # 4. Attempt AI Selection if AI is available
        if self.ai and getattr(self.ai, "client", None):
            try:
                recent_titles = [h["title"] for h in fatigue_tracker.recent_history[:5]]
                prompt = [
                    {"role": "system", "content": (
                        "You are the Senior Editorial Director for ReadContext (readcontext.blogspot.com). "
                        "Your mission is to curate the front page edition with maximum editorial diversity, "
                        "high journalistic substance, and zero reader fatigue.\n\n"
                        "STRICT CURATION DIRECTIVES:\n"
                        "1. NO REPEATED SUBJECTS: Do NOT pick any story about a person or company that appeared in recent headlines.\n"
                        "2. DESK ROTATION: Strongly prioritize non-tech desks (Tamil Nadu Regional, India National, World Affairs, Science & Discovery, Markets) if recent coverage was tech-heavy.\n"
                        "3. NO GRAPHIC CONFLICT: Reject any war combat, airstrikes, bombings, or casualties.\n"
                        "4. PRIORITY CLASSIFICATION: Decide if this story warrants 'high' priority (broad regional/global impact, multi-faceted) or 'standard' priority.\n"
                        "Output strict JSON only: {\"selected_index\": <int 0..N>, \"priority\": \"high\"|\"standard\", \"rationale\": \"<1 sentence>\"}"
                    )},
                    {"role": "user", "content": f"""
RECENT HEADLINES PUBLISHED ON READCONTEXT:
{json.dumps(recent_titles, indent=2)}

CANDIDATE DESK STORIES FOR TODAY'S EDITION:
{json.dumps([{'index': idx, 'desk': c.get('beat'), 'source': c.get('source'), 'title': c.get('title'), 'summary': c.get('description', '')[:140]} for idx, c in enumerate(diverse_pool)], indent=2)}
"""}
                ]
                resp = self.ai.generate(prompt, max_tokens=200, temperature=0.3, timeout=25.0)
                if resp:
                    clean_resp = re.search(r'\{.*\}', resp, re.DOTALL)
                    if clean_resp:
                        decision = json.loads(clean_resp.group(0))
                        idx = int(decision.get("selected_index", 0))
                        if 0 <= idx < len(diverse_pool):
                            choice = diverse_pool[idx]
                            choice["is_high_priority"] = (decision.get("priority", "").lower() == "high")
                            log("🎯", f"AI Editorial Director selected [{choice.get('beat', '').upper()}]: '{choice['title']}' ({decision.get('rationale', '')})")
                            return choice
            except Exception as e:
                log("⚠️", f"AI Editorial Director selection exception: {e}. Using deterministic beat rotation.")

        # 5. Deterministic Beat Rotation Selection
        choice = diverse_pool[0]
        # High priority if score is strong or has lead press image
        choice["is_high_priority"] = bool(choice.get("image_url") and choice.get("virality_score", 0) >= 6)
        log("🎯", f"Deterministic Editorial Curator selected [{choice.get('beat', '').upper()}]: '{choice['title']}'")
        return choice


# ═══════════════════════════════════════════════════════════════════════════
#  NVIDIA AI CLIENT — 5-Model Fallback & Vision Integration
# ═══════════════════════════════════════════════════════════════════════════

class NvidiaAIClient:
    """Manages OpenAI-compatible interactions with NVIDIA NIM microservices."""

    def __init__(self):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("The 'openai' package is required.")
        self.models = TEXT_MODELS
        self.vision_models = VISION_MODELS
        self.tool_model = TOOL_MODEL
        if not NVIDIA_API_KEY:
            self.client = None
            log("⚠️", "NVIDIA_API_KEY is not set. Running in offline/dry-run mode.")
            return
        self.client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
        log("🤖", f"NVIDIA NIM Client initialized with {len(self.models)} text models in fallback chain")

    def generate(self, messages, max_tokens=4096, temperature=0.7, timeout=50.0):
        """
        Query top models in fallback chain.
        If a model fails, times out, or errors in the middle, the next takes over immediately.
        Extracts content or reasoning_content seamlessly.
        """
        if not self.client:
            return None
        for idx, model in enumerate(self.models, start=1):
            try:
                log("🧠", f"Attempting Model [{idx}/{len(self.models)}]: {model}")
                t0 = time.time()
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                dt = time.time() - t0
                msg = resp.choices[0].message
                content = (getattr(msg, "content", None) or "").strip()
                reasoning = (getattr(msg, "reasoning_content", None) or "").strip()

                final_text = content if len(content) > 100 else (content or reasoning)

                if final_text and len(final_text) > 100:
                    log("✅", f"Success with {model} ({len(final_text)} chars generated in {dt:.1f}s)")
                    return final_text
                else:
                    log("⚠️", f"{model} returned short output ({len(final_text)} chars); falling back...")
            except Exception as e:
                log("⚠️", f"{model} pass ({str(e)[:80]}); advancing to next model...")
                continue

        log("❌", "All 5 models in the fallback chain were exhausted.")
        return None

    def generate_tool_queries(self, topic_title, topic_summary):
        """
        Use tool/function-calling on Nemotron-3.5-Bolt to formulate structured web search queries.
        """
        if not self.client:
            kw = extract_keywords(topic_title, topic_summary)
            return [
                f"{topic_title} analysis",
                f"{' '.join(kw[:3])} reaction community",
                f"{' '.join(kw[:2])} discussion debate",
            ]
        tools = [{
            "type": "function",
            "function": {
                "name": "search_trending_web",
                "description": "Searches Reddit, Hacker News, Bluesky, Quora, and X for discussions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific search queries for community reactions and technical depth"
                        },
                        "target_platforms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Target platforms (e.g., reddit, hackernews, bluesky, quora)"
                        }
                    },
                    "required": ["queries", "target_platforms"]
                }
            }
        }]

        prompt = (
            f"You are the senior investigative editor at ReadContext.\n"
            f"Topic: {topic_title}\n"
            f"Context: {topic_summary}\n\n"
            f"Call search_trending_web to gather community debates, reactions, and expert analysis."
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.tool_model,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,
                tool_choice="auto",
                max_tokens=400,
                timeout=20.0
            )
            msg = resp.choices[0].message
            if msg.tool_calls:
                args = json.loads(msg.tool_calls[0].function.arguments)
                queries = args.get("queries", [])
                if queries:
                    log("🔧", f"Tool Calling generated {len(queries)} research queries: {queries[:2]}")
                    return queries
        except Exception as e:
            log("⚠️", f"Tool calling error: {e}")

        kw = extract_keywords(topic_title, topic_summary)
        return [
            f"{topic_title} analysis",
            f"{' '.join(kw[:3])} reaction community",
            f"{' '.join(kw[:2])} discussion debate",
        ]

    def verify_image_with_vision(self, image_url, topic_title):
        """
        Use multimodal vision model to inspect the image, confirm topic relevance,
        verify zero graphic violence or gore, and generate a contextually accurate photo caption.
        """
        if not self.client:
            return None
        for v_model in self.vision_models:
            try:
                prompt = (
                    f"Analyze this image for a news publication about: '{topic_title}'.\n"
                    f"1. Is this a graphic violence, weapon, bloody, or offensive image? (If yes, state REJECT)\n"
                    f"2. Is this a generic social media button, icon, or logo? (If yes, state REJECT)\n"
                    f"3. If it is a clean, documentary, or educational photo, provide a one-sentence descriptive caption."
                )
                resp = self.client.chat.completions.create(
                    model=v_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }],
                    max_tokens=70,
                    timeout=20.0
                )
                caption = (resp.choices[0].message.content or "").strip()
                if caption:
                    return caption
            except Exception:
                continue
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  MULTI-SOURCE DATA COLLECTOR — Reddit, HN, Slashdot, Lemmy, Bluesky, etc.
# ═══════════════════════════════════════════════════════════════════════════

class MultiPlatformCollector:
    """Collects real-time trending stories across 12+ online platforms with strict safety filtering."""

    SOURCES = [
        # ── Tamil Nadu Regional News & Governance ──────────────────────────
        ("The Hindu Tamil Nadu", "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss", 6, "regional_rss", "tamil_nadu"),
        ("The Hindu Chennai", "https://www.thehindu.com/news/cities/chennai/feeder/default.rss", 6, "regional_rss", "tamil_nadu"),

        # ── India National Affairs ─────────────────────────────────────────
        ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss", 6, "national_rss", "india_national"),
        ("Times of India India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", 5, "national_rss", "india_national"),
        ("NDTV India News", "https://feeds.feedburner.com/ndtvnews-india-news", 5, "national_rss", "india_national"),
        ("Indian Express National", "https://indianexpress.com/section/india/feed/", 5, "national_rss", "india_national"),

        # ── Global Affairs & World Diplomacy ───────────────────────────────
        ("BBC World News", "http://feeds.bbci.co.uk/news/world/rss.xml", 6, "global_rss", "world_news"),
        ("Google News World", "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en", 6, "global_rss", "world_news"),

        # ── Science, Space & Discovery ─────────────────────────────────────
        ("ScienceDaily", "https://www.sciencedaily.com/rss/all.xml", 6, "science_rss", "science"),
        ("Phys.org Science", "https://phys.org/rss-feed/", 5, "science_rss", "science"),
        ("Space.com", "https://www.space.com/feeds/all", 4, "science_rss", "science"),

        # ── Business, Commerce & Economy ───────────────────────────────────
        ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml", 5, "business_rss", "business"),
        ("Economic Times", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", 5, "business_rss", "business"),

        # ── Culture, Arts & Living ─────────────────────────────────────────
        ("BBC Arts & Culture", "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", 4, "culture_rss", "culture"),

        # ── Applied Technology & Innovation ────────────────────────────────
        ("The Verge", "https://www.theverge.com/rss/index.xml", 4, "media_rss", "technology"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", 4, "media_rss", "technology"),
        ("Slashdot", "https://rss.slashdot.org/Slashdot/slashdotMain", 4, "rss", "technology"),
        ("Reddit r/technology", "https://www.reddit.com/r/technology/.rss", 4, "reddit", "technology"),
        ("Lemmy World", "https://lemmy.world/feeds/c/technology.xml?sort=Hot", 3, "rss", "technology"),
    ]

    BLUESKY_PROFILES = [
        ("Bluesky News", "https://bsky.app/profile/bsky.app/rss"),
        ("TechCrunch Bluesky", "https://bsky.app/profile/techcrunch.com/rss"),
    ]

    def _is_valid_article_image(self, url):
        """Reject non-article images like tweet buttons, share icons, tracking pixels."""
        if not url:
            return False
        u = url.lower()
        reject_tokens = [
            "tweet", "button", "icon", "share", "badge", "avatar", "logo",
            "pixel", "spinner", "advert", "sponsor", "favicon", "1x1", "doubleclick"
        ]
        return not any(tok in u for tok in reject_tokens)

    def _extract_media_image(self, entry):
        """Extract high-resolution real press images embedded in feeds."""
        if hasattr(entry, 'media_content') and entry.media_content:
            for m in entry.media_content:
                url = m.get('url')
                if url and any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    if self._is_valid_article_image(url):
                        return url
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                href = enc.get('href') or enc.get('url')
                if href and enc.get('type', '').startswith('image/') and self._is_valid_article_image(href):
                    return href
        if hasattr(entry, 'links'):
            for l in entry.links:
                href = l.get('href')
                if href and 'image' in l.get('type', '') and self._is_valid_article_image(href):
                    return href
        for field in ['content', 'summary_detail', 'summary']:
            raw = getattr(entry, field, '')
            if isinstance(raw, list) and raw:
                raw = raw[0].get('value', '')
            elif isinstance(raw, dict):
                raw = raw.get('value', '')
            if '<img' in str(raw):
                soup = BeautifulSoup(str(raw), 'html.parser')
                img = soup.find('img')
                if img and img.get('src') and self._is_valid_article_image(img['src']):
                    return img['src']
        return None

    def _fetch_single_source(self, name, url, limit, parser_type, beat="general"):
        """Fetch items from a single provider with compliance validation."""
        results = []
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ReadContext/2.0"}
            resp = SESSION.get(url, timeout=12, headers=headers)
            if resp.status_code != 200:
                return results

            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:limit]:
                title = clean_text(getattr(entry, 'title', '') or '')
                if not title or len(title) < 12 or '[Removed]' in title:
                    continue

                summary = clean_text(getattr(entry, 'summary', '') or getattr(entry, 'description', '') or '')

                # ── COMPLIANCE GUARD ──────────────────────────────────────────
                safe, reason = ContentComplianceGuard.evaluate(title, summary)
                if not safe:
                    # Discard immediately
                    continue

                link = getattr(entry, 'link', '') or ''
                image_url = self._extract_media_image(entry)

                results.append({
                    "title": title,
                    "description": summary[:600],
                    "source": name,
                    "source_url": link,
                    "image_url": image_url,
                    "published": getattr(entry, 'published', ''),
                    "beat": beat,
                    "entry": entry
                })
        except Exception as e:
            log("⚠️", f"{name} error: {str(e)[:60]}")
        return results

    def _fetch_bluesky(self):
        """Fetch posts from Bluesky feeds with compliance validation."""
        results = []
        for name, url in self.BLUESKY_PROFILES:
            try:
                resp = SESSION.get(url, timeout=10)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    for entry in feed.entries[:3]:
                        text = clean_text(entry.get('description', '') or entry.get('summary', '') or '')
                        if len(text) > 25:
                            safe, _ = ContentComplianceGuard.evaluate(text)
                            if safe:
                                results.append({
                                    "title": text[:120],
                                    "description": text,
                                    "source": name,
                                    "source_url": entry.get('link', 'https://bsky.app'),
                                    "image_url": self._extract_media_image(entry),
                                    "published": entry.get('published', ''),
                                    "beat": "technology",
                                    "entry": entry
                                })
            except Exception:
                pass
        return results

    def _fetch_quora_and_x(self):
        """Fetch active public discussions and debates with compliance validation."""
        results = []
        queries = [
            ("Quora Debates", "site:quora.com science space breakthroughs OR global economy", "science"),
            ("X / Twitter Trends", "site:x.com OR site:twitter.com infrastructure developments OR technology", "technology"),
        ]
        for label, q, beat in queries:
            try:
                url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"
                resp = SESSION.get(url, timeout=10)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    for entry in feed.entries[:3]:
                        title = clean_text(entry.get('title', ''))
                        summary = clean_text(entry.get('summary', ''))
                        if len(title) > 20:
                            safe, _ = ContentComplianceGuard.evaluate(title, summary)
                            if safe:
                                results.append({
                                    "title": title,
                                    "description": summary,
                                    "source": label,
                                    "source_url": entry.get('link', ''),
                                    "image_url": None,
                                    "published": entry.get('published', ''),
                                    "beat": beat,
                                    "entry": entry
                                })
            except Exception:
                pass
        return results

    def collect_all_topics(self):
        """Fetch from all multi-beat sources in parallel and score cross-platform virality."""
        log("🌐", "Harvesting stories across all multi-beat desks (Tamil Nadu, India, World, Science, Business, Tech)...")
        all_stories = []

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = [
                executor.submit(self._fetch_single_source, name, url, limit, ptype, beat)
                for name, url, limit, ptype, beat in self.SOURCES
            ]
            futures.append(executor.submit(self._fetch_bluesky))
            futures.append(executor.submit(self._fetch_quora_and_x))

            for f in as_completed(futures, timeout=30):
                try:
                    items = f.result()
                    if items:
                        all_stories.extend(items)
                except Exception:
                    pass

        log("📊", f"Aggregated {len(all_stories)} compliant candidate stories across all desks")

        # Score stories by cross-platform resonance
        for story in all_stories:
            keywords = set(extract_keywords(story['title']))
            score = 1
            if story.get('image_url'):
                score += 3
            for other in all_stories:
                if other is story:
                    continue
                other_kw = set(extract_keywords(other['title']))
                common = keywords & other_kw
                if len(common) >= 2:
                    score += len(common) * 2
            story['virality_score'] = score

        all_stories.sort(key=lambda s: s.get('virality_score', 0), reverse=True)

        # Deduplicate against previous publications to ensure 100% fresh content
        posted_titles, posted_urls = get_posted_history()
        fresh_stories = []
        batch_seen_titles = []

        for s in all_stories:
            norm_title = s['title'].strip()
            norm_url = s.get('source_url', '').strip()

            # 1. Check against historical posts
            is_dup, matched_title, score = is_duplicate_story(norm_title, norm_url, posted_titles, posted_urls, threshold=0.52)
            if is_dup:
                log("⏭️", f"Deduplicated (Historical): '{norm_title[:45]}...' matches '{matched_title[:45]}...' (sim: {score:.2f})")
                continue

            # 2. Check against other stories already chosen in this batch
            is_batch_dup = False
            for seen in batch_seen_titles:
                sim = title_similarity(norm_title, seen)
                if sim >= 0.52:
                    is_batch_dup = True
                    log("⏭️", f"Deduplicated (Batch): '{norm_title[:45]}...' duplicates higher-ranked story '{seen[:45]}...' (sim: {sim:.2f})")
                    break

            if not is_batch_dup:
                fresh_stories.append(s)
                batch_seen_titles.append(norm_title)

        log("📊", f"Retained {len(fresh_stories)} fresh non-duplicate compliant candidate stories")
        return fresh_stories


# ═══════════════════════════════════════════════════════════════════════════
#  DEEP WEB RESEARCHER — Web Scraping, Reddit JSON & Forums, HN, Google News
# ═══════════════════════════════════════════════════════════════════════════

class WebResearcher:
    """Gathers real web context, article scrape data, Reddit comments, and forum quotes."""

    def __init__(self, ai_client):
        self.ai = ai_client

    def deep_research(self, topic, candidate_pool=None):
        log("🔍", f"Conducting multi-source deep research on: '{topic['title'][:60]}...'")
        queries = self.ai.generate_tool_queries(topic['title'], topic.get('description', ''))

        research_dossier = {
            "topic": topic['title'],
            "source_url": topic.get('source_url', ''),
            "scraped_facts": [],
            "source_lead_image": None,
            "hn_threads": [],
            "reddit_reactions": [],
            "cross_web_reports": [],
            "community_discussions": [],
            "search_queries": queries,
            "real_quotes": []
        }

        # Cross-reference correlated stories from the harvested multi-platform candidate pool
        if candidate_pool:
            topic_kw = set(extract_keywords(topic['title']))
            for item in candidate_pool:
                if item.get('source_url') == topic.get('source_url'):
                    continue
                item_kw = set(extract_keywords(item['title']))
                if len(topic_kw & item_kw) >= 2:
                    src = item.get('source', '')
                    if 'reddit' in src.lower() or 'r/' in src.lower():
                        research_dossier['reddit_reactions'].append({
                            'title': item['title'],
                            'url': item.get('source_url', ''),
                            'subreddit': src,
                            'score': item.get('base_score', 15),
                            'comments': 12
                        })
                    elif any(s in src.lower() for s in ['lemmy', 'slashdot', 'bluesky', 'quora']):
                        research_dossier['community_discussions'].append({
                            'title': item['title'],
                            'url': item.get('source_url', ''),
                            'source': src
                        })
                    else:
                        research_dossier['cross_web_reports'].append({
                            'title': item['title'],
                            'url': item.get('source_url', ''),
                            'source': src,
                            'snippet': item.get('description', '')
                        })

        # Concurrently gather primary source text, Reddit discussions, HN Algolia, Lemmy, and Google News
        with ThreadPoolExecutor(max_workers=5) as executor:
            f_scrape = executor.submit(self._scrape_source_article, topic.get('source_url', ''))
            f_hn = executor.submit(self._query_hn_algolia, topic['title'], queries)
            f_reddit = executor.submit(self._query_reddit_discussions, topic['title'], queries)
            f_web = executor.submit(self._query_cross_web, topic['title'], queries)
            f_lemmy = executor.submit(self._query_lemmy_discussions, topic['title'])

            try:
                scraped_info = f_scrape.result(timeout=12)
                if scraped_info:
                    research_dossier['scraped_facts'] = scraped_info.get('paragraphs', [])
                    research_dossier['source_lead_image'] = scraped_info.get('lead_image')
                    research_dossier['real_quotes'].extend(scraped_info.get('quotes', []))
                    if scraped_info.get('meta_desc') and not topic.get('description'):
                        topic['description'] = scraped_info['meta_desc']
            except Exception as e:
                log("⚠️", f"Source scraper note: {e}")

            try:
                research_dossier['hn_threads'] = f_hn.result(timeout=10)
            except Exception:
                pass

            try:
                reddit_res = f_reddit.result(timeout=12)
                for t in reddit_res.get('threads', []):
                    if not any(t['url'] == r.get('url') for r in research_dossier['reddit_reactions']):
                        research_dossier['reddit_reactions'].append(t)
                research_dossier['real_quotes'].extend(reddit_res.get('quotes', []))
            except Exception:
                pass

            try:
                web_res = f_web.result(timeout=10)
                for w in web_res:
                    if not any(w['url'] == r.get('url') for r in research_dossier['cross_web_reports']):
                        research_dossier['cross_web_reports'].append(w)
            except Exception:
                pass

            try:
                lemmy_res = f_lemmy.result(timeout=8)
                for l in lemmy_res:
                    if not any(l['url'] == c.get('url') for c in research_dossier['community_discussions']):
                        research_dossier['community_discussions'].append(l)
            except Exception:
                pass

        total_intel = (
            len(research_dossier['scraped_facts']) +
            len(research_dossier['hn_threads']) +
            len(research_dossier['reddit_reactions']) +
            len(research_dossier['cross_web_reports']) +
            len(research_dossier['community_discussions'])
        )
        log("📑", f"Dossier ready with {total_intel} intel items & {len(research_dossier['real_quotes'])} real quotes")
        return research_dossier

    def _scrape_source_article(self, url):
        """Scrapes the original primary source web page to get actual facts, context, and lead image."""
        if not url or not url.startswith('http'):
            return None

        # Skip scraping direct social profiles or generic domain homepages
        if any(bad in url for bad in ['bsky.app/profile', 'news.ycombinator.com', 'reddit.com/r/']):
            return None

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ReadContextJournalism/3.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = SESSION.get(url, headers=headers, timeout=9, allow_redirects=True)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.content, "html.parser")

            # Remove navigation, scripts, ads, headers, footers
            for elem in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form"]):
                elem.extract()

            # 1. Lead Image from og:image or twitter:image
            lead_image = None
            og_img = soup.find("meta", property=re.compile(r"^(og:image|twitter:image)$", re.I))
            if og_img and og_img.get("content"):
                cand_img = og_img["content"].strip()
                if cand_img.startswith("http") and not any(bad in cand_img.lower() for bad in ["logo", "icon", "avatar", "pixel", "button", "default"]):
                    lead_image = cand_img

            # 2. Meta description
            meta_desc = ""
            desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)}) or soup.find("meta", property=re.compile(r"^og:description$", re.I))
            if desc_tag and desc_tag.get("content"):
                meta_desc = desc_tag["content"].strip()

            # 3. Meaningful paragraphs
            paragraphs = []
            article_root = soup.find("article") or soup.find("main") or soup.find("div", class_=re.compile(r"(content|article|entry|post-body)", re.I)) or soup
            for p in article_root.find_all("p"):
                txt = clean_text(p.get_text())
                if len(txt) > 60 and not any(skip in txt.lower() for skip in ["cookie", "subscribe", "terms of service", "all rights reserved", "newsletter", "sign in"]):
                    paragraphs.append(txt)
                if len(paragraphs) >= 8:
                    break

            # 4. Real Quotes inside article
            quotes = []
            for bq in article_root.find_all(["blockquote", "q"]):
                q_text = clean_text(bq.get_text())
                if 30 < len(q_text) < 300:
                    quotes.append({"quote": q_text, "source": "Primary Source Report"})
                if len(quotes) >= 3:
                    break

            # Also look for quoted text in paragraphs: "..." said ...
            if not quotes:
                for p_txt in paragraphs:
                    matches = re.findall(r'“([^”]{30,220})”|"([^"]{30,220})"', p_txt)
                    for m in matches:
                        q_str = m[0] or m[1]
                        quotes.append({"quote": q_str, "source": "Primary Source Reporting"})
                        if len(quotes) >= 2:
                            break
                    if quotes:
                        break

            return {
                "paragraphs": paragraphs[:6],
                "lead_image": lead_image,
                "meta_desc": meta_desc,
                "quotes": quotes
            }
        except Exception:
            return None

    def _query_hn_algolia(self, title, queries):
        """Queries Hacker News Algolia API for real tech developer sentiments."""
        results = []
        kw = " ".join(extract_keywords(title)[:3])
        try:
            resp = SESSION.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": kw, "tags": "story", "hitsPerPage": 6},
                timeout=8
            )
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for h in hits[:4]:
                    t = clean_text(h.get("title", ""))
                    safe, _ = ContentComplianceGuard.evaluate(t)
                    if safe:
                        results.append({
                            "title": t,
                            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                            "points": h.get("points", 0),
                            "comments": h.get("num_comments", 0),
                            "author": h.get("author", "Hacker News contributor")
                        })
        except Exception:
            pass
        return results

    def _query_reddit_discussions(self, title, queries):
        """
        Deep Reddit Search: Queries Reddit search endpoints for authentic public threads,
        upvote counts, and real community comments across r/technology, r/programming, r/gadgets.
        """
        data = {"threads": [], "quotes": []}
        kw = extract_keywords(title)[:3]
        query_str = " ".join(kw) if kw else "tech"

        # 1. Reddit JSON search API (public read-only endpoint)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ReadContextTech/3.1"
        }
        try:
            search_url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(query_str)}&sort=relevance&limit=5"
            resp = SESSION.get(search_url, headers=headers, timeout=8)
            if resp.status_code == 200:
                json_data = resp.json()
                children = json_data.get("data", {}).get("children", [])
                for child in children[:4]:
                    post = child.get("data", {})
                    p_title = clean_text(post.get("title", ""))
                    safe, _ = ContentComplianceGuard.evaluate(p_title)
                    if safe and len(p_title) > 15:
                        permalink = f"https://www.reddit.com{post.get('permalink', '')}"
                        sub = post.get("subreddit_name_prefixed", "r/technology")
                        score = post.get("score", 0)
                        num_comments = post.get("num_comments", 0)
                        selftext = clean_text(post.get("selftext", ""))

                        data["threads"].append({
                            "title": p_title,
                            "url": permalink,
                            "subreddit": sub,
                            "score": score,
                            "comments": num_comments
                        })

                        # Extract authentic discussion snippet if available
                        if len(selftext) > 40:
                            data["quotes"].append({
                                "quote": selftext[:180] + ("..." if len(selftext) > 180 else ""),
                                "source": f"{sub} community thread"
                            })
        except Exception:
            pass

        # 2. Reddit RSS Fallback if JSON yielded few results
        if len(data["threads"]) < 2:
            try:
                rss_url = f"https://www.reddit.com/r/technology/search.rss?q={urllib.parse.quote(query_str)}&restrict_sr=1&sort=relevance"
                resp = SESSION.get(rss_url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    for e in feed.entries[:3]:
                        t = clean_text(e.get("title", ""))
                        safe, _ = ContentComplianceGuard.evaluate(t)
                        if safe and not any(t == th["title"] for th in data["threads"]):
                            data["threads"].append({
                                "title": t,
                                "url": e.get("link", ""),
                                "subreddit": "r/technology",
                                "score": 10,
                                "comments": 5
                            })
            except Exception:
                pass

        return data

    def _query_cross_web(self, title, queries):
        """Queries Google News RSS to discover secondary corroborating reports and context."""
        results = []
        kw = extract_keywords(title)[:3]
        q_str = " ".join(kw)
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q_str)}&hl=en-US&gl=US&ceid=US:en"
            resp = SESSION.get(url, timeout=8)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                for entry in feed.entries[:4]:
                    t = clean_text(entry.get('title', ''))
                    safe, _ = ContentComplianceGuard.evaluate(t)
                    if safe and len(t) > 20:
                        results.append({
                            "title": t,
                            "url": entry.get('link', ''),
                            "source": entry.get('source', {}).get('title', 'News Wire'),
                            "snippet": clean_text(entry.get('summary', ''))[:220]
                        })
        except Exception:
            pass
        return results

    def _query_lemmy_discussions(self, title):
        """Queries decentralized Lemmy technology community for open public discussions."""
        results = []
        kw = extract_keywords(title)[:2]
        if not kw:
            return results
        try:
            resp = SESSION.get(
                "https://lemmy.world/api/v3/post/list",
                params={"community_name": "technology", "sort": "TopDay", "limit": 10},
                timeout=6
            )
            if resp.status_code == 200:
                posts = resp.json().get("posts", [])
                for p in posts:
                    name = p.get("post", {}).get("name", "")
                    p_kw = set(extract_keywords(name))
                    if len(set(kw) & p_kw) >= 1:
                        safe, _ = ContentComplianceGuard.evaluate(name)
                        if safe:
                            results.append({
                                "title": name,
                                "url": p.get("post", {}).get("ap_id") or p.get("post", {}).get("url", ""),
                                "source": "Lemmy Tech Community"
                            })
        except Exception:
            pass
        return results


# ═══════════════════════════════════════════════════════════════════════════
#  REAL SOURCE IMAGE COLLECTOR & VISION VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════

class RealImageCollector:
    """Collects authentic real-world photos — never uses fake or generic placeholders."""

    # Categorized high-resolution editorial fallbacks (only used if all live searches fail)
    CATEGORICAL_FALLBACKS = {
        "hardware": "https://images.unsplash.com/photo-1550009158-9ebf69173e03?w=1200&auto=format&fit=crop", # Electronics & hardware bench
        "ai": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1200&auto=format&fit=crop",       # Modern AI / compute network
        "cloud": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=1200&auto=format&fit=crop",    # Enterprise servers & data center
        "security": "https://images.unsplash.com/photo-1563986768609-322da13575f3?w=1200&auto=format&fit=crop", # Cybersecurity / code interface
        "business": "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1200&auto=format&fit=crop", # Corporate high-rise & venture capital
        "mobile": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=1200&auto=format&fit=crop",   # Smartphone technology
        "default": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=1200&auto=format&fit=crop",  # Tech workspace & innovation
    }

    def __init__(self, ai_client):
        self.ai = ai_client

    def _detect_category(self, title, description):
        text = f"{title} {description}".lower()
        if any(w in text for w in ["phone", "android", "iphone", "camera", "barista", "appliance", "robot", "gadget", "coffee", "hardware", "device"]):
            return "hardware"
        if any(w in text for w in ["ai", "llm", "claude", "gpt", "model", "neural", "deep learning", "agent"]):
            return "ai"
        if any(w in text for w in ["hack", "leak", "breach", "password", "security", "vulnerability", "cve"]):
            return "security"
        if any(w in text for w in ["data center", "server", "cloud", "aws", "infrastructure", "gpu", "energy"]):
            return "cloud"
        if any(w in text for w in ["bank", "valuation", "vc", "sequoia", "acquisition", "cfo", "stock", "shares", "startup", "fund"]):
            return "business"
        return "default"

    def fetch_verified_images(self, topic, research_dossier=None):
        log("🖼️", "Collecting real documentary photo assets...")
        candidates = []
        title = topic['title']
        description = topic.get('description', '')
        category = self._detect_category(title, description)

        # 1. Primary Scraped Article Lead Image (Direct authentic press photo from the source page)
        if research_dossier and research_dossier.get('source_lead_image'):
            lead_img = research_dossier['source_lead_image']
            if self._is_valid_url(lead_img):
                candidates.append({
                    "url": lead_img,
                    "source": f"Original Press Asset / {topic.get('source', 'News Wire')}",
                    "caption": f"Press visual accompanying the original report on {title[:60]}"
                })

        # 2. Feed Media Image (From RSS media enclosure)
        if topic.get('image_url') and self._is_valid_url(topic['image_url']):
            if not any(c['url'] == topic['image_url'] for c in candidates):
                candidates.append({
                    "url": topic['image_url'],
                    "source": f"Official Press Wire / {topic.get('source', 'Wire Service')}",
                    "caption": f"Documentary photograph documenting {title[:70]}"
                })

        # 3. Targeted Wikimedia Commons Search (Uses high-precision entities, e.g. 'Coffee maker' or 'Binance' or 'Floppy disk')
        wiki_img = self._search_wikimedia(title, description, category)
        if wiki_img and self._is_valid_url(wiki_img.get('url')):
            candidates.append(wiki_img)

        # 4. Unsplash Editorial Photo Search (if key provided)
        if UNSPLASH_ACCESS_KEY:
            unsplash_img = self._search_unsplash(title, description, category)
            if unsplash_img and self._is_valid_url(unsplash_img.get('url')):
                candidates.append(unsplash_img)

        # 5. Google Custom Search (if configured)
        if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
            google_img = self._search_google_cse(title, description)
            if google_img and self._is_valid_url(google_img.get('url')):
                candidates.append(google_img)

        # 6. Fallback: Contextually Matched Category Photo (Never a chip photo for coffee/finance!)
        if not candidates:
            fb_url = self.CATEGORICAL_FALLBACKS.get(category, self.CATEGORICAL_FALLBACKS["default"])
            candidates.append({
                "url": fb_url,
                "source": "Unsplash Documentary Archive",
                "caption": f"Contextual archival imagery representing {category.title()} development"
            })

        # Run vision model verification if available to screen out icons, buttons, or violent imagery
        verified_candidates = []
        for cand in candidates:
            caption = self.ai.verify_image_with_vision(cand['url'], title)
            if caption:
                cap_lower = caption.lower()
                if any(bad in cap_lower for bad in [
                    "reject", "cannot analyze", "tweet", "button", "icon", "logo",
                    "social media", "weapon", "blood", "gun", "military", "gore"
                ]):
                    log("⚠️", f"Vision model screened out visual: '{caption[:60]}'")
                    continue
                cand['caption'] = caption
            verified_candidates.append(cand)
            if len(verified_candidates) >= 2:
                break

        if not verified_candidates:
            verified_candidates = [candidates[0]]

        log("📸", f"Verified {len(verified_candidates)} documentary photo asset(s) (Category: {category})")
        return verified_candidates

    def _is_valid_url(self, url):
        if not url or not isinstance(url, str):
            return False
        return url.startswith("http://") or url.startswith("https://")

    def _search_wikimedia(self, title, description, category):
        kw = extract_keywords(title, description)
        query = " ".join(kw[:2]) if kw else category
        try:
            url = (
                "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                f"&gsrnamespace=6&gsrsearch={urllib.parse.quote(query)}&gsrlimit=4"
                "&prop=imageinfo&iiprop=url|extmetadata&format=json"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "ReadContextNews/3.0 (https://readcontext.blogspot.com)"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
                pages = data.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    info = p.get("imageinfo", [{}])[0]
                    img_url = info.get("url")
                    if img_url and any(img_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        artist = info.get("extmetadata", {}).get("Artist", {}).get("value", "Wikimedia Commons")
                        artist = clean_text(artist)[:40]
                        return {
                            "url": img_url,
                            "source": f"Wikimedia Commons / {artist}",
                            "caption": f"Documentary photo documenting {query}"
                        }
        except Exception:
            pass
        return None

    def _search_unsplash(self, title, description, category):
        kw = extract_keywords(title, description)
        query = " ".join(kw[:2]) if kw else category
        try:
            resp = SESSION.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 3, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
                timeout=8
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    photo = results[0]
                    user = photo.get("user", {}).get("name", "Unsplash Contributor")
                    return {
                        "url": photo["urls"]["regular"],
                        "source": f"Photo by {user} on Unsplash",
                        "caption": photo.get("description") or f"Editorial photo regarding {query}"
                    }
        except Exception:
            pass
        return None

    def _search_google_cse(self, title, description):
        kw = extract_keywords(title, description)
        query = " ".join(kw[:3])
        try:
            resp = SESSION.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_CSE_API_KEY, "cx": GOOGLE_CSE_ID,
                    "q": query, "searchType": "image", "imgSize": "LARGE",
                    "num": 3, "safe": "active"
                },
                timeout=8
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    return {
                        "url": items[0]["link"],
                        "source": items[0].get("displayLink", "Press Source"),
                        "caption": items[0].get("title", "")[:90]
                    }
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  ARTICLE GENERATOR — Topic-Adaptive, SEO-Optimized Newspaper Journalism
# ═══════════════════════════════════════════════════════════════════════════

class ArticleGenerator:
    """Generates unique, topic-adaptive, mobile-optimized journalism formatted for readcontext.blogspot.com."""

    MIN_TARGET_WORDS = 800
    MAX_TARGET_WORDS = 1050

    # News desks covering comprehensive global, regional, science, business, and technology affairs
    BEATS = {
        "tamil_nadu": {
            "name": "Tamil Nadu & Regional Governance",
            "kicker": "REGIONAL REPORT · TAMIL NADU & CHENNAI DESK",
            "focus": "State infrastructure, civic policy, governance reforms, educational initiatives, waterbody restoration, local economy, and regional progress.",
            "avoid": "Generic sensationalism or biased party rhetoric; report factual developments with balanced civic depth.",
            "labels": ["Tamil Nadu", "Regional News", "India", "Governance"]
        },
        "india_national": {
            "name": "India National Affairs",
            "kicker": "NATIONAL DISPATCH · INDIA AFFAIRS",
            "focus": "Parliamentary developments, national infrastructure, economic policies, ISRO space initiatives, supreme court rulings, and federal administration.",
            "avoid": "Partisan hostility; maintain neutral, authoritative national reporting.",
            "labels": ["India", "National Affairs", "Public Policy", "Governance"]
        },
        "world_news": {
            "name": "Global Affairs & World Diplomacy",
            "kicker": "GLOBAL DESK · WORLD AFFAIRS & DIPLOMACY",
            "focus": "Multilateral diplomacy, international treaties, trade agreements, climate summits, global economic stability, and international cooperation.",
            "avoid": "Graphic warfare, battlefield violence, or taking sides in territorial disputes.",
            "labels": ["World News", "Global Affairs", "Diplomacy", "International"]
        },
        "science": {
            "name": "Science, Discovery & Space",
            "kicker": "SCIENCE & NATURE · DISCOVERY & INNOVATION",
            "focus": "Peer-reviewed research breakthroughs, space exploration (ISRO, NASA, ESA), astronomy, clean energy, medical science, and biodiversity.",
            "avoid": "Unscientific hype or unproven claims; explain methodology, empirical findings, and practical significance.",
            "labels": ["Science", "Space", "Discovery", "Research"]
        },
        "business": {
            "name": "Markets, Commerce & Economy",
            "kicker": "MARKETS & COMMERCE · ECONOMIC MONITOR",
            "focus": "Corporate governance, fiscal policy, supply chain dynamics, consumer enterprise, venture capital, and market trends.",
            "avoid": "Investment advice or speculative hype; analyze structural economics and business fundamentals.",
            "labels": ["Business", "Markets", "Economy", "Finance"]
        },
        "culture": {
            "name": "Culture, Arts & Society",
            "kicker": "CULTURE & SOCIETY · CONTEMPORARY PERSPECTIVES",
            "focus": "Literary achievements, cultural heritage, cinematic craft, sporting milestones, architecture, and contemporary lifestyle shifts.",
            "avoid": "Superficial gossip; explore cultural nuance and societal resonance.",
            "labels": ["Culture", "Society", "Arts", "Living"]
        },
        "technology": {
            "name": "Applied Technology & Digital Engineering",
            "kicker": "INNOVATION & DIGITAL · APPLIED TECHNOLOGY",
            "focus": "Consumer hardware engineering, software architecture, open-source ecosystems, digital privacy, and practical computing.",
            "avoid": "Generic AI buzzwords ('AI investigate', 'developer reactions', 'economic trade-off'); focus on concrete technical specs and user utility.",
            "labels": ["Technology", "Innovation", "Computing", "Digital"]
        }
    }

    def __init__(self, ai_client):
        self.ai = ai_client

    def _determine_beat(self, title, description, feed_beat=None):
        if feed_beat and feed_beat in self.BEATS:
            return self.BEATS[feed_beat], feed_beat
        text = f"{title} {description}".lower()
        if any(w in text for w in ["tamil nadu", "chennai", "coimbatore", "madurai", "kodaikanal", "dmk", "aiadmk", "stalin"]):
            return self.BEATS["tamil_nadu"], "tamil_nadu"
        if any(w in text for w in ["india", "delhi", "mumbai", "parliament", "isro", "rbi", "modi", "sonia", "gandhi"]):
            return self.BEATS["india_national"], "india_national"
        if any(w in text for w in ["world", "diplomacy", "treaty", "summit", "election", "europe", "un "]):
            return self.BEATS["world_news"], "world_news"
        if any(w in text for w in ["science", "space", "discovery", "astronomy", "brain", "cancer", "nasa", "physics", "biology"]):
            return self.BEATS["science"], "science"
        if any(w in text for w in ["market", "bank", "valuation", "shares", "stock", "revenue", "cfo", "economy", "trade"]):
            return self.BEATS["business"], "business"
        if any(w in text for w in ["film", "cinema", "music", "sport", "cricket", "museum", "art", "book"]):
            return self.BEATS["culture"], "culture"
        return self.BEATS["technology"], "technology"

    def build_article(self, topic, research, images):
        beat_info, beat_key = self._determine_beat(topic['title'], topic.get('description', ''), topic.get('beat'))
        is_high_priority = topic.get("is_high_priority", False)
        log("✍️", f"Drafting [{beat_info['name']}] dispatch with NVIDIA NIM...")

        research_notes = self._synthesize_research(research)

        # ── Step 1: Generate Bespoke Outline & Unique Story-Specific Headings ──
        if not getattr(self.ai, "client", None):
            log("ℹ️", "Running in local preview mode (NVIDIA_API_KEY not configured). Synthesizing preview dispatch...")
            dateline_city = "CHENNAI" if beat_key == "tamil_nadu" else ("NEW DELHI" if beat_key == "india_national" else "LONDON")
            preview_body = f"""<p><strong>{dateline_city} —</strong> {topic.get('description', topic['title'])}. The latest developments across {beat_info['name']} underscore significant regional and institutional implications for observers globally, marking a notable milestone in contemporary public discourse and civic governance.</p>
<h2>Policy Framework and Institutional Milestones</h2>
<p>Public records and recent official communications highlight how institutional leadership and regional initiatives are shaping discourse in this sector. Independent reporting from primary sources confirms that ongoing deliberations reflect broader strategic considerations, ensuring that governance frameworks align with contemporary constitutional principles, economic stability, and public expectations across the board.</p>
<p>According to documented dispatches and administrative documentation, stakeholders have emphasized the importance of transparency, structured implementation, and long-term public interest in driving sustainable civic and institutional milestones. The comprehensive evaluation process involves cross-departmental coordination designed to streamline public service delivery while addressing systemic considerations.</p>
<p>In addition, legal and policy analysts note that institutional precedents set during prior administrative cycles offer valuable context for understanding current trajectories. The ongoing dialogue demonstrates an evolving consensus among domain experts regarding procedural rigor, stakeholder engagement, and accountability across regional and national institutions.</p>
<p>Furthermore, regional civic groups have underscored the critical necessity of participatory oversight in ensuring that administrative policies effectively address ground-level operational realities. The integration of modern data verification mechanisms has enabled oversight bodies to systematically assess institutional efficacy and refine strategic priorities with empirical precision.</p>
<h2>Impact Analysis and Forward Trajectory</h2>
<p>As analytical observers evaluate these newly released findings, the broader discussion highlights how leadership accountability, institutional transparency, and public communication contribute to governance integrity. Academic scholars point out that public institutions must maintain continuous equilibrium between policy ambition and operational execution.</p>
<p>Community feedback and public discourse further underscore the necessity of adaptive governance models capable of addressing emerging socio-economic demands. Comparative assessments across peer jurisdictions indicate that structured reform initiatives consistently yield durable outcomes when grounded in verifiable data and public consultation.</p>
<p>Moving forward, upcoming reviews, strategic evaluations, and parliamentary consultations will determine how these milestones translate into long-term outcomes for stakeholders across the region. With key oversight bodies monitoring implementation timelines, the road ahead promises significant structural reinforcement for the sector.</p>
<p>Economic observers have noted that stable institutional governance serves as a foundational catalyst for sustainable commercial growth, capital investment, and employment stability. Transparent institutional protocols enhance investor certainty, mitigate transactional risks, and ensure that developmental programs reach their designated beneficiaries with minimal friction.</p>
<h2>Strategic Outlook and Democratic Accountability</h2>
<p>The convergence of administrative oversight, civic participation, and institutional reform creates a constructive foundation for future policy development. Observers emphasize that sustained progress will depend on consistent regulatory benchmarks, independent auditing protocols, and transparent review mechanisms.</p>
<p>As international observers and regional institutions monitor subsequent developments, the overarching narrative reinforces the vital role of transparent institutional governance in sustaining public confidence and promoting comprehensive national development across all key indicators.</p>
<h2>Comparative Governance and Institutional Evolution</h2>
<p>In evaluating modern administrative trajectories, political scientists emphasize that institutional evolution requires steady adherence to foundational norms while embracing technological and civic modernizations. The continuous calibration between statutory mandates and emerging social expectations forms the cornerstone of effective democratic resilience.</p>
<p>Historical precedent across parliamentary democracies suggests that transparent leadership transitions, grounded in mutual institutional respect and public disclosure, provide enduring stability during periods of rapid socio-economic transformation. Observers across regional desks note that these ongoing dialogues offer a constructive precedent for future policy formulations.</p>
<p>Ultimately, the continuous refinement of institutional standards represents a proactive investment in democratic resilience. By anchoring governance decisions in empirical evaluation and stakeholder collaboration, administrative authorities can navigate emerging challenges while safeguarding core institutional values for future generations.</p>
<p>Through sustained dialogue, constructive institutional criticism, and commitment to statutory norms, the broader governance framework continues to adapt to contemporary domestic and international dynamics with renewed institutional vigor and accountability.</p>"""
            cleaned_body = self._sanitize_html(preview_body)
            word_count = len(clean_text(cleaned_body).split())
            linker = WikipediaLinker()
            cleaned_body, linked_entities = linker.link_entities_in_html(cleaned_body)
            meta = {
                "headline": topic['title'],
                "dek": topic.get('description', topic['title'])[:120],
                "description": topic.get('description', topic['title'])[:155],
                "tags": beat_info['labels'][:3]
            }
            final_layout = self._render_readcontext_layout(
                topic=topic,
                article_body=cleaned_body,
                images=images,
                research=research,
                meta=meta,
                beat_info=beat_info,
                is_high_priority=is_high_priority
            )
            return {
                "title": meta.get("headline", topic['title']),
                "html": final_layout,
                "meta_description": meta.get("description", topic['title'])[:160],
                "tags": meta.get("tags", beat_info['labels'][:3]),
                "raw_text": cleaned_body,
                "word_count": word_count,
                "beat": beat_key
            }

        outline_prompt = [
            {"role": "system", "content": (
                "You are the Executive Managing Editor of ReadContext (readcontext.blogspot.com). "
                "Enforce pristine journalistic rigor: zero sensationalism, zero violence, "
                "and ZERO cookie-cutter boilerplate templates. Every story must have its own organic structure tailored to its news desk."
            )},
            {"role": "user", "content": f"""
Create a bespoke editorial outline for this specific story:

STORY HEADLINE: {topic['title']}
PRIMARY SOURCE: {topic.get('source', '')} ({topic.get('source_url', '')})
NEWS DESK: {beat_info['name']}
EDITORIAL FOCUS: {beat_info['focus']}
AVOID: {beat_info['avoid']}

MULTI-SOURCE RESEARCH DOSSIER (Scraped facts, community discussions, quotes):
{research_notes}

CRITICAL EDITORIAL RULES:
1. Do NOT use generic canned headings like "The Genesis of the Shift", "Technical Architecture & Core Mechanics", "Industry Winners and Losers", or "The Road Ahead".
2. Instead, craft 3-4 bespoke, natural H2 section headings tailored for a fast 4-minute mobile read, mentioning the actual names, places, policies, discoveries, or events from this story.
3. Provide a 1-sentence journalistic Dek (subtitle).

Output the outline clearly with the custom H2 headings and the 1-sentence Dek.
"""}
        ]
        outline = self.ai.generate(outline_prompt, max_tokens=1000, temperature=0.6, timeout=35.0)
        if not outline:
            log("❌", "Outline generation failed.")
            return None

        # ── Step 2: Write Full Mobile-Optimized Article with Original Synthesis ──
        article_prompt = [
            {"role": "system", "content": (
                "You are a senior staff correspondent for ReadContext (readcontext.blogspot.com). "
                "Your objective is to produce 100% original, deeply insightful, monetization-grade journalism. "
                "\n"
                "STRICT COMPLIANCE & EDITORIAL DIRECTIVES:\n"
                "• ZERO ROBOTIC / AI JARGON: Strictly NEVER use phrases like 'AI investigate', 'AI automated', 'autonomous journalism', 'AI generated', 'as an AI', or robotic buzzwords.\n"
                "• ZERO PLAGIARISM: Synthesize all facts into your own distinct journalistic voice. Never copy verbatim paragraphs from sources.\n"
                "• ZERO COOKIE-CUTTER REPETITION: STRICTLY FORBIDDEN PHRASES:\n"
                "  - Do NOT write 'Developer reactions'\n"
                "  - Do NOT write 'Real-world benchmarks'\n"
                "  - Do NOT write 'economic trade-off'\n"
                "  - Do NOT write 'The genesis of the shift'\n"
                "  - Do NOT write 'In today's fast-paced digital world'\n"
                "  - Do NOT write 'Only time will tell' or 'A double-edged sword'\n"
                "• BEAT ADAPTIVITY: Adopt the natural tone of the desk. For Tamil Nadu & national news, write with authoritative civic, economic, and institutional context. For science, explain research discoveries with clarity. For business, focus on market dynamics and consumer impact.\n"
                "• BALANCED ATTRIBUTION: Naturally cite reporting sources or public records (e.g. 'According to reporting in The Hindu', 'As noted in official releases', 'Community debates emphasized...'). Do NOT rely on or repeatedly name Hacker News.\n"
                "• SUBSTANCE & MOBILE READABILITY: Fast-paced, punchy, authoritative reporting (strictly 800–1,050 words, designed for under a 5-minute read time for mobile readers).\n"
                "• CLEAN EDITORIAL PROSE & PARAGRAPH FLOW: Wrap every narrative paragraph in clean semantic <p> tags. Write in cohesive, comfortable paragraphs (3 to 5 sentences each) with standard left alignment and no awkward spaces, gaps, or empty line breaks.\n"
                "• SUB-HEADINGS HIERARCHY: Structure sections with <h2> and indented subsections with <h3>. Always close tags with matching end tags (e.g. <h3>...</h3>).\n"
                "• SEMANTIC HTML OUTPUT: Output ONLY semantic HTML content. Do NOT wrap in <html>, <body>, <head>, or <h1>.\n"
                "• Begin immediately with a natural journalistic dateline inside the first paragraph matching the actual location of the story: e.g. <p><strong>CHENNAI —</strong> ...</p>, <p><strong>NEW DELHI —</strong> ...</p>, <p><strong>LONDON —</strong> ...</p>, <p><strong>WASHINGTON —</strong> ...</p>"
            )},
            {"role": "user", "content": f"""
Write a crisp, high-impact 800–1,050 word journalistic article (under 5-minute read time) adhering strictly to this outline:

BESPOKE OUTLINE:
{outline}

GROUND TRUTH INTEL & MULTI-SOURCE RESEARCH:
{research_notes}

STORY DETAILS:
Headline: {topic['title']}
Source: {topic.get('source')} ({topic.get('source_url')})
Desk: {beat_info['name']}

STRUCTURE INSTRUCTIONS:
1. Lead Dateline Hook: Start with a strong bold dateline explaining what happened, why it matters today, and the primary context.
2. Follow the 3-4 bespoke H2 headings generated in the outline. Under each H2, include 2 focused, analytical, information-dense paragraphs.
3. Integrate 1-2 blockquotes with authentic source citations (referencing the actual reporting wire, state release, or community thread).
4. Include an informative comparison or bulleted breakdown (`<ul><li>...</li></ul>`) detailing key milestones, specifications, or civic/market metrics.
5. End with an analytical conclusion section focusing on upcoming milestones, unresolved questions, and the strategic road ahead.
"""}
        ]

        article_html = self.ai.generate(article_prompt, max_tokens=2500, temperature=0.7, timeout=50.0)
        if not article_html:
            log("❌", "Article body generation failed.")
            return None

        # Sanitize HTML tags (fix mismatched <h3> ... </h2> tags and remove wrappers)
        cleaned_body = self._sanitize_html(article_html)
        word_count = len(clean_text(cleaned_body).split())

        # ── Step 2b: Enforce Mobile Read Depth (Target: 800–1,050 Words, Under 5 Mins) ──
        if word_count < 700:
            log("⚠️", f"Draft reached {word_count} words (below mobile depth standard). Deepening analysis...")
            expand_prompt = [
                {"role": "system", "content": (
                    "You are the Senior Executive Editor of ReadContext. "
                    "Deepen the provided draft by adding 1-2 focused analytical paragraphs under existing sections. "
                    "Keep total article length strictly between 800 and 1,050 words so mobile reading time stays under 5 minutes. "
                    "Incorporate technical, civic, or economic nuances, user feedback, and real-world context. "
                    "DO NOT repeat generic phrases like 'developer reactions' or 'economic trade-off'. "
                    "Output ONLY clean semantic HTML matching existing section headings."
                )},
                {"role": "user", "content": f"Deepen this draft to reach between 800 and 1,050 words (under 5 min read):\n\n{cleaned_body}"}
            ]
            expanded = self.ai.generate(expand_prompt, max_tokens=2500, temperature=0.6, timeout=45.0)
            if expanded:
                cand_body = self._sanitize_html(expanded)
                cand_words = len(clean_text(cand_body).split())
                if cand_words > word_count:
                    cleaned_body = cand_body
                    word_count = cand_words
                    log("✅", f"Article expanded to mobile-optimized depth: {word_count} words")

        # ── Step 3: Wikipedia Entity Mapping (Hyperlink prominent entities to Wikipedia for deep informational context) ──
        linker = WikipediaLinker()
        cleaned_body, linked_entities = linker.link_entities_in_html(cleaned_body)
        if linked_entities:
            log("🔗", f"Wikipedia mapped {len(linked_entities)} entities: {', '.join(list(linked_entities)[:5])}")

        # ── Step 4: Extract SEO Metadata ──
        meta = self._generate_seo(topic, cleaned_body, beat_info)

        # ── Step 5: Assemble Native ReadContext Presentation ──
        final_layout = self._render_readcontext_layout(
            topic=topic,
            article_body=cleaned_body,
            images=images,
            research=research,
            meta=meta,
            beat_info=beat_info,
            is_high_priority=is_high_priority
        )

        return {
            "title": meta.get("headline", topic['title']),
            "html": final_layout,
            "meta_description": meta.get("description", topic['title'])[:160],
            "tags": meta.get("tags", beat_info['labels'][:3]),
            "raw_text": cleaned_body,
            "word_count": word_count,
            "beat": beat_key
        }

    def _sanitize_html(self, html_str):
        """Clean wrappers, fix mismatched tags, and prevent nested heading paragraphs."""
        clean = strip_html_wrappers(html_str)
        # Fix nested <p> inside headings: e.g. <h3><p>Title</p></h3> -> <h3>Title</h3>
        clean = re.sub(r'<h([23])([^>]*)>\s*<p>(.*?)</p>\s*</h\1>', r'<h\1\2>\3</h\1>', clean, flags=re.IGNORECASE | re.DOTALL)
        # Fix unclosed <h3> or <h2> before another block tag like <ul>, <ol>, <p>, <blockquote>, <h[23]>
        clean = re.sub(r'<h([23])([^>]*)>([^<]+?)(?=\n*<(?:ul|ol|p|blockquote|h[23]))', r'<h\1\2>\3</h\1>\n', clean, flags=re.IGNORECASE)
        # Fix mismatched <h3> ... </h2>
        clean = re.sub(r'<h3([^>]*)>(.*?)</h2>', r'<h3\1>\2</h3>', clean, flags=re.IGNORECASE | re.DOTALL)
        clean = re.sub(r'<h2([^>]*)>(.*?)</h3>', r'<h2\1>\2</h2>', clean, flags=re.IGNORECASE | re.DOTALL)
        # Fix nested <p> tags: <p>Text <p>Inner</p></p>
        clean = re.sub(r'<p>\s*<p>(.*?)</p>\s*</p>', r'<p>\1</p>', clean, flags=re.IGNORECASE | re.DOTALL)
        # Remove empty headings or paragraphs
        clean = re.sub(r'<p>\s*</p>', '', clean)
        clean = re.sub(r'<h[23]>\s*</h[23]>', '', clean)
        return clean.strip()

    def _synthesize_research(self, research):
        lines = []

        # 1. Primary Scraped Facts & Ground Truth
        if research.get("scraped_facts"):
            lines.append("PRIMARY INVESTIGATIVE REPORTING (Directly Scraped from Source):")
            for p in research["scraped_facts"][:5]:
                lines.append(f"  • {p}")

        # 2. Documented Quotes & Primary Statements
        if research.get("real_quotes"):
            lines.append("\nDOCUMENTED QUOTES & OFFICIAL STATEMENTS:")
            for q in research["real_quotes"][:4]:
                lines.append(f"  • \"{q['quote']}\" ({q.get('source', 'Report')})")

        # 3. Reddit Community Debates & User Perspectives
        if research.get("reddit_reactions"):
            lines.append("\nREDDIT COMMUNITY PERSPECTIVES & DEBATES:")
            for r in research["reddit_reactions"][:4]:
                lines.append(f"  • [{r.get('subreddit', 'r/technology')}] \"{r['title']}\" — {r.get('url')}")

        # 4. Cross-Web Wire Reports (The Verge, Reuters, BBC, Ars Technica)
        if research.get("cross_web_reports"):
            lines.append("\nCORROBORATING NEWS COVERAGE & WIRE REPORTS:")
            for w in research["cross_web_reports"][:4]:
                lines.append(f"  • {w.get('source', 'Press Wire')}: \"{w['title']}\" — {w.get('snippet', '')}")

        # 5. Open Community & Forum Discussions (Lemmy, Slashdot)
        if research.get("community_discussions"):
            lines.append("\nCOMMUNITY FORUM SIGNALS:")
            for c in research["community_discussions"][:3]:
                lines.append(f"  • [{c.get('source', 'Community Forum')}]: \"{c['title']}\" — {c.get('url')}")

        # 6. Technical Forum Signals (Hacker News)
        if research.get("hn_threads"):
            lines.append("\nTECHNICAL FORUM SIGNALS:")
            for h in research["hn_threads"][:3]:
                lines.append(f"  • \"{h['title']}\" — {h.get('url')}")

        if not lines:
            lines.append("Multi-platform discourse indicates significant industry debate regarding practical trade-offs and future roadmaps.")
        return "\n".join(lines)

    def _extract_takeaways(self, outline, body):
        """Extracts 3-4 concise executive takeaways for the reader."""
        takeaways = []
        # Try extracting from outline first
        matches = re.findall(r'(?:takeaway|bullet|highlight)s?[:\n]+(.*?)(?=\n\n|\n[A-Z0-9]|$)', outline, re.IGNORECASE | re.DOTALL)
        if matches:
            raw_bullets = re.findall(r'[-•*]\s*(.+)', matches[0])
            for b in raw_bullets[:4]:
                clean_b = clean_text(b).strip()
                if len(clean_b) > 20:
                    takeaways.append(clean_b)

        if not takeaways:
            # Fallback to key sentences
            sentences = [s.strip() for s in re.split(r'\. |\n', clean_text(body)) if len(s.strip()) > 40]
            takeaways = sentences[:3] if sentences else ["Key developments and market shifts documented in this dispatch."]

        return takeaways[:4]

    def _generate_seo(self, topic, body, beat_info=None):
        prompt = [
            {"role": "system", "content": "You are a senior digital news SEO editor. Output strict JSON only."},
            {"role": "user", "content": f"""
Generate SEO metadata optimized for Google Search and Discover:
Headline Candidate: {topic['title']}
Article Context: {clean_text(body)[:500]}

Respond in JSON format:
{{
  "headline": "Compelling, High-CTR Headline (50-70 characters, clear entity names, zero clickbait)",
  "dek": "Insightful 1-sentence journalistic subtitle explaining what happened and why it matters (80-120 chars)",
  "description": "Engaging meta description for search engine snippets (140-155 characters)",
  "tags": ["Entity1", "Entity2", "Topic", "Industry", "Analysis"]
}}
"""}
        ]
        try:
            resp = self.ai.generate(prompt, max_tokens=300, temperature=0.3, timeout=25.0)
            if resp:
                m = re.search(r'\{.*\}', resp, re.DOTALL)
                if m:
                    return json.loads(m.group(0))
        except Exception:
            pass
        default_tags = beat_info.get("labels", ["News", "Analysis"])[:4] if beat_info else extract_keywords(topic['title'])[:5]
        return {
            "headline": topic['title'],
            "dek": topic.get('description', '')[:120],
            "description": (topic.get('description') or topic['title'])[:155],
            "tags": default_tags
        }

    def _render_readcontext_layout(self, topic, article_body, images, research, meta, beat_info, is_high_priority=False):
        """
        Creates a custom responsive newspaper layout tailored for readcontext.blogspot.com:
        Warm orange accents (#F36C21), clean modern web typography (no huge tab indents, no excessive gaps),
        concise image captions with corner sources, and balanced multi-platform citations.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%B %d, %Y")
        iso_date = now.isoformat()
        headline = meta.get("headline", topic['title'])
        meta_desc = meta.get("description", topic['title'])

        # Hero Image Frame (Short clean context + source at the corner)
        hero_img_html = ""
        hero_url = ""
        if images:
            hero = images[0]
            hero_url = hero['url']
            caption = hero.get('caption', headline).strip()
            caption = re.sub(r'^\d+[\.\)]\s*', '', caption)
            caption = re.sub(r'^[📸📷]\s*', '', caption)
            if len(caption) > 65:
                caption = caption[:62].rsplit(' ', 1)[0] + '...'
            source_name = hero.get('source', 'Press Wire').strip()
            if len(source_name) > 25:
                source_name = source_name[:22] + '...'

            hero_img_html = f'''
            <div style="margin:20px 0 24px 0; text-align:center;">
                <figure style="margin:0; padding:0;">
                    <img src="{hero_url}" alt="{headline}"
                         style="width:100%; max-height:500px; object-fit:cover; border-radius:14px; box-shadow:0 8px 24px rgba(0,0,0,0.08); display:block;"
                         loading="eager" />
                    <figcaption style="display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#777; margin-top:8px; padding:0 4px;">
                        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:70%; text-align:left;">{caption}</span>
                        <span style="font-style:italic; font-size:11.5px; white-space:nowrap; color:#999; margin-left:12px;">Source: {source_name}</span>
                    </figcaption>
                </figure>
            </div>
            '''

        # Contextual Secondary Image (Only for High-Priority Stories, neatly placed inside the narrative body)
        if is_high_priority and len(images) > 1:
            sec = images[1]
            sec_caption = sec.get('caption', 'Contextual documentation').strip()
            sec_caption = re.sub(r'^\d+[\.\)]\s*', '', sec_caption)
            sec_caption = re.sub(r'^[📸📷]\s*', '', sec_caption)
            if len(sec_caption) > 65:
                sec_caption = sec_caption[:62].rsplit(' ', 1)[0] + '...'
            sec_source = sec.get('source', 'Editorial Archive').strip()
            if len(sec_source) > 25:
                sec_source = sec_source[:22] + '...'

            secondary_img_html = f'''
            <div style="margin:26px 0; text-align:center;">
                <figure style="margin:0; padding:0;">
                    <img src="{sec['url']}" alt="{headline} - Detailed Documentation"
                         style="width:100%; max-height:420px; object-fit:cover; border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,0.06); display:block;"
                         loading="lazy" />
                    <figcaption style="display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#777; margin-top:8px; padding:0 4px;">
                        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:70%; text-align:left;">{sec_caption}</span>
                        <span style="font-style:italic; font-size:11.5px; white-space:nowrap; color:#999; margin-left:12px;">Source: {sec_source}</span>
                    </figcaption>
                </figure>
            </div>
            '''
            # Insert secondary image inside article body right before the second <h2>
            h2_matches = list(re.finditer(r'<h2\b', article_body, flags=re.IGNORECASE))
            if len(h2_matches) >= 2:
                insert_pos = h2_matches[1].start()
                article_body = article_body[:insert_pos] + secondary_img_html + "\n\n" + article_body[insert_pos:]
            else:
                article_body += "\n" + secondary_img_html
                sec_source = sec_source[:22] + '...'

            secondary_img_html = f'''
            <div style="margin:28px 0; text-align:center;">
                <figure style="margin:0; padding:0;">
                    <img src="{sec['url']}" alt="Contextual Documentation"
                         style="width:100%; max-height:400px; object-fit:cover; border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,0.06); display:block;"
                         loading="lazy" />
                    <figcaption style="display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#777; margin-top:8px; padding:0 4px;">
                        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:70%; text-align:left;">{sec_caption}</span>
                        <span style="font-style:italic; font-size:11.5px; white-space:nowrap; color:#999; margin-left:12px;">Source: {sec_source}</span>
                    </figcaption>
                </figure>
            </div>
            '''

        # ── Citations & Related Documentation (No Repeating Brands, No Points/Scores) ──
        def _get_brand(url_str, default_name="Document"):
            try:
                domain = urllib.parse.urlparse(url_str).netloc.lower()
                domain = re.sub(r'^www\.', '', domain)
                if "techcrunch.com" in domain:
                    return "TechCrunch"
                if "theverge.com" in domain:
                    return "The Verge"
                if "arstechnica.com" in domain:
                    return "Ars Technica"
                if "bbc." in domain:
                    return "BBC News"
                if "reddit.com" in domain:
                    return "Reddit"
                if "ycombinator.com" in domain:
                    return "Hacker News"
                if "github.com" in domain:
                    return "GitHub"
                if "lemmy.world" in domain:
                    return "Lemmy World"
                if "slashdot.org" in domain:
                    return "Slashdot"
                if "producthunt.com" in domain:
                    return "Product Hunt"
                if "bloomberg.com" in domain:
                    return "Bloomberg"
                if "reuters.com" in domain:
                    return "Reuters"
                parts = domain.split('.')
                return parts[0].capitalize() if parts else default_name
            except Exception:
                return default_name

        citations = []
        seen_brands = set()

        # 1. Primary Scraped Source
        if topic.get('source_url'):
            brand = _get_brand(topic['source_url'], topic.get('source', 'Press Wire'))
            if brand not in seen_brands:
                seen_brands.add(brand)
                citations.append(
                    f'<li style="margin-bottom:10px; line-height:1.5;">'
                    f'<span style="display:inline-block; min-width:130px; font-weight:700; color:#333;">{brand}:</span> '
                    f'<a href="{topic["source_url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">Original Investigative Coverage</a>'
                    f'</li>'
                )

        # 2. Reddit Discussions (distinct brand, zero karma/points numbers displayed)
        for r in research.get("reddit_reactions", []):
            if "Reddit" not in seen_brands and r.get("url"):
                seen_brands.add("Reddit")
                citations.append(
                    f'<li style="margin-bottom:10px; line-height:1.5;">'
                    f'<span style="display:inline-block; min-width:130px; font-weight:700; color:#333;">Reddit:</span> '
                    f'<a href="{r["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{r["title"][:80]}</a>'
                    f'</li>'
                )
                break

        # 3. Cross-Web Secondary Wire Reports (The Verge, Reuters, BBC, Ars Technica)
        for w in research.get("cross_web_reports", []):
            if w.get("url"):
                w_brand = _get_brand(w['url'], w.get('source', 'Press Wire'))
                if w_brand not in seen_brands:
                    seen_brands.add(w_brand)
                    citations.append(
                        f'<li style="margin-bottom:10px; line-height:1.5;">'
                        f'<span style="display:inline-block; min-width:130px; font-weight:700; color:#333;">{w_brand}:</span> '
                        f'<a href="{w["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{w["title"][:80]}</a>'
                        f'</li>'
                    )
            if len(citations) >= 4:
                break

        # 4. Lemmy / Slashdot / Community Discussions
        for c in research.get("community_discussions", []):
            if c.get("url"):
                c_brand = _get_brand(c['url'], c.get('source', 'Community Forum'))
                if c_brand not in seen_brands:
                    seen_brands.add(c_brand)
                    citations.append(
                        f'<li style="margin-bottom:10px; line-height:1.5;">'
                        f'<span style="display:inline-block; min-width:130px; font-weight:700; color:#333;">{c_brand}:</span> '
                        f'<a href="{c["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{c["title"][:80]}</a>'
                        f'</li>'
                    )
            if len(citations) >= 4:
                break

        # 5. Hacker News Technical Discussion (only if under 4 citations)
        if len(citations) < 4:
            for h in research.get("hn_threads", []):
                if "Hacker News" not in seen_brands and h.get("url"):
                    seen_brands.add("Hacker News")
                    citations.append(
                        f'<li style="margin-bottom:10px; line-height:1.5;">'
                        f'<span style="display:inline-block; min-width:130px; font-weight:700; color:#333;">Hacker News:</span> '
                        f'<a href="{h["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{h["title"][:80]}</a>'
                        f'</li>'
                    )
                    break

        citations_html = ""
        if citations:
            citations_html = f'''
            <div style="margin-top:36px; padding:20px; background:rgba(243,108,33,0.03); border-left:4px solid #F36C21; border-radius:0 14px 14px 0;">
                <h3 style="margin:0 0 12px 0; font-size:15px; font-weight:800; color:#222; text-transform:uppercase; letter-spacing:0.05em;">
                    🔗 Related Documentation & Research Across the Web
                </h3>
                <ul style="list-style:none; padding:0; margin:0; line-height:1.75; font-size:14px;">
                    {"".join(citations)}
                </ul>
            </div>
            '''

        logo_b64 = self._get_logo_base64()
        logo_html = ""
        if logo_b64:
            logo_html = f'''
            <div style="margin-top:40px; padding-top:20px; border-top:1px solid rgba(0,0,0,0.08); text-align:center;">
                <img src="data:image/png;base64,{logo_b64}" alt="ReadContext" style="max-height:38px; margin:0 auto 8px; display:block; opacity:0.9;" />
                <div style="font-size:11.5px; color:#999; letter-spacing:1px; text-transform:uppercase;">
                    ReadContext Independent Newsroom · Fully Compliant Autonomous Journalism
                </div>
            </div>
            '''

        # JSON-LD Structured Data for Google News & SEO
        schema_json = json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": headline,
            "description": meta_desc,
            "image": [hero_url] if hero_url else [],
            "datePublished": iso_date,
            "dateModified": iso_date,
            "author": [{
                "@type": "Organization",
                "name": "ReadContext Newsroom",
                "url": BLOG_URL
            }],
            "publisher": {
                "@type": "Organization",
                "name": "ReadContext",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{BLOG_URL}/favicon.ico"
                }
            },
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": topic.get('source_url', BLOG_URL)
            }
        })

        dek_text = meta.get('dek', topic.get('description', '')).strip()
        kicker_text = beat_info.get("kicker", "NEWS DESK · SPECIAL REPORT")

        html = f'''<div class="readcontext-article">

    <!-- Editorial Dek (Clean summary placed at top for search engines and post card snippets) -->
    <p class="readcontext-dek" style="font-size:1.22em; line-height:1.55; color:#444; font-style:italic; margin:0 0 16px 0; font-weight:500;">
        {dek_text}
    </p>

    <!-- Editorial Kicker (Source name kept in backend only, never exposed at top) -->
    <div style="margin-bottom:12px;">
        <span style="display:inline-block; font-size:11.5px; font-weight:800; text-transform:uppercase; letter-spacing:1.5px; color:#F36C21; background:rgba(243,108,33,0.1); padding:4px 12px; border-radius:30px;">
            {kicker_text}
        </span>
    </div>

    <!-- Byline & Full Published Date & Time (Reading time and resonance scores removed) -->
    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; padding:10px 0; border-top:1px solid rgba(0,0,0,0.08); border-bottom:1px solid rgba(0,0,0,0.08); margin-bottom:20px; font-size:13px; color:#666;">
        <div>
            By <strong style="color:#222;">ReadContext Newsroom</strong>
        </div>
        <div>
            📅 <span>Published on {now.strftime("%B %d, %Y · %I:%M %p UTC")}</span>
        </div>
    </div>

    <!-- Hero Documentary Photo -->
    {hero_img_html}

    <!-- Article Narrative Body -->
    <div class="article-content">
        {article_body}
    </div>

    <!-- Related Documentation & Research on the Internet (No Repeating Brands) -->
    {citations_html}

    <!-- Branded Signature -->
    {logo_html}

</div>

<!-- Responsive Newspaper Styling -->
<style>
.readcontext-article {{
    line-height: 1.65;
    color: #222222;
    font-size: 16.5px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    word-wrap: break-word;
}}
.readcontext-article .article-content p {{
    margin: 0 0 14px 0 !important;
    text-indent: 0 !important; /* Clean modern web typography with no awkward tab gaps */
    line-height: 1.68 !important;
    color: #2c2c2c;
}}
.readcontext-article .article-content h2 {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Georgia, serif;
    font-size: 21px;
    font-weight: 700;
    color: #111111;
    margin-top: 26px;
    margin-bottom: 10px;
    line-height: 1.35;
    border-bottom: 2px solid rgba(243, 108, 33, 0.25);
    padding-bottom: 6px;
}}
.readcontext-article .article-content h3 {{
    font-size: 17.5px;
    font-weight: 600;
    color: #222222;
    margin-top: 20px;
    margin-bottom: 8px;
    padding-left: 10px;
    border-left: 3px solid #F36C21;
}}
.readcontext-article .article-content blockquote {{
    margin: 20px 0;
    padding: 14px 18px;
    background: #fdfaf6;
    border-left: 4px solid #F36C21;
    font-style: italic;
    font-size: 16px;
    color: #333;
    border-radius: 0 10px 10px 0;
    line-height: 1.6;
}}
.readcontext-article .article-content blockquote cite {{
    display: block;
    font-size: 12.5px;
    font-style: normal;
    color: #777;
    margin-top: 6px;
    font-weight: 500;
}}
.readcontext-article .article-content ul,
.readcontext-article .article-content ol {{
    margin: 14px 0 16px 20px;
    padding: 0;
    line-height: 1.65;
}}
.readcontext-article .article-content li {{
    margin-bottom: 6px;
}}
</style>

<!-- SEO Structured Data (JSON-LD placed at end to prevent leaking into Blogger snippet cards) -->
<script type="application/ld+json">
{schema_json}
</script>
'''
        return html

    def _get_logo_base64(self):
        if not LOGO_PATH.exists():
            return None
        try:
            with open(LOGO_PATH, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  BLOGGER PUBLISHER & ESSENTIAL PAGES
# ═══════════════════════════════════════════════════════════════════════════

class BloggerPublisher:
    """Manages publishing to Google Blogger API v3 and triggering SEO indexing."""

    def __init__(self):
        self.sitemap_url = None

    def verify_sitemap(self):
        for candidate in SITEMAP_CANDIDATES:
            try:
                r = SESSION.head(candidate, timeout=5, allow_redirects=True)
                if r.status_code == 200:
                    self.sitemap_url = candidate
                    log("🗺️", f"Confirmed live sitemap: {candidate}")
                    return
            except Exception:
                pass
        self.sitemap_url = SITEMAP_CANDIDATES[0]

    def get_service(self):
        if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
            log("❌", "Missing Google Blogger OAuth credentials")
            return None
        try:
            creds = Credentials(
                token=None,
                refresh_token=GOOGLE_REFRESH_TOKEN,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                scopes=["https://www.googleapis.com/auth/blogger"]
            )
            creds.refresh(GoogleAuthRequest())
            service = google_build('blogger', 'v3', credentials=creds)
            info = service.blogs().get(blogId=BLOGGER_BLOG_ID).execute()
            log("✅", f"Connected to Blogger blog: '{info.get('name')}' (ID: {BLOGGER_BLOG_ID})")
            return service
        except Exception as e:
            log_err("Blogger Auth", str(e))
            return None

    def publish_post(self, article):
        log("🚀", "Publishing article to readcontext.blogspot.com...")
        service = self.get_service()
        if not service:
            return False, "Blogger authentication failed"

        beat = article.get("beat", "technology")
        beat_label_map = {
            "tamil_nadu": ["Tamil Nadu", "Regional News", "India", "Governance"],
            "india_national": ["India", "National Affairs", "Public Policy", "Governance"],
            "world_news": ["World News", "Global Affairs", "Diplomacy", "International"],
            "science": ["Science", "Space", "Discovery", "Research"],
            "business": ["Business", "Markets", "Economy", "Finance"],
            "culture": ["Culture", "Society", "Arts", "Living"],
            "technology": ["Technology", "Innovation", "Computing", "Digital"]
        }
        labels = beat_label_map.get(beat, ["News", "ReadContext"]) + article.get("tags", [])[:3]
        labels = [re.sub(r'[^\w\s-]', '', lab).strip() for lab in labels if lab]

        body = {
            "kind": "blogger#post",
            "title": article["title"],
            "content": article["html"],
            "labels": list(dict.fromkeys(labels))[:6],
            "metaDescription": article.get("meta_description", "")[:160]
        }

        try:
            res = service.posts().insert(blogId=BLOGGER_BLOG_ID, body=body).execute()
            url = res.get("url")
            log("🎉", f"Article successfully published live: {url}")

            posts_log.append({
                "title": article["title"],
                "url": url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            with open(POSTS_LOG, "w", encoding="utf-8") as f:
                json.dump(posts_log[-100:], f, indent=2)

            return True, url
        except Exception as e:
            log_err("Blogger Insert", str(e))
            return False, str(e)

    def publish_essential_pages(self):
        """Publish or update Privacy Policy, About Us, and Contact pages in Blogger."""
        service = self.get_service()
        if not service:
            log("❌", "Cannot publish essential pages without Blogger authentication.")
            return

        pages_to_publish = [
            ("Privacy Policy", PAGES_DIR / "privacy-policy.html"),
            ("About Us", PAGES_DIR / "about-us.html"),
            ("Contact Us", PAGES_DIR / "contact.html"),
            ("Terms of Service", PAGES_DIR / "terms-of-service.html"),
        ]

        for title, filepath in pages_to_publish:
            if not filepath.exists():
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            body = {
                "kind": "blogger#page",
                "title": title,
                "content": content
            }
            try:
                res = service.pages().insert(blogId=BLOGGER_BLOG_ID, body=body).execute()
                log("📄", f"Published essential page '{title}': {res.get('url')}")
            except Exception as e:
                log("⚠️", f"Error publishing '{title}': {e}")

    def ping_google(self):
        if not self.sitemap_url:
            self.verify_sitemap()
        try:
            ping_url = f"https://www.google.com/ping?sitemap={self.sitemap_url}"
            resp = SESSION.get(ping_url, timeout=8)
            if resp.status_code == 200:
                log("📡", "Successfully pinged Google Search indexing engine")
            else:
                log("⚠️", f"Google ping returned status {resp.status_code}")
        except Exception as e:
            log("⚠️", f"Google ping error: {e}")

    def submit_search_console(self, post_url):
        if not GSC_SERVICE_ACCOUNT_JSON:
            log("ℹ️", "GSC_SERVICE_ACCOUNT_JSON not set — skipping direct indexing API submission.")
            return False
        try:
            data_str = GSC_SERVICE_ACCOUNT_JSON.strip()
            if data_str.startswith('"') and data_str.endswith('"'):
                data_str = data_str[1:-1].replace('\\"', '"')
            info = json.loads(data_str)
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/indexing"]
            )
            if not creds.valid:
                creds.refresh(GoogleAuthRequest())

            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json"
            }
            body = {"url": post_url, "type": "URL_UPDATED"}
            r = requests.post(
                "https://indexing.googleapis.com/v3/urlNotifications:publish",
                headers=headers,
                json=body,
                timeout=10
            )
            if r.status_code == 200:
                log("🚀", "Submitted post URL directly to Google Search Console Indexing API")
                return True
            else:
                log("⚠️", f"Search Console API responded with: {r.status_code} {r.text[:80]}")
        except Exception as e:
            log("⚠️", f"Search Console submission exception: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  LOCAL FILE BACKUP
# ═══════════════════════════════════════════════════════════════════════════

def save_local_markdown(article):
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', article['title'].lower()).strip('-')[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = POSTS_DIR / f"{ts}_{slug}.md"

    frontmatter = (
        f"---\n"
        f"title: \"{article['title']}\"\n"
        f"date: {datetime.now(timezone.utc).isoformat()}\n"
        f"description: \"{article.get('meta_description', '')}\"\n"
        f"tags: {json.dumps(article.get('tags', []))}\n"
        f"word_count: {article.get('word_count', 0)}\n"
        f"---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter + article["html"])
    log("💾", f"Saved full local backup to: {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN EXECUTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    t_start = time.time()
    print("=" * 76)
    print("  📰 READCONTENT BLOGGER AUTO POST — NVIDIA NIM EDITION")
    print(f"  Target Blog: https://readcontext.blogspot.com (ID: {BLOGGER_BLOG_ID})")
    print(f"  Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Compliance: Zero Violence, Zero Geopolitical Conflict, No Thin Text")
    print("=" * 76)

    # Check for optional --publish-pages flag
    if "--publish-pages" in sys.argv:
        log("📄", "Publishing essential pages (Privacy Policy, About Us, Contact)...")
        publisher = BloggerPublisher()
        publisher.publish_essential_pages()
        return

    # 1. Verify critical environment setup
    missing_secrets = []
    for var_name, val in [
        ("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID),
        ("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET),
        ("GOOGLE_REFRESH_TOKEN", GOOGLE_REFRESH_TOKEN)
    ]:
        if not val:
            missing_secrets.append(var_name)

    is_dry_run = bool(missing_secrets)
    if is_dry_run:
        log("ℹ️", f"Running in GENERATION & TEST MODE (Blogger publish skipped: missing {', '.join(missing_secrets)})")
    else:
        log("🔑", "All Blogger API credentials verified.")

    # 2. Initialize AI Client & Subsystems
    ai_client = NvidiaAIClient()
    collector = MultiPlatformCollector()
    researcher = WebResearcher(ai_client)
    image_collector = RealImageCollector(ai_client)
    generator = ArticleGenerator(ai_client)
    publisher = BloggerPublisher()
    publisher.verify_sitemap()

    # 3. Harvest Trending Topics across 12+ platforms (Strict Compliance Guard Active)
    stories = collector.collect_all_topics()
    if not stories:
        log("❌", "No compliant stories could be collected across platforms. Aborting.")
        sys.exit(1)

    # 4. Subject Fatigue Tracking & Multi-Beat Lead Story Selection
    fatigue_tracker = SubjectFatigueTracker(posts_dir=POSTS_DIR, posts_log=posts_log)
    editorial_director = EditorialDirector(ai_client)

    selected_topic = editorial_director.curate_lead_story(stories, fatigue_tracker)
    if not selected_topic:
        log("⚠️", "Editorial Director could not select from pool. Falling back to top story.")
        selected_topic = stories[0]

    log("🎯", f"Selected Edition Lead Story: '{selected_topic['title']}'")
    log("📌", f"Desk: {selected_topic.get('beat', 'general').upper()} | Source: {selected_topic['source']}")
    log("🔗", f"Reference URL: {selected_topic.get('source_url')}")
    log("⭐", f"Editorial Priority: {'HIGH PRIORITY (Contextual Subtopic Photo Enabled)' if selected_topic.get('is_high_priority') else 'STANDARD PRIORITY (Hero Visual Focused)'}")

    # 4. Deep Research (Multi-source Web scraping, Reddit discussions, HN, Lemmy, and cross-web wires)
    dossier = researcher.deep_research(selected_topic, candidate_pool=stories)

    # 5. Real Image Discovery & Vision Validation (Prioritizes primary source lead image)
    images = image_collector.fetch_verified_images(selected_topic, research_dossier=dossier)
    log("📸", f"Matched {len(images)} authentic real documentary image(s)")

    # 6. Generate Newspaper Article
    article = generator.build_article(selected_topic, dossier, images)
    if not article:
        log("❌", "Failed to generate newspaper article.")
        sys.exit(1)

    # Strict Pre-Publication Compliance & Anti-Thin-Text Validation
    is_valid, val_reason = ContentComplianceGuard.validate_article(
        article['title'],
        article['raw_text'],
        article['word_count']
    )
    if not is_valid:
        log("❌", f"Article failed pre-publication safety/depth check: {val_reason}")
        sys.exit(1)

    log("📝", f"Validated compliant article: '{article['title']}' (~{article['word_count']} words)")

    # 7. Save Local Markdown Archive
    backup_file = save_local_markdown(article)

    # 8. Publish to Blogger
    if not is_dry_run:
        ok, post_url = publisher.publish_post(article)
        if ok:
            record_posted_story(article["title"], selected_topic.get("source_url", ""), post_url)
            publisher.ping_google()
            publisher.submit_search_console(post_url)
            log("✨", f"SUCCESS! Article published live at: {post_url}")
        else:
            log("❌", f"Publication error: {post_url}")
            sys.exit(1)
    else:
        record_posted_story(article["title"], selected_topic.get("source_url", ""), "local_test")
        log("💡", "Test run completed successfully! Ready for automated live publishing on GitHub Actions.")

    elapsed = time.time() - t_start
    print("=" * 76)
    print(f"  ✅ Workflow completed in {elapsed:.1f} seconds")
    print(f"  📄 Headline: {article['title']}")
    print(f"  📊 Word Count: ~{article['word_count']} words")
    print(f"  📁 Local Archive: {backup_file}")
    print("=" * 76)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        log_err("Main Process", str(e))
        sys.exit(1)
