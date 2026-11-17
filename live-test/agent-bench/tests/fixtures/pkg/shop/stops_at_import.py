# Fixture of the Python key tests: a module that stops its import with a BaseException, as pytest.importorskip does.
class StopImport(BaseException):
    pass


raise StopImport()
