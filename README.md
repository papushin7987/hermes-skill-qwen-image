# hermes-skill-qwen-image

Скилл для [Hermes Agent](https://github.com/NousResearch/hermes-agent): генерация картинок локально через ComfyUI + Qwen-Image 2.1 (GGUF, low-VRAM воркфлоу под 12 ГБ карты). Учит агента писать промпты по официальному методу Qwen («опиши готовый кадр как наблюдатель») и содержит драйвер `scripts/qwen_image.py`.

## Установка
```
mkdir -p ~/.hermes/skills/media
git clone https://github.com/papushin7987/hermes-skill-qwen-image ~/.hermes/skills/media/qwen-image
```
Если ComfyUI не на этой машине — в `~/.hermes/.env` добавить `COMFY_HOST=http://<ip>:8188`. Затем перезапустить gateway (`systemctl --user restart hermes-gateway` или `sudo systemctl restart hermes-gateway`) либо начать новую сессию.

Подробности — `INSTALL.md`, метод промпта — `SKILL.md`, примеры — `references/prompt-guide.md`.

## Требования на стороне ComfyUI
- нода `leejet/ComfyUI-GGUF`
- `models/unet/qwen-image-2.1-*.gguf` (Q5_K_M для 12 ГБ), `models/text_encoders/qwen3vl_8b_int8_convrot.safetensors`, `models/vae/qwen_image_2.1_vae_bf16.safetensors` — репозиторий `abenzerps/Qwen-Image-2.1-Uncensored-GGUF` или `Comfy-Org/Qwen-Image-2.1`
