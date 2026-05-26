"""
启动脚本
运行山海·云烟 Web服务
"""
import sys
import io
import os
import threading
import time
import webbrowser
from pathlib import Path

import socket


def configure_runtime_paths():
    """配置打包后运行时路径

    重要：此函数必须在打开日志文件和导入其他模块之前调用。
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        # 确保工作目录在exe同级
        try:
            os.chdir(exe_dir)
        except Exception:
            pass


def _get_runtime_log_file() -> Path:
    """Return a stable writable startup log path for dev and packaged runs."""
    try:
        from novel_agent.constants import get_data_dir

        log_dir = get_data_dir() / "logs"
    except Exception:
        root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
        log_dir = root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "agent.log"


# 设置标准输出为 UTF-8 编码，解决 Windows 控制台编码问题
# 在 --noconsole 模式下 sys.stdout/sys.stderr 可能为 None，需兜底处理
if sys.platform == 'win32':
    def _safe_text_stream(stream):
        if stream is None or not hasattr(stream, "isatty"):
            # 仅包装一次，避免二次包装导致底层句柄被关闭
            devnull_binary = open(os.devnull, "wb")
            return io.TextIOWrapper(devnull_binary, encoding="utf-8", errors="replace")
        if isinstance(stream, io.TextIOWrapper):
            # 终端默认可能是 gbk，显式切到 utf-8，避免 UnicodeEncodeError
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            return stream
        if hasattr(stream, "buffer"):
            return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
        return stream

    sys.stdout = _safe_text_stream(sys.stdout)
    sys.stderr = _safe_text_stream(sys.stderr)

# 在打开日志文件前执行路径配置，避免打包EXE把 agent.log 写到启动目录。
configure_runtime_paths()

import logging
from logging.handlers import RotatingFileHandler

RUNTIME_LOG_MAX_BYTES = 2 * 1024 * 1024
RUNTIME_LOG_BACKUP_COUNT = 5
RUNTIME_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def _get_runtime_log_max_bytes() -> int:
    raw = os.getenv("SHANHAI_LOG_MAX_MB", "").strip()
    if not raw:
        return RUNTIME_LOG_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return RUNTIME_LOG_MAX_BYTES
    return max(value, 1) * 1024 * 1024


def _get_runtime_log_backup_count() -> int:
    raw = os.getenv("SHANHAI_LOG_BACKUP_COUNT", "").strip()
    if not raw:
        return RUNTIME_LOG_BACKUP_COUNT
    try:
        value = int(raw)
    except ValueError:
        return RUNTIME_LOG_BACKUP_COUNT
    return min(max(value, 1), 20)


def _build_runtime_log_handlers():
    file_handler = RotatingFileHandler(
        _get_runtime_log_file(),
        maxBytes=_get_runtime_log_max_bytes(),
        backupCount=_get_runtime_log_backup_count(),
        encoding='utf-8',
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    return [file_handler, stream_handler]


# 配置根日志 - 打包版长期运行时按大小轮转，避免 agent.log 无限增长。
logging.basicConfig(
    level=logging.INFO,
    format=RUNTIME_LOG_FORMAT,
    handlers=_build_runtime_log_handlers()
)
logger = logging.getLogger(__name__)

from novel_agent.version import get_app_version
# 不要直接替换 uvicorn 的 handler。
# uvicorn 的 AccessFormatter 依赖特定参数结构，强制复用根 handler 会导致
# "ValueError: not enough values to unpack" 并刷屏日志。
logging.getLogger("uvicorn").propagate = True
logging.getLogger("uvicorn.error").propagate = True
logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("uvicorn.access").propagate = False

for noisy_logger_name in (
    "httpx",
    "httpcore",
    "openai",
    "urllib3",
    "watchfiles",
    "ddgs",
    "chromadb",
):
    logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)

# 确保能找到模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_env():
    """检查环境配置"""
    from dotenv import load_dotenv
    load_dotenv()
    return True

def check_write_permission():
    """检查数据目录写入权限"""
    from novel_agent.constants import get_data_dir
    from pathlib import Path
    
    try:
        data_dir = get_data_dir()
        test_file = Path(data_dir) / ".write_test"
        
        # 尝试写入测试文件
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        
        logger.info(f"数据目录写入权限检查通过: {data_dir}")
        return True
        
    except Exception as e:
        logger.error(f"数据目录写入权限检查失败: {e}")
        print(f"\n{'='*60}")
        print(f"[错误] 无法写入数据目录")
        print(f"{'='*60}")
        print(f"目录: {data_dir}")
        print(f"错误: {e}")
        print(f"\n可能的原因:")
        print(f"  1. 程序位于受保护的目录（如 C:\\Program Files）")
        print(f"  2. 目录权限不足")
        print(f"  3. 磁盘空间不足")
        print(f"\n建议:")
        print(f"  • 将程序移动到有写入权限的目录")
        print(f"    （如桌面、文档文件夹或 D:\\）")
        print(f"  • 以管理员身份运行（不推荐）")
        print(f"{'='*60}\n")
        
        return False

def find_available_port(start_port: int, max_retries: int = 10) -> int:
    """寻找可用端口"""
    for port in range(start_port, start_port + max_retries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find an available port in range {start_port}-{start_port + max_retries}")

def open_browser(port: int, delay: float = 1.5):
    """延迟打开浏览器"""
    time.sleep(delay)
    url = f"http://localhost:{port}"
    try:
        webbrowser.open(url)
        print(f"\n[自动打开浏览器] {url}")
    except Exception as e:
        print(f"\n[提示] 请手动打开浏览器访问: {url}")

def main():
    """主函数"""
    try:
        try:
            import uvicorn
        except ModuleNotFoundError as exc:
            if exc.name == "uvicorn":
                logger.critical(
                    "Missing required dependency '%s' for interpreter %s",
                    exc.name,
                    sys.executable,
                )
            raise
        from novel_agent.config import config
        from novel_agent.web import create_app

        # 检查配置
        check_env()
        
        # 检查写入权限（打包环境特别重要）
        if not check_write_permission():
            print("\n按任意键退出...")
            try:
                input()
            except:
                pass
            sys.exit(1)
        
        # 初始化
        config.init()
        
        # 自动寻找可用端口
        base_port = config.server.port
        port = find_available_port(base_port)
        
        if port != base_port:
            print(f"\n[注意] 端口 {base_port} 被占用，自动切换到 {port}")
        
        app_version = get_app_version()

        print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║   ✨ 山海·云烟 v{app_version} - 山海入云烟                             ║
    ║                                                              ║
    ║   智能小说创作系统                                           ║
    ║   采用 Coordinator-Worker 多Agent协作架构                    ║
    ║                                                              ║
    ║   🌐 访问地址: http://localhost:{port}                              ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
        """)
        
        # 创建应用
        app = create_app()
        
        # 启动浏览器打开线程（延迟1.5秒等待服务器启动）
        browser_thread = threading.Thread(target=open_browser, args=(port,), daemon=True)
        browser_thread.start()
        
        # 启动服务
        uvicorn.run(
            app,
            host=config.server.host,
            port=port,
            log_level="info",
            # 使用当前进程的 logging.basicConfig，避免 uvicorn AccessFormatter 误配导致日志解包异常
            log_config=None
        )
    except Exception as e:
        logger.critical(f"Critical error during startup: {e}", exc_info=True)
        # 尝试写入独立错误日志，以防agent.log都写入失败
        try:
            with open("startup_error.txt", "w", encoding="utf-8") as f:
                import traceback
                f.write(f"Python executable: {sys.executable}\n")
                f.write(f"Working directory: {os.getcwd()}\n")
                f.write(f"Startup failed: {e}\n")
                if isinstance(e, ModuleNotFoundError):
                    missing_name = getattr(e, "name", None) or "unknown"
                    # 检测是否为打包环境（便携版EXE不是Python解释器）
                    is_packaged = getattr(sys, 'frozen', False) or not sys.executable.lower().endswith('python.exe')
                    if is_packaged:
                        f.write(
                            f"Suggested fix: 请重新下载最新便携版，或联系技术支持\n"
                            f"  # missing module: {missing_name}\n"
                        )
                    else:
                        f.write(
                            f"Suggested fix: \"{sys.executable}\" -m pip install -r requirements.txt"
                            f"  # missing: {missing_name}\n"
                        )
                f.write("\n")
                f.write(traceback.format_exc())
        except Exception as write_error:
            logger.error(f"Failed to write startup_error.txt: {write_error}")
        raise e

if __name__ == "__main__":
    main()
