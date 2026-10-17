# -*- coding: utf-8 -*-
"""批量任务结果累积器 —— 把「逐文件成败」汇总为单一 TaskResult。

规则（M2.1 约定）：
    * 全部成功 -> SUCCESS；
    * 全部失败 -> FAILED；
    * 有成功也有失败 -> PARTIAL（message 汇总成功/失败数）；
    * 没有任何输入（既无成功也无失败）-> FAILED。
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .result import TaskResult
from .status import TaskStatus


@dataclass
class TaskReport:
    """按文件/子任务累积结果，最后 ``finalize()`` 成 TaskResult。"""

    details: dict = field(default_factory=dict)
    _success_count: int = field(default=0, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _outputs: List[str] = field(default_factory=list, init=False, repr=False)
    _failures: List[str] = field(default_factory=list, init=False, repr=False)
    _exit_codes: List[int] = field(default_factory=list, init=False, repr=False)
    _warnings: List[str] = field(default_factory=list, init=False, repr=False)

    # ----------------------------------------------------------------
    # 累积
    # ----------------------------------------------------------------

    def add_success(self, output: Optional[str] = None) -> None:
        """记录一个成功项；``output`` 非空时计入产出列表。"""
        self._success_count += 1
        if output:
            self._outputs.append(output)

    def add_failure(self, message: str, exit_code: Optional[int] = None) -> None:
        """记录一个失败项（message 为可读原因）。"""
        self._failure_count += 1
        self._failures.append(str(message))
        if exit_code is not None:
            self._exit_codes.append(exit_code)

    def warn(self, message: str) -> None:
        """记录一条不阻断成功的警告。"""
        self._warnings.append(str(message))

    # ----------------------------------------------------------------
    # 查询
    # ----------------------------------------------------------------

    @property
    def success_count(self) -> int:
        return self._success_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def has_successes(self) -> bool:
        return self._success_count > 0

    @property
    def has_failures(self) -> bool:
        return self._failure_count > 0

    @property
    def failures(self):
        """失败原因列表（tuple）。"""
        return tuple(self._failures)

    @property
    def warnings(self):
        """警告列表（tuple）。"""
        return tuple(self._warnings)

    # ----------------------------------------------------------------
    # 汇总
    # ----------------------------------------------------------------

    def finalize(self) -> TaskResult:
        """把累积结果汇总为一个 TaskResult。"""
        details = dict(self.details)
        details.update({
            "success_count": self._success_count,
            "failure_count": self._failure_count,
        })

        if self._success_count == 0 and self._failure_count == 0:
            return TaskResult.failed(
                "没有可处理的任务输入",
                warnings=self._warnings,
                details=details,
            )

        if self._failure_count == 0:
            message = (
                f"全部成功（{self._success_count} 个）"
                if self._success_count > 1 else ""
            )
            return TaskResult.ok(
                message,
                outputs=self._outputs,
                warnings=self._warnings,
                details=details,
            )

        if self._success_count == 0:
            message = f"全部失败（{self._failure_count} 个）: {self._failures[0]}"
            details["failures"] = tuple(self._failures)
            return TaskResult.failed(
                message,
                exit_code=self._exit_codes[0] if self._exit_codes else None,
                warnings=self._warnings,
                details=details,
            )

        message = f"成功 {self._success_count} 个, 失败 {self._failure_count} 个"
        details["failures"] = tuple(self._failures)
        return TaskResult.partial(
            message,
            outputs=self._outputs,
            warnings=self._warnings,
            details=details,
        )

    # 便捷属性：当前累积态（尚未 finalize 时的近似状态）
    @property
    def status(self) -> TaskStatus:
        if self._success_count == 0 and self._failure_count == 0:
            return TaskStatus.FAILED
        if self._failure_count == 0:
            return TaskStatus.SUCCESS
        if self._success_count == 0:
            return TaskStatus.FAILED
        return TaskStatus.PARTIAL
