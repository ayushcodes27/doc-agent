import subprocess
import os
import time

edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
images_dir = os.path.join(base_dir, "images")

targets = [
    {
        "name": "image1.png",
        "url": "http://127.0.0.1:8501",
        "window": "1280,880",
        "budget": 6000,
        "desc": "Upload Dashboard",
    },
    {
        "name": "image2.png",
        "url": "http://127.0.0.1:8501?demo=1",
        "window": "1280,1050",
        "budget": 6000,
        "desc": "Extraction & Compliance",
    },
    {
        "name": "image3.png",
        "url": "http://127.0.0.1:8501?demo=1&expand_audit=1",
        "window": "1280,2550",
        "budget": 8000,
        "desc": "Agent Audit Trail",
    },
]

for t in targets:
    out_path = os.path.join(images_dir, t["name"])
    print(f"[+] Capturing {t['desc']} -> {t['name']} (Window: {t['window']})...")
    tmp_user_data = os.path.join(base_dir, ".temp_edge_profile")
    cmd = [
        edge_path,
        "--headless=new",
        "--disable-gpu",
        f"--user-data-dir={tmp_user_data}",
        f"--virtual-time-budget={t['budget']}",
        f"--window-size={t['window']}",
        f"--screenshot={out_path}",
        t["url"],
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    time.sleep(1)
    if os.path.exists(out_path):
        size = os.path.getsize(out_path)
        print(f"    Saved: {out_path} ({size:,} bytes)")
    else:
        print(f"    [X] Failed to capture {t['name']}")

print("\n[+] All UI screenshots updated successfully!")
