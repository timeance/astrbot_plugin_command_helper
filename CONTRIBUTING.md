# 贡献指南

## 反馈问题

请在 [Issues](https://github.com/timeance/astrbot_plugin_command_helper/issues) 中说明：

- 插件、AstrBot、Python 和平台适配器版本。
- 触发问题的输入、是否真正 @机器人、预期回复与实际回复。
- 复现步骤、相关配置和日志。删除访问令牌、验证码及个人信息，用测试参数替代。

命令未被识别时，请补充目标插件及处理器方法名，说明是否使用了自定义过滤器或命令重命名。

## 开发环境

使用 Python 3.12，在虚拟环境中安装测试依赖：

```sh
python -m pip install -r requirements-dev.txt -r tests/requirements-framework.txt
```

测试需要 AstrBot 源码及其导入依赖，但不启动机器人、不连接模型或 QQ。下面以 Bash 和 4.28.0 为例，在仓库目录执行：

```sh
git clone --depth 1 --branch v4.28.0 https://github.com/AstrBotDevs/AstrBot ../AstrBot-test
export PYTHONPATH="$(cd ../AstrBot-test && pwd)"
export ASTRBOT_ROOT="$(mktemp -d)"
python -m pytest -q --ignore=tests/test_phcraft_framework.py
python -m ruff check .
python -m ruff format --check .
```

公开 CI 运行通用分派和适配规则测试，不依赖其他业务插件的源码。两个 AstrBot 版本及固定提交见 [CI 配置](.github/workflows/ci.yml)。CI 不允许跳过测试。

`test_phcraft_framework.py` 是本地可选的真实适配集成测试。已有对应源码及访问权限时，安装其依赖，并将 `PHCRAFT_SOURCE` 设为源码的绝对路径后运行：

```sh
python -m pip install -r "$PHCRAFT_SOURCE/requirements.txt"
python -m pytest -q tests/test_phcraft_framework.py
```

本地未指定源码时，这组测试会跳过。

修改消息处理时，至少检查正确命令放行、错误提醒只发一次、权限与会话范围、冷却期阻止聊天。不要用伪造的 AstrBot 模块替代分派测试；模型回复可以模拟，真实模型和 QQ 收发需单独验收。

## 提交 PR

从 `main` 创建分支，向 `main` 提交 PR，说明问题、改动和验证结果。行为或配置变化时同步更新 README 和 CHANGELOG。不要提交本地配置、令牌、聊天记录、缓存或构建产物。

CI 检查代码格式、安装包和框架测试。检查通过后由维护者审阅、合并，不自动发布。

## 打包

```sh
python scripts/package.py
```

`dist/` 中生成安装 ZIP 和 SHA-256 文件。脚本核对文件清单和 ZIP 完整性。已经对外发布的安装包不覆盖；后续修复递增版本。

贡献沿用仓库的 [MIT 许可证](LICENSE)。
