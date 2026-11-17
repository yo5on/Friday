"""Wake-word check using installed speech models, without playing or recording audio."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from friday_core import CONFIG

SPEEDS = (0.9, 0.95, 1.0, 1.05, 1.1)  # Piper varies run to run anyway; speeds spread the takes further


@unittest.skipUnless(Path(CONFIG['speech']['models']).exists(), 'Speech models not installed')
class WakeWord(unittest.TestCase):
    def test_name_and_greeting_wake_but_unrelated_speech_does_not(self):
        import numpy as np
        from friday_core.voice import Voice, Listener, SR
        voice = Voice()

        def wakes(text, speed):
            audio = voice.tts.generate(text, sid=voice.speaker, speed=speed)
            samples = np.array(audio.samples, dtype=np.float32)
            samples = np.interp(np.arange(round(len(samples) * SR / audio.sample_rate)) *
                                audio.sample_rate / SR, np.arange(len(samples)), samples).astype(np.float32)
            samples = np.concatenate([np.zeros(SR // 2, np.float32), samples, np.zeros(SR, np.float32)])
            listener = Listener(voice)
            for i in range(0, len(samples), 1600):
                event = listener.feed((np.clip(samples[i:i + 1600], -1, 1) * 32767).astype('<i2').tobytes())
                if event and event[0] == 'wake':
                    return True
            return False

        # measured 2026-11-13 on Piper alan: "Hey Friday" wakes on most takes, the bare name on only ~2/3,
        # so a single take is a coin flip; these minimums still fail if the detector stops hearing the name
        for text, minimum in [('Hey Friday.', 3), ('Friday.', 1),
                              ('Open Spotify on my phone.', 0), ('Hey Siri.', 0)]:
            with self.subTest(text=text):
                hits = sum(wakes(text, s) for s in SPEEDS)
                if minimum:
                    self.assertGreaterEqual(hits, minimum)
                else:
                    self.assertEqual(hits, 0)
