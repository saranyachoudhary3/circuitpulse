import unittest
import numpy as np
import os
import sys

# Ensure env var is unset before import
if 'CIRCUITPULSE_ENABLE_CLOUD_EXPLAINER' in os.environ:
    os.environ.pop('CIRCUITPULSE_ENABLE_CLOUD_EXPLAINER')

# Add the project root to sys.path so intelligence module can be imported
sys.path.insert(0, r"c:\Users\Ayushman\Desktop\circuit_pulse")

from intelligence.vlm import CLASS_COLORS, KNOWLEDGE_BASE, CircuitAnalyzer

class VlmContractTests(unittest.TestCase):
    def setUp(self):
        if 'CIRCUITPULSE_ENABLE_CLOUD_EXPLAINER' in os.environ:
            os.environ.pop('CIRCUITPULSE_ENABLE_CLOUD_EXPLAINER')
            
    def test_class_colors_covers_all_eight_circuitpulse_classes(self):
        expected_keys = {'arduino_uno', 'arduino_nano', 'arduino_mega', 'esp32', 'breadboard', 'led', 'resistor', 'wire'}
        self.assertEqual(set(CLASS_COLORS.keys()), expected_keys)
        
    def test_class_colors_values_are_bgr_tuples(self):
        for color in CLASS_COLORS.values():
            self.assertIsInstance(color, tuple)
            self.assertEqual(len(color), 3)
            for val in color:
                self.assertIsInstance(val, int)
                self.assertTrue(0 <= val <= 255)
                
    def test_knowledge_base_is_populated(self):
        self.assertIsInstance(KNOWLEDGE_BASE, str)
        self.assertGreater(len(KNOWLEDGE_BASE), 0)
        
    def test_analyzer_defaults_to_cloud_disabled(self):
        analyzer = CircuitAnalyzer()
        self.assertFalse(analyzer.api_available)
        self.assertIsNone(analyzer.model)
        
    def test_ask_question_resets_analysis_timer(self):
        analyzer = CircuitAnalyzer()
        analyzer.last_analysis_time = 999
        analyzer.ask_question('test')
        self.assertEqual(analyzer.last_analysis_time, 0)
        self.assertEqual(analyzer._user_question, 'test')
        
    def test_annotate_frame_draws_on_numpy_array(self):
        analyzer = CircuitAnalyzer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = [{'bbox': {'x1': 10, 'y1': 10, 'x2': 100, 'y2': 100}, 'class': 'resistor', 'confidence': 0.85}]
        result = analyzer._annotate_frame(frame, detections)
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, (480, 640, 3))
        self.assertTrue(np.any(result > 0))
        
    def test_annotate_frame_with_empty_detections(self):
        analyzer = CircuitAnalyzer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[0, 0] = [1, 2, 3]
        result = analyzer._annotate_frame(frame.copy(), [])
        self.assertTrue(np.array_equal(result, frame))
        
    def test_analyzer_initializes_history_and_state(self):
        analyzer = CircuitAnalyzer()
        self.assertEqual(analyzer._analysis_history, [])
        self.assertEqual(analyzer._max_history, 5)
        self.assertEqual(analyzer.analysis_count, 0)
        self.assertEqual(analyzer.completed_steps, set())

if __name__ == '__main__':
    unittest.main()
