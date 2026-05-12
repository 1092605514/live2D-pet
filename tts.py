from __future__ import annotations

import base64
import os
import queue
import tempfile
import threading
import winsound
from pathlib import Path
from openai import OpenAI

def _load_env():
    """Load .env from project root as fallback for MIMO_API_KEY."""
    if os.environ.get("MIMO_API_KEY"):
        return
    dotenv = Path(__file__).resolve().parent / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == "MIMO_API_KEY" and v.strip():
                    os.environ["MIMO_API_KEY"] = v.strip()
                    break

_load_env()

MIMO_API_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_VOICE = "冰糖"
DEFAULT_MODEL = "mimo-v2.5-tts"

# MiMo TTS model presets
TTS_MODELS = {
    "mimo-v2.5-tts": "预置精品音色",
    "mimo-v2.5-tts-voicedesign": "文本描述定制音色",
    "mimo-v2.5-tts-voiceclone": "音频样本复刻音色",
}

# MiMo TTS voice presets for mimo-v2.5-tts
VOICE_PRESETS = {
    "冰糖": "甜美女声（默认）",
    "茉莉": "温柔女声",
    "苏打": "活力男声",
    "白桦": "沉稳男声",
    "Mia": "英文女声",
    "Chloe": "英文女声",
    "Milo": "英文男声",
    "Dean": "英文男声",
}

# Voice design presets for mimo-v2.5-tts-voicedesign
VOICE_DESIGN_PRESETS = {
    "温柔甜美的少女": "温柔甜美的少女声音，适合日常对话",
    "活泼开朗的少年": "活泼开朗的少年声音，充满活力",
    "沉稳知性的女声": "沉稳知性的成熟女声，适合正式场合",
    "低沉磁性的男声": "低沉磁性的男声，有磁性质感",
    "可爱软萌的萝莉": "可爱软萌的萝莉声音，非常适合萌系角色",
    "冷酷帅气的御姐": "冷酷帅气的御姐声音，气场强大",
}


class MiMoTTS:
    """MiMo TTS engine with queue-based sequential playback.

    Supports three models:
    - mimo-v2.5-tts: Preset voices (use voice name like "冰糖")
    - mimo-v2.5-tts-voicedesign: Voice design (use text description as voice)
    - mimo-v2.5-tts-voiceclone: Voice clone (use audio file path as voice)
    """

    def __init__(self, voice: str = DEFAULT_VOICE, model: str = DEFAULT_MODEL, speed: float = 1.0):
        self._voice = voice
        self._model = model
        self._speed = speed
        self._client: OpenAI | None = None
        self._queue: queue.Queue[tuple[str, str | None] | None] = queue.Queue()
        self._speaking = threading.Event()
        self._worker = threading.Thread(target=self._queue_worker, daemon=True)
        self._worker.start()

    def _get_client(self) -> OpenAI | None:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("MIMO_API_KEY")
        if not api_key:
            print("[TTS] MIMO_API_KEY not set")
            return None
        self._client = OpenAI(api_key=api_key, base_url=MIMO_API_URL)
        return self._client

    def speak(self, text: str, voice: str | None = None):
        """Enqueue text for speech synthesis. Plays sequentially."""
        if not text or not text.strip():
            return
        self._queue.put((text.strip(), voice))

    def speak_segments(self, segments: list[str], voice: str | None = None):
        """Enqueue multiple text segments for sequential speech synthesis.

        Each segment is synthesized and played separately, creating natural
        pauses between sentences. Segments are added to the queue in order.
        """
        for seg in segments:
            if seg and seg.strip():
                self._queue.put((seg.strip(), voice))

    def _queue_worker(self):
        """Process TTS queue: speak one item at a time, wait for playback."""
        while True:
            item = self._queue.get()
            if item is None:
                break
            text, voice = item
            self._speaking.set()
            try:
                self._speak_sync(text, voice)
            except Exception as e:
                print(f"[TTS] Error: {e}")
            finally:
                self._speaking.clear()

    def _speak_sync(self, text: str, voice: str | None = None):
        """Synthesize and play text. Blocks until playback finishes."""
        client = self._get_client()
        if not client:
            return
        tmp_path = None
        try:
            voice_param = voice or self._voice
            audio_config: dict = {"format": "wav"}

            if self._model == "mimo-v2.5-tts-voicedesign":
                # Voice design: description in user message, text in assistant
                messages = [
                    {"role": "user", "content": voice_param},
                    {"role": "assistant", "content": text},
                ]
            elif self._model == "mimo-v2.5-tts-voiceclone":
                # Voice clone: audio sample in audio_data
                audio_b64 = None
                if voice_param:
                    audio_path = Path(voice_param)
                    if audio_path.exists():
                        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode()
                messages = [{"role": "assistant", "content": text}]
                if audio_b64:
                    audio_config["audio_data"] = audio_b64
                else:
                    audio_config["voice"] = voice_param
            else:
                # Preset voice model
                messages = [{"role": "assistant", "content": text}]
                audio_config["voice"] = voice_param

            # Add speed parameter if not default
            if self._speed != 1.0:
                audio_config["speed"] = self._speed

            completion = client.chat.completions.create(
                model=self._model,
                messages=messages,
                audio=audio_config,
            )
            message = completion.choices[0].message
            if message.audio and getattr(message.audio, "data", None):
                wav_bytes = base64.b64decode(message.audio.data)
                fd, tmp_path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                with open(tmp_path, "wb") as f:
                    f.write(wav_bytes)
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def stop(self):
        """Stop current playback and clear queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        winsound.PlaySound(None, winsound.SND_PURGE)

    def set_voice(self, voice: str):
        self._voice = voice

    def set_model(self, model: str):
        self._model = model

    def set_speed(self, speed: float):
        """Set speech speed. 1.0 = normal, <1.0 = slower, >1.0 = faster."""
        self._speed = max(0.5, min(2.0, speed))

    @property
    def current_voice(self) -> str:
        return self._voice

    @property
    def current_model(self) -> str:
        return self._model

    @property
    def current_speed(self) -> float:
        return self._speed

    @staticmethod
    def available_voices() -> dict[str, str]:
        return dict(VOICE_PRESETS)

    @staticmethod
    def available_models() -> dict[str, str]:
        return dict(TTS_MODELS)

    @staticmethod
    def voice_design_presets() -> dict[str, str]:
        return dict(VOICE_DESIGN_PRESETS)
