from flask import jsonify
from app.exceptions import APIException

def register_error_handlers(app):

    # Custom API exception
    @app.errorhandler(APIException)
    def handle_api_exception(e):
        return jsonify({
            "status": "error",
            "message": e.message
        }), e.status_code

    # Handle bad request (400)
    @app.errorhandler(400)
    def handle_400(e):
        return jsonify({
            "status": "error",
            "message": "Bad Request"
        }), 400

    # Handle all unhandled exceptions (500)
    @app.errorhandler(Exception)
    def handle_exception(e):
        import traceback
        traceback.print_exc()  # Print the full traceback to container logs
        return jsonify({
            "status": "error",
            "message": str(e)  # Return the actual error message for now
        }), 500