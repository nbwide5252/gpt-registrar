"""ChatGPT channel - Phase 1 SMS Registration."""

# Use flow.py (Phase 1) by default
try:
    from .flow import register
except ImportError:
    # Fallback to hybrid if flow.py has issues
    try:
        from .flow_hybrid_final import register_hybrid as register
    except ImportError:
        from .flow_old import register

__all__ = ["register"]
