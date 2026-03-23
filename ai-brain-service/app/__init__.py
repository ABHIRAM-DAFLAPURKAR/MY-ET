from flask import Flask
from app.routes_fixed import register_routes
from app.error_handler import register_error_handlers

def create_app():
    app = Flask(__name__)

    register_routes(app)
    register_error_handlers(app)

    return app
