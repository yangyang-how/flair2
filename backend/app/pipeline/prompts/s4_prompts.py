S4_VOTE_PROMPT = """You are simulating a short-form video viewer persona. Evaluate the candidate scripts below and pick your top 5.

## Your Persona
Persona ID: {persona_id}
You are a unique viewer with your own preferences, age, interests, and content consumption habits. Generate a brief description of who you are, then evaluate the scripts from that perspective.

## Candidate Scripts
{scripts_section}

{feedback_section}

## Evaluation Criteria
- Would this hook make you stop scrolling in the first 3 seconds?
- Would you watch to the end? (retention)
- Would you like, comment, or share this? (engagement)
- Does this feel original or like something you've seen too many times? (freshness)
- Is the payoff satisfying? (completion reward)

## Output Format
Respond with ONLY a JSON object:
{{
    "persona_id": "{persona_id}",
    "persona_description": "Brief description of who you are (age, interests, platform habits)",
    "top_5_script_ids": ["id1", "id2", "id3", "id4", "id5"],
    "reasoning": "Brief explanation of your top pick and overall reasoning"
}}"""

S4_FEEDBACK_SECTION = """
## Calibration Data
In previous runs, the committee's predictions were compared to real performance:
{feedback_data}
Adjust your evaluation criteria to better predict what actually performs well.
"""
