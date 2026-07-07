class Limiter:
    def __init__(self, *a, **k): pass
    def limit(self, *a, **k):
        def deco(fn): return fn
        return deco
