import unittest
from logic.gpio import GPIOController
from unittest.mock import patch, MagicMock

class TestGpioCoverage(unittest.TestCase):
    @patch.dict('sys.modules', {'gpiozero': None, 'RPi': None, 'RPi.GPIO': None})
    @patch('logic.gpio.time.sleep')
    def test_gpio_init_no_hardware(self, mock_sleep):
        controller = GPIOController()
        self.assertFalse(controller.is_pi)
        
    @patch('logic.gpio.time.time')
    def test_beep_throttling(self, mock_time):
        mock_time.return_value = 100.0
        controller = GPIOController()
        controller.is_pi = True
        controller.use_gpiozero = True
        controller.buzzer = MagicMock()
        
        controller.beep(0.1)
        controller.buzzer.beep.assert_called_once()
        
        # Should be throttled
        mock_time.return_value = 100.5
        controller.beep(0.1)
        self.assertEqual(controller.buzzer.beep.call_count, 1)
        
        # Should not be throttled
        mock_time.return_value = 101.1
        controller.beep(0.1)
        self.assertEqual(controller.buzzer.beep.call_count, 2)
        
    def test_update_pass(self):
        controller = GPIOController()
        controller.is_pi = True
        controller.use_gpiozero = True
        controller.green_led = MagicMock()
        controller.red_led = MagicMock()
        
        controller.update({"status": "PASS", "errors": []})
        controller.green_led.on.assert_called_once()
        controller.red_led.off.assert_called_once()
        
    def test_update_fail_with_short(self):
        controller = GPIOController()
        controller.is_pi = True
        controller.use_gpiozero = True
        controller.green_led = MagicMock()
        controller.red_led = MagicMock()
        controller.beep = MagicMock()
        
        controller.update({"status": "FAIL", "errors": [{"message": "There is a short circuit"}]})
        controller.green_led.off.assert_called_once()
        controller.red_led.on.assert_called_once()
        controller.beep.assert_called_once_with(0.5)
        
    def test_cleanup(self):
        controller = GPIOController()
        controller.is_pi = True
        controller.use_gpiozero = True
        controller.red_led = MagicMock()
        controller.green_led = MagicMock()
        controller.buzzer = MagicMock()
        
        controller.cleanup()
        controller.red_led.close.assert_called_once()
        controller.green_led.close.assert_called_once()
        controller.buzzer.close.assert_called_once()
