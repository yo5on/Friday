"""Generate synthetic audio for the on-phone KWS test. Does not record/play any audio."""
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core'))
import sherpa_onnx
from frosti_core import CONFIG
from frosti_core.voice import Voice, SR, _one

voice = Voice()
v = Path(CONFIG['speech']['models']) / CONFIG['speech']['voice']
if not (v / 'voices.bin').exists():  # Piper/VITS samples random noise; zero it so every run makes the same clips
    voice.tts = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=_one(v, '*.onnx'), tokens=str(v / 'tokens.txt'),
                                                   data_dir=str(v / 'espeak-ng-data'), noise_scale=0.0, noise_scale_w=0.0))))
directory = ROOT / 'data' / 'wake-tests'
directory.mkdir(exist_ok=True)
for name, text in [('frosti', 'Frosti.'), ('hey-frosti', 'Hey Frosti.'),
                   ('unrelated', 'Open Spotify on my phone.'), ('other-name', 'Hey Siri.'),
                   ('cmd-battery', "What's my battery?"), ('cmd-youtube', 'Open YouTube.'),
                   ('cmd-volume', 'Volume up.'), ('cmd-timer-five', 'Five minute timer.'),
                   ('cmd-timer-twenty-five', 'Twenty five minute timer.')]:
    audio = voice.tts.generate(text, sid=voice.speaker, speed=1.0)
    samples = np.array(audio.samples, np.float32)
    samples = np.interp(np.arange(round(len(samples) * SR / audio.sample_rate)) * audio.sample_rate / SR,
                        np.arange(len(samples)), samples).astype(np.float32)
    samples = np.concatenate([np.zeros(SR // 2, np.float32), samples, np.zeros(SR, np.float32)])
    (directory / f'{name}.pcm').write_bytes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
print('On-phone test audio prepared.')
