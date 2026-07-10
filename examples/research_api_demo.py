"""
Call the research API app locally with FastAPI TestClient.

This example does not start a server and does not access the network.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from autowealth.api.research_server import app


def main():
    client = TestClient(app)
    health = client.get("/research/health").json()
    demo = client.get("/research/demo").json()
    report = client.post("/research/deepseek/mock-report", json=demo["result"]).json()

    print("Health:")
    print(json.dumps(health, ensure_ascii=False, indent=2))
    print("\nDemo target weights:")
    print(json.dumps(demo["result"]["target_weights"], ensure_ascii=False, indent=2))
    print("\nMock DeepSeek report metadata:")
    print(json.dumps(report["metadata"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
