"""ASR + speaker diarization for the AMI series on a GPU pod.

Standalone (does not import the repo packages), so the pod only needs this folder.
For each meeting x mic it writes:
  out/{mid}.{condition}.json       faster-whisper words (start, end, probability) + segments
  out/{mid}.{condition}.diar.json  pyannote turns (overlap kept) + exclusive turns
Finished outputs are skipped, so re-running after an interruption resumes.

  bash gpu/run.sh --smoke                        # 60 s check + time/cost estimate
  bash gpu/run.sh --series ES2004 IS1009 TS3003  # primary series
  bash gpu/run.sh                                # all six series
"""

import argparse
import json
import os
import shutil
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path

import torch  # imported first so torch's cuDNN/cuBLAS are loaded before CTranslate2 looks for them
from faster_whisper import BatchedInferencePipeline, WhisperModel, decode_audio
from pyannote.audio import Pipeline

# Mirrors core/config.py.
PRIMARY = ["ES2004", "IS1009", "TS3003"]
EXTENDED = ["ES2011", "IS1008", "TS3004"]
MIRROR = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
MICS = {"headset": "Mix-Headset", "farfield": "Array1-01"}
SR = 16000
TOTAL_AUDIO_HRS = 24.4  # both mics, all six series (from AMI word end times)

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "audio"
OUT = HERE / "out"


def download(mid: str, cond: str) -> Path:
    path = AUDIO / f"{mid}.{MICS[cond]}.wav"
    if not path.exists():
        AUDIO.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")
        urllib.request.urlretrieve(f"{MIRROR}/{mid}/audio/{path.name}", part)
        part.rename(path)
    return path


def out_paths(mid: str, cond: str) -> tuple[Path, Path]:
    return OUT / f"{mid}.{cond}.json", OUT / f"{mid}.{cond}.diar.json"


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.rename(path)


def load_models(args):
    whisper = BatchedInferencePipeline(
        WhisperModel(args.whisper, device="cuda", compute_type="float16"))
    diar = Pipeline.from_pretrained(args.diarizer, token=os.environ["HF_TOKEN"])
    if diar is None:
        raise SystemExit(f"Could not load {args.diarizer}: accept its terms on Hugging Face "
                         "and check HF_TOKEN.")
    diar.to(torch.device("cuda"))
    return whisper, diar


def run_asr(whisper, audio) -> dict:
    t0 = time.time()
    segments, _ = whisper.transcribe(audio, language="en", batch_size=16, beam_size=5,
                                     word_timestamps=True)
    segs, words = [], []
    for s in segments:  # generator: decoding happens here
        segs.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                     "avg_logprob": round(s.avg_logprob, 4),
                     "no_speech_prob": round(s.no_speech_prob, 4)})
        for w in s.words or []:
            words.append({"text": w.word.strip(), "start": round(w.start, 3),
                          "end": round(w.end, 3), "prob": round(w.probability, 4)})
    return {"segments": segs, "words": words, "asr_sec": round(time.time() - t0, 1)}


def run_diar(diar, audio, num_speakers: int | None) -> dict:
    t0 = time.time()
    out = diar({"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": SR},
               num_speakers=num_speakers)

    def turns(ann):
        return [{"start": round(t.start, 3), "end": round(t.end, 3), "speaker": spk}
                for t, _, spk in ann.itertracks(yield_label=True)]

    # pyannote 4 returns both views; 3.x returns a single Annotation.
    full = getattr(out, "speaker_diarization", out)
    exclusive = getattr(out, "exclusive_speaker_diarization", None)
    return {"turns": turns(full),
            "exclusive_turns": turns(exclusive) if exclusive is not None else None,
            "diar_sec": round(time.time() - t0, 1)}


def process(mid: str, cond: str, path: Path, whisper, diar, args) -> dict:
    audio = decode_audio(str(path), sampling_rate=SR)
    duration = len(audio) / SR
    asr_path, diar_path = out_paths(mid, cond)
    meta = {"meeting_id": mid, "condition": cond, "mic": MICS[cond],
            "duration_sec": round(duration, 1)}

    asr = run_asr(whisper, audio)
    write_json(asr_path, meta | {"model": args.whisper} | asr)
    d = run_diar(diar, audio, args.num_speakers)
    write_json(diar_path, meta | {"model": args.diarizer, "num_speakers": args.num_speakers} | d)

    timing = {"meeting_id": mid, "condition": cond, "audio_min": round(duration / 60, 2),
              "asr_sec": asr["asr_sec"], "diar_sec": d["diar_sec"], "words": len(asr["words"])}
    with (OUT / "timing.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(timing) + "\n")
    return timing


def smoke(whisper, diar, args) -> None:
    print(f"GPU: {torch.cuda.get_device_name(0)} (capability {torch.cuda.get_device_capability(0)})")
    mid = PRIMARY[0] + "a"
    print(f"Downloading {mid} far-field ...")
    audio = decode_audio(str(download(mid, "farfield")), sampling_rate=SR)
    clip = audio[300 * SR: 360 * SR]  # minute 5-6: past the opening silence

    try:
        run_asr(whisper, clip[: 10 * SR])  # warm-up so CUDA init is not counted
        asr = run_asr(whisper, clip)
    except RuntimeError as e:
        print(f"\nWhisper failed on this GPU: {e}\n"
              "If it mentions 'no kernel image' or cuDNN/cuBLAS, CTranslate2 does not support "
              "this GPU. Terminate the pod and redeploy on an RTX 4090.")
        raise
    d = run_diar(diar, clip, None)

    print(f"\nWhisper: {len(asr['words'])} words in {asr['asr_sec']}s")
    print("  " + " ".join(f"{w['text']}({w['prob']:.2f})" for w in asr["words"][:20]))
    speakers = sorted({t["speaker"] for t in d["turns"]})
    print(f"pyannote: {len(d['turns'])} turns, speakers {speakers} in {d['diar_sec']}s")

    rtf = (asr["asr_sec"] + d["diar_sec"]) / 60
    est_hrs = TOTAL_AUDIO_HRS * rtf
    print(f"\nReal-time factor {rtf:.3f} -> all six series ~{est_hrs * 60:.0f} min GPU, "
          f"~${est_hrs * args.price:.2f} at ${args.price}/hr "
          f"(primary three ~${est_hrs * args.price * 0.53:.2f}). Short clips overstate this.")
    print("Smoke test passed.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="60 s check of GPU, Whisper and pyannote")
    p.add_argument("--series", nargs="+", default=PRIMARY + EXTENDED)
    p.add_argument("--conditions", nargs="+", default=list(MICS), choices=list(MICS))
    p.add_argument("--whisper", default="large-v3")
    p.add_argument("--diarizer", default="pyannote/speaker-diarization-community-1")
    # Every AMI meeting has four participants; a meeting bot knows this from the invite.
    p.add_argument("--num-speakers", type=int, default=4)
    p.add_argument("--price", type=float, default=1.19, help="GPU $/hr, for the estimate")
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    whisper, diar = load_models(args)
    if args.smoke:
        smoke(whisper, diar, args)
        return

    write_json(OUT / "run_info.json", {
        "gpu": torch.cuda.get_device_name(0), "whisper": args.whisper, "diarizer": args.diarizer,
        "num_speakers": args.num_speakers,
        "versions": {pkg: version(pkg) for pkg in
                     ["torch", "ctranslate2", "faster-whisper", "pyannote.audio"]}})

    jobs = [(f"{s}{part}", c) for s in args.series for part in "abcd" for c in args.conditions]
    todo = [j for j in jobs if not all(f.exists() for f in out_paths(*j))]
    print(f"{len(jobs) - len(todo)} of {len(jobs)} already done; {len(todo)} to run.")

    t_start = time.time()
    with ThreadPoolExecutor(4) as pool:  # downloads run ahead of the GPU
        pending = [pool.submit(download, *j) for j in todo]
        for i, (job, fut) in enumerate(zip(todo, pending), 1):
            t = process(*job, fut.result(), whisper, diar, args)
            took = t["asr_sec"] + t["diar_sec"]
            print(f"[{i}/{len(todo)}] {job[0]} {job[1]}: {t['audio_min']:.1f} min audio, "
                  f"{t['words']} words, {took:.0f}s "
                  f"(elapsed {(time.time() - t_start) / 60:.1f} min)", flush=True)

    archive = shutil.make_archive(str(HERE / "asr_out"), "gztar", OUT)
    print(f"\nDone. Download {archive} from the Jupyter file browser, then terminate the pod.")


if __name__ == "__main__":
    main()
