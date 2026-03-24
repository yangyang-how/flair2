# Dataset Research — Briefing for Sam & Jess

**Date:** 2026-03-24
**Purpose:** Resolve OQ#2 (what datasets are available) and determine the best data source for the pipeline.

---

## Critical Finding

**The "Tsinghua/Kuaishou 10K user preference dataset" referenced in the spec is a recommender system dataset (likely KuaiRec), NOT a content analysis dataset.** It contains user-item interaction logs (who watched what, for how long) but **zero information about video content** — no transcripts, no scripts, no visual features, no captions. It cannot be used to analyze *why* videos go viral.

This means the data source strategy needs to change. Below are the options, ranked by usefulness.

---

## Tier 1: Best Fit for Our Project

### 1. TikTok-10M (HuggingFace)
**URL:** https://huggingface.co/datasets/The-data-company/TikTok-10M
**What:** ~6.65M TikTok videos with 65 columns of metadata
**Format:** Parquet

| Feature | Included? |
|---------|-----------|
| Video descriptions/captions | Yes (`desc` field — hashtags, text, calls-to-action) |
| Engagement metrics | Yes — `play_count`, `digg_count` (likes), `comment_count`, `share_count`, `collect_count` (saves) |
| Video duration | Yes |
| Music/audio metadata | Yes — title, artist, duration, audio URL |
| Hashtags/challenges | Yes — JSON array per video |
| Location data | Yes — 15 POI fields |
| Actual video files | No — URLs provided but no downloads |
| Transcripts | No |
| Video quality score | Yes (`vq_score`) |

**Why it's great for us:**
- Massive scale — can filter for top-performing videos by engagement
- Captions + hashtags give us text content to analyze patterns
- Engagement metrics let us study what performs well vs poorly
- Duration data helps analyze pacing
- Music metadata reveals audio trend patterns
- Recent data (collected March 2025)

**Limitations:**
- No transcripts — would need to generate via Whisper if we want spoken content
- No actual video files — URLs may expire, but we mainly need metadata for S1 analysis
- Non-commercial license

**How to use for our pipeline:**
- S1: Analyze top 100 videos by `play_count`. Feed `desc`, `duration`, `challenges`, `music_title` to LLM. Extract hook type, pacing, structure from the caption/description patterns.
- S4: Personas evaluate scripts against patterns learned from high-engagement videos.

---

### 2. Tsinghua ShortVideo Dataset (WWW 2025)
**URL:** https://github.com/tsinghua-fib-lab/ShortVideo_dataset
**Paper:** "A Large-scale Dataset with Behavior, Attributes, and Content of Mobile Short-video Platform" (WWW 2025)
**What:** 10,000 users × 153,561 videos from a Chinese short-video platform
**Download:** http://fi.ee.tsinghua.edu.cn/datasets/short-video-dataset (user: videodata, pass: ShortVideo@10000)

| Feature | Included? |
|---------|-----------|
| Raw video files (MP4) | Yes — 3.2TB total |
| Visual features (ResNet/ViT) | Yes — 256-dim vectors per 8 clips |
| ASR transcripts (Chinese) | Yes (`asr_zn` folder) |
| ASR transcripts (English) | Yes (`asr_en` folder) |
| Video titles (English) | Yes (`title_en` folder) |
| Engagement metrics | Yes — `watch_time`, `cvm_like`, `comment`, `follow`, `collect`, `forward`, `hate`, `effective_view` |
| Video categories | Yes — 3-level hierarchy (37 → 281 → 382 categories) |
| User demographics | Yes — gender, age, city, phone price |
| Duration | Yes |

**Why it's great for us:**
- **Has everything** — actual video files, transcripts, engagement metrics, and content features
- Transcripts in English enable direct text analysis of what's said in videos
- Visual features pre-extracted (don't need to process 3.2TB of video ourselves)
- Academic dataset with proper paper — strong for course project credibility
- From Tsinghua — matches the original spec reference

**Limitations:**
- 3.2TB for raw videos is huge (but we can use just the transcripts + features)
- Chinese platform — content patterns may differ from TikTok/YouTube
- No explicit license (paper citation required)
- Download may be slow (3 concurrent connections max for large files)

**How to use for our pipeline:**
- S1: Feed English transcripts + visual features + categories to LLM. Extract hook type, pacing, structure, engagement triggers.
- Can use engagement metrics (`watch_time`, `effective_view`, likes, forwards) to rank videos and analyze top performers.
- **This is the closest match to the original spec's "100 videos from Tsinghua/Kuaishou dataset."**

---

## Tier 2: Good Supplementary Sources

### 3. FineVideo (HuggingFace, by HuggingFace team)
**URL:** https://huggingface.co/datasets/HuggingFaceFV/finevideo
**What:** 43,751 YouTube videos with rich annotations
**Format:** Video files + JSON metadata

| Feature | Included? |
|---------|-----------|
| Video files | Yes |
| Speech-to-text transcripts | Yes |
| Scene-level annotations | Yes — activities, timestamps, mood shifts |
| Character descriptions | Yes |
| Engagement score | Yes — composite of views, likes, comments |
| Categories | Yes — 122 categories |

**Usefulness: Medium.** Great content annotations but YouTube long-form (avg 4.7 min), not short-form. Could supplement pattern analysis but doesn't match our 4-8 second video target.

### 4. TikTok Video Performance Dataset (Kaggle)
**URL:** https://www.kaggle.com/datasets/haseebindata/tiktok-video-performance-dataset
**What:** ~19,382 TikTok videos with engagement metrics
**Format:** CSV, 13 columns

**Usefulness: Medium.** Smaller scale, engagement metrics included, but limited content-level features. Good for quick prototyping.

### 5. TikTok Viral Trends 2025 (Kaggle)
**URL:** https://www.kaggle.com/datasets/imaadmahmood/tiktok-viral-trends-2025
**What:** Trending TikTok data from 2025

**Usefulness: Medium.** Recent data, but column details not confirmed. Worth checking.

### 6. YouTube/TikTok Trends 2025 (Kaggle)
**URL:** https://www.kaggle.com/datasets/tarekmasryo/youtube-shorts-and-tiktok-trends-2025
**What:** Combined YouTube Shorts + TikTok trending data

**Usefulness: Medium.** Cross-platform data could reveal universal short-form patterns.

---

## Tier 3: Kuaishou Datasets (NOT Suitable for Content Analysis)

These are recommender system evaluation datasets. They answer "who watched what" but NOT "what makes a video good."

| Dataset | Records | Has Video Content? | Has Transcripts? | Has Engagement? | Useful for Us? |
|---------|---------|-------------------|------------------|-----------------|---------------|
| **KuaiRec** | 1.4K users × 3.3K videos (dense) | No | No | Yes (watch ratio, likes) | No |
| **KuaiRand** | 27K users × 7.5K videos | No | No | Yes (clicks, likes, follows) | No |
| **KuaiSAR** | 25K users × 6.9M interactions | No | No | Yes (clicks, likes) | No |

---

## Recommendation

**Primary dataset: Tsinghua ShortVideo Dataset (WWW 2025)**
- Closest to the original spec
- Has transcripts (English), visual features, engagement metrics, and video categories
- Academic credibility for a course project
- We don't need to download 3.2TB — just the transcripts, features, and interaction data

**Supplementary dataset: TikTok-10M**
- Massive TikTok-specific data with captions and engagement
- Good for validating patterns across platforms
- Easy to load (Parquet via HuggingFace)

**Updated spec language:**
> ~~"100 videos from Tsinghua/Kuaishou 10K user preference dataset"~~
> → "Top 100 videos by engagement from the Tsinghua ShortVideo Dataset (WWW 2025), using English ASR transcripts and pre-extracted visual features. Supplemented by TikTok-10M for cross-platform pattern validation."

---

## Sources

- [Tsinghua ShortVideo Dataset (GitHub)](https://github.com/tsinghua-fib-lab/ShortVideo_dataset)
- [ShortVideo Paper (arXiv)](https://arxiv.org/abs/2502.05922)
- [TikTok-10M (HuggingFace)](https://huggingface.co/datasets/The-data-company/TikTok-10M)
- [FineVideo (HuggingFace)](https://huggingface.co/datasets/HuggingFaceFV/finevideo)
- [TikTok Video Performance (Kaggle)](https://www.kaggle.com/datasets/haseebindata/tiktok-video-performance-dataset)
- [TikTok Viral Trends 2025 (Kaggle)](https://www.kaggle.com/datasets/imaadmahmood/tiktok-viral-trends-2025)
- [YouTube/TikTok Trends 2025 (Kaggle)](https://www.kaggle.com/datasets/tarekmasryo/youtube-shorts-and-tiktok-trends-2025)
- [KuaiRec (GitHub)](https://github.com/chongminggao/KuaiRec)
- [KuaiRand (GitHub)](https://github.com/chongminggao/KuaiRand)
- [datahiveai TikTok-Videos (HuggingFace)](https://huggingface.co/datasets/datahiveai/Tiktok-Videos)
