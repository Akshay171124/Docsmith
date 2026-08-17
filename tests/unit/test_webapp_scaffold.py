def test_webapp_package_and_fastapi_importable():
    import fastapi  # from requirements-web.txt

    import webapp  # the new package

    assert fastapi.FastAPI is not None
    assert webapp.__doc__  # package has a module docstring
