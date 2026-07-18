"""Entry point — run with: uvicorn wizard_kernel.main:app --reload --port 8080"""
from wizard_kernel.api.app import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wizard_kernel.main:app", host="0.0.0.0", port=8080, reload=True)
