def check_missing_resistor(circuit):
    """Flag if an LED has no resistor anywhere in its components."""
    has_led = any(c["type"] == "led" for c in circuit["components"].values())
    has_resistor = any(c["type"] == "resistor" for c in circuit["components"].values())
    if has_led and not has_resistor:
        return {"status": "fail", "component": "LED1", "issue": "missing current-limiting resistor"}
    return {"status": "pass"}

def check_polarity(circuit):
    """Flag if LED anode connects toward ground instead of toward power."""
    for name, comp in circuit["components"].items():
        if comp["type"] == "led":
            if "GND" in comp.get("anode", ""):
                return {"status": "fail", "component": name, "issue": "reversed polarity"}
    return {"status": "pass"}

def check_short_circuit(circuit):
    """Flag if power connects directly to ground with nothing between them."""
    for net in circuit["nets"]:
        from_comp = circuit["components"].get(net["from"].split("_")[0], {})
        if from_comp.get("type") == "power_source" and "GND" in net["to"]:
            return {"status": "fail", "component": net["name"], "issue": "direct short circuit"}
    return {"status": "pass"}

def run_all_checks(circuit):
    """Run every rule and collect results."""
    results = [
        check_missing_resistor(circuit),
        check_polarity(circuit),
        check_short_circuit(circuit),
    ]
    failures = [r for r in results if r["status"] == "fail"]
    if failures:
        return failures
    return [{"status": "pass", "message": "circuit looks safe"}]