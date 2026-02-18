"""Motion/noise detection and Vision AI analysis for SenseCAP Watcher."""

import asyncio
import glob
import io
import logging
import os
import time
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = "/share/watcher/snapshots"
MAX_SNAPSHOTS = 100
MAX_AGE_DAYS = 7


class MonitoringService:
    """Service for motion detection, noise detection, and Vision AI analysis."""

    def __init__(self, config, llm_adapter, ha_integration):
        self.config = config
        self.llm_adapter = llm_adapter
        self.ha_integration = ha_integration

        self._last_vision_call: float = 0
        self._last_frame: Optional[bytes] = None
        self._motion_threshold: float = 0.05
        self._noise_threshold: float = 500
        self._monitoring_enabled: bool = False

    async def detect_motion(self, current_frame: bytes) -> bool:
        if self._last_frame is None:
            self._last_frame = current_frame
            return False

        try:
            current_img = Image.open(io.BytesIO(current_frame)).convert("L")
            last_img = Image.open(io.BytesIO(self._last_frame)).convert("L")

            if current_img.size != last_img.size:
                last_img = last_img.resize(current_img.size)

            current_arr = np.array(current_img, dtype=np.float32)
            last_arr = np.array(last_img, dtype=np.float32)

            diff = np.abs(current_arr - last_arr)
            pixel_change_threshold = 25
            changed_pixels = np.sum(diff > pixel_change_threshold)
            total_pixels = current_arr.size

            change_ratio = changed_pixels / total_pixels
            self._last_frame = current_frame

            motion_detected = bool(change_ratio > self._motion_threshold)
            if motion_detected:
                logger.debug(f"Motion detected: {change_ratio:.2%} pixels changed")

            return motion_detected

        except Exception as e:
            logger.error(f"Motion detection error: {e}")
            self._last_frame = current_frame
            return False

    async def detect_noise(self, audio_frame: bytes) -> bool:
        try:
            if len(audio_frame) < 2:
                return False

            samples = np.frombuffer(audio_frame, dtype=np.int16)
            if len(samples) == 0:
                return False

            rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
            noise_detected = rms > self._noise_threshold

            if noise_detected:
                logger.debug(f"Noise detected: RMS={rms:.2f}")

            return noise_detected

        except Exception as e:
            logger.error(f"Noise detection error: {e}")
            return False

    async def analyze_scene(
        self, image_bytes: bytes, force: bool = False
    ) -> Optional[dict]:
        rate_limit_seconds = 30
        current_time = time.time()
        if not force and (current_time - self._last_vision_call) < rate_limit_seconds:
            logger.debug("Vision AI rate limited")
            return None

        try:
            prompt = (
                self.config.custom_prompt
                if self.config.custom_prompt
                else "Describe what you see in this image. Focus on any people, animals, or unusual activity."
            )

            result = await self.llm_adapter.vision(image_bytes, prompt)
            self._last_vision_call = current_time

            await self.save_snapshot(image_bytes)

            logger.info(
                f"Vision AI analysis: confidence={result.get('confidence', 0):.2f}"
            )
            return result

        except Exception as e:
            logger.error(f"Vision AI analysis error: {e}")
            return None

    async def save_snapshot(self, image_bytes: bytes) -> str:
        try:
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}.jpg"
            filepath = os.path.join(SNAPSHOT_DIR, filename)

            with open(filepath, "wb") as f:
                f.write(image_bytes)

            logger.debug(f"Saved snapshot: {filepath}")
            await self._cleanup_snapshots()

            return filepath

        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            return ""

    async def _cleanup_snapshots(self):
        try:
            pattern = os.path.join(SNAPSHOT_DIR, "*.jpg")
            files = glob.glob(pattern)

            if not files:
                return

            file_info = []
            current_time = time.time()
            max_age_seconds = MAX_AGE_DAYS * 24 * 60 * 60

            for filepath in files:
                try:
                    mtime = os.path.getmtime(filepath)
                    age = current_time - mtime
                    file_info.append((filepath, mtime, age))
                except OSError:
                    continue

            for filepath, mtime, age in file_info:
                if age > max_age_seconds:
                    try:
                        os.remove(filepath)
                        logger.debug(f"Deleted old snapshot: {filepath}")
                    except OSError as e:
                        logger.warning(f"Failed to delete {filepath}: {e}")

            files = glob.glob(pattern)
            if len(files) <= MAX_SNAPSHOTS:
                return

            files_with_mtime = []
            for filepath in files:
                try:
                    mtime = os.path.getmtime(filepath)
                    files_with_mtime.append((filepath, mtime))
                except OSError:
                    continue

            files_with_mtime.sort(key=lambda x: x[1])

            files_to_delete = len(files_with_mtime) - MAX_SNAPSHOTS
            for filepath, _ in files_with_mtime[:files_to_delete]:
                try:
                    os.remove(filepath)
                    logger.debug(f"Deleted excess snapshot: {filepath}")
                except OSError as e:
                    logger.warning(f"Failed to delete {filepath}: {e}")

        except Exception as e:
            logger.error(f"Snapshot cleanup error: {e}")

    async def run_monitoring_loop(self, get_frame_callback):
        logger.info("Starting monitoring loop")

        while True:
            try:
                if not self._monitoring_enabled:
                    await asyncio.sleep(1)
                    continue

                frame = await get_frame_callback()
                if frame is None:
                    await asyncio.sleep(self.config.monitoring_interval)
                    continue

                motion_detected = await self.detect_motion(frame)

                if self.ha_integration:
                    state = "ON" if motion_detected else "OFF"
                    await self.ha_integration.publish_state(
                        "binary_sensor/motion_detected", state
                    )

                if motion_detected:
                    result = await self.analyze_scene(frame)

                    if result:
                        confidence = result.get("confidence", 0)
                        description = result.get("description", "")

                        if self.ha_integration:
                            await self.ha_integration.publish_state(
                                "sensor/last_event", description[:255]
                            )

                        if confidence >= self.config.confidence_threshold:
                            if self.ha_integration:
                                await self.ha_integration.fire_event(
                                    "alert",
                                    {
                                        "description": description,
                                        "confidence": confidence,
                                    },
                                )
                            logger.info(
                                f"Alert fired: confidence={confidence:.2f}, desc={description[:50]}..."
                            )

                await asyncio.sleep(self.config.monitoring_interval)

            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(5)

    def set_monitoring_enabled(self, enabled: bool):
        self._monitoring_enabled = enabled
        logger.info(f"Monitoring {'enabled' if enabled else 'disabled'}")

    def set_motion_threshold(self, threshold: float):
        self._motion_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Motion threshold set to {self._motion_threshold:.2%}")

    def set_noise_threshold(self, threshold: float):
        self._noise_threshold = max(0.0, threshold)
        logger.info(f"Noise threshold set to {self._noise_threshold:.2f}")
