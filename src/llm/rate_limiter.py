"""
Un limiteur d'appels LLM simple (token-bucket) global pour protéger le quota.
Bloque l'appelant jusqu'à obtenir un jeton disponible.
"""
import time
import threading

from config import settings


class RateLimiter:
    def __init__(self, rate_per_minute: int):
        self.capacity = max(1, int(rate_per_minute))
        self.tokens = float(self.capacity)
        self.fill_rate = float(self.capacity) / 60.0  # tokens per second
        self.timestamp = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self):
        """Bloque jusqu'à ce qu'un jeton soit disponible puis le consomme."""
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.timestamp
                # Refill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
                self.timestamp = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                # temps estimé avant le prochain jeton
                needed = (1.0 - self.tokens) / self.fill_rate
            # attendre en-dehors du verrou
            time.sleep(max(needed, 0.05))


# Instance globale utilisée par le client LLM
GLOBAL_RATE_LIMITER = RateLimiter(settings.LLM_REQUESTS_PER_MINUTE)
