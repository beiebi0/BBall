import logging
import os
import subprocess
import tempfile
from pathlib import Path

from pipeline.models import ClipSpec

logger = logging.getLogger(__name__)


class ClipExtractor:
    """Extract and concatenate video clips using ffmpeg."""

    def __init__(self, work_dir: str | None = None):
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="bball_clips_")
        os.makedirs(self.work_dir, exist_ok=True)

    def extract_clip(
        self,
        source_path: str,
        clip_index: int,
        start_time: float,
        end_time: float,
    ) -> str:
        """
        Extract a single clip from source video using ffmpeg.
        Uses -c copy for speed (cuts at nearest keyframe).
        Returns path to extracted clip.
        """
        output_path = os.path.join(self.work_dir, f"clip_{clip_index:04d}.mp4")

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", f"{start_time:.3f}",
            "-to", f"{end_time:.3f}",
            "-i", source_path,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            logger.warning(
                "ffmpeg copy failed, falling back to re-encode: %s", result.stderr
            )
            # Fallback: re-encode for frame-exact cuts
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", f"{start_time:.3f}",
                "-to", f"{end_time:.3f}",
                "-i", source_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "aac",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)

        return output_path

    def extract_clips(
        self, source_path: str, clip_specs: list[ClipSpec]
    ) -> list[str]:
        """Extract all clips from source video. Returns list of clip paths."""
        clip_paths = []
        for i, spec in enumerate(clip_specs):
            path = self.extract_clip(source_path, i, spec.start_time, spec.end_time)
            clip_paths.append(path)
            logger.info(
                "Extracted clip %d/%d: %.1fs - %.1fs",
                i + 1,
                len(clip_specs),
                spec.start_time,
                spec.end_time,
            )
        return clip_paths

    def concatenate_clips(self, clip_paths: list[str], output_path: str) -> str:
        """Concatenate multiple clips into a single reel using ffmpeg concat demuxer."""
        if not clip_paths:
            raise ValueError("No clips to concatenate")

        if len(clip_paths) == 1:
            # Just copy the single clip
            subprocess.run(
                ["cp", clip_paths[0], output_path], check=True
            )
            return output_path

        # Create concat list file
        list_path = os.path.join(self.work_dir, "concat_list.txt")
        with open(list_path, "w") as f:
            for path in clip_paths:
                f.write(f"file '{path}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning("Concat copy failed, re-encoding: %s", result.stderr)
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "aac",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)

        return output_path

    def cleanup(self) -> None:
        """Remove temporary clip files."""
        import shutil
        if os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir)
