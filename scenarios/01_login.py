from importlib import import_module


web_login = import_module("scenarios.00_web_login")


async def run(page):
    return await web_login.run(page)
