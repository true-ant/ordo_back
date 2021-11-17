class VendorSiteError(Exception):
    pass


class VendorNotSupported(Exception):
    pass


class VendorAuthenticationFailed(Exception):
    pass


class OrderFetchException(Exception):
    pass


class NetworkConnectionException(Exception):
    pass


class VendorNotConnected(Exception):
    pass
