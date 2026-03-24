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

### 3. Shofo TikTok General (HuggingFace) — NEW FIND
**URL:** https://huggingface.co/datasets/Shofo/shofo-tiktok-general-small
**What:** 58K TikTok videos with full video files, transcripts, descriptions, hashtags, sticker text, comments, and rich engagement metrics
**Format:** Parquet (~500GB with video files)

| Feature | Included? |
|---------|-----------|
| Video files | Yes |
| Transcripts | Yes |
| Descriptions + hashtags | Yes |
| Engagement metrics | Yes — play, like, comment, share, collect, repost, download counts |
| Video duration/resolution/fps | Yes |
| Comments with metadata | Yes |
| AI-generated flag | Yes |
| Language | English + Spanish |

**Why it's great for us:** This is arguably the single best dataset for our use case. It has *everything* — transcripts for hook/pacing analysis, engagement metrics to define "viral," video metadata, and even comments for audience reaction analysis. Transcripts are the key differentiator — we can analyze exactly what's said in viral videos.

**Limitations:** ~500GB if downloading video files (but we mainly need the transcripts + metadata). Custom license.

### 4. YouTube/TikTok Trends 2025 (HuggingFace) — NEW FIND
**URL:** https://huggingface.co/datasets/tarekmasryo/youtube-tiktok-trends-dataset-2025
**What:** 98K short-form videos from YouTube Shorts AND TikTok (Jan-Aug 2025)
**Format:** CSV/Parquet (44.1 MB — lightweight!)
**License:** CC BY 4.0 (most permissive of all datasets found)

| Feature | Included? |
|---------|-----------|
| Title + hashtags + tags | Yes |
| Sample comments | Yes |
| Sound type + music track + genre | Yes |
| Duration | Yes |
| Engagement metrics | Yes — views, likes, comments, shares, saves, dislikes |
| **Completion rate** | **Yes — critical for hook/pacing analysis** |
| **Average watch time** | **Yes — reveals content retention** |
| Engagement velocity | Yes — pre-computed |
| Creator tier | Yes |
| Traffic source | Yes |
| Trend labels | Yes |
| Cross-platform | Yes — YouTube Shorts + TikTok |

**Why it's great for us:** The only dataset with **completion rate and average watch time** — these are the two most important signals for understanding hooks and pacing. If viewers drop off in the first 2 seconds, the hook failed. If they watch to the end, the structure worked. Also uniquely provides cross-platform comparison. CC BY 4.0 license means no restrictions. Only 44MB — can load instantly.

### 5. Gopher-Lab TikTok Transcript Sets (HuggingFace) — NEW FIND
Three complementary datasets of transcripts from high-performing TikTok videos:

| Dataset | URL | Size | Focus |
|---------|-----|------|-------|
| Most-Commented Transcripts | https://huggingface.co/datasets/Gopher-Lab/TikTok_MostComment_Video_Transcription_Example | 4,580 videos | What generates discussion |
| Most-Shared Transcripts | https://huggingface.co/datasets/Gopher-Lab/TikTok_Most_Shared_Video_Transcription_Example | 3,222 videos | What people spread |
| Hottest/Trending Transcripts | https://huggingface.co/datasets/Gopher-Lab/TikTok_Hottest_Video_Transcript_Example | 363 videos | What's currently trending |

**Combined:** ~8,165 transcripts from proven viral TikTok content. MIT license.
**Format:** Parquet/CSV/JSON. Fields: video ID, URL, title, country, duration, cover image, full transcription text, detected language, confidence score.

**Why it's great for us:** A curated corpus of proven viral scripts — exactly the kind of content we want S1 to learn patterns from. These are transcripts from videos that have already demonstrated they generate engagement. MIT license is maximally permissive.

**Limitation:** No engagement counts beyond the selection criterion (most commented/shared/trending).

### 6. MicroLens (Academic — Jilin University) — NEW FIND
**URL:** https://github.com/westlake-repl/MicroLens
**Paper:** "MicroLens: A Content-Driven Micro-Video Recommendation Dataset at Scale" (2024)
**What:** 100K users, 1M+ short videos, 100M+ interactions with actual video files AND multimodal features

| Feature | Included? |
|---------|-----------|
| Raw video files | Yes |
| Visual features (pre-extracted) | Yes |
| Audio features | Yes |
| Text descriptions | Yes |
| Engagement metrics | Yes — click, like, follow, share, comment, watch time |
| Cover images | Yes |

**Why it's great for us:** One of the only academic datasets with actual video files alongside engagement metrics at scale. The multimodal features (visual + audio + text) enable the richest content analysis possible.

**Access:** Open download after agreement.

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

### For the MVP (start immediately)

**YouTube/TikTok Trends 2025** — 44MB CSV, CC BY 4.0, loads in seconds. Has completion_rate and avg_watch_time which are the most important signals for hook/pacing analysis. Use the top 100 videos by engagement as S1 input. Feed titles + hashtags + sound metadata + engagement metrics to the LLM.

**Gopher-Lab transcript sets** — ~8K transcripts from proven viral TikTok content. MIT license. Combine all three sets for a corpus of what viral scripts actually sound like. Feed directly to S3 for pattern learning.

### For the full distributed system

**Shofo TikTok General** — 58K videos with transcripts + engagement. The richest single dataset for content analysis. Use transcripts as S1 input for deep hook/pacing/structure extraction.

**TikTok-10M** — 6.65M videos for statistical validation. Cross-reference patterns found in smaller datasets against massive engagement data.

**Tsinghua ShortVideo** — Academic credibility. Has English ASR transcripts + visual features. Good for the course write-up since it's from Tsinghua.

### Suggested spec language update
> ~~"100 videos from Tsinghua/Kuaishou 10K user preference dataset"~~
> → "Top 100 videos by engagement, sourced from the YouTube/TikTok Trends 2025 dataset (completion rate + watch time signals) and Gopher-Lab TikTok transcript corpus (proven viral scripts). Supplemented by Shofo TikTok transcripts and TikTok-10M for large-scale pattern validation."

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
- [Shofo TikTok General (HuggingFace)](https://huggingface.co/datasets/Shofo/shofo-tiktok-general-small)
- [YouTube/TikTok Trends 2025 (HuggingFace)](https://huggingface.co/datasets/tarekmasryo/youtube-tiktok-trends-dataset-2025)
- [Gopher-Lab Most-Commented Transcripts](https://huggingface.co/datasets/Gopher-Lab/TikTok_MostComment_Video_Transcription_Example)
- [Gopher-Lab Most-Shared Transcripts](https://huggingface.co/datasets/Gopher-Lab/TikTok_Most_Shared_Video_Transcription_Example)
- [Gopher-Lab Hottest Transcripts](https://huggingface.co/datasets/Gopher-Lab/TikTok_Hottest_Video_Transcript_Example)
- [MicroLens (GitHub)](https://github.com/westlake-repl/MicroLens)
- [datahiveai TikTok-Videos (HuggingFace)](https://huggingface.co/datasets/datahiveai/Tiktok-Videos)
