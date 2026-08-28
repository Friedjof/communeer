"""WPPConnect Server spike: authenticate a session and dump raw community/group
JSON so we can empirically check what data is actually reachable via REST.

Read-only. Does not call any promote/demote/remove/add endpoint.

Usage:
    uv run poc/whatsapp/explore.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
OUTPUT_DIR = HERE / "output"

SESSION = os.environ.get("SESSION_NAME", "communeer-poc")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:21465")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def dump(name: str, data: object) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  wrote {path.relative_to(HERE)}")


def save_qrcode(data_url: str) -> None:
    _, _, b64 = data_url.partition(",")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "qrcode.png"
    path.write_bytes(base64.b64decode(b64))
    print(f"\nQR code saved to {path} — scan it with the target WhatsApp account.")
    print("(Use a secondary/test account, not your primary daily-driver number.)\n")


def generate_token(client: httpx.Client) -> str:
    resp = client.post(f"/api/{SESSION}/{SECRET_KEY}/generate-token")
    resp.raise_for_status()
    body = resp.json()
    token = body.get("token") or body.get("Token") or body.get("result")
    if not token:
        raise RuntimeError(f"could not find token in response: {body}")
    return token


def start_session(client: httpx.Client) -> None:
    resp = client.post(f"/api/{SESSION}/start-session", json={"waitQrCode": False})
    resp.raise_for_status()
    print("start-session:", resp.json())


def wait_for_connection(client: httpx.Client, timeout_s: int = 180) -> None:
    deadline = time.monotonic() + timeout_s
    printed_qr = False
    last_status = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/{SESSION}/status-session")
        resp.raise_for_status()
        body = resp.json()
        status = body.get("status")

        if status != last_status:
            print("status:", status)
            last_status = status

        if status == "CONNECTED":
            return

        qrcode = body.get("qrcode")
        if qrcode and not printed_qr:
            save_qrcode(qrcode)
            printed_qr = True

        time.sleep(3)

    raise TimeoutError(f"session did not reach CONNECTED within {timeout_s}s")


def find_admin_community_id(all_groups: list[dict]) -> str | None:
    for group in all_groups:
        meta = group.get("groupMetadata") or group
        if meta.get("isParentGroup"):
            return meta.get("id", {}).get("_serialized") or group.get("id")
    return None


def summarize_all_groups(all_groups: list[dict]) -> None:
    print("\n--- all-groups summary ---")
    parents = []
    subgroups_by_parent: dict[str, list[dict]] = {}

    for group in all_groups:
        meta = group.get("groupMetadata") or group
        parent_id = meta.get("parentGroup")
        if meta.get("isParentGroup"):
            parents.append(group)
        elif parent_id:
            subgroups_by_parent.setdefault(parent_id, []).append(group)

    if not parents and not subgroups_by_parent:
        print(
            "No isParentGroup/parentGroup fields found anywhere in the response.\n"
            "=> all-groups does NOT carry community structure. See FINDINGS.md."
        )
        return

    for parent in parents:
        meta = parent.get("groupMetadata") or parent
        parent_id = meta.get("id", {}).get("_serialized") or parent.get("id")
        name = meta.get("subject") or parent.get("name") or "?"
        print(f"Community: {name} ({parent_id})")

        subgroups = subgroups_by_parent.get(parent_id, [])
        for sub in subgroups:
            sub_meta = sub.get("groupMetadata") or sub
            sub_id = sub_meta.get("id", {}).get("_serialized") or sub.get("id")
            sub_name = sub_meta.get("subject") or sub.get("name") or "?"
            announce = sub_meta.get("announce", False)
            size = sub_meta.get("size", len(sub_meta.get("participants", [])))
            pending = len(sub_meta.get("pendingParticipants", []) or [])
            tag = " [announcement group]" if announce else ""
            print(f"  - {sub_name} ({sub_id}): {size} members, {pending} pending{tag}")


def main() -> None:
    load_dotenv(HERE / ".env")

    global SESSION, SECRET_KEY, BASE_URL
    SESSION = os.environ.get("SESSION_NAME", SESSION)
    SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY)
    BASE_URL = os.environ.get("BASE_URL", BASE_URL)

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        print(f"Generating token for session '{SESSION}'...")
        token = generate_token(client)
        client.headers["Authorization"] = f"Bearer {token}"

        print("Starting session...")
        start_session(client)

        print("Waiting for QR scan / connection...")
        wait_for_connection(client)
        print("Connected.\n")

        print("Fetching all-groups (deprecated route, main thing under test)...")
        all_groups_resp = client.get(f"/api/{SESSION}/all-groups")
        all_groups_resp.raise_for_status()
        all_groups_body = all_groups_resp.json()
        dump("all-groups", all_groups_body)

        all_groups = all_groups_body.get("response", all_groups_body)
        if not isinstance(all_groups, list):
            print(f"  unexpected shape, got: {type(all_groups)}")
            all_groups = []

        summarize_all_groups(all_groups)

        community_id = find_admin_community_id(all_groups)
        if community_id:
            print(f"\nFetching community-participants for {community_id}...")
            resp = client.get(f"/api/{SESSION}/community-participants/{community_id}")
            dump("community-participants", resp.json() if resp.status_code == 200 else {"status_code": resp.status_code, "text": resp.text})
        else:
            print("\nNo community found in all-groups — skipping community-participants.")

        subgroup = next(
            (
                g
                for g in all_groups
                if (g.get("groupMetadata") or g).get("parentGroup")
            ),
            None,
        )
        if subgroup:
            sub_meta = subgroup.get("groupMetadata") or subgroup
            group_id = sub_meta.get("id", {}).get("_serialized") or subgroup.get("id")
            print(f"\nFetching group-info/group-members/group-admins for {group_id}...")
            for name, path in [
                ("group-info", f"/api/{SESSION}/group-info/{group_id}"),
                ("group-members", f"/api/{SESSION}/group-members/{group_id}"),
                ("group-admins", f"/api/{SESSION}/group-admins/{group_id}"),
            ]:
                resp = client.get(path)
                dump(name, resp.json() if resp.status_code == 200 else {"status_code": resp.status_code, "text": resp.text})
        else:
            print("\nNo subgroup found — skipping per-group endpoint checks.")

    print("\nDone. Inspect poc/whatsapp/output/*.json and write FINDINGS.md.")


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPStatusError, TimeoutError, RuntimeError) as exc:
        print(f"\nSpike failed: {exc}", file=sys.stderr)
        sys.exit(1)
