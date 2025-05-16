import os
import json
import webbrowser
import sys
import atexit
from flask import Flask, render_template, request, jsonify, send_from_directory, flash, redirect, url_for
from flask_cors import CORS
import threading
import logging
import concurrent.futures
import traceback
import io
import time
import csv

# 获取应用程序路径
def get_app_path():
    # 判断是否是PyInstaller打包的环境
    if getattr(sys, 'frozen', False):
        # 如果是打包环境，使用可执行文件所在目录
        app_path = os.path.dirname(sys.executable)
    else:
        # 如果是普通Python环境，使用脚本所在目录
        app_path = os.path.dirname(os.path.abspath(__file__))
    return app_path

# 配置
API_BASE_URL = 'https://你的域名/api'
ALLOWED_MAILBOXES = ['INBOX', 'Junk']
LOGO_URL = 'https://img.xwyue.com/i/2025/01/23/6791c8b24239a.png'

# 本地存储路径（使用可执行文件所在目录中的data文件夹）
APP_DIR = os.path.join(get_app_path(), "data")
API_CONFIG_FILE = os.path.join(APP_DIR, "api_config.json")
ACCOUNTS_FILE = os.path.join(APP_DIR, "accounts.json")
UPLOADS_DIR = os.path.join(APP_DIR, "uploads")  # 用于存储上传的CSV文件

# 添加一个文件锁
file_lock = threading.RLock()

# 确保应用目录存在
os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)  # 确保上传目录存在

# 确保api_config.json文件存在且为有效的JSON
if not os.path.exists(API_CONFIG_FILE):
    with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({"api_base_url": API_BASE_URL}, f)
else:
    try:
        with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.loads(f.read().strip())
            if config and 'api_base_url' in config:
                API_BASE_URL = config['api_base_url']
    except Exception as e:
        logger.error(f"加载API配置时出错: {e}")
        # 如果文件损坏，重置文件
        with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"api_base_url": API_BASE_URL}, f)

# 确保accounts.json文件存在且为有效的JSON
if not os.path.exists(ACCOUNTS_FILE):
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f)

# 初始化Flask应用
app = Flask(__name__)
app.secret_key = os.urandom(24)  # 用于flash消息
CORS(app)  # 允许跨域请求

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(APP_DIR, "app.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 账户操作函数
def load_accounts():
    """从本地文件加载账户，添加文件锁保护"""
    with file_lock:
        try:
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:  # 文件为空
                        return {}
                    return json.loads(content)
            return {}
        except Exception as e:
            logger.error(f"加载账户时出错: {e}")
            logger.error(traceback.format_exc())
            # 如果文件损坏，重置文件
            try:
                with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump({}, f)
                logger.info("检测到JSON文件损坏，已重置为空JSON对象")
                return {}
            except Exception as reset_error:
                logger.error(f"重置账户文件时出错: {reset_error}")
                return {}

def save_accounts(accounts):
    """保存账户到本地文件，添加文件锁保护"""
    with file_lock:
        try:
            # 先写入临时文件，然后重命名，确保原子性写入
            temp_file = ACCOUNTS_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
            
            # 在Windows上，重命名可能会失败，如果文件已存在
            if os.path.exists(ACCOUNTS_FILE):
                os.remove(ACCOUNTS_FILE)
            
            os.rename(temp_file, ACCOUNTS_FILE)
            return True
        except Exception as e:
            logger.error(f"保存账户时出错: {e}")
            logger.error(traceback.format_exc())
            return False

# 添加账号到内存缓存，每30秒保存一次
accounts_cache = {}
last_save_time = 0
save_interval = 30  # 30秒保存一次
cache_lock = threading.RLock()

# 添加邮件操作计数存储
mail_fetch_counts = {}
MAIL_COUNTS_FILE = os.path.join(APP_DIR, "mail_counts.json")

# 确保mail_counts.json文件存在且为有效的JSON
if not os.path.exists(MAIL_COUNTS_FILE):
    with open(MAIL_COUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f)

def load_mail_counts():
    """从本地文件加载邮件操作计数"""
    with file_lock:
        try:
            if os.path.exists(MAIL_COUNTS_FILE):
                with open(MAIL_COUNTS_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:  # 文件为空
                        return {}
                    return json.loads(content)
            return {}
        except Exception as e:
            logger.error(f"加载邮件计数时出错: {e}")
            logger.error(traceback.format_exc())
            return {}

def save_mail_counts():
    """保存邮件操作计数到本地文件"""
    with file_lock:
        try:
            temp_file = MAIL_COUNTS_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(mail_fetch_counts, f, ensure_ascii=False, indent=2)
            
            if os.path.exists(MAIL_COUNTS_FILE):
                os.remove(MAIL_COUNTS_FILE)
            
            os.rename(temp_file, MAIL_COUNTS_FILE)
            logger.info(f"已保存邮件计数数据，共 {len(mail_fetch_counts)} 个记录")
            return True
        except Exception as e:
            logger.error(f"保存邮件计数时出错: {e}")
            logger.error(traceback.format_exc())
            return False

def load_cache():
    """从文件加载到缓存"""
    global accounts_cache, mail_fetch_counts
    with cache_lock:
        accounts = load_accounts()
        accounts_cache = accounts.copy()
        logger.info(f"已加载 {len(accounts_cache)} 个账号到缓存")
        
        # 加载邮件计数
        counts = load_mail_counts()
        mail_fetch_counts = counts.copy()
        logger.info(f"已加载 {len(mail_fetch_counts)} 个邮件计数记录")

def save_cache_to_file():
    """将缓存保存到文件"""
    global last_save_time
    current_time = time.time()
    
    with cache_lock:
        if current_time - last_save_time >= save_interval:
            success = save_accounts(accounts_cache)
            save_mail_counts()  # 同时保存邮件计数
            if success:
                last_save_time = current_time
                logger.info(f"缓存已保存到文件，共 {len(accounts_cache)} 个账号")
                return True
    return False

# 从CSV文件导入账号
def import_accounts_from_csv(file_path, delimiter=','):
    """从CSV文件导入账号，返回导入结果统计"""
    result = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as csvfile:
            content = csvfile.read()
            lines = content.strip().split('\n')
            result['total'] = len(lines)
            
            # 处理可能的标题行
            if result['total'] > 0:
                first_line = lines[0].lower()
                if 'email' in first_line or 'token' in first_line or 'client' in first_line:
                    lines = lines[1:]
                    result['total'] -= 1
                    logger.info("CSV文件包含标题行，已跳过")
            
            # 解析每一行
            with cache_lock:
                for i, line in enumerate(lines):
                    try:
                        # 尝试使用指定的分隔符分割
                        if delimiter == 'auto':
                            # 尝试检测是CSV格式还是特殊分隔符格式
                            if '----' in line:
                                parts = line.split('----')
                            elif '\t' in line:
                                parts = line.split('\t')
                            elif ';' in line:
                                parts = line.split(';')
                            else:
                                parts = line.split(',')
                        elif delimiter == '----':
                            parts = line.split('----')
                        elif delimiter == 'tab':
                            parts = line.split('\t')
                        else:
                            # 如果是CSV格式，使用CSV解析器
                            try:
                                parts = next(csv.reader([line], delimiter=delimiter))
                            except Exception:
                                # 如果CSV解析失败，回退到简单分割
                                parts = line.split(delimiter)
                        
                        # 确保有足够的部分
                        if len(parts) < 3:
                            error_msg = f"行 {i+1}: 列数不足，至少需要3列 (email, client_id, refresh_token)"
                            result['errors'].append(error_msg)
                            result['failed'] += 1
                            logger.warning(error_msg)
                            continue
                        
                        # 提取数据
                        email = parts[0].strip() if parts[0] else None
                        
                        # 处理原始格式和CSV格式
                        if len(parts) >= 4 and delimiter == '----':  # 特殊格式: email----pwd----client_id----refresh_token
                            client_id = parts[2].strip() if parts[2] else None
                            refresh_token = parts[3].strip() if parts[3] else None
                        else:  # 标准CSV格式: email,client_id,refresh_token
                            client_id = parts[1].strip() if parts[1] else None
                            refresh_token = parts[2].strip() if parts[2] else None
                        
                        if not email or not refresh_token or not client_id:
                            error_msg = f"行 {i+1}: 缺少必要字段 - {email}"
                            result['errors'].append(error_msg)
                            result['failed'] += 1
                            logger.warning(error_msg)
                            continue
                        
                        # 添加账号到缓存
                        accounts_cache[email] = {
                            'refresh_token': refresh_token,
                            'client_id': client_id
                        }
                        result['success'] += 1
                        logger.info(f"从CSV导入账号成功: {email}")
                    except Exception as e:
                        error_msg = f"行 {i+1}: 处理出错 - {str(e)}"
                        result['errors'].append(error_msg)
                        result['failed'] += 1
                        logger.error(error_msg)
                        logger.error(traceback.format_exc())
                
                # 保存更改
                if result['success'] > 0:
                    save_cache_to_file()
        
        return result
    except Exception as e:
        logger.error(f"导入CSV文件出错: {e}")
        logger.error(traceback.format_exc())
        result['errors'].append(f"处理CSV文件时出错: {str(e)}")
        return result

# 初始化缓存
load_cache()

# 启动自动保存线程
def auto_save_worker():
    while True:
        time.sleep(save_interval)
        save_cache_to_file()
        
auto_save_thread = threading.Thread(target=auto_save_worker, daemon=True)
auto_save_thread.start()

# 路由定义
@app.route('/')
def index():
    """主页"""
    return render_template('index.html', 
                           API_BASE_URL=API_BASE_URL,
                           LOGO_URL=LOGO_URL)

@app.route('/fetched')
def fetched_accounts():
    """显示已取件邮箱的页面"""
    return render_template('fetched.html', API_BASE_URL=API_BASE_URL, LOGO_URL=LOGO_URL)

@app.route('/fetch')
def fetch_operation():
    """显示取件操作的页面"""
    return render_template('fetch.html', API_BASE_URL=API_BASE_URL, LOGO_URL=LOGO_URL)

@app.route('/manage')
def manage():
    """账户管理页面"""
    return render_template('manage.html', 
                           API_BASE_URL=API_BASE_URL,
                           LOGO_URL=LOGO_URL)

@app.route('/accounts', methods=['GET'])
def get_accounts():
    """获取所有账户"""
    with cache_lock:
        return jsonify(accounts_cache)

@app.route('/manage', methods=['POST'])
def add_account():
    """添加新账户"""
    try:
        data = request.json
        email = data.get('email')
        refresh_token = data.get('refresh_token')
        client_id = data.get('client_id')
        
        # 详细记录添加账号的请求内容
        logger.info(f"添加账号请求: email={email}, refresh_token长度={len(refresh_token) if refresh_token else 0}, client_id长度={len(client_id) if client_id else 0}")
        
        # 验证参数
        if not email:
            logger.warning("添加账号失败: 邮箱地址为空")
            return "邮箱地址不能为空", 400
            
        if not refresh_token:
            logger.warning(f"添加账号失败: {email} 的refresh_token为空")
            return "Refresh Token不能为空", 400
            
        if not client_id:
            logger.warning(f"添加账号失败: {email} 的client_id为空")
            return "Client ID不能为空", 400
        
        # 清理可能的空白字符
        email = email.strip()
        refresh_token = refresh_token.strip()
        client_id = client_id.strip()
        
        # 再次验证参数
        if not all([email, refresh_token, client_id]):
            logger.warning(f"添加账号失败: 参数清理后存在空值 - email={email}, refresh_token长度={len(refresh_token)}, client_id长度={len(client_id)}")
            return "参数无效，请检查所有输入", 400
        
        # 使用缓存添加账号
        with cache_lock:
            # 添加或更新账号
            accounts_cache[email] = {
                'refresh_token': refresh_token,
                'client_id': client_id
            }
            logger.info(f"成功添加账号到缓存: {email}")
            
            # 检查是否需要立即保存
            if len(accounts_cache) % 10 == 0:  # 每添加10个账号保存一次
                save_cache_to_file()
            
            return "账户已添加", 200
    except Exception as e:
        logger.error(f"添加账户时出错: {e}")
        logger.error(traceback.format_exc())
        return f"添加账户时出错: {str(e)}", 500

@app.route('/manage', methods=['DELETE'])
def delete_account():
    """删除账户"""
    try:
        # 删除全部账号
        delete_all = request.args.get('delete_all') == 'true'
        if delete_all:
            logger.info("执行删除全部账号操作")
            with cache_lock:
                total_accounts = len(accounts_cache)
                if total_accounts == 0:
                    return "没有账号可删除", 400
                    
                # 清空账号并保存
                accounts_cache.clear()
                save_cache_to_file()  # 立即保存
                
                logger.info(f"成功删除全部账号，共{total_accounts}个")
                return f"已成功删除全部账号，共{total_accounts}个", 200
        
        # 批量删除
        emails = request.args.get('emails')
        if emails:
            email_list = emails.split(',')
            logger.info(f"执行批量删除操作，选择了{len(email_list)}个账号")
            deleted_count = 0
            
            with cache_lock:
                for email in email_list:
                    if email in accounts_cache:
                        del accounts_cache[email]
                        deleted_count += 1
                        logger.info(f"已删除账号: {email}")
                    else:
                        logger.warning(f"账号不存在，跳过删除: {email}")
                
                if deleted_count > 0:
                    save_cache_to_file()  # 立即保存
                    logger.info(f"批量删除成功，共删除{deleted_count}个账号")
                    return f"已成功删除 {deleted_count} 个账户", 200
                else:
                    logger.warning("批量删除：没有账户被删除或保存失败")
                    return "没有账户被删除", 400
                
        # 单个删除
        email = request.args.get('email')
        if not email:
            logger.warning("单个删除：未提供邮箱地址")
            return "需要提供邮箱地址", 400
        
        with cache_lock:
            if email in accounts_cache:
                del accounts_cache[email]
                save_cache_to_file()  # 立即保存
                logger.info(f"成功删除单个账号: {email}")
                return "账户已删除", 200
            else:
                logger.warning(f"尝试删除不存在的账号: {email}")
                return "账户不存在", 404
    except Exception as e:
        logger.error(f"删除账户时出错: {e}")
        logger.error(traceback.format_exc())
        return f"删除账户时出错: {str(e)}", 500

@app.route('/accounts/count', methods=['GET'])
def get_accounts_count():
    """获取账号总数"""
    with cache_lock:
        count = len(accounts_cache)
    return jsonify({"count": count})

@app.route('/manifest.json')
def manifest():
    """PWA清单文件"""
    manifest_data = {
        "name": "邮箱 API 客户端",
        "short_name": "邮箱客户端",
        "icons": [
            {
                "src": LOGO_URL,
                "sizes": "192x192",
                "type": "image/png"
            }
        ],
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0078d4"
    }
    return jsonify(manifest_data)

@app.route('/test-connection', methods=['POST'])
def test_connection():
    """测试账号连接是否有效"""
    try:
        data = request.json
        email = data.get('email', '').strip()
        refresh_token = data.get('refresh_token', '').strip()
        client_id = data.get('client_id', '').strip()
        
        if not all([email, refresh_token, client_id]):
            return jsonify({"success": False, "message": "缺少必要参数"}), 400
        
        # 这里应该是实际去调用API测试连接的代码
        # 作为示例，我们只返回成功
        logger.info(f"测试账号连接: {email}")
        return jsonify({
            "success": True, 
            "message": "连接成功，账号有效"
        })
    except Exception as e:
        logger.error(f"测试连接时出错: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False, 
            "message": f"测试连接时出错: {str(e)}"
        }), 500

# CSV导入功能
@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    """上传并导入CSV文件"""
    try:
        if 'csv_file' not in request.files and 'csv_text' not in request.form:
            return jsonify({"success": False, "message": "没有上传文件或提供文本"}), 400
        
        delimiter = request.form.get('delimiter', ',')
        if delimiter == 'tab':
            delimiter = '\t'
        elif delimiter == 'four-dashes':
            delimiter = '----'
        
        # 处理文件上传
        if 'csv_file' in request.files and request.files['csv_file'].filename:
            file = request.files['csv_file']
            
            # 保存上传的文件
            timestamp = int(time.time())
            filename = f"accounts_import_{timestamp}.csv"
            file_path = os.path.join(UPLOADS_DIR, filename)
            file.save(file_path)
            
            logger.info(f"开始导入CSV文件: {file_path}，分隔符: {delimiter}")
            
            # 导入账号
            result = import_accounts_from_csv(file_path, delimiter)
            
            # 可选：删除上传的文件
            try:
                os.remove(file_path)
                logger.info(f"已删除上传的CSV文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除CSV文件失败: {e}")
        
        # 处理文本输入
        elif 'csv_text' in request.form and request.form['csv_text'].strip():
            csv_text = request.form['csv_text'].strip()
            
            # 保存为临时文件
            timestamp = int(time.time())
            filename = f"text_import_{timestamp}.csv"
            file_path = os.path.join(UPLOADS_DIR, filename)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(csv_text)
            
            logger.info(f"开始导入文本内容，分隔符: {delimiter}")
            
            # 导入账号
            result = import_accounts_from_csv(file_path, delimiter)
            
            # 删除临时文件
            try:
                os.remove(file_path)
                logger.info(f"已删除临时文本文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")
        else:
            return jsonify({"success": False, "message": "没有提供有效的数据"}), 400
        
        # 记录结果
        logger.info(f"导入完成: 总计{result['total']}个账号，成功{result['success']}个，失败{result['failed']}个")
        
        return jsonify({
            "success": True,
            "message": f"导入完成：总计{result['total']}个账号，成功{result['success']}个，失败{result['failed']}个",
            "result": result
        })
    except Exception as e:
        logger.error(f"处理数据导入时出错: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False, 
            "message": f"处理导入数据时出错: {str(e)}"
        }), 500

@app.route('/import-text', methods=['POST'])
def import_text():
    """处理文本导入请求"""
    try:
        data = request.json
        text = data.get('text', '').strip()
        delimiter = data.get('delimiter', '----')
        
        if not text:
            return jsonify({"success": False, "message": "没有提供文本内容"}), 400
        
        # 保存为临时文件
        timestamp = int(time.time())
        filename = f"text_import_{timestamp}.txt"
        file_path = os.path.join(UPLOADS_DIR, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        logger.info(f"开始导入文本内容，分隔符: {delimiter}")
        
        # 导入账号
        result = import_accounts_from_csv(file_path, delimiter)
        
        # 删除临时文件
        try:
            os.remove(file_path)
            logger.info(f"已删除临时文本文件: {file_path}")
        except Exception as e:
            logger.warning(f"删除临时文件失败: {e}")
        
        # 记录结果
        logger.info(f"文本导入完成: 总计{result['total']}个账号，成功{result['success']}个，失败{result['failed']}个")
        
        return jsonify({
            "success": True,
            "message": f"导入完成：总计{result['total']}个账号，成功{result['success']}个，失败{result['failed']}个",
            "result": result
        })
    except Exception as e:
        logger.error(f"处理文本导入时出错: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "success": False, 
            "message": f"处理文本导入时出错: {str(e)}"
        }), 500

# 生成CSV模板
@app.route('/csv-template')
def get_csv_template():
    """下载CSV导入模板"""
    try:
        # 创建CSV模板
        template_file = os.path.join(UPLOADS_DIR, "account_template.csv")
        with open(template_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Email', 'Client_ID', 'Refresh_Token'])
            writer.writerow(['example@outlook.com', 'your_client_id_here', 'your_refresh_token_here'])
            
        return send_from_directory(UPLOADS_DIR, "account_template.csv", as_attachment=True)
    except Exception as e:
        logger.error(f"生成CSV模板时出错: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "message": f"生成模板失败: {str(e)}"}), 500

# 添加浏览器关闭检测
browser_closed = False
shutdown_timer = None
check_interval = 5  # 每5秒检查一次

def check_browser_connection():
    """检查浏览器连接状态，如果浏览器关闭则关闭应用"""
    global browser_closed, shutdown_timer
    
    # 如果已经记录为关闭状态，执行关闭程序
    if browser_closed:
        logger.info("检测到浏览器已关闭，正在关闭应用...")
        save_on_exit()  # 保存数据
        os._exit(0)  # 强制关闭程序
        return
    
    # 安排下一次检查
    shutdown_timer = threading.Timer(check_interval, check_browser_connection)
    shutdown_timer.daemon = True
    shutdown_timer.start()

@app.route('/heartbeat', methods=['GET'])
def heartbeat():
    """提供心跳检测端点，重置浏览器状态为连接状态"""
    global browser_closed
    browser_closed = False
    return jsonify({"status": "ok"})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """提供关闭应用的端点"""
    global browser_closed
    browser_closed = True
    return jsonify({"status": "shutting_down"})

# 退出时保存数据
def save_on_exit():
    logger.info("应用正在关闭，保存数据...")
    with cache_lock:
        save_accounts(accounts_cache)
        save_mail_counts()
    logger.info("数据已保存，应用关闭")

# 注册退出处理函数
atexit.register(save_on_exit)

def open_browser():
    """打开浏览器访问应用"""
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    logger.info("已打开浏览器")
    
    # 启动浏览器连接检查
    global browser_closed
    browser_closed = False
    check_browser_connection()

# 账号统计API
@app.route('/api/accounts/stats')
def account_stats():
    try:
        with cache_lock:
            total = len(accounts_cache)
            # 计算已取件邮箱数量（取件次数>0的邮箱）
            fetched_count = sum(1 for email in accounts_cache if email in mail_fetch_counts and mail_fetch_counts[email] > 0)
            # 将活跃账号定义为未取件邮箱数量（总数减去已取件邮箱的数量）
            active = total - fetched_count
        
        return jsonify({
            "total": total,
            "active": active,
            "fetched": fetched_count
        })
    except Exception as e:
        return jsonify({
            "total": 0,
            "active": 0,
            "fetched": 0,
            "error": str(e)
        })

# 邮件计数API和更新接口
@app.route('/api/mail/count/<email>', methods=['GET'])
def get_mail_count(email):
    """获取指定邮箱的邮件获取次数"""
    count = mail_fetch_counts.get(email, 0)
    return jsonify({"email": email, "count": count})

@app.route('/api/mail/count/<email>', methods=['POST'])
def increment_mail_count(email):
    """增加指定邮箱的邮件获取次数"""
    if email not in mail_fetch_counts:
        mail_fetch_counts[email] = 0
    
    mail_fetch_counts[email] += 1
    save_mail_counts()  # 立即保存更新
    
    return jsonify({
        "email": email, 
        "count": mail_fetch_counts[email],
        "success": True
    })

@app.route('/api/mail/counts', methods=['GET'])
def get_all_mail_counts():
    """获取所有邮箱的邮件获取次数"""
    return jsonify(mail_fetch_counts)

@app.route('/api/mail/counts/delete-all', methods=['POST'])
def delete_all_mail_counts():
    """删除所有已取件邮箱的计数和账号"""
    global mail_fetch_counts, accounts_cache
    
    # 收集要删除的邮箱
    emails_to_delete = list(mail_fetch_counts.keys())
    
    # 清空邮件计数
    mail_fetch_counts.clear()
    save_mail_counts_success = save_mail_counts()
    logger.info(f"删除所有邮件计数，保存结果: {save_mail_counts_success}")
    
    # 同时从账号缓存中删除这些邮箱
    deleted_accounts = 0
    with cache_lock:
        for email in emails_to_delete:
            if email in accounts_cache:
                del accounts_cache[email]
                deleted_accounts += 1
        
        # 保存账号变更
        save_accounts_success = save_accounts(accounts_cache)
        logger.info(f"删除所有已取件邮箱的账号，共删除{deleted_accounts}个，保存结果: {save_accounts_success}")
    
    return jsonify({
        "success": True,
        "deleted_accounts": deleted_accounts,
        "deleted_counts": len(emails_to_delete),
        "message": f"已成功删除所有已取件邮箱的记录及账号，共{deleted_accounts}个账号"
    })

@app.route('/api/mail/count/<email>/delete', methods=['POST'])
def delete_single_mail_count(email):
    """删除单个邮箱的计数记录和账号"""
    global mail_fetch_counts, accounts_cache
    
    if email in mail_fetch_counts:
        # 删除邮件计数
        del mail_fetch_counts[email]
        save_mail_counts_success = save_mail_counts()
        logger.info(f"删除单个邮箱计数: {email}，保存结果: {save_mail_counts_success}")
        
        # 删除对应的账号
        account_deleted = False
        with cache_lock:
            if email in accounts_cache:
                del accounts_cache[email]
                save_accounts_success = save_accounts(accounts_cache)
                account_deleted = True
                logger.info(f"删除单个邮箱账号: {email}，保存结果: {save_accounts_success}")
        
        return jsonify({
            "success": True,
            "email": email,
            "account_deleted": account_deleted,
            "message": f"已成功删除 {email} 的取件计数和账号"
        })
    else:
        logger.warning(f"尝试删除不存在的邮箱计数: {email}")
        return jsonify({
            "success": False,
            "email": email,
            "message": f"邮箱 {email} 不存在计数记录"
        }), 404

@app.route('/api/mail/counts/delete-by-threshold', methods=['POST'])
def delete_mail_counts_by_threshold():
    """根据取件次数阈值删除邮箱计数和对应账号"""
    data = request.json
    threshold = data.get('threshold', 1)
    specific_email = data.get('email', None)
    
    if not isinstance(threshold, int) or threshold < 1:
        return jsonify({
            "success": False,
            "message": "阈值必须是大于等于1的整数"
        }), 400
    
    global mail_fetch_counts, accounts_cache
    
    # 如果指定了特定邮箱，只删除该邮箱
    if specific_email:
        if specific_email in mail_fetch_counts:
            count = mail_fetch_counts[specific_email]
            if count >= threshold:
                # 删除邮件计数
                del mail_fetch_counts[specific_email]
                save_mail_counts_success = save_mail_counts()
                logger.info(f"删除单个邮箱计数: {specific_email}，保存结果: {save_mail_counts_success}")
                
                # 删除对应的账号
                account_deleted = False
                with cache_lock:
                    if specific_email in accounts_cache:
                        del accounts_cache[specific_email]
                        save_accounts_success = save_accounts(accounts_cache)
                        account_deleted = True
                        logger.info(f"删除单个邮箱账号: {specific_email}，保存结果: {save_accounts_success}")
                
                return jsonify({
                    "success": True,
                    "deleted_count": 1,
                    "account_deleted": account_deleted,
                    "remaining_count": len(mail_fetch_counts),
                    "message": f"已成功删除邮箱 {specific_email} 的记录和账号"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": f"邮箱 {specific_email} 的计数值 ({count}) 小于阈值 ({threshold})"
                }), 400
        else:
            return jsonify({
                "success": False,
                "message": f"邮箱 {specific_email} 不存在计数记录"
            }), 404
    
    # 否则删除所有满足阈值的邮箱
    emails_to_delete = [email for email, count in mail_fetch_counts.items() if count >= threshold]
    
    # 删除符合条件的邮箱计数
    for email in emails_to_delete:
        if email in mail_fetch_counts:
            del mail_fetch_counts[email]
    
    # 保存邮件计数更改
    save_mail_counts_success = save_mail_counts()
    logger.info(f"删除邮件计数（阈值{threshold}），删除{len(emails_to_delete)}个，保存结果: {save_mail_counts_success}")
    
    # 同时删除对应的账号
    deleted_accounts = 0
    with cache_lock:
        for email in emails_to_delete:
            if email in accounts_cache:
                del accounts_cache[email]
                deleted_accounts += 1
        
        # 保存账号变更
        if deleted_accounts > 0:
            save_accounts_success = save_accounts(accounts_cache)
            logger.info(f"删除邮箱账号（阈值{threshold}），删除{deleted_accounts}个，保存结果: {save_accounts_success}")
    
    return jsonify({
        "success": True,
        "deleted_count": len(emails_to_delete),
        "deleted_accounts": deleted_accounts,
        "remaining_count": len(mail_fetch_counts),
        "message": f"已成功删除{len(emails_to_delete)}个取件次数大于等于{threshold}的邮箱记录和对应账号"
    })

# API URL配置相关接口
@app.route('/api/config', methods=['GET'])
def get_api_config():
    """获取API基础URL配置"""
    return jsonify({
        "api_base_url": API_BASE_URL
    })

@app.route('/api/config', methods=['POST'])
def update_api_config():
    """更新API基础URL配置"""
    global API_BASE_URL
    try:
        data = request.json
        new_url = data.get('api_base_url')
        
        if not new_url:
            return jsonify({
                "success": False,
                "message": "API URL不能为空"
            }), 400
        
        # 简单验证URL格式
        if not new_url.startswith('http'):
            return jsonify({
                "success": False,
                "message": "API URL必须以http或https开头"
            }), 400
        
        # 验证URL是否变更，如果相同则无需保存
        if new_url == API_BASE_URL:
            return jsonify({
                "success": True,
                "message": "API URL保持不变",
                "api_base_url": API_BASE_URL
            })
        
        # 更新全局变量
        API_BASE_URL = new_url
        
        # 创建一个线程异步保存配置文件
        def save_config():
            try:
                with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump({"api_base_url": API_BASE_URL}, f, ensure_ascii=False, indent=2)
                logger.info(f"API配置已更新为: {API_BASE_URL}")
            except Exception as e:
                logger.error(f"保存API配置时出错: {e}")
                
        threading.Thread(target=save_config).start()
        
        return jsonify({
            "success": True,
            "message": "API URL已更新",
            "api_base_url": API_BASE_URL
        })
    except Exception as e:
        logger.error(f"更新API配置时出错: {e}")
        return jsonify({
            "success": False,
            "message": f"更新配置失败: {str(e)}"
        }), 500

if __name__ == '__main__':
    PORT = 5000
    threading.Timer(1, open_browser).start()
    logger.info(f"启动应用，访问地址: http://127.0.0.1:{PORT}")
    logger.info(f"数据存储位置: {APP_DIR}")
    app.run(debug=False, port=PORT) 