"""Align ASR transcripts to the AMI human transcript (Day 1).

- Parses the AMI words/segments XML into the CLEAN Transcript.
- Word-level alignment (jiwer) gives per-word correct/substituted/deleted flags, reused by
  evals.attribution to check whether an insight's quote span was misheard.
- Maps anonymous diarization speakers to AMI roles by majority overlap with the human turns,
  so speaker mix-ups show up as role disagreements.
Out: data/transcripts/{meeting}.{condition}.jsonl
"""
