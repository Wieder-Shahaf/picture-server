from flask import jsonify


class MalformedImage(Exception):
    pass


def make_error(status: int, message: str):
    response = jsonify({"error": {"http_status": status, "message": message}})
    response.status_code = status
    response.headers["Content-Type"] = "application/json"
    return response


def register_error_handlers(app):
    app.url_map.strict_slashes = False

    @app.errorhandler(400)
    def _400(e):
        return make_error(400, "Bad request")

    @app.errorhandler(401)
    def _401(e):
        return make_error(401, "Missing or invalid token")

    @app.errorhandler(404)
    def _404(e):
        return make_error(404, "Not found")

    @app.errorhandler(405)
    def _405(e):
        return make_error(405, "Method not allowed")

    @app.errorhandler(413)
    def _413(e):
        return make_error(413, "Request body too large")

    @app.errorhandler(500)
    def _500(e):
        return make_error(500, "Internal server error")

    @app.errorhandler(Exception)
    def _unhandled(e):
        return make_error(500, "Internal server error")
