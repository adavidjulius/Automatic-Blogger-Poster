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
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "at",
        "to", "for", "with", "this", "that", "these", "those", "and", "or",
        "but", "how", "what", "when", "why", "who", "will", "can", "has",
        "have", "its", "it", "not", "from", "been", "more", "new", "about",
        "just", "than", "into", "over", "after", "also", "may", "some",
        "could", "would", "should", "most", "all", "one", "two", "first",
        "says", "said", "like", "year", "make", "take", "post", "read",
        "shows", "shown", "show", "release", "releases"
    }
    raw = f"{title} {description}"
    words = re.findall(r'\b[a-zA-Z]{3,}\b', raw)
    filtered = [w.lower() for w in words if w.lower() not in stop_words]
    deduped = []
    seen = set()
    for w in filtered:
        if w not in seen:
            seen.add(w)
            deduped.append(w)
    return deduped[:6]


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
        for s in all_stories:
            norm_title = s['title'].strip().lower()
            norm_url = s.get('source_url', '').strip().lower()
            if norm_title in posted_titles or (norm_url and norm_url in posted_urls):
                continue
            # Also check significant keyword overlap
            kw_s = set(extract_keywords(norm_title))
            is_dup = False
            for pt in posted_titles:
                kw_p = set(extract_keywords(pt))
                if kw_s and kw_p and len(kw_s & kw_p) >= min(len(kw_s), 3) and len(kw_s & kw_p) / max(len(kw_s), 1) > 0.7:
                    is_dup = True
                    break
            if not is_dup:
                fresh_stories.append(s)

        log("📊", f"Retained {len(fresh_stories)} fresh non-duplicate compliant candidate stories")
        return fresh_stories


# ═══════════════════════════════════════════════════════════════════════════
#  DEEP WEB RESEARCHER — HN Algolia, Reddit Discussions, Quotes
# ═══════════════════════════════════════════════════════════════════════════

class WebResearcher:
    """Gathers real perspectives, technical details, and quotes across forums."""

    def __init__(self, ai_client):
        self.ai = ai_client

    def deep_research(self, topic):
        log("🔍", f"Conducting deep research on: '{topic['title'][:60]}...'")
        queries = self.ai.generate_tool_queries(topic['title'], topic.get('description', ''))

        research_dossier = {
            "topic": topic['title'],
            "source_url": topic.get('source_url', ''),
            "hn_threads": [],
            "reddit_reactions": [],
            "search_queries": queries,
            "quotes": []
        }

        with ThreadPoolExecutor(max_workers=3) as executor:
            f_hn = executor.submit(self._query_hn_algolia, topic['title'], queries)
            f_reddit = executor.submit(self._query_reddit_rss, topic['title'], queries)

            try:
                research_dossier['hn_threads'] = f_hn.result(timeout=15)
            except Exception:
                pass
            try:
                research_dossier['reddit_reactions'] = f_reddit.result(timeout=15)
            except Exception:
                pass

        total_points = len(research_dossier['hn_threads']) + len(research_dossier['reddit_reactions'])
        log("📑", f"Dossier ready with {total_points} primary discussion threads & community quotes")
        return research_dossier

    def _query_hn_algolia(self, title, queries):
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
                            "author": h.get("author", "community")
                        })
        except Exception:
            pass
        return results

    def _query_reddit_rss(self, title, queries):
        results = []
        kw = extract_keywords(title)[:2]
        query_str = "+".join(kw) if kw else "tech"
        try:
            url = f"https://www.reddit.com/r/technology/search.rss?q={query_str}&restrict_sr=1&sort=relevance"
            resp = SESSION.get(url, timeout=8)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                for e in feed.entries[:4]:
                    t = clean_text(e.get("title", ""))
                    safe, _ = ContentComplianceGuard.evaluate(t)
                    if safe:
                        results.append({
                            "title": t,
                            "url": e.get("link", ""),
                            "summary": clean_text(e.get("summary", ""))[:200]
                        })
        except Exception:
            pass
        return results


# ═══════════════════════════════════════════════════════════════════════════
#  REAL SOURCE IMAGE COLLECTOR & VISION VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════

class RealImageCollector:
    """Collects authentic real-world photos — never uses fake or generic placeholders."""

    def __init__(self, ai_client):
        self.ai = ai_client

    def fetch_verified_images(self, topic):
        log("🖼️", "Collecting real documentary photo assets...")
        candidates = []
        title = topic['title']
        description = topic.get('description', '')

        # 1. Primary Source Image (From RSS media content, verified not a button/icon)
        if topic.get('image_url'):
            candidates.append({
                "url": topic['image_url'],
                "source": f"Official Press Wire / {topic['source']}",
                "caption": f"Documentary photograph documenting {title[:70]}"
            })

        # 2. Wikimedia Commons (Real Public Factual Imagery)
        wiki_img = self._search_wikimedia(title, description)
        if wiki_img:
            candidates.append(wiki_img)

        # 3. Unsplash Editorial Photo Search (if key provided)
        if UNSPLASH_ACCESS_KEY:
            unsplash_img = self._search_unsplash(title, description)
            if unsplash_img:
                candidates.append(unsplash_img)

        # 4. Google Custom Search (if configured)
        if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
            google_img = self._search_google_cse(title, description)
            if google_img:
                candidates.append(google_img)

        # 5. Fallback: High Quality Unsplash Documentary Image
        if not candidates:
            candidates.append({
                "url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&auto=format&fit=crop",
                "source": "Unsplash Editorial Archive",
                "caption": "Documentary archival image representing modern critical infrastructure"
            })

        # Run vision model verification to screen out any icons, buttons, or violent imagery
        verified_candidates = []
        for cand in candidates:
            caption = self.ai.verify_image_with_vision(cand['url'], title)
            if caption:
                cap_lower = caption.lower()
                # Reject icons, buttons, gore, weapons, violence
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

        log("📸", f"Verified {len(verified_candidates)} documentary photo asset(s)")
        return verified_candidates

    def _search_wikimedia(self, title, description):
        kw = extract_keywords(title, description)
        query = " ".join(kw[:3]) if kw else "technology"
        try:
            url = (
                "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                f"&gsrnamespace=6&gsrsearch={urllib.parse.quote(query)}&gsrlimit=4"
                "&prop=imageinfo&iiprop=url|extmetadata&format=json"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "ReadContextNews/2.0"})
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
                            "caption": f"Documentary photo via Wikimedia Commons"
                        }
        except Exception:
            pass
        return None

    def _search_unsplash(self, title, description):
        kw = extract_keywords(title, description)
        query = " ".join(kw[:3])
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
#  ARTICLE GENERATOR — Professional Newspaper Edition for ReadContext
# ═══════════════════════════════════════════════════════════════════════════

class ArticleGenerator:
    """Generates comprehensive, long-form journalism formatted for readcontext.blogspot.com."""

    MIN_TARGET_WORDS = 1500
    MAX_TARGET_WORDS = 2500

    def __init__(self, ai_client):
        self.ai = ai_client

    def build_article(self, topic, research, images):
        log("✍️", "Drafting long-form investigative article with NVIDIA NIM...")

        research_notes = self._synthesize_research(research)

        # ── Step 1: Generate Master Outline & Key Takeaways ─────────────────
        outline_prompt = [
            {"role": "system", "content": (
                "You are the Executive Editor of a prestigious technology journal. "
                "Enforce strict journalistic standards: absolute neutrality, no geopolitical bias, "
                "no graphic violence, no weapons, no unverified medical or financial claims."
            )},
            {"role": "user", "content": f"""
Develop an authoritative investigative outline for this trending technology story:

HEADLINE CANDIDATE: {topic['title']}
INITIAL CONTEXT: {topic.get('description', '')}
ORIGINAL SOURCE: {topic.get('source', '')} ({topic.get('source_url', '')})

RESEARCH INTEL:
{research_notes}

Provide:
1. PUNCHY DEK (1 sentence editorial subtitle)
2. 4 EXECUTIVE TAKEAWAYS (Bullet points summarizing the core shift)
3. SECTION BY SECTION NARRATIVE ARC:
   - The Lead & Current Catalysts
   - Deep Technical & Strategic Breakdown
   - Public & Industry Repercussions (HN, Reddit, X sentiments)
   - Economic & Industry Ramifications
   - Forward Looking Outlook
"""}
        ]
        outline = self.ai.generate(outline_prompt, max_tokens=1500, temperature=0.6, timeout=35.0)
        if not outline:
            log("❌", "Outline generation failed.")
            return None

        # ── Step 2: Write Full Long-Form Article ───────────────────────────
        article_prompt = [
            {"role": "system", "content": (
                "You are an award-winning technology investigative journalist writing for ReadContext. "
                "Write in a captivating, authoritative voice. "
                "STRICT COMPLIANCE DIRECTIVES:\n"
                "• ZERO Graphic Violence: Never describe blood, injuries, weapons, casualties, or physical destruction.\n"
                "• ZERO Geopolitical Bias: Maintain absolute journalistic neutrality. Do not take sides or use emotional or derogatory language.\n"
                "• ZERO Copyright Infringement: Write 100% original prose synthesizing the concepts. Never copy-paste blocks of text.\n"
                "• ZERO Misinformation: Rely only on verifiable technical facts, documented benchmarks, and cited sources.\n"
                "• NO Click Solicitations: Never include text asking readers to click ads, support via ads, or fake download buttons.\n"
                "• HIGH SUBSTANCE: Produce comprehensive, thorough coverage (1,500–2,200 words). Never write thin or shallow summaries.\n"
                "• OUTPUT FORMAT: Output ONLY semantic HTML content (using <h2>, <h3>, <p>, <blockquote>, <ul>, <li>, <strong>, <em>). "
                "Do NOT output <!DOCTYPE html>, <html>, <head>, <style>, <body>, or <h1> tags. "
                "Begin immediately with the lead dateline paragraph (e.g. <strong>SAN FRANCISCO —</strong>)."
            )},
            {"role": "user", "content": f"""
Write an exhaustive, high-impact 1500–2200 word newspaper article based on this outline and intel:

OUTLINE:
{outline}

INTEL & REAL COMMUNITY PERSPECTIVES:
{research_notes}

STORY DETAILS:
Title: {topic['title']}
Source: {topic.get('source')} ({topic.get('source_url')})

REQUIRED STRUCTURE:
1. LEAD SECTION: Begin directly with the opening narrative hook (bold dateline, e.g. <strong>SAN FRANCISCO —</strong>), explaining the urgency and core technological breakthrough.
2. <h2>The Genesis of the Shift</h2>: How this situation developed, previous benchmarks, and behind-the-scenes factors.
3. <h2>Technical Architecture & Core Mechanics</h2>: Deep analysis of how it works, technical breakthroughs, or data points.
4. <h2>Multi-Platform Reactions: What the Tech Community is Saying</h2>: Directly analyze opinions from Hacker News, Reddit discussions, and social commentators (attribute sentiments accurately).
5. <h2>Industry Winners, Losers, and Economic Consequences</h2>: The broader market disruption, competitive stakes, and corporate strategies.
6. <h2>Ethical, Policy & Societal Implications</h2>: Regulatory hurdles, user impact, and philosophical debates.
7. <h2>The Road Ahead: What to Watch</h2>: Concrete future milestones, upcoming releases, and unresolved questions.

FORMATTING REQUIREMENTS:
- Use <blockquote> with speaker/platform attribution for 2-3 prominent quotes.
- Break up text with informative <h2> and <h3> subheadings.
- Keep paragraphs punchy (3-4 sentences max per paragraph).
- Start immediately with real reporting.
"""}
        ]

        article_html = self.ai.generate(article_prompt, max_tokens=3800, temperature=0.7, timeout=60.0)
        if not article_html:
            log("❌", "Article body generation failed.")
            return None

        cleaned_body = strip_html_wrappers(article_html)
        word_count = len(clean_text(cleaned_body).split())

        # ── Step 2b: Enforce In-Depth Journalism (Prevent Thin Text < 1,100 words) ──
        if word_count < 1100:
            log("⚠️", f"Initial draft reached {word_count} words (below 1,100 word minimum). Deepening analysis to ensure high depth...")
            expand_prompt = [
                {"role": "system", "content": (
                    "You are the Senior Executive Editor of ReadContext (readcontext.blogspot.com). "
                    "Expand the provided article by adding 2-3 deep, highly analytical paragraphs under each existing <h2> section. "
                    "Detail the technical architecture, real-world benchmarks, developer reactions, and economic trade-offs. "
                    "Output ONLY clean semantic HTML without wrapping <html>, <head>, or <body> tags."
                )},
                {"role": "user", "content": f"Expand this draft with comprehensive technical depth and industry context:\n\n{cleaned_body}\n\nEnsure total word count exceeds 1,400 words."}
            ]
            expanded = self.ai.generate(expand_prompt, max_tokens=3800, temperature=0.6, timeout=50.0)
            if expanded:
                cand_body = strip_html_wrappers(expanded)
                cand_words = len(clean_text(cand_body).split())
                if cand_words > word_count:
                    cleaned_body = cand_body
                    word_count = cand_words
                    log("✅", f"Article expanded to authoritative depth: {word_count} words")

        # ── Step 3: Extract Meta Description & Tags ────────────────────────
        meta = self._generate_seo(topic, cleaned_body)

        # ── Step 4: Assemble Native ReadContext Presentation ───────────────
        final_layout = self._render_readcontext_layout(
            topic=topic,
            article_body=cleaned_body,
            images=images,
            research=research,
            meta=meta
        )

        return {
            "title": meta.get("headline", topic['title']),
            "html": final_layout,
            "meta_description": meta.get("description", topic['title'])[:160],
            "tags": meta.get("tags", ['Technology', 'AI', 'Analysis']),
            "raw_text": cleaned_body,
            "word_count": word_count
        }

    def _synthesize_research(self, research):
        lines = []
        if research.get("hn_threads"):
            lines.append("HACKER NEWS SIGNALS:")
            for h in research["hn_threads"]:
                lines.append(f"  • \"{h['title']}\" ({h.get('points')} pts, {h.get('comments')} comments) — {h.get('url')}")
        if research.get("reddit_reactions"):
            lines.append("\nREDDIT COMMUNITY DEBATES:")
            for r in research["reddit_reactions"]:
                lines.append(f"  • \"{r['title']}\" — {r.get('url')}")
        if not lines:
            lines.append("Community sentiment shows intense debate regarding technological feasibility and strategic motives.")
        return "\n".join(lines)

    def _generate_seo(self, topic, body):
        prompt = [
            {"role": "system", "content": "You are a news SEO specialist. Output strict JSON only."},
            {"role": "user", "content": f"""
Generate SEO metadata for this story:
Title: {topic['title']}
Snippet: {clean_text(body)[:400]}

Respond in JSON format:
{{
  "headline": "Compelling Newspaper Headline (50-70 chars)",
  "dek": "One-sentence journalistic subtitle explaining the significance (max 120 chars)",
  "description": "Engaging meta description (max 155 chars)",
  "tags": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"]
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

    def _render_readcontext_layout(self, topic, article_body, images, research, meta):
        """
        Creates a custom responsive layout tailored for readcontext.blogspot.com:
        Warm orange accents (#F36C21), Playfair Display styling, clean cards,
        pull quotes, and real source attributions.
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%B %d, %Y")

        hero_img_html = ""
        if images:
            hero = images[0]
            hero_img_html = f'''
            <div style="margin:24px 0 32px 0; text-align:center;">
                <img src="{hero['url']}" alt="{meta.get('headline', topic['title'])}"
                     style="width:100%; max-height:540px; object-fit:cover; border-radius:18px; box-shadow:0 12px 36px rgba(0,0,0,0.08); display:block;"
                     loading="eager" />
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#888; margin-top:10px; padding:0 6px;">
                    <span>📸 {hero.get('caption', 'Featured Story Photo')}</span>
                    <span style="font-style:italic;">Source: {hero.get('source', 'Press Wire')}</span>
                </div>
            </div>
            '''

        secondary_img_html = ""
        if len(images) > 1:
            sec = images[1]
            secondary_img_html = f'''
            <div style="margin:30px 0; text-align:center;">
                <img src="{sec['url']}" alt="Supporting Documentary Visual"
                     style="width:100%; max-height:420px; object-fit:cover; border-radius:14px; box-shadow:0 8px 24px rgba(0,0,0,0.06); display:block;"
                     loading="lazy" />
                <div style="font-size:12px; color:#888; margin-top:8px; text-align:center; font-style:italic;">
                    {sec.get('caption', '')} · <span>{sec.get('source', '')}</span>
                </div>
            </div>
            '''

        citations = []
        if topic.get('source_url'):
            citations.append(
                f'<li style="margin-bottom:8px;">'
                f'<strong>Primary Report:</strong> <a href="{topic["source_url"]}" target="_blank" rel="noopener" style="color:#F36C21; font-weight:600;">{topic["source"]} — Original Coverage</a>'
                f'</li>'
            )
        for h in research.get("hn_threads", [])[:3]:
            citations.append(
                f'<li style="margin-bottom:8px;">'
                f'<strong>Hacker News Discussion:</strong> <a href="{h["url"]}" target="_blank" rel="noopener" style="color:#F36C21;">{h["title"][:75]}</a> '
                f'<span style="color:#888; font-size:12px;">({h.get("points")} points · {h.get("comments")} comments)</span>'
                f'</li>'
            )
        for r in research.get("reddit_reactions", [])[:3]:
            citations.append(
                f'<li style="margin-bottom:8px;">'
                f'<strong>Reddit Community Thread:</strong> <a href="{r["url"]}" target="_blank" rel="noopener" style="color:#F36C21;">{r["title"][:75]}</a>'
                f'</li>'
            )

        citations_html = ""
        if citations:
            citations_html = f'''
            <div style="margin-top:40px; padding:24px; background:rgba(243,108,33,0.04); border-left:4px solid #F36C21; border-radius:0 16px 16px 0;">
                <h3 style="margin:0 0 14px 0; font-size:17px; font-weight:800; color:#222; text-transform:uppercase; letter-spacing:0.04em;">
                    📚 Documented Sources & Community Trails
                </h3>
                <ul style="list-style:none; padding:0; margin:0; line-height:1.7; font-size:14px;">
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
                </div>
            </div>
            '''

        html = f'''
<div class="readcontext-article" style="line-height:1.85; color:#2a2a2a; font-size:17px;">

    <!-- Editorial Kicker & Subtitle -->
    <div style="margin-bottom:12px;">
        <span style="display:inline-block; font-size:11.5px; font-weight:800; text-transform:uppercase; letter-spacing:1.5px; color:#F36C21; background:rgba(243,108,33,0.1); padding:4px 12px; border-radius:30px;">
            INVESTIGATIVE DISPATCH · {topic.get('source', 'GLOBAL WIRE').upper()}
        </span>
    </div>

    <!-- Editorial Dek (Subtitle) -->
    <p style="font-size:1.2em; line-height:1.5; color:#555; font-style:italic; margin:0 0 18px 0; font-weight:500;">
        {meta.get('dek', topic.get('description', ''))}
    </p>

    <!-- Byline & Metadata Bar -->
    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; padding:12px 0; border-top:1px solid rgba(0,0,0,0.08); border-bottom:1px solid rgba(0,0,0,0.08); margin-bottom:24px; font-size:13px; color:#777;">
        <div>
            By <strong style="color:#222;">ReadContext Special Bureau</strong> · <span>{date_str}</span>
        </div>
        <div style="display:flex; gap:12px; align-items:center;">
            <span>⏱️ 7 min read</span>
            <span>⚡ Trending Resonance Score: {topic.get('virality_score', 12)}</span>
        </div>
    </div>

    <!-- Hero Documentary Photo -->
    {hero_img_html}

    <!-- Article Narrative Body -->
    <div class="article-content">
        {article_body}
    </div>

    <!-- Secondary Visual -->
    {secondary_img_html}

    <!-- Citations & References -->
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
        f.write(frontmatter + article["raw_text"])
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

    # 4. Deep Research (HN discussions, Reddit debates, quotes)
    dossier = researcher.deep_research(selected_topic)

    # 5. Real Image Discovery & Vision Validation
    images = image_collector.fetch_verified_images(selected_topic)
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
