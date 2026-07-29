from fastapi import APIRouter

class AmphotericRouter:
    def __init__(self):
        self.router = APIRouter()
        self._tools = {}

    def tool(self, name: str, description: str):
        def decorator(func):
            self._tools[name] = func
            # Expose the tool as a REST endpoint for compatibility
            self.router.post(f"/api/mcp/tools/{name}")(func)
            return func
        return decorator

def create_mcp_endpoints(app, amphoteric):
    pass
