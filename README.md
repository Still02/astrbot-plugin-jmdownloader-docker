[简体中文](README.md) | [English](README_EN.md)

# astrbot-plugin-jmdownloader-docker

**AstrBot 的 jmdownloader 插件 Linux 云服务器 / Docker 双容器兼容性适配版**

基于 [CLRedfield 的 `astrbot-plugin-jmdownloader`](https://github.com/CLRedfield/astrbot-plugin-jmdownloader) 进行修改，主要解决 AstrBot 与 NapCat 分别部署在 Linux Docker 容器时可能出现的文件路径不可访问、文件权限不足等问题。

> **项目说明**
>
> 本仓库是针对 Linux 云服务器部署环境的个人兼容性修改版本，并非原项目官方版本。
>
> 原插件功能及主要代码归原作者所有。本项目主要记录 Docker 文件共享与 Linux 权限兼容方面的修改。

## 1. 项目背景

在 Windows 本地部署中，AstrBot 和 NapCat 通常能够访问相同的本地文件路径。

但迁移到 Linux 云服务器后，如果 AstrBot 和 NapCat 分别运行在独立的 Docker 容器中，两者的文件系统默认相互隔离。

这可能导致以下问题：

- AstrBot 已经成功生成文件，但 NapCat 无法读取。
- OneBot 文件接口返回 `retcode=1200`。
- 日志提示 `识别URL失败`。
- 即使配置了 Docker 共享目录，仍然出现 `EACCES: permission denied`。

本修改版主要针对上述环境兼容性问题进行调整。

## 2. 主要修改

### 2.1 Docker 共享目录兼容

原实现使用 Python 默认临时目录：

```python
TEMP_ROOT = Path(tempfile.gettempdir()) / "astrbot_jmdownloader"
```

在 Linux 容器中，默认位置通常位于 `/tmp`。

由于两个 Docker 容器的 `/tmp` 并不共享，可能导致文件访问失败。

修改后的临时文件根目录为：

```text
/AstrBot/data/pdf_uploads/
```

该目录需要同时对 AstrBot 和 NapCat 容器可见。

### 2.2 Linux 文件权限兼容

Python 的 `tempfile.mkdtemp()` 通常创建权限为 `0700` 的临时目录。

当 AstrBot 和 NapCat 使用不同的 Linux 用户身份运行时，可能出现目录可以共享，但 NapCat 无法读取其中内容的情况。

本修改版针对临时目录的访问权限进行了兼容性处理。

**注意：** 不建议通过 `chmod -R 777` 放开整个 AstrBot 数据目录。应仅对必要目录授予适当权限。

### 2.3 临时文件管理

本修改版保留原项目的任务隔离与临时文件管理机制，包括：

- 为每个任务创建独立的临时目录。
- 自动创建所需的文件夹。
- 任务结束后安排异步清理，延迟约 10 分钟删除临时目录。
- 保留过期任务清理机制，在插件初始化或新任务开始时清理符合条件的旧目录。

**注意：** 延迟清理任务依赖 AstrBot 进程持续运行。如果进程在清理执行前重启，该异步任务将被取消，剩余临时文件需要由后续的过期清理机制处理。

## 3. 适用环境

本修改主要面向以下部署场景：

| 项目 | 环境 |
|---|---|
| 操作系统 | Linux / Ubuntu |
| 容器环境 | Docker |
| AstrBot | 独立 Docker 容器 |
| NapCat | 独立 Docker 容器 |
| 通信方式 | OneBot v11 / WebSocket |
| 文件共享 | Docker Bind Mount |

**测试背景：** Ubuntu 云服务器、AstrBot v4.29.4、独立 AstrBot 与 NapCat Docker 容器。

其他部署环境尚未进行全面验证。

## 4. Docker 共享目录说明

在双容器部署中，两个容器应能够访问相同的宿主机目录。

示例结构：

```text
Host shared directory
          │
    ┌─────┴─────┐
    │           │
 AstrBot      NapCat
    │           │
/AstrBot/data /AstrBot/data
```

两个容器内的挂载路径保持一致，可以减少跨容器文件路径转换问题。

部署前还需要确认：

- 共享目录实际存在。
- 两个容器均已挂载该目录。
- 文件所有权及权限满足访问要求。
- 文件在被读取之前没有提前删除。

## 5. 常见错误

### `retcode=1200`：识别 URL 失败

可能原因：

- 文件保存在某个容器独有的目录。
- 接收文件路径的容器无法访问该位置。
- 文件接口无法识别传入的路径格式。

### `EACCES: permission denied`

可能原因：

- 临时目录访问权限不足。
- 容器之间运行用户的 UID/GID 不一致。
- 父目录缺少必要的进入权限。
- 目标文件本身缺少读取权限。

### 文件不存在

可能原因：

- 临时文件已被自动清理。
- Docker 挂载目录不一致。
- 文件生成失败或实际保存路径不同。

## 6. 安全与隐私

公开发布代码前，请检查仓库中是否包含：

- QQ 登录信息
- Cookie 或 Session
- API Key、Access Token
- SSH 私钥
- 下载缓存或用户文件
- 包含私人信息的日志

即使是 Private 仓库，也不建议提交这些敏感信息。

## 7. 致谢与原项目

本项目基于以下上游项目修改：

**原项目：** [CLRedfield/astrbot-plugin-jmdownloader](https://github.com/CLRedfield/astrbot-plugin-jmdownloader)

感谢原作者提供基础实现。本修改版主要针对 Linux Docker 部署环境中的文件路径、共享目录和访问权限问题进行兼容性调整。

本仓库为非官方修改版本，与原作者无官方关联。

## 8. 免责声明

本项目仅用于软件部署兼容性研究与技术交流。

使用者应遵守所在地法律法规、相关平台服务条款及版权规定。本仓库不托管或提供第三方内容。

## 9. License

本项目遵循上游项目的 [MIT License](LICENSE)，并保留原作者的版权声明。修改版本的说明见本 README。
