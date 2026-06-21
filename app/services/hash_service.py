from __future__ import annotations
from pathlib import Path
from PIL import Image
import imagehash
import cv2


def image_phash(path: str | Path) -> str:
    img = Image.open(path)
    return str(imagehash.phash(img))


def video_frame_hashes(path: str | Path) -> list[str]:
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        return []
    hashes: list[str] = []
    for pct in (0.10, 0.50, 0.90):
        frame_no = max(0, min(total - 1, int(total * pct)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = cap.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        hashes.append(str(imagehash.phash(img)))
    cap.release()
    return hashes


def hamming_distance(hex_a: str, hex_b: str) -> int:
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count('1')
