class ZhihuError(RuntimeError):
    """Base class for user-facing engine failures."""


class ZhihuAuthError(ZhihuError):
    pass


class ZhihuRateLimitError(ZhihuError):
    pass


class ZhihuRiskControlError(ZhihuRateLimitError):
    """Zhihu error 40362: login is valid but this access is risk-controlled."""


class ZhihuNetworkError(ZhihuError):
    pass


class ZhihuParseError(ZhihuError):
    pass
