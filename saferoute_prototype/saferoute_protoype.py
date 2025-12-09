"""
SafeRoute Prototype for LM Studio + Edge Gallery
Author: [Your Name]
Description:
A functional prototype demonstrating LM Studio local AI reasoning and
Edge Gallery fallback for offline evacuation routing and SOS coordination.
"""

import json
import random
import time

# ========== MOCK ENVIRONMENT ========== #
# Simulate offline mode and LM Studio model response

OFFLINE_MODE = True  # Toggle offline fallback
ACTIVE_MODEL = "LMStudio-Edge-AI-v1"
SAFE_AREAS = ["North Ridge Shelter", "East High Gym", "City Hall", "Hilltop Church"]

# Hazard map mock data
hazard_data = {
    "flood_zones": ["Downtown Riverfront", "Harbor District"],
    "closed_roads": ["Main St", "Bridge Ave", "Riverside Blvd"],
    "power_outages": ["Industrial Park", "West Valley"],
    "sos_pings": []
}

# ========== CORE CLASSES ========== #
class SafeRouteAI:
    def __init__(self, offline=OFFLINE_MODE):
        self.offline = offline
        print(f"[INIT] SafeRoute AI started with model: {ACTIVE_MODEL}")
        print("[STATUS] Offline mode active" if offline else "[STATUS] Online edge mode active")

    def generate_route(self, start="User Location"):
        destination = random.choice(SAFE_AREAS)
        hazards_nearby = [hz for hz, zones in hazard_data.items() if "Downtown" in str(zones)]
        route = {
            "start": start,
            "destination": destination,
            "hazards": hazards_nearby,
            "path": ["User Location", "Hill St", "Maple Ave", destination]
        }
        return route

    def send_sos(self, survivors=1, location="User Location"):
        sos_id = f"SOS-{random.randint(1000,9999)}"
        hazard_data["sos_pings"].append({
            "id": sos_id,
            "location": location,
            "survivors": survivors,
            "timestamp": time.ctime()
        })
        return {"status": "SOS Sent", "id": sos_id}

    def summarize_status(self):
        return {
            "mode": "Offline" if self.offline else "Edge Connected",
            "active_model": ACTIVE_MODEL,
            "hazard_summary": {
                "flood_zones": len(hazard_data["flood_zones"]),
                "closed_roads": len(hazard_data["closed_roads"]),
                "power_outages": len(hazard_data["power_outages"]),
                "active_sos": len(hazard_data["sos_pings"])
            }
        }

# ========== SIMULATION FUNCTIONS ========== #
def simulate_user_session():
    ai = SafeRouteAI(offline=OFFLINE_MODE)

    print("\n--- CURRENT STATUS ---")
    print(json.dumps(ai.summarize_status(), indent=2))

    print("\n--- GENERATING EVACUATION ROUTE ---")
    route = ai.generate_route()
    print(json.dumps(route, indent=2))

    print("\n--- SENDING SOS BEACON ---")
    sos_response = ai.send_sos(survivors=3)
    print(json.dumps(sos_response, indent=2))

    print("\n--- UPDATED STATUS ---")
    print(json.dumps(ai.summarize_status(), indent=2))

# ========== MAIN EXECUTION ========== #
if __name__ == "__main__":
    simulate_user_session()
