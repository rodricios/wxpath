class XPathEvaluationError(Exception):
    """Errors during XPath evaluation with elementpath."""
    
    def __init__(
        self, 
        message: str, 
        xpath: str, 
        base_url: str | None = None,
        element_tag: str | None = None,
        error_code: str | None = None,  # XPath error codes like XPST0003
        position: tuple[int, int] | None = None,  # (line, column)
        original_error: Exception | None = None
    ):
        context = {
            "xpath": xpath,
            "base_url": base_url,
            "element_tag": element_tag,
            "error_code": error_code,
            "position": position,
        }
        if original_error:
            context["original_error"] = str(original_error)
            # Extract XPath error code if present (e.g., [err:XPST0003])
            if hasattr(original_error, 'code'):
                context["error_code"] = original_error.code
        
        super().__init__(message, context)

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "xpath": self.xpath,
            "base_url": self.base_url,
            "element_tag": self.element_tag,
            "error_code": self.error_code,
            "position": self.position,
            "original_error": self.original_error,
        }


class XPathSyntaxError(XPathEvaluationError):
    """Invalid XPath syntax."""
    pass


class XPathTypeError(XPathEvaluationError):
    """Type error in XPath expression."""
    pass


class XPathRuntimeError(XPathEvaluationError):
    """Runtime error during XPath evaluation."""
    pass