#!/usr/bin/env python3
"""Qwen-Image 2.1 (GGUF) через ComfyUI API — драйвер low-VRAM воркфлоу (энкодер на CPU + тайловый VAE).
Только stdlib. Хост: --host или env COMFY_HOST (по умолчанию http://127.0.0.1:8188).

Примеры:
  qwen_image.py out.png "<длинный промпт-описание на английском>"
  qwen_image.py out.png "..." --ratio 3:2 --steps 40
  qwen_image.py out.png "..." --ratio 9:16 --mp 1.5 --count 3          # три варианта с разными сидами
  qwen_image.py out.png "... the character from <image1> ..." --ref hero.png
  qwen_image.py out.png "..." --neg "text, watermark" --cfg 3.5        # негатив работает ТОЛЬКО при cfg > 1
Печатает пути готовых файлов (по одному на строку). Диагностика — в stderr.
"""
import sys, os, json, time, uuid, math, argparse, mimetypes, urllib.request, urllib.parse

def log(*a):
    print(*a, file=sys.stderr, flush=True)

class Comfy:
    def __init__(self, host):
        self.host = host.rstrip("/")
    def get(self, path):
        return json.load(urllib.request.urlopen(self.host + path, timeout=60))
    def post(self, path, data):
        req = urllib.request.Request(self.host + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=60))
    def upload(self, path):
        boundary = "----qi" + uuid.uuid4().hex
        fname = os.path.basename(path)
        ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        body = b""
        for k, v in (("overwrite", "true"), ("type", "input")):
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.host + "/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        r = json.load(urllib.request.urlopen(req, timeout=120))
        return (r["subfolder"] + "/" if r.get("subfolder") else "") + r["name"]
    def options(self, node, field):
        info = self.get(f"/object_info/{node}")
        return info[node]["input"]["required"][field][0]

def pick(files, prefer, must):
    cands = [f for f in files if must in f.lower()]
    for p in prefer:
        for f in cands:
            if p.lower() in f.lower():
                return f
    return cands[0] if cands else None

def size_for(ratio, mp):
    a, b = (float(x) for x in ratio.split(":"))
    h = math.sqrt(mp * 1e6 / (a / b)); w = h * a / b
    r = lambda v: max(256, int(round(v / 32)) * 32)
    return r(w), r(h)

def build(m, prompt, neg, w, h, steps, seed, cfg, ref_names, enc_device, tile):
    g = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": m["unet"]}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": m["clip"], "type": "qwen_image", "device": enc_device}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": m["vae"]}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["2", 0], "prompt": prompt, "negative_prompt": neg, "resolution": int(round(math.sqrt(w * h) / 32)) * 32}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "qwen21"}},
    }
    if tile > 0:
        g["7"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["6", 0], "vae": ["3", 0], "tile_size": tile, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
    else:
        g["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}}
    if ref_names:
        g["4"]["inputs"]["vae"] = ["3", 0]
        for i, name in enumerate(ref_names, 1):
            g[f"r{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
            g["4"]["inputs"][f"images.image_{i}"] = [f"r{i}", 0]
        g["6"]["inputs"]["latent_image"] = ["4", 2]
    else:
        g["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
        g["6"]["inputs"]["latent_image"] = ["5", 0]
    return g

def run(c, wf, out, timeout=1800):
    r = c.post("/prompt", {"prompt": wf, "client_id": uuid.uuid4().hex})
    if "prompt_id" not in r:
        raise SystemExit("ComfyUI отклонил граф: " + json.dumps(r, ensure_ascii=False)[:1200])
    pid = r["prompt_id"]; t0 = time.time()
    while time.time() - t0 < timeout:
        h = c.get(f"/history/{pid}")
        if pid in h:
            for node in h[pid].get("outputs", {}).values():
                for im in node.get("images", []):
                    q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")})
                    data = urllib.request.urlopen(c.host + "/view?" + q, timeout=120).read()
                    with open(out, "wb") as f:
                        f.write(data)
                    return out, time.time() - t0
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit("Ошибка выполнения: " + json.dumps(st, ensure_ascii=False)[:1200])
        time.sleep(1)
    raise SystemExit("Таймаут ожидания генерации")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="куда сохранить PNG (при --count N добавляется _1.._N)")
    ap.add_argument("prompt", help="описание кадра на английском (см. SKILL.md)")
    ap.add_argument("--neg", default="", help="негатив; действует только при --cfg > 1")
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--steps", type=int, default=30, help="25 черновик, 30 обычно, 40 чистовой/текст")
    ap.add_argument("--ratio", default="1:1", help="1:1, 3:2, 2:3, 4:3, 3:4, 16:9, 9:16, 21:9 …")
    ap.add_argument("--mp", type=float, default=1.0, help="мегапиксели: 1.0 по умолчанию, 1.5–2 для финала (дольше, больше VRAM)")
    ap.add_argument("--size", help="явно WxH (кратно 32), перекрывает --ratio/--mp")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--count", type=int, default=1, help="сколько вариантов (сид+i)")
    ap.add_argument("--ref", action="append", default=[], help="референс-картинка → <image1>, <image2>…")
    ap.add_argument("--model", help="имя GGUF в ComfyUI/models/unet (по умолчанию авто: Q5_K_M > Q6_K > Q4_K_M > Q8_0)")
    ap.add_argument("--encoder-device", choices=["cpu", "default"], default="cpu", help="cpu = энкодер в ОЗУ (12 ГБ карты); default = в VRAM (быстрее, 16+ ГБ)")
    ap.add_argument("--tile", type=int, default=256, help="тайл VAE-декода; 0 = без тайлинга")
    ap.add_argument("--host", default=os.environ.get("COMFY_HOST", "http://127.0.0.1:8188"))
    a = ap.parse_args()

    c = Comfy(a.host)
    try:
        unets = c.options("UnetLoaderGGUF", "unet_name")
    except Exception as e:
        raise SystemExit(f"ComfyUI недоступен на {a.host} или нет ноды UnetLoaderGGUF (leejet/ComfyUI-GGUF): {e}")
    unet = a.model or pick(unets, ["Q5_K_M", "Q6_K", "Q4_K_M", "Q8_0", "Q5", "Q4"], "qwen-image")
    clip = pick(c.options("CLIPLoader", "clip_name"), ["int8_convrot", "qwen3vl"], "qwen3vl")
    vae = pick(c.options("VAELoader", "vae_name"), ["qwen_image_2.1", "qwen_image"], "qwen_image")
    if not (unet and clip and vae):
        raise SystemExit(f"Не найдены модели: unet={unet} clip={clip} vae={vae}. Список unet: {unets}")
    m = {"unet": unet, "clip": clip, "vae": vae}
    if a.size:
        w, h = (int(x) for x in a.size.lower().split("x"))
    else:
        w, h = size_for(a.ratio, a.mp)
    refs = [c.upload(p) for p in a.ref]
    if a.neg and a.cfg <= 1.0:
        log("ВНИМАНИЕ: --neg игнорируется при cfg 1.0; поставь --cfg 3.5, если негатив нужен")
    seed0 = a.seed if a.seed is not None else int.from_bytes(os.urandom(4), "big")
    log(f"model={unet} clip={clip} enc={a.encoder_device} size={w}x{h} steps={a.steps} cfg={a.cfg} refs={refs or '-'}")
    base, ext = os.path.splitext(a.out); ext = ext or ".png"
    for i in range(a.count):
        seed = (seed0 + i) % (2**32)
        out = a.out if a.count == 1 else f"{base}_{i+1}{ext}"
        wf = build(m, a.prompt, a.neg, w, h, a.steps, seed, a.cfg, refs, a.encoder_device, a.tile)
        path, dt = run(c, wf, out)
        log(f"seed={seed} {dt:.0f}s")
        print(path, flush=True)

if __name__ == "__main__":
    main()
