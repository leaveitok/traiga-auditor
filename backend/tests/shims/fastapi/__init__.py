"""Minimal fastapi shim for sandbox unit tests (no PyPI). NOT shipped."""
class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")

def Depends(dep=None):
    return dep

class _Route:
    def __init__(self, *a, **k): pass
    def __call__(self, fn): return fn

class APIRouter:
    def __init__(self, *a, **k): pass
    def get(self, *a, **k):    return _Route()
    def post(self, *a, **k):   return _Route()
    def patch(self, *a, **k):  return _Route()
    def delete(self, *a, **k): return _Route()
    def put(self, *a, **k):    return _Route()
