class KeitaroError(Exception):
    """Base exception for Keitaro integration."""


class KeitaroConfigurationError(KeitaroError):
    """Keitaro integration is not configured correctly."""


class KeitaroConnectionError(KeitaroError):
    """Cannot connect to Keitaro API."""


class KeitaroTimeoutError(KeitaroError):
    """Keitaro API request timed out."""


class KeitaroAPIError(KeitaroError):
    """Keitaro API returned an unsuccessful response."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(
            f"Keitaro API returned HTTP {status_code}"
        )


class KeitaroInvalidResponseError(KeitaroError):
    """Keitaro API returned invalid JSON."""
