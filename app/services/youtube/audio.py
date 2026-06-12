from pathlib import Path
import wave

import av


class AliyunAudioNormalizer:
    def __init__(self, sample_rate: int = 16000):
        self._sample_rate = sample_rate

    def normalize(self, audio_path: str) -> str:
        source = Path(audio_path)
        if source.suffix.lower() == ".wav" and ".aliyun" in source.stem:
            return str(source)
        target = source.with_suffix(".aliyun.wav")
        if target.exists() and target.stat().st_size > 44:
            return str(target)
        self._convert(source, target)
        return str(target)

    def _convert(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        container = av.open(str(source))
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(
            format="s16",
            layout="mono",
            rate=self._sample_rate,
        )
        with wave.open(str(target), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(self._sample_rate)
            for frame in container.decode(stream):
                self._write(output, resampler.resample(frame))
            self._write(output, resampler.resample(None))
        container.close()

    @staticmethod
    def _write(output: wave.Wave_write, frames) -> None:
        if not frames:
            return
        if not isinstance(frames, list):
            frames = [frames]
        for frame in frames:
            output.writeframes(frame.to_ndarray().tobytes())
