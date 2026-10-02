# -*- coding: utf-8 -*-
import os
import zipfile

def create_deployment_package():
    deploy_dir = "pi_deploy"
    if not os.path.exists(deploy_dir):
        os.makedirs(deploy_dir)
        
    zip_path = os.path.join(deploy_dir, "circuit_pulse_pi5.zip")
    print(f"[*] Creating deployment package: {zip_path}")
    
    # New humanized file structure
    targets = {
        "main.py": "main.py",
        "camera.py": "camera.py",
        "web": "web",
        "detectors": "detectors",
        "logic": "logic",
        "intelligence": "intelligence",
        "runs/detect/ProductionRun/circuit_master_optimized/weights/best_ncnn_model": "runs/detect/ProductionRun/circuit_master_optimized/weights/best_ncnn_model",
        "runs/detect/ProductionRun/circuit_master_optimized/weights/best.pt": "runs/detect/ProductionRun/circuit_master_optimized/weights/best.pt",
        "pi_deploy/circuitpulse.service": "circuitpulse.service",
        "pi_deploy/requirements.txt": "requirements.txt"
    }
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for src, dest_prefix in targets.items():
            if not os.path.exists(src):
                print(f"[!] Warning: {src} not found. Skipping.")
                continue
                
            if os.path.isfile(src):
                zipf.write(src, dest_prefix)
                print(f"  Added {src} -> {dest_prefix}")
            else:
                for root, dirs, files in os.walk(src):
                    if '__pycache__' in root or '/.' in root.replace('\\', '/'):
                        continue
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = file_path.replace('\\', '/')  # Linux-compatible paths
                        zipf.write(file_path, arcname)
                print(f"  Added directory {src}")
                
    print("\n[OK] Core Deployment package locked and zipped!")

if __name__ == "__main__":
    create_deployment_package()
