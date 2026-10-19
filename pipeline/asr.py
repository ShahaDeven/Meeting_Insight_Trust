"""Load the GPU pod's faster-whisper output into core.transcript.Transcript (Day 1).

In:  data/asr/{meeting}.{condition}.json (words with start/end/probability, from gpu/transcribe.py)
Out: words with conf set; speakers attached later by diarize + align.
"""
