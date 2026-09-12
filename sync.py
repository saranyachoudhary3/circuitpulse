import os
import sys
import socket
import subprocess
import threading
import http.server

user = "circuit"
src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pi_transfer")
dest_dir = "~/circuitpulse"

files = [
    "app.py",
    "circuit.py",
    "circuit_engine.py",
    "tracker.py",
    "resistor.py",
    "index.html",
    "server_v2.py",
    "dashboard.html",
    "preview.py",
    "install.sh",
]


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_scp(host):
    print(f"Connecting to {host}...")
    subprocess.run(f'ssh -o ConnectTimeout=5 {user}@{host} "mkdir -p {dest_dir}/models {dest_dir}/circuits"', shell=True)

    for f in files:
        src = os.path.join(src_dir, f)
        if os.path.exists(src):
            print(f"Sending {f}...")
            subprocess.run(f'scp -o ConnectTimeout=5 "{src}" {user}@{host}:{dest_dir}/{f}', shell=True)

    circuits_dir = os.path.join(src_dir, "circuits")
    if os.path.exists(circuits_dir):
        for c in os.listdir(circuits_dir):
            if c.endswith(".json"):
                src = os.path.join(circuits_dir, c)
                subprocess.run(f'scp -o ConnectTimeout=5 "{src}" {user}@{host}:{dest_dir}/circuits/{c}', shell=True)

    models_dir = os.path.join(src_dir, "models")
    if os.path.exists(models_dir):
        for m in os.listdir(models_dir):
            if m.endswith(".pt"):
                src = os.path.join(models_dir, m)
                print(f"Sending model {m}...")
                subprocess.run(f'scp -o ConnectTimeout=5 "{src}" {user}@{host}:{dest_dir}/models/{m}', shell=True)


def run_http_server(port=8888):
    server = http.server.HTTPServer(("0.0.0.0", port), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    target = input("Raspberry Pi IP address [10.155.25.242]: ").strip() or "10.155.25.242"
    print("Attempting direct file transfer...")

    try:
        run_scp(target)
        print("Transfer complete.")
    except Exception:
        print("Direct transfer failed, starting local file server instead...")
        ip = get_local_ip()
        orig = os.getcwd()
        os.chdir(src_dir)
        server = run_http_server(8888)
        os.chdir(orig)

        print(f"\nDownload files on the Pi using:")
        print(f"  mkdir -p ~/circuitpulse/models ~/circuitpulse/circuits && cd ~/circuitpulse")
        print(f"  wget -O app.py http://{ip}:8888/app.py")
        print(f"  wget -O circuit.py http://{ip}:8888/circuit.py")
        print(f"  wget -O tracker.py http://{ip}:8888/tracker.py")
        print(f"  wget -O resistor.py http://{ip}:8888/resistor.py")
        print(f"  wget -O index.html http://{ip}:8888/index.html")
        print(f"  wget -O models/base.pt http://{ip}:8888/models/base.pt")
        print(f"  wget -O models/passives.pt http://{ip}:8888/models/passives.pt")
        print(f"  wget -O models/faults.pt http://{ip}:8888/models/faults.pt")
        input("\nPress Enter when finished downloading to stop the server...")
        server.shutdown()


if __name__ == "__main__":
    main()
