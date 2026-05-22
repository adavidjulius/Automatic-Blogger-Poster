#!/usr/bin/env python3
"""
Blogger Auto-Poster – Optimized for CPU (1500-2000 words)
- Uses Ollama with tinyllama for speed, falls back to phi.
- Increased timeouts, warm‑up prompt, and lower word count.
- FIXED: Proper keyword-matched image search with 4-level fallback.
"""

import os, sys, requests, feedparser, random, subprocess, traceback, urllib.parse, base64, json, time, re
from datetime import datetime
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

try:
    from airllm import AutoModel
    AIRLLM_AVAILABLE = True
except ImportError:
    AIRLLM_AVAILABLE = False

# ==================== CONFIG ====================
BLOGGER_BLOG_ID        = os.getenv("BLOGGER_BLOG_ID")
GOOGLE_CLIENT_ID       = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET   = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN   = os.getenv("GOOGLE_REFRESH_TOKEN")
GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON")

# ── NEW: Image API keys (add these as secrets) ──────────────────────────
UNSPLASH_ACCESS_KEY    = os.getenv("UNSPLASH_ACCESS_KEY", "")   # free at unsplash.com/developers
GOOGLE_CSE_API_KEY     = os.getenv("GOOGLE_CSE_API_KEY", "")    # Google Custom Search API key
GOOGLE_CSE_ID          = os.getenv("GOOGLE_CSE_ID", "")         # Programmable Search Engine ID

OLLAMA_PRIMARY   = "tinyllama"
OLLAMA_SECONDARY = "phi"
OLLAMA_TERTIARY  = "llama3:8b"
TIMEOUT_SECONDS  = 900

LOGO_PATH = Path("logo.png")
BLOG_URL  = "https://readcontext.blogspot.com"

SITEMAP_CANDIDATES = [
    f"{BLOG_URL}/sitemap.xml",
    f"{BLOG_URL}/atom.xml?redirect=false&start-index=1&max-results=500",
    f"{BLOG_URL}/feeds/posts/default",
]
SITEMAP_URL = None

CACHE_DIR = Path(".blog-cache")
POSTS_DIR = Path("_posts")
CACHE_DIR.mkdir(exist_ok=True)
POSTS_DIR.mkdir(exist_ok=True)

POSTS_LOG = CACHE_DIR / "posts_log.json"
if POSTS_LOG.exists():
    with open(POSTS_LOG, 'r') as f:
        posts_log = json.load(f)
else:
    posts_log = []

# ==================== HELPERS ====================
def log_error(step, error, details=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n❌ ERROR at {timestamp}")
    print(f"   Step: {step}")
    print(f"   Error: {error}")
    if details:
        print(f"   Details: {details}")
    print(f"   Traceback: {traceback.format_exc()}")

def test_sitemap():
    global SITEMAP_URL
    for url in SITEMAP_CANDIDATES:
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            if r.status_code == 200:
                SITEMAP_URL = url
                print(f"✅ Using sitemap: {url}")
                return
        except:
            continue
    SITEMAP_URL = SITEMAP_CANDIDATES[0]
    print(f"⚠️ No working sitemap found, using default: {SITEMAP_URL}")

def extract_keywords(title, description=""):
    """Extract best 3-5 keywords from title for image search."""
    stop_words = {"the","a","an","is","are","was","were","of","in","on","at","to",
                  "for","with","this","that","these","those","and","or","but","how",
                  "what","when","why","who","will","can","has","have","its","it"}
    text = f"{title} {description}"
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
    filtered = [w.lower() for w in words if w.lower() not in stop_words]
    # Deduplicate while preserving order
    seen, keywords = set(), []
    for w in filtered:
        if w not in seen:
            seen.add(w)
            keywords.append(w)
    return keywords[:5]

# ==================== IMAGE FUNCTIONS (FIXED) ====================

def get_rss_image(entry):
    """Level 0: Try RSS entry's own image first (most relevant)."""
    if not entry:
        return None
    if hasattr(entry, 'media_content') and entry.media_content:
        for m in entry.media_content:
            if 'url' in m:
                return m['url']
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for e in entry.enclosures:
            if e.get('type', '').startswith('image/'):
                return e.get('href') or e.get('url')
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get('rel') == 'enclosure' and link.get('type','').startswith('image/'):
                return link.get('href')
    return None

def get_unsplash_search_image(title, description=""):
    """
    Level 1: Unsplash /search/photos API — returns topic-matched photos.
    Requires UNSPLASH_ACCESS_KEY env var (free: 50 req/hr).
    """
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        keywords = extract_keywords(title, description)
        query    = " ".join(keywords[:3])
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query":       query,
                "per_page":    5,
                "orientation": "landscape",
                "order_by":    "relevant"
            },
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                photo = random.choice(results[:3])  # pick from top 3 relevant
                url   = photo["urls"]["regular"]     # 1080px wide
                print(f"🖼️ Unsplash matched image: '{query}' → {url[:60]}...")
                return url
    except Exception as e:
        print(f"⚠️ Unsplash search error: {e}")
    return None

def get_google_cse_image(title, description=""):
    """
    Level 2: Google Custom Search API image search — very accurate matching.
    Requires GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID env vars (free: 100 req/day).
    """
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        return None
    try:
        keywords = extract_keywords(title, description)
        query    = " ".join(keywords[:4])
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key":        GOOGLE_CSE_API_KEY,
                "cx":         GOOGLE_CSE_ID,
                "q":          query,
                "searchType": "image",
                "imgSize":    "LARGE",
                "imgType":    "photo",
                "num":        5,
                "safe":       "active"
            },
            timeout=10
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                item = items[0]
                url  = item["link"]
                print(f"🖼️ Google CSE matched image: '{query}' → {url[:60]}...")
                return url
    except Exception as e:
        print(f"⚠️ Google CSE image error: {e}")
    return None

def get_unsplash_source_image(title, description=""):
    """
    Level 3: Unsplash source URL (no key needed) — better than random
    because we inject topic keywords into the URL path.
    NOT fully reliable for exact matches but much better than pure random.
    """
    try:
        keywords = extract_keywords(title, description)
        query    = ",".join(keywords[:3])
        url      = f"https://source.unsplash.com/featured/1200x600/?{urllib.parse.quote(query)}"
        resp     = requests.head(url, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            final_url = resp.url
            print(f"🖼️ Unsplash source image (keywords: {query}): {final_url[:60]}...")
            return final_url
    except Exception as e:
        print(f"⚠️ Unsplash source error: {e}")
    return None

def get_picsum_fallback():
    """Level 4: Last resort — random placeholder."""
    url = f"https://picsum.photos/1200/600?random={random.randint(1, 100000)}"
    print("🖼️ Using Picsum placeholder (last resort)")
    return url

def get_image_url(entry, title, description=""):
    """
    4-level fallback chain — always returns a URL.
    Order: RSS image → Unsplash Search API → Google CSE → Unsplash Source → Picsum
    """
    # Level 0: RSS entry image (most relevant — it's the article's own image)
    url = get_rss_image(entry)
    if url:
        print(f"🖼️ Using RSS article image (most relevant)")
        return url

    # Level 1: Unsplash Search API (keyword-matched, free)
    url = get_unsplash_search_image(title, description)
    if url:
        return url

    # Level 2: Google Custom Search Images (keyword-matched, very accurate)
    url = get_google_cse_image(title, description)
    if url:
        return url

    # Level 3: Unsplash Source with keywords injected (no key, decent match)
    url = get_unsplash_source_image(title, description)
    if url:
        return url

    # Level 4: Picsum absolute fallback
    return get_picsum_fallback()

# ==================== HTML BUILDERS ====================
def create_image_html(img_url, title):
    if not img_url:
        return f'''
        <div style="margin-bottom:30px; text-align:center; background:linear-gradient(135deg,#667eea,#764ba2); padding:50px; border-radius:12px; color:white;">
            <span style="font-size:48px;">📰</span>
            <h2 style="color:white;">{title}</h2>
            <p>Today&#39;s featured story</p>
        </div>
        '''
    return f'''
    <div style="margin-bottom:30px; text-align:center;">
        <img src="{img_url}" alt="{title}"
             style="width:100%; max-width:900px; height:auto; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.15);">
        <p style="color:#777; font-size:0.8em;">📸 Image source</p>
    </div>
    '''

def get_logo_base64():
    if not LOGO_PATH.exists():
        return None
    try:
        with open(LOGO_PATH, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except:
        return None

def create_logo_html():
    b64 = get_logo_base64()
    if not b64:
        return ''
    return f'''
    <div style="margin-top:40px; text-align:center; padding:20px; border-top:1px solid #eaeaea;">
        <img src="data:image/png;base64,{b64}" alt="Logo" style="max-width:200px; margin:0 auto; display:block;">
        <p style="color:#777; margin-top:10px;">© {datetime.now().year} ReadContext</p>
    </div>
    '''

def get_related_posts_html(current_title, max_links=3):
    if not posts_log:
        return ""
    candidates = [p for p in posts_log if p['title'] != current_title]
    if not candidates:
        return ""
    selected = random.sample(candidates, min(max_links, len(candidates)))
    html = '<h2>📚 Related Posts</h2><ul style="list-style:none; padding:0;">'
    for p in selected:
        html += f'<li style="margin-bottom:10px;"><a href="{p["url"]}" style="text-decoration:none; color:#F36C21;">{p["title"]}</a></li>'
    html += '</ul>'
    return html

# ==================== GOOGLE PING & SEARCH CONSOLE ====================
def ping_google():
    global SITEMAP_URL
    if not SITEMAP_URL:
        test_sitemap()
    try:
        ping_url = f"https://www.google.com/ping?sitemap={SITEMAP_URL}"
        r = requests.get(ping_url, timeout=10)
        if r.status_code == 200:
            print("✅ Google pinged successfully")
        else:
            print(f"⚠️ Google ping returned {r.status_code}")
    except Exception as e:
        log_error("Google Ping", str(e))

def submit_to_search_console(post_url):
    if not GSC_SERVICE_ACCOUNT_JSON:
        print("⚠️ GSC_SERVICE_ACCOUNT_JSON not set – skipping Search Console submission.")
        return False
    try:
        json_str = GSC_SERVICE_ACCOUNT_JSON.strip()
        if json_str.startswith('"') and json_str.endswith('"'):
            json_str = json_str[1:-1].replace('\\"', '"')
        service_account_info = json.loads(json_str)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/indexing"]
        )
        if not credentials.valid:
            credentials.refresh(Request())
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type":  "application/json"
        }
        data = {"url": post_url, "type": "URL_UPDATED"}
        resp = requests.post(
            "https://indexing.googleapis.com/v3/urlNotifications:publish",
            headers=headers, json=data, timeout=10
        )
        if resp.status_code == 200:
            print("✅ Submitted to Google Search Console")
            return True
        else:
            print(f"⚠️ Search Console API error: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        log_error("Search Console API", str(e))
        return False

# ==================== BLOGGER AUTH ====================
def get_blogger_service():
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        print("❌ Missing Google Blogger credentials.")
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
        creds.refresh(Request())
        service   = build('blogger', 'v3', credentials=creds)
        blog_info = service.blogs().get(blogId=BLOGGER_BLOG_ID).execute()
        print(f"✅ Blog verified: {blog_info.get('name')}")
        return service
    except Exception as e:
        log_error("Blogger Auth", str(e))
        return None

def post_to_blogger(title, content, meta_description, img_url, labels):
    service = get_blogger_service()
    if not service:
        return False, "Auth failed"

    image_html   = create_image_html(img_url, title)
    related_html = get_related_posts_html(title)
    logo_html    = create_logo_html()
    full_content = image_html + content + related_html + logo_html

    post_body = {
        "kind":            "blogger#post",
        "title":           title,
        "content":         f"""
        <div style="font-family:Georgia,serif; line-height:1.8; max-width:900px; margin:0 auto;">
            {full_content}
            <hr>
            <p style="color:#777; text-align:center;">Published on {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}</p>
        </div>
        """,
        "labels":          labels,
        "metaDescription": meta_description[:160] if meta_description else None
    }

    try:
        res      = service.posts().insert(blogId=BLOGGER_BLOG_ID, body=post_body).execute()
        post_url = res.get('url')
        print(f"✅ Post published: {post_url}")
        posts_log.append({"title": title, "url": post_url, "date": datetime.now().isoformat()})
        with open(POSTS_LOG, 'w') as f:
            json.dump(posts_log[-100:], f, indent=2)
        return True, post_url
    except Exception as e:
        log_error("Blogger API", str(e))
        return False, str(e)

# ==================== TOPICS ====================
def get_trending_topics():
    topics  = []
    sources = [
        ('https://news.ycombinator.com/rss',    'Hacker News', 3),
        ('http://feeds.bbci.co.uk/news/rss.xml','BBC',         2),
        ('https://techcrunch.com/feed/',         'TechCrunch',  2),
    ]
    for url, name, limit in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                if entry.title and '[Removed]' not in entry.title:
                    topics.append({
                        'title':       entry.title,
                        'description': entry.get('summary', '')[:500],
                        'source':      name,
                        'entry':       entry
                    })
        except:
            pass
    if not topics:
        topics = [{'title': 'The Future of AI', 'description': 'AI transforming lives', 'source': 'Tech', 'entry': None}]
    random.shuffle(topics)
    return topics

# ==================== GENERATION ====================
def warm_up_model(model):
    try:
        requests.post('http://localhost:11434/api/generate',
                      json={"model": model, "prompt": "Hello", "stream": False},
                      timeout=30)
    except:
        pass

def generate_with_ollama(prompt, model, timeout_sec=TIMEOUT_SECONDS):
    try:
        resp = requests.post('http://localhost:11434/api/generate',
                              json={
                                  "model":   model,
                                  "prompt":  prompt,
                                  "stream":  False,
                                  "options": {"temperature": 0.7, "num_predict": 2048}
                              },
                              timeout=timeout_sec)
        if resp.status_code == 200:
            content = resp.json().get('response', '').strip()
            if content:
                return content
    except Exception as e:
        print(f"⚠️ {model} API error: {e}")
    try:
        result = subprocess.run(['/usr/local/bin/ollama', 'run', model, prompt],
                                capture_output=True, text=True, timeout=timeout_sec)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ {model} CLI error: {e}")
    return None

def generate_blog_post(topic):
    prompt = f"""You are a journalist. Write a detailed, well‑structured blog post.

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

STRUCTURE:
- <h1>{topic['title']}</h1>
- <h2>Synopsis</h2> – one paragraph summary.
- <h2>Introduction</h2>
- <h2>Analysis</h2> – 2-3 paragraphs.
- <h2>Implications</h2>
- <h2>Conclusion</h2>

Length: 1500-2000 words. Use <h2> headings, <p> paragraphs. No meta‑comments.

Write the post now:
"""
    warm_up_model(OLLAMA_PRIMARY)

    content = generate_with_ollama(prompt, OLLAMA_PRIMARY)
    if content:
        return content, f"Generated by {OLLAMA_PRIMARY}"

    print(f"⚠️ {OLLAMA_PRIMARY} failed, falling back to {OLLAMA_SECONDARY}.")
    content = generate_with_ollama(prompt, OLLAMA_SECONDARY)
    if content:
        return content, f"Generated by {OLLAMA_SECONDARY}"

    print(f"⚠️ {OLLAMA_SECONDARY} failed, falling back to {OLLAMA_TERTIARY}.")
    content = generate_with_ollama(prompt, OLLAMA_TERTIARY)
    if content:
        return content, f"Generated by {OLLAMA_TERTIARY}"

    return None, None

def save_local_post(title, content, summary):
    slug  = title.lower().replace(' ', '-')[:50]
    slug  = ''.join(c for c in slug if c.isalnum() or c == '-')
    fname = POSTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
    with open(fname, 'w') as f:
        f.write(f"# {title}\n\n## Summary\n{summary}\n\n{content}")
    return fname

# ==================== MAIN ====================
def main():
    test_sitemap()
    print("="*70)
    print("🚀 AI BLOGGER – CPU Optimized (1500‑2000 words)")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # ── Image API status report ──────────────────────────────────────────
    print("\n🖼️  Image API status:")
    print(f"   Unsplash Search API : {'✅ configured' if UNSPLASH_ACCESS_KEY else '⚠️  not set (add UNSPLASH_ACCESS_KEY secret)'}")
    print(f"   Google CSE Images   : {'✅ configured' if (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID) else '⚠️  not set (add GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID secrets)'}")
    print(f"   Unsplash Source     : ✅ always available (keyword-based, no key)")
    print(f"   Picsum fallback     : ✅ always available (last resort)")

    missing = [k for k, v in [
        ('BLOGGER_BLOG_ID',      BLOGGER_BLOG_ID),
        ('GOOGLE_CLIENT_ID',     GOOGLE_CLIENT_ID),
        ('GOOGLE_CLIENT_SECRET', GOOGLE_CLIENT_SECRET),
        ('GOOGLE_REFRESH_TOKEN', GOOGLE_REFRESH_TOKEN)
    ] if not v]
    if missing:
        print(f"\n❌ Missing Blogger secrets: {', '.join(missing)}")
        sys.exit(1)

    topics = get_trending_topics()
    if not topics:
        print("❌ No topics")
        sys.exit(1)

    topic = random.choice(topics)
    print(f"\n🎯 Topic: {topic['title']} ({topic['source']})")

    # Pass description so keyword extraction works better
    img_url = get_image_url(topic.get('entry'), topic['title'], topic.get('description', ''))

    print("\n✍️ Generating content (1500‑2000 words, ~5‑10 minutes)...")
    content, summary = generate_blog_post(topic)
    if not content:
        print("❌ Generation failed")
        sys.exit(1)
    print(f"✅ Generated {len(content)} chars")
    print(f"📝 Summary: {summary[:100]}...")

    local = save_local_post(topic['title'], content, summary)

    print("\n📤 Posting to Blogger...")
    ok, url = post_to_blogger(
        topic['title'],
        content,
        summary,
        img_url,
        ['AI Generated', topic['source'].replace(' ', '-'), 'Optimized']
    )

    if ok:
        print("\n🔔 Pinging Google...")
        ping_google()
        if GSC_SERVICE_ACCOUNT_JSON:
            print("\n📤 Submitting to Google Search Console...")
            submit_to_search_console(url)
        print(f"\n✨ SUCCESS! Post published: {url}")
        print(f"📁 Backup: {local}")
    else:
        print(f"\n❌ Failed to publish: {url}\nBackup saved at {local}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error("Main", str(e))
        sys.exit(1)
