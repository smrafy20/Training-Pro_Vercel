# Vercel serverless entrypoint for Flask (WSGI)
# Vercel's Python runtime will import this module and look for a WSGI callable named "app".
# We re-export the Flask app defined in app.py.

from app import app as flask_app

# Expose the WSGI application for Vercel
app = flask_app

if __name__ == "__main__":
    # Optional: run locally for testing this entrypoint
    # python api/index.py
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", 5000, app)