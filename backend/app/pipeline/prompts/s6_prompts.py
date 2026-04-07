S6_PERSONALIZE_PROMPT = """You are a content style adapter. Rewrite this video script to match the creator's voice AND generate a video production prompt.

## Original Script
Hook: {hook}
Body: {body}
Payoff: {payoff}
Pattern: {pattern_used}
Duration target: ~{estimated_duration}s

## Creator Voice Profile
Tone: {tone}
Vocabulary they use: {vocabulary}
Catchphrases: {catchphrases}
Topics to avoid: {topics_to_avoid}
{creator_context}
## Task
1. **Personalized script**: Rewrite the script in this creator's authentic voice. Keep the structural pattern (hook type, pacing, emotional arc) but change the words, phrases, and delivery style to match their personality. It should sound like THEM, not a generic copywriter.{niche_instruction}
2. **Video prompt**: Write a detailed video production prompt describing the visual style, camera angles, transitions, text overlays, and pacing for this script. This prompt will be used by an AI video generator.

## Output Format
Respond with ONLY a JSON object:
{{
    "personalized_script": "The full rewritten script in the creator's voice",
    "video_prompt": "Detailed video production prompt for AI video generation"
}}"""
