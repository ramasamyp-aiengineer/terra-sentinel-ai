"""Assemble the 3-minute TerraSentinel demo video from screenshots + TTS.

Output: docs/pitch/TerraSentinel-AI-Demo-3min.mp4
Does not read or print secrets.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import textwrap
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"d:\Ram\TerraSentinelAI")
SHOTS = ROOT / "docs" / "pitch" / "shots"
OUT_DIR = ROOT / "docs" / "pitch" / "video" / "_build"
FINAL = ROOT / "docs" / "pitch" / "TerraSentinel-AI-Demo-3min.mp4"
W, H = 1920, 1080
FPS = 30

# Timed beats: (duration_s, image_key or "title"/"end", caption)
BEATS: list[tuple[float, str, str]] = [
    (11.0, "title", "Which 250 metres should an engineer inspect today?"),
    (16.0, "command", "62,330 observations → 87 sites → 7 Critical/Elevated → 4 Act today"),
    (18.0, "datahub", "Data Hub: upload, validate, provenance — synthetic demo labelled"),
    (18.0, "chamoli", "Chamoli map: ranked 250 m segments, not a raw heat-map"),
    (24.0, "site", "NH-58 · RPI 86 CRITICAL · threshold window 35–64 days if trend continues"),
    (14.0, "trends", "16 passes recomputed · action sites 3 → 7 · this site 61 → 86"),
    (22.0, "workorder", "Gemini reasons with tools · summarises · creates the ticket"),
    (20.0, "workorder_ai", "Guard verifies every number · 6 tool calls · 7 numbers verified"),
    (12.0, "method", "Engine computes risk · Gemini narrates · Google Cloud ready"),
    (12.0, "end", "Team Agent Ram · review the demo, video and repository"),
]

NARRATION = textwrap.dedent(
    """
    Which 250 metres should an engineer inspect today?
    Satellites see the ground move. TerraSentinel ranks what matters.
    Gemini tells the engineer where to go first.

    After one pass on our demonstration dataset — labelled synthetic —
    we have sixty-two thousand displacement observations,
    cut into eighty-seven sites of two hundred and fifty metres.
    Only seven are Critical or Elevated. Four need a crew today.

    Everything starts in Data Hub.
    Engineers upload InSAR points, time series, assets and rainfall —
    or import from a link.
    Every file is validated in plain language before it enters the model.
    Provenance is kept for every dataset.

    Zoom to Chamoli. Sixty-nine sites along the Himalayan corridor.
    The map is the ranked shortlist.
    Rain alone never raises the alarm.
    Earthquakes are context only. They never move the score.

    Open N H 58, kilometre 3.25 to 3.50.
    Risk Priority Index eighty-six — Critical.
    Moving 6.2 millimetres a month, twice the baseline.
    Rain amplifies motion; it is not the hazard by itself.
    The outlook is a threshold-crossing window of thirty-five to sixty-four days
    if this trend continues — not a failure date.

    Trends and History replays sixteen satellite passes from the same data.
    Action sites rose from three to seven.
    This site climbed from sixty-one to eighty-six.
    History is recomputed, so every past score is reproducible.

    Now the generative A I.
    Gemini does not compute risk. The engine already did that.
    Gemini investigates with seven read-only tools.
    It reasons over those facts, summarises what is happening,
    and creates the inspection ticket —
    recommended action and a field checklist.
    A guard verifies every millimetre and every day against the tool results.
    On this live ticket: six tool calls, seven numbers verified.
    Recommendation: dispatch an inspection crew within twenty-four hours.

    Built for Google Cloud: Cloud Run, BigQuery-ready storage,
    and Vertex A I or A I Studio for Gemini.
    Deterministic maths. Tool-grounded narration. Auditable decisions.

    TerraSentinel A I — Team Agent Ram.
    Review the live demo, this video, and the repository.
    Thank you.
    """
).strip()

IMAGES = {
    "command": SHOTS / "app-command.png",
    "datahub": SHOTS / "app-datahub.png",
    "chamoli": SHOTS / "app-chamoli.png",
    "site": SHOTS / "app-site.png",
    "trends": SHOTS / "app-trends.png",
    "workorder": SHOTS / "app-workorders.png",
    "workorder_ai": SHOTS / "c-workorder-ai.png",
    "method": SHOTS / "app-methodology.png",
}


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidate = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = list(candidate.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
    if matches:
        return str(matches[0])
    raise SystemExit("ffmpeg not found on PATH")


def ffprobe() -> str:
    ff = Path(ffmpeg())
    probe = ff.with_name("ffprobe.exe" if ff.suffix.lower() == ".exe" else "ffprobe")
    if probe.exists():
        return str(probe)
    found = shutil.which("ffprobe")
    if found:
        return found
    raise SystemExit("ffprobe not found")


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ):
        p = Path(name)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def fit_cover(src: Path, dest: Path) -> None:
    im = Image.open(src).convert("RGB")
    scale = max(W / im.width, H / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    im = im.crop((left, top, left + W, top + H))
    im.save(dest, quality=95)


def title_card(dest: Path) -> None:
    im = Image.new("RGB", (W, H), "#0f1d1b")
    d = ImageDraw.Draw(im)
    # soft gradient band
    for y in range(H):
        t = y / H
        r = int(15 + 20 * t)
        g = int(29 + 90 * (1 - abs(t - 0.35)))
        b = int(27 + 40 * t)
        d.line([(0, y), (W, y)], fill=(r, min(g, 118), b))
    logo = SHOTS / "logo-mark.jpg"
    if logo.exists():
        mark = Image.open(logo).convert("RGB").resize((120, 120), Image.Resampling.LANCZOS)
        im.paste(mark, (120, 160))
    d.text((280, 175), "TerraSentinel AI", fill="#ffffff", font=font(54))
    d.text((280, 245), "GROUND-MOTION EARLY WARNING FOR INFRASTRUCTURE", fill="#5eead4", font=font(22))
    d.text((120, 380), "Which 250 metres should an", fill="#ffffff", font=font(64))
    d.text((120, 470), "engineer inspect today?", fill="#ffffff", font=font(64))
    d.text(
        (120, 620),
        "Satellites see the ground move.  Gemini tells engineers where to go first.",
        fill="#ccfbf1",
        font=font(32),
    )
    d.text((120, 920), "Google Cloud AI Builder Cup 2026  ·  JAPAC  ·  Sustainability", fill="#94a3b8", font=font(24))
    d.text((120, 970), "Team Agent Ram  ·  Demonstration data labelled synthetic", fill="#64748b", font=font(22))
    im.save(dest, quality=95)


def end_card(dest: Path) -> None:
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 8], fill="#0f766e")
    logo = SHOTS / "logo-mark.jpg"
    if logo.exists():
        mark = Image.open(logo).convert("RGB").resize((96, 96), Image.Resampling.LANCZOS)
        im.paste(mark, (120, 160))
    d.text((250, 180), "TerraSentinel AI", fill="#0f1d1b", font=font(48))
    d.text((120, 340), "Thank you.", fill="#0f1d1b", font=font(96))
    d.text(
        (120, 480),
        "Engine ranks.  Gemini reasons, summarises, and creates the ticket.",
        fill="#475854",
        font=font(30),
    )
    d.text((120, 540), "Every number is checked before an engineer sees it.", fill="#475854", font=font(30))
    d.rounded_rectangle([120, 640, 900, 820], radius=16, outline="#0f766e", width=3)
    d.text((160, 670), "TEAM", fill="#0f766e", font=font(18))
    d.text((160, 700), "Agent Ram", fill="#0f1d1b", font=font(42))
    d.text((160, 760), "Ramasamy P  ·  ramp21052000@gmail.com", fill="#475854", font=font(24))
    d.text((120, 900), "Ask: review the live demo, this video, and the repository.", fill="#0f766e", font=font(26))
    d.text((120, 960), "Google Cloud  ·  Cloud Run · BigQuery · Vertex AI / Gemini", fill="#64748b", font=font(22))
    im.save(dest, quality=95)


def caption_bar(im: Image.Image, text: str) -> Image.Image:
    out = im.copy()
    d = ImageDraw.Draw(out)
    bar_h = 110
    d.rectangle([0, H - bar_h, W, H], fill=(15, 29, 27, 230))
    # approximate with solid for RGB
    overlay = Image.new("RGBA", (W, bar_h), (15, 29, 27, 210))
    base = out.convert("RGBA")
    base.paste(overlay, (0, H - bar_h), overlay)
    d2 = ImageDraw.Draw(base)
    # wrap
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d2.textlength(trial, font=font(28)) < W - 160:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    y = H - bar_h + 28
    for line in lines[:2]:
        d2.text((80, y), line, fill="#ffffff", font=font(28))
        y += 36
    return base.convert("RGB")


def make_tts(wav_path: Path) -> None:
    ps = textwrap.dedent(
        f"""
        Add-Type -AssemblyName System.Speech
        $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $s.Rate = -1
        $s.Volume = 100
        try {{ $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female) }} catch {{}}
        $s.SetOutputToWaveFile('{str(wav_path).replace("'", "''")}')
        $s.Speak(@'
{NARRATION}
'@)
        $s.Dispose()
        """
    )
    script = OUT_DIR / "tts.ps1"
    script.write_text(ps, encoding="utf-8")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        check=True,
    )


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def make_segment(idx: int, duration: float, key: str, caption: str) -> Path:
    frame = OUT_DIR / f"frame_{idx:02d}.jpg"
    if key == "title":
        title_card(frame)
    elif key == "end":
        end_card(frame)
    else:
        src = IMAGES[key]
        if not src.exists():
            raise SystemExit(f"missing image {src}")
        fit_cover(src, frame)
        captioned = caption_bar(Image.open(frame), caption)
        captioned.save(frame, quality=95)

    seg = OUT_DIR / f"seg_{idx:02d}.mp4"
    # slight zoom for motion
    frames = max(1, int(duration * FPS))
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"zoompan=z='min(1.06,1+0.00035*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
        f"fps={FPS}"
    )
    cmd = [
        ffmpeg(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(frame),
        "-vf",
        vf,
        "-t",
        f"{duration:.2f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        str(seg),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return seg


def concat_and_mux(segs: list[Path], wav: Path, dest: Path) -> None:
    lst = OUT_DIR / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs), encoding="utf-8")
    silent = OUT_DIR / "video_silent.mp4"
    subprocess.run(
        [
            ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c",
            "copy",
            str(silent),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # pad or trim audio to video length
    vid_probe = subprocess.run(
        [
            ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(silent),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    vdur = float(vid_probe.stdout.strip())
    adur = wav_duration(wav)
    # If narration shorter/longer, keep video length and pad audio with silence
    audio_filter = f"apad=whole_dur={vdur:.2f}" if adur < vdur else f"atrim=0:{vdur:.2f},asetpts=PTS-STARTPTS"
    subprocess.run(
        [
            ffmpeg(),
            "-y",
            "-i",
            str(silent),
            "-i",
            str(wav),
            "-filter_complex",
            f"[1:a]{audio_filter}[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    total = sum(b[0] for b in BEATS)
    print(f"planned video length {total:.1f}s · beats {len(BEATS)}")

    wav = OUT_DIR / "narration.wav"
    print("generating narration (Windows SAPI)…")
    make_tts(wav)
    print(f"narration {wav_duration(wav):.1f}s")

    # Scale beat durations to match narration length (~3 min target)
    target = max(170.0, min(185.0, wav_duration(wav) + 2.0))
    scale = target / total
    segs: list[Path] = []
    for i, (dur, key, cap) in enumerate(BEATS):
        d = dur * scale
        print(f"  seg {i:02d} {key:12} {d:5.1f}s")
        segs.append(make_segment(i, d, key, cap))

    print("muxing…")
    concat_and_mux(segs, wav, FINAL)
    size_mb = FINAL.stat().st_size / (1024 * 1024)
    print(f"wrote {FINAL} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
