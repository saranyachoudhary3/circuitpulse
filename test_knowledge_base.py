import unittest
from intelligence.knowledge import (
    BREADBOARD_KNOWLEDGE,
    ARDUINO_KNOWLEDGE,
    COMPONENT_KNOWLEDGE,
    IC_KNOWLEDGE,
    CIRCUIT_PATTERNS,
    ADVANCED_MODULES,
    DEBUGGING_METHODOLOGY,
    get_full_knowledge_base
)

class KnowledgeBaseTests(unittest.TestCase):
    
    def test_get_full_knowledge_base_returns_nonempty_string(self):
        full_kb = get_full_knowledge_base()
        self.assertIsInstance(full_kb, str)
        self.assertTrue(len(full_kb) > 0)
        
    def test_knowledge_base_contains_all_sections(self):
        full_kb = get_full_knowledge_base()
        key_phrases = [
            'BREADBOARD TOPOLOGY',
            'ARDUINO UNO PIN REFERENCE',
            'LED:',
            'RESISTOR:',
            '555 TIMER',
            'VOLTAGE DIVIDER',
            'L298N MOTOR DRIVER',
            'SYSTEMATIC DEBUGGING'
        ]
        for phrase in key_phrases:
            self.assertIn(phrase.lower(), full_kb.lower(), f"Missing phrase: {phrase}")
            
    def test_breadboard_knowledge_covers_row_column_topology(self):
        kb_lower = BREADBOARD_KNOWLEDGE.lower()
        self.assertIn("row", kb_lower)
        self.assertIn("column", kb_lower)
        self.assertIn("center gap", kb_lower)
        self.assertIn("power rail", kb_lower)
        
    def test_arduino_knowledge_covers_all_board_types(self):
        kb_lower = ARDUINO_KNOWLEDGE.lower()
        self.assertIn("uno", kb_lower)
        self.assertIn("nano", kb_lower)
        self.assertIn("mega", kb_lower)
        self.assertIn("esp32", kb_lower)
        
    def test_component_knowledge_covers_polarity_components(self):
        kb_lower = COMPONENT_KNOWLEDGE.lower()
        self.assertIn("anode", kb_lower)
        self.assertIn("cathode", kb_lower)
        self.assertIn("capacitor", kb_lower)
        self.assertIn("diode", kb_lower)
        
    def test_ic_knowledge_includes_common_chips(self):
        kb_lower = IC_KNOWLEDGE.lower()
        chips = ['555', 'l293d', 'lm7805', '74hc595', 'lm358']
        for chip in chips:
            self.assertIn(chip, kb_lower)
            
    def test_debugging_methodology_covers_six_check_categories(self):
        kb_lower = DEBUGGING_METHODOLOGY.lower()
        categories = [
            'power check', 
            'ground check', 
            'connection tracing', 
            'component validation', 
            'signal path', 
            'common mistakes'
        ]
        for category in categories:
            self.assertIn(category, kb_lower)
            
    def test_knowledge_base_includes_electrical_formulas(self):
        full_kb_lower = get_full_knowledge_base().lower()
        self.assertIn("ohm", full_kb_lower)
        self.assertIn("voltage divider", full_kb_lower)
        
    def test_knowledge_base_type_consistency(self):
        constants = [
            BREADBOARD_KNOWLEDGE, ARDUINO_KNOWLEDGE, COMPONENT_KNOWLEDGE,
            IC_KNOWLEDGE, CIRCUIT_PATTERNS, ADVANCED_MODULES, DEBUGGING_METHODOLOGY
        ]
        for const in constants:
            self.assertIsInstance(const, str)
        self.assertIsInstance(get_full_knowledge_base(), str)

if __name__ == '__main__':
    unittest.main()
