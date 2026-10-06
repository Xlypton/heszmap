"""Upload a municipality's plan tiles to the R2 bucket the Worker serves them from.

    R2_ACCOUNT_ID=… R2_ACCESS_KEY_ID=… R2_SECRET_ACCESS_KEY=… python3 scripts/upload_tiles.py <key> [<key> ...]
Uploads public/tiles/<key>/**.webp to s3://heszmap-tiles/tiles/<key>/… (R2's S3 API), skipping
objects that already exist with the same size. Needs `pip install boto3`.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
BUCKET = os.environ.get("R2_BUCKET", "heszmap-tiles")


def main():
    s3 = boto3.client("s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    for key in sys.argv[1:]:
        root = ROOT / "public" / "tiles" / key
        files = sorted(root.rglob("*.webp"))
        existing = {}
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"tiles/{key}/"):
            existing.update({o["Key"]: o["Size"] for o in page.get("Contents", [])})

        def put(f):
            k = "tiles/" + str(f.relative_to(ROOT / "public" / "tiles"))
            if existing.get(k) == f.stat().st_size:
                return 0
            s3.upload_file(str(f), BUCKET, k, ExtraArgs={"ContentType": "image/webp", "CacheControl": "public, max-age=604800"})
            return 1

        with ThreadPoolExecutor(32) as ex:
            n = sum(ex.map(put, files))
        print(f"{key}: {n} uploaded, {len(files) - n} already there")


if __name__ == "__main__":
    main()
