def elite_check(pf: float = 3.0, accuracy: float = 70.0, health: float = 80.0, data_ok: bool = True) -> str:
    if not data_ok:
        return "BLOCK"
    if pf < 1.0:
        return "BLOCK"
    if accuracy < 45.0:
        return "BLOCK"
    if health < 30.0:
        return "BLOCK"
    if pf < 2.5 or accuracy < 60.0 or health < 60.0:
        return "RESTRICT"
    return "ALLOW"
