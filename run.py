"""
启动脚本
运行文思Agent Web服务
"""
import sys
import io
import threading
import time
import webbrowser

# 设置标准输出为 UTF-8 编码，解决 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os

# 确保能找到模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_env():
    """检查环境配置"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # 不再强制检查API Key，允许在前端配置
    return True

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
    import uvicorn
    from novel_agent.config import config
    from novel_agent.web import create_app
    
    # 检查配置
    check_env()
    
    # 初始化
    config.init()
    
    port = config.server.port
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ✨ 文思Agent v1.0 - 文思如泉涌                             ║
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
        log_level="info"
    )

if __name__ == "__main__":
    main()
