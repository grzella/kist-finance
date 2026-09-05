"""Leniwe proxy do fasady `planner` dla modułów planner_*.

Moduły dzielą przestrzeń nazw dawnego planner.py: odwołanie do funkcji z innego modułu
idzie przez `P.nazwa`, które w momencie wywołania czyta atrybut z `planner` — dzięki temu
nie ma cykli importów przy starcie, a monkeypatch `planner.X` w testach działa tak samo jak
przed podziałem. Odwołania w obrębie jednego modułu są gołe (jak dawniej).
"""


class _PlannerProxy:
    __slots__ = ()

    def __getattr__(self, name):
        import planner
        return getattr(planner, name)


P = _PlannerProxy()
