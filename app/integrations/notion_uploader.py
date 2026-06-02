import os
import mimetypes
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")
load_dotenv()

NOTION_VERSION = "2022-06-28"
FILE_UPLOAD_VERSION = "2026-03-11"


class NotionUploadError(RuntimeError):
    def __init__(self, user_message: str, detail: str | None = None):
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.detail = detail or user_message


class NotionUploader:
    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        self.database_id = os.getenv("NOTION_DB_ID")
        self.database_schema = None

        if not self.token:
            raise NotionUploadError(
                "Notion 토큰이 설정되지 않았습니다. .env의 NOTION_TOKEN 값을 확인하세요."
            )

        if not self.database_id:
            raise NotionUploadError(
                "Notion 데이터베이스 ID가 설정되지 않았습니다. .env의 NOTION_DB_ID 값을 확인하세요."
            )

        self._validate_config()

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _validate_config(self) -> None:
        if not self.token.isascii() or any(char.isspace() for char in self.token):
            raise NotionUploadError(
                "Notion 토큰 형식이 올바르지 않습니다. .env에 Internal Integration Secret 값을 다시 입력하세요.",
                "NOTION_TOKEN contains non-ASCII or whitespace characters.",
            )

        if not self.database_id.isascii() or any(char.isspace() for char in self.database_id):
            raise NotionUploadError(
                "Notion 데이터베이스 ID 형식이 올바르지 않습니다. .env의 NOTION_DB_ID 값을 다시 입력하세요.",
                "NOTION_DB_ID contains non-ASCII or whitespace characters.",
            )

    def _request(self, method: str, url: str, notion_version: str | None = None, **kwargs):
        headers = self.headers.copy()
        if notion_version:
            headers["Notion-Version"] = notion_version

        try:
            response = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise NotionUploadError(
                "Notion API 요청에 실패했습니다. 네트워크와 Notion 설정을 확인하세요.",
                str(exc),
            ) from exc

        if response.status_code not in (200, 201):
            raise NotionUploadError(
                self._format_user_error(response),
                self._format_error(response),
            )
        return response.json()

    def _upload_file(self, file_path: str | Path) -> dict:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise NotionUploadError(
                f"첨부 파일을 찾을 수 없습니다: {path.name}",
                f"Attachment not found: {path}",
            )

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        create_response = self._request(
            "POST",
            "https://api.notion.com/v1/file_uploads",
            notion_version=FILE_UPLOAD_VERSION,
            json={
                "mode": "single_part",
                "filename": path.name,
                "content_type": content_type,
            },
        )

        upload_id = create_response["id"]
        upload_headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": FILE_UPLOAD_VERSION,
        }

        try:
            with path.open("rb") as file_obj:
                response = requests.post(
                    f"https://api.notion.com/v1/file_uploads/{upload_id}/send",
                    headers=upload_headers,
                    files={"file": (path.name, file_obj, content_type)},
                    timeout=60,
                )
        except requests.RequestException as exc:
            raise NotionUploadError(
                f"첨부 파일 업로드에 실패했습니다: {path.name}",
                str(exc),
            ) from exc

        if response.status_code not in (200, 201):
            raise NotionUploadError(
                f"첨부 파일 업로드에 실패했습니다: {path.name}",
                self._format_error(response),
            )

        return response.json()

    def _format_user_error(self, response) -> str:
        if response.status_code == 401:
            return "Notion 토큰이 유효하지 않습니다. 새 Internal Integration Secret 값을 .env에 입력하세요."
        if response.status_code == 403:
            return "Notion 권한이 없습니다. 데이터베이스를 해당 Integration에 공유했는지 확인하세요."
        if response.status_code == 404:
            return "Notion 데이터베이스를 찾을 수 없습니다. DB ID와 Integration 공유 여부를 확인하세요."
        if response.status_code == 400:
            return "Notion 데이터베이스 속성 형식이 맞지 않습니다. DB 컬럼 이름과 타입을 확인하세요."
        return "Notion 등록 중 오류가 발생했습니다. 설정과 Notion 상태를 확인하세요."

    def _format_error(self, response) -> str:
        try:
            data = response.json()
            message = data.get("message", response.text)
            code = data.get("code")
            if code:
                return f"Notion API 오류 {response.status_code} ({code}): {message}"
            return f"Notion API 오류 {response.status_code}: {message}"
        except ValueError:
            return f"Notion API 오류 {response.status_code}: {response.text}"

    def _apply_page_display_options(self, page_id: str) -> None:
        try:
            self._request(
                "PATCH",
                f"https://api.notion.com/v1/pages/{page_id}",
                json={
                    "is_full_width": True,
                    "is_small_text": True,
                },
            )
        except NotionUploadError:
            pass

    def _get_database_schema(self):
        if self.database_schema is None:
            self.database_schema = self._request(
                "GET",
                f"https://api.notion.com/v1/databases/{self.database_id}",
            )
        return self.database_schema

    def _get_property(self, name: str):
        schema = self._get_database_schema()
        return schema.get("properties", {}).get(name)

    def _property_name(self, candidates: list[str]) -> str:
        schema = self._get_database_schema()
        properties = schema.get("properties", {})
        for candidate in candidates:
            if candidate in properties:
                return candidate
        raise NotionUploadError(
            f"Notion DB에 '{candidates[0]}' 컬럼이 없습니다. 컬럼 이름을 확인하세요.",
            f"Missing Notion property. candidates={candidates}",
        )

    def _property(self, candidates: list[str]) -> tuple[str, dict]:
        name = self._property_name(candidates)
        return name, self._get_property(name)

    def _available_option_names(self, prop: dict, prop_type: str) -> list[str]:
        if not prop or prop.get("type") != prop_type:
            return []
        return [
            option.get("name")
            for option in prop.get(prop_type, {}).get("options", [])
            if option.get("name")
        ]

    def _pick_option(self, candidates: list[str], options: list[str]) -> str:
        for candidate in candidates:
            if candidate and candidate in options:
                return candidate
        if options:
            return options[0]
        for candidate in candidates:
            if candidate:
                return candidate
        raise NotionUploadError(
            "Notion 선택 옵션 값을 만들 수 없습니다. 플랫폼/상태 값을 확인하세요.",
            f"No valid option candidate. candidates={candidates}",
        )

    def _text_property(self, prop: dict, value: str) -> dict:
        prop_type = prop.get("type")
        if prop_type == "rich_text":
            return {"rich_text": [{"text": {"content": value}}]}
        if prop_type == "title":
            return {"title": [{"text": {"content": value}}]}
        raise NotionUploadError(
            "Notion DB 텍스트 컬럼 타입이 맞지 않습니다. 제목/버전/결과 컬럼 타입을 확인하세요.",
            f"Invalid text property type: {prop_type}",
        )

    def _number_property(self, prop: dict, value: int) -> dict:
        if prop.get("type") != "number":
            raise NotionUploadError(
                "Notion DB 숫자 컬럼 타입이 맞지 않습니다. PASS/FAIL/N/A/Total 컬럼 타입을 number로 설정하세요.",
                f"Invalid number property type: {prop.get('type')}",
            )
        return {"number": int(value)}

    def _date_property(self, prop: dict, value: str) -> dict | None:
        prop_type = prop.get("type")
        if prop_type == "created_time":
            return None
        if prop_type != "date":
            raise NotionUploadError(
                "Notion DB 등록일 컬럼 타입이 맞지 않습니다. 등록일 컬럼 타입을 date 또는 created_time으로 설정하세요.",
                f"Invalid date property type: {prop_type}",
            )
        return {"date": {"start": value}}

    def _status_property(self, requested_status: str) -> tuple[str, dict]:
        status_name, status_prop = self._property(["상태", "Status"])
        prop_type = status_prop.get("type") if status_prop else "status"
        if prop_type not in ("status", "select"):
            raise NotionUploadError("Notion DB의 '상태' 속성 타입을 status 또는 select로 변경하세요.")

        options = self._available_option_names(status_prop, prop_type)

        if requested_status in ("완료", "성공"):
            candidates = [
                os.getenv("NOTION_STATUS_SUCCESS"),
                "성공",
                "완료",
                "Done",
                "Complete",
                "Completed",
                "Success",
            ]
        else:
            candidates = [
                os.getenv("NOTION_STATUS_FAILURE"),
                "실패",
                "Blocked",
                "Fail",
                "Failed",
                "Error",
            ]

        return status_name, {prop_type: {"name": self._pick_option(candidates, options)}}

    def _test_result_property(self, requested_result: str) -> tuple[str, dict]:
        result_name, result_prop = self._property(["테스트 결과", "Test Result"])
        prop_type = result_prop.get("type") if result_prop else "select"
        if prop_type != "select":
            raise NotionUploadError(
                "Notion DB의 '테스트 결과' 속성 타입을 select로 변경하세요.",
                f"Invalid test result property type: {prop_type}",
            )

        options = self._available_option_names(result_prop, prop_type)
        if requested_result in ("테스트 성공", "테스트 완료"):
            candidates = [
                os.getenv("NOTION_TEST_RESULT_SUCCESS"),
                "테스트 성공",
                "테스트 완료",
                "완료",
                "성공",
                "Success",
                "Completed",
            ]
        else:
            candidates = [
                os.getenv("NOTION_TEST_RESULT_FAILURE"),
                "테스트 실패",
                "실패",
                "Fail",
                "Failed",
            ]

        return result_name, {prop_type: {"name": self._pick_option(candidates, options)}}

    def _platform_property(self, platform: str) -> tuple[str, dict]:
        platform_name, platform_prop = self._property(["플랫폼", "Platform"])
        prop_type = platform_prop.get("type")
        if prop_type not in ("select", "status", "rich_text"):
            raise NotionUploadError(
                "Notion DB 플랫폼 컬럼 타입이 맞지 않습니다. 플랫폼 컬럼 타입을 select로 설정하세요.",
                f"Invalid platform property type: {prop_type}",
            )
        if prop_type == "rich_text":
            return platform_name, {"rich_text": [{"text": {"content": platform}}]}

        options = self._available_option_names(platform_prop, prop_type)
        return platform_name, {prop_type: {"name": self._pick_option([platform], options)}}

    def _rich_text(self, content: str, annotations: dict | None = None) -> dict:
        text = {"type": "text", "text": {"content": content[:2000]}}
        if annotations:
            text["annotations"] = annotations
        return text

    def _paragraph_block(self, content: str, annotations: dict | None = None) -> dict:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [self._rich_text(content, annotations)]
            },
        }

    def _bulleted_item_block(self, content: str, annotations: dict | None = None) -> dict:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [self._rich_text(content, annotations)]
            },
        }

    def _test_case_description(self, name: str) -> str:
        normalized = name.strip()
        descriptions = {
            "ensure_login": "로그인 상태 확인 및 필요 시 자동 로그인",
            "open_url": "검증 대상 URL 접속",
            "open_home": "홈 화면 접속",
            "open_go_hanpass_home": "GO Hanpass 홈 화면 접속",
            "open_payment_tab": "결제 탭 열기",
            "open_travel_tab": "여행 탭 열기",
            "title_check": "페이지 타이틀 노출 확인",
            "email_input": "로그인 이메일 입력",
            "password_input_click": "비밀번호 입력창 선택",
            "password_keypad_input": "보안 키패드로 비밀번호 입력",
            "confirm_click": "로그인 확인 버튼 선택",
            "login_flow": "웹 로그인 진입 및 자동 로그인 수행",
            "web_signin_response_check": "web-signin API 로그인 성공 응답 확인",
            "login_result_check": "로그인 성공 및 보호 메뉴 접근 확인",
            "region_open_click": "지역 선택 바텀시트 열기",
            "region_close_click": "지역 선택 바텀시트 닫기",
            "weather_click": "날씨 화면 진입",
            "menu_open_click": "전체 메뉴 열기",
            "menu_close_click": "메뉴/레이어 닫기",
            "scroll_down": "화면 아래 방향 스크롤",
            "scroll_up": "화면 위 방향 스크롤",
            "back_click": "이전 화면으로 이동",
            "home_result_check": "홈 화면 복귀 상태 확인",
            "collect_full_menu_items": "전체 메뉴 항목 수집",
            "scenario_execution": "시나리오 실행 상태",
        }

        if normalized in descriptions:
            return descriptions[normalized]

        prefix_descriptions = [
            ("select_region_", "지역 선택 기능 확인"),
            ("payment_menu_", "결제 탭 메뉴 진입 및 반응 확인"),
            ("travel_menu_", "여행 탭 메뉴 진입 및 반응 확인"),
            ("main_click_", "메인 화면 클릭 후보 진입 및 반응 확인"),
            ("menu_", "전체 메뉴 항목 진입 및 반응 확인"),
        ]

        for prefix, description in prefix_descriptions:
            if normalized.startswith(prefix):
                return description

        keyword_descriptions = [
            ("popup", "팝업 노출 및 닫기 동작 확인"),
            ("closed", "바텀시트/팝업 닫기 동작 확인"),
            ("close", "닫기 동작 확인"),
            ("back", "뒤로가기 동작 확인"),
            ("scroll", "스크롤 동작 확인"),
            ("click", "버튼/메뉴 클릭 동작 확인"),
            ("tab", "탭 전환 동작 확인"),
            ("input", "입력 필드 동작 확인"),
            ("swipe", "가로 스와이프 동작 확인"),
            ("banner", "배너 영역 동작 확인"),
        ]

        lowered = normalized.lower()
        for keyword, description in keyword_descriptions:
            if keyword in lowered:
                return description

        return "화면 요소 노출 및 동작 확인"

    def _parse_result_text(self, result_text: str) -> list[dict]:
        scenarios = []
        current = None

        for line in result_text.splitlines():
            text = line.strip()
            if not text:
                continue

            if text.startswith("[") and text.endswith("]"):
                current = {"name": text.strip("[]"), "tests": []}
                scenarios.append(current)
                continue

            if not text.startswith("- "):
                continue

            if current is None:
                current = {"name": "테스트 결과", "tests": []}
                scenarios.append(current)

            clean_text = text[2:]
            if ": " in clean_text:
                name, status = clean_text.split(": ", 1)
            else:
                name, status = clean_text, "-"

            current["tests"].append(
                {
                    "name": name.strip(),
                    "description": self._test_case_description(name),
                    "status": status.strip(),
                }
            )

        return scenarios

    def _status_annotations(self, status: str) -> dict:
        upper = status.upper()
        if upper.startswith("PASS"):
            return {"color": "green", "bold": True}
        if upper.startswith("FAIL"):
            return {"color": "red", "bold": True}
        if upper.startswith("ERROR"):
            return {"color": "red", "bold": True}
        if upper.startswith(("NA", "N/A")):
            return {"color": "gray", "bold": True}
        return {}

    def _summary_text(
        self,
        pass_count: int,
        fail_count: int,
        na_count: int,
        error_count: int,
        total_count: int,
        status: str,
        scenarios: list[dict],
    ) -> str:
        scenario_count = len(scenarios)
        failed_tests = [
            f"{scenario['name']} / {test['name']}"
            for scenario in scenarios
            for test in scenario["tests"]
            if str(test.get("status", "")).upper().startswith(("FAIL", "ERROR"))
        ]

        if fail_count == 0 and error_count == 0:
            outcome = "전체 테스트가 실패 없이 완료되었습니다."
        elif status in ("성공", "완료"):
            sample = ", ".join(failed_tests[:3])
            suffix = " 등" if len(failed_tests) > 3 else ""
            outcome = f"기능 검증 FAIL 항목은 {sample}{suffix}입니다." if sample else "기능 검증 FAIL 항목을 상세 표에서 확인하세요."
        else:
            sample = ", ".join(failed_tests[:3])
            suffix = " 등" if len(failed_tests) > 3 else ""
            outcome = f"실패/오류 항목은 {sample}{suffix}입니다." if sample else "실패/오류 항목을 상세 표에서 확인하세요."

        return "\n".join(
            [
                f"이번 실행은 {scenario_count}개 시나리오, 총 {total_count}개 TC 기준으로 진행되었습니다.",
                f"결과는 {status}이며 PASS {pass_count}건, FAIL {fail_count}건, N/A {na_count}건, ERROR {error_count}건입니다.",
                outcome,
            ]
        )

    def _result_table_block(self, tests: list[dict], is_api: bool = False) -> dict:
        if is_api:
            return self._api_result_table_block(tests)

        rows = [
            {
                "object": "block",
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [self._rich_text("테스트 항목", {"bold": True})],
                        [self._rich_text("테스트 설명", {"bold": True})],
                        [self._rich_text("결과", {"bold": True})],
                    ]
                },
            }
        ]

        for test in tests:
            rows.append(
                {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [self._rich_text(test["name"])],
                            [self._rich_text(test["description"])],
                            [self._rich_text(test["status"], self._status_annotations(test["status"]))],
                        ]
                    },
                }
            )

        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 3,
                "has_column_header": True,
                "has_row_header": False,
                "children": rows,
            },
        }

    def _api_result_table_block(self, tests: list[dict]) -> dict:
        headers = ["테스트 항목", "Method", "Endpoint", "Status Code", "결과", "실패 사유"]
        rows = [
            {
                "object": "block",
                "type": "table_row",
                "table_row": {
                    "cells": [[self._rich_text(header, {"bold": True})] for header in headers]
                },
            }
        ]

        for test in tests:
            status = str(test.get("status") or test.get("result") or "-")
            rows.append(
                {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [self._rich_text(str(test.get("name", "-")))],
                            [self._rich_text(str(test.get("method", "-")))],
                            [self._rich_text(str(test.get("endpoint", "-")))],
                            [self._rich_text(str(test.get("status_code", "-")))],
                            [self._rich_text(status, self._status_annotations(status))],
                            [self._rich_text(str(test.get("reason", "")))],
                        ]
                    },
                }
            )

        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": len(headers),
                "has_column_header": True,
                "has_row_header": False,
                "children": rows,
            },
        }

    def _scenario_detail_children(self, scenario: dict, snapshot_paths: list[str] | None = None) -> list[dict]:
        table_block = self._result_table_block(
            scenario["tests"],
            is_api=scenario.get("type") == "api",
        )
        if scenario.get("type") == "api" or not snapshot_paths:
            return [table_block]

        return [
            {
                "object": "block",
                "type": "column_list",
                "column_list": {
                    "children": [
                        {
                            "object": "block",
                            "type": "column",
                            "column": {
                                "children": [table_block],
                            },
                        },
                        {
                            "object": "block",
                            "type": "column",
                            "column": {
                                "children": self._snapshot_children(snapshot_paths),
                            },
                        },
                    ],
                },
            }
        ]

    def _scenarios_from_results(self, scenario_results: list[dict]) -> list[dict]:
        scenarios = []
        for scenario in scenario_results:
            tests = []
            for item in scenario.get("results", []):
                tests.append(
                    {
                        **item,
                        "description": self._test_case_description(str(item.get("name", ""))),
                    }
                )
            scenarios.append(
                {
                    "name": scenario.get("name", "테스트 결과"),
                    "type": scenario.get("type", "web"),
                    "tests": tests,
                }
            )
        return scenarios

    def _page_children(
        self,
        result_text: str,
        pass_count: int,
        fail_count: int,
        na_count: int,
        error_count: int,
        total_count: int,
        status: str,
        scenario_results: list[dict] | None = None,
        scenario_snapshots: dict[str, list[str]] | None = None,
    ) -> list[dict]:
        scenarios = self._scenarios_from_results(scenario_results) if scenario_results else self._parse_result_text(result_text)
        children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [self._rich_text("테스트 요약")]
                },
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        self._rich_text(
                            self._summary_text(
                                pass_count,
                                fail_count,
                                na_count,
                                error_count,
                                total_count,
                                status,
                                scenarios,
                            )
                        )
                    ],
                    "icon": {
                        "type": "emoji",
                        "emoji": "📌",
                    },
                    "color": "gray_background",
                },
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [self._rich_text("테스트 상세")]
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        self._rich_text(
                            f"상태: {status} | PASS {pass_count} / FAIL {fail_count} / N/A {na_count} / ERROR {error_count} / Total {total_count}"
                        )
                    ]
                },
            },
        ]

        for scenario in scenarios:
            children.append(
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [self._rich_text(scenario["name"])]
                    },
                }
            )
            children.extend(
                self._scenario_detail_children(
                    scenario,
                    scenario_snapshots.get(scenario["name"]) if scenario_snapshots else None,
                )
            )

        return children[:100]

    def _result_summary_text(
        self,
        pass_count: int,
        fail_count: int,
        na_count: int,
        error_count: int,
        total_count: int,
        status: str,
    ) -> str:
        return f"{status} | PASS {pass_count} / FAIL {fail_count} / N/A {na_count} / ERROR {error_count} / Total {total_count}"

    def _execution_failed(self, scenario_results: list[dict] | None, error_count: int) -> bool:
        if error_count > 0:
            return True

        for scenario in scenario_results or []:
            results = scenario.get("results", [])
            if not results:
                return True
            for item in results:
                name = str(item.get("name", ""))
                status = str(item.get("status") or item.get("result") or "")
                if name == "scenario_execution" and status.upper().startswith(("FAIL", "ERROR")):
                    return True

        return False

    def _attachment_children(self, attachment_paths: list[str] | None) -> list[dict]:
        if not attachment_paths:
            return []

        children = [
            {
                "object": "block",
                "type": "divider",
                "divider": {},
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [self._rich_text("첨부 파일")]
                },
            },
        ]

        for attachment_path in attachment_paths:
            path = Path(attachment_path)
            uploaded = self._upload_file(path)
            file_upload = {
                "type": "file_upload",
                "file_upload": {"id": uploaded["id"]},
            }

            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                children.append(
                    {
                        "object": "block",
                        "type": "image",
                        "image": file_upload,
                    }
                )
            else:
                children.append(
                    {
                        "object": "block",
                        "type": "file",
                        "file": {
                            **file_upload,
                            "caption": [self._rich_text(path.name)],
                        },
                    }
                )

        return children

    def _snapshot_children(self, snapshot_paths: list[str]) -> list[dict]:
        children = [
            {
                "object": "block",
                "type": "heading_4",
                "heading_4": {
                    "rich_text": [self._rich_text("스냅샷")]
                },
            }
        ]

        for snapshot_path in snapshot_paths:
            path = Path(snapshot_path)
            uploaded = self._upload_file(path)
            children.append(
                {
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "file_upload",
                        "file_upload": {"id": uploaded["id"]},
                    },
                }
            )

        return children

    def upload_result(
        self,
        title: str,
        version: str,
        platform: str,
        pass_count: int,
        fail_count: int,
        na_count: int,
        total_count: int,
        status: str,
        result_text: str,
        error_count: int = 0,
        scenario_results: list[dict] | None = None,
        scenario_snapshots: dict[str, list[str]] | None = None,
        attachment_paths: list[str] | None = None,
    ):
        title = str(title)
        version = str(version)
        platform = str(platform)
        status = str(status)
        result_text = str(result_text)

        today = datetime.now().strftime("%Y-%m-%d")
        title_name, title_prop = self._property(["제목", "Name", "Title"])
        version_name, version_prop = self._property(["버전", "Version"])
        pass_name, pass_prop = self._property(["PASS", "Pass"])
        fail_name, fail_prop = self._property(["FAIL", "Fail"])
        na_name, na_prop = self._property(["N/ A", "N/A", "NA"])
        total_name, total_prop = self._property(["Total", "TOTAL"])
        result_name, result_prop = self._property(["결과", "Result"])
        execution_failed = self._execution_failed(scenario_results, error_count)
        status = "실패" if execution_failed else "성공"
        test_result_name, test_result_property = self._test_result_property(
            "테스트 실패" if execution_failed else "테스트 성공"
        )
        date_name, date_prop = self._property(["등록일", "날짜", "Date"])
        platform_name, platform_property = self._platform_property(platform)
        status_name, status_property = self._status_property(status)

        children = self._page_children(
            result_text,
            pass_count,
            fail_count,
            na_count,
            error_count,
            total_count,
            status,
            scenario_results=scenario_results,
            scenario_snapshots=scenario_snapshots,
        )

        properties = {
            title_name: self._text_property(title_prop, title),
            version_name: self._text_property(version_prop, version),
            platform_name: platform_property,
            pass_name: self._number_property(pass_prop, pass_count),
            fail_name: self._number_property(fail_prop, fail_count),
            na_name: self._number_property(na_prop, na_count),
            total_name: self._number_property(total_prop, total_count),
            status_name: status_property,
            test_result_name: test_result_property,
            result_name: self._text_property(
                result_prop,
                self._result_summary_text(pass_count, fail_count, na_count, error_count, total_count, status),
            ),
        }
        date_property = self._date_property(date_prop, today)
        if date_property:
            properties[date_name] = date_property

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "children": children,
        }

        page = self._request(
            "POST",
            "https://api.notion.com/v1/pages",
            json=payload,
        )
        self._apply_page_display_options(page["id"])

        if attachment_paths:
            attachment_children = self._attachment_children(attachment_paths)
            if attachment_children:
                self._request(
                    "PATCH",
                    f"https://api.notion.com/v1/blocks/{page['id']}/children",
                    notion_version=FILE_UPLOAD_VERSION,
                    json={"children": attachment_children},
                )

        return page
