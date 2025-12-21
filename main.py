"""
Auto-mashup generator
---------------------
This script produces a fully automatic AI-inspired music mashup.
Running ``python main.py`` will create ``output/mashup.wav`` without needing any input.

The implementation is intentionally dependency-free and uses simple synthesis
techniques (sine waves, filtered noise, envelopes) to mimic drums, bass, and melody.
"""

from __future__ import annotations

import math
import os
import random
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

SAMPLE_RATE = 44_100
BIT_DEPTH = 16
MAX_AMPLITUDE = 2 ** (BIT_DEPTH - 1) - 1


@dataclass
class Envelope:
    attack: float
    decay: float
    sustain: float
    release: float
    sustain_level: float = 0.7

    def apply(self, samples: List[float]) -> List[float]:
        total_samples = len(samples)
        attack_end = int(self.attack * SAMPLE_RATE)
        decay_end = attack_end + int(self.decay * SAMPLE_RATE)
        release_start = max(0, total_samples - int(self.release * SAMPLE_RATE))

        shaped: List[float] = []
        for i, sample in enumerate(samples):
            if i < attack_end:
                gain = i / max(1, attack_end)
            elif i < decay_end:
                gain = 1 - (1 - self.sustain_level) * (i - attack_end) / max(1, decay_end - attack_end)
            elif i < release_start:
                gain = self.sustain_level
            else:
                gain = self.sustain_level * (1 - (i - release_start) / max(1, total_samples - release_start))
            shaped.append(sample * max(0.0, min(1.0, gain)))
        return shaped


def sine_wave(frequency: float, duration: float, volume: float = 0.5) -> List[float]:
    length = int(duration * SAMPLE_RATE)
    return [volume * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE) for i in range(length)]


def noise(duration: float, volume: float = 0.3) -> List[float]:
    length = int(duration * SAMPLE_RATE)
    rand = random.random
    return [volume * (2 * rand() - 1) for _ in range(length)]


def low_pass(samples: List[float], strength: float = 0.1) -> List[float]:
    filtered: List[float] = []
    acc = 0.0
    for sample in samples:
        acc += strength * (sample - acc)
        filtered.append(acc)
    return filtered


def add_to_timeline(timeline: List[float], clip: Iterable[float], start_index: int) -> None:
    idx = start_index
    for sample in clip:
        if idx >= len(timeline):
            timeline.append(0.0)
        timeline[idx] += sample
        idx += 1


def normalize_track(track: List[float]) -> List[int]:
    if not track:
        return []
    peak = max(abs(sample) for sample in track)
    if peak == 0:
        scale = 0
    else:
        scale = MAX_AMPLITUDE / (peak * 1.1)
    return [int(max(-MAX_AMPLITUDE, min(MAX_AMPLITUDE, sample * scale))) for sample in track]


def generate_kick(duration: float = 0.3, base_freq: float = 55.0) -> List[float]:
    samples = []
    for i in range(int(duration * SAMPLE_RATE)):
        progress = i / (duration * SAMPLE_RATE)
        freq = base_freq * (1 - 0.6 * progress)
        envelope = 1 - progress
        samples.append(envelope * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) * 0.9)
    return samples


def generate_snare(duration: float = 0.25) -> List[float]:
    body = sine_wave(180, duration, volume=0.2)
    noise_part = low_pass(noise(duration, volume=0.6), strength=0.35)
    mix = [b + n for b, n in zip(body, noise_part)]
    env = Envelope(attack=0.01, decay=0.1, sustain=0.02, release=0.08)
    return env.apply(mix)


def generate_hat(duration: float = 0.12) -> List[float]:
    hiss = noise(duration, volume=0.4)
    env = Envelope(attack=0.005, decay=0.05, sustain=0.01, release=0.05, sustain_level=0.3)
    return env.apply(hiss)


def arpeggio(base_freq: float, pattern: List[int], tempo_bpm: int, bars: int) -> List[float]:
    beat_duration = 60 / tempo_bpm
    note_duration = beat_duration / 2
    clip: List[float] = []
    env = Envelope(attack=0.01, decay=0.1, sustain=0.05, release=0.15, sustain_level=0.6)
    for bar in range(bars):
        for degree in pattern:
            freq = base_freq * (2 ** (degree / 12))
            tone = env.apply(sine_wave(freq, note_duration, volume=0.35))
            clip.extend(tone)
    return clip


def build_timeline(duration_seconds: int = 30, tempo_bpm: int = 110) -> List[float]:
    total_samples = int(duration_seconds * SAMPLE_RATE)
    timeline: List[float] = [0.0] * total_samples
    beat_duration = 60 / tempo_bpm
    beats = int(duration_seconds / beat_duration)

    kick = generate_kick()
    snare = generate_snare()
    hat = generate_hat()

    for beat in range(beats):
        start = int(beat * beat_duration * SAMPLE_RATE)
        add_to_timeline(timeline, kick, start)
        if beat % 4 == 2:
            add_to_timeline(timeline, snare, start)
        for subdivision in range(2):
            hat_start = start + int(subdivision * beat_duration * SAMPLE_RATE / 2)
            add_to_timeline(timeline, hat, hat_start)

    random.seed(time.time())
    keys = [55.0, 65.4, 73.4, 82.4, 97.99]
    base_freq = random.choice(keys)
    pattern = random.choice([[0, 7, 10, 5], [0, 3, 7, 10], [0, 5, 7, 12]])
    bars = max(4, int(duration_seconds * tempo_bpm / 240))
    arp = arpeggio(base_freq, pattern, tempo_bpm, bars)
    add_to_timeline(timeline, arp, 0)

    bass_pattern = random.choice([[0, -5, -3, -7], [0, -7, -2, -9]])
    bass = arpeggio(base_freq / 2, bass_pattern, tempo_bpm // 2, bars)
    bass = [sample * 1.8 for sample in bass]
    add_to_timeline(timeline, bass, 0)

    ambience = Envelope(attack=0.2, decay=0.3, sustain=duration_seconds - 0.6, release=0.5)
    pad = ambience.apply(low_pass(noise(duration_seconds, volume=0.05), strength=0.02))
    add_to_timeline(timeline, pad, 0)

    return timeline


def save_wave(path: Path, samples: List[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(BIT_DEPTH // 8)
        wav_file.setframerate(SAMPLE_RATE)
        frames = b"".join(struct.pack("<h", sample) * 2 for sample in samples)
        wav_file.writeframes(frames)


def generate_mashup(duration_seconds: int = 30, tempo_bpm: int = 110) -> Path:
    print("✨ Creating automatic mashup...")
    timeline = build_timeline(duration_seconds, tempo_bpm)
    print("🎛️  Normalizing mix...")
    normalized = normalize_track(timeline)
    output_path = Path("output/mashup.wav")
    save_wave(output_path, normalized)
    print(f"✅ Mashup ready: {output_path} ({len(normalized) / SAMPLE_RATE:.1f}s)")
    return output_path


if __name__ == "__main__":
    generate_mashup()
