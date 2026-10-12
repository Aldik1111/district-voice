"""Explicit, resumable download of public model assets. Never reads appeal data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import httpx

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = ["config.json", "modules.json", "1_Pooling/config.json", "sentence_bert_config.json",
         "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json",
         "sentencepiece.bpe.model", "model.safetensors"]
BLOCK = 8 * 1024 * 1024


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "backend/models/multilingual-e5-small")
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        response = client.get(f"https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true")
        response.raise_for_status()
        metadata = {item["rfilename"]: item for item in response.json()["siblings"]}
    manifest = {}
    for name in FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        size = metadata[name]["size"]
        expected = metadata[name].get("lfs", {}).get("sha256")
        if target.exists() and target.stat().st_size == size and (not expected or digest(target) == expected):
            print(f"Cached: {name}", flush=True)
            manifest[name] = {"size": size, "sha256": digest(target)}
            continue
        partial = target.with_suffix(target.suffix + ".part")
        chunks = target.parent / (target.name + ".chunks")
        chunks.mkdir(exist_ok=True)
        # Preserve complete blocks from an interrupted older sequential download.
        if partial.exists():
            with partial.open("rb") as source:
                for offset in range(0, partial.stat().st_size - BLOCK + 1, BLOCK):
                    piece = chunks / str(offset)
                    block = source.read(BLOCK)
                    if not piece.exists():
                        piece.write_bytes(block)

        def download_block(start):
            end = min(start + BLOCK, size) - 1
            piece = chunks / str(start)
            length = end - start + 1
            if piece.exists() and piece.stat().st_size == length:
                return piece
            for attempt in range(5):
                try:
                    url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}?download=true&block={start}&attempt={attempt}"
                    with httpx.Client(timeout=httpx.Timeout(180, read=180), follow_redirects=True) as client:
                        with client.stream("GET", url, headers={"Range": f"bytes={start}-{end}"}) as response:
                            response.raise_for_status()
                            if response.status_code == 206:
                                if response.headers.get("content-range") != f"bytes {start}-{end}/{size}":
                                    raise ValueError("Unexpected content range")
                            elif start != 0 or length != size:
                                raise ValueError("Server did not honor requested range")
                            with piece.open("wb") as output:
                                received = 0
                                for block in response.iter_bytes(256 * 1024):
                                    received += len(block)
                                    if received > length:
                                        raise ValueError("Unexpected response length")
                                    output.write(block)
                    if piece.stat().st_size != length:
                        raise ValueError("Incomplete block")
                    print(f"Downloaded: {name} bytes {start}-{end}", flush=True)
                    return piece
                except (httpx.HTTPError, ValueError):
                    if attempt == 4:
                        raise
                    time.sleep(1 + attempt)
            raise RuntimeError("Block download failed")

        with ThreadPoolExecutor(max_workers=6) as pool:
            pieces = list(pool.map(download_block, range(0, size, BLOCK)))
        with partial.open("wb") as output:
            for piece in pieces:
                with piece.open("rb") as source:
                    while block := source.read(1024 * 1024):
                        output.write(block)
        actual = digest(partial)
        if partial.stat().st_size != size or (expected and actual != expected):
            raise RuntimeError(f"Checksum/size mismatch: {name}. Remove its .chunks directory before retrying.")
        partial.replace(target)
        for piece in pieces:
            piece.unlink()
        chunks.rmdir()
        manifest[name] = {"size": size, "sha256": actual}
        print(f"Verified: {name}", flush=True)
    (destination / "MODEL-MANIFEST.json").write_text(json.dumps({"model_id": MODEL, "revision": REVISION, "files": manifest}, indent=2), encoding="utf-8")
    print("Local model assets ready. Restart backend and verify the actual algorithm of a completed run.", flush=True)


if __name__ == "__main__":
    main()
