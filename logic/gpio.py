import time
import threading

class GPIOController:
    def __init__(self, red_pin=17, green_pin=27, buzzer_pin=22):
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.buzzer_pin = buzzer_pin
        self.is_pi = False
        self.last_beep_time = 0  # Throttle beeps
        
        # Try gpiozero first (Pi 5 compatible), fall back to RPi.GPIO
        try:
            from gpiozero import LED, Buzzer
            self.red_led = LED(red_pin)
            self.green_led = LED(green_pin)
            self.buzzer = Buzzer(buzzer_pin)
            self.is_pi = True
            self.use_gpiozero = True
            self.buzzer.beep(on_time=0.2, n=1)
            print(f"[GPIO] gpiozero initialized (Pi 5 compatible). Pins: R={red_pin}, G={green_pin}, Bz={buzzer_pin}")
        except Exception:
            self.use_gpiozero = False
            try:
                import RPi.GPIO as gpio
                self.gpio = gpio
                self.is_pi = True
                self.gpio.setmode(self.gpio.BCM)
                self.gpio.setwarnings(False)
                self.gpio.setup(self.red_pin, self.gpio.OUT)
                self.gpio.setup(self.green_pin, self.gpio.OUT)
                self.gpio.setup(self.buzzer_pin, self.gpio.OUT)
                self.beep(0.2)
                print(f"[GPIO] RPi.GPIO initialized. Pins: R={red_pin}, G={green_pin}, Bz={buzzer_pin}")
            except Exception as e:
                self.is_pi = False
                print(f"[GPIO] No hardware GPIO available ({e}). Running in simulation mode.")

    def beep(self, duration=0.1):
        if not self.is_pi:
            return
        
        # Throttle beeps to max 1 per second
        now = time.time()
        if now - self.last_beep_time < 1.0:
            return
        self.last_beep_time = now
            
        if self.use_gpiozero:
            try:
                self.buzzer.beep(on_time=duration, n=1)
            except Exception:
                pass
        else:
            def _beep():
                try:
                    self.gpio.output(self.buzzer_pin, self.gpio.HIGH)
                    time.sleep(duration)
                    self.gpio.output(self.buzzer_pin, self.gpio.LOW)
                except Exception:
                    pass
            threading.Thread(target=_beep, daemon=True).start()

    def update(self, report):
        if not self.is_pi:
            return
            
        status = report.get("status")
        errors = report.get("errors", [])
        
        try:
            if status == "PASS" and not report.get("current_step") and report.get("circuit_name") != "scanning":
                if self.use_gpiozero:
                    self.green_led.on()
                    self.red_led.off()
                else:
                    self.gpio.output(self.green_pin, self.gpio.HIGH)
                    self.gpio.output(self.red_pin, self.gpio.LOW)
            elif len(errors) > 0:
                if self.use_gpiozero:
                    self.green_led.off()
                    self.red_led.on()
                else:
                    self.gpio.output(self.green_pin, self.gpio.LOW)
                    self.gpio.output(self.red_pin, self.gpio.HIGH)
                
                for err in errors:
                    if "short" in err.get("message", "").lower():
                        self.beep(0.5)
                        break
            else:
                if self.use_gpiozero:
                    self.green_led.off()
                    self.red_led.off()
                else:
                    self.gpio.output(self.green_pin, self.gpio.LOW)
                    self.gpio.output(self.red_pin, self.gpio.LOW)
        except Exception:
            pass  # Silently handle any GPIO errors during demo

    def cleanup(self):
        if self.is_pi:
            try:
                if self.use_gpiozero:
                    self.red_led.close()
                    self.green_led.close()
                    self.buzzer.close()
                else:
                    self.gpio.cleanup()
            except Exception:
                pass
