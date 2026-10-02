from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 15)
        self.cell(0, 10, 'CircuitPulse: Complete Construction & Integration Guide', border=0, new_x='LMARGIN', new_y='NEXT', align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', border=0, new_x='LMARGIN', new_y='NEXT', align='C')

    def chapter_title(self, title):
        self.set_font('helvetica', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, border=0, new_x='LMARGIN', new_y='NEXT', align='L', fill=True)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('helvetica', '', 11)
        self.multi_cell(190, 6, body)
        self.ln(4)

    def bullet_point(self, text):
        self.set_font('helvetica', '', 11)
        self.multi_cell(190, 6, f"  * {text}")

pdf = PDF()
pdf.add_page()
pdf.set_auto_page_break(auto=True, margin=15)

# --- SECTION 1 ---
pdf.chapter_title('1. Introduction & Project Setup')
pdf.chapter_body(
    "Welcome to the CircuitPulse physical setup guide! Since you are building a computer vision "
    "inspection system, we need a physical 'target' circuit for your camera to look at. We will build "
    "a classic 3-LED sequence circuit. It uses a variety of components (Arduino, LEDs, Resistors, Jumper Wires) "
    "which makes it the PERFECT test subject for the YOLOv8 model we just trained."
)

# --- SECTION 2 ---
pdf.chapter_title('2. Components Required')
pdf.chapter_body("Gather the following components from your list:")
pdf.bullet_point("1x Raspberry Pi 5 (4GB) with power supply and MicroSD card")
pdf.bullet_point("1x Smartphone (to act as our wireless webcam)")
pdf.bullet_point("1x Arduino Uno")
pdf.bullet_point("1x Full-size breadboard")
pdf.bullet_point("3x LEDs (any color)")
pdf.bullet_point("3x 330 Ohm Resistors (Color code: Orange-Orange-Brown)")
pdf.bullet_point("5x Jumper wires (1 Black for Ground, 3 colored for signals)")
pdf.bullet_point("1x USB-A to USB-B cable")
pdf.ln(5)

# --- SECTION 3 ---
pdf.chapter_title('3. Step-by-Step Circuit Wiring (For Total Beginners)')
pdf.chapter_body("Place your breadboard horizontally in front of you. Let's wire it up:")
pdf.chapter_body("STEP 1: The Ground (GND) Rail")
pdf.bullet_point("Take a black jumper wire. Connect one end to any 'GND' pin on the Arduino.")
pdf.bullet_point("Connect the other end to the blue negative (-) rail running along the bottom of the breadboard.")

pdf.chapter_body("STEP 2: The First LED & Resistor")
pdf.bullet_point("Grab an LED. Notice one leg is longer (Anode +) and one is shorter (Cathode -).")
pdf.bullet_point("Insert the long leg into row 10 (e.g., hole 10j) and the short leg into row 11 (e.g., 11j).")
pdf.bullet_point("Take a 330 Ohm resistor. Plug one end into the blue (-) ground rail, and the other end into row 11 (same row as the short LED leg).")
pdf.bullet_point("Take a colored jumper wire. Connect Arduino Digital Pin 13 to row 10 (same row as the long LED leg).")

pdf.chapter_body("STEP 3: The Second LED & Resistor")
pdf.bullet_point("Insert the second LED's long leg into row 15, and short leg into row 16.")
pdf.bullet_point("Connect a 330 Ohm resistor from row 16 to the blue (-) ground rail.")
pdf.bullet_point("Connect Arduino Digital Pin 12 to row 15 with a jumper wire.")

pdf.chapter_body("STEP 4: The Third LED & Resistor")
pdf.bullet_point("Insert the third LED's long leg into row 20, and short leg into row 21.")
pdf.bullet_point("Connect a 330 Ohm resistor from row 21 to the blue (-) ground rail.")
pdf.bullet_point("Connect Arduino Digital Pin 11 to row 20 with a jumper wire.")
pdf.ln(5)

# --- SECTION 4 ---
pdf.chapter_title('4. System Architecture & Integration')
pdf.chapter_body(
    "Now that the physical circuit is built, here is how you connect the 'Brain' (Raspberry Pi), "
    "the 'Eye' (Smartphone), and the 'Target' (Arduino Circuit):"
)
pdf.chapter_body("1. THE EYE (Smartphone Camera):")
pdf.bullet_point("Install the 'IP Webcam' app (Android) or 'DroidCam' (iOS/Android) on your phone.")
pdf.bullet_point("Connect the phone to the same Wi-Fi network as the Raspberry Pi.")
pdf.bullet_point("Start the server in the app. It will give you an IP address (e.g., http://192.168.1.15:8080/video).")
pdf.bullet_point("Mount your phone above the breadboard using a stand or tripod, looking down at the circuit.")

pdf.chapter_body("2. THE TARGET (Arduino):")
pdf.bullet_point("Connect the Arduino to the Raspberry Pi using the USB-A to USB-B cable. The Arduino will power on and provide a complete circuit for inspection.")

pdf.chapter_body("3. THE BRAIN (Raspberry Pi 5):")
pdf.bullet_point("Boot up the Raspberry Pi.")
pdf.bullet_point("Copy the YOLOv8 models we trained (PRODUCTION_eesob_48class_best.pt) from your laptop to the Pi using a USB drive or SCP over network.")
pdf.bullet_point("Install the required software on the Pi by opening the terminal and typing:")
pdf.bullet_point("  pip install ultralytics opencv-python")
pdf.ln(5)

# --- SECTION 5 ---
pdf.chapter_title('5. Running the AI Model on the Pi')
pdf.chapter_body("Create a file on the Raspberry Pi called 'inspect.py' and add this code:")
code = """
from ultralytics import YOLO
import cv2

# Load the production model
model = YOLO("PRODUCTION_eesob_48class_best.pt")

# Replace with the IP address from your smartphone app
video_url = "http://192.168.1.15:8080/video"

# Run the real-time AI inspection
results = model.predict(source=video_url, show=True, conf=0.30)
"""
pdf.set_font('courier', '', 10)
pdf.set_fill_color(240, 240, 240)
pdf.multi_cell(0, 5, code, 0, 'L', 1)

pdf.set_font('helvetica', '', 11)
pdf.ln(5)
pdf.chapter_body(
    "Run the script by typing 'python inspect.py' in the Pi terminal. A window will pop up showing the "
    "live video feed from your phone. The AI will draw boxes around the Arduino, breadboard, LEDs, and "
    "resistors in real-time, proving your fault detection system works!"
)

pdf_path = r"C:\Users\Ayushman\Desktop\CircuitPulse_Integration_Guide.pdf"
pdf.output(pdf_path)
print(f"PDF successfully created at: {pdf_path}")
