import os
import tempfile
import unittest
import wave

from voice_app.audio_utils import split_audio_by_silence
from voice_app.gemini_stt_client import _timeline_validation_errors


class TimelineValidationTest(unittest.TestCase):
    def test_accepts_normal_chunk_timeline(self):
        segments = [
            {"start": 0.4, "end": 4.8, "text": "Chúng ta bắt đầu cuộc họp."},
            {"start": 5.1, "end": 12.0, "text": "Tôi sẽ báo cáo phần công việc tuần này."},
        ]

        self.assertEqual(_timeline_validation_errors(segments, 15.0), [])

    def test_rejects_long_and_collapsed_tail_segments(self):
        segments = [
            {"start": 114.0, "end": 227.0, "text": "Nội dung báo cáo " * 30},
            {"start": 319.49, "end": 320.49, "text": "Đồng ý với phương án trên."},
            {"start": 320.49, "end": 320.49, "text": "Đoạn cuối vẫn còn rất nhiều nội dung."},
        ]

        errors = _timeline_validation_errors(segments, 320.49)

        self.assertTrue(any("dài bất thường" in error for error in errors))
        self.assertTrue(any("start>=end" in error for error in errors))
        self.assertTrue(any("dồn vào cuối chunk" in error for error in errors))


class AudioChunkLimitTest(unittest.TestCase):
    def test_splitter_honors_max_chunk_duration(self):
        sample_rate = 16000
        duration_sec = 4
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = os.path.join(temp_dir, "input.wav")
            with wave.open(wav_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(b"\x00\x00" * sample_rate * duration_sec)

            chunks = split_audio_by_silence(
                wav_path,
                chunk_length_sec=1.0,
                max_chunk_sec=1.5,
                output_dir=os.path.join(temp_dir, "chunks"),
            )

            self.assertGreaterEqual(len(chunks), 3)
            for chunk_path, _offset, _mappings in chunks:
                with wave.open(chunk_path, "rb") as chunk_file:
                    chunk_duration = chunk_file.getnframes() / chunk_file.getframerate()
                self.assertLessEqual(chunk_duration, 1.5)


if __name__ == "__main__":
    unittest.main()
