"""每个 handler 模块必须实现：

    can_handle(url: str) -> bool
        判断本 handler 是否处理该 URL。

    download(url: str, output_path: str) -> tuple[bool, str]
        执行下载。返回 (ok, human_readable_message)。
"""
