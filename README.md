#  ReadContext — Autonomous AI Tech Journalism & Blogger Publisher

<p align="center">
  <img src="logo.png" alt="ReadContext Logo" width="180" style="border-radius: 12px;" />
</p>

<p align="center">
  <strong>An autonomous, multi-platform investigative tech journalism engine engineered for <a href="https://readcontext.blogspot.com">readcontext.blogspot.com</a>.</strong><br>
  Powered by NVIDIA NIM microservices, real-time web scraping, authentic community discourse (Reddit, Hacker News, Google News), multi-layer deduplication, and strict Google AdSense / Publisher Policy safeguards.
</p>

<p align="center">
  <a href="https://github.com/adavidjulius/Automatic-Blogger-Poster/actions"><img src="https://img.shields.io/badge/GitHub%20Actions-Automated%20Workflow-2088FF?style=flat&logo=github-actions&logoColor=white" alt="Actions"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://www.nvidia.com/en-us/ai/"><img src="https://img.shields.io/badge/NVIDIA%20NIM-AI%20Microservices-76B900?style=flat&logo=nvidia&logoColor=white" alt="NVIDIA"></a>
  <a href="https://developers.google.com/blogger"><img src="https://img.shields.io/badge/Google%20Blogger-API%20v3-FF5722?style=flat&logo=blogger&logoColor=white" alt="Blogger"></a>
  <a href="https://adsense.google.com/"><img src="https://img.shields.io/badge/Google%20AdSense-Policy%20Compliant-4285F4?style=flat&logo=google&logoColor=white" alt="AdSense"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat" alt="License"></a>
</p>

---

## 🌟 Overview

**ReadContext** is an enterprise-grade automated digital newsroom system. Operating on scheduled GitHub Actions runners at zero hosting cost, it autonomously tracks emerging technology stories across 12+ public feeds, performs deep investigative web research, gathers authentic user sentiment from Reddit and Hacker News, synthesizes original, mobile-optimized dispatches (800–1,050 words; under 5 min read), matches verified press imagery, and publishes directly to Google Blogger while pinging Google Search Console for near-instant search indexing.

Unlike basic RSS feed auto-posters that republish scraped snippets or generate cookie-cutter text, ReadContext functions as a complete digital editorial team:
- **Zero Plagiarism & Original Synthesis**: Rewrites raw facts and benchmarks into original investigative journalism.
- **Topic-Adaptive Journalism**: Dynamically determines the narrative archetype (Hardware Review, AI Research, Cybersecurity Incident, Corporate Strategy) and generates bespoke, contextual section headings.
- **Multi-Source Primary Grounding**: Scrapes original article pages, extracts real quotes from industry leaders, and analyzes authentic Reddit and Hacker News discussion threads.
- **Anti-Duplicate Guardian**: Hybrid fuzzy deduplication combines sequence matching, token Jaccard indices, canonical URL tracking, and live Blogger feed queries to prevent duplicate publications.
- **Google AdSense Protection**: Strict content filtering guarantees zero graphic violence, zero unverified financial scams, zero click solicitations, and zero thin text.

## 🚀 Key Features

### 1. 🛡️ Google AdSense & Publisher Policy Guardrails
Every article passes automated safety checks prior to publication:
- **Zero Graphic Violence**: Automatic regex filtering eliminates any mention or imagery of weapons, casualties, gore, warfare, or physical harm.
- **Zero Geopolitical Bias**: Strict journalistic neutrality with no partisan war commentary or taking sides.
- **Zero Copyright Infringement**: Facts are synthesized into unique analytical prose; no copy-pasting of source paragraphs.
- **Zero Deceptive Placements & Click Solicitations**: Strictly bans "support us by clicking", fake download buttons, or misleading ad layouts.
- **Mobile-Optimized Substance (Under 5 Min Read)**: Targets **800 to 1,050 words** (~4-minute average reading speed) with a safety minimum of 650 words, keeping mobile readers engaged and boosting page completion rates for monetization.

### 2. 🧠 Topic-Adaptive AI Architecture (Ending the Cookie-Cutter Template)
ReadContext automatically identifies the story archetype and adapts its tone, vocabulary, and heading structure:
- **Consumer Hardware & Gadgets**: Focuses on ergonomics, engineering trade-offs, sensory accuracy, pricing, and teardown insights.
- **Artificial Intelligence & Software**: Covers neural architectures, token throughput, training weights, open-source adoption, and energy demands.
- **Cybersecurity Forensics**: Investigates attack vectors, CVE numbers, credential leaks, liability, and mitigation patches.
- **Venture & Corporate Strategy**: Analyzes M&A terms, board dynamics, market moats, and regulatory antitrust scrutiny.

> **Goodbye to Canned Phrases**: The generator bans repetitive tropes such as *"The Genesis of the Shift"*, *"Developer reactions"*, *"Real-world benchmarks"*, and *"economic trade-off"*. Every headline, H2, and H3 is bespoke to the story.

### 3. 🔍 Multi-Source Web Scraping & Reddit Comment Mining
ReadContext doesn't guess what people think — it reads the real web:
- **Direct Source Webpage Scraping**: Uses `BeautifulSoup` to extract actual ground-truth facts, executive quotes, and the official press photo directly from the source URL.
- **Reddit Community Mining**: Queries Reddit's search APIs across `r/technology`, `r/programming`, and `r/gadgets` to extract authentic comments, upvote trends, and user sentiment.
- **Hacker News Algolia**: Tracks developer discussions, technical critiques, and community karma scores.
- **Google News Cross-Reporting**: Finds corroborating reports across news wires for balanced reporting.

### 4. 🔁 Multi-Layer Deduplication Engine
Eliminates repeat postings through four robust layers:
1. **Fuzzy Sequence Matching**: Matches titles using `difflib.SequenceMatcher` to catch rephrased headlines.
2. **Token Jaccard & Keyword Overlap**: Detects stories with similar key entity combinations even if titles vary widely.
3. **Canonical URL & Aggregator Resolution**: Normalizes URLs and links across platforms (e.g., TechCrunch article vs. Bluesky post pointing to the same story).
4. **Live Blogger Feed Synchronization**: Queries the live Blogger JSON feed before publication to prevent duplicates across GitHub Action runs.

### 5. 📸 Context-Aware Real Press Visuals
- Extracts authentic press photos from `og:image` / `twitter:image` tags of the scraped source article.
- Queries Wikimedia Commons and Unsplash using high-precision entity keywords.
- Contextual categorized fallbacks ensure a hardware post never gets an irrelevant semiconductor photo.

### 6. 📐 SEO-Optimized Layout & Typography
- **Schema.org `NewsArticle` JSON-LD**: Embedded structured data for Google News and Google Discover rich snippets.
- **Executive Key Takeaways**: High-value summary card at the start of each dispatch.
- **Typographic Hierarchy**: Distinct H2/H3 headings, paragraph indentation, styled pull-quotes, and responsive image frames.
- **Full Source Citations**: Clean citation card with verified backlinks to all reference discussions.

---

## 📂 Project Structure

```
Automatic-Blogger-Poster/
├── .github/
│   └── workflows/
│       └── daily-blog.yml          # GitHub Actions workflow (6x daily schedule)
├── .blog-cache/
│   ├── posted_history.json         # Deduplication cache of published dispatches
│   └── posts_log.json              # Published URLs and timestamp logs
├── _posts/                         # Local archive of published articles in Markdown/HTML
├── pages/                          # AdSense mandatory compliance pages
│   ├── privacy-policy.html         # GDPR, CCPA & AdSense cookie disclosure
│   ├── about-us.html               # Editorial standards & fact-checking policy
│   ├── contact.html                # Newsroom contact & corrections policy
│   └── terms-of-service.html       # Intellectual property & terms of service
├── scripts/
│   └── generate_post.py            # Main autonomous engine script
├── logo.png                        # ReadContext brand signature
├── requirements.txt                # Python dependencies
├── _config.yml                     # Jekyll static site configuration
├── index.md                        # Jekyll blog homepage
└── README.md                       # Documentation
```

---

## ⚡ Quick Setup & Deployment

### Step 1: Fork or Clone the Repository

```bash
git clone https://github.com/adavidjulius/Automatic-Blogger-Poster.git
cd Automatic-Blogger-Poster
```

### Step 2: Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Configure GitHub Secrets

In your GitHub repository, navigate to **Settings → Secrets and variables → Actions** and add the following repository secrets:

| Secret Name | Required? | Description |
|---|---|---|
| `BLOGGER_BLOG_ID` | **Required** | Your Blogger Blog ID (found in the Blogger dashboard URL). |
| `GOOGLE_CLIENT_ID` | **Required** | OAuth 2.0 Client ID from Google Cloud Console. |
| `GOOGLE_CLIENT_SECRET` | **Required** | OAuth 2.0 Client Secret from Google Cloud Console. |
| `GOOGLE_REFRESH_TOKEN` | **Required** | OAuth refresh token with `https://www.googleapis.com/auth/blogger` scope. |
| `NVIDIA_API_KEY` | **Required** | NVIDIA NIM API key for LLM inference ([build.nvidia.com](https://build.nvidia.com)). |
| `GSC_SERVICE_ACCOUNT_JSON` | Optional | Service account JSON key for instant Google Search Console indexing. |
| `UNSPLASH_ACCESS_KEY` | Optional | Unsplash Developer Access Key for editorial photo curation. |
| `GOOGLE_CSE_API_KEY` | Optional | Google Custom Search API key. |
| `GOOGLE_CSE_ID` | Optional | Google Programmable Search Engine ID. |

---

## 🔑 How to Generate Blogger OAuth Credentials

1. Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create a new project (e.g., `Blogger-Auto-Poster`).
3. Enable the **Blogger API v3**:
   - Navigate to **APIs & Services → Library** → search for `Blogger API v3` → click **Enable**.
4. Configure the **OAuth Consent Screen**:
   - Choose **External** user type.
   - Add the scope: `https://www.googleapis.com/auth/blogger`.
   - Add your Google account under **Test users**.
5. Create OAuth 2.0 Credentials:
   - Navigate to **APIs & Services → Credentials** → **Create Credentials** → **OAuth client ID**.
   - Application type: **Desktop app** (or Web application with `https://developers.google.com/oauthplayground` as redirect URI).
   - Copy your `Client ID` and `Client Secret`.
6. Obtain your `Refresh Token`:
   - Visit the **[Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)**.
   - Click the gear icon (top right) → check **Use your own OAuth credentials** → enter your Client ID and Client Secret.
   - In Step 1, enter `https://www.googleapis.com/auth/blogger` → click **Authorize APIs**.
   - Sign in with your Google account.
   - In Step 2, click **Exchange authorization code for tokens**.
   - Copy the generated `Refresh token`.

---

## ⏰ Automated Publishing Schedule

The GitHub Actions workflow (`.github/workflows/daily-blog.yml`) is scheduled to run **6 times daily** at peak traffic hours:

| UTC Time | IST Time (UTC+5:30) | EST Time (UTC-5) | Target Audience |
|---|---|---|---|
| `03:30 UTC` | `09:00 IST` | `22:30 EST` (prev) | Asia Morning / US Late Evening |
| `07:00 UTC` | `12:30 IST` | `02:00 EST` | Europe Morning / Asia Midday |
| `12:30 UTC` | `18:00 IST` | `07:30 EST` | US East Morning / Europe Midday |
| `13:00 UTC` | `18:30 IST` | `08:00 EST` | US Market Opening Rush |
| `16:30 UTC` | `22:00 IST` | `11:30 EST` | US Midday Peak Traffic |
| `19:00 UTC` | `00:30 IST` (next) | `14:00 EST` | US Afternoon Peak Traffic |

> **Manual Trigger**: You can also trigger a run on demand anytime via the **Actions** tab in GitHub by selecting **"Daily Blog Post to Blogger"** → **"Run workflow"**.

---

## 🛠️ Local Testing

You can run the engine locally before pushing to production:

```bash
# 1. Export your API keys (or create a local .env file)
export NVIDIA_API_KEY="your-nvidia-api-key"

# 2. Run in test/generation mode (skips Blogger publishing if Google credentials are absent)
python scripts/generate_post.py

# 3. View the generated article
cat _posts/*.md | head -n 40
```

To test publishing the essential AdSense compliance pages:
```bash
python scripts/generate_post.py --publish-pages
```

---

## 📑 AdSense Compliance Pages

Google AdSense requires specific static compliance pages before approving an account. Pre-written, beautifully formatted pages are located in `pages/`:

| Page | File Path | Purpose |
|---|---|---|
| **Privacy Policy** | `pages/privacy-policy.html` | Discloses GDPR, CCPA, and Google AdSense DART cookies. |
| **About Us** | `pages/about-us.html` | Editorial standards, fact-checking principles, and mission. |
| **Contact Us** | `pages/contact.html` | Newsroom editorial contacts, corrections, and turnaround times. |
| **Terms of Service** | `pages/terms-of-service.html` | Fair use, copyright disclaimers, and liability limits. |

To publish these pages to Blogger:
1. Open the [Blogger Dashboard](https://www.blogger.com).
2. Go to **Pages → New page**.
3. Switch from **Compose view** to **HTML view** (`<>`).
4. Paste the content from each corresponding file in `pages/` and click **Publish**.

---

## 🤝 Contributing

Contributions are warmly welcomed! Please follow these steps:
1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/editorial-upgrade`).
3. Commit your changes (`git commit -m 'Add new tech feed source'`).
4. Push to the branch (`git push origin feature/editorial-upgrade`).
5. Open a Pull Request.

---

## 📄 License

This project is open-source and licensed under the [MIT License](LICENSE).

---

<p align="center">
  Crafted with ❤️ for autonomous high-quality digital journalism.
</p>
