# SenseCAP Watcher Add-on for Home Assistant

Integrate your SenseCAP Watcher with Home Assistant using Vision AI and Voice capabilities.

## Features

- **16 Home Assistant Entities**: Full control and monitoring through binary sensors, switches, and selects.
- **Vision AI Analysis**: Real-time scene analysis using Claude or local Ollama models.
- **Voice Interaction**: Text-to-speech and speech-to-text integration using Yandex SpeechKit.
- **Monitoring Mode**: Automatic periodic scene analysis with movement and noise detection.
- **OTA Updates**: Built-in support for firmware updates.
- **Customizable Display**: Control the Watcher's display with custom messages and emotions.

## Requirements

- Home Assistant with MQTT Broker installed and configured.
- SenseCAP Watcher device.
- API Key for Claude (via proxy) or a local Ollama instance.
- (Optional) Yandex Cloud API Key for voice features.

## Installation

1. Add this repository to your Home Assistant Add-on Store.
2. Search for "SenseCAP Watcher AI" and click **Install**.
3. Configure the add-on options (see below).
4. Start the add-on.

## Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `llm_provider` | string | `claude` | LLM provider to use (`claude` or `ollama`). |
| `claude_proxy_url` | url | `https://yunyi.cfd/claude` | Primary URL for Claude API proxy. |
| `claude_proxy_key` | string | | API Key for primary Claude proxy. |
| `claude_fallback_url` | url | `https://code.mmkg.cloud` | Fallback URL for Claude API. |
| `claude_fallback_key` | string | | API Key for fallback Claude proxy. |
| `claude_model` | string | `claude-sonnet-4-5-20250929` | Model ID for Claude. |
| `ollama_url` | url | `http://localhost:11434` | URL for local Ollama instance. |
| `ollama_model` | string | `llama3.2` | Text model for Ollama. |
| `ollama_vision_model` | string | `llava` | Vision model for Ollama. |
| `yandex_api_key` | string | | Yandex Cloud API Key for SpeechKit. |
| `yandex_folder_id` | string | | Yandex Cloud Folder ID. |
| `monitoring_interval` | integer | 60 | Interval in seconds for periodic monitoring. |
| `confidence_threshold` | integer | 70 | Threshold for AI detection confidence (0-100). |
| `custom_prompt` | string | `Опиши что происходит...` | Custom prompt for scene analysis. |
| `websocket_port` | port | 8080 | Port for Watcher communication. |
| `ota_port` | port | 8081 | Port for OTA updates. |
| `log_level` | string | `info` | Logging level (`debug`, `info`, `warning`, `error`). |

## Usage

### Home Assistant Entities

The add-on creates several entities in Home Assistant:

- `switch.sensecap_watcher_monitoring`: Enable/disable AI monitoring.
- `switch.sensecap_watcher_display_power`: Turn the device screen on/off.
- `sensor.sensecap_watcher_scene_description`: The latest AI analysis of the scene.
- `select.sensecap_watcher_display_mode`: Switch between different display modes.
- `select.sensecap_watcher_emotion`: Set the current emotion on the display.

### Voice Commands

You can send text to the device to be spoken using the Yandex SpeechKit integration. The device also sends recognized speech events to Home Assistant.

### Vision AI

When monitoring is enabled, the Watcher periodically sends snapshots for analysis. Results are published to Home Assistant and can trigger automations.

## Troubleshooting

- **MQTT connection failed**: Ensure the MQTT add-on is running and configured in Home Assistant.
- **AI Analysis error**: Check your API keys and internet connection for Claude, or ensure Ollama is accessible.
- **Device not connecting**: Verify the Watcher is configured with the correct IP and port of the add-on.

## License

MIT License. See LICENSE for details.
