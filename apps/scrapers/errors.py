class VendorNotSupported(Exception):
    pass


class VendorAuthenticationFailed(Exception):
    pass


class OrderFetchException(Exception):
    pass


class NetworkConnectionException(Exception):
    pass
