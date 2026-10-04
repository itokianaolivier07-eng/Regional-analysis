"""Exceptions LLM unifiées."""
class LLMError(Exception): pass
class QuotaError(LLMError): pass
class GoogleQuotaError(QuotaError): pass
class OpenRouterError(LLMError): pass
class OpenRouterQuotaError(QuotaError, OpenRouterError): pass
