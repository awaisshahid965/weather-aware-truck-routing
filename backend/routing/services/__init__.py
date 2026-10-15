"""Use cases.

A service receives its ports and settings through its constructor, combines
domain rules, and returns domain values. It never reads Django settings or
imports an adapter: the composition root builds it with concrete adapters, and
tests build it with fakes.
"""
