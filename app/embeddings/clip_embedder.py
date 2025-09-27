# app/embeddings/clip_embedder.py
import logging
import os
from io import BytesIO

import requests
import torch
import clip
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


device = "cuda" if torch.cuda.is_available() else "cpu"

model, preprocess = None, None


def load_model(force_reload: bool = False):
    global model, preprocess
    if force_reload:
        model = None
        preprocess = None
    if model is None or preprocess is None:
        # Force CLIP to use /app/.cache instead of ~/.cache
        cache_dir = "/app/.cache/clip"
        os.makedirs(cache_dir, exist_ok=True)
        m, p = clip.load("ViT-B/32", device=device, download_root=cache_dir)
        m.eval()
        # Không cần gradient cho inference
        for param in m.parameters():
            param.requires_grad_(False)
        model, preprocess = m, p
        logger.info(f"[CLIP] Loaded ViT-B/32 on {device}")


def get_embedding(image_url: str, timeout: int = 15) -> list:
    """Tải ảnh và trả về embedding đã L2-normalize (list[float], 512 chiều). Lỗi -> []."""
    try:
        # đảm bảo model đã nạp
        if model is None or preprocess is None:
            load_model()

        r = requests.get(image_url, timeout=timeout)
        r.raise_for_status()

        # Đảm bảo đóng file ảnh đúng cách
        with Image.open(BytesIO(r.content)) as img:
            # ép RGB (tránh RGBA/LA/palette)
            if img.mode != "RGB":
                img = img.convert("RGB")

            tens = preprocess(img).unsqueeze(0).to(device)
            with torch.no_grad():
                emb = model.encode_image(tens).float()
                # chuẩn hoá L2 để dùng cosine similarity
                emb = emb / emb.norm(dim=-1, keepdim=True)

        
        return emb.cpu().numpy().tolist()[0]

    except (requests.RequestException, UnidentifiedImageError) as e:
        logger.error(f"[CLIP] Image load error {image_url}: {e}")
        return []
    except Exception as e:
        logger.error(f"[CLIP] Embedding error {image_url}: {e}", exc_info=True)
        return []
