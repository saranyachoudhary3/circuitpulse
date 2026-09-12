from app import *

if __name__ == "__main__":
    load_dual_models()
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=inference_loop, daemon=True).start()
    print(f"Running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
