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
   • NO Thin Content: Exhaustive, high-depth coverage (1,500–2,500 words).
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
    6. Thin Text Prevention: Minimum 1,000 words enforced on every published dispatch.
    """

    GRAPHIC_VIOLENCE = [
        r"\b(drone\s*strikes?|air\s*strikes?|missiles?|artillery|casualt(y|ies)|bloodshed|gore|gory|weaponry|warfare|battlefield|bombed|bombing|grenades?|slaughter|genocide|terroris[mt]|military\s*strike|firearms?|gunfire|shootout|massacre|assassination|fatalit(y|ies)|corpses?|severed\s*limbs?|dismember(ed|ment)|torture|suicide|self-harm|firing\s*squad|summary\s*execution)\b",
    ]

    GEOPOLITICAL_CONFLICT = [
        r"\b(ukraine|russia|kremlin|putin|zelensky|gaza|israel|hezbollah|hamas|pentagon|idf|pla|invad(ed|ing|ion)|troops?|battle\s*lines?|annexation|ceasefire\s*violation)\b",
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

    MIN_COMPLIANT_WORDS = 1000

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
#  NVIDIA AI CLIENT — 5-Model Fallback & Vision Integration
# ═══════════════════════════════════════════════════════════════════════════

class NvidiaAIClient:
    """Manages OpenAI-compatible interactions with NVIDIA NIM microservices."""

    def __init__(self):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("The 'openai' package is required.")
        if not NVIDIA_API_KEY:
            raise RuntimeError(
                "NVIDIA_API_KEY is not configured! "
                "Please configure NVIDIA_API_KEY in GitHub Secrets or your environment."
            )
        self.client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
        self.models = TEXT_MODELS
        self.vision_models = VISION_MODELS
        self.tool_model = TOOL_MODEL
        log("🤖", f"NVIDIA NIM Client initialized with {len(self.models)} text models in fallback chain")

    def generate(self, messages, max_tokens=4096, temperature=0.7, timeout=50.0):
        """
        Query top models in fallback chain.
        If a model fails, times out, or errors in the middle, the next takes over immediately.
        Extracts content or reasoning_content seamlessly.
        """
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
        ("Hacker News", "https://news.ycombinator.com/rss", 8, "rss"),
        ("HN High Points", "https://hnrss.org/newest?points=100", 6, "rss"),
        ("Slashdot", "https://rss.slashdot.org/Slashdot/slashdotMain", 5, "rss"),
        ("Lemmy World", "https://lemmy.world/feeds/c/technology.xml?sort=Hot", 5, "rss"),
        ("Reddit r/technology", "https://www.reddit.com/r/technology/.rss", 6, "reddit"),
        ("Reddit r/programming", "https://www.reddit.com/r/programming/.rss", 5, "reddit"),
        ("Product Hunt", "https://www.producthunt.com/feed", 5, "rss"),
        ("TechCrunch", "https://techcrunch.com/feed/", 6, "media_rss"),
        ("The Verge", "https://www.theverge.com/rss/index.xml", 6, "media_rss"),
        ("BBC Technology", "http://feeds.bbci.co.uk/news/technology/rss.xml", 5, "media_rss"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", 5, "media_rss"),
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

    def _fetch_single_source(self, name, url, limit, parser_type):
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
                                    "entry": entry
                                })
            except Exception:
                pass
        return results

    def _fetch_quora_and_x(self):
        """Fetch active public discussions and debates with compliance validation."""
        results = []
        queries = [
            ("Quora Debates", "site:quora.com technology AI breakthrough OR programming"),
            ("X / Twitter Trends", "site:x.com OR site:twitter.com AI breakthrough OR open source software"),
        ]
        for label, q in queries:
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
                                    "entry": entry
                                })
            except Exception:
                pass
        return results

    def collect_all_topics(self):
        """Fetch from all 12+ sources in parallel and score cross-platform virality."""
        log("🌐", "Harvesting stories across all 12+ channels (Strict Compliance Guard Active)...")
        all_stories = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(self._fetch_single_source, name, url, limit, ptype)
                for name, url, limit, ptype in self.SOURCES
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

        log("📊", f"Aggregated {len(all_stories)} compliant tech & science candidate stories")

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

    def deep_research(self, topic):
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
            "search_queries": queries,
            "real_quotes": []
        }

        # Concurrently gather primary source text, Reddit discussions, HN Algolia, and Google News
        with ThreadPoolExecutor(max_workers=4) as executor:
            f_scrape = executor.submit(self._scrape_source_article, topic.get('source_url', ''))
            f_hn = executor.submit(self._query_hn_algolia, topic['title'], queries)
            f_reddit = executor.submit(self._query_reddit_discussions, topic['title'], queries)
            f_web = executor.submit(self._query_cross_web, topic['title'], queries)

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
                research_dossier['reddit_reactions'] = reddit_res.get('threads', [])
                research_dossier['real_quotes'].extend(reddit_res.get('quotes', []))
            except Exception:
                pass

            try:
                research_dossier['cross_web_reports'] = f_web.result(timeout=10)
            except Exception:
                pass

        total_intel = (
            len(research_dossier['scraped_facts']) +
            len(research_dossier['hn_threads']) +
            len(research_dossier['reddit_reactions']) +
            len(research_dossier['cross_web_reports'])
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
    """Generates unique, topic-adaptive, long-form journalism formatted for readcontext.blogspot.com."""

    MIN_TARGET_WORDS = 1400
    MAX_TARGET_WORDS = 2400

    # Archetype styles to ensure distinct narrative structures
    ARCHETYPES = {
        "hardware": {
            "name": "Hardware & Consumer Teardown",
            "focus": "Hands-on ergonomics, engineering compromises, sensor reliability, pricing vs performance, and user longevity.",
            "avoid": "Generic macro-economics or corporate finance jargon when discussing kitchen appliances or consumer gadgets."
        },
        "ai": {
            "name": "Artificial Intelligence & Computational Systems",
            "focus": "Model architecture, latency benchmarks, open-source vs proprietary weights, developer ecosystem adoption, and energy demands.",
            "avoid": "Sci-fi hype or vague predictions; focus on verified capabilities and developer codebases."
        },
        "security": {
            "name": "Cybersecurity & Incident Forensics",
            "focus": "Attack vector analysis, root cause, credential exposure, mitigation steps, and enterprise liability.",
            "avoid": "Fear-mongering; maintain measured, precise technical reporting on the vulnerability."
        },
        "business": {
            "name": "Venture, Valuation & Market Disruption",
            "focus": "Deal mechanics, board-level shifts, investor thesis, competitive market moat, and regulatory antitrust scrutiny.",
            "avoid": "Stock promotion or investment advice; analyze strategic positioning neutrally."
        },
        "general": {
            "name": "Digital Culture & Technology Investigation",
            "focus": "Broader societal adoption, community friction, product philosophy, and cultural footprint.",
            "avoid": "Repetitive formulaic phrases."
        }
    }

    def __init__(self, ai_client):
        self.ai = ai_client

    def _determine_archetype(self, title, description):
        text = f"{title} {description}".lower()
        if any(w in text for w in ["phone", "camera", "barista", "coffee", "appliance", "gadget", "robot", "hardware", "device", "specs"]):
            return self.ARCHETYPES["hardware"]
        if any(w in text for w in ["ai", "llm", "claude", "gpt", "model", "neural", "weights", "agent", "algorithm"]):
            return self.ARCHETYPES["ai"]
        if any(w in text for w in ["hack", "leak", "breach", "password", "security", "cve", "github file", "vulnerability"]):
            return self.ARCHETYPES["security"]
        if any(w in text for w in ["valuation", "bank", "vc", "sequoia", "cfo", "acquisition", "shares", "fintech", "startup", "revolut"]):
            return self.ARCHETYPES["business"]
        return self.ARCHETYPES["general"]

    def build_article(self, topic, research, images):
        log("✍️", "Drafting topic-adaptive investigative journalism with NVIDIA NIM...")

        archetype = self._determine_archetype(topic['title'], topic.get('description', ''))
        research_notes = self._synthesize_research(research)

        # ── Step 1: Generate Bespoke Outline & Unique Story-Specific Headings ──
        outline_prompt = [
            {"role": "system", "content": (
                "You are the Executive Managing Editor of ReadContext, a premier independent technology journal. "
                "Enforce pristine journalistic rigor: zero sensationalism, zero geopolitical bias, zero violence, "
                "and ZERO cookie-cutter boilerplate templates. Every story must have its own organic structure."
            )},
            {"role": "user", "content": f"""
Create a bespoke editorial outline for this specific story:

STORY HEADLINE: {topic['title']}
PRIMARY SOURCE: {topic.get('source', '')} ({topic.get('source_url', '')})
STORY ANGLE / GENRE: {archetype['name']}
EDITORIAL FOCUS: {archetype['focus']}
AVOID: {archetype['avoid']}

MULTI-SOURCE RESEARCH DOSSIER (Scraped facts, Reddit discussions, HN signals, Real quotes):
{research_notes}

CRITICAL EDITORIAL RULES:
1. Do NOT use generic canned headings like "The Genesis of the Shift", "Technical Architecture & Core Mechanics", "Industry Winners and Losers", or "The Road Ahead".
2. Instead, craft 5-6 bespoke, natural H2 section headings that mention the actual names, products, technologies, or controversies from this story.
3. Formulate 4 concrete Key Takeaways (factual and punchy).
4. Provide a 1-sentence journalistic Dek (subtitle).

Output the outline clearly with the custom H2 headings and Key Takeaways.
"""}
        ]
        outline = self.ai.generate(outline_prompt, max_tokens=1500, temperature=0.6, timeout=35.0)
        if not outline:
            log("❌", "Outline generation failed.")
            return None

        # ── Step 2: Write Full Long-Form Article with Original Synthesis ──
        article_prompt = [
            {"role": "system", "content": (
                "You are an investigative technology correspondent for ReadContext (readcontext.blogspot.com). "
                "Your objective is to produce 100% original, deeply insightful, monetization-grade journalism. "
                "\n"
                "STRICT COMPLIANCE & ORIGINALITY DIRECTIVES:\n"
                "• ZERO PLAGIARISM: Synthesize all facts into your own distinct journalistic voice. Never copy verbatim paragraphs from sources.\n"
                "• ZERO COOKIE-CUTTER REPETITION: STRICTLY FORBIDDEN PHRASES:\n"
                "  - Do NOT write 'Developer reactions'\n"
                "  - Do NOT write 'Real-world benchmarks'\n"
                "  - Do NOT write 'economic trade-off'\n"
                "  - Do NOT write 'The genesis of the shift'\n"
                "  - Do NOT write 'In today's fast-paced digital world'\n"
                "  - Do NOT write 'Only time will tell' or 'A double-edged sword'\n"
                "• ADAPTIVE VOCABULARY: Match the natural language of the subject. A coffee gadget or consumer phone should be discussed in terms of user experience, build quality, and real-world testing. A security breach should focus on attack vectors and remediation. An AI launch should focus on computational capabilities.\n"
                "• AUTHENTIC CITATIONS: Use the provided research quotes and community discussions from Reddit and Hacker News. Attribute them accurately.\n"
                "• SUBSTANCE DEPTH: Comprehensive, authoritative reporting (1,500–2,200 words).\n"
                "• PARAGRAPH INDENTATION & STRUCTURE: Every single narrative paragraph MUST be wrapped in <p> tags. Never leave naked text lines or unformatted sentences. Keep each paragraph at 3 to 5 sentences so the typographic tab indentation is clearly visible.\n"
                "• SUB-HEADINGS HIERARCHY: Structure sections with <h2> and indented subsections with <h3>. Always close tags with matching end tags (e.g. <h3>...</h3>).\n"
                "• SEMANTIC HTML OUTPUT: Output ONLY semantic HTML content. Do NOT wrap in <html>, <body>, <head>, or <h1>.\n"
                "• Begin immediately with a professional journalistic dateline inside a paragraph: <p><strong>SAN FRANCISCO —</strong> ...</p>"
            )},
            {"role": "user", "content": f"""
Write an exhaustive, high-impact 1500–2200 word investigative article adhering strictly to this outline:

BESPOKE OUTLINE:
{outline}

GROUND TRUTH INTEL & MULTI-SOURCE RESEARCH:
{research_notes}

STORY DETAILS:
Headline: {topic['title']}
Source: {topic.get('source')} ({topic.get('source_url')})
Genre: {archetype['name']}

STRUCTURE INSTRUCTIONS:
1. Lead Dateline Hook: Start with a strong bold dateline explaining what happened, why it matters today, and the primary tension.
2. Follow the 5-6 bespoke H2 headings generated in the outline. Under each H2, include 2-4 analytical, highly detailed paragraphs.
3. Integrate 2-3 blockquotes with authentic source citations (referencing the actual reporting wire or community thread).
4. Include an informative comparison or bulleted breakdown (`<ul><li>...</li></ul>`) detailing specifications, key milestones, or architectural trade-offs.
5. End with an analytical conclusion section focusing on upcoming milestones, unresolved questions, and the strategic road ahead.
"""}
        ]

        article_html = self.ai.generate(article_prompt, max_tokens=3900, temperature=0.7, timeout=60.0)
        if not article_html:
            log("❌", "Article body generation failed.")
            return None

        # Sanitize HTML tags (fix mismatched <h3> ... </h2> tags and remove wrappers)
        cleaned_body = self._sanitize_html(article_html)
        word_count = len(clean_text(cleaned_body).split())

        # ── Step 2b: Enforce In-Depth Coverage (Minimum 1,200 Words) ────────
        if word_count < 1200:
            log("⚠️", f"Draft reached {word_count} words (below depth standard). Deepening analysis...")
            expand_prompt = [
                {"role": "system", "content": (
                    "You are the Senior Executive Editor of ReadContext. "
                    "Deepen the provided draft by adding 2-3 substantive, highly specific analytical paragraphs under the existing sections. "
                    "Incorporate technical nuances, user feedback, economic realities, and historical context. "
                    "DO NOT repeat generic phrases like 'developer reactions' or 'economic trade-off'. "
                    "Output ONLY clean semantic HTML matching existing section headings."
                )},
                {"role": "user", "content": f"Expand this draft with comprehensive depth and context to exceed 1,500 words:\n\n{cleaned_body}"}
            ]
            expanded = self.ai.generate(expand_prompt, max_tokens=3800, temperature=0.6, timeout=50.0)
            if expanded:
                cand_body = self._sanitize_html(expanded)
                cand_words = len(clean_text(cand_body).split())
                if cand_words > word_count:
                    cleaned_body = cand_body
                    word_count = cand_words
                    log("✅", f"Article expanded to authoritative depth: {word_count} words")

        # ── Step 3: Extract Key Takeaways & SEO Metadata ───────────────────
        meta = self._generate_seo(topic, cleaned_body)
        takeaways = self._extract_takeaways(outline, cleaned_body)

        # ── Step 4: Assemble Native ReadContext Presentation ───────────────
        final_layout = self._render_readcontext_layout(
            topic=topic,
            article_body=cleaned_body,
            images=images,
            research=research,
            meta=meta,
            takeaways=takeaways,
            archetype=archetype
        )

        return {
            "title": meta.get("headline", topic['title']),
            "html": final_layout,
            "meta_description": meta.get("description", topic['title'])[:160],
            "tags": meta.get("tags", ['Technology', 'AI', 'Analysis']),
            "raw_text": cleaned_body,
            "word_count": word_count
        }

    def _sanitize_html(self, html_str):
        """Clean wrappers and fix mismatched tags like <h3> ... </h2>."""
        clean = strip_html_wrappers(html_str)
        # Fix mismatched <h3> ... </h2>
        clean = re.sub(r'<h3([^>]*)>(.*?)</h2>', r'<h3\1>\2</h3>', clean, flags=re.IGNORECASE | re.DOTALL)
        clean = re.sub(r'<h2([^>]*)>(.*?)</h3>', r'<h2\1>\2</h2>', clean, flags=re.IGNORECASE | re.DOTALL)
        # Remove empty headings or paragraphs
        clean = re.sub(r'<p>\s*</p>', '', clean)
        clean = re.sub(r'<h[23]>\s*</h[23]>', '', clean)
        return clean.strip()

    def _synthesize_research(self, research):
        lines = []

        # 1. Primary Scraped Facts
        if research.get("scraped_facts"):
            lines.append("PRIMARY SOURCE GROUND TRUTH (Directly Scraped):")
            for p in research["scraped_facts"][:5]:
                lines.append(f"  • {p}")

        # 2. Real Quotes
        if research.get("real_quotes"):
            lines.append("\nDOCUMENTED QUOTES & STATEMENTS:")
            for q in research["real_quotes"][:4]:
                lines.append(f"  • \"{q['quote']}\" ({q.get('source', 'Report')})")

        # 3. Reddit Community Debates
        if research.get("reddit_reactions"):
            lines.append("\nREDDIT COMMUNITY PERSPECTIVES & DEBATES:")
            for r in research["reddit_reactions"][:4]:
                lines.append(f"  • [{r.get('subreddit', 'r/tech')}] \"{r['title']}\" ({r.get('score', 0)} upvotes, {r.get('comments', 0)} comments) — {r.get('url')}")

        # 4. Hacker News Signals
        if research.get("hn_threads"):
            lines.append("\nHACKER NEWS TECHNICAL DISCUSSIONS:")
            for h in research["hn_threads"][:4]:
                lines.append(f"  • \"{h['title']}\" ({h.get('points')} pts, {h.get('comments')} comments) — {h.get('url')}")

        # 5. Cross-Web Coverage
        if research.get("cross_web_reports"):
            lines.append("\nCORROBORATING NEWS COVERAGE:")
            for w in research["cross_web_reports"][:3]:
                lines.append(f"  • {w.get('source', 'Wire')}: \"{w['title']}\" — {w.get('snippet', '')}")

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

    def _generate_seo(self, topic, body):
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
        return {
            "headline": topic['title'],
            "dek": topic.get('description', '')[:120],
            "description": (topic.get('description') or topic['title'])[:155],
            "tags": extract_keywords(topic['title'])[:5]
        }

    def _render_readcontext_layout(self, topic, article_body, images, research, meta, takeaways, archetype):
        """
        Creates a custom responsive newspaper layout tailored for readcontext.blogspot.com:
        Warm orange accents (#F36C21), Playfair Display styling, clean cards,
        proper paragraph indentation, pull quotes, and real source attributions.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%B %d, %Y")
        iso_date = now.isoformat()
        headline = meta.get("headline", topic['title'])
        meta_desc = meta.get("description", topic['title'])

        # Hero Image Frame
        hero_img_html = ""
        hero_url = ""
        if images:
            hero = images[0]
            hero_url = hero['url']
            hero_img_html = f'''
            <div style="margin:24px 0 28px 0; text-align:center;">
                <figure style="margin:0; padding:0;">
                    <img src="{hero['url']}" alt="{headline}"
                         style="width:100%; max-height:540px; object-fit:cover; border-radius:16px; box-shadow:0 12px 32px rgba(0,0,0,0.08); display:block;"
                         loading="eager" />
                    <figcaption style="display:flex; justify-content:space-between; align-items:center; font-size:12.5px; color:#777; margin-top:10px; padding:0 6px;">
                        <span>📸 {hero.get('caption', 'Editorial Documentary Visual')}</span>
                        <span style="font-style:italic;">Credit: {hero.get('source', 'Press Wire')}</span>
                    </figcaption>
                </figure>
            </div>
            '''

        # Secondary Image Frame
        secondary_img_html = ""
        if len(images) > 1:
            sec = images[1]
            secondary_img_html = f'''
            <div style="margin:34px 0; text-align:center;">
                <figure style="margin:0; padding:0;">
                    <img src="{sec['url']}" alt="Contextual Analysis Visual"
                         style="width:100%; max-height:420px; object-fit:cover; border-radius:14px; box-shadow:0 8px 24px rgba(0,0,0,0.06); display:block;"
                         loading="lazy" />
                    <figcaption style="font-size:12.5px; color:#777; margin-top:8px; text-align:center; font-style:italic;">
                        {sec.get('caption', 'Supporting technical documentation')} · <span>{sec.get('source', 'Archival Wire')}</span>
                    </figcaption>
                </figure>
            </div>
            '''

        # Executive Takeaways Box
        takeaways_items = "".join(f"<li style='margin-bottom:8px; padding-left:4px;'>{t}</li>" for t in takeaways)
        takeaways_html = f'''
        <div style="margin:24px 0 32px 0; padding:20px 24px; background:linear-gradient(135deg, rgba(243,108,33,0.05) 0%, rgba(243,108,33,0.01) 100%); border-left:4px solid #F36C21; border-radius:0 14px 14px 0; box-shadow:0 4px 16px rgba(0,0,0,0.02);">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
                <span style="font-size:18px;">⚡</span>
                <h3 style="margin:0; font-size:15px; font-weight:800; color:#222; text-transform:uppercase; letter-spacing:0.06em;">
                    Executive Key Takeaways
                </h3>
            </div>
            <ul style="margin:0; padding-left:20px; font-size:15px; line-height:1.65; color:#333;">
                {takeaways_items}
            </ul>
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
                    return "Reddit Community"
                if "ycombinator.com" in domain:
                    return "Hacker News"
                if "github.com" in domain:
                    return "GitHub Repository"
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
                    f'<li style="margin-bottom:12px; line-height:1.6;">'
                    f'<span style="display:inline-block; min-width:140px; font-weight:700; color:#333;">{brand}:</span> '
                    f'<a href="{topic["source_url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">Original Investigative Coverage</a>'
                    f'</li>'
                )

        # 2. Reddit Discussions (distinct brand, zero karma/points numbers displayed)
        for r in research.get("reddit_reactions", []):
            if "Reddit Community" not in seen_brands and r.get("url"):
                seen_brands.add("Reddit Community")
                citations.append(
                    f'<li style="margin-bottom:12px; line-height:1.6;">'
                    f'<span style="display:inline-block; min-width:140px; font-weight:700; color:#333;">Reddit:</span> '
                    f'<a href="{r["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{r["title"][:85]}</a>'
                    f'</li>'
                )
                break

        # 3. Hacker News Technical Discussion (distinct brand, zero points/karma displayed)
        for h in research.get("hn_threads", []):
            if "Hacker News" not in seen_brands and h.get("url"):
                seen_brands.add("Hacker News")
                citations.append(
                    f'<li style="margin-bottom:12px; line-height:1.6;">'
                    f'<span style="display:inline-block; min-width:140px; font-weight:700; color:#333;">Hacker News:</span> '
                    f'<a href="{h["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{h["title"][:85]}</a>'
                    f'</li>'
                )
                break

        # 4. Cross-Web Secondary Wire Reports (only if different brand)
        for w in research.get("cross_web_reports", []):
            if w.get("url"):
                w_brand = _get_brand(w['url'], w.get('source', 'Press Wire'))
                if w_brand not in seen_brands:
                    seen_brands.add(w_brand)
                    citations.append(
                        f'<li style="margin-bottom:12px; line-height:1.6;">'
                        f'<span style="display:inline-block; min-width:140px; font-weight:700; color:#333;">{w_brand}:</span> '
                        f'<a href="{w["url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:500; text-decoration:underline;">{w["title"][:85]}</a>'
                        f'</li>'
                    )
            if len(citations) >= 4:
                break

        citations_html = ""
        if citations:
            citations_html = f'''
            <div style="margin-top:42px; padding:24px; background:rgba(243,108,33,0.03); border-left:4px solid #F36C21; border-radius:0 16px 16px 0;">
                <h3 style="margin:0 0 14px 0; font-size:16px; font-weight:800; color:#222; text-transform:uppercase; letter-spacing:0.05em;">
                    🔗 Related Documentation & Research Across the Web
                </h3>
                <ul style="list-style:none; padding:0; margin:0; line-height:1.75; font-size:14.5px;">
                    {"".join(citations)}
                </ul>
            </div>
            '''

        logo_b64 = self._get_logo_base64()
        logo_html = ""
        if logo_b64:
            logo_html = f'''
            <div style="margin-top:48px; padding-top:24px; border-top:1px solid rgba(0,0,0,0.08); text-align:center;">
                <img src="data:image/png;base64,{logo_b64}" alt="ReadContext" style="max-height:42px; margin:0 auto 10px; display:block; opacity:0.9;" />
                <div style="font-size:12px; color:#999; letter-spacing:1px; text-transform:uppercase;">
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
                "name": "ReadContext Special Bureau",
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

        html = f'''
<!-- SEO Structured Data -->
<script type="application/ld+json">
{schema_json}
</script>

<style>
.readcontext-article {{
    line-height: 1.85;
    color: #2a2a2a;
    font-size: 17px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}}
.readcontext-article .article-content p {{
    margin: 0 0 1.35em 0 !important;
    text-indent: 2.4em !important; /* Clear tab space indentation on every paragraph */
    line-height: 1.88 !important;
    color: #2b2b2b;
}}
.readcontext-article .article-content h2 {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 23px;
    font-weight: 700;
    color: #1a1a1a;
    margin-top: 36px;
    margin-bottom: 14px;
    line-height: 1.35;
    border-bottom: 2px solid rgba(243, 108, 33, 0.2);
    padding-bottom: 6px;
}}
.readcontext-article .article-content h3 {{
    font-size: 18px;
    font-weight: 600;
    color: #2c3e50;
    margin-top: 26px;
    margin-bottom: 12px;
    padding-left: 14px;
    margin-left: 1.5em; /* Tab indented subsection */
    border-left: 3.5px solid #F36C21;
}}
.readcontext-article .article-content blockquote {{
    margin: 26px 0;
    padding: 16px 22px;
    background: #fdfaf6;
    border-left: 4px solid #F36C21;
    font-style: italic;
    font-size: 17px;
    color: #333;
    border-radius: 0 12px 12px 0;
}}
.readcontext-article .article-content blockquote cite {{
    display: block;
    font-size: 13px;
    font-style: normal;
    color: #777;
    margin-top: 8px;
    font-weight: 500;
}}
.readcontext-article .article-content ul,
.readcontext-article .article-content ol {{
    margin: 16px 0 20px 24px;
    padding: 0;
    line-height: 1.75;
}}
.readcontext-article .article-content li {{
    margin-bottom: 8px;
}}
</style>

<div class="readcontext-article">

    <!-- Editorial Kicker (Source name kept in backend only, never exposed at top) -->
    <div style="margin-bottom:12px;">
        <span style="display:inline-block; font-size:11.5px; font-weight:800; text-transform:uppercase; letter-spacing:1.5px; color:#F36C21; background:rgba(243,108,33,0.1); padding:4px 12px; border-radius:30px;">
            SPECIAL REPORT · {archetype['name'].upper()}
        </span>
    </div>

    <!-- Editorial Dek (Subtitle) -->
    <p style="font-size:1.22em; line-height:1.5; color:#555; font-style:italic; margin:0 0 18px 0; font-weight:500;">
        {meta.get('dek', topic.get('description', ''))}
    </p>

    <!-- Byline & Full Published Date & Time (Reading time and resonance scores removed) -->
    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; padding:12px 0; border-top:1px solid rgba(0,0,0,0.08); border-bottom:1px solid rgba(0,0,0,0.08); margin-bottom:24px; font-size:13px; color:#666;">
        <div>
            By <strong style="color:#222;">ReadContext Special Bureau</strong>
        </div>
        <div>
            📅 <span>Published on {now.strftime("%B %d, %Y · %I:%M %p UTC")}</span>
        </div>
    </div>

    <!-- Hero Documentary Photo -->
    {hero_img_html}

    <!-- Executive Takeaways -->
    {takeaways_html}

    <!-- Article Narrative Body -->
    <div class="article-content">
        {article_body}
    </div>

    <!-- Secondary Visual -->
    {secondary_img_html}

    <!-- Related Documentation & Research on the Internet (No Repeating Brands) -->
    {citations_html}

    <!-- Branded Signature -->
    {logo_html}

</div>
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

        labels = ["Technology", "AI", "Investigative", "ReadContext"] + article.get("tags", [])[:3]
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

    # Pick the top safe story by resonance & virality
    selected_topic = stories[0]
    log("🎯", f"Selected Top Compliant Story: '{selected_topic['title']}'")
    log("📌", f"Source: {selected_topic['source']} | Virality Score: {selected_topic.get('virality_score', 0)}")
    log("🔗", f"Reference URL: {selected_topic.get('source_url')}")

    # 4. Deep Research (Web scraping, Reddit discussions, HN Algolia, quotes)
    dossier = researcher.deep_research(selected_topic)

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
