"""Attach pyannote speaker turns to ASR words by maximum time overlap (Day 1).

In:  data/asr/{meeting}.{condition}.diar.json (anonymous SPEAKER_xx turns)
Out: Transcript with anonymous speakers; pipeline.align maps them to AMI roles.
"""
