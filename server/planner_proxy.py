"""Lazy proxy to the `planner` facade for the planner_* modules.

The modules share the namespace of the former planner.py: a reference to a function from
another module goes through `P.name`, which reads the attribute from `planner` at call time —
so there are no import cycles at start-up and `monkeypatch.setattr(planner, …)` in tests keeps
working exactly as before the split. References within one module stay bare (as before).
"""


class _PlannerProxy:
    __slots__ = ()

    def __getattr__(self, name):
        import planner
        return getattr(planner, name)


P = _PlannerProxy()
