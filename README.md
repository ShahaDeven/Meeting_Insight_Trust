# Meeting Insight Trust

**Which meeting insights are safe to write to a CRM automatically, and which need a human?**

Meeting assistants extract decisions, action items, owners and numbers from calls and increasingly write them straight into systems of record. On real audio — accents, far-field room mics, crosstalk — some of those insights are wrong. This project measures *how often*, *why*, and *whether a trained risk score can route the risky ones to review*.

> 🚧 Work in progress. Results, charts and a live demo link will land here.

## What it does

1. **Transcribes real meetings at three noise levels** — human transcript (clean), headset-mic ASR (light), far-field room-mic ASR (heavy) — from the [AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/).
2. **Extracts quote-backed insights** — decisions, action items with owners and deadlines, cost figures, open risks — each tied to a timestamped supporting quote.
3. **Attributes every wrong insight** to a misheard word, a speaker mix-up, or a model mistake, using a counterfactual ladder (clean → speaker-swapped → headset → far-field).
4. **Scores each insight's risk** with a small calibrated classifier and splits results into *auto-write* vs *needs review*.
5. **Tracks project state across a 4-meeting series**, comparing re-summarization against a quote-backed evidence ledger.

## Layout

```
core/       config, AMI meeting ids, JSONL I/O
gpu/        RunPod script: faster-whisper + pyannote (word timestamps, confidence, speakers)
pipeline/   ASR/diarization loaders, alignment to human transcripts
extract/    insight schema, extractor, memory strategies
evals/      scoring, error attribution, speaker-swap test
risk/       features, training, calibration
app/        Streamlit review console
report/     charts and findings
```

All stages read and write JSONL, so any stage can be swapped for another team's pipeline.

## Data and license

Uses the AMI Meeting Corpus (Carletta et al., 2005), released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Raw audio is not redistributed; only short derived samples are included.
