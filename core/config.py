"""Paths, meeting selection, and model settings shared by every stage."""

import os
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
AMI_RAW = DATA / "ami"            # official annotations zip, unpacked
ASR_OUT = DATA / "asr"            # per-meeting JSON pulled back from the GPU pod
TRANSCRIPTS = DATA / "transcripts"  # one Transcript JSON per meeting x condition (pipeline.build)
INSIGHTS = DATA / "insights"
RESULTS = DATA / "results"
SAMPLES = DATA / "samples"        # small derived samples, committed
REPORT = ROOT / "report"


class Condition(StrEnum):
    """Rungs of the counterfactual ladder used for error attribution.

    An error that first appears at a rung is blamed on what that rung adds:
    CLEAN -> model, SPEAKER_SWAP -> speaker mix-up, HEADSET/FARFIELD -> mishearing.
    """

    CLEAN = "clean"                # AMI human transcript, true speakers
    SPEAKER_SWAP = "speaker_swap"  # human words, a share of turns relabeled
    HEADSET = "headset"            # ASR + diarization on the Mix-Headset recording
    FARFIELD = "farfield"          # ASR + diarization on one far-field array channel


# AMI scenario series: four meetings (a-d) by the same team of four.
# One series per recording site (Edinburgh, Idiap, TNO) so room acoustics vary.
# PRIMARY is the 3-series run; EXTENDED adds three more for 6-fold series-level CV.
# Verify completeness against the downloaded annotations before the GPU run.
PRIMARY_SERIES = ["ES2004", "IS1009", "TS3003"]
EXTENDED_SERIES = ["ES2011", "IS1008", "TS3004"]
SERIES = PRIMARY_SERIES + EXTENDED_SERIES


def meetings(series: list[str] = SERIES) -> list[str]:
    return [f"{s}{part}" for s in series for part in "abcd"]


# AMI participant roles; owners are recorded as roles so speaker mix-ups are visible.
ROLES = ["PM", "ME", "UI", "ID"]  # project manager, marketing, user interface, industrial design

AMI_MIRROR = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
AMI_ANNOTATIONS_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
MIC_FILES = {
    Condition.HEADSET: "{mid}.Mix-Headset.wav",
    Condition.FARFIELD: "{mid}.Array1-01.wav",
}

EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "claude-haiku-5-5")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-haiku-5-5")
MAX_USD = float(os.getenv("MAX_USD", "10"))
