from rest_framework.versioning import AcceptHeaderVersioning


class OrdoAPIVersioning(AcceptHeaderVersioning):
    default_version = "1.0"
    allowed_versions = ["1.0", "2.0"]
