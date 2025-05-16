# 邮箱 API 客户端

本应用是一个基于Python和Flask的邮箱API客户端，用于管理和访问多个Outlook邮箱账号。
前提部署了api后端具体看这个项目Vercel 无服务器版](https://github.com/HChaoHui/msOauth2api)

## 功能特点

- 支持多邮箱账号管理
- 查看新邮件和全部邮件
- 支持收件箱和垃圾邮件文件夹
- 清空收件箱或垃圾邮件
- 批量导入账号功能（支持并行加速）
- 批量删除账号功能
- 本地存储，数据安全
- 响应式设计，兼容桌面和移动设备
- 支持深色模式
- 支持分页显示，更适合大量账号管理

## 运行方式

### 方法一：直接运行Python脚本

1. 安装依赖：
```
pip install -r requirements.txt
```

2. 运行应用：
```
python main.py
```

### 方法二：运行打包的EXE文件

直接双击运行`邮箱API客户端.exe`即可。

## 打包成EXE

### 方法一：使用cx_Freeze打包

1. 安装cx_Freeze：
```
pip install cx_Freeze
```

2. 执行打包命令：
```
python setup.py build
```

### 方法二：使用PyInstaller打包（推荐）

1. 安装PyInstaller：
```
pip install pyinstaller
```

2. 使用配置文件打包：
```
pyinstaller pyinstaller.spec
```

或者直接使用命令行打包：
```
pyinstaller --noconfirm --name="邮箱API客户端" --windowed --add-data="templates;templates" --add-data="data;data" main.py
```

打包完成后，在dist目录下可以找到生成的`邮箱API客户端.exe`文件。

## 数据存储

应用数据存储在**可执行文件所在目录**下的`data`文件夹中，包括：
- accounts.json - 账号信息
- mail_counts.json - 邮件计数信息
- app.log - 应用日志

## 使用说明

1. 双击运行`邮箱API客户端.exe`，程序会自动打开浏览器访问应用
2. 在浏览器中使用程序的各项功能
3. 当关闭浏览器窗口后，程序会自动检测并在短时间内自动退出
4. 下次启动时，程序会自动读取之前保存的数据

## 新增功能说明

### 批量删除
1. 在管理页面，使用复选框选择要删除的账号
2. 点击"批量删除"按钮执行删除操作

### 并行导入
1. 数据解析使用Web Worker并行处理
2. API请求使用异步队列，支持并行导入多个账号
3. 导入过程显示实时进度

### 分页浏览
1. 账号列表支持分页显示
2. 默认每页显示10个账号
3. 使用上一页/下一页按钮进行导航

## 技术栈

- 后端：Python + Flask
- 前端：HTML + CSS + JavaScript (纯原生实现，无框架依赖)
- 打包工具：PyInstaller / cx_Freeze 
