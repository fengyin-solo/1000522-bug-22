"""轨道电路业务规则：状态流转、字段校验与筛选口径都收在这里。

判定口径与实际测试记录保持一致：
- 「确认正常」只把设备置回「运用正常」；
- 「提交测试」以最新一条分路灵敏度测试记录的结论判定合格/不合格；
- 任何动作都不允许把设备改回「待测试」；
- 列表与详情共用同一份口径，分路灵敏度取自最新测试记录，设备状态与内部状态同步。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "track"
MEASURE_MODULE = "measure"
REQUIRED_FIELDS = ["设备编号", "制式类型", "区段长度"]
STATUS_ORDER = ["待测试", "运用正常", "分路不良", "已更换"]
FIRST_STATUS = "待测试"
ACTIVE_STATUSES = ["运用正常", "分路不良"]
BAD_STATUS = "分路不良"
REPLACED_STATUS = "已更换"
# 更换设备是终态动作，按老规则照旧保留；其余动作见 run_action 里的显式流转。
ACTION_RULES = {"更换设备": REPLACED_STATUS}
SENSITIVITY_ITEM = "分路灵敏度"

LIST_FIELDS = ["设备编号", "制式类型", "区段长度", "分路灵敏度", "所属区段", "上次测试日", "下次测试日", "设备状态"]


def _latest_test(entry: dict[str, Any]) -> dict[str, Any] | None:
    """取该设备最新一条分路灵敏度测试记录（编号最大视为最新）。"""
    device_code = str(entry.get("设备编号", ""))
    matches: list[dict[str, Any]] = []
    for test in store.rows(MEASURE_MODULE):
        if str(test.get("测试设备", "")).strip() != device_code:
            continue
        if SENSITIVITY_ITEM not in str(test.get("测试项目", "")):
            continue
        matches.append(test)
    if not matches:
        return None
    return max(matches, key=lambda row: int(row.get("id", 0)))


def _test_conclusion(test: dict[str, Any]) -> str:
    """把测试单状态收敛成合格 / 不合格 / 空（测试尚未完成）。"""
    status = str(test.get("status") or "").strip()
    if status == "合格":
        return "合格"
    if status == "不合格":
        return "不合格"
    return ""


class TrackService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._present(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._present(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = FIRST_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        entry["设备状态"] = FIRST_STATUS
        rows.append(entry)
        return self._present(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"轨道电路 {entry_id} 不存在或已归档"

        target = self._resolve_target(entry, action)
        if target is None:
            return None, self._reject_message(action)
        if target == FIRST_STATUS:
            # 提交测试后只能落到判定结论，禁止回退成待测试。
            return None, "设备已提交测试，不能改回待测试"
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        entry["status"] = target
        entry["pending"] = target == FIRST_STATUS
        entry["abnormal"] = target == BAD_STATUS
        entry["设备状态"] = target
        return self._present(entry), f"轨道电路已{action}"

    def _resolve_target(self, entry: dict[str, Any], action: str) -> str | None:
        if action in ACTION_RULES:
            return ACTION_RULES[action]
        if action == "确认正常":
            return "运用正常"
        if action == "提交测试":
            test = _latest_test(entry)
            conclusion = _test_conclusion(test) if test else ""
            if not conclusion:
                return None
            return "运用正常" if conclusion == "合格" else BAD_STATUS
        return None

    @staticmethod
    def _reject_message(action: str) -> str:
        if action == "提交测试":
            return "该设备暂无分路灵敏度测试结论，待测试记录形成合格/不合格结论后再提交"
        return f"动作「{action}」不属于轨道电路可执行范围"

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表与详情共用的展示口径：状态字段与测试记录对齐。"""
        view = dict(entry)
        status = str(entry.get("status") or FIRST_STATUS)
        view["status"] = status
        view["设备状态"] = status
        view["pending"] = status == FIRST_STATUS
        view["abnormal"] = status == BAD_STATUS

        test = _latest_test(entry)
        view["测试结论"] = ""
        if test is not None:
            measured = str(test.get("测试值") or "").strip()
            if measured:
                view["分路灵敏度"] = measured
            conclusion = _test_conclusion(test)
            if conclusion:
                view["测试结论"] = conclusion
        return view

    def summarize(self, rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
        """按给定列表实时统计；不传则统计全量。"""
        rows = store.rows(MODULE) if rows is None else rows
        return {
            "在运轨道电路": sum(1 for row in rows if row.get("status") in ACTIVE_STATUSES),
            "分路不良区段": sum(1 for row in rows if row.get("status") == BAD_STATUS),
            "待测试设备": sum(1 for row in rows if row.get("status") == FIRST_STATUS),
        }
