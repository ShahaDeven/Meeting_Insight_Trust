"""Project state across a 4-meeting series (Day 3).

re_summarize:     rewrite the state from (previous state + new meeting) each time.
evidence_ledger:  append/retire quote-backed entries; abstain when no new evidence.
Scored on retention by meeting d and on unsupported writes, at each noise level.
"""
