# 📰 ReadContent Blogger Auto Post — Automated Journalism Engine

An autonomous investigative journalism system engineered specifically for **[readcontext.blogspot.com](https://readcontext.blogspot.com)** (Blog ID: `6965563738161457805`). Powered by **NVIDIA NIM** cloud microservices with an active 5-model fallback chain, real multi-platform web research (Hacker News, Reddit, Slashdot, Lemmy, Bluesky, Quora, X, Product Hunt, TechCrunch, The Verge), verified real documentary photo curation via multimodal vision models, and strict **Google AdSense & Publisher Policy Safeguards**.

Runs seamlessly on **GitHub Actions** 6 times daily at zero hosting cost.

---

## 🛡️ Content Compliance & AdSense Policy Guardrails

The engine enforces strict editorial standards to guarantee high-quality monetization eligibility:

1. **🚫 Zero Graphic Violence**:
   - Automated screening filters out any text or imagery depicting blood, weapons, casualties, injuries, warfare, or physical destruction.
   - Multimodal vision model screens out gory or weapon-laden imagery before publication.

2. **🚫 Zero Geopolitical Bias**:
   - Excludes partisan battlefield updates and active military conflict commentary.
   - Enforces neutral, objective, third-person journalistic prose without emotional or derogatory language.

3. **🚫 Zero Copyright Infringement & Piracy**:
   - Articles are 100% original journalistic syntheses written by AI; no copy-pasting of third-party articles.
   - Prohibits cracked software, keygens, torrents, warez, or paywall bypass links.

4. **🚫 Zero Misinformation & Financial Schemes**:
   - Relies strictly on verified benchmarks, published research, and reputable tech press wires.
   - Blocks unscientific medical cures, conspiracy theories, and get-rich-quick/crypto schemes.

5. **🚫 Zero Advertising & Click Violations**:
   - Zero click solicitations: Never asks readers to click ads or includes text like "support us by clicking here."
   - Zero deceptive placements: Formats articles with native semantic HTML cards without deceptive buttons or fake download prompts.
   - Clean traffic: Directly pings standard Google Search sitemaps and Search Console indexing.

6. **🚫 Anti-Thin-Text Enforcement**:
   - Rejects thin 200-word summaries or raw unedited text blocks.
   - Enforces exhaustive, multi-section coverage (**1,400 to 2,200 words**) with automatic depth expansion if a draft falls below editorial thresholds.

---

## ⚡ NVIDIA NIM Microservices Architecture

- **Serverless API Speed**: High-velocity generation via NVIDIA NIM (`https://integrate.api.nvidia.com/v1`).
- **Active 5-Model Fallback Chain**: If any model encounters rate limits, timeouts, or transient errors mid-generation, the next model seamlessly takes over:
  1. `nvidia/nemotron-3.5-bolt-e4b` *(Primary: Blazing speed & tool use)*
  2. `nvidia/nemotron-3-ultra-550b-a55b` *(Secondary: Frontier 550B MoE narrative depth)*
  3. `poolside/laguna-xs-2.1` *(Tertiary: Fast structured technical journalism)*
  4. `minimaxai/minimax-m3.1-flash` *(Quaternary: High-throughput flash fallback)*
  5. `google/diffusiongemma-26b-a4b-it` *(Quinary: Multimodal text & vision)*
- **Multimodal Vision Verification**: Uses `google/diffusiongemma-26b-a4b-it` to inspect documentary visuals, confirm topic relevance, screen out social media share icons/buttons, and author descriptive photo captions.
- **Deduplication Engine**: Caches published stories in `.blog-cache/posted_history.json` and scans `_posts/` to ensure no duplicate stories are published across scheduled runs.

---

## 📑 Essential Compliance Pages (Required for AdSense)

To comply with AdSense requirements, the `pages/` directory includes pre-written, styled compliance pages formatted with ReadContext branding (`#F36C21` brand accents, Playfair Display typography, responsive cards):

- `pages/privacy-policy.html`: Complete GDPR, CCPA, and Google AdSense DART cookies disclosure.
- `pages/about-us.html`: Mission statement, editorial standards, zero-sensationalism, and fact-checking policy.
- `pages/contact.html`: Newsroom contact emails, corrections policy, turnaround time.
- `pages/terms-of-service.html`: Intellectual property, fair use, and external link disclaimers.

### How to Publish Essential Pages to Blogger:

**Method A: Automatic (with Blogger API credentials configured)**
```bash
python scripts/generate_post.py --publish-pages
```

**Method B: Blogger Dashboard (Manual)**
1. Log in to [Blogger Dashboard](https://www.blogger.com).
2. Go to **Pages** → click **New page**.
3. In the top-left of the post editor, switch from **Compose view** to **HTML view** (`<>`).
4. Paste the content of each file in `pages/` and set the page title:
   - `pages/privacy-policy.html` → Title: **Privacy Policy**
   - `pages/about-us.html` → Title: **About Us**
   - `pages/contact.html` → Title: **Contact Us**
   - `pages/terms-of-service.html` → Title: **Terms of Service**
5. Click **Publish**, then add these pages to your blog's top navigation bar or footer widget via **Layout** → **Page List / Link List**.

---

## 🚀 Quick Setup & Deployment

### 1. Configure GitHub Secrets

In your GitHub repository, navigate to **Settings → Secrets and variables → Actions** and add:

| Secret Name | Required? | Description |
|---|---|---|
| `BLOGGER_BLOG_ID` | Required | Your Blogger Blog ID: `6965563738161457805` |
| `GOOGLE_CLIENT_ID` | Required | OAuth 2.0 Client ID from Google Cloud Console. |
| `GOOGLE_CLIENT_SECRET` | Required | OAuth 2.0 Client Secret from Google Cloud Console. |
| `GOOGLE_REFRESH_TOKEN` | Required | Refresh token with `https://www.googleapis.com/auth/blogger` scope. |
| `NVIDIA_API_KEY` | Optional | Your NVIDIA NIM API key (defaults to built-in key if omitted). |
| `GSC_SERVICE_ACCOUNT_JSON` | Optional | Service account JSON key for instant Google Search Console indexing. |
| `UNSPLASH_ACCESS_KEY` | Optional | Free API access key from Unsplash Developers. |
| `GOOGLE_CSE_API_KEY` | Optional | Google Custom Search API key. |
| `GOOGLE_CSE_ID` | Optional | Google Programmable Search Engine ID. |

### 2. Posting Schedule

The workflow in `.github/workflows/daily-blog.yml` runs 6 times daily at peak engagement hours:
- `03:30 UTC` *(09:00 IST)*
- `07:00 UTC` *(12:30 IST)*
- `12:30 UTC` *(18:00 IST)*
- `13:00 UTC` *(18:30 IST)*
- `16:30 UTC` *(22:00 IST)*
- `19:00 UTC` *(00:30 IST)*

You can also trigger a publication manually anytime via the **Actions** tab by selecting **"Daily Blog Post to Blogger (NVIDIA AI Edition)"** → **"Run workflow"**.

### 3. Push to GitHub

```bash
git remote add origin https://github.com/adavidjulius/<your-repo-name>.git
git push -u origin main
```

---

## 🛠️ Local Testing

To run the generation pipeline on your local machine:

```bash
# 1. Activate the virtual environment
source .venv/bin/activate

# 2. Run the generator (runs in test/generation mode if Google secrets are absent)
python scripts/generate_post.py
```

Generated articles are saved as markdown archives in `_posts/` and the cache is updated in `.blog-cache/`.

---

## 📄 License

Open source under the [MIT License](LICENSE).
