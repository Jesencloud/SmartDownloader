# 更新日志
 ## 2025年7月10日

### 新增功能与改进

   0 *   **网络重试策略优化（熔断机制）**：
   1     *   在 `downloader.py`
      中引入了熔断机制。当网络请求连续失败达到预设阈值时，熔断器将打开，后续请求会快速失败，避免长时间无效
      重试。
   2     *   熔断器的连续失败阈值和打开时长现在可以通过 `config.yaml` 进行配置。
   3 *   **可配置的错误重试模式**：
   4     *   `downloader.py` 中用于判断是否需要重试的网络错误模式（`retry_patterns` 和 `proxy_patterns`
      ）已从硬编码列表提取到 `config.yaml` 中，提高了可维护性和适应性。
   5 *   **可配置的 Whisper 模型路径**：
   6     *   `subtitles.py` 中 Whisper 模型的加载路径不再硬编码，现在可以通过 `config.yaml`
      进行配置，以适应用户不同的模型存储位置。
   7 *   **代码结构优化（职责分离）**：
   8     *   将 `main.py` 中混合的业务逻辑和工具函数进行了拆分。
   9     *   创建了 `utils.py`
      文件，用于存放通用的辅助函数（如日志设置、输入获取、媒体文件判断、音频提取和文件名清理）。
   10     *   创建了 `handlers.py`
      文件，用于存放核心业务逻辑处理函数（如处理本地文件、保存元数据信息和处理下载项）。
   11     *   `main.py` 现在主要负责参数解析和流程协调，代码结构更加清晰。
   12 *   **子进程调用逻辑复用**：
   13     *   在 `downloader.py` 中，将 `_run_subprocess_with_progress` 和 `_run_subprocess`
      中重复的重试、延迟计算和错误判断逻辑提取到一个新的公共辅助函数 `_execute_subprocess_with_retries`
      中，减少了代码重复。
   14 *   **错误日志增强**：
   15     *   `handlers.py` 中 `save_info` 函数在处理 JSON
      失败时，错误日志现在会包含导致错误的具体文件名，方便问题排查。
   16 *   **类型提示完善**：
   17     *   对 `main.py`、`downloader.py`、`subtitles.py` 和 `config_manager.py`
      中的多个函数和方法添加或完善了类型提示，提高了代码的可读性和可维护性。
   18 
   19 ### Bug 修复
   20 
   21 *   **Bug 1: 中文字幕文件内容错误或未生成**
   22     *   **问题原因**：`subtitles.py` 中用于从英文 SRT 文件提取文本块的正则表达式不准确，导致
      `deep-translator` 接收到的文本为空或不正确。此外，`re.sub` 在将翻译后的内容替换回原始 SRT
      结构时也存在逻辑缺陷。
   23     *   **修复方法**：
   24         *   修正了 `subtitles.py` 中提取字幕文本的正则表达式，确保能准确捕获内容。
   25         *   放弃了 `re.sub` 的复杂替换方式，改为在 `_translate`
      函数中手动迭代字幕块，并精确地将翻译后的中文文本插入到新的 SRT 内容中，确保替换的正确性。
   26 *   **Bug 2: `SyntaxError: unterminated string literal` (多处)**
   27     *   **问题原因**：在多次修改 `subtitles.py` 和 `downloader.py` 中的正则表达式或 f-string
      时，由于传递给 `replace` 工具的 `new_string` 参数中的换行符 (`\n`) 未正确转义，导致写入文件后 Python
      语法错误。
   28     *   **修复方法**：确保所有传递给 `replace` 工具的 `new_string` 参数中的特殊字符（特别是 `\` 和
      `\n`）都进行了正确的双重转义（例如 `\n` 写为 `\\n`），以保证写入文件后的 Python
      代码是合法的字符串字面量。
   29 *   **Bug 3: `AttributeError: module 'asyncio' has no attribute 'Process'`**
   30     *   **问题原因**：`downloader.py` 中 `_execute_subprocess_with_retries` 函数的返回类型提示错误，
      `asyncio.create_subprocess_exec` 返回的是 `asyncio.subprocess.Process` 对象，而非 `asyncio.Process`。
   31     *   **修复方法**：将 `_execute_subprocess_with_retries` 的返回类型提示修正为
      `asyncio.subprocess.Process`。
   32 *   **Bug 4: `mypy` 报告 `StreamReader | None` 属性访问错误**
   33     *   **问题原因**：`mypy` 无法确定 `asyncio.subprocess.Process` 对象的 `stdout` 和 `stderr`
      属性在类型提示中是否为 `None`，即使在实际运行时它们通常不为 `None`。
   34     *   **修复方法**：在访问 `process.stdout` 和 `process.stderr` 之前，添加 `assert` 语句（例如
      `assert process.stdout is not None`），明确告诉 `mypy` 在该点这些变量不会是 `None`。同时，在
      `_execute_subprocess_with_retries` 中，根据 `stdout_pipe` 和 `stderr_pipe` 的具体值（`PIPE` 或
      `STDOUT`）有条件地进行 `assert`，避免在 `stderr` 被重定向到 `stdout` 时出现不必要的 `AssertionError`
      。
   35 *   **Bug 5: `Module has no attribute "os"` (在 `handlers.py` 中)**
   36     *   **问题原因**：尽管 `handlers.py` 中导入了 `os` 模块，但 `mypy` 仍然报告 `os` 模块没有
      `remove` 属性。这可能是 `mypy` 在处理 `aiofiles.os` 这种特殊导入方式时出现的解析问题。
   37     *   **修复方法**：将 `handlers.py` 中对 `aiofiles.os` 的导入方式改为 `import aiofiles.os as aos`
      ，并将所有 `aiofiles.os.remove` 的调用替换为 `aos.remove`。这种显式别名的方式帮助 `mypy` 正确识别了
      `aos` 提供的功能。
   38 *   **Bug 6: `AssertionError` (在 `downloader.py` 中，当 `stderr_pipe` 为 `asyncio.subprocess.STDOUT`
      时)**
   39     *   **问题原因**：在 `_execute_subprocess_with_retries` 中，即使 `stderr` 被重定向到 `stdout`
      导致 `process.stderr` 为 `None`，`assert process.stderr is not None` 仍然会被执行，从而引发
      `AssertionError`。
   40     *   **修复方法**：修改 `_execute_subprocess_with_retries` 中的 `assert` 逻辑，使其仅在
      `stderr_pipe` 明确设置为 `asyncio.subprocess.PIPE` 时才断言 `process.stderr` 不为 `None`。


