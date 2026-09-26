"""轨道电路业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "track"
MEASURE_MODULE = "measure"
REQUIRED_FIELDS = ["设备编号", "制式类型", "区段长度"]
STATUS_ORDER = ["待测试", "运用正常", "分路不良", "已更换"]
# 结论 -> 目标状态：判定必须与实际测试结论一致，确认正常只能回到运用正常。
CONCLUSION_RULES = {"合格": "运用正常", "不合格": "分路不良"}
# 每个动作允许的起始状态：已提交测试的设备不允许再被打回待测试。
ACTION_SOURCES = {
    "提交测试": {"待测试", "分路不良"},
    "确认正常": {"分路不良"},
    "更换设备": {"待测试", "运用正常", "分路不良"},
}
ABNORMAL_STATUS = "分路不良"
PENDING_STATUS = "待测试"
REPLACED_STATUS = "已更换"
DISPLAY_STATUS_FIELD = "设备状态"
TEST_PROJECT_KEYWORD = "分路灵敏度"


class TrackService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._with_latest_test(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summarize(self, *, keyword: str | None = None, status: str | None = None) -> dict[str, int]:
        """按当前筛选条件（即当前列表口径）实时重算统计，不使用缓存计数。"""
        rows = [self._with_latest_test(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return {
            "在运轨道电路": sum(1 for row in rows if row.get("status") != REPLACED_STATUS),
            "分路不良区段": sum(1 for row in rows if row.get("status") == ABNORMAL_STATUS),
            "待测试设备": sum(1 for row in rows if row.get("status") == PENDING_STATUS),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._with_latest_test(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_STATUS_FIELD] = entry["status"]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"轨道电路 {entry_id} 不存在或已归档"
        if action not in ACTION_SOURCES:
            return None, f"动作「{action}」不属于轨道电路可执行范围"
        current = str(entry.get("status") or "")
        if current not in ACTION_SOURCES[action]:
            allowed = "、".join(
                name for name in STATUS_ORDER if name in ACTION_SOURCES[action]
            )
            return None, f"当前状态「{current}」不允许{action}，仅{allowed}状态可操作"

        values = values or {}
        if action == "提交测试":
            target, message = self._submit_test(entry, values)
            if target is None:
                return None, message
        elif action == "确认正常":
            target = "运用正常"
            message = "轨道电路已确认正常，恢复运用正常"
        else:  # 更换设备：老动作照旧
            target = REPLACED_STATUS
            message = "轨道电路已更换"

        entry["status"] = target
        entry[DISPLAY_STATUS_FIELD] = target
        entry["pending"] = target == PENDING_STATUS
        entry["abnormal"] = target == ABNORMAL_STATUS
        return self._with_latest_test(entry), message

    # ---- 内部辅助 ---------------------------------------------------------

    def _submit_test(
        self,
        entry: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[str | None, str]:
        """落一条测试记录，并以测试结论决定运用正常/分路不良。"""
        sensitivity = str(values.get("分路灵敏度") or "").strip()
        conclusion = str(values.get("测试结论") or "").strip()
        if not conclusion:
            # 页面未带结论时，以该设备最新一条测试记录的结论为准
            latest = self._latest_test(entry)
            conclusion = str(latest.get("测试结论") or "") if latest else ""
        if conclusion not in CONCLUSION_RULES:
            return None, "测试结论必须是「合格」或「不合格」，无法据此判定设备状态"
        target = CONCLUSION_RULES[conclusion]

        today = date.today().isoformat()
        measure_rows = store.rows(MEASURE_MODULE)
        record = {
            "id": max((int(row.get("id", 0)) for row in measure_rows), default=0) + 1,
            "测试单号": f"MEAS-T{int(entry.get('id', 0)):04d}-{len(measure_rows) + 1:02d}",
            "测试项目": f"轨道电路{TEST_PROJECT_KEYWORD}测试",
            "测试设备": entry.get("设备编号"),
            "测试值": sensitivity or None,
            "标准范围": str(values.get("标准范围") or "分路残压 ≤ 0.15Ω"),
            "测试结论": conclusion,
            "测试人员": str(values.get("测试人员") or "值班测试员"),
            "测试状态": "合格" if conclusion == "合格" else "不合格",
            "status": "合格" if conclusion == "合格" else "不合格",
            "pending": False,
            "abnormal": conclusion == "不合格",
        }
        measure_rows.append(record)
        if sensitivity:
            entry["分路灵敏度"] = sensitivity
        entry["上次测试日"] = today
        verdict = "分路不良" if target == ABNORMAL_STATUS else "运用正常"
        return target, f"测试结论为「{conclusion}」，轨道电路判定为{verdict}"

    def _latest_test(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """找该设备最新一条分路灵敏度测试记录。"""
        device = str(entry.get("设备编号") or "")
        candidates = [
            row for row in store.rows(MEASURE_MODULE)
            if str(row.get("测试设备") or "") == device
            and TEST_PROJECT_KEYWORD in str(row.get("测试项目") or "")
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda row: int(row.get("id", 0)))

    def _with_latest_test(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表/详情展示：分路灵敏度取最新测试记录的实测值，与实际测试记录对得上。"""
        view = dict(entry)
        latest = self._latest_test(entry)
        if latest is not None:
            measured = latest.get("测试值")
            if measured not in (None, ""):
                view["分路灵敏度"] = measured
        # 设备状态列永远以 status 为准，避免详情/列表与真实状态不同步
        view[DISPLAY_STATUS_FIELD] = entry.get("status")
        return view
