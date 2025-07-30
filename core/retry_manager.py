import asyncio
import functools
import logging
from typing import Any, Callable, Optional, Tuple, Type

from .exceptions import UnhandledException

log = logging.getLogger(__name__)


def with_retries(
    max_retries: int = 3,
    initial_delay: int = 1,
    backoff: int = 2,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
):
    """
    一个装饰器，为异步函数提供指数退避重试逻辑。

    Args:
        max_retries (int): 最大重试次数。
        initial_delay (int): 初始延迟秒数。
        backoff (int): 每次重试后延迟的乘数。
        retry_on (Optional[Tuple[Type[Exception], ...]]):
            一个异常类型的元组，应该触发重试。
            如果为 None，则默认重试所有 Exception 的子类。
    """
    if retry_on is None:
        retry_on = (Exception,)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """
            包装函数，实现重试逻辑。
            """
            # 将 RetryManager 的实例化移到这里，确保每次调用都使用新的实例
            retry_manager = RetryManager(
                max_retries=max_retries,
                initial_delay=initial_delay,
                backoff=backoff,
                retry_on=retry_on,
            )
            return await retry_manager.execute_with_retries(func, *args, **kwargs)

        return wrapper

    return decorator


class RetryManager:
    """
    管理具有指数退避策略的重试逻辑。
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: int = 1,
        backoff: int = 2,
        retry_on: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """
        初始化 RetryManager。

        Args:
            max_retries (int): 最大重试次数。
            initial_delay (int): 初始延迟秒数。
            backoff (int): 每次重试后延迟的乘数。
            retry_on (Tuple[Type[Exception], ...]):
                应该触发重试的异常元组。
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff = backoff
        self.retry_on = retry_on
        self.attempts = 0
        self.delay = initial_delay

    async def execute_with_retries(self, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        执行一个操作，如果失败则根据策略重试。

        Args:
            operation: 要执行的异步函数。
            *args: 传递给操作的位置参数。
            **kwargs: 传递给操作的关键字参数。

        Returns:
            操作成功时的返回值。

        Raises:
            Exception: 如果所有重试都失败，则重新引发最后的异常。
        """
        while self.attempts < self.max_retries:
            self.attempts += 1
            try:
                result = await operation(*args, **kwargs)
                if self.attempts > 1:
                    log.info(f"操作在第 {self.attempts} 次尝试时成功。")
                return result
            except self.retry_on as e:
                if self.attempts >= self.max_retries:
                    log.error(
                        f"操作失败，已达到最大重试次数 ({self.max_retries})。最后一次错误: {e}",
                        exc_info=True,
                    )
                    raise e

                log.warning(
                    f"操作失败 (尝试 {self.attempts}/{self.max_retries}): {e}。将在 {self.delay:.2f} 秒后重试..."
                )

                # 在重试前执行异步延迟
                await asyncio.sleep(self.delay)

                # 更新下一次重试的延迟
                self.delay *= self.backoff
            except Exception as e:
                # 捕获不应重试的异常
                log.warning(f"捕获到未处理的异常，将立即失败: {e}", exc_info=False)
                # 将其包装在一个特定的异常类型中，以便上层可以识别它
                raise UnhandledException(f"操作失败，出现非重试错误: {e}") from e

        # 如果循环结束但没有成功，这是个意外情况
        raise RuntimeError("重试逻辑出现意外错误，所有尝试均已用尽但未成功也未引发异常。")
