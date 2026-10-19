"""Attribute each wrong insight to mishearing, speaker mix-up, or the model (Day 4).

Counterfactual ladder: an error first appearing at CLEAN is the model; at SPEAKER_SWAP a
speaker mix-up; at HEADSET/FARFIELD mishearing. Per-insight confirmation from the word
alignment (quote span misheard?) and role mapping (owner speaker mislabeled?).
"""
