"""Save the default ticket pipeline and its first stage to config/hubspot.json. Run: python -m scripts.setup_hubspot"""

import json

import httpx

import config

HUBSPOT_API = "https://api.hubapi.com"
CONFIG_FILE = config.ROOT / "config" / "hubspot.json"


def main() -> None:
    headers = {"Authorization": f"Bearer {config.HUBSPOT_TOKEN}"}
    response = httpx.get(
        f"{HUBSPOT_API}/crm/v3/pipelines/tickets", headers=headers, timeout=15
    )
    if response.is_error:
        raise RuntimeError(
            f"HubSpot pipelines -> {response.status_code}: {response.text[:300]}"
        )
    pipelines = response.json()["results"]
    if not pipelines:
        raise RuntimeError("HubSpot returned no ticket pipelines.")
    # The default pipeline is the first one in display order, and new tickets go to its first stage.
    pipeline = min(pipelines, key=lambda p: p["displayOrder"])
    stage = min(pipeline["stages"], key=lambda s: s["displayOrder"])
    settings = {
        "pipeline_id": pipeline["id"],
        "pipeline_label": pipeline["label"],
        "stage_id": stage["id"],
        "stage_label": stage["label"],
    }
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(
        f"{len(pipelines)} ticket pipeline(s); saved to {CONFIG_FILE.relative_to(config.ROOT)}:"
    )
    print(json.dumps(settings, indent=2))


if __name__ == "__main__":
    main()
