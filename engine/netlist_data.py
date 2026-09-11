# A netlist is just a list of connections (nets).
# Each net is a dict with component pins connected together.

correct_circuit = {
    "components": {
        "Arduino_Pin13": {"type": "power_source"},
        "R1": {"type": "resistor", "value": 220},
        "LED1": {"type": "led", "anode": "R1_Leg2", "cathode": "GND_net"},
        "Arduino_GND": {"type": "ground"},
    },
    "nets": [
        {"name": "Net_1", "from": "Arduino_Pin13", "to": "R1_Leg1"},
        {"name": "Net_2", "from": "R1_Leg2", "to": "LED1_Anode"},
        {"name": "Net_GND", "from": "LED1_Cathode", "to": "Arduino_GND"},
    ]
}

reversed_polarity_circuit = {
    "components": {
        "Arduino_Pin13": {"type": "power_source"},
        "R1": {"type": "resistor", "value": 220},
        "LED1": {"type": "led", "anode": "GND_net", "cathode": "R1_Leg2"},  # flipped!
        "Arduino_GND": {"type": "ground"},
    },
    "nets": [
        {"name": "Net_1", "from": "Arduino_Pin13", "to": "R1_Leg1"},
        {"name": "Net_2", "from": "R1_Leg2", "to": "LED1_Cathode"},
        {"name": "Net_GND", "from": "LED1_Anode", "to": "Arduino_GND"},
    ]
}

missing_resistor_circuit = {
    "components": {
        "Arduino_Pin13": {"type": "power_source"},
        "LED1": {"type": "led", "anode": "Arduino_Pin13", "cathode": "GND_net"},
        "Arduino_GND": {"type": "ground"},
    },
    "nets": [
        {"name": "Net_1", "from": "Arduino_Pin13", "to": "LED1_Anode"},  # no resistor!
        {"name": "Net_GND", "from": "LED1_Cathode", "to": "Arduino_GND"},
    ]
}