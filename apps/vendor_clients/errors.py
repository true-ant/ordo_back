class VendorClientException(Exception):
    pass


class VendorAuthenticationFailed(VendorClientException):
    pass
