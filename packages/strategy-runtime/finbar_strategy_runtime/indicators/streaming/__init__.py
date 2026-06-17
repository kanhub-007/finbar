"""Streaming indicator state objects.

One class per indicator family. Each exposes ``update(bar)`` and
``reset()``. State is maintained per-instance; the engine owns the
instances.
"""
