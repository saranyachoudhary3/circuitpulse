from netlist_data import correct_circuit, reversed_polarity_circuit, missing_resistor_circuit
from rules import run_all_checks

print("Testing correct circuit:")
print(run_all_checks(correct_circuit))
print()

print("Testing reversed polarity circuit:")
print(run_all_checks(reversed_polarity_circuit))
print()

print("Testing missing resistor circuit:")
print(run_all_checks(missing_resistor_circuit))