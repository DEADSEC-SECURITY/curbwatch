"""Cache real Syracuse street geometry; this does not import public ticket records."""

import json
import httpx
from . import config

SOURCE = config.STREETS_SOURCE_URL


def download_streets():
    features = []
    with httpx.Client(timeout=45) as client:
        count = client.get(
            SOURCE + "/query", params={"where": "1=1", "returnCountOnly": "true", "f": "json"}
        )
        count.raise_for_status()
        expected = count.json()["count"]
        for offset in range(0, expected, 1000):
            response = client.get(
                SOURCE + "/query",
                params={
                    "where": "1=1",
                    "outFields": "FID,STREET_NAM,FROM_STREE,TO_STREET,BLOCK",
                    "outSR": "4326",
                    "f": "geojson",
                    "resultOffset": offset,
                    "resultRecordCount": 1000,
                    "orderByFields": "FID ASC",
                },
            )
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                raise RuntimeError(result["error"])
            for feature in result["features"]:
                p = feature["properties"]
                feature["properties"] = {
                    "name": p["STREET_NAM"],
                    "from": p["FROM_STREE"],
                    "to": p["TO_STREET"],
                    "block": p["BLOCK"],
                }
                features.append(feature)
    if len(features) != expected:
        raise RuntimeError(f"Incomplete street download: {len(features)} of {expected}")
    path = config.STREETS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    temporary.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "source": SOURCE,
                "attribution": config.STREETS_ATTRIBUTION,
                "features": features,
            },
            separators=(",", ":"),
        )
    )
    temporary.replace(path)
    print(f"Saved {len(features)} verified street segments ({path.stat().st_size:,} bytes)")
    print("Example street names:", [f["properties"]["name"] for f in features[:8]])


if __name__ == "__main__":
    download_streets()
