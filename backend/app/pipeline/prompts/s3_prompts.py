S3_GENERATE_PROMPT = """You are a viral short-form video scriptwriter. Generate ONE script using the specified structural pattern.

## Pattern to Use
{pattern_type}

## Pattern Library Context
These are the most common structural patterns found in high-engagement videos:
{pattern_library_summary}

{feedback_section}

## Requirements
- Write a script for a 15-45 second video
- Use the specified structural pattern (hook type + pacing)
- The script must have three parts: hook, body, payoff
- Focus on STRUCTURAL effectiveness, not trend-chasing
- The hook must capture attention in the first 3 seconds
- Include at least one pattern interrupt to maintain retention

## Output Format
Respond with ONLY a JSON object:
{{
    "script_id": "placeholder",
    "pattern_used": "{pattern_type}",
    "hook": "The opening 1-2 sentences (the first 3 seconds)",
    "body": "The main content (middle section)",
    "payoff": "The closing/payoff (last few seconds)",
    "estimated_duration": 25.0,
    "structural_notes": "Brief note on why this structure works"
}}"""

S3_FEEDBACK_SECTION = """
## Performance Calibration
Based on real performance data from previously posted videos:
{feedback_data}
Generate scripts more like the high-performers and less like the low-performers.
"""
