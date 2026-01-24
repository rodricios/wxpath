from wxpath.http.policy.backoff import exponential_backoff
from wxpath.util.logging import get_logger

log = get_logger(__name__)


class RetryPolicy:
    def __init__(
        self,
        max_retries: int = 3,
        retry_statuses: set[int] = None,
    ):
        self.max_retries = max_retries
        self.retry_statuses = retry_statuses or {500, 502, 503, 504}

    def should_retry(self, request, response=None, exception=None) -> bool:
        if request.dont_retry:
            return False

        if request.max_retries is not None and request.retries >= request.max_retries:
            return False

        if request.retries >= self.max_retries:
            return False

        if response is not None and response.status in self.retry_statuses:
            return True

        if exception is not None:
            return True

        return False

    def get_delay(self, request) -> float:
        return exponential_backoff(request.retries)