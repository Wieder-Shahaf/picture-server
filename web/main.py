import argparse

from website import create_app

app = create_app()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run the PictureServer.")
    p.add_argument("--port", type=int, default=5000)
    args = p.parse_args()
    app.run(debug=False, host="0.0.0.0", port=args.port, threaded=True)
