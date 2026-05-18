import frappe
import json

def run():
    # Check all Voice Speaker records
    speakers = frappe.get_all("Voice Speaker", fields=["speaker_name", "email", "embedding"])
    print(f"Total Voice Speaker records: {len(speakers)}")
    for s in speakers:
        has_emb = bool(s.get("embedding"))
        print(f"  - Name: '{s.speaker_name}' | Email: '{s.email}' | Has Embedding: {has_emb}")
