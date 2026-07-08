import frappe
import json

def run():
    last_meeting = frappe.get_all("Voice Meeting", order_by="creation desc", limit=1, fields=["name", "tasks_json"])
    if last_meeting:
        print(f"Last meeting: {last_meeting[0].name}")
        print(last_meeting[0].tasks_json)
    else:
        print("No meetings found")
