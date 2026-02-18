import httpx
import logging


class YandexSpeechKit:
    def __init__(self, config):
        """
        Initialize Yandex SpeechKit adapter.
        :param config: Configuration object with yandex_api_key and yandex_folder_id
        """
        self.config = config
        self.client = httpx.AsyncClient(timeout=10.0)
        self.stt_url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
        self.tts_url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

    async def recognize(self, audio_bytes: bytes) -> str:
        """
        Recognize speech from audio bytes using Yandex STT API.
        :param audio_bytes: Raw audio bytes
        :return: Recognized text or empty string on failure
        """
        if not self.config.yandex_api_key or not self.config.yandex_folder_id:
            logging.warning("Yandex STT: API key or Folder ID is missing")
            return ""

        headers = {"Authorization": f"Api-Key {self.config.yandex_api_key}"}
        params = {
            "folderId": self.config.yandex_folder_id,
            "lang": "ru-RU",
        }

        try:
            response = await self.client.post(
                self.stt_url,
                headers=headers,
                params=params,
                content=audio_bytes,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result", "")
        except httpx.HTTPStatusError as e:
            logging.error(
                f"Yandex STT HTTP error: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logging.error(f"Yandex STT error: {e}")

        return ""

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize speech from text using Yandex TTS API.
        :param text: Text to synthesize
        :return: Audio bytes (oggopus) or empty bytes on failure
        """
        if not self.config.yandex_api_key or not self.config.yandex_folder_id:
            logging.warning("Yandex TTS: API key or Folder ID is missing")
            return b""

        headers = {"Authorization": f"Api-Key {self.config.yandex_api_key}"}
        data = {
            "text": text,
            "lang": "ru-RU",
            "voice": "alena",
            "folderId": self.config.yandex_folder_id,
            "format": "oggopus",
        }

        try:
            response = await self.client.post(
                self.tts_url,
                headers=headers,
                data=data,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            logging.error(
                f"Yandex TTS HTTP error: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logging.error(f"Yandex TTS error: {e}")

        return b""

    async def close(self):
        """Close the httpx client."""
        await self.client.aclose()
