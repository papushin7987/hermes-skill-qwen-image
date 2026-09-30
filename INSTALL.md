# Установка скилла qwen-image в Hermes

1. Распаковать архив в папку скиллов Hermes (категория media):
   mkdir -p ~/.hermes/skills/media && tar -xzf qwen-image-skill.tar.gz -C ~/.hermes/skills/media/
   Должно получиться: ~/.hermes/skills/media/qwen-image/{SKILL.md, scripts/qwen_image.py, references/prompt-guide.md}
2. Указать адрес ComfyUI, если он не на этой же машине: в ~/.hermes/.env добавить COMFY_HOST=http://<ip>:8188
3. Перезапустить gateway (или начать новую сессию /new), чтобы Hermes подхватил скилл.
4. Проверка из терминала:
   python3 ~/.hermes/skills/media/qwen-image/scripts/qwen_image.py /tmp/test.png "The image is a square photorealistic photograph of a red apple on a white table. The lighting is soft window light from the left. The overall composition is minimal." --steps 25
