from rest_framework.renderers import JSONRenderer


class APIRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        status_code = renderer_context["response"].status_code
        response = {"status": "success", "code": status_code, "data": data, "message": None}
        if not str(status_code).startswith("2"):
            response["status"] = "error"
            response["data"] = None
            try:
                response["message"] = data["message"]
            except KeyError:
                response["data"] = data
        return super().render(response, accepted_media_type, renderer_context)