"""Quote-backed insight extraction with an LLM (Day 2).

In:  Transcript (any condition). Out: list[extract.schema.Insight] as JSONL.
Rules: every insight cites verbatim quotes with timestamps; quotes not found in the
transcript are rejected, not repaired. Temperature 0; repeated CLEAN runs measure
model self-disagreement so it is not counted as noise damage.
"""
