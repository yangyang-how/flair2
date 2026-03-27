S1_ANALYZE_PROMPT = """You are a short-form video content analyst. Analyze this video and extract its STRUCTURAL patterns — not surface trends.

## Video Information
- Video ID: {video_id}
- Duration: {duration}s
- Description: {description}
- Transcript: {transcript}
- Engagement: {engagement}

## What to Extract (structural only)

1. **hook_type**: How does the video open? One of: "question", "shock", "story", "direct_address"
2. **pacing**: What is the rhythm? e.g., "fast_slow_fast", "escalating", "steady", "staccato"
3. **emotional_arc**: What emotional journey? e.g., "curiosity_gap", "negative_to_positive", "tension_release", "surprise_reveal"
4. **pattern_interrupts**: List techniques used to maintain attention (visual cuts, topic shifts, tonal changes)
5. **retention_mechanics**: What keeps viewers watching? (open loops, payoff delays, numbered lists, dares/challenges)
6. **engagement_triggers**: What drives likes/shares/comments? (relatability, practical value, social currency, controversy, humor)
7. **structure_notes**: Free-form notes on the overall structure and why it works

## What NOT to Extract
- Do NOT mention specific sounds, dances, memes, challenges, hashtags, or trends
- Focus on the STRUCTURE that makes this video work, not the specific CONTENT

## Output Format
Respond with ONLY a JSON object:
{{
    "video_id": "{video_id}",
    "hook_type": "...",
    "pacing": "...",
    "emotional_arc": "...",
    "pattern_interrupts": ["...", "..."],
    "retention_mechanics": ["...", "..."],
    "engagement_triggers": ["...", "..."],
    "structure_notes": "..."
}}"""
