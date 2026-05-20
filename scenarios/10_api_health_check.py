from app.api_runner import ApiCheck, run_api_checks


SCENARIO_TYPE = "api"


async def run():
    return await run_api_checks(
        [
            ApiCheck(
                name="api_health_root",
                method="GET",
                endpoint="/",
            ),
        ]
    )
