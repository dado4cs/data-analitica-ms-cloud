class AthenaQueryError(Exception):
    """Se lanza cuando Athena devuelve un estado FAILED o CANCELLED."""
    pass


class AthenaTimeoutError(Exception):
    """Se lanza cuando Athena no termina dentro del tiempo límite."""
    pass
