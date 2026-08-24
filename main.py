import flet as ft
import flet_permission_handler as fph
import mysql.connector
from datetime import datetime, date, timedelta
import hashlib
import json
import io
from PIL import Image as PILImage
import threading
from typing import Callable, Optional, List
import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import requests
import base64
import sys
import math
import tempfile
import asyncio
import flet_camera as fc
from typing import Callable, Optional
from pyzbar.pyzbar import decode as pyzbar_decode
import concurrent.futures
import time
import re
import shutil
import flet_flashlight as ffl
import flet_geolocator as ftg


SERVER_DECODE_URL = os.getenv("SERVER_DECODE_URL", "https://api.qrserver.com/v1/read-qr-code/")
MAX_IMAGE_LONG_EDGE = 1280
DEFAULT_WIDTH = 360

DB_HOST = os.getenv("DB_HOST", "240e:338:4a26:f3b1::84")
DB_PORT = int(os.getenv("DB_PORT", 13306))
DB_USER = os.getenv("DB_USER", "ipv6user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_DATABASE = os.getenv("DB_DATABASE", "jiuchengerp")

PERMISSIONS = ["🏠 首页", "🧾 销售", "📥 入库", "🚚 运输", "🔧 安装", "📦 库存", "更多"]
PERMISSION_ICONS = {
    "🏠 首页": ft.Icons.HOME,
    "🧾 销售": ft.Icons.SHOPPING_CART,
    "📥 入库": ft.Icons.INVENTORY,
    "🚚 运输": ft.Icons.LOCAL_SHIPPING,
    "🔧 安装": ft.Icons.HANDYMAN,
    "📦 库存": ft.Icons.DATASET,
    "更多": ft.Icons.SETTINGS,
}

# ====================== 通用工具函数 ======================
def get_window_width(page):
    try:
        if hasattr(page, 'width') and page.width:
            return page.width
        elif hasattr(page, 'window') and page.window and hasattr(page.window, 'width'):
            return page.window.width
        else:
            return DEFAULT_WIDTH
    except:
        return DEFAULT_WIDTH

def get_asset_path(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", filename)

def get_config_dir():
    if getattr(sys, 'frozen', False):
        if os.name == 'nt':
            config_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'jiuchengerp')
        else:
            config_dir = os.path.join(os.path.expanduser('~'), '.config', 'jiuchengerp')
    else:
        config_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

CONFIG_DIR = get_config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, 'server_config.json')
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'saved_login.json')

DEFAULT_HOST = os.getenv("DB_HOST", DB_HOST)
DEFAULT_PORT = int(os.getenv("DB_PORT", DB_PORT))
DEFAULT_USER = os.getenv("DB_USER", DB_USER)
DEFAULT_PASSWORD = os.getenv("DB_PASSWORD", DB_PASSWORD)
DEFAULT_DATABASE = os.getenv("DB_DATABASE", DB_DATABASE)

DB_HOST = DEFAULT_HOST
DB_PORT = DEFAULT_PORT
DB_USER = DEFAULT_USER
DB_PASSWORD = DEFAULT_PASSWORD
DB_DATABASE = DEFAULT_DATABASE

def run_ui_task(page: ft.Page, func: Callable):
    """线程安全：子线程调度主线程执行UI更新（修复handler必须是协程的错误）"""
    async def _ui_wrapper():
        func()
    page.run_task(_ui_wrapper)

def safe_close_dialog(page: ft.Page, dlg):
    """标准化安全关闭弹窗，清理overlay"""
    def _close():
        try:
            dlg.open = False
            page.update()
            if dlg in page.overlay:
                page.overlay.remove(dlg)
                page.update()
        except Exception:
            pass
    run_ui_task(page, _close)

def load_server_config():
    global DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_DATABASE
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                DB_HOST = cfg.get("DB_HOST", DEFAULT_HOST)
                DB_PORT = int(cfg.get("DB_PORT", DEFAULT_PORT))
                DB_USER = cfg.get("DB_USER", DEFAULT_USER)
                DB_PASSWORD = cfg.get("DB_PASSWORD", DEFAULT_PASSWORD)
                DB_DATABASE = cfg.get("DB_DATABASE", DEFAULT_DATABASE)
        except Exception as e:
            print(f"读取配置文件失败: {e}，使用默认值")
    else:
        save_server_config(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DATABASE)

def save_server_config(host, port, user, pwd, db):
    cfg = {
        "DB_HOST": host,
        "DB_PORT": port,
        "DB_USER": user,
        "DB_PASSWORD": pwd,
        "DB_DATABASE": db
    }
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

load_server_config()

def get_db_conn():
    try:
        return mysql.connector.connect(
            host=DB_HOST, port=int(DB_PORT), user=DB_USER,
            password=DB_PASSWORD, database=DB_DATABASE,
            use_pure=True, connect_timeout=5)
    except Exception as e:
        print("数据库错误:", e)
        return None

def md5_pwd(pwd):
    return hashlib.md5(pwd.encode("utf-8")).hexdigest()

def gen_order_no():
    year = date.today().strftime("%Y")
    conn = get_db_conn()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(order_no) FROM sale_main WHERE order_no LIKE %s", (f"{year}%",))
        max_no = cur.fetchone()[0]
        conn.close()
        seq = int(max_no[4:]) + 1 if max_no else 1
        return f"{year}{seq:04d}"
    return f"{year}0001"

def gen_invoice_no():
    return f"INV{date.today().strftime('%Y%m%d')}{int(datetime.now().timestamp()) % 10000:04d}"

def resource_path(relative_path):
    try:
        return os.path.join(sys._MEIPASS, relative_path)
    except:
        return os.path.join(os.path.abspath("."), relative_path)

# ====================== 弹窗统一管理 ======================
def close_all_dialogs(page: ft.Page):
    to_remove = []
    for ctrl in list(page.overlay):
        if isinstance(ctrl, (ft.AlertDialog, ft.DatePicker, ft.BottomSheet)):
            try:
                ctrl.open = False
                to_remove.append(ctrl)
            except:
                pass
    page.update()
    for d in to_remove:
        try:
            page.overlay.remove(d)
        except:
            pass

def safe_remove_dialog(page: ft.Page, dialog):
    async def _remove():
        await asyncio.sleep(0.15)          # 等待关闭动画
        if dialog in page.overlay:
            try:
                page.overlay.remove(dialog)
                page.update()
            except:
                pass
    page.run_task(_remove)                 # 安全调度到事件循环


def show_alert(page: ft.Page, title, content, on_ok=None):
    """同步弹窗，统一使用官方API，层级由框架管理"""

    async def handle_ok(e):
        page.pop_dialog()
        if on_ok:
            on_ok(e)

    dlg = ft.AlertDialog(
        title=ft.Text(title, weight=ft.FontWeight.BOLD),
        content=ft.Text(content),
        modal=True,
        actions=[ft.TextButton("确定", on_click=handle_ok)]
    )
    page.show_dialog(dlg)


async def show_alert_async(page: ft.Page, title, content, on_ok=None):
    """异步安全弹窗，统一官方API"""

    async def handle_ok(e):
        page.pop_dialog()
        if on_ok:
            await on_ok(e)

    dlg = ft.AlertDialog(
        title=ft.Text(title, weight=ft.FontWeight.BOLD),
        content=ft.Text(content),
        modal=True,
        actions=[ft.TextButton("确定", on_click=handle_ok)]
    )
    page.show_dialog(dlg)

def show_snack(page: ft.Page, msg, bgcolor=ft.Colors.GREY_800):
    # 创建 SnackBar 对象（可增加浮动行为避免被遮挡）
    snack = ft.SnackBar(
        ft.Text(msg),
        bgcolor=bgcolor,
        behavior=ft.SnackBarBehavior.FLOATING   # 可选，让 SnackBar 浮在底部之上
    )
    # 兼容旧版 Flet：用 overlay 方式显示
    page.overlay.append(snack)
    snack.open = True
    page.update()

# ====================== 文件/相册/相机（全修复） ======================
def resolve_picker_file(page: ft.Page, file: ft.FilePickerFile) -> Optional[str]:
    if not file:
        return None
    if hasattr(file, "data") and file.data:
        try:
            ext = os.path.splitext(file.name or "")[1] or ".jpg"
            tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            tmp.write(file.data)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception as e:
            print(f"[FileResolver] data write error: {e}")
    if file.path and os.path.exists(file.path):
        return file.path
    if file.path and file.path.startswith("content://"):
        try:
            file_obj = page.get_file(file.path)
            if file_obj and file_obj.bytes:
                ext = os.path.splitext(file.name or "")[1] or ".jpg"
                tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                tmp.write(file_obj.bytes)
                tmp.flush()
                tmp.close()
                return tmp.name
        except Exception as e:
            print(f"[FileResolver] content uri error: {e}")
    return None

def compress_image_to_bytes(file_path: str, max_long_edge: int = MAX_IMAGE_LONG_EDGE) -> bytes:
    with PILImage.open(file_path) as img:
        width, height = img.size
        if max(width, height) > max_long_edge:
            scale = max_long_edge / max(width, height)
            new_w = int(width * scale)
            new_h = int(height * scale)
            img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=100, optimize=True)
        return buf.getvalue()

async def get_current_location(page: ft.Page) -> tuple[bool, str, str]:
    """
    对齐官方flet_geolocator示例：申请位置权限 + 获取当前坐标
    返回：(是否成功, 纬度, 经度)
    失败自动降级IP粗略定位
    """
    # 桌面端/Web直接走IP定位
    if page.platform not in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        try:
            res = requests.get("https://ipapi.co/json", timeout=4)
            if res.status_code == 200:
                loc = res.json()
                return True, str(loc.get("latitude", "获取失败")), str(loc.get("longitude", "获取失败"))
        except:
            pass
        return False, "获取失败", "获取失败"

    try:
        geo = ftg.Geolocator(
            configuration=ftg.GeolocatorConfiguration(
                accuracy=ftg.GeolocatorPositionAccuracy.LOW
            )
        )
        # 申请位置权限
        perm_status = await geo.request_permission()
        print(f"[Location] 权限申请结果：{perm_status}")

        # 修复：正确的授权状态是 WHILE_IN_USE，不是 GRANTED
        if perm_status != ftg.GeolocatorPermissionStatus.WHILE_IN_USE:
            print("[Location] 位置权限未授予，降级IP定位")
            try:
                res = requests.get("https://ipapi.co/json", timeout=4)
                if res.status_code == 200:
                    loc = res.json()
                    return True, str(loc.get("latitude", "获取失败")), str(loc.get("longitude", "获取失败"))
            except:
                pass
            return False, "获取失败", "获取失败"

        # 获取当前GPS坐标
        position = await geo.get_current_position()
        lat = str(round(position.latitude, 6))
        lng = str(round(position.longitude, 6))
        print(f"[Location] GPS定位成功：{lat}, {lng}")
        return True, lat, lng

    except Exception as e:
        print(f"[Location] 定位异常：{e}")
        # 异常降级IP定位
        try:
            res = requests.get("https://ipapi.co/json", timeout=4)
            if res.status_code == 200:
                loc = res.json()
                return True, str(loc.get("latitude", "获取失败")), str(loc.get("longitude", "获取失败"))
        except:
            pass
        return False, "获取失败", "获取失败"

async def request_gallery_permission(page: ft.Page) -> bool:
    """
    多机型兼容的相册权限申请
    优先级：安卓13+/鸿蒙4.x媒体权限 → 原有存储权限降级
    返回：是否获得相册权限
    """
    if page.platform != ft.PagePlatform.ANDROID:
        return True

    ph = page._permission_handler
    print("[Picker] 相册权限多级适配启动")

    # ========== 第一级：安卓13+/鸿蒙4.x 专属图片权限 ==========
    try:
        media_perm = fph.Permission.READ_MEDIA_IMAGES
        status = await ph.request(media_perm)
        print(f"[Picker] READ_MEDIA_IMAGES 授权结果：{status}")

        if status == fph.PermissionStatus.GRANTED:
            print("[Picker] 高版本相册权限授权成功")
            return True

        if status == fph.PermissionStatus.PERMANENTLY_DENIED:
            await ph.open_app_settings()
            page.show_snack_bar(
                ft.SnackBar(content=ft.Text("相册权限已永久禁用，请前往系统设置手动开启"))
            )
            return False

    except AttributeError:
        print("[Picker] 权限库无READ_MEDIA_IMAGES枚举，降级使用旧版存储权限")
    except Exception as e:
        print(f"[Picker] 高版本权限申请异常，降级处理：{e}")

    # ========== 第二级：降级为原有 STORAGE 存储权限（保留原有方式） ==========
    print("[Picker] 降级申请 STORAGE 存储权限（原有兼容方式）")
    status = await ph.request(fph.Permission.STORAGE)
    print(f"[Picker] STORAGE 授权结果：{status}")

    if status == fph.PermissionStatus.GRANTED:
        return True

    if status == fph.PermissionStatus.PERMANENTLY_DENIED:
        await ph.open_app_settings()
        page.show_snack_bar(
            ft.SnackBar(content=ft.Text("相册权限已永久禁用，请前往系统设置手动开启"))
        )
        return False

    # 普通拒绝
    page.show_snack_bar(ft.SnackBar(content=ft.Text("未授予相册读取权限")))
    return False

async def pick_image_async(page: ft.Page) -> Optional[str]:
    print("[Picker] 鸿蒙4.x 相册权限适配启动")
    if page.data is None:
        page.data = {}
    if page.data.get("picker_lock", False):
        print("[Picker] 文件选择器正在运行，禁止重复唤起")
        return None
    page.data["picker_lock"] = True
    result_path: Optional[str] = None

    try:
        # ========== 替换为新的多级权限适配 ==========
        if page.platform == ft.PagePlatform.ANDROID:
            has_permission = await request_gallery_permission(page)
            if not has_permission:
                return None

        # 原有选图逻辑完全保留
        file_picker = ft.FilePicker()
        files = await file_picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.IMAGE
        )
        if files and len(files) > 0:
            result_path = files[0].path

    except Exception as err:
        print(f"[Picker] 相册运行异常：{err}")
        page.show_snack_bar(ft.SnackBar(content=ft.Text(f"打开相册失败：{str(err)}")))
    finally:
        page.data["picker_lock"] = False

    return result_path


def show_camera_view(page: ft.Page, on_picture_taken: Callable[[str], None]):
    print("[Camera] 最终修复版相机启动")

    if page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.LINUX, ft.PagePlatform.MACOS):
        async def desktop_fallback():
            path = await pick_image_async(page)
            if path:
                on_picture_taken(path)
        page.run_task(desktop_fallback)
        return

    is_initialized = False
    flash_on = False
    camera_widget = fc.Camera(
        expand=True,
        preview_enabled=True,
    )

    async def close_camera():
        nonlocal is_initialized, flash_on
        if flash_on:
            try:
                await camera_widget.set_flash_mode(fc.FlashMode.OFF)
                flash_on = False
            except Exception:
                pass
        is_initialized = False
        page.pop_dialog()
        page.update()

    async def toggle_flash(e):
        nonlocal flash_on
        if not is_initialized:
            show_snack(page, "相机正在初始化，请稍候...", ft.Colors.ORANGE)
            return

        flash_on = not flash_on
        try:
            if flash_on:
                await camera_widget.set_flash_mode(fc.FlashMode.TORCH)
                flash_btn.icon = ft.Icons.FLASH_ON
            else:
                await camera_widget.set_flash_mode(fc.FlashMode.OFF)
                flash_btn.icon = ft.Icons.FLASH_OFF
            flash_btn.update()
        except AttributeError:
            show_snack(page, "闪光灯控制不可用", ft.Colors.ORANGE)
            flash_on = not flash_on
        except Exception as ex:
            print(f"[Camera] 闪光灯异常: {ex}")
            show_snack(page, "闪光灯控制失败", ft.Colors.ORANGE)
            flash_on = not flash_on

    async def take_photo():
        nonlocal is_initialized, flash_on
        if not is_initialized:
            show_snack(page, "相机正在初始化，请稍候...", ft.Colors.ORANGE)
            return

        # 记录拍照前闪光灯是否开启
        was_flash_on = flash_on

        try:
            # 如果闪光灯开启，先延迟1秒，期间保持灯光亮着
            if was_flash_on:
                await asyncio.sleep(1)

            # 拍照时闪光灯保持开启（不提前关闭）
            img_data = await camera_widget.take_picture()

            # 拍照成功后关闭闪光灯（避免一直亮着）
            if was_flash_on:
                await camera_widget.set_flash_mode(fc.FlashMode.OFF)
                flash_on = False
                flash_btn.icon = ft.Icons.FLASH_OFF
                flash_btn.update()

            # 处理图片数据（原有代码保持不变）
            if isinstance(img_data, str):
                if "," in img_data:
                    _, b64_body = img_data.split(",", 1)
                    img_bytes = base64.b64decode(b64_body)
                else:
                    img_bytes = base64.b64decode(img_data)
            elif isinstance(img_data, bytes):
                img_bytes = img_data
            else:
                raise Exception("图片数据格式无效")

            if not img_bytes:
                show_snack(page, "拍照失败，请重试", ft.Colors.RED)
                return

            tmp_path = tempfile.mktemp(suffix=".jpg")
            with open(tmp_path, "wb") as f:
                f.write(img_bytes)

            await close_camera()
            on_picture_taken(tmp_path)

        except Exception as e:
            # 异常时也要确保闪光灯关闭
            if was_flash_on:
                try:
                    await camera_widget.set_flash_mode(fc.FlashMode.OFF)
                    flash_on = False
                    flash_btn.icon = ft.Icons.FLASH_OFF
                    flash_btn.update()
                except:
                    pass
            print(f"[Camera] 拍照异常：{e}")
            show_snack(page, f"拍照失败：{str(e)[:30]}", ft.Colors.RED)

    def on_camera_state(e: fc.CameraStateEvent):
        nonlocal is_initialized
        if e.has_error:
            print(f"[Camera] 相机错误：{e.error_description}")
            show_snack(page, f"相机错误：{e.error_description[:30]}", ft.Colors.RED)
            is_initialized = False
        elif e.is_preview_paused:
            is_initialized = False
        else:
            is_initialized = True
        page.update()

    camera_widget.on_state_change = on_camera_state

    async def init_camera():
        nonlocal is_initialized
        try:
            cam_list = await camera_widget.get_available_cameras()
            if not cam_list:
                raise Exception("未检测到可用摄像头")

            selected_cam = cam_list[0]
            for cam in cam_list:
                if cam.lens_direction == fc.CameraLensDirection.BACK:
                    selected_cam = cam
                    break
            print(f"[Camera] 使用摄像头: {selected_cam.name}")

            await camera_widget.initialize(
                description=selected_cam,
                resolution_preset=fc.ResolutionPreset.HIGH,
                enable_audio=False,
                image_format_group=fc.ImageFormatGroup.JPEG,
            )

            try:
                await camera_widget.lock_capture_orientation()
            except Exception as ex:
                print(f"[Camera] 锁定方向失败（不影响使用）：{ex}")

            is_initialized = True
            print("[Camera] 相机初始化完成")

        except Exception as e:
            print(f"[Camera] 初始化失败：{e}")
            show_snack(page, f"相机启动失败：{str(e)[:30]}", ft.Colors.RED)
            await close_camera()

    flash_btn = ft.IconButton(
        icon=ft.Icons.FLASH_OFF,
        icon_size=28,
        bgcolor=ft.Colors.WHITE,
        padding=8,
        style=ft.ButtonStyle(shape=ft.CircleBorder()),
        tooltip="闪光灯",
        on_click=lambda e: page.run_task(toggle_flash, e),
    )

    take_btn = ft.IconButton(
        icon=ft.Icons.CAMERA,
        icon_color=ft.Colors.WHITE,
        bgcolor=ft.Colors.BLUE_600,
        icon_size=48,
        on_click=lambda e: page.run_task(take_photo),
    )

    camera_dialog = ft.AlertDialog(
        modal=True,
        content_padding=ft.Padding(0, 0, 0, 0),
        title_padding=ft.Padding(0, 0, 0, 0),
        actions_padding=ft.Padding(0, 0, 0, 0),
        inset_padding=ft.Padding(0, 0, 0, 0),
        content=ft.Stack(
            controls=[
                # 相机底层预览
                ft.Container(
                    content=camera_widget,
                    expand=True,
                    alignment=ft.Alignment(0, 0),
                ),
                # 闪光灯按钮：左上角绝对定位
                ft.Container(
                    content=flash_btn,
                    left=16,
                    top=16,
                    width=48,
                    height=48,
                ),
                # 拍照按钮：底部居中绝对定位
                ft.Container(
                    content=take_btn,
                    left=0,
                    right=0,
                    bottom=24,
                    alignment=ft.Alignment(0, 0),
                ),
            ],
            expand=True,
            width=page.width,
            height=page.height,
        ),
        actions=[],
    )

    page.show_dialog(camera_dialog)
    page.update()
    page.run_task(init_camera)

def show_image_source_dialog(page: ft.Page, on_image_selected: Callable[[str], None], title: str = "选择图片"):
    close_all_dialogs(page)
    is_desktop = page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.LINUX, ft.PagePlatform.MACOS)

    async def pick_and_callback():
        path = await pick_image_async(page)
        print(path)
        if path:
            try:
                on_image_selected(path)
            except Exception as ex:
                print(f"[Picker] callback error: {ex}")

    def on_gallery(e):
        dlg.open = False
        page.update()
        safe_remove_dialog(page, dlg)
        page.run_task(pick_and_callback)

    def on_camera(e):
        dlg.open = False
        page.update()
        safe_remove_dialog(page, dlg)
        # 调用新的相机函数
        show_camera_view(page, on_image_selected)

    def on_cancel(e):
        dlg.open = False
        page.update()
        safe_remove_dialog(page, dlg)

    if is_desktop:
        dlg = ft.AlertDialog(
            title=ft.Text(title, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.ListTile(leading=ft.Icon(ft.Icons.PHOTO, color=ft.Colors.GREEN),
                            title=ft.Text("选择图片"), on_click=on_gallery)
            ], tight=True),
            actions=[ft.TextButton("取消", on_click=on_cancel)]
        )
    else:
        dlg = ft.AlertDialog(
            title=ft.Text(title, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.ListTile(leading=ft.Icon(ft.Icons.CAMERA_ALT, color=ft.Colors.BLUE),
                            title=ft.Text("拍照"), on_click=on_camera),
                ft.ListTile(leading=ft.Icon(ft.Icons.PHOTO, color=ft.Colors.GREEN),
                            title=ft.Text("从相册选择"), on_click=on_gallery)
            ], tight=True),
            actions=[ft.TextButton("取消", on_click=on_cancel)]
        )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()


def barcode_image_decode(file_path: str, timeout: float = 3.0) -> List[str]:
    """
    使用 pyzbar 本地解码图片中的条码/二维码。
    设置超时限制，防止长时间阻塞。
    若解码失败或超时，返回空列表。
    """
    def _decode():
        codes = []
        try:
            img = PILImage.open(file_path)
            # 转灰度可提高解码速度（可选）
            if img.mode != 'L':
                img = img.convert('L')
            barcodes = pyzbar_decode(img)
            for barcode in barcodes:
                data = barcode.data.decode('utf-8').strip()
                if data:
                    codes.append(data)
        except ImportError:
            print("[Barcode] pyzbar 未安装或 zbar 库缺失")
        except Exception as e:
            print(f"[Barcode] 解码异常: {e}")
        return codes

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_decode)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"[Barcode] 解码超时 ({timeout}s)")
            return []


async def show_code_selector(page: ft.Page, codes: List[str], callback: Callable[[str], None]):
    if not codes:
        return

    # 选中条码
    def handle_select(e):
        selected_code = e.control.data
        # 官方关闭弹窗
        page.pop_dialog()

        async def run_cb():
            await asyncio.sleep(0.02)
            callback(selected_code)
        page.run_task(run_cb)

    # 取消关闭
    def handle_cancel(e):
        page.pop_dialog()

    items = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.QR_CODE),
            title=ft.Text(code),
            on_click=handle_select,
            data=code
        )
        for code in codes
    ]
    if not items:
        items.append(ft.Text("没有可识别的条码"))

    # 严格对齐官方 modal AlertDialog 写法
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("发现多个条码/二维码", weight=ft.FontWeight.BOLD),
        content=ft.Column(items, tight=True, scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton("取消", on_click=handle_cancel)
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=lambda e: None
    )

    # 官方标准打开弹窗方式，不需要手动操作 overlay
    page.show_dialog(dlg)
    page.update()
    await asyncio.sleep(0)


def unified_barcode_scan(page: ft.Page, result_callback: Callable[[str], None], title: str = "扫码识别"):
    print(f"[Barcode] unified_barcode_scan called, title='{title}'")

    def on_image_selected(path):
        preview_img = ft.Image(src=path, width=300, height=300, fit="contain")
        status_text = ft.Text(
            "请确认图片包含条码/二维码，点击“开始识别”",
            size=14,
            color=ft.Colors.BLUE
        )
        start_btn = ft.Button("开始识别", icon=ft.Icons.CAMERA_ALT)
        cancel_btn = ft.TextButton("取消")

        # 取消按钮：官方方式关闭弹窗
        def do_cancel(e):
            page.pop_dialog()

        # 开始识别
        def do_start(e):
            start_btn.disabled = True
            status_text.value = "🔄 识别中，请稍候..."
            status_text.color = ft.Colors.ORANGE
            page.update()

            # 识别成功回调
            async def _handle_result(code_list):
                # 【关键点】先调用官方接口关闭预览弹窗
                page.pop_dialog()
                await asyncio.sleep(0.05)

                if code_list:
                    if len(code_list) == 1:
                        # 单个条码直接回调业务逻辑，图片上传数据库可在这里异步执行，不受弹窗关闭影响
                        result_callback(code_list[0])
                    else:
                        # 多个条码唤起选择弹窗
                        await show_code_selector(page, code_list, result_callback)
                else:
                    show_snack(page, "未识别到条码或超时", ft.Colors.RED)

            # 识别异常回调
            async def _handle_error(error_msg):
                page.pop_dialog()
                show_snack(page, f"识别异常: {error_msg[:30]}", ft.Colors.RED)

            # 子线程执行耗时解码
            def decode_thread():
                try:
                    code_list = barcode_image_decode(path, timeout=3.0)
                    # 抛入页面异步事件循环
                    page.run_task(_handle_result, code_list)
                except Exception as ex:
                    page.run_task(_handle_error, str(ex))

            threading.Thread(target=decode_thread, daemon=True).start()

        cancel_btn.on_click = do_cancel
        start_btn.on_click = do_start

        # 严格对齐官方 AlertDialog 标准写法
        preview_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("预览图片", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    preview_img,
                    ft.Divider(height=10),
                    status_text,
                ],
                tight=True,
                spacing=10,
                width=min(get_window_width(page) * 0.8, 400),
            ),
            actions=[
                cancel_btn,
                start_btn,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: None
        )

        # 官方标准打开弹窗，不再手动 append overlay
        page.show_dialog(preview_dlg)
        page.update()

    show_image_source_dialog(page, on_image_selected, title)

# ====================== 业务工具函数 ======================
def get_product_by_model(model):
    conn = get_db_conn()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT code, model, spec, factory, category, piece, price,
                          union_subsidy, gov_subsidy, old_discount
                   FROM base_product WHERE model=%s""", (model,))
    row = cur.fetchone()
    conn.close()
    return row

def query_product_by_code(code):
    conn = get_db_conn()
    if not conn:
        return None
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT code, model, spec, factory, category, piece, price,
                          union_subsidy, gov_subsidy, old_discount
                   FROM base_product WHERE code=%s""", (code,))
    row = cur.fetchone()
    conn.close()
    return row

def add_product_from_scan(page, code, callback):
    def save_product(e):
        model = model_input.value.strip()
        if not model:
            show_alert(page, "提示", "型号不能为空")
            return
        try:
            price = float(price_input.value or 0)
            union = float(union_input.value or 0)
            gov = float(gov_input.value or 0)
            old = float(old_input.value or 0)
        except:
            show_alert(page, "提示", "价格/补贴请输入数字")
            return

        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO base_product
                        (code, model, spec, factory, category, piece, price,
                         union_subsidy, gov_subsidy, old_discount)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (code, model, spec_input.value, factory_input.value,
                         category_input.value, piece_input.value, price,
                         union, gov, old))
            conn.commit()
            show_alert(page, "恭喜", "产品添加成功", lambda e: (
                setattr(dialog, 'open', False),
                safe_remove_dialog(page, dialog),
                callback(model)
            ))
        except Exception as ex:
            show_alert(page, "提示", f"添加失败: {ex}")
        finally:
            conn.close()

    model_input = ft.TextField(label="型号*", width=250)
    code_input = ft.TextField(label="69码", value=code, width=250, read_only=True)
    factory_input = ft.TextField(label="品牌", width=250)
    category_input = ft.TextField(label="品类", width=250)
    spec_input = ft.TextField(label="规格", width=250)
    piece_input = ft.TextField(label="单位", value="台", width=250)
    price_input = ft.TextField(label="单价", value="0", width=250)
    union_input = ft.TextField(label="工会补贴%", value="0", width=250)
    gov_input = ft.TextField(label="国家补贴%", value="0", width=250)
    old_input = ft.TextField(label="旧机折扣", value="0", width=250)

    dialog = ft.AlertDialog(
        title=ft.Text("新增产品"),
        content=ft.Column([model_input, code_input, factory_input, category_input,
                           spec_input, piece_input, price_input, union_input,
                           gov_input, old_input], tight=True, spacing=8,
                          scroll=ft.ScrollMode.AUTO),
        actions=[ft.TextButton("保存", on_click=save_product),
                 ft.TextButton("取消", on_click=lambda e: (setattr(dialog, 'open', False), safe_remove_dialog(page, dialog)))]
    )
    page.overlay.append(dialog)
    dialog.open = True
    page.update()

def upload_image_to_db(file_path: str, file_type: str, biz_no: str, prefix:str, delete_old: bool = True) -> tuple[bool, Optional[str], str]:
    """
    纯后台图片入库函数，无任何UI操作
    返回：(是否成功, 成功时返回db标记, 失败时返回错误信息)
    """
    if not biz_no:
        return False, None, "业务编号不能为空"
    try:
        img_bytes = compress_image_to_bytes(file_path)
        file_name = f"{prefix}{biz_no}.jpg"
        conn = get_db_conn()
        if not conn:
            return False, None, "数据库连接异常"
        cur = conn.cursor()
        if delete_old:
            cur.execute("DELETE FROM erp_files WHERE file_type=%s AND biz_no=%s", (file_type, biz_no))
        cur.execute(
            """INSERT INTO erp_files (file_type, biz_no, file_name, file_data) 
               VALUES (%s, %s, %s, %s)""",
            (file_type, biz_no, file_name, img_bytes)
        )
        conn.commit()
        conn.close()
        return True, f"db:{file_type}:{biz_no}", ""
    except Exception as ex:
        print(f"图片入库异常:{str(ex)}")
        return False, None, str(ex)[:60]

def get_file_from_db(file_type, biz_no):
    conn = get_db_conn()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT file_data FROM erp_files WHERE file_type=%s AND biz_no=%s ORDER BY id DESC LIMIT 1",
        (file_type, biz_no)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def load_saved_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("username", ""), data.get("password", "")
        except:
            pass
    return "", ""

def save_credentials(username, password):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            json.dump({"username": username, "password": password}, f)
    except Exception as e:
        print(f"保存凭据失败: {e}")

def clear_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        try:
            os.remove(CREDENTIALS_FILE)
        except Exception as e:
            print(f"清除凭据失败: {e}")

# ====================== 上传动画封装（Dialog顶层版，盖住所有弹窗） ======================
_loading_dialog = None

async def show_upload_loading_async(page: ft.Page, text: str = "正在上传，请稍候..."):
    """
    用官方Dialog实现顶层加载弹窗
    自动盖住所有已打开的弹窗，底层界面完全不可操作
    """
    global _loading_dialog
    if _loading_dialog is not None:
        return

    # 构造加载内容，严格对齐官方ProgressRing示例
    loading_content = ft.Column(
        controls=[
            ft.ProgressRing(width=48, height=48, stroke_width=4),
            ft.Text(text, size=16),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20,
        width=200,
        height=140,
    )

    # 模态加载弹窗：无按钮、用户无法手动关闭
    _loading_dialog = ft.AlertDialog(
        modal=True,
        content=loading_content,
        actions=[],
        content_padding=ft.Padding(20, 30, 20, 30),
    )

    page.show_dialog(_loading_dialog)
    page.update()

    # 确保弹窗渲染完成
    await asyncio.sleep(0.15)

def hide_upload_loading(page: ft.Page):
    """关闭加载弹窗"""
    global _loading_dialog
    if _loading_dialog is not None:
        page.pop_dialog()
        _loading_dialog = None
        page.update()

# ====================== 主程序 ======================
def main(page: ft.Page):
    print("=== APP START ===")
    print(f"Platform: {page.platform}")
    # 在 main 函数开头添加权限请求（Android 端）
    page._permission_handler = fph.PermissionHandler()
    page.title = "玖诚电器ERP"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.spacing = 0
    page.window_resizable = True

    page._picker_lock = False
    page._persistent_picker = None
    current_user = None
    main_content = ft.Column(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)

    # ---------- 配置界面 ----------
    config_overlay = ft.Container(
        content=ft.Column(
            [
                ft.Text("数据库服务器配置", size=20, weight=ft.FontWeight.BOLD),
                ft.Divider(height=10),
                ft.TextField(label="服务器地址（支持IPv6）", value=DB_HOST, width=300),
                ft.TextField(label="端口", value=str(DB_PORT), width=300),
                ft.TextField(label="数据库用户名", value=DB_USER, width=300),
                ft.TextField(label="数据库密码", password=True, can_reveal_password=True, value=DB_PASSWORD, width=300,
                             on_blur=lambda e: setattr(e.control, 'password', True) or e.control.update()),
                ft.TextField(label="数据库名称", value=DB_DATABASE, width=300),
                ft.Divider(height=10),
                ft.Column(
                    [
                        ft.Button("读取主机IPv6", on_click=lambda e: read_ipv6(page), width=260),
                        ft.Button("测试连接", on_click=lambda e: test_conn(), width=260),
                        ft.Button("保存并重新登录", on_click=lambda e: save_and_restart(), width=260),
                        ft.OutlinedButton("取消", on_click=lambda e: hide_config(), width=260),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.WHITE,
        padding=20,
        expand=True,
        visible=False,
    )

    def get_field_width(page, ratio=1, subtract=40):
        base_width = get_window_width(page)
        calc_width = (base_width - subtract) / ratio
        return max(100, round(calc_width))

    def get_fields():
        controls = config_overlay.content.controls
        return {
            "host": controls[2],
            "port": controls[3],
            "user": controls[4],
            "pwd": controls[5],
            "db": controls[6],
        }

    def read_ipv6(page):
        input_tf = ft.TextField(
            label="读取码",
            width=280,
            autofocus=True,
            on_change=lambda e: (setattr(error_tip, "value", ""), page.update())
        )
        error_tip = ft.Text("", size=12, text_align=ft.TextAlign.CENTER)

        def fetch_data(key):
            try:
                web_url = f"https://textdb.online/{key}"
                resp = requests.get(web_url, timeout=10)
                raw_text = resp.text.strip()
                decoded = raw_text
                try:
                    decoded = base64.b64decode(raw_text).decode("utf-8")
                except Exception:
                    decoded = raw_text

                if resp.status_code != 200:
                    error_tip.value = f"读取失败：HTTP {resp.status_code}"
                    error_tip.color = ft.Colors.RED
                    page.update()
                    return
                if not raw_text:
                    error_tip.value = "读取码对应数据为空"
                    error_tip.color = ft.Colors.RED
                    page.update()
                    return
                if ":" in decoded:
                    fields = get_fields()
                    fields["host"].value = decoded
                    page.update()
                    error_tip.value = f"已填入IPv6: {decoded}"
                    error_tip.color = ft.Colors.GREEN
                    page.update()
                else:
                    error_tip.value = "内容不是有效IPv6地址"
                    error_tip.color = ft.Colors.RED
                    page.update()
            except Exception as ex:
                error_tip.value = f"读取失败: {str(ex)[:50]}"
                error_tip.color = ft.Colors.RED
                page.update()

        def on_submit(e):
            read_key = input_tf.value.strip()
            if not read_key:
                error_tip.value = "请输入读取码"
                error_tip.color = ft.Colors.RED
                page.update()
                return
            error_tip.value = "读取ipv6中，请稍等……"
            error_tip.color = ft.Colors.BLUE
            page.update()
            threading.Thread(target=fetch_data, args=(read_key,), daemon=True).start()

        def on_cancel(e):
            input_dlg.open = False
            page.update()
            safe_remove_dialog(page, input_dlg)

        dialog_content = ft.Container(
            content=ft.Stack([
                input_tf,
                ft.Row([error_tip], alignment=ft.MainAxisAlignment.CENTER, top=78)
            ]),
            width=280,
            height=95
        )
        input_dlg = ft.AlertDialog(
            title=ft.Text("请输入读取码"),
            content=dialog_content,
            modal=True,
            content_padding=ft.Padding(16, 10, 16, 8),
            actions=[
                ft.TextButton("确定", on_click=on_submit),
                ft.TextButton("取消", on_click=on_cancel),
            ]
        )
        page.overlay.append(input_dlg)
        input_dlg.open = True
        page.update()

    def test_conn():
        fields = get_fields()
        host = fields["host"].value.strip()
        port_str = fields["port"].value.strip()
        user = fields["user"].value.strip()
        pwd = fields["pwd"].value.strip()
        db = fields["db"].value.strip()
        if not host or not port_str or not user or not db:
            show_alert(page,"提示", "请填写完整的连接信息")
            return
        try:
            port = int(port_str)
            conn = mysql.connector.connect(
                host=host, port=port, user=user,
                password=pwd, database=db,
                use_pure=True, connect_timeout=3
            )
            conn.close()
            show_alert(page,"成功", "✅ 连接成功")
        except Exception as ex:
            show_alert(page,"错误", f"❌ 连接失败: {str(ex)[:50]}")

    def save_and_restart():
        nonlocal current_user
        fields = get_fields()
        host = fields["host"].value.strip()
        port = int(fields["port"].value)
        user = fields["user"].value.strip()
        pwd = fields["pwd"].value.strip()
        db = fields["db"].value.strip()

        save_server_config(host, port, user, pwd, db)
        global DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_DATABASE
        DB_HOST = host
        DB_PORT = port
        DB_USER = user
        DB_PASSWORD = pwd
        DB_DATABASE = db

        config_overlay.visible = False
        page.update()

        def on_ok(e):
            nonlocal current_user
            current_user = None
            page.controls.clear()
            page.add(ft.Stack([login_container, config_overlay], expand=True))
            page.update()

        show_alert(page, "配置保存成功", "数据库配置已更新，请重新登录", on_ok)

    def show_config(e):
        config_overlay.visible = True
        fields = get_fields()
        fields["host"].value = DB_HOST
        fields["port"].value = str(DB_PORT)
        fields["user"].value = DB_USER
        fields["pwd"].value = DB_PASSWORD
        fields["db"].value = DB_DATABASE
        page.update()

    def hide_config():
        config_overlay.visible = False
        page.update()

    # ---------- 登录 ----------
    saved_username, saved_password = load_saved_credentials()
    username_input = ft.TextField(label="用户名", width=300, autofocus=True, value=saved_username)

    # 密码输入框：保留眼睛图标，但失去焦点自动隐藏明文
    password_input = ft.TextField(
        label="密码",
        password=True,
        can_reveal_password=True,
        width=300,
        value=saved_password,
        on_blur=lambda e: setattr(e.control, 'password', True) or e.control.update()
    )

    remember_cb = ft.Checkbox(label="自动登录", value=bool(saved_username and saved_password))

    def login_action():
        nonlocal current_user
        uname = username_input.value.strip()
        pwd = password_input.value.strip()
        if not uname or not pwd:
            show_alert(page, "提示", "请输入用户名和密码")
            return
        if remember_cb.value:
            save_credentials(uname, pwd)
        else:
            clear_credentials()

        # 显示登录加载动画
        loading_dlg = ft.AlertDialog(
            content=ft.Column(
                [
                    ft.ProgressRing(),
                    ft.Text("正在登录，服务器连接中，请稍后…"),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=20,
                tight=True,
            ),
            modal=True,
        )
        page.show_dialog(loading_dlg)
        page.update()

        # 辅助函数：关闭当前对话框
        def close_dialog():
            page.pop_dialog()

        async def do_login_async():
            nonlocal current_user
            try:
                # 将阻塞的数据库连接操作放到线程中执行
                conn = await asyncio.to_thread(get_db_conn)
                if not conn:
                    close_dialog()
                    show_alert(page, "提示", "数据库连接失败，请检查服务器配置")
                    return

                cur = conn.cursor(dictionary=True)

                # 查询操作也放入线程，避免阻塞 UI
                def query_user():
                    cur.execute(
                        "SELECT id,username,real_name,role,permissions,expire_date FROM users WHERE username=%s AND password=%s",
                        (uname, md5_pwd(pwd))
                    )
                    return cur.fetchone()

                user = await asyncio.to_thread(query_user)
                conn.close()

                if user:
                    expire = user.get("expire_date")
                    if expire and expire < date.today():
                        close_dialog()
                        show_alert(page, "提示", "用户权限已过期，请联系管理员")
                        return
                    current_user = user
                    close_dialog()
                    build_main_ui()
                else:
                    close_dialog()
                    show_alert(page, "提示", "用户名或密码错误")
            except Exception as ex:
                close_dialog()
                show_alert(page, "错误", f"登录异常: {str(ex)[:50]}")

        # 启动异步登录任务
        page.run_task(do_login_async)

    def do_login(e):
        login_action()

    login_btn = ft.Button("登录", on_click=do_login, width=300)
    settings_btn = ft.IconButton(ft.Icons.SETTINGS, on_click=show_config)

    login_column = ft.Column(
        [
            ft.Row([ft.Container(expand=True), settings_btn], alignment=ft.MainAxisAlignment.END),
            ft.Container(height=20),
            ft.Text("玖诚电器ERP", size=32, weight=ft.FontWeight.BOLD),
            ft.Image(src=get_asset_path("login_bg.png"), width=100, height=100),
            username_input,
            password_input,
            remember_cb,
            login_btn,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=15,
    )
    login_container = ft.Container(
        content=login_column,
        alignment=ft.Alignment(0, 0),
        expand=True,
        padding=ft.Padding(top=30, left=0, right=0, bottom=0),
    )

    page.add(
        ft.Stack(
            [
                login_container,
                config_overlay,
            ],
            expand=True,
        )
    )
    page.update()

    # 自动获取IPv6（后台）
    def auto_fetch_ipv6():
        key = "songtaotianmaoyoupin"
        try:
            url = f"https://textdb.online/{key}"
            resp = requests.get(url, timeout=10)
            raw = resp.text.strip()
            if resp.status_code == 200 and raw:
                try:
                    decoded = base64.b64decode(raw).decode("utf-8")
                except:
                    decoded = raw
                if ":" in decoded:
                    fields = get_fields()
                    fields["host"].value = decoded
                    save_server_config(decoded, DB_PORT, DB_USER, DB_PASSWORD, DB_DATABASE)
                    global DB_HOST
                    DB_HOST = decoded
                    print(f"[Auto IPv6] 已自动获取并设置IPv6: {decoded}")
                    page.update()
                else:
                    print("[Auto IPv6] 获取的内容不是有效IPv6，跳过")
            else:
                print("[Auto IPv6] 获取失败，HTTP状态码:", resp.status_code)
        except Exception as e:
            print(f"[Auto IPv6] 异常: {e}")

    threading.Thread(target=auto_fetch_ipv6, daemon=True).start()

    # ---------- 自动登录（如果勾选了自动登录） ----------
    if remember_cb.value and saved_username and saved_password:
        def auto_login():
            async def login_wrapper():
                login_action()
            page.run_task(login_wrapper)
        threading.Timer(0.5, auto_login).start()

    # ---------- 主界面框架 ----------
    def build_main_ui():
        page.controls.clear()
        page.scroll = None

        appbar = ft.AppBar(
            title=ft.Text("玖诚电器ERP"),
            center_title=False,
            bgcolor=ft.Colors.SURFACE,
            actions=[ft.IconButton(ft.Icons.PERSON, on_click=lambda e: show_profile())]
        )

        if current_user and current_user.get("role") == "超级管理员":
            perm_list = PERMISSIONS
        else:
            perm_list = (current_user.get("permissions") or "").split(",") if current_user else []
            if not perm_list:
                perm_list = ["🏠 首页"]
            perm_list = [p for p in perm_list if p in PERMISSIONS]
            if not perm_list:
                perm_list = ["🏠 首页"]

        destinations = []
        for p in PERMISSIONS:
            if p in perm_list:
                destinations.append(
                    ft.NavigationBarDestination(
                        icon=PERMISSION_ICONS.get(p, ft.Icons.HELP),
                        label=p
                    )
                )

        nav_bar = ft.NavigationBar(
            destinations=destinations,
            on_change=on_nav_change,
            elevation=8
        )

        main_content.controls.clear()
        main_content.expand = True
        main_content.scroll = ft.ScrollMode.AUTO

        main_layout = ft.Column(
            [
                appbar,
                main_content,
                nav_bar,
            ],
            spacing=0,
            expand=True,
        )
        page.add(main_layout)
        show_home()

    def on_nav_change(e):
        selected_index = e.control.selected_index
        if selected_index < len(e.control.destinations):
            label = e.control.destinations[selected_index].label
            if label == "🏠 首页":
                show_home()
            elif label == "🧾 销售":
                show_sale()
            elif label == "📥 入库":
                show_inbound()
            elif label == "🚚 运输":
                show_transport()
            elif label == "🔧 安装":
                show_install()
            elif label == "📦 库存":
                show_stock()
            elif label == "更多":
                show_more_menu()

    def show_profile():
        if not current_user:
            return
        name = current_user.get("real_name") or current_user.get("username")
        role = current_user.get("role", "")
        expire = current_user.get("expire_date", "")
        info = f"用户名：{name}\n角色：{role}"
        if expire:
            info += f"\n有效期至：{expire}"
        show_alert(page, "个人资料", info)

    #==================== 首页 =================

    # ==================== 全局缓存变量 ====================
    _photo_cache = {"date": None, "photos": []}

    # ==================== 辅助函数 ====================
    def detect_image_mime(file_data: bytes) -> str:
        """根据文件头检测图片 MIME 类型"""
        if file_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        elif file_data.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif file_data.startswith(b'GIF87a') or file_data.startswith(b'GIF89a'):
            return 'image/gif'
        elif file_data.startswith(b'BM'):
            return 'image/bmp'
        elif file_data[:4] == b'RIFF' and file_data[8:12] == b'WEBP':
            return 'image/webp'
        else:
            return 'image/png'  # 默认

    def show_large_image(base64_str, cust_name, upload_time_str, model, mime='image/png'):
        """点击缩略图后弹出大图对话框"""
        print(f"正在打开大图: {cust_name}, 时间: {upload_time_str}")  # 调试用
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{cust_name or '未知客户'}---{model}"),
            content=ft.Container(
                content=ft.Image(
                    src=f"data:{mime};base64,{base64_str}",
                    fit="contain"
                ),
                width=600,
                height=400,
            ),
            actions=[ft.TextButton("关闭", on_click=lambda e: page.pop_dialog())],
        )
        # 使用 overlay 显示对话框（Flet 0.86.2 稳定）
        page.show_dialog(dlg)

    # ==================== 主页面函数 ====================
    # ==================== 新增：异步刷新函数 ====================
    async def refresh_home(e):
        """点击刷新按钮：检查数据库新照片，有则更新缓存并重新渲染首页"""
        # 显示“正在检查”对话框
        checking_dlg = ft.AlertDialog(
            modal=True,
            content=ft.Column(
                [
                    ft.ProgressRing(),
                    ft.Text("正在检查新照片...")
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )
        page.show_dialog(checking_dlg)
        page.update()

        try:
            # 在后台线程中执行数据库查询和缓存更新（避免阻塞UI）
            has_new = await asyncio.to_thread(check_and_update_photos)

            if has_new:
                # 更新对话框文本为“发现新照片，正在加载...”
                checking_dlg.content = ft.Column(
                    [
                        ft.ProgressRing(),
                        ft.Text("发现新上传照片，正在加载……")
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                )
                page.update()
                await asyncio.sleep(0.5)  # 短暂停留，让用户看到动画

                # 关闭对话框，重新构建首页（显示新照片）
                page.pop_dialog()
                page.update()
                show_home()  # 重新加载整个首页（统计和照片区域都会刷新）
            else:
                # 没有新照片，直接关闭对话框
                page.pop_dialog()
                page.update()
                # 可选：提示没有新照片（这里暂不提示，保持安静）
        except Exception as ex:
            # 异常时关闭对话框并提示错误
            page.pop_dialog()
            page.update()
            show_alert(page, "错误", f"刷新失败: {str(ex)}")

    def check_and_update_photos():
        """
        同步函数（运行在后台线程）：
        查询当天所有照片，与缓存比较，如有新增则更新缓存，返回是否有新增。
        """
        conn = get_db_conn()
        if not conn:
            raise Exception("无法连接数据库")
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT ef.file_data, ef.upload_time, t.cust_name, t.model
                FROM erp_files ef
                LEFT JOIN transport t ON ef.biz_no = t.out_order_no
                WHERE DATE(ef.upload_time) = CURDATE()
                ORDER BY ef.upload_time DESC
            """)
            rows = cur.fetchall()

            # 构建最新的照片列表
            new_photos = []
            for file_data, upload_time, cust_name, model in rows:
                if file_data:
                    mime = detect_image_mime(file_data)
                    base64_str = base64.b64encode(file_data).decode('utf-8')
                    upload_time_str = upload_time.strftime('%Y-%m-%d %H:%M:%S') if upload_time else ''
                    new_photos.append({
                        "base64": base64_str,
                        "mime": mime,
                        "cust_name": cust_name,
                        "upload_time_str": upload_time_str,
                        "model": model
                    })

            # 与现有缓存比较（主要判断数量是否增加，或最新时间是否更新）
            old_photos = _photo_cache["photos"]
            has_new = False
            if len(new_photos) > len(old_photos):
                has_new = True
            elif new_photos and old_photos:
                # 如果数量相同但最新时间不同，也视为有新照片（应对同秒多传但数量未变的情况）
                new_latest = max(p["upload_time_str"] for p in new_photos)
                old_latest = max(p["upload_time_str"] for p in old_photos)
                if new_latest > old_latest:
                    has_new = True
            elif new_photos and not old_photos:
                has_new = True

            # 如有新增，更新缓存
            if has_new:
                _photo_cache["photos"] = new_photos
                _photo_cache["date"] = date.today().isoformat()
            return has_new
        finally:
            conn.close()

    # ==================== 修改后的 show_home 函数 ====================
    def show_home():
        main_content.controls.clear()
        conn = get_db_conn()
        if not conn:
            main_content.controls.append(ft.Text("无法连接数据库"))
            page.update()
            return
        cur = conn.cursor()

        # ---------- 查询统计数据（原有逻辑） ----------
        cur.execute("SELECT SUM(s_qty) FROM stock_now")
        total_stock = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(DISTINCT order_no) FROM sale_main WHERE MONTH(order_date)=MONTH(CURDATE())")
        month_sales = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM transport WHERE status='待出库'")
        pending_trans = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM install WHERE status='待安装'")
        pending_install = cur.fetchone()[0] or 0

        # ---------- 检查缓存：日期变化则重新加载照片 ----------
        today_str = date.today().isoformat()
        if _photo_cache["date"] != today_str:
            _photo_cache["date"] = today_str
            _photo_cache["photos"] = []

            # 查询当天上传的照片，关联客户姓名
            cur.execute("""
                SELECT ef.file_data, ef.upload_time, t.cust_name, t.model
                FROM erp_files ef
                LEFT JOIN transport t ON ef.biz_no = t.out_order_no
                WHERE DATE(ef.upload_time) = CURDATE()
                ORDER BY ef.upload_time DESC
            """)
            rows = cur.fetchall()
            for file_data, upload_time, cust_name, model in rows:
                if file_data:
                    mime = detect_image_mime(file_data)
                    base64_str = base64.b64encode(file_data).decode('utf-8')
                    upload_time_str = upload_time.strftime('%Y-%m-%d %H:%M:%S') if upload_time else ''
                    _photo_cache["photos"].append({
                        "base64": base64_str,
                        "mime": mime,
                        "cust_name": cust_name,
                        "upload_time_str": upload_time_str,
                        "model": model
                    })
        conn.close()

        # ---------- 构建统计卡片行 ----------
        cards_data = [
            ("📦", "当前库存", str(total_stock), ft.Colors.BLUE),
            ("📊", "本月销售单数", str(month_sales), ft.Colors.GREEN),
            ("🚚", "待出库订单", str(pending_trans), ft.Colors.ORANGE),
            ("🔧", "待安装订单", str(pending_install), ft.Colors.RED),
        ]
        padding, spacing = 20, 15
        card_width = (get_window_width(page) - padding * 2 - spacing) // 2
        cards_row = ft.Row(
            wrap=True, spacing=spacing, run_spacing=spacing,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER
        )
        for icon, label, value, color in cards_data:
            cards_row.controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(icon, size=30),
                                ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=color),
                                ft.Text(label, size=12, color=ft.Colors.GREY_700)
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=5
                        ),
                        alignment=ft.Alignment(0, 0),
                        padding=15,
                        width=card_width,
                        height=card_width * 1.1
                    ),
                    elevation=3
                )
            )

        # ---------- 构建图片预览区 ----------
        photo_section = []
        if _photo_cache["photos"]:
            photo_section.append(ft.Container(height=20))
            photo_section.append(
                ft.Text("今日照片", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700)
            )
            photo_section.append(ft.Container(height=10))

            photo_row = ft.Row(
                wrap=True,
                spacing=15,
                run_spacing=15,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START
            )
            for photo in _photo_cache["photos"]:
                thumb = ft.Image(
                    src=f"data:{photo['mime']};base64,{photo['base64']}",
                    width=130,
                    height=130,
                    fit="cover",
                    border_radius=10,
                )
                display_time = photo["upload_time_str"][5:16] if len(photo["upload_time_str"]) >= 16 else photo[
                    "upload_time_str"]
                text = ft.Text(
                    f"{photo['cust_name'] or '未知客户'}  {display_time}",
                    size=12,
                    color=ft.Colors.GREY_700,
                    text_align=ft.TextAlign.CENTER,
                    width=150,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS
                )
                item = ft.Column(
                    [thumb, text],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=5
                )
                clickable = ft.Container(
                    content=item,
                    on_click=lambda e, b64=photo["base64"], cn=photo["cust_name"], ut=photo["upload_time_str"],
                                    md=photo["model"],
                                    mime=photo['mime']: show_large_image(b64, cn, ut, md, mime),
                    ink=True,
                    border_radius=10,
                    padding=5,
                    tooltip="点击放大"
                )
                photo_row.controls.append(clickable)
            photo_section.append(photo_row)
        else:
            photo_section.append(ft.Container(height=20))
            photo_section.append(ft.Text("今日暂无上传照片", size=16, color=ft.Colors.GREY))

        # ---------- 整合主列 ----------
        main_column = ft.Column(
            [
                cards_row,
                ft.Container(height=20),
                ft.Row(
                    [ft.Button("刷新数据", icon=ft.Icons.REFRESH, on_click=refresh_home, width=200)],
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                *photo_section
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        main_content.controls.append(main_column)
        page.update()

    # ========== 销售订单 ==========

    def show_sale():
        main_content.controls.clear()
        order_no = gen_order_no()
        current_county = ""
        county_list = []

        conn = get_db_conn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT county FROM base_address WHERE TRIM(city) = %s GROUP BY county ORDER BY MIN(id)",
                            ("铜仁市",))
                county_list = [row[0].strip() for row in cur.fetchall()]
            except:
                pass
            finally:
                conn.close()
        if not county_list:
            county_list = ["碧江区", "万山区", "松桃苗族自治县", "玉屏县", "江口县", "石阡县", "思南县", "德江县",
                           "沿河县", "印江县", "其他"]
        current_county = county_list[2] if len(county_list) > 2 else county_list[0] if county_list else ""

        w1 = get_field_width(page, 2, 60)
        w2 = get_field_width(page, 1, 40)
        w3 = get_field_width(page, 3, 80)

        # ========== 中文字体加载（备用） ==========
        def load_chinese_font(size: int = 28):
            try:
                font_path = get_asset_path("simhei.ttf")
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                pass
            try:
                font_path = get_asset_path("SIMLI.TTF")
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                pass
            android_font_paths = [
                "/system/fonts/NotoSansCJK-Regular.ttc",
                "/system/fonts/DroidSansFallback.ttf",
                "/system/fonts/HarmonyOS_Sans_SC_Regular.ttf",
                "/system/fonts/Miui-Regular.ttf",
                "/system/fonts/SourceHanSansCN-Regular.otf",
            ]
            for path in android_font_paths:
                try:
                    if os.path.exists(path):
                        return ImageFont.truetype(path, size)
                except Exception:
                    continue
            try:
                if os.name == "nt":
                    return ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", size)
                elif sys.platform == "darwin":
                    return ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", size)
            except Exception:
                pass
            return ImageFont.load_default(size)

        # ---------- 客户输入及联想 ----------
        cust_input = ft.TextField(label="客户名称", hint_text="输入2字以上查询", width=w1)
        cust_suggestions = ft.Column(spacing=0, visible=False)

        def load_customer_suggestions(val):
            if len(val) < 2:
                cust_suggestions.controls.clear()
                cust_suggestions.visible = False
                cust_suggestions.update()
                page.update()
                return
            conn = get_db_conn()
            if not conn: return
            cur = conn.cursor()
            cur.execute(
                "SELECT name,phone,card_holder,card_no,county,street,community,detail_addr FROM base_customer WHERE name LIKE %s LIMIT 8",
                (f"%{val}%",))
            rows = cur.fetchall()
            conn.close()
            cust_suggestions.controls.clear()
            if not rows:
                cust_suggestions.visible = False
                cust_suggestions.update()
                page.update()
                return
            for row in rows:
                cust_suggestions.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Text(f"{row[0]} | {row[1]}"),
                            padding=10,
                            on_click=lambda e, r=row: select_customer(r)
                        )
                    )
                )
            cust_suggestions.visible = True
            cust_suggestions.update()
            page.update()

        def select_customer(row):
            nonlocal current_county
            cust_input.value = row[0]
            phone.value = row[1] or ""
            card_holder.value = row[2] or ""
            card_no.value = row[3] or ""
            if row[4]:
                selected_county_text.value = row[4]
                current_county = row[4]
                load_streets()
            street_dropdown.value = row[5] or None
            community_input.value = row[6] or ""
            detail_addr.value = row[7] or ""
            cust_suggestions.controls.clear()
            cust_suggestions.visible = False
            cust_suggestions.update()
            page.update()

        # ---------- 商品型号输入及联想 ----------
        model_input_width = w2
        scan_btn = ft.IconButton(
            ft.Icons.CAMERA_ALT, icon_size=24, tooltip="扫码识别型号",
            on_click=lambda e: unified_barcode_scan(page, on_scan_success, title="扫码识别商品"),
            style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT), opacity=0.6
        )
        model_input = ft.TextField(label="商品型号", hint_text="输入2字以上查询", width=model_input_width,
                                   suffix=scan_btn)
        model_suggestions = ft.Column(spacing=0, visible=False)

        def load_model_suggestions(val):
            if len(val) < 2:
                model_suggestions.controls.clear()
                model_suggestions.visible = False
                model_suggestions.update()
                page.update()
                return
            conn = get_db_conn()
            if not conn: return
            cur = conn.cursor()
            cur.execute(
                "SELECT model,price,union_subsidy,gov_subsidy,old_discount FROM base_product WHERE model LIKE %s LIMIT 8",
                (f"%{val}%",))
            rows = cur.fetchall()
            conn.close()
            model_suggestions.controls.clear()
            if not rows:
                model_suggestions.visible = False
                model_suggestions.update()
                page.update()
                return
            for row in rows:
                model_suggestions.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Text(f"{row[0]} (¥{row[1]})"),
                            padding=10,
                            on_click=lambda e, r=row: select_product(r)
                        )
                    )
                )
            model_suggestions.visible = True
            model_suggestions.update()
            page.update()

        def select_product(row):
            model_input.value = row[0]
            price.value = str(row[1] or 0)
            union_subsidy.value = str(row[2] or 0)
            gov_subsidy.value = str(row[3] or 0)
            old_discount.value = str(row[4] or 0)
            model_suggestions.controls.clear()
            model_suggestions.visible = False
            model_suggestions.update()
            page.update()

        cust_input.on_change = lambda e: load_customer_suggestions(cust_input.value.strip())
        model_input.on_change = lambda e: load_model_suggestions(model_input.value.strip())

        # ---------- 其他输入控件 ----------
        phone = ft.TextField(label="联系电话", width=w1)
        card_holder = ft.TextField(label="工会卡持卡人", width=w1)
        card_no = ft.TextField(label="工会卡号", width=w1)

        default_county = county_list[2] if len(county_list) > 2 else county_list[0] if county_list else ""
        selected_county_text = ft.Text(default_county)
        county_selector = ft.Stack(
            [
                ft.Container(
                    content=ft.Row(
                        [selected_county_text, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, color=ft.Colors.OUTLINE)],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    width=w1, padding=ft.Padding(10, 16, 10, 10),
                    border=ft.Border(
                        left=ft.BorderSide(1, ft.Colors.OUTLINE),
                        right=ft.BorderSide(1, ft.Colors.OUTLINE),
                        top=ft.BorderSide(1, ft.Colors.OUTLINE),
                        bottom=ft.BorderSide(1, ft.Colors.OUTLINE)
                    ),
                    border_radius=4, bgcolor=ft.Colors.WHITE
                ),
                ft.Container(
                    content=ft.Text("所在县", size=12, color=ft.Colors.OUTLINE),
                    left=8, top=-7, bgcolor=ft.Colors.WHITE, padding=ft.Padding(2, 2, 0, 0)
                )
            ],
            width=w1
        )

        street_dropdown = ft.Dropdown(label="街道", width=w1, options=[])
        community_input = ft.TextField(label="小区/村", width=w1)
        detail_addr = ft.TextField(label="详细地址", width=w1)

        def load_streets():
            nonlocal current_county
            if not current_county:
                street_dropdown.options.clear()
                street_dropdown.value = None
                street_dropdown.update()
                page.update()
                return
            conn = get_db_conn()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT street FROM base_address WHERE TRIM(county)=%s GROUP BY street ORDER BY MIN(id)",
                        (current_county,))
                    streets = [row[0].strip() for row in cur.fetchall()]
                except:
                    streets = []
                finally:
                    conn.close()
                street_dropdown.options = [ft.dropdown.Option(s) for s in streets]
                street_dropdown.value = "蓼皋街道" if streets else None
                street_dropdown.update()
                page.update()

        def build_county_handler(name):
            def handler(e):
                nonlocal current_county
                current_county = name
                selected_county_text.value = name
                county_selector.update()
                load_streets()

            return handler

        county_menu_items = [ft.PopupMenuItem(content=ft.Text(c), on_click=build_county_handler(c)) for c in
                             county_list]
        county_popup = ft.PopupMenuButton(content=county_selector, items=county_menu_items)

        send_date = ft.TextField(label="拟送货日期", hint_text="YYYY-MM-DD", value=date.today().isoformat(), width=w1)
        order_remark = ft.TextField(label="订单备注", width=w1)
        out_order_no = ft.TextField(label="外部订单号", value="01", width=w3)
        qty = ft.TextField(label="数量", value="1", width=w3)
        price = ft.TextField(label="单价", width=w3)
        old_discount = ft.TextField(label="旧机折扣(元)", value="0", width=w3)
        union_subsidy = ft.TextField(label="工会补贴%", value="0", width=w3)
        gov_subsidy = ft.TextField(label="国家补贴%", value="0", width=w3)
        store_discount = ft.TextField(label="门店优惠(元)", value="0", width=w3)
        item_remark = ft.TextField(label="商品备注", width=w3)
        need_install_cb = ft.Checkbox(label="需要安装", value=False)
        add_btn = ft.Button("添加商品", icon=ft.Icons.ADD)
        items_list = ft.Column(spacing=5)
        total_label = ft.Text("合计: 0.00 元", size=16, weight=ft.FontWeight.BOLD)
        items = []
        next_item_seq = 1

        # ---------- 扫码回调 ----------
        def on_scan_success(code, prod=None):
            if prod:
                model_input.value = prod["model"]
                price.value = str(prod["price"])
                union_subsidy.value = str(prod.get("union_subsidy", 0))
                gov_subsidy.value = str(prod.get("gov_subsidy", 0))
                old_discount.value = str(prod.get("old_discount", 0))
                page.update()
                page.run_task(show_alert_async, page, "成功", f"已加载产品: {prod['model']}")
            else:
                prod = query_product_by_code(code)
                if prod:
                    model_input.value = prod["model"]
                    price.value = str(prod["price"])
                    union_subsidy.value = str(prod.get("union_subsidy", 0))
                    gov_subsidy.value = str(prod.get("gov_subsidy", 0))
                    old_discount.value = str(prod.get("old_discount", 0))
                    page.update()
                    page.run_task(show_alert_async, page, "成功", f"已加载产品: {prod['model']}")
                else:
                    add_product_from_scan(page, code, lambda m: (setattr(model_input, 'value', m), page.update()))

        # ---------- 商品清单管理 ----------
        def refresh_items():
            items_list.controls.clear()
            total = 0.0
            for idx, it in enumerate(items):
                total += it["total"]
                items_list.controls.append(
                    ft.Row(
                        [
                            ft.Text(
                                f"[{it['out_order_no']}] {it['model']} x{it['qty']}  ¥{it['total']:.2f}  {'[安装]' if it['need_install'] else ''}"
                            ),
                            ft.IconButton(ft.Icons.DELETE, on_click=lambda e, i=idx: remove_item(i))
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                )
            total_label.value = f"合计: {total:.2f} 元"
            page.update()

        def remove_item(idx):
            items.pop(idx)
            refresh_items()

        def add_item(e):
            nonlocal next_item_seq
            m = model_input.value.strip()
            try:
                qt = int(qty.value or 0)
                unit_price = float(price.value or 0)
                old = float(old_discount.value or 0)
                union = float(union_subsidy.value or 0)
                gov = float(gov_subsidy.value or 0)
                store = float(store_discount.value or 0)
            except:
                show_alert(page, "提示", "数量和金额必须是数字")
                return
            if not m or qt <= 0:
                show_alert(page, "提示", "请完整填写商品信息")
                return
            prod = get_product_by_model(m)
            if not prod:
                # 商品不存在时弹窗选择操作
                def on_add_product_click(e):
                    page.pop_dialog()
                    # 复用已有的添加商品函数（自动弹出扫描或手动录入界面）
                    add_product_from_scan(page, "", lambda m: (setattr(model_input, 'value', m), page.update()))

                def on_back_click(e):
                    page.pop_dialog()

                dlg = ft.AlertDialog(
                    title=ft.Text("提示"),
                    content=ft.Text(f"型号 {m} 不存在，请先添加商品或返回重新填写"),
                    actions=[
                        ft.TextButton("返回重填", on_click=on_back_click),
                        ft.Button("添加商品", on_click=on_add_product_click),
                    ],
                    modal=True,
                )
                page.show_dialog(dlg)
                return

            # ===== 风管机判断逻辑 =====
            spec = prod.get("spec", "")
            is_duct = "风管机" in spec or "分管机" in spec
            has_duct_existing = any(
                "风管机" in it.get("spec", "") or "分管机" in it.get("spec", "") for it in items
            )

            if is_duct:
                if items:
                    show_alert(page, "提示", "风管机类商品不能与其他商品混装，且只能添加一个")
                    return
            else:
                if has_duct_existing:
                    show_alert(page, "提示", "风管机类订单不能添加其他商品")
                    return

            # ===== 风管机自动填充备注 =====
            if is_duct:
                factory = prod.get("factory", "")
                if factory == "璀璨":
                    item_remark.value = "1、含9米铜管内免费，超出按照120元/米收取；2、4米内出风口加长免费，回风口自费；3、含2个孔（铜管、排水各一个），超出部分自费；4、高空、支架免费；5、普通线控器一个。"
                else:
                    item_remark.value = "1、含7米铜管内免费，超出按照120元/米收取；2、4米内出风口加长免费，回风口自费；3、含2个孔（铜管、排水各一个），超出部分自费；4、高空、支架免费；5、普通线控器一个。"

            out_no = f"{next_item_seq:02d}"

            after_old = unit_price - old
            after_union = after_old * (1 - union / 100)
            after_store = after_union - store
            if gov == 0:
                final_unit = after_store
            else:
                final_unit = math.ceil(
                    after_store * (1 - gov / 100) * 100) / 100 if after_store <= 10000 else after_store - 1500
            total = final_unit * qt
            t_price = after_store

            items.append({
                "model": m,
                "out_order_no": out_no,
                "qty": qt,
                "price": unit_price,
                "old_discount": old,
                "union_subsidy": union,
                "gov_subsidy": gov,
                "store_discount": store,
                "t_price": t_price,
                "total": total,
                "need_install": need_install_cb.value,
                "sale_remark": item_remark.value,
                "factory": prod["factory"],
                "category": prod["category"],
                "spec": spec,
                "piece": prod["piece"],
                "code": prod["code"]
            })

            next_item_seq += 1
            out_order_no.value = f"{next_item_seq:02d}"

            refresh_items()

            model_input.value = ""
            qty.value = "1"
            price.value = ""
            old_discount.value = "0"
            union_subsidy.value = "0"
            gov_subsidy.value = "0"
            store_discount.value = "0"
            item_remark.value = ""
            need_install_cb.value = False
            page.update()

        add_btn.on_click = add_item

        # ---------- 工具函数 ----------
        def increment_order_no(order_no_str):
            match = re.search(r'(\d+)$', order_no_str)
            if match:
                num_str = match.group(1)
                prefix = order_no_str[:match.start()]
                num_len = len(num_str)
                new_num = int(num_str) + 1
                new_num_str = str(new_num).zfill(num_len)
                return prefix + new_num_str
            else:
                return order_no_str + "1"

        def num2rmb(num):
            if not num:
                return "人民币零元整"
            cap = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]
            unit = ["", "拾", "佰", "仟"]
            big_unit = ["", "万", "亿"]
            num = round(num, 2)
            integer_part = int(num)
            decimal_part = int(round((num - integer_part) * 100))

            int_str = ""
            if integer_part == 0:
                int_str = "零"
            else:
                groups = []
                n = integer_part
                while n > 0:
                    groups.append(n % 10000)
                    n = n // 10000
                for i, group in enumerate(groups):
                    group_str = ""
                    g = group
                    zero_flag = False
                    for j in range(4):
                        digit = g % 10
                        if digit == 0:
                            if zero_flag:
                                group_str = "零" + group_str
                                zero_flag = False
                        else:
                            group_str = cap[digit] + unit[j] + group_str
                            zero_flag = True
                        g = g // 10
                    if group == 0:
                        if i < len(groups) - 1 and int_str and not int_str.startswith("零"):
                            int_str = "零" + int_str
                    else:
                        int_str = group_str + big_unit[i] + int_str
                    while "零零" in int_str:
                        int_str = int_str.replace("零零", "零")
                    if int_str.endswith("零"):
                        int_str = int_str[:-1]

            jiao = decimal_part // 10
            fen = decimal_part % 10
            dec_str = ""
            if jiao == 0 and fen == 0:
                dec_str = "整"
            else:
                if jiao > 0:
                    dec_str += cap[jiao] + "角"
                elif integer_part > 0:
                    dec_str += "零"
                if fen > 0:
                    dec_str += cap[fen] + "分"

            return f"人民币{int_str}元{dec_str}"

        # ========== 生成电子订单 PDF（修复跨列越界+严格14列对齐版） ==========
        def generate_pdf_by_template(order_no, items, full_addr, cust_name, cust_phone, send_date, payment_dict):
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib import colors
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import tempfile
            import xml.sax.saxutils as saxutils

            # ========== 辅助函数 ==========
            def safe_para(text):
                if not isinstance(text, str):
                    text = str(text)
                text = text.replace("<br/>", "\x00BR\x00")
                text = saxutils.escape(text)
                text = text.replace("\x00BR\x00", "<br/>")
                return text

            # ========== 字体加载 ==========
            font_normal = "Helvetica"
            font_bold = "Helvetica-Bold"
            font_path = get_asset_path("simhei.ttf")
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont("Simhei", font_path))
                    font_normal = "Simhei"
                    font_bold = "Simhei"
                except Exception:
                    font_normal = None
            if font_normal is None or font_normal == "Helvetica":
                try:
                    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                    font_normal = "STSong-Light"
                    font_bold = "STSong-Light"
                except Exception:
                    font_normal = "Helvetica"
                    font_bold = "Helvetica-Bold"

            # ========== 样式定义 ==========
            company_title_style = ParagraphStyle("company", fontName=font_bold, fontSize=16, leading=22, alignment=1)
            order_title_style = ParagraphStyle("order_title", fontName=font_bold, fontSize=14, leading=18, alignment=1)
            label_style = ParagraphStyle("label", fontName=font_normal, fontSize=10, leading=14, alignment=2)
            content_style = ParagraphStyle("content", fontName=font_normal, fontSize=10, leading=14, alignment=0)
            table_head_style = ParagraphStyle("th", fontName=font_bold, fontSize=9, leading=12, alignment=1)
            table_content_style = ParagraphStyle("td", fontName=font_normal, fontSize=9, leading=12, alignment=1)
            tip_text_style = ParagraphStyle("tip_text", fontName=font_normal, fontSize=9, leading=14, alignment=0)
            vertical_tip_style = ParagraphStyle("vtip", fontName=font_normal, fontSize=11, leading=20, alignment=1)
            sign_style = ParagraphStyle("sign", fontName=font_normal, fontSize=10, leading=14, alignment=0)
            bill_copy_style = ParagraphStyle("bill_copy", fontName=font_normal, fontSize=9, leading=12, alignment=0)
            page_no_style = ParagraphStyle("page_no", fontName=font_normal, fontSize=9, leading=12, alignment=1)

            # ========== 从数据库获取完整客户信息 ==========
            conn = get_db_conn()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT cust_name, phone, receiver_phone, card_holder, card_no FROM sale_main WHERE order_no=%s",
                        (order_no,)
                    )
                    row = cur.fetchone()
                    if row:
                        cust_name_db = row[0] or cust_name
                        cust_phone_db = row[1] or cust_phone
                        receiver_phone_db = row[2] or f"{cust_name_db} {cust_phone_db}"
                        card_holder_db = row[3] or ""
                        card_no_db = row[4] or ""
                    else:
                        cust_name_db = cust_name
                        cust_phone_db = cust_phone
                        receiver_phone_db = f"{cust_name} {cust_phone}"
                        card_holder_db = ""
                        card_no_db = ""
                except Exception:
                    cust_name_db = cust_name
                    cust_phone_db = cust_phone
                    receiver_phone_db = f"{cust_name} {cust_phone}"
                    card_holder_db = ""
                    card_no_db = ""
                finally:
                    conn.close()
            else:
                cust_name_db = cust_name
                cust_phone_db = cust_phone
                receiver_phone_db = f"{cust_name} {cust_phone}"
                card_holder_db = ""
                card_no_db = ""

            print_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

            # ========== 固定文案 ==========
            COMPANY_NAME = safe_para("贵州玖诚电器有限责任公司（松桃天猫优品东晟府店）")
            ORDER_TITLE = safe_para("销售订单")
            STORE_ADDR = safe_para("贵州省松桃苗族自治县蓼皋街道东晟府一、二号楼12-15门面")
            STORE_PHONE = safe_para("13096861211/13096863533")
            PAYEE_NAME = safe_para("成雯")
            BILL_COPY_1 = safe_para(f"电子单时间戳：{print_time}")
            BILL_COPY_2 = safe_para("电子订单请妥善保存，修改无效")

            # ========== 判断风管机 ==========
            has_duct = any("风管机" in it.get("spec", "") or "分管机" in it.get("spec", "") for it in items)
            if has_duct:
                duct_item = next(
                    (it for it in items if "风管机" in it.get("spec", "") or "分管机" in it.get("spec", "")), None)
                tip_content = duct_item.get("sale_remark", "") if duct_item else ""
            else:
                tip_content = """1.请确认以上资料正确无误，收货时核对相应物品及配件外观完好无损，配件齐全。
                2.所购新机在7天内若有质量问题，经厂家售后鉴定后包换新机（请确保原包装箱/盒、保修卡等配件完好无损），若机身或机壳刮花损坏、影响二次销售时，无法支持换机，只做维修处理
                3.请按照厂家说明书规范使用，机器在质保期内若有质量问题，经厂家售后鉴定后免费维修，人为损坏（如入液、受潮、私自拆装等）均不在免费维修范围内。
                4.本单据可作为保修凭证，请妥善保管，如需售后，请出示此单。"""

            # ========== 列宽配置 ==========
            col_widths = [32, 40, 40, 130, 85, 28, 28, 43, 37, 35, 35, 35, 55, 60]
            total_cols = 14

            # ========== 分页计算 ==========
            page_size = 1 if has_duct else 5
            total_pages = max(1, (len(items) + page_size - 1) // page_size)
            page_items_list = [items[i:i + page_size] for i in range(0, len(items), page_size)]

            # ========== 全局信息 ==========
            pay_text = safe_para("、".join([f"{k}{v:.2f}元" for k, v in payment_dict.items()]))
            card_holder_text = safe_para(card_holder_db)
            card_no_text = safe_para(card_no_db)
            remark_text = safe_para(order_remark.value or "")
            handler_name = safe_para(current_user.get("real_name", "系统管理员"))

            send_date_str = send_date.isoformat() if hasattr(send_date, 'isoformat') else str(send_date)
            today_str = date.today().isoformat()

            # ========== 创建文档 ==========
            pdf_dir = tempfile.gettempdir()
            pdf_path = os.path.join(pdf_dir, f"电子订单_{order_no}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=landscape(A4),
                                    topMargin=15, bottomMargin=12, leftMargin=12, rightMargin=12)
            story = []

            # ========== 逐页构建 ==========
            for page_idx, page_items in enumerate(page_items_list, 1):
                # 标题区
                title_data = [
                    [Paragraph(COMPANY_NAME, company_title_style)],
                    [Paragraph(ORDER_TITLE, order_title_style)]
                ]
                title_table = Table(title_data, colWidths=[sum(col_widths)], rowHeights=[26, 22])
                title_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]))
                story.append(title_table)
                story.append(Spacer(1, 2))

                # 订单信息区
                info_rows = []
                info_rows.append([
                    Paragraph(safe_para("下单日期："), label_style), "",
                    Paragraph(safe_para(today_str), content_style), "", "", "", "", "", "", "", "", "", "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("门店地址："), label_style), "",
                    Paragraph(STORE_ADDR, content_style), "", "", "", "", "",
                    Paragraph(safe_para("门店电话："), label_style), "", "",
                    Paragraph(STORE_PHONE, content_style), "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("订 单 号："), label_style), "",
                    Paragraph(safe_para(order_no), content_style), "",
                    Paragraph(safe_para("销售类型："), label_style), "",
                    Paragraph(safe_para("标准销售"), content_style), "",
                    Paragraph(safe_para("拟发货日期："), label_style), "", "",
                    Paragraph(safe_para(send_date_str), content_style), "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("客      户："), label_style), "",
                    Paragraph(safe_para(cust_name_db), content_style), "",
                    Paragraph(safe_para("客户电话："), label_style), "",
                    Paragraph(safe_para(cust_phone_db), content_style), "",
                    Paragraph(safe_para("收货人/电话："), label_style), "", "",
                    Paragraph(safe_para(receiver_phone_db), content_style), "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("送货地址："), label_style), "",
                    Paragraph(safe_para(full_addr), content_style), "", "", "", "",
                    Paragraph(safe_para("工会卡持卡人："), label_style), "", "",
                    Paragraph(card_holder_text, content_style), "", "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("付款方式："), label_style), "",
                    Paragraph(pay_text, content_style), "", "", "",
                    Paragraph(safe_para("工会卡卡号："), label_style), "", "",
                    Paragraph(card_no_text, content_style), "", "", "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("备    注："), label_style), "",
                    Paragraph(remark_text, content_style), "", "", "", "", "", "", "", "", "", "", ""
                ])

                info_table = Table(info_rows, colWidths=col_widths, rowHeights=[20, 20, 20, 20, 20, 20, 20])
                info_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)), ("SPAN", (0, 2), (1, 2)),
                    ("SPAN", (0, 3), (1, 3)), ("SPAN", (0, 4), (1, 4)), ("SPAN", (0, 5), (1, 5)),
                    ("SPAN", (0, 6), (1, 6)),
                    ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                    ("SPAN", (2, 0), (3, 0)), ("ALIGN", (2, 0), (3, 0), "LEFT"),
                    ("SPAN", (2, 1), (7, 1)), ("ALIGN", (2, 1), (7, 1), "LEFT"),
                    ("SPAN", (8, 1), (10, 1)), ("ALIGN", (8, 1), (10, 1), "RIGHT"),
                    ("SPAN", (11, 1), (13, 1)), ("ALIGN", (11, 1), (13, 1), "LEFT"),
                    ("SPAN", (2, 2), (3, 2)), ("ALIGN", (2, 2), (3, 2), "LEFT"),
                    ("SPAN", (4, 2), (5, 2)), ("ALIGN", (4, 2), (5, 2), "RIGHT"),
                    ("SPAN", (6, 2), (7, 2)), ("ALIGN", (6, 2), (7, 2), "LEFT"),
                    ("SPAN", (8, 2), (10, 2)), ("ALIGN", (8, 2), (10, 2), "RIGHT"),
                    ("SPAN", (11, 2), (13, 2)), ("ALIGN", (11, 2), (13, 2), "LEFT"),
                    ("SPAN", (2, 3), (3, 3)), ("ALIGN", (2, 3), (3, 3), "LEFT"),
                    ("SPAN", (4, 3), (5, 3)), ("ALIGN", (4, 3), (5, 3), "RIGHT"),
                    ("SPAN", (6, 3), (7, 3)), ("ALIGN", (6, 3), (7, 3), "LEFT"),
                    ("SPAN", (8, 3), (10, 3)), ("ALIGN", (8, 3), (10, 3), "RIGHT"),
                    ("SPAN", (11, 3), (13, 3)), ("ALIGN", (11, 3), (13, 3), "LEFT"),
                    ("SPAN", (2, 4), (6, 4)), ("ALIGN", (2, 4), (6, 4), "LEFT"),
                    ("SPAN", (7, 4), (9, 4)), ("ALIGN", (7, 4), (9, 4), "RIGHT"),
                    ("SPAN", (10, 4), (13, 4)), ("ALIGN", (10, 4), (13, 4), "LEFT"),
                    ("SPAN", (2, 5), (5, 5)), ("ALIGN", (2, 5), (5, 5), "LEFT"),
                    ("SPAN", (6, 5), (8, 5)), ("ALIGN", (6, 5), (8, 5), "RIGHT"),
                    ("SPAN", (9, 5), (13, 5)), ("ALIGN", (9, 5), (13, 5), "LEFT"),
                    ("SPAN", (2, 6), (13, 6)), ("ALIGN", (2, 6), (13, 6), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]))
                story.append(info_table)
                story.append(Spacer(1, 2))

                # 商品表 + 合计行
                table_data = []
                headers = ["序号", "品牌", "大类", "型号", "规格", "单位", "数量", "单价",
                           "旧机<br/>补贴", "工会<br/>补贴", "门店<br/>优惠", "国家<br/>补贴", "金额<br/>小计", "备注"]
                table_data.append([Paragraph(safe_para(h), table_head_style) for h in headers])
                for i, item in enumerate(page_items):
                    remark_display = "见温馨提示" if has_duct else item.get("sale_remark", "")
                    row = [
                        safe_para(str(i + 1)),
                        safe_para(item.get("factory", "")),
                        safe_para(item.get("category", "")),
                        safe_para(item.get("model", "")),
                        safe_para(item.get("spec", "")),
                        safe_para(item.get("piece", "")),
                        safe_para(str(item["qty"])),
                        safe_para(f"{item['price']:.2f}"),
                        safe_para(f"{item['old_discount']:.2f}"),
                        safe_para(f"{item['union_subsidy']:.0f}%"),
                        safe_para(f"{item['store_discount']:.2f}"),
                        safe_para(f"{item['gov_subsidy']:.0f}%"),
                        safe_para(f"{item['total']:.2f}"),
                        safe_para(remark_display),
                    ]
                    table_data.append([Paragraph(cell, table_content_style) for cell in row])
                for _ in range(page_size - len(page_items)):
                    table_data.append([""] * total_cols)

                # 当前页合计
                page_total_amt = round(sum(it["total"] for it in page_items), 2)
                page_total_amt_upper = num2rmb(page_total_amt)
                total_row = [
                    Paragraph(safe_para("金额合计（大写）："), label_style), "", "",
                    Paragraph(safe_para(page_total_amt_upper), content_style), "", "", "",
                    Paragraph(safe_para("（小写）"), label_style), "",
                    Paragraph(safe_para(f"rmb {page_total_amt:.2f}元"), content_style), "", "", "", ""
                ]
                table_data.append(total_row)

                goods_table = Table(table_data, colWidths=col_widths)
                goods_style = [
                    ("FONTNAME", (0, 0), (-1, -1), font_normal),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("SPAN", (0, -1), (2, -1)), ("ALIGN", (0, -1), (2, -1), "RIGHT"),
                    ("SPAN", (3, -1), (6, -1)), ("ALIGN", (3, -1), (6, -1), "LEFT"),
                    ("SPAN", (7, -1), (8, -1)), ("ALIGN", (7, -1), (8, -1), "CENTER"),
                    ("SPAN", (9, -1), (13, -1)), ("ALIGN", (9, -1), (13, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
                goods_table.setStyle(TableStyle(goods_style))
                story.append(goods_table)

                # ========== 温馨提示（直接位于金额合计下方） ==========
                tip_html = tip_content.replace("\n", "<br/>")
                tip_row = [
                    Paragraph(safe_para("温<br/>馨<br/>提<br/>示"), vertical_tip_style),
                    Paragraph(safe_para(tip_html), tip_text_style),
                    "", "", "", "", "", "", "", "", "", "", "", ""
                ]
                tip_table = Table([tip_row], colWidths=col_widths, rowHeights=[90])
                tip_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("SPAN", (1, 0), (13, 0)),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("LEFTPADDING", (0, 0), (0, 0), 4),
                    ("RIGHTPADDING", (0, 0), (0, 0), 4),
                    ("LEFTPADDING", (1, 0), (-1, 0), 8),
                    ("RIGHTPADDING", (1, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(tip_table)
                story.append(Spacer(1, 4))

                # ========== 签章行 ==========
                sign_row = [
                    Paragraph(safe_para("收款单位（公章）："), sign_style), "", "", "",
                    Paragraph(safe_para(f"收款人：{PAYEE_NAME}"), sign_style), "", "", "", "",
                    Paragraph(safe_para(f"经手人：{handler_name}"), sign_style), "", "", "", ""
                ]
                sign_table = Table([sign_row], colWidths=col_widths, rowHeights=[22])
                sign_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, 0), (3, 0)), ("SPAN", (4, 0), (8, 0)),
                    ("SPAN", (9, 0), (13, 0)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                story.append(sign_table)
                story.append(Spacer(1, 3))

                # 联次行
                copy_row = [
                    Paragraph(BILL_COPY_1, bill_copy_style), "", "", "", "", "",
                    Paragraph(BILL_COPY_2, bill_copy_style), "", "", "", "", "", "", ""
                ]
                copy_table = Table([copy_row], colWidths=col_widths, rowHeights=[18])
                copy_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, 0), (5, 0)), ("ALIGN", (0, 0), (5, 0), "LEFT"),
                    ("SPAN", (6, 0), (13, 0)), ("ALIGN", (6, 0), (13, 0), "RIGHT"),
                ]))
                story.append(copy_table)
                story.append(Spacer(1, 2))

                # 页码
                page_no_text = safe_para(f"第{page_idx}页/共{total_pages}页")
                page_no_table = Table([[Paragraph(page_no_text, page_no_style)]], colWidths=[sum(col_widths)],
                                      rowHeights=[16])
                page_no_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(page_no_table)

                if page_idx < total_pages:
                    story.append(PageBreak())

            # 公章
            seal_path = get_asset_path("icon.png")

            def add_seal(canvas, doc):
                if os.path.exists(seal_path):
                    try:
                        canvas.saveState()
                        canvas.drawImage(seal_path, 72, 90, width=75, height=75, mask='auto')
                        canvas.restoreState()
                    except Exception:
                        pass

            try:
                doc.build(story, onFirstPage=add_seal, onLaterPages=add_seal)
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise
            return pdf_path

        # ========== 生成电子订单入口 ==========
        def generate_electronic_order(order_no, items, full_addr, cust_name, phone, send_date, payment_dict):
            try:
                print("\n========== 调用 generate_electronic_order ==========")
                pdf_path = generate_pdf_by_template(order_no, items, full_addr, cust_name, phone, send_date,
                                                    payment_dict)
                show_pdf_preview(pdf_path, order_no)
            except Exception as e:
                import traceback
                traceback.print_exc()
                show_alert(page, "错误", f"生成电子订单失败：{str(e)}")

        # ========== PDF预览与分享 ==========
        def show_pdf_preview(pdf_path, order_no):
            share = ft.Share()

            async def share_pdf(e):
                try:
                    share = ft.Share()
                    if page.web:
                        # Web 平台不支持路径分享，改用字节分享
                        with open(pdf_path, "rb") as f:
                            file_bytes = f.read()
                        share_file = ft.ShareFile.from_bytes(
                            file_bytes,
                            mime_type="application/pdf",
                            name=f"电子订单_{order_no}.pdf",
                        )
                    else:
                        share_file = ft.ShareFile.from_path(pdf_path)

                    result = await share.share_files(
                        [share_file],
                        text="电子订单",
                        title="分享电子订单",
                    )
                    show_alert(page, "提示", f"分享状态：{result.status}")
                except Exception as ex:
                    show_alert(page, "错误", f"分享失败: {str(ex)[:50]}")

            def save_pdf(e):
                try:
                    page.pop_dialog()
                    page.update()

                    async def do_save():
                        try:
                            path = await ft.FilePicker().save_file(
                                dialog_title="保存电子订单",
                                file_name=f"电子订单_{order_no}.pdf",
                                allowed_extensions=["pdf"],
                                src_bytes=open(pdf_path, "rb").read()
                            )
                            if path:
                                show_alert(page, "成功", "PDF已保存")
                        except Exception as ex:
                            show_alert(page, "错误", f"保存失败: {str(ex)[:50]}")

                    page.run_task(do_save)
                except Exception as ex:
                    show_alert(page, "错误", f"操作异常: {str(ex)[:50]}")

            dlg = ft.AlertDialog(
                title=ft.Text("电子订单已生成"),
                content=ft.Column(
                    [
                        ft.Text(f"订单文件：电子订单_{order_no}.pdf", size=14),
                        ft.Text("可分享到微信、钉钉，或保存到本地", size=12, color=ft.Colors.GREY),
                    ],
                    tight=True,
                ),
                actions=[
                    ft.Row(
                        [
                            ft.IconButton(ft.Icons.SHARE, tooltip="分享", on_click=share_pdf),
                            ft.IconButton(ft.Icons.SAVE, tooltip="保存", on_click=save_pdf),
                            ft.IconButton(ft.Icons.CLOSE, tooltip="关闭", on_click=lambda _: page.pop_dialog()),
                        ],
                        spacing=20,
                        alignment=ft.MainAxisAlignment.CENTER,
                    )
                ],
                modal=True,
            )
            page.show_dialog(dlg)

        # ========== 保存订单 ==========
        def save_order(e):
            payment_method_json = ""
            if not cust_input.value:
                show_alert(page, "提示", "客户名称不能为空")
                return
            if not items:
                show_alert(page, "提示", "请至少添加一个商品")
                return
            county = current_county
            street = street_dropdown.value
            community = community_input.value
            receiver_phone = f"{cust_input.value} {phone.value}"
            if not county:
                show_alert(page, "提示", "请选择所在县")
                return
            full_addr = f"{county}{street or ''}{community or ''}{detail_addr.value or ''}"
            try:
                send_dt = datetime.strptime(send_date.value, "%Y-%m-%d").date()
            except:
                show_alert(page, "错误", "送货日期格式错误")
                return

            total_order_amt = round(sum(it["total"] for it in items), 2)
            pay_methods = ["云闪付", "微   信", "支付宝", "刷   卡", "现   金", "未   付"]
            pay_checkboxes = {}
            pay_amount_inputs = {}

            def build_pay_method_options():
                options = []
                for method in pay_methods:
                    cb = ft.Checkbox(label=method, value=(method == "云闪付"))
                    amt_input = ft.TextField(label="金额", value=str(total_order_amt) if method == "云闪付" else "0.00",
                                             width=120, keyboard_type=ft.KeyboardType.NUMBER)
                    pay_checkboxes[method] = cb
                    pay_amount_inputs[method] = amt_input
                    options.append(ft.Row([cb, amt_input], spacing=10))
                return options

            def confirm_payment(e):
                payment_dict = {}
                for method, cb in pay_checkboxes.items():
                    if cb.value:
                        try:
                            amt = float(pay_amount_inputs[method].value or 0)
                        except:
                            amt = 0.0
                        if amt > 0:
                            payment_dict[method] = amt
                if not payment_dict:
                    show_alert(page, "提示", "请至少选择一种支付方式并填写金额")
                    return
                page.pop_dialog()
                nonlocal payment_method_json
                payment_method_json = json.dumps(payment_dict, ensure_ascii=False)
                do_save_order(payment_dict)

            payment_dialog = ft.AlertDialog(
                title=ft.Text("选择支付方式"),
                content=ft.Column(
                    [
                        ft.Text(f"订单总额：{total_order_amt:.2f} 元", weight=ft.FontWeight.BOLD),
                        ft.Divider(height=10),
                        *build_pay_method_options(),
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    width=min(get_window_width(page) - 40, 450),
                ),
                actions=[
                    ft.TextButton("取消", on_click=lambda _: page.pop_dialog()),
                    ft.Button("确认支付", on_click=confirm_payment),
                ],
                modal=True,
            )
            page.show_dialog(payment_dialog)

            def do_save_order(payment_dict):
                nonlocal next_item_seq
                current_order_no = order_no
                max_retries = 10

                for attempt in range(max_retries):
                    conn = get_db_conn()
                    if not conn:
                        show_alert(page, "错误", "数据库连接失败")
                        return
                    cur = conn.cursor()
                    try:
                        total_order = round(sum(it["total"] for it in items), 2)
                        payment_method_json_local = json.dumps(payment_dict, ensure_ascii=False)

                        cur.execute(
                            """INSERT INTO sale_main (order_no,order_date,send_date,cust_name,phone,receiver_phone,
                               card_holder,card_no,county,street,community,detail_addr,full_addr,remark,
                               order_type,sales_name,payment_method)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (current_order_no, date.today(), send_dt, cust_input.value, phone.value, receiver_phone,
                             card_holder.value, card_no.value, county, street, community, detail_addr.value, full_addr,
                             order_remark.value, "标准销售", current_user["real_name"], payment_method_json_local)
                        )

                        for it in items:
                            cur.execute(
                                """INSERT INTO sale_items (order_no,out_order_no,model,qty,price,old_discount,
                                   union_subsidy,gov_subsidy,store_discount,t_price,total,need_install,
                                   sale_remark,factory,category,spec,piece)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (current_order_no, f"{current_order_no}{it['out_order_no']}", it["model"], it["qty"],
                                 it["price"], it["old_discount"], it["union_subsidy"] / 100, it["gov_subsidy"] / 100,
                                 it["store_discount"], it["t_price"], it["total"], 1 if it["need_install"] else 0,
                                 it["sale_remark"], it["factory"], it["category"], it["spec"], it["piece"])
                            )

                            cur.execute("SELECT qty FROM stock_now WHERE model=%s", (it["model"],))
                            stock = cur.fetchone()
                            if stock:
                                cur.execute("UPDATE stock_now SET qty=qty-%s, s_qty=s_qty-%s WHERE model=%s",
                                            (it["qty"], it["qty"], it["model"]))
                            else:
                                cur.execute(
                                    "INSERT INTO stock_now (factory,model,spec,qty,s_qty) VALUES (%s,%s,%s,%s,%s)",
                                    (it["factory"], it["model"], it["spec"], -it["qty"], -it["qty"]))

                            cur.execute(
                                """INSERT INTO transport (order_date,order_no,out_order_no,cust_name,phone,full_addr,
                                   factory,category,model,spec,t_qty,send_date,status)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (date.today(), current_order_no, f"{current_order_no}{it['out_order_no']}",
                                 cust_input.value, phone.value, full_addr, it["factory"], it["category"], it["model"],
                                 it["spec"], it["qty"], send_dt, "待派单")
                            )

                            if it["need_install"]:
                                cur.execute(
                                    """INSERT INTO install (order_date,order_no,cust_name,phone,factory,model,spec,
                                       i_qty,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                    (date.today(), current_order_no, cust_input.value, phone.value, it["factory"],
                                     it["model"], it["spec"], it["qty"], "待安装")
                                )

                        cur.execute("SELECT total_amount FROM base_customer WHERE name=%s AND phone=%s",
                                    (cust_input.value, phone.value))
                        cust = cur.fetchone()
                        if cust:
                            cur.execute(
                                "UPDATE base_customer SET total_amount=total_amount+%s WHERE name=%s AND phone=%s",
                                (total_order, cust_input.value, phone.value))
                        else:
                            cur.execute("SELECT MAX(cust_id) FROM base_customer")
                            max_id = cur.fetchone()[0]
                            num = int(max_id[1:]) + 1 if max_id else 1
                            cust_id = f"C{num:05d}"
                            cur.execute(
                                """INSERT INTO base_customer (cust_id,name,phone,card_holder,card_no,county,street,
                                   community,detail_addr,full_addr,total_amount,level)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (cust_id, cust_input.value, phone.value, card_holder.value, card_no.value, county,
                                 street, community, detail_addr.value, full_addr, total_order, "三级")
                            )

                        conn.commit()
                        show_alert(page, "成功", f"订单 {current_order_no} 保存成功")

                        items_copy = [item.copy() for item in items]

                        def ask_generate_pdf(e):
                            receiver_phone = None
                            conn = get_db_conn()
                            if conn:
                                cur = conn.cursor()
                                cur.execute("SELECT cust_name,phone,receiver_phone FROM sale_main WHERE order_no=%s",
                                            (current_order_no,))
                                res = cur.fetchone()
                                if res:
                                    cust_name = res[0]
                                    phone = res[1]
                                    receiver_phone = res[2]
                                conn.close()
                            page.pop_dialog()
                            generate_electronic_order(current_order_no, items_copy, full_addr,
                                                      cust_name, phone, send_dt, payment_dict)

                        ask_dialog = ft.AlertDialog(
                            title=ft.Text("生成电子订单"),
                            content=ft.Text("订单已保存，是否生成 PDF 电子订单？"),
                            actions=[
                                ft.TextButton("否", on_click=lambda _: page.pop_dialog()),
                                ft.Button("是", on_click=ask_generate_pdf),
                            ],
                            modal=True,
                        )
                        page.show_dialog(ask_dialog)

                        cust_input.value = ""
                        phone.value = ""
                        card_holder.value = ""
                        card_no.value = ""
                        street_dropdown.options.clear()
                        community_input.value = ""
                        detail_addr.value = ""
                        order_remark.value = ""
                        send_date.value = date.today().isoformat()
                        items.clear()
                        nonlocal next_item_seq
                        next_item_seq = 1
                        out_order_no.value = "01"
                        refresh_items()
                        page.update()
                        return


                    except Exception as ex:
                        conn.rollback()
                        error_msg = str(ex)
                        # 判断是否为订单号重复冲突（MySQL 错误码 1062）
                        if hasattr(ex, 'args') and len(ex.args) > 0 and ex.args[0] == 1062:
                            current_order_no = increment_order_no(current_order_no)
                            print(f"[save_order] 订单号冲突，尝试使用 {current_order_no}")
                            if attempt == max_retries - 1:
                                show_alert(page, "错误", "订单号冲突次数过多，请稍后重试")
                                return
                            continue
                        else:
                            show_alert(page, "错误", f"保存失败: {ex}")
                            return
                    finally:
                        conn.close()

                show_alert(page, "错误", "保存失败，未知错误")

        save_btn = ft.Button("💾 保存订单", icon=ft.Icons.SAVE, on_click=save_order, bgcolor=ft.Colors.GREEN,
                             color=ft.Colors.WHITE)
        query_btn = ft.Button("🔍 查询订单", icon=ft.Icons.SEARCH, on_click=lambda e: show_order_query(),
                              bgcolor=ft.Colors.BLUE_500, color=ft.Colors.WHITE)
        btn_row = ft.Row([save_btn, query_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=10)

        cust_container = ft.Column([cust_input, cust_suggestions], spacing=0)
        model_container = ft.Column([model_input, model_suggestions], spacing=0, width=model_input_width)

        main_content.controls.append(
            ft.Column(
                [
                    ft.Text("新建销售订单", size=20, weight=ft.FontWeight.BOLD),
                    ft.Row([cust_container, phone], spacing=10, wrap=True),
                    ft.Row([card_holder, card_no], spacing=10, wrap=True),
                    ft.Row([county_popup, street_dropdown], spacing=10, wrap=True),
                    ft.Row([community_input, detail_addr], spacing=10, wrap=True),
                    ft.Row([send_date, order_remark], spacing=10, wrap=True),
                    ft.Text("商品信息", weight=ft.FontWeight.BOLD),
                    ft.Row([model_container], alignment=ft.MainAxisAlignment.START),
                    ft.Row([out_order_no, qty, price], alignment=ft.MainAxisAlignment.START, wrap=True),
                    ft.Row([old_discount, union_subsidy, gov_subsidy], alignment=ft.MainAxisAlignment.START, wrap=True),
                    ft.Row([store_discount, item_remark, need_install_cb], alignment=ft.MainAxisAlignment.START,
                           wrap=True),
                    add_btn,
                    ft.Text("商品清单", weight=ft.FontWeight.BOLD),
                    items_list,
                    total_label,
                    btn_row,
                ],
                spacing=12,
            )
        )
        page.update()

        if county_list:
            current_county = county_list[2] if len(county_list) > 2 else county_list[0] if county_list else ""
            selected_county_text.value = current_county
            load_streets()

    # ---------------------------- 订单查询 ----------------------------

    def show_order_query():
        import traceback  # 添加这行导入
        main_content.controls.clear()
        field_width = get_field_width(page, ratio=2, subtract=60)
        btn_width = field_width / 2

        order_no_input = ft.TextField(label="订单号", width=field_width * 2 + 10)
        cust_name_input = ft.TextField(label="客户姓名", width=field_width)
        phone_input = ft.TextField(label="联系方式", width=field_width)
        address_input = ft.TextField(label="地址", width=field_width)
        brand_input = ft.TextField(label="品牌", width=field_width)
        category_input = ft.TextField(label="品类", width=field_width)
        model_input = ft.TextField(label="型号", width=field_width)

        # 互斥复选框
        all_check = ft.Checkbox(label="全部", value=True)
        single_no_check = ft.Checkbox(label="单号录入", value=False)
        gov_subsidy_check = ft.Checkbox(label="国补", value=False)

        def on_check_changed(e):
            if e.control == all_check:
                if all_check.value:
                    single_no_check.value = False
                    gov_subsidy_check.value = False
                    single_no_check.update()
                    gov_subsidy_check.update()
            elif e.control == single_no_check:
                if single_no_check.value:
                    all_check.value = False
                    all_check.update()
            elif e.control == gov_subsidy_check:
                if gov_subsidy_check.value:
                    all_check.value = False
                    all_check.update()

        all_check.on_change = on_check_changed
        single_no_check.on_change = on_check_changed
        gov_subsidy_check.on_change = on_check_changed

        selected_date_str = None
        date_display = ft.Text("选择日期", size=14, color=ft.Colors.GREY_700)
        date_picker = ft.DatePicker(
            first_date=datetime(2020, 1, 1),
            last_date=datetime(2030, 12, 31)
        )

        def on_date_picked(e):
            nonlocal selected_date_str
            if date_picker.value:
                dt = date_picker.value + timedelta(hours=8)
                selected_date_str = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
                date_display.value = selected_date_str
                date_display.color = ft.Colors.BLACK
            else:
                selected_date_str = None
                date_display.value = "选择日期"
                date_display.color = ft.Colors.GREY_700
            date_display.update()
            date_picker.open = False
            page.update()

        date_picker.on_change = on_date_picked

        def pick_date(e):
            if date_picker not in page.overlay:
                page.overlay.append(date_picker)
            date_picker.open = True
            page.update()

        date_picker_btn = ft.Container(
            content=ft.Row([ft.Icon(ft.Icons.CALENDAR_TODAY, size=20, color=ft.Colors.BLUE), date_display],
                           alignment=ft.MainAxisAlignment.START, spacing=5),
            padding=ft.Padding(left=10, top=8, right=10, bottom=8),
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=8,
            width=field_width,
            on_click=pick_date,
            ink=True,
        )

        result_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

        # ========== 工具函数：人民币大写 ==========
        def num2rmb(num):
            if not num:
                return "人民币零元整"
            cap = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]
            unit = ["", "拾", "佰", "仟"]
            big_unit = ["", "万", "亿"]
            num = round(num, 2)
            integer_part = int(num)
            decimal_part = int(round((num - integer_part) * 100))

            int_str = ""
            if integer_part == 0:
                int_str = "零"
            else:
                groups = []
                n = integer_part
                while n > 0:
                    groups.append(n % 10000)
                    n = n // 10000
                for i, group in enumerate(groups):
                    group_str = ""
                    g = group
                    zero_flag = False
                    for j in range(4):
                        digit = g % 10
                        if digit == 0:
                            if zero_flag:
                                group_str = "零" + group_str
                                zero_flag = False
                        else:
                            group_str = cap[digit] + unit[j] + group_str
                            zero_flag = True
                        g = g // 10
                    if group == 0:
                        if i < len(groups) - 1 and int_str and not int_str.startswith("零"):
                            int_str = "零" + int_str
                    else:
                        int_str = group_str + big_unit[i] + int_str
                    while "零零" in int_str:
                        int_str = int_str.replace("零零", "零")
                    if int_str.endswith("零"):
                        int_str = int_str[:-1]

            jiao = decimal_part // 10
            fen = decimal_part % 10
            dec_str = ""
            if jiao == 0 and fen == 0:
                dec_str = "整"
            else:
                if jiao > 0:
                    dec_str += cap[jiao] + "角"
                elif integer_part > 0:
                    dec_str += "零"
                if fen > 0:
                    dec_str += cap[fen] + "分"

            return f"人民币{int_str}元{dec_str}"

        # ========== 生成电子订单PDF ==========
        def generate_pdf_by_template(order_no, items, full_addr, cust_name, cust_phone, send_date, order_date,
                                     payment_dict, card_holder_text="", card_no_text="", remark_text="",
                                     photo_files=None):
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib import colors
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import tempfile
            import xml.sax.saxutils as saxutils
            import os

            def safe_para(text):
                if not isinstance(text, str):
                    text = str(text)
                text = text.replace("<br/>", "\x00BR\x00")
                text = saxutils.escape(text)
                text = text.replace("\x00BR\x00", "<br/>")
                return text

            font_normal = "Helvetica"
            font_bold = "Helvetica-Bold"
            font_path = get_asset_path("simhei.ttf")
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont("Simhei", font_path))
                    font_normal = "Simhei"
                    font_bold = "Simhei"
                except Exception:
                    font_normal = None
            if font_normal is None or font_normal == "Helvetica":
                try:
                    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                    font_normal = "STSong-Light"
                    font_bold = "STSong-Light"
                except Exception:
                    font_normal = "Helvetica"
                    font_bold = "Helvetica-Bold"

            company_title_style = ParagraphStyle("company", fontName=font_bold, fontSize=16, leading=22, alignment=1)
            order_title_style = ParagraphStyle("order_title", fontName=font_bold, fontSize=14, leading=18, alignment=1)
            label_style = ParagraphStyle("label", fontName=font_normal, fontSize=10, leading=14, alignment=2)
            content_style = ParagraphStyle("content", fontName=font_normal, fontSize=10, leading=14, alignment=0)
            table_head_style = ParagraphStyle("th", fontName=font_bold, fontSize=9, leading=12, alignment=1)
            table_content_style = ParagraphStyle("td", fontName=font_normal, fontSize=9, leading=12, alignment=1)
            tip_text_style = ParagraphStyle("tip_text", fontName=font_normal, fontSize=9, leading=14, alignment=0)
            vertical_tip_style = ParagraphStyle("vtip", fontName=font_normal, fontSize=11, leading=20, alignment=1)
            sign_style = ParagraphStyle("sign", fontName=font_normal, fontSize=10, leading=14, alignment=0)
            bill_copy_style = ParagraphStyle("bill_copy", fontName=font_normal, fontSize=9, leading=12, alignment=0)
            page_no_style = ParagraphStyle("page_no", fontName=font_normal, fontSize=9, leading=12, alignment=1)

            print_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

            COMPANY_NAME = safe_para("贵州玖诚电器有限责任公司（松桃天猫优品东晟府店）")
            ORDER_TITLE = safe_para("销售订单")
            STORE_ADDR = safe_para("贵州省松桃苗族自治县蓼皋街道东晟府一、二号楼12-15门面")
            STORE_PHONE = safe_para("13096861211/13096863533")
            PAYEE_NAME = safe_para("成雯")
            BILL_COPY_1 = safe_para(f"电子单时间戳：{print_time}")
            BILL_COPY_2 = safe_para("电子订单请妥善保存，修改无效")

            has_duct = any("风管机" in it.get("spec", "") or "分管机" in it.get("spec", "") for it in items)
            if has_duct:
                duct_item = next(
                    (it for it in items if "风管机" in it.get("spec", "") or "分管机" in it.get("spec", "")), None)
                tip_content = duct_item.get("sale_remark", "") if duct_item else ""
            else:
                tip_content = """1.请确认以上资料正确无误，收货时核对相应物品及配件外观完好无损，配件齐全。
                2.所购新机在7天内若有质量问题，经厂家售后鉴定后包换新机（请确保原包装箱/盒、保修卡等配件完好无损），若机身或机壳刮花损坏、影响二次销售时，无法支持换机，只做维修处理
                3.请按照厂家说明书规范使用，机器在质保期内若有质量问题，经厂家售后鉴定后免费维修，人为损坏（如入液、受潮、私自拆装等）均不在免费维修范围内。
                4.本单据可作为保修凭证，请妥善保管，如需售后，请出示此单。"""

            col_widths = [32, 40, 40, 130, 85, 28, 28, 43, 37, 35, 35, 35, 55, 60]
            total_cols = 14

            page_size = 1 if has_duct else 5
            total_order_pages = max(1, (len(items) + page_size - 1) // page_size)
            page_items_list = [items[i:i + page_size] for i in range(0, len(items), page_size)]

            if photo_files is None:
                photo_files = []
            photo_count = len(photo_files)
            photos_per_page = 8
            photo_pages = (photo_count + photos_per_page - 1) // photos_per_page
            total_pages = total_order_pages + photo_pages

            pay_text = safe_para("、".join([f"{k}{v:.2f}元" for k, v in payment_dict.items()]))
            card_holder_text = safe_para(card_holder_text)
            card_no_text = safe_para(card_no_text)
            remark_text = safe_para(remark_text)
            handler_name = safe_para(current_user.get("real_name", "系统管理员"))

            send_date_str = send_date.isoformat() if hasattr(send_date, 'isoformat') else str(send_date)
            order_date_str = order_date.isoformat() if hasattr(order_date, 'isoformat') else str(order_date)
            today_str = date.today().isoformat()

            pdf_dir = tempfile.gettempdir()
            pdf_path = os.path.join(pdf_dir, f"电子订单_{order_no}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=landscape(A4),
                                    topMargin=15, bottomMargin=12, leftMargin=12, rightMargin=12)
            story = []

            # 构建订单页
            for page_idx, page_items in enumerate(page_items_list, 1):
                title_data = [
                    [Paragraph(COMPANY_NAME, company_title_style)],
                    [Paragraph(ORDER_TITLE, order_title_style)]
                ]
                title_table = Table(title_data, colWidths=[sum(col_widths)], rowHeights=[26, 22])
                title_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]))
                story.append(title_table)
                story.append(Spacer(1, 2))

                info_rows = []
                info_rows.append([
                    Paragraph(safe_para("下单日期："), label_style), "",
                    Paragraph(safe_para(order_date_str), content_style), "", "", "", "", "", "", "", "", "", "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("门店地址："), label_style), "",
                    Paragraph(STORE_ADDR, content_style), "", "", "", "", "",
                    Paragraph(safe_para("门店电话："), label_style), "", "",
                    Paragraph(STORE_PHONE, content_style), "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("订 单 号："), label_style), "",
                    Paragraph(safe_para(order_no), content_style), "",
                    Paragraph(safe_para("销售类型："), label_style), "",
                    Paragraph(safe_para("标准销售"), content_style), "",
                    Paragraph(safe_para("拟发货日期："), label_style), "", "",
                    Paragraph(safe_para(send_date_str), content_style), "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("客      户："), label_style), "",
                    Paragraph(safe_para(cust_name), content_style), "",
                    Paragraph(safe_para("客户电话："), label_style), "",
                    Paragraph(safe_para(cust_phone), content_style), "",
                    Paragraph(safe_para("收货人/电话："), label_style), "", "",
                    Paragraph(safe_para(f"{cust_name} {cust_phone}"), content_style), "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("送货地址："), label_style), "",
                    Paragraph(safe_para(full_addr), content_style), "", "", "", "",
                    Paragraph(safe_para("工会卡持卡人："), label_style), "", "",
                    Paragraph(card_holder_text, content_style), "", "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("付款方式："), label_style), "",
                    Paragraph(pay_text, content_style), "", "", "",
                    Paragraph(safe_para("工会卡卡号："), label_style), "", "",
                    Paragraph(card_no_text, content_style), "", "", "", ""
                ])
                info_rows.append([
                    Paragraph(safe_para("备    注："), label_style), "",
                    Paragraph(remark_text, content_style), "", "", "", "", "", "", "", "", "", "", ""
                ])

                info_table = Table(info_rows, colWidths=col_widths, rowHeights=[20, 20, 20, 20, 20, 20, 20])
                info_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)), ("SPAN", (0, 2), (1, 2)),
                    ("SPAN", (0, 3), (1, 3)), ("SPAN", (0, 4), (1, 4)), ("SPAN", (0, 5), (1, 5)),
                    ("SPAN", (0, 6), (1, 6)),
                    ("ALIGN", (0, 0), (1, -1), "RIGHT"),
                    ("SPAN", (2, 0), (3, 0)), ("ALIGN", (2, 0), (3, 0), "LEFT"),
                    ("SPAN", (2, 1), (7, 1)), ("ALIGN", (2, 1), (7, 1), "LEFT"),
                    ("SPAN", (8, 1), (10, 1)), ("ALIGN", (8, 1), (10, 1), "RIGHT"),
                    ("SPAN", (11, 1), (13, 1)), ("ALIGN", (11, 1), (13, 1), "LEFT"),
                    ("SPAN", (2, 2), (3, 2)), ("ALIGN", (2, 2), (3, 2), "LEFT"),
                    ("SPAN", (4, 2), (5, 2)), ("ALIGN", (4, 2), (5, 2), "RIGHT"),
                    ("SPAN", (6, 2), (7, 2)), ("ALIGN", (6, 2), (7, 2), "LEFT"),
                    ("SPAN", (8, 2), (10, 2)), ("ALIGN", (8, 2), (10, 2), "RIGHT"),
                    ("SPAN", (11, 2), (13, 2)), ("ALIGN", (11, 2), (13, 2), "LEFT"),
                    ("SPAN", (2, 3), (3, 3)), ("ALIGN", (2, 3), (3, 3), "LEFT"),
                    ("SPAN", (4, 3), (5, 3)), ("ALIGN", (4, 3), (5, 3), "RIGHT"),
                    ("SPAN", (6, 3), (7, 3)), ("ALIGN", (6, 3), (7, 3), "LEFT"),
                    ("SPAN", (8, 3), (10, 3)), ("ALIGN", (8, 3), (10, 3), "RIGHT"),
                    ("SPAN", (11, 3), (13, 3)), ("ALIGN", (11, 3), (13, 3), "LEFT"),
                    ("SPAN", (2, 4), (6, 4)), ("ALIGN", (2, 4), (6, 4), "LEFT"),
                    ("SPAN", (7, 4), (9, 4)), ("ALIGN", (7, 4), (9, 4), "RIGHT"),
                    ("SPAN", (10, 4), (13, 4)), ("ALIGN", (10, 4), (13, 4), "LEFT"),
                    ("SPAN", (2, 5), (5, 5)), ("ALIGN", (2, 5), (5, 5), "LEFT"),
                    ("SPAN", (6, 5), (8, 5)), ("ALIGN", (6, 5), (8, 5), "RIGHT"),
                    ("SPAN", (9, 5), (13, 5)), ("ALIGN", (9, 5), (13, 5), "LEFT"),
                    ("SPAN", (2, 6), (13, 6)), ("ALIGN", (2, 6), (13, 6), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]))
                story.append(info_table)
                story.append(Spacer(1, 2))

                table_data = []
                headers = ["序号", "品牌", "大类", "型号", "规格", "单位", "数量", "单价",
                           "旧机<br/>补贴", "工会<br/>补贴", "门店<br/>优惠", "国家<br/>补贴", "金额<br/>小计", "备注"]
                table_data.append([Paragraph(safe_para(h), table_head_style) for h in headers])
                for i, item in enumerate(page_items):
                    remark_display = "见温馨提示" if has_duct else item.get("sale_remark", "")
                    row = [
                        safe_para(str(i + 1)),
                        safe_para(item.get("factory", "")),
                        safe_para(item.get("category", "")),
                        safe_para(item.get("model", "")),
                        safe_para(item.get("spec", "")),
                        safe_para(item.get("piece", "")),
                        safe_para(str(item["qty"])),
                        safe_para(f"{item['price']:.2f}"),
                        safe_para(f"{item['old_discount']:.2f}"),
                        safe_para(f"{item['union_subsidy']:.0f}%"),
                        safe_para(f"{item['store_discount']:.2f}"),
                        safe_para(f"{item['gov_subsidy']:.0f}%"),
                        safe_para(f"{item['total']:.2f}"),
                        safe_para(remark_display),
                    ]
                    table_data.append([Paragraph(cell, table_content_style) for cell in row])
                for _ in range(page_size - len(page_items)):
                    table_data.append([""] * total_cols)

                page_total_amt = round(sum(it["total"] for it in page_items), 2)
                page_total_amt_upper = num2rmb(page_total_amt)
                total_row = [
                    Paragraph(safe_para("金额合计（大写）："), label_style), "", "",
                    Paragraph(safe_para(page_total_amt_upper), content_style), "", "", "",
                    Paragraph(safe_para("（小写）"), label_style), "",
                    Paragraph(safe_para(f"rmb {page_total_amt:.2f}元"), content_style), "", "", "", ""
                ]
                table_data.append(total_row)

                goods_table = Table(table_data, colWidths=col_widths)
                goods_style = [
                    ("FONTNAME", (0, 0), (-1, -1), font_normal),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("SPAN", (0, -1), (2, -1)), ("ALIGN", (0, -1), (2, -1), "RIGHT"),
                    ("SPAN", (3, -1), (6, -1)), ("ALIGN", (3, -1), (6, -1), "LEFT"),
                    ("SPAN", (7, -1), (8, -1)), ("ALIGN", (7, -1), (8, -1), "CENTER"),
                    ("SPAN", (9, -1), (13, -1)), ("ALIGN", (9, -1), (13, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
                goods_table.setStyle(TableStyle(goods_style))
                story.append(goods_table)

                # 温馨提示
                tip_html = tip_content.replace("\n", "<br/>")
                tip_row = [
                    Paragraph(safe_para("温<br/>馨<br/>提<br/>示"), vertical_tip_style),
                    Paragraph(safe_para(tip_html), tip_text_style),
                    "", "", "", "", "", "", "", "", "", "", "", ""
                ]
                tip_table = Table([tip_row], colWidths=col_widths, rowHeights=[90])
                tip_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("SPAN", (1, 0), (13, 0)),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("LEFTPADDING", (0, 0), (0, 0), 4),
                    ("RIGHTPADDING", (0, 0), (0, 0), 4),
                    ("LEFTPADDING", (1, 0), (-1, 0), 8),
                    ("RIGHTPADDING", (1, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(tip_table)
                story.append(Spacer(1, 4))

                sign_row = [
                    Paragraph(safe_para("收款单位（公章）："), sign_style), "", "", "",
                    Paragraph(safe_para(f"收款人：{PAYEE_NAME}"), sign_style), "", "", "", "",
                    Paragraph(safe_para(f"经手人：{handler_name}"), sign_style), "", "", "", ""
                ]
                sign_table = Table([sign_row], colWidths=col_widths, rowHeights=[22])
                sign_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, 0), (3, 0)), ("SPAN", (4, 0), (8, 0)),
                    ("SPAN", (9, 0), (13, 0)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                story.append(sign_table)
                story.append(Spacer(1, 3))

                copy_row = [
                    Paragraph(BILL_COPY_1, bill_copy_style), "", "", "", "", "",
                    Paragraph(BILL_COPY_2, bill_copy_style), "", "", "", "", "", "", ""
                ]
                copy_table = Table([copy_row], colWidths=col_widths, rowHeights=[18])
                copy_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, 0), (5, 0)), ("ALIGN", (0, 0), (5, 0), "LEFT"),
                    ("SPAN", (6, 0), (13, 0)), ("ALIGN", (6, 0), (13, 0), "RIGHT"),
                ]))
                story.append(copy_table)
                story.append(Spacer(1, 2))

                page_no_text = safe_para(f"第{page_idx}页/共{total_pages}页")
                page_no_table = Table([[Paragraph(page_no_text, page_no_style)]], colWidths=[sum(col_widths)],
                                      rowHeights=[16])
                page_no_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(page_no_table)

                if page_idx < total_order_pages:
                    story.append(PageBreak())

            # 照片页
            page_height = landscape(A4)[1]  # 595.27
            top_margin = 25
            bottom_margin = 25
            footer_height = 25
            available_height = page_height - top_margin - bottom_margin - footer_height - 20
            photo_row_height = available_height / 2

            for photo_page_idx in range(photo_pages):
                current_page_num = total_order_pages + photo_page_idx + 1
                start_idx = photo_page_idx * photos_per_page
                end_idx = min(start_idx + photos_per_page, photo_count)
                page_photos = photo_files[start_idx:end_idx]

                rows = []
                for r in range(2):
                    row_imgs = []
                    for c in range(4):
                        img_index = r * 4 + c
                        if img_index < len(page_photos):
                            img_path = page_photos[img_index]
                            img = Image(img_path, width=sum(col_widths) / 4, height=photo_row_height)
                            row_imgs.append(img)
                        else:
                            row_imgs.append("")
                    rows.append(row_imgs)

                photo_table = Table(rows, colWidths=[sum(col_widths) / 4] * 4,
                                    rowHeights=[photo_row_height, photo_row_height])
                photo_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(photo_table)

                page_no_text = safe_para(f"第{current_page_num}页/共{total_pages}页")
                page_no_table = Table([[Paragraph(page_no_text, page_no_style)]], colWidths=[sum(col_widths)],
                                      rowHeights=[16])
                page_no_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(page_no_table)

                if photo_page_idx < photo_pages - 1:
                    story.append(PageBreak())

            seal_path = get_asset_path("icon.png")

            def add_seal(canvas, doc):
                if os.path.exists(seal_path):
                    try:
                        canvas.saveState()
                        canvas.drawImage(seal_path, 72, 90, width=75, height=75, mask='auto')
                        canvas.restoreState()
                    except Exception:
                        pass

            try:
                doc.build(story, onFirstPage=add_seal, onLaterPages=add_seal)
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise
            return pdf_path

        # ========== 加载照片数据 ==========
        def load_photos_from_db(items):
            photo_files = []
            try:
                out_nos = [it["out_order_no"] for it in items if it.get("out_order_no")]
                if not out_nos:
                    return photo_files
                conn = get_db_conn()
                if not conn:
                    return photo_files
                cur = conn.cursor()
                format_strings = ','.join(['%s'] * len(out_nos))
                cur.execute(f"SELECT file_data FROM erp_files WHERE biz_no IN ({format_strings})", tuple(out_nos))
                photo_datas = [row[0] for row in cur.fetchall()]
                conn.close()
                for data in photo_datas:
                    try:
                        from PIL import Image as PILImage
                        import io
                        img = PILImage.open(io.BytesIO(data))
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                        img.save(tmp.name, "PNG")
                        tmp.close()
                        photo_files.append(tmp.name)
                    except Exception:
                        continue
            except Exception as ex:
                print(f"加载照片失败: {ex}")
            return photo_files

        # ========== 生成电子订单入口 ==========
        def generate_electronic_order_for_query(order_no):
            conn = get_db_conn()
            if not conn:
                show_alert(page, "错误", "数据库连接失败")
                return
            cur = conn.cursor()
            try:
                cur.execute("""
                    SELECT cust_name, phone, receiver_phone, card_holder, card_no, full_addr, remark, send_date, order_date, payment_method
                    FROM sale_main WHERE order_no=%s
                """, (order_no,))
                main_row = cur.fetchone()
                if not main_row:
                    show_alert(page, "提示", "未找到该订单")
                    return
                cust_name, phone, receiver_phone, card_holder, card_no, full_addr, remark, send_date, order_date, payment_method = main_row
                try:
                    payment_dict = json.loads(payment_method) if payment_method else {}
                except:
                    payment_dict = {"云闪付": 0}

                cur.execute("""
                    SELECT factory, category, model, spec, piece, qty, price, old_discount, union_subsidy,
                           gov_subsidy, store_discount, total, need_install, sale_remark, out_order_no
                    FROM sale_items WHERE order_no=%s ORDER BY id
                """, (order_no,))
                item_rows = cur.fetchall()
                if not item_rows:
                    show_alert(page, "提示", "该订单无商品明细")
                    return
                items = []
                for row in item_rows:
                    factory, category, model, spec, piece, qty, price, old_discount, union_subsidy, gov_subsidy, store_discount, total, need_install, sale_remark, out_no = row
                    items.append({
                        "factory": factory,
                        "category": category,
                        "model": model,
                        "spec": spec,
                        "piece": piece,
                        "qty": qty,
                        "price": float(price) if price else 0,
                        "old_discount": float(old_discount) if old_discount else 0,
                        "union_subsidy": float(union_subsidy) * 100 if union_subsidy and union_subsidy <= 1 else float(
                            union_subsidy) if union_subsidy else 0,
                        "gov_subsidy": float(gov_subsidy) * 100 if gov_subsidy and gov_subsidy <= 1 else float(
                            gov_subsidy) if gov_subsidy else 0,
                        "store_discount": float(store_discount) if store_discount else 0,
                        "total": float(total) if total else 0,
                        "need_install": bool(need_install),
                        "sale_remark": sale_remark or "",
                        "out_order_no": out_no or "",
                    })
                send_dt = send_date.date() if isinstance(send_date, datetime) else send_date
                order_dt = order_date.date() if isinstance(order_date, datetime) else order_date
            except Exception as ex:
                conn.close()
                show_alert(page, "错误", f"查询订单失败: {ex}")
                return
            finally:
                conn.close()

            # 询问是否导出照片
            def on_confirm_export_photos(e):
                page.pop_dialog()

                async def _export_with_photos():
                    await show_upload_loading_async(page, "加载照片数据中，请稍后……")
                    try:
                        photo_files = await asyncio.to_thread(load_photos_from_db, items)
                        hide_upload_loading(page)  # 照片加载完成，先关闭动画
                        # 生成PDF（可能耗时，但不再显示加载动画）
                        pdf_path = await asyncio.to_thread(
                            generate_pdf_by_template,
                            order_no, items, full_addr, cust_name, phone, send_dt, order_dt, payment_dict,
                            card_holder or "", card_no or "", remark or "", photo_files
                        )
                        show_pdf_preview(pdf_path, order_no)
                    except Exception as ex:
                        traceback.print_exc()
                        show_alert(page, "错误", f"生成电子订单失败：{str(ex)}")
                    finally:
                        # 确保动画关闭，如果之前没关闭的话
                        hide_upload_loading(page)

                page.run_task(_export_with_photos)

            def on_skip_photos(e):
                page.pop_dialog()

                async def _generate_without_photos():
                    try:
                        pdf_path = await asyncio.to_thread(
                            generate_pdf_by_template,
                            order_no, items, full_addr, cust_name, phone, send_dt, order_dt, payment_dict,
                            card_holder or "", card_no or "", remark or "", []
                        )
                        show_pdf_preview(pdf_path, order_no)
                    except Exception as ex:
                        traceback.print_exc()
                        show_alert(page, "错误", f"生成电子订单失败：{str(ex)}")

                page.run_task(_generate_without_photos)

            ask_dialog = ft.AlertDialog(
                title=ft.Text("导出照片"),
                content=ft.Text("是否同时导出数据库中的照片？"),
                actions=[
                    ft.TextButton("不导出", on_click=on_skip_photos),
                    ft.Button("导出照片", on_click=on_confirm_export_photos),
                ],
                modal=True,
            )
            page.show_dialog(ask_dialog)

        # ========== PDF预览与分享 ==========
        def show_pdf_preview(pdf_path, order_no):
            share = ft.Share()

            async def share_pdf(e):
                try:
                    share = ft.Share()
                    if page.web:
                        # Web 平台不支持路径分享，改用字节分享
                        with open(pdf_path, "rb") as f:
                            file_bytes = f.read()
                        share_file = ft.ShareFile.from_bytes(
                            file_bytes,
                            mime_type="application/pdf",
                            name=f"电子订单_{order_no}.pdf",
                        )
                    else:
                        share_file = ft.ShareFile.from_path(pdf_path)

                    result = await share.share_files(
                        [share_file],
                        text="电子订单",
                        title="分享电子订单",
                    )
                    show_alert(page, "提示", f"分享状态：{result.status}")
                except Exception as ex:
                    show_alert(page, "错误", f"分享失败: {str(ex)[:50]}")

            def save_pdf(e):
                try:
                    page.pop_dialog()
                    page.update()

                    async def do_save():
                        try:
                            path = await ft.FilePicker().save_file(
                                dialog_title="保存电子订单",
                                file_name=f"电子订单_{order_no}.pdf",
                                allowed_extensions=["pdf"],
                                src_bytes=open(pdf_path, "rb").read()
                            )
                            if path:
                                show_alert(page, "成功", "PDF已保存")
                        except Exception as ex:
                            show_alert(page, "错误", f"保存失败: {str(ex)[:50]}")

                    page.run_task(do_save)
                except Exception as ex:
                    show_alert(page, "错误", f"操作异常: {str(ex)[:50]}")

            dlg = ft.AlertDialog(
                title=ft.Text("电子订单已生成"),
                content=ft.Column([
                    ft.Text(f"订单文件：电子订单_{order_no}.pdf", size=14),
                    ft.Text("可分享到微信、钉钉，或保存到本地", size=12, color=ft.Colors.GREY),
                ], tight=True),
                actions=[
                    ft.Row([
                        ft.IconButton(ft.Icons.SHARE, tooltip="分享", on_click=share_pdf),
                        ft.IconButton(ft.Icons.SAVE, tooltip="保存", on_click=save_pdf),
                        ft.IconButton(ft.Icons.CLOSE, tooltip="关闭", on_click=lambda _: page.pop_dialog()),
                    ], spacing=20, alignment=ft.MainAxisAlignment.CENTER)
                ],
                modal=True,
            )
            page.show_dialog(dlg)

        # ========== 加载订单列表 ==========
        def load_orders(is_default=False):
            result_list.controls.clear()
            order_no = order_no_input.value.strip() if order_no_input.value else None
            cust_name = cust_name_input.value.strip() if cust_name_input.value else None
            phone = phone_input.value.strip() if phone_input.value else None
            address = address_input.value.strip() if address_input.value else None
            brand = brand_input.value.strip() if brand_input.value else None
            category = category_input.value.strip() if category_input.value else None
            model = model_input.value.strip() if model_input.value else None

            is_all = all_check.value
            only_full_out_no = single_no_check.value and not is_all
            only_empty_full_out_no = (not single_no_check.value) and (not is_all)
            only_gov_subsidy = gov_subsidy_check.value and not is_all
            only_no_gov_subsidy = (not gov_subsidy_check.value) and (not is_all)

            if is_default:
                date_val = datetime.now().strftime("%Y-%m-%d")
            else:
                date_val = selected_date_str

            conn = get_db_conn()
            if not conn:
                result_list.controls.append(ft.Text("数据库连接失败"))
                page.update()
                return
            cur = conn.cursor()
            sql = """
                SELECT DISTINCT 
                    m.order_no, m.order_date, m.cust_name, m.phone, m.full_addr,
                    GROUP_CONCAT(DISTINCT i.model SEPARATOR ', ') AS models,
                    IFNULL(SUM(i.total), 0) AS total_amount
                FROM sale_main m
                JOIN sale_items i ON m.order_no = i.order_no
                WHERE 1=1
            """
            params = []
            if order_no:
                sql += " AND m.order_no LIKE %s"
                params.append(f"%{order_no}%")
            if cust_name:
                sql += " AND m.cust_name LIKE %s"
                params.append(f"%{cust_name}%")
            if phone:
                sql += " AND m.phone LIKE %s"
                params.append(f"%{phone}%")
            if address:
                sql += " AND m.full_addr LIKE %s"
                params.append(f"%{address}%")
            if brand:
                sql += " AND i.factory LIKE %s"
                params.append(f"%{brand}%")
            if category:
                sql += " AND i.category LIKE %s"
                params.append(f"%{category}%")
            if model:
                sql += " AND i.model LIKE %s"
                params.append(f"%{model}%")

            if only_full_out_no:
                sql += " AND i.full_out_no IS NOT NULL AND i.full_out_no <> ''"
            elif only_empty_full_out_no:
                sql += " AND (i.full_out_no IS NULL OR i.full_out_no = '')"

            if only_gov_subsidy:
                sql += " AND i.gov_subsidy = %s"
                params.append(0.15)
            elif only_no_gov_subsidy:
                sql += " AND (i.gov_subsidy IS NULL OR i.gov_subsidy = 0)"

            if date_val:
                sql += " AND DATE(m.order_date) = %s"
                params.append(date_val)

            sql += " GROUP BY m.order_no, m.order_date, m.cust_name, m.phone, m.full_addr ORDER BY m.order_date DESC"

            try:
                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()
            except Exception as ex:
                conn.close()
                result_list.controls.append(ft.Text(f"查询失败: {ex}"))
                page.update()
                return

            if not rows:
                result_list.controls.append(ft.Text("未找到订单，请调整查询条件", size=16))
                page.update()
                return

            for row in rows:
                order_no, order_date, cust_name, phone, full_addr, models, total = row
                total = float(total) if total else 0.0
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(f"订单号: {order_no}", weight=ft.FontWeight.BOLD),
                                ft.Text(f"日期: {order_date}  客户: {cust_name}  电话: {phone}"),
                                ft.Text(f"地址: {full_addr}"),
                                ft.Text(f"商品: {models or '无商品'}"),
                                ft.Row(
                                    [
                                        ft.Text(f"总金额: ¥{total:.2f}", color=ft.Colors.GREEN,
                                                weight=ft.FontWeight.BOLD),
                                        ft.IconButton(
                                            ft.Icons.PRINT,
                                            tooltip="生成电子订单",
                                            icon_size=20,
                                            on_click=lambda e, o=order_no: generate_electronic_order_for_query(o),
                                        ),
                                        ft.IconButton(
                                            ft.Icons.EDIT,
                                            tooltip="修改订单",
                                            icon_size=20,
                                            on_click=lambda e, r=row: change_order(r),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                            ],
                            spacing=5,
                        ),
                        padding=15,
                        on_click=lambda e, o=order_no: show_order_detail(o),
                    ),
                    elevation=2,
                )
                result_list.controls.append(card)
            page.update()

        # ========== 重置查询 ==========
        def reset_search():
            nonlocal selected_date_str
            order_no_input.value = ""
            cust_name_input.value = ""
            phone_input.value = ""
            address_input.value = ""
            brand_input.value = ""
            category_input.value = ""
            model_input.value = ""
            selected_date_str = None
            date_display.value = "选择日期"
            date_display.color = ft.Colors.GREY_700
            date_display.update()

            all_check.value = True
            single_no_check.value = False
            gov_subsidy_check.value = False
            all_check.update()
            single_no_check.update()
            gov_subsidy_check.update()

            load_orders(is_default=True)

        # ========== 订单详情 ==========
        def show_order_detail(order_no):
            detail_dlg = ft.AlertDialog(
                title=ft.Text(f"订单详情 - {order_no}"),
                modal=True,
                content=ft.Column(
                    [
                        ft.Text("商品明细:", weight=ft.FontWeight.BOLD),
                        ft.Column(spacing=5),
                    ],
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    width=min(get_window_width(page) * 0.9 if get_window_width(page) else 400, 500),
                    height=min(get_window_width(page) * 0.9 if get_window_width(page) else 500, 600),
                ),
                actions=[
                    ft.TextButton("关闭", on_click=lambda e: page.pop_dialog())
                ],
            )

            def load_items():
                item_container = detail_dlg.content.controls[1]
                item_container.controls.clear()

                conn = get_db_conn()
                if not conn:
                    item_container.controls.append(ft.Text("数据库连接失败"))
                    page.update()
                    return

                cur = conn.cursor()
                cur.execute("""
                    SELECT out_order_no, model, qty, total, full_out_no, id, sale_remark
                    FROM sale_items
                    WHERE order_no = %s
                """, (order_no,))
                rows = cur.fetchall()
                conn.close()

                if not rows:
                    item_container.controls.append(ft.Text("无商品明细"))
                    page.update()
                    return

                for row in rows:
                    out_no, model, qty, total, full_out_no, item_id, sale_remark = row
                    total_val = float(total) if total else 0.0

                    item_card = ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(f"{model} x {qty}", weight=ft.FontWeight.BOLD),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    ft.Text(f"商品金额：¥{total_val:.2f}元", color=ft.Colors.GREEN),
                                    ft.Text(f"外部单号: {out_no}", size=12),
                                    ft.Text(
                                        f"完整外部单号: {full_out_no or '未录入'}",
                                        size=12,
                                        color=ft.Colors.BLUE if full_out_no else ft.Colors.GREY
                                    ),
                                    ft.Text(f"备注: {sale_remark}", size=12),
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                ft.Icons.CAMERA_ALT,
                                                icon_size=20,
                                                tooltip="拍摄支付凭证并识别二维码",
                                                on_click=lambda e, o=order_no, out=out_no,
                                                                item=item_id: capture_payment_voucher(o, out, item)
                                            ),
                                            ft.Text("拍摄凭证", size=12),
                                        ],
                                        alignment=ft.MainAxisAlignment.END,
                                    ),
                                ],
                                spacing=5,
                            ),
                            padding=10,
                        ),
                        elevation=1,
                    )
                    item_container.controls.append(item_card)

                page.update()

            def capture_payment_voucher(biz_order_no, out_order_no, item_id):
                page.pop_dialog()
                payment_voucher = f"db:payment_vouchers:{out_order_no}"

                def on_image_selected(path):
                    if not path:
                        page.show_dialog(detail_dlg)
                        return

                    print(f"[Voucher] Image selected: {path}")
                    code_list = barcode_image_decode(path)
                    scan_code = code_list[0].strip() if code_list else ""
                    print(f"[Voucher] Decoded code: {scan_code}")

                    preview_img = ft.Image(src=path, width=300, fit="contain")
                    scan_tip_text = ft.Text(
                        f"识别凭证号：{scan_code if scan_code else '未识别到二维码'}",
                        size=14
                    )

                    async def confirm_upload_async():
                        await show_upload_loading_async(page, "正在上传支付凭证...")
                        try:
                            def _background_work():
                                success, upload_result, err_msg = upload_image_to_db(
                                    file_path=path,
                                    file_type="payment_vouchers",
                                    biz_no=out_order_no,
                                    prefix="PV",
                                    delete_old=True
                                )
                                if success and scan_code:
                                    conn = get_db_conn()
                                    if conn:
                                        cur = conn.cursor()
                                        cur.execute(
                                            "UPDATE sale_items SET full_out_no = %s, payment_voucher = %s WHERE id = %s",
                                            (scan_code, payment_voucher, item_id)
                                        )
                                        conn.commit()
                                        conn.close()
                                return success, err_msg

                            success, err_msg = await asyncio.to_thread(_background_work)
                            if success:
                                hide_upload_loading(page)
                                page.pop_dialog()
                                await asyncio.to_thread(load_items)
                                page.show_dialog(detail_dlg)
                                await show_alert_async(page, "操作成功", "支付凭证已上传，单号已自动录入")
                            else:
                                hide_upload_loading(page)
                                await show_alert_async(page, "上传失败", f"图片存入数据库异常：{err_msg[:30]}")
                        except Exception as ex:
                            hide_upload_loading(page)
                            await show_alert_async(page, "错误", f"上传异常: {str(ex)[:30]}")

                    def btn_confirm_upload(ev):
                        page.run_task(confirm_upload_async)

                    def btn_retake(ev):
                        page.pop_dialog()
                        import threading
                        threading.Timer(0.1,
                                        lambda: capture_payment_voucher(biz_order_no, out_order_no, item_id)).start()

                    preview_dlg = ft.AlertDialog(
                        title=ft.Text("预览支付凭证", weight=ft.FontWeight.BOLD),
                        modal=True,
                        content=ft.Column([preview_img, scan_tip_text], tight=True),
                        actions=[
                            ft.TextButton("重新拍摄", on_click=btn_retake),
                            ft.Button(
                                "确认上传",
                                bgcolor=ft.Colors.BLUE,
                                color=ft.Colors.WHITE,
                                on_click=btn_confirm_upload
                            )
                        ]
                    )
                    page.show_dialog(preview_dlg)

                show_image_source_dialog(page, on_image_selected, title="扫码识别凭证")

            load_items()
            page.show_dialog(detail_dlg)
            page.update()

        # ========== 修改订单 ==========
        def change_order(row):
            order_no = row[0]
            items_container = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"修改-{order_no}"),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("商品明细", weight=ft.FontWeight.BOLD),
                            items_container,
                        ],
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=min(get_window_width(page) * 0.9 if get_window_width(page) else 800, 800),
                    height=400,
                ),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
                    ft.Button(
                        "保存修改",
                        bgcolor=ft.Colors.BLUE,
                        color=ft.Colors.WHITE,
                        on_click=lambda e: page.run_task(save_changes, dlg, items_data)
                    ),
                ],
            )

            items_data = []

            def load_items_for_edit():
                items_container.controls.clear()
                items_data.clear()

                conn = get_db_conn()
                if not conn:
                    items_container.controls.append(ft.Text("数据库连接失败"))
                    page.update()
                    return

                cur = conn.cursor()
                cur.execute("""
                    SELECT id, out_order_no, model, qty, price, old_discount, union_subsidy,
                           store_discount, gov_subsidy, sale_remark
                    FROM sale_items
                    WHERE order_no = %s
                    ORDER BY id
                """, (order_no,))
                rows = cur.fetchall()
                conn.close()

                if not rows:
                    items_container.controls.append(ft.Text("该订单无商品明细"))
                    page.update()
                    return

                for row_item in rows:
                    item_id, out_no, model, qty, price, old_discount, union_subsidy, store_discount, gov_subsidy, sale_remark = row_item

                    qty_val = qty if qty is not None else 1
                    price_val = float(price) if price else 0.0
                    old_discount_val = float(old_discount) if old_discount else 0.0
                    union_subsidy_val = float(union_subsidy) if union_subsidy else 0.0
                    store_discount_val = float(store_discount) if store_discount else 0.0
                    gov_subsidy_val = float(gov_subsidy) if gov_subsidy else 0.0
                    sale_remark_val = sale_remark or ""

                    if 0 < union_subsidy_val <= 1:
                        union_subsidy_val *= 100
                    if 0 < gov_subsidy_val <= 1:
                        gov_subsidy_val *= 100

                    qty_input = ft.TextField(label="数量", value=str(qty_val), width=75,
                                             text_align=ft.TextAlign.CENTER)
                    price_input = ft.TextField(label="价格", value=f"{price_val:.2f}", width=90)
                    old_discount_input = ft.TextField(label="旧机补贴", value=f"{old_discount_val:.2f}", width=90)
                    union_subsidy_input = ft.TextField(label="工会(%)", value=f"{union_subsidy_val:.2f}", width=75)
                    store_discount_input = ft.TextField(label="门店折扣", value=f"{store_discount_val:.2f}", width=90)
                    gov_subsidy_input = ft.TextField(label="国补(%)", value=f"{gov_subsidy_val:.2f}", width=75)
                    sale_remark_input = ft.TextField(label="商品备注", value=sale_remark_val, multiline=True,
                                                     min_lines=2, max_lines=4, width=185)

                    item_card = ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Column(
                                        [
                                            ft.Text(f"型号: {model}", weight=ft.FontWeight.BOLD),
                                            ft.Text(f"外部单号: {out_no or '无'}", size=12, color=ft.Colors.GREY),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    ft.Row([qty_input, price_input], spacing=10),
                                    ft.Row([old_discount_input, union_subsidy_input], spacing=10),
                                    ft.Row([store_discount_input, gov_subsidy_input], spacing=10),
                                    sale_remark_input,
                                ],
                                spacing=8,
                            ),
                            padding=10,
                        ),
                        elevation=1,
                    )
                    items_container.controls.append(item_card)

                    items_data.append({
                        "id": item_id,
                        "qty": qty_input,
                        "price": price_input,
                        "old_discount": old_discount_input,
                        "union_subsidy": union_subsidy_input,
                        "store_discount": store_discount_input,
                        "gov_subsidy": gov_subsidy_input,
                        "sale_remark": sale_remark_input,
                    })

                page.update()

            async def save_changes(dlg, items_data):
                conn = get_db_conn()
                if not conn:
                    await show_alert_async(page, "错误", "数据库连接失败")
                    return

                cur = conn.cursor()
                try:
                    for item in items_data:
                        item_id = item["id"]
                        try:
                            qty = int(item["qty"].value or 0)
                            price = float(item["price"].value or 0)
                            old_discount = float(item["old_discount"].value or 0)
                            union_input = float(item["union_subsidy"].value or 0)
                            store_discount = float(item["store_discount"].value or 0)
                            gov_input = float(item["gov_subsidy"].value or 0)
                            sale_remark = item["sale_remark"].value or ""
                        except ValueError:
                            await show_alert_async(page, "输入错误", "请输入有效数字")
                            return

                        if union_input > 1:
                            union_percent = union_input
                            union_decimal = union_input / 100
                        else:
                            union_percent = union_input * 100 if union_input > 0 else 0
                            union_decimal = union_input

                        if gov_input > 1:
                            gov_percent = gov_input
                            gov_decimal = gov_input / 100
                        else:
                            gov_percent = gov_input * 100 if gov_input > 0 else 0
                            gov_decimal = gov_input

                        after_old = price - old_discount
                        after_union = after_old * (1 - union_percent / 100)
                        after_store = after_union - store_discount

                        if gov_percent == 0:
                            final_unit = after_store
                        else:
                            if after_store <= 10000:
                                final_unit = math.ceil(after_store * (1 - gov_percent / 100) * 100) / 100
                            else:
                                final_unit = after_store - 1500

                        total = final_unit * qty
                        t_price = after_store

                        cur.execute("""
                            UPDATE sale_items
                            SET qty=%s, price=%s, old_discount=%s, union_subsidy=%s,
                                store_discount=%s, gov_subsidy=%s, sale_remark=%s,
                                total=%s, t_price=%s
                            WHERE id=%s
                        """, (qty, price, old_discount, union_decimal, store_discount,
                              gov_decimal, sale_remark, total, t_price, item_id))

                    conn.commit()

                    page.pop_dialog()
                    await show_alert_async(page, "操作成功", "订单商品修改已保存")
                    load_orders(is_default=False)
                except Exception as ex:
                    conn.rollback()
                    await show_alert_async(page, "保存失败", f"更新数据库异常：{ex}")
                finally:
                    conn.close()

            load_items_for_edit()
            page.show_dialog(dlg)
            page.update()

        def on_query_click(e):
            load_orders(is_default=False)

        action_row = ft.Row(
            [
                date_picker_btn,
                ft.Button("查询", on_click=on_query_click, width=btn_width + 10),
                ft.Button("重置", on_click=lambda e: reset_search(), width=btn_width + 10),
            ],
            spacing=10,
        )

        check_row = ft.Row(
            [all_check, single_no_check, gov_subsidy_check],
            spacing=20,
        )

        query_panel = ft.Column(
            [
                ft.Text("订单查询", size=20, weight=ft.FontWeight.BOLD),
                order_no_input,
                ft.Row([cust_name_input, phone_input], spacing=10),
                ft.Row([address_input, brand_input], spacing=10),
                ft.Row([category_input, model_input], spacing=10),
                check_row,
                action_row,
                ft.Divider(height=10),
                result_list,
            ],
            spacing=10,
        )
        main_content.controls.append(query_panel)
        load_orders(is_default=True)
        page.update()

    # ---------------------------- 入库管理 ----------------------------
    def show_inbound():
        nonlocal current_user
        main_content.controls.clear()
        input_height = 50
        input_width = get_field_width(page, ratio=1, subtract=40)
        title = ft.Text("商品入库", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.LEFT)

        inbound_type = ft.Container(
            content=ft.Dropdown(
                label="入库类型",
                options=[
                    ft.dropdown.Option("标准入库"),
                    ft.dropdown.Option("退货入库"),
                    ft.dropdown.Option("调拨入库")
                ],
                value="标准入库",
                width=input_width,
            ),
            height=input_height,
            width=input_width,
        )

        scan_btn = ft.IconButton(
            ft.Icons.CAMERA_ALT,
            icon_size=24,
            tooltip="扫码识别型号",
            on_click=lambda e: unified_barcode_scan(page, on_scan, title="扫码识别商品"),
            style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT),
            opacity=0.6,
        )
        model_input = ft.TextField(
            label="商品型号",
            hint_text="输入2字以上自动查询",
            width=input_width,
            height=input_height,
            suffix=scan_btn,
        )
        model_suggestions = ft.Column(spacing=0, visible=False)

        def load_model_suggestions(val):
            if len(val) < 2:
                model_suggestions.controls.clear()
                model_suggestions.visible = False
                model_suggestions.update()
                page.update()
                return
            conn = get_db_conn()
            if not conn:
                return
            cur = conn.cursor()
            cur.execute("SELECT model, factory, spec FROM base_product WHERE model LIKE %s LIMIT 10", (f"%{val}%",))
            rows = cur.fetchall()
            conn.close()
            model_suggestions.controls.clear()
            if not rows:
                model_suggestions.visible = False
                model_suggestions.update()
                page.update()
                return
            for row in rows:
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Text(f"{row[0]} | {row[1]} | {row[2]}", size=13),
                        padding=12,
                        on_click=lambda e, r=row: select_product(r)
                    ),
                    elevation=0,
                    margin=ft.Margin(0, 0, 0, 2),
                )
                model_suggestions.controls.append(card)
            model_suggestions.visible = True
            model_suggestions.update()
            page.update()

        def select_product(row):
            model_input.value = row[0]
            model_suggestions.controls.clear()
            model_suggestions.visible = False
            model_suggestions.update()
            page.update()

        model_input.on_change = lambda e: load_model_suggestions(e.control.value.strip())
        model_column = ft.Column(
            [
                model_input,
                model_suggestions,
            ],
            spacing=0,
            width=input_width,
        )

        def on_scan(code, prod=None):
            if prod:
                model_input.value = prod["model"]
                model_suggestions.controls.clear()
                model_suggestions.visible = False
                model_suggestions.update()
                page.update()
            else:
                prod = query_product_by_code(code)
                if prod:
                    model_input.value = prod["model"]
                    model_suggestions.controls.clear()
                    model_suggestions.visible = False
                    model_suggestions.update()
                    page.update()
                else:
                    def after_add(m):
                        model_input.value = m
                        model_suggestions.controls.clear()
                        model_suggestions.visible = False
                        model_suggestions.update()
                        page.update()
                    add_product_from_scan(page, code, after_add)

        qty = ft.TextField(label="入库数量", width=input_width, height=input_height)
        in_price = ft.TextField(label="入库价格", value="0", width=input_width, height=input_height)
        location = ft.TextField(label="库位", value="A-00-00",width=input_width, height=input_height)
        in_date = ft.TextField(label="入库日期", value=date.today().isoformat(), width=input_width, height=input_height)

        def save_inbound(e):
            print("=== 确认入库按钮被点击 ===")
            model_suggestions.controls.clear()
            model_suggestions.visible = False
            model_suggestions.update()
            page.update()

            if not isinstance(current_user, dict):
                show_alert(page, "错误", "用户信息异常，请重新登录")
                return
            m = model_input.value.strip()
            if not m:
                show_alert(page, "提示", "请输入商品型号")
                return
            try:
                qt = int(qty.value) if qty.value else 0
                if qt <= 0:
                    raise ValueError
            except ValueError:
                show_alert(page, "错误", "请输入有效的正整数")
                return
            try:
                price = float(in_price.value) if in_price.value else 0.0
                if price < 0:
                    raise ValueError
            except ValueError:
                show_alert(page, "错误", "请输入有效的数字（入库价格）")
                return

            conn = get_db_conn()
            if not conn:
                show_alert(page, "错误", "数据库连接失败，请检查配置")
                return
            prod = get_product_by_model(m)
            if not prod:
                conn.close()
                show_alert(page, "提示", f"型号 {m} 不存在，请先添加产品")
                return

            cur = conn.cursor()
            try:
                operator = current_user.get("real_name", "未知用户")
                cur.execute("""INSERT INTO stock_in 
                            (inbound_type, factory, category, model, code, spec, qty, in_price,
                             union_subsidy, gov_subsidy, old_discount, location, in_date, operator)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            (inbound_type.content.value, prod["factory"], prod["category"], m, prod["code"],
                             prod["spec"], qt, price, prod["union_subsidy"], prod["gov_subsidy"], prod["old_discount"],
                             location.value, in_date.value, operator))
                cur.execute("""INSERT INTO stock_now (factory, model, spec, qty, s_qty)
                            VALUES (%s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE qty = qty + %s, s_qty = s_qty + %s""",
                            (prod["factory"], m, prod["spec"], qt, qt, qt, qt))
                conn.commit()
                print(f"入库成功：{m} × {qt}，单价：{price}")

                def on_success(e):
                    model_input.value = ""
                    qty.value = ""
                    in_price.value = "0"
                    location.value = ""
                    in_date.value = date.today().isoformat()
                    model_suggestions.controls.clear()
                    model_suggestions.visible = False
                    model_suggestions.update()
                    page.update()
                show_alert(page, "成功", f"入库 {qt} 件成功", on_success)
            except Exception as ex:
                conn.rollback()
                print("入库异常:", ex)
                show_alert(page, "错误", f"入库失败: {ex}")
            finally:
                conn.close()

        save_btn = ft.Button(
            "确认入库",
            icon=ft.Icons.SAVE,
            on_click=save_inbound,
            bgcolor=ft.Colors.GREEN,
            color=ft.Colors.WHITE,
            width=input_width,
            height=input_height,
        )

        main_content.controls.append(
            ft.Column(
                [
                    title,
                    inbound_type,
                    model_column,
                    qty,
                    in_price,
                    location,
                    in_date,
                    save_btn,
                ],
                spacing=15,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
        page.update()

    # ---------------------------- 运输管理 ----------------------------

    def show_transport():
        main_content.controls.clear()
        w1 = get_field_width(page, ratio=2, subtract=60)
        w2 = get_field_width(page, ratio=3, subtract=80)

        status_dropdown = ft.Dropdown(
            label="订单状态",
            options=[
                ft.dropdown.Option("全部"),
                ft.dropdown.Option("待派单"),
                ft.dropdown.Option("待出库"),
                ft.dropdown.Option("已出库"),
                ft.dropdown.Option("待自提"),
                ft.dropdown.Option("已自提"),
                ft.dropdown.Option("已送货入户"),
            ],
            value="待出库",
            width=w1,
        )

        start_date = ft.TextField(label="起始日期", hint_text="YYYY-MM-DD", width=w2)
        end_date = ft.TextField(label="结束日期", hint_text="YYYY-MM-DD", width=w2)
        order_no_input = ft.TextField(label="订单号", width=w2)
        cust_name_input = ft.TextField(label="客户名称", width=w2)
        query_btn = ft.Button("查询", icon=ft.Icons.SEARCH)
        reset_btn = ft.Button("重置", icon=ft.Icons.REFRESH)
        trans_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

        # 全局默认送货人配置
        def get_default_delivers():
            """从 user 表查询 role 为 '配送员' 的 real_name，最多取两个"""
            try:
                conn = get_db_conn()
                if not conn:
                    return "", ""
                cur = conn.cursor()
                cur.execute("SELECT real_name FROM users WHERE role='配送员' ORDER BY id ASC LIMIT 2")
                rows = cur.fetchall()
                conn.close()
                if len(rows) >= 2:
                    return rows[0][0], rows[1][0]
                elif len(rows) == 1:
                    return rows[0][0], ""
                else:
                    return "", ""
            except Exception as e:
                print(f"获取默认送货人失败: {e}")
                return "", ""

        # 全局默认送货人配置
        DEFAULT_DELIVER1, DEFAULT_DELIVER2 = get_default_delivers()
        # 上传并发锁：防止重复点击上传
        upload_busy_lock = False

        # ============= 直接拨号、短信 =============
        def show_phone_dialog(phone_number: str):
            """弹出拨号/短信选择对话框"""
            clean_number = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

            async def make_call(e):
                dialog.open = False
                page.update()
                await ft.UrlLauncher().launch_url(f"tel:{clean_number}")

            async def send_sms(e):
                dialog.open = False
                page.update()
                await ft.UrlLauncher().launch_url(f"sms:{clean_number}")

            dialog = ft.AlertDialog(
                title=ft.Text("选择操作"),
                content=ft.Text(f"电话号码：{phone_number}"),
                actions=[
                    ft.TextButton("拨打电话", icon=ft.Icons.CALL, on_click=make_call),
                    ft.TextButton("发送短信", icon=ft.Icons.SMS, on_click=send_sms),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
        # ====================== 优化 show_snack 线程安全 ======================
        def show_snack(page: ft.Page, msg, bgcolor=ft.Colors.GREY_800):
            """线程安全的 SnackBar 显示，统一调度到主线程"""

            def _show():
                snack = ft.SnackBar(
                    ft.Text(msg),
                    bgcolor=bgcolor,
                    behavior=ft.SnackBarBehavior.FLOATING
                )
                page.overlay.append(snack)
                snack.open = True
                page.update()

            run_ui_task(page, _show)

        # 统一关闭当前所有弹窗（业务专用）
        def close_all_trans_dialogs():
            """异步安全关闭多层弹窗，避免阻塞UI"""

            async def _close_all():
                for _ in range(5):  # 最多关闭5层弹窗，防止死循环
                    try:
                        page.pop_dialog()
                        await asyncio.sleep(0.01)
                    except Exception:
                        break

            page.run_task(_close_all)

        # ------------------------------------------------------------

        def get_home_photo_biz_info(order_no, out_order_no):
            try:
                out_int = int(out_order_no) if out_order_no else 0
            except (ValueError, TypeError):
                out_int = 0
            if out_int <= 20:
                biz_no = f"{order_no}_{out_int}"
                prefix = "ORD"
            else:
                biz_no = str(out_order_no)
                prefix = "HM"
            return biz_no, prefix

        def format_date(val):
            if not val:
                return ""
            if isinstance(val, datetime):
                return val.strftime("%Y-%m-%d")
            s = str(val)
            if ' ' in s:
                return s.split()[0]
            return s

        def change_status(row):
            order_no = row[2]
            out_order_no = row[3]
            current_st = row[12]
            current_send_date = row[13] or ""
            current_trans_date = row[14] or ""

            status_dropdown_edit = ft.Dropdown(
                label="新状态",
                options=[
                    ft.dropdown.Option("待派单"),
                    ft.dropdown.Option("待出库"),
                    ft.dropdown.Option("已出库"),
                    ft.dropdown.Option("待自提"),
                    ft.dropdown.Option("已自提"),
                    ft.dropdown.Option("已送货入户"),
                ],
                value=current_st,
                width=200,
            )
            send_checkbox = ft.Checkbox(label="", value=False)
            send_textfield = ft.TextField(
                label="计划送货日期",
                value=format_date(current_send_date),
                width=150,
                disabled=True,
            )
            trans_checkbox = ft.Checkbox(label="", value=False)
            trans_textfield = ft.TextField(
                label="实际送货日期",
                value=format_date(current_trans_date),
                width=150,
                disabled=True,
            )

            def on_send_checkbox_change(e):
                send_textfield.disabled = not send_checkbox.value
                page.update()

            def on_trans_checkbox_change(e):
                trans_textfield.disabled = not trans_checkbox.value
                page.update()

            send_checkbox.on_change = on_send_checkbox_change
            trans_checkbox.on_change = on_trans_checkbox_change

            def save_status_change(e):
                new_status = status_dropdown_edit.value
                updates = ["status=%s"]
                params = [new_status]
                if send_checkbox.value and send_textfield.value.strip():
                    updates.append("send_date=%s")
                    params.append(send_textfield.value.strip())
                if trans_checkbox.value and trans_textfield.value.strip():
                    updates.append("trans_date=%s")
                    params.append(trans_textfield.value.strip())
                params.extend([order_no, out_order_no])

                conn = get_db_conn()
                if not conn:
                    show_alert(page, "错误", "数据库连接失败")
                    return
                cur = conn.cursor()
                try:
                    sql = f"UPDATE transport SET {', '.join(updates)} WHERE order_no=%s AND out_order_no=%s"
                    cur.execute(sql, params)
                    conn.commit()
                    show_alert(page, "成功", "状态更新完成")
                    load_trans()
                except Exception as ex:
                    conn.rollback()
                    show_alert(page, "错误", f"更新失败：{str(ex)}")
                finally:
                    conn.close()

            dlg = ft.AlertDialog(
                title=ft.Text("修改状态&日期"),
                content=ft.Column(
                    [
                        ft.Text(f"当前状态：{current_st}"),
                        status_dropdown_edit,
                        ft.Row([send_checkbox, send_textfield]),
                        ft.Row([trans_checkbox, trans_textfield]),
                    ],
                    spacing=10,
                    tight=True,
                ),
                actions=[
                    ft.TextButton("保存", on_click=save_status_change),
                    ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
                ],
                modal=True,
            )
            page.show_dialog(dlg)
        def load_chinese_font(size: int = 28):
                """多端兼容加载中文字体，解决PIL水印中文乱码"""
                try:
                    font_path = get_asset_path("SIMLI.TTF")
                    if os.path.exists(font_path):
                        return ImageFont.truetype(font_path, size)
                except Exception:
                    pass

                android_font_paths = [
                    "/system/fonts/NotoSansCJK-Regular.ttc",
                    "/system/fonts/DroidSansFallback.ttf",
                    "/system/fonts/HarmonyOS_Sans_SC_Regular.ttf",
                    "/system/fonts/Miui-Regular.ttf",
                    "/system/fonts/SourceHanSansCN-Regular.otf",
                ]
                for path in android_font_paths:
                    try:
                        if os.path.exists(path):
                            return ImageFont.truetype(path, size)
                    except Exception:
                        continue

                try:
                    if os.name == "nt":
                        return ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", size)
                    elif sys.platform == "darwin":
                        return ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", size)
                except Exception:
                    pass

                print("[Font] 所有中文字体均加载失败，水印可能显示乱码")
                return ImageFont.load_default(size)
        def open_operation_dialog(row):
            # ========== 优化：重新查询最新数据，确保弹窗显示实时信息 ==========
            try:
                conn = get_db_conn()
                if conn:
                    cur = conn.cursor()
                    cur.execute(
                        """SELECT id, order_date, order_no, out_order_no, cust_name, phone, full_addr,
                                  factory, category, model, t_qty, trans_remark,
                                  status, send_date, trans_date,
                                  COALESCE(delivery01_name,''), COALESCE(delivery02_name,''),
                                  sn_code, sn_photo, home_photo
                           FROM transport WHERE order_no=%s AND out_order_no=%s""",
                        (row[2], row[3])
                    )
                    fresh_row = cur.fetchone()
                    if fresh_row:
                        row = fresh_row
                    conn.close()
            except Exception:
                pass

            trans_id, order_date, order_no, out_order_no, cust_name, phone, full_addr, factory, category, model, t_qty, trans_remark, status_val, send_date_val, trans_date_val, delivery01_name, delivery02_name, sn_code, sn_photo, home_photo = row

            current_order = {
                "trans_id": trans_id,
                "order_no": order_no,
                "out_order_no": out_order_no,
                "status": status_val,
                "sn_code": sn_code or "",
                "sn_photo": sn_photo,
                "home_photo": home_photo,
            }
            biz_no, prefix = get_home_photo_biz_info(order_no, out_order_no)

            sn_entry = ft.TextField(label="SN码", value=current_order["sn_code"], expand=True)
            trans_date_input = ft.TextField(label="实际送货日期", value=date.today().isoformat(), expand=True)
            delivery01 = ft.TextField(label="送  货  人", value=DEFAULT_DELIVER1, expand=True)
            delivery02 = ft.TextField(label="共同送货人", value=DEFAULT_DELIVER2, expand=True)
            need_delivery_cb = ft.Checkbox(label="送货", value=True)
            status_label = ft.Text(f"当前状态: {status_val}", weight=ft.FontWeight.BOLD)
            sn_photo_status = ft.Text("SN: 已上传" if sn_photo else "SN: 未上传",
                                      color=ft.Colors.GREEN if sn_photo else ft.Colors.GREY)
            home_photo_status = ft.Text("送货: 已上传" if home_photo else "送货: 未上传",
                                        color=ft.Colors.GREEN if home_photo else ft.Colors.GREY)

            def on_delivery_check_change(e):
                if need_delivery_cb.value:
                    delivery01.value = DEFAULT_DELIVER1
                    delivery02.value = DEFAULT_DELIVER2
                else:
                    delivery01.value = ""
                    delivery02.value = ""
                page.update()

            need_delivery_cb.on_change = on_delivery_check_change

            def do_confirm_out(e):
                if current_order["status"] not in ["待出库", "待派单"]:
                    show_alert(page, "提示", f"当前状态 {current_order['status']}，不能出库")
                    return
                sn_code_input = sn_entry.value.strip()
                trans_date = trans_date_input.value.strip()
                delivery01_name_val = delivery01.value.strip()
                delivery02_name_val = delivery02.value.strip()
                need_delivery = need_delivery_cb.value
                new_status = "已出库" if need_delivery else "待自提"
                sn_mark = f"db:sn_photos:{current_order['out_order_no']}"
                conn = get_db_conn()
                cur = conn.cursor()
                try:
                    cur.execute(
                        """UPDATE transport SET status=%s, trans_date=%s,
                           delivery01_name=%s, delivery02_name=%s, sn_photo=%s
                           WHERE order_no=%s AND out_order_no=%s""",
                        (new_status, trans_date,
                         delivery01_name_val, delivery02_name_val, sn_mark,
                         current_order["order_no"], current_order["out_order_no"])
                    )
                    conn.commit()

                    # ========== 新增：更新弹窗内的状态显示 ==========
                    current_order["status"] = new_status
                    status_label.value = f"当前状态: {new_status}"
                    page.update()

                    show_alert(page, "成功", f"订单 {current_order['order_no']} → {new_status}")
                    load_trans()
                except Exception as ex:
                    conn.rollback()
                    show_alert(page, "错误", str(ex))
                finally:
                    conn.close()

            def do_confirm_delivered(e):
                if need_delivery_cb.value:
                    if current_order["status"] not in ["已出库", "待自提"]:
                        show_alert(page, "提示", f"当前状态 {current_order['status']}，不能确认送达")
                        return
                new_status = "已送货入户" if current_order["status"] == "已出库" else "已自提"
                hm_mark = f"db:home_photos:{biz_no}"
                conn = get_db_conn()
                cur = conn.cursor()
                try:
                    cur.execute(
                        "UPDATE transport SET status=%s, trans_date=%s, home_photo=%s WHERE order_no=%s AND out_order_no=%s",
                        (new_status, date.today().isoformat(), hm_mark, current_order["order_no"],
                         current_order["out_order_no"])
                    )
                    conn.commit()

                    # ========== 新增：更新弹窗内的状态显示 ==========
                    current_order["status"] = new_status
                    status_label.value = f"当前状态: {new_status}"
                    page.update()

                    show_alert(page, "成功", f"订单 {current_order['order_no']} → {new_status}")
                    load_trans()
                except Exception as ex:
                    conn.rollback()
                    show_alert(page, "错误", str(ex))
                finally:
                    conn.close()

            def do_view_sn_photo(e):
                file_data = get_file_from_db("sn_photos", current_order["out_order_no"])
                if not file_data:
                    show_alert(page, "提示", "该订单暂无 SN 照片")
                    return
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(file_data)
                    tmp_path = tmp.name
                img_dlg = ft.AlertDialog(
                    title=ft.Text("SN照片预览"),
                    content=ft.Container(
                        content=ft.Image(
                            src=tmp_path,
                            fit="contain",
                            width=min(get_window_width(page) * 0.85, 600),
                            height=min(get_window_width(page) * 0.85, 800),
                        ),
                        width=min(get_window_width(page) * 0.85, 600),
                        height=min(get_window_width(page) * 0.85, 800),
                    ),
                    actions=[ft.TextButton("关闭", on_click=lambda _: page.pop_dialog())],
                    modal=True,
                )
                page.show_dialog(img_dlg)

            def do_view_home_photo(e):
                biz_no, prefix = get_home_photo_biz_info(order_no, out_order_no)
                file_data = get_file_from_db("home_photos", biz_no)
                if not file_data:
                    show_alert(page, "提示", "该订单暂无送货照片")
                    return

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(file_data)
                    tmp_path = tmp.name

                # 创建预览图片控件（供后续更新）
                img_control = ft.Image(
                    src=tmp_path,
                    fit="contain",
                    width=min(get_window_width(page) * 0.85, 600),
                    height=min(get_window_width(page) * 0.85, 800),
                )
                preview_container = ft.Container(
                    content=img_control,
                    width=min(get_window_width(page) * 0.85, 600),
                    height=min(get_window_width(page) * 0.85, 800),
                )

                # ---------- 下载照片 ----------
                async def do_download_home_photo(e):
                    try:
                        page.pop_dialog()
                    except Exception:
                        pass
                    page.update()
                    await asyncio.sleep(0.1)

                    try:
                        path = await ft.FilePicker().save_file(
                            dialog_title="保存送货照片",
                            file_name=f"送货照片_{biz_no}.jpg",
                            allowed_extensions=["jpg", "jpeg"],
                            src_bytes=file_data  # 关键：移动端必须传入字节数据
                        )
                        if path:
                            show_alert(page, "成功", "照片已保存")
                    except Exception as ex:
                        show_alert(page, "错误", f"下载失败: {str(ex)}")

                # ---------- 修改水印 ----------
                def do_edit_home_photo(e):
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    edit_time_input = ft.TextField(label="水印时间", value=now_str)
                    edit_order_input = ft.TextField(label="订单号", value=order_no)
                    edit_cust_input = ft.TextField(label="客户", value=cust_name)
                    edit_addr_input = ft.TextField(label="地址", value=full_addr)
                    edit_lng_input = ft.TextField(label="经度", value="获取失败")
                    edit_lat_input = ft.TextField(label="纬度", value="获取失败")

                    def get_location(e):
                        async def _task():
                            ok, lat, lng = await get_current_location(page)
                            if ok:
                                edit_lat_input.value = str(lat)
                                edit_lng_input.value = str(lng)
                                page.update()
                            else:
                                show_alert(page, "提示", "无法获取当前位置")

                        page.run_task(_task)

                    def save_edit(e):
                        custom_text = "\n".join([
                            edit_time_input.value.strip(),
                            f"订单号:{edit_order_input.value.strip()}",
                            f"客户:{edit_cust_input.value.strip()}",
                            f"地址:{edit_addr_input.value.strip()}",
                            f"经度:{edit_lng_input.value.strip()} 纬度:{edit_lat_input.value.strip()}"
                        ])
                        page.pop_dialog()  # 关闭修改水印弹窗

                        async def _task():
                            await show_upload_loading_async(page, "正在重新添加水印...")
                            try:
                                success, db_tag, err = await asyncio.to_thread(
                                    process_image,
                                    tmp_path,
                                    True,
                                    order_no,
                                    cust_name,
                                    full_addr,
                                    out_order_no,
                                    edit_lat_input.value.strip(),
                                    edit_lng_input.value.strip(),
                                    custom_text
                                )
                                hide_upload_loading(page)
                                if success:
                                    # 关键：重新读取最新图片，直接更新预览控件，不重新打开弹窗
                                    new_data = get_file_from_db("home_photos", biz_no)
                                    if new_data:
                                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as new_tmp:
                                            new_tmp.write(new_data)
                                            new_tmp_path = new_tmp.name
                                        img_control.src = new_tmp_path
                                        page.update()
                                    show_alert(page, "成功", "水印已更新")
                                else:
                                    show_alert(page, "错误", f"更新失败: {err[:50]}")
                            except Exception as ex:
                                hide_upload_loading(page)
                                show_alert(page, "错误", f"处理异常: {str(ex)[:50]}")

                        page.run_task(_task)

                    edit_dlg = ft.AlertDialog(
                        title=ft.Text("修改水印内容"),
                        content=ft.Column(
                            [
                                edit_time_input,
                                edit_order_input,
                                edit_cust_input,
                                edit_addr_input,
                                ft.ResponsiveRow(
                                    [
                                        ft.Column(col={"sm": 6}, controls=[edit_lng_input]),
                                        ft.Column(col={"sm": 6}, controls=[edit_lat_input]),
                                    ],
                                    spacing=5,
                                ),
                                ft.TextButton("获取当前位置", icon=ft.Icons.MY_LOCATION, on_click=get_location),
                            ],
                            spacing=8,
                            tight=True,
                            scroll=ft.ScrollMode.AUTO,
                            width=min(get_window_width(page) - 40, 420)
                        ),
                        modal=True,
                        actions=[
                            ft.TextButton("取消", on_click=lambda _: page.pop_dialog()),
                            ft.TextButton("保存修改", on_click=save_edit),
                        ],
                    )
                    page.show_dialog(edit_dlg)

                # ---------- 预览弹窗 ----------
                preview_dlg = ft.AlertDialog(
                    title=ft.Text("送货照片预览"),
                    content=preview_container,
                    actions=[
                        ft.Row(
                            [
                                ft.IconButton(icon=ft.Icons.EDIT, tooltip="修改",on_click=do_edit_home_photo),
                                ft.IconButton(icon=ft.Icons.DOWNLOAD, tooltip="下载",on_click=do_download_home_photo),
                                ft.IconButton(icon=ft.Icons.CLOSE,tooltip="关闭",on_click=lambda _: page.pop_dialog()),
                            ],
                            spacing=20,
                            wrap=False,
                            alignment=ft.MainAxisAlignment.CENTER,
                        )
                    ],
                    modal=True,
                )
                page.show_dialog(preview_dlg)

            # ---------------------- SN码管理弹窗 (优化上传+弹窗关闭) ----------------------
            def open_sn_manage_dialog(e):
                sn_dialog = None
                current_mode = "menu"

                def refresh_view():
                    if current_mode == "menu":
                        sn_dialog.content = build_menu_view()
                    elif current_mode == "manual":
                        sn_dialog.content = build_manual_view()
                    page.update()

                def build_menu_view():
                    def go_scan(e):
                        page.pop_dialog()

                        def on_image_selected(path):
                            if not path:
                                open_sn_manage_dialog(None)
                                return

                            async def decode_and_process():
                                await show_upload_loading_async(page, "正在识别条码...")
                                try:
                                    codes = await asyncio.to_thread(barcode_image_decode, path, timeout=3.0)
                                    hide_upload_loading(page)
                                    if not codes:
                                        show_alert(page, "提示", "未识别到条码或二维码",
                                                   on_ok=lambda ev: open_sn_manage_dialog(None))
                                        return
                                    if len(codes) == 1:
                                        code = codes[0].strip()

                                        def on_confirm(ev):
                                            page.pop_dialog()

                                            async def do_save():
                                                await save_sn_and_photo(code, path)

                                            page.run_task(do_save)

                                        confirm_dlg = ft.AlertDialog(
                                            title=ft.Text("识别到条码"),
                                            content=ft.Text(f"SN码：{code}"),
                                            modal=True,
                                            actions=[
                                                ft.TextButton("取消", on_click=lambda ev: (
                                                    page.pop_dialog(), open_sn_manage_dialog(None))),
                                                ft.TextButton("确认", on_click=on_confirm),
                                            ]
                                        )
                                        page.show_dialog(confirm_dlg)
                                    else:
                                        def handle_select(selected_code):
                                            async def do_save():
                                                await save_sn_and_photo(selected_code, path)

                                            page.run_task(do_save)

                                        await show_code_selector(page, codes, handle_select)
                                except Exception as ex:
                                    hide_upload_loading(page)
                                    show_alert(page, "错误", f"识别失败: {str(ex)[:30]}")

                            page.run_task(decode_and_process)

                        show_image_source_dialog(page, on_image_selected, title="选择条码图片")

                    def go_manual(e):
                        nonlocal current_mode
                        current_mode = "manual"
                        refresh_view()

                    return ft.Column(
                        [
                            ft.Text("SN码录入", size=16, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                            ft.Divider(height=10),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.CAMERA_ALT, color=ft.Colors.BLUE),
                                title=ft.Text("扫码录入"),
                                subtitle=ft.Text("拍照/选图自动识别，一步完成"),
                                on_click=go_scan
                            ),
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.EDIT, color=ft.Colors.GREY),
                                title=ft.Text("手动录入"),
                                subtitle=ft.Text("扫码失败时手动输入"),
                                on_click=go_manual
                            ),
                        ],
                        width=min(320, (get_window_width(page) or 480) - 40),
                        spacing=8,
                    )

                async def save_sn_and_photo(sn_code, img_path):
                    await show_upload_loading_async(page, "正在保存并上传...")
                    try:
                        def _background_work():
                            success, db_tag, err = upload_image_to_db(
                                img_path, "sn_photos",
                                current_order["out_order_no"], "SN", delete_old=True
                            )
                            if not success:
                                return False, err
                            conn = get_db_conn()
                            if not conn:
                                return False, "数据库连接失败"
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE transport SET sn_code=%s, sn_photo=%s WHERE out_order_no=%s",
                                (sn_code, db_tag, current_order["out_order_no"])
                            )
                            conn.commit()
                            conn.close()
                            return True, ""

                        success, err_msg = await asyncio.to_thread(_background_work)
                        hide_upload_loading(page)

                        if success:
                            # 更新UI状态（关键：原地更新，不重建弹窗）
                            current_order["sn_code"] = sn_code
                            current_order["sn_photo"] = f"db:sn_photos:{current_order['out_order_no']}"
                            sn_entry.value = sn_code
                            sn_photo_status.value = "SN照片: 已上传"
                            sn_photo_status.color = ft.Colors.GREEN
                            page.update()

                            # 修改：不再关闭并重新打开操作弹窗，只提示成功
                            show_alert(page, "成功", "SN码已保存，照片已自动上传")
                        else:
                            show_alert(page, "失败", f"保存失败: {err_msg[:30]}")
                    except Exception as ex:
                        hide_upload_loading(page)
                        show_alert(page, "错误", f"处理异常: {str(ex)[:30]}")

                def build_manual_view():
                    tip = ft.Text("请输入SN码并上传照片", size=12, text_align=ft.TextAlign.CENTER)
                    sn_input = ft.TextField(label="手动输入SN码", value=current_order["sn_code"], width=280)

                    def pick_photo(e):
                        async def _pick_task():
                            path = await pick_image_async(page)
                            if not path:
                                return
                            await show_upload_loading_async(page)
                            try:
                                success, db_tag, err_msg = await asyncio.to_thread(
                                    upload_image_to_db,
                                    path, "sn_photos",
                                    current_order["out_order_no"], "SN", delete_old=True
                                )
                                if success:
                                    current_order["sn_photo"] = db_tag
                                    sn_photo_status.value = "SN照片: 已上传"
                                    sn_photo_status.color = ft.Colors.GREEN
                                    tip.value = "照片上传成功"
                                    tip.color = ft.Colors.GREEN
                                    page.update()
                                else:
                                    await show_alert_async(page, "上传失败", err_msg[:30])
                            except Exception as ex:
                                await show_alert_async(page, "上传失败", str(ex)[:30])
                            finally:
                                hide_upload_loading(page)

                        page.run_task(_pick_task)

                    def save_sn_code(e):
                        sn_code = sn_input.value.strip()
                        if not sn_code:
                            show_alert(page, "提示", "请输入SN码")
                            return
                        try:
                            conn = get_db_conn()
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE transport SET sn_code=%s WHERE out_order_no=%s",
                                (sn_code, current_order["out_order_no"])
                            )
                            conn.commit()
                            conn.close()
                            current_order["sn_code"] = sn_code
                            sn_entry.value = sn_code
                            show_alert(page, "成功", "SN码已保存")
                            # 原地更新，不关闭操作弹窗
                        except Exception as ex:
                            show_alert(page, "错误", f"保存失败: {str(ex)}")

                    def back_to_menu(e):
                        nonlocal current_mode
                        current_mode = "menu"
                        refresh_view()

                    return ft.Column(
                        [
                            ft.Text("手动录入SN码", size=16, weight=ft.FontWeight.BOLD),
                            tip,
                            ft.Button("拍摄/选择SN照片", on_click=pick_photo, expand=True),
                            sn_input,
                            ft.Row(
                                [
                                    ft.TextButton("返回菜单", on_click=back_to_menu),
                                    ft.Button("保存SN码", on_click=save_sn_code)
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                            )
                        ],
                        width=min(320, (get_window_width(page) or 480) - 40),
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO
                    )

                sn_dialog = ft.AlertDialog(
                    title=ft.Text("SN码录入"),
                    content=build_menu_view(),
                    modal=True,
                    content_padding=ft.Padding(12, 10, 12, 10),
                    actions=[
                        ft.TextButton("关闭", on_click=lambda e: page.pop_dialog())
                    ],
                    on_dismiss=lambda e: None
                )
                page.show_dialog(sn_dialog)

            def process_image(file_path, add_watermark, order_no, cust_name, full_addr, out_order_no,
                              lat="获取失败", lng="获取失败", custom_watermark_text=None):
                """纯后台图片处理+入库函数，无任何UI/权限/定位操作"""
                try:
                    import datetime
                    import io
                    import os
                    from PIL import Image, ImageDraw, ImageFont

                    img = Image.open(file_path)
                    if add_watermark:
                        draw = ImageDraw.Draw(img)
                        if custom_watermark_text is not None:
                            # 用户自定义水印内容
                            watermark_text = custom_watermark_text
                        else:
                            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            loc_line = f"经度:{lng} 纬度:{lat}"
                            watermark_text = "\n".join([
                                now_str,
                                f"订单号:{order_no}",
                                f"客户:{cust_name}",
                                f"地址:{full_addr}",
                                loc_line
                            ])
                        font = load_chinese_font(28)
                        bbox = draw.textbbox((0, 0), watermark_text, font=font)
                        tw = bbox[2] - bbox[0]
                        th = bbox[3] - bbox[1]
                        x_pos = img.width - tw - 20
                        y_pos = img.height - th - 20
                        draw.rectangle(
                            [x_pos - 8, y_pos - 8, x_pos + tw + 8, y_pos + th + 8],
                            fill=(0, 0, 0, 170)
                        )
                        draw.text((x_pos, y_pos), watermark_text, font=font, fill=(255, 255, 255, 255))

                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=100)
                    tmp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
                    with open(tmp_file, "wb") as f:
                        f.write(buf.getvalue())
                    biz_no, prefix = get_home_photo_biz_info(order_no, out_order_no)
                    success, db_tag, err = upload_image_to_db(tmp_file, "home_photos", biz_no, prefix, delete_old=True)
                    try:
                        os.unlink(tmp_file)
                    except:
                        pass
                    return success, db_tag, err
                except Exception as ex:
                    print(f"[HomePhoto] Process error: {ex}")
                    return False, None, str(ex)

            # ---------------------- 送货照片上传入口 ----------------------
            def do_upload_home_photo(e):
                if upload_busy_lock:
                    show_alert(page, "提示", "正在上传中，请稍后再操作")
                    return
                biz_no, prefix = get_home_photo_biz_info(order_no, out_order_no)
                conn = get_db_conn()
                if not conn:
                    show_alert(page, "数据库异常", "无法连接数据库，照片上传中断")
                    return
                cur = conn.cursor()
                cur.execute("SELECT cust_name, full_addr FROM sale_main WHERE order_no=%s", (order_no,))
                res = cur.fetchone()
                conn.close()
                if not res:
                    show_alert(page, "错误", "未找到订单信息")
                    return

                def on_camera_click(e):
                    page.pop_dialog()

                    # 定义上传逻辑（从原 camera_callback 中提取）
                    async def do_upload_photo(path, add_watermark):
                        loc_success, lat, lng = await get_current_location(page)
                        if not loc_success:
                            show_snack(page, "位置获取失败，水印将使用粗略定位", ft.Colors.ORANGE)

                        await show_upload_loading_async(page, "正在处理并上传照片...")
                        try:
                            success, db_tag, err_msg = await asyncio.to_thread(
                                process_image,
                                path,
                                add_watermark=add_watermark,
                                order_no=order_no,
                                cust_name=cust_name,
                                full_addr=full_addr,
                                out_order_no=out_order_no,
                                lat=lat,
                                lng=lng
                            )
                            hide_upload_loading(page)

                            if success:
                                # 原地更新UI（不重建弹窗）
                                current_order["home_photo"] = db_tag
                                home_photo_status.value = "送货照片: 已上传"
                                home_photo_status.color = ft.Colors.GREEN
                                page.update()
                                show_alert(page, "成功", "送货照片上传完成")
                            else:
                                show_alert(page, "错误", f"上传失败: {err_msg[:50]}")
                        except Exception as ex:
                            hide_upload_loading(page)
                            show_alert(page, "错误", f"上传异常: {str(ex)[:50]}")

                    # 预览对话框构建
                    def show_preview_dialog(path):
                        # 预览图片
                        preview_image = ft.Image(
                            src=path,
                            fit="contain",
                            expand=True,
                        )

                        # 三个操作按钮
                        def on_confirm(e):
                            page.pop_dialog()  # 关闭预览
                            page.run_task(do_upload_photo, path, True)  # 上传（拍照带水印）

                        def on_retake(e):
                            page.pop_dialog()  # 关闭预览
                            show_camera_view(page, camera_callback)  # 重新打开相机

                        def on_close(e):
                            page.pop_dialog()  # 仅关闭预览

                        preview_dlg = ft.AlertDialog(
                            title=ft.Text("照片预览"),
                            content=ft.Column(
                                [
                                    preview_image,
                                    ft.Column(
                                        [
                                            ft.Button("确定上传", on_click=on_confirm),
                                            ft.Button("返回重拍", on_click=on_retake),
                                            ft.TextButton("关闭", on_click=on_close),
                                        ],
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        spacing=10,
                                    ),
                                ],
                                spacing=10,
                                tight=True,
                            ),
                            modal=True,
                        )
                        page.show_dialog(preview_dlg)

                    # 相机回调：拍照完成后显示预览，不再直接上传
                    def camera_callback(path):
                        if not path:
                            return  # 用户取消拍照
                        show_preview_dialog(path)

                    show_camera_view(page, camera_callback)

                def on_gallery_click(e):
                    page.pop_dialog()

                    async def pick_task():
                        path = await pick_image_async(page)
                        if not path:
                            return

                        loc_success, lat, lng = await get_current_location(page)
                        if not loc_success:
                            show_snack(page, "位置获取失败，水印将使用粗略定位", ft.Colors.ORANGE)

                        await show_upload_loading_async(page, "正在上传照片...")
                        try:
                            success, db_tag, err_msg = await asyncio.to_thread(
                                process_image,
                                path,
                                add_watermark=False,
                                order_no=order_no,
                                cust_name=cust_name,
                                full_addr=full_addr,
                                out_order_no=out_order_no,
                                lat=lat,
                                lng=lng
                            )
                            hide_upload_loading(page)

                            if success:
                                # 原地更新UI（不重建弹窗）
                                current_order["home_photo"] = db_tag
                                home_photo_status.value = "送货照片: 已上传"
                                home_photo_status.color = ft.Colors.GREEN
                                page.update()

                                show_alert(page, "成功", "送货照片上传完成")
                            else:
                                show_alert(page, "错误", f"上传失败: {err_msg[:50]}")
                        except Exception as ex:
                            hide_upload_loading(page)
                            show_alert(page, "错误", f"上传异常: {str(ex)[:50]}")

                    page.run_task(pick_task)

                upload_dlg = ft.AlertDialog(
                    title=ft.Text("上传送货照片", weight=ft.FontWeight.BOLD),
                    content=ft.Column([
                        ft.ListTile(leading=ft.Icon(ft.Icons.CAMERA_ALT, color=ft.Colors.BLUE),
                                    title=ft.Text("拍照（自动添加水印）"), on_click=on_camera_click),
                        ft.ListTile(leading=ft.Icon(ft.Icons.PHOTO, color=ft.Colors.GREEN),
                                    title=ft.Text("从相册选择（无水印）"), on_click=on_gallery_click),
                    ], tight=True),
                    actions=[ft.TextButton("取消", on_click=lambda e: page.pop_dialog())],
                    modal=True,
                )
                page.show_dialog(upload_dlg)

            # 构建操作弹窗内容
            content = ft.Column(
                [
                    ft.Text(f"订单: {order_no}", size=16, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.Text(f"客户: {cust_name}  电话: ", size=13),
                            ft.GestureDetector(
                                content=ft.Text(
                                    phone,
                                    size=13,
                                    color=ft.Colors.BLUE,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                on_tap=lambda e: show_phone_dialog(phone),
                            ),
                        ],
                        spacing=0,
                    ),
                    ft.Text(f"地址: {full_addr}", size=13),
                    ft.Text(f"型号: {model}  数量: {t_qty}", size=13),
                    status_label,
                    ft.Row([sn_photo_status, home_photo_status], spacing=5),
                    ft.Divider(height=8),
                    ft.Text("操作", weight=ft.FontWeight.BOLD),
                    ft.Row([sn_entry], spacing=8),
                    ft.Row([trans_date_input, need_delivery_cb], spacing=5),
                    ft.Row([delivery01], spacing=5),
                    ft.Row([delivery02], spacing=5),
                    ft.Row(
                        [
                            ft.IconButton(ft.Icons.CAMERA_ALT, tooltip="上传SN照片", on_click=open_sn_manage_dialog),
                            ft.IconButton(ft.Icons.HOME, tooltip="上传送货照片", on_click=do_upload_home_photo),
                            ft.IconButton(ft.Icons.PHOTO, tooltip="查看SN照片", on_click=do_view_sn_photo),
                            ft.IconButton(ft.Icons.PHOTO_LIBRARY, tooltip="查看送货照片", on_click=do_view_home_photo),
                        ],
                        spacing=4,
                        alignment=ft.MainAxisAlignment.SPACE_EVENLY
                    ),
                    ft.Row(
                        [
                            ft.Button("出库", icon=ft.Icons.CHECK, expand=True, on_click=do_confirm_out),
                            ft.Button("送达", icon=ft.Icons.LOCAL_SHIPPING, expand=True,
                                      on_click=do_confirm_delivered),
                        ],
                        spacing=5,
                    ),
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                width=min(get_window_width(page) + 20, 520) if (get_window_width(page) or 520) else 500,
                height=min(get_window_width(page) - 50, 600) if (get_window_width(page) or 480) else 500,
            )

            dlg = ft.AlertDialog(
                title=ft.Text("出库操作"),
                content=content,
                modal=True,
                actions=[
                    ft.TextButton("关闭", on_click=lambda e: page.pop_dialog())
                ],
                on_dismiss=lambda e: None
            )
            page.show_dialog(dlg)

        # ====================== 派单功能 ======================
        def open_assign_dialog(row):
            """打开同地址批量派单对话框，支持修改默认送货人"""
            # 从选中订单行获取必要信息
            _, _, order_no, out_order_no, cust_name, phone, full_addr, factory, category, model, t_qty, trans_remark, status_val, send_date_val, trans_date_val, delivery01_name, delivery02_name, sn_code, sn_photo, home_photo = row

            # 查询同地址所有待派单订单，并额外获取 sale_items 表中的 sale_remark
            conn = get_db_conn()
            if not conn:
                show_alert(page, "错误", "数据库连接失败")
                return
            cur = conn.cursor()
            cur.execute(
                """SELECT t.order_date, t.order_no, t.out_order_no, t.cust_name, t.phone, t.full_addr,
                          t.factory, t.category, t.model, t.t_qty, t.trans_remark, t.send_date,
                          (SELECT s.sale_remark FROM sale_items s 
                           WHERE s.order_no = t.order_no AND s.out_order_no = t.out_order_no 
                           LIMIT 1) AS sale_remark
                   FROM transport t
                   WHERE t.full_addr=%s AND t.status='待派单'
                   ORDER BY t.send_date ASC""",
                (full_addr,)
            )
            all_orders = cur.fetchall()
            conn.close()

            if not all_orders:
                show_alert(page, "提示", "该地址暂无待派单订单！")
                return

            # 查询收货人电话（从 sale_main 表）
            receiver_phone = None
            conn = get_db_conn()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT receiver_phone FROM sale_main WHERE order_no=%s", (order_no,))
                res = cur.fetchone()
                if res:
                    receiver_phone = res[0]
                conn.close()

            # 获取所有用户 real_name 列表（用于下拉选项）
            conn = get_db_conn()
            all_users = []
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT real_name FROM users ORDER BY real_name")
                all_users = [r[0] for r in cur.fetchall()]
                conn.close()

            # 下拉选项：包含空选项和所有用户
            def build_user_options(exclude=None):
                opts = [ft.dropdown.Option("", "无")]
                for name in all_users:
                    if name != exclude:
                        opts.append(ft.dropdown.Option(name))
                return opts

            # 当前默认送货人（全局变量）
            current_d1 = DEFAULT_DELIVER1
            current_d2 = DEFAULT_DELIVER2

            # 创建送货人下拉框
            deliver1_dd = ft.Dropdown(
                label="送货人1",
                options=build_user_options(),
                value=current_d1 if current_d1 in all_users else "",
                width=min(get_window_width(page) - 40, 250),
            )
            deliver2_dd = ft.Dropdown(
                label="送货人2",
                options=build_user_options(exclude=current_d1 if current_d1 else None),
                value=current_d2 if current_d2 in all_users else "",
                width=min(get_window_width(page) - 40, 250),
            )

            # 处理下拉联动：当 deliver1 改变时，更新 deliver2 的选项排除 deliver1 选中的值
            def on_deliver1_change(e):
                selected = deliver1_dd.value
                deliver2_dd.options = build_user_options(exclude=selected if selected else None)
                if deliver2_dd.value == selected and selected:
                    deliver2_dd.value = ""
                page.update()

            def on_deliver2_change(e):
                selected = deliver2_dd.value
                deliver1_dd.options = build_user_options(exclude=selected if selected else None)
                if deliver1_dd.value == selected and selected:
                    deliver1_dd.value = ""
                page.update()

            deliver1_dd.on_change = on_deliver1_change
            deliver2_dd.on_change = on_deliver2_change

            # 存储每个订单的复选框和对应数据（order 包含 13 个字段）
            check_items = []  # 每个元素为 (checkbox, order_data_13fields)

            # 构建订单列表容器
            orders_column = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO)

            for order in all_orders:
                # 只显示订单号、型号、数量、备注（sale_remark）
                cb = ft.Checkbox(value=True, label="")
                order_text = f"订单号: {order[1]} | 型号: {order[8]} | 数量: {order[9]} | 备注: {order[12]}"
                item_row = ft.Row([cb, ft.Text(order_text, size=12, expand=True)], spacing=5)
                orders_column.controls.append(item_row)
                check_items.append((cb, order))

            # 全选/取消全选
            def select_all(e):
                for cb, _ in check_items:
                    cb.value = True
                page.update()

            def deselect_all(e):
                for cb, _ in check_items:
                    cb.value = False
                page.update()

            # 生成派单图片的函数（紧凑裁剪，只显示文字区域）
            def generate_assign_image(text):
                try:
                    from PIL import Image, ImageDraw, ImageFont
                    font = load_chinese_font(20)
                    lines = text.split('\n')
                    # 临时绘制以计算文字包围盒
                    draw_tmp = ImageDraw.Draw(Image.new('RGB', (1, 1)))
                    max_width = 0
                    total_height = 0
                    line_heights = []
                    for line in lines:
                        bbox = draw_tmp.textbbox((0, 0), line, font=font)
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                        max_width = max(max_width, w)
                        line_heights.append(h)
                        total_height += h + 6  # 行间距 6 像素
                    # 设置极小的边距
                    margin = 10
                    img_width = max_width + margin * 2
                    img_height = total_height + margin * 2
                    img = Image.new('RGB', (img_width, img_height), color=(255, 255, 255))
                    draw = ImageDraw.Draw(img)
                    y = margin
                    for line, h in zip(lines, line_heights):
                        draw.text((margin, y), line, font=font, fill=(0, 0, 0))
                        y += h + 6
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    img.save(tmp.name)
                    return tmp.name
                except Exception as e:
                    print(f"生成派单图片失败: {e}")
                    return None

            # 确认派单
            def do_confirm(e):
                # 收集勾选订单（转换为原 12 字段元组，便于后续处理）
                selected_orders = [order[:12] for cb, order in check_items if cb.value]
                if not selected_orders:
                    show_alert(page, "提示", "请至少勾选一个订单")
                    return

                # 构建派单信息文本（与原逻辑完全一致）
                first_order = selected_orders[0]
                cust_name = first_order[3]
                phone = first_order[4]
                address = first_order[5]
                rem = first_order[10]  # trans_remark，保持不变
                pic_text = f"======= ★★★ 配送派单明细 ★★★ =======\n"
                pic_text += f"收货人：{receiver_phone}\n"
                pic_text += f"客户：{cust_name}    电话：{phone}\n"
                pic_text += f"地址：{address}\n"
                pic_text += f"备注：{rem}\n"
                pic_text += "----------------------------------------\n"
                pic_text += "产品信息\n\n"

                from collections import defaultdict
                product_map = defaultdict(lambda: {"qty": 0, "fac": "", "categ": ""})
                for order in selected_orders:
                    od, ono, outno, cust, ph, ad, fac, categ, model, qty, remark, send_date = order
                    key = (fac, categ, model)
                    try:
                        qty_num = int(qty)
                    except:
                        qty_num = 0
                    product_map[key]["qty"] += qty_num
                    product_map[key]["fac"] = fac
                    product_map[key]["categ"] = categ

                for key, val in product_map.items():
                    fac, categ, model = key
                    total_qty = val["qty"]
                    pic_text += f"   品牌：{fac}\n"
                    pic_text += f"   品类：{categ}\n"
                    pic_text += f"** 型号：{model}\n"
                    pic_text += f"   数量：{total_qty}\n\n"

                # 执行数据库更新（使用事务）
                conn = get_db_conn()
                if not conn:
                    show_alert(page, "错误", "数据库连接失败")
                    return
                cur = conn.cursor()
                try:
                    # 更新订单状态：勾选的改为待出库，未勾选的保持待派单
                    for cb, order in check_items:
                        if cb.value:
                            cur.execute(
                                "UPDATE transport SET status='待出库' WHERE order_no=%s AND out_order_no=%s",
                                (order[1], order[2])
                            )
                        else:
                            cur.execute(
                                "UPDATE transport SET status='待派单' WHERE order_no=%s AND out_order_no=%s",
                                (order[1], order[2])
                            )

                    # 更新送货人角色（表名使用 users）
                    cur.execute("SELECT real_name FROM users WHERE role='配送员'")
                    old_delivers = [r[0] for r in cur.fetchall()]
                    new_delivers = [d for d in [deliver1_dd.value, deliver2_dd.value] if d]

                    for old in old_delivers:
                        if old not in new_delivers:
                            cur.execute("UPDATE users SET role='普通用户' WHERE real_name=%s", (old,))
                    for new in new_delivers:
                        cur.execute("UPDATE users SET role='配送员' WHERE real_name=%s", (new,))

                    conn.commit()

                    # 生成派单图片
                    img_path = generate_assign_image(pic_text)

                    # 更新全局默认送货人变量
                    nonlocal DEFAULT_DELIVER1, DEFAULT_DELIVER2
                    DEFAULT_DELIVER1 = deliver1_dd.value if deliver1_dd.value else ""
                    DEFAULT_DELIVER2 = deliver2_dd.value if deliver2_dd.value else ""

                    # 关闭派单对话框
                    page.pop_dialog()

                    # 刷新运输列表
                    load_trans()

                    # 显示成功提示
                    show_alert(page, "完成", "✅ 勾选订单已改为【待出库】\n派单明细已生成")

                    # 延迟显示派单图片预览（异步）
                    if img_path:
                        async def show_preview_async():
                            await asyncio.sleep(0.5)

                            # 分享图片到系统分享面板
                            async def share_image(e):
                                try:
                                    share = ft.Share()
                                    if page.web:
                                        # Web 平台不支持路径分享，改用字节分享
                                        with open(img_path, "rb") as f:
                                            file_bytes = f.read()
                                        share_file = ft.ShareFile.from_bytes(
                                            file_bytes,
                                            mime_type="image/png",
                                            name=f"派单图片_{order_no}.png",
                                        )
                                    else:
                                        share_file = ft.ShareFile.from_path(img_path)

                                    result = await share.share_files(
                                        [share_file],
                                        text="派单图片",
                                        title="分享派单图片",
                                    )
                                    show_alert(page, "提示", f"分享状态：{result.status}")
                                except Exception as ex:
                                    show_alert(page, "错误", f"分享失败: {str(ex)[:50]}")

                            # 保存图片到本地
                            def save_image(e):
                                try:
                                    page.pop_dialog()
                                    page.update()

                                    async def do_save():
                                        try:
                                            path = await ft.FilePicker().save_file(
                                                dialog_title="保存派单图片",
                                                file_name=f"派单图片_{order_no}.png",
                                                allowed_extensions=["png"],
                                                src_bytes=open(img_path, "rb").read()
                                            )
                                            if path:
                                                show_alert(page, "成功", "图片已保存")
                                        except Exception as ex:
                                            show_alert(page, "错误", f"保存失败: {str(ex)[:50]}")

                                    page.run_task(do_save)
                                except Exception as ex:
                                    show_alert(page, "错误", f"操作异常: {str(ex)[:50]}")

                            preview_dlg = ft.AlertDialog(
                                title=ft.Text("派单图片"),
                                content=ft.Container(
                                    content=ft.Image(src=img_path, fit="contain"),
                                    width=min(get_window_width(page) - 40, 500),
                                    height=min(get_window_width(page) * 0.8, 600),
                                ),
                                actions=[
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                ft.Icons.SHARE,
                                                tooltip="分享图片",
                                                on_click=share_image,  # 异步函数作为事件处理需注意
                                            ),
                                            ft.IconButton(
                                                ft.Icons.SAVE,
                                                tooltip="保存图片",
                                                on_click=save_image,
                                            ),
                                            ft.IconButton(
                                                ft.Icons.CLOSE,
                                                tooltip="关闭",
                                                on_click=lambda _: page.pop_dialog(),
                                            ),
                                        ],
                                        spacing=20,
                                        alignment=ft.MainAxisAlignment.CENTER,
                                    )
                                ],
                                modal=True,
                            )
                            page.show_dialog(preview_dlg)

                        page.run_task(show_preview_async)

                    load_trans()
                    page.pop_dialog()
                except Exception as ex:
                    conn.rollback()
                    show_alert(page, "错误", f"派单失败: {str(ex)}")
                finally:
                    conn.close()

            # 构建派单对话框内容
            assign_content = ft.Column(
                [
                    ft.Text(f"收货人及电话：{receiver_phone}", size=14, weight=ft.FontWeight.BOLD),
                    ft.Text(f"送货地址：{full_addr}", size=12),
                    ft.Divider(height=10),
                    ft.Text("选择要派送的订单（默认全选）", weight=ft.FontWeight.BOLD),
                    orders_column,
                    ft.Row(
                        [
                            ft.TextButton("全选", on_click=select_all),
                            ft.TextButton("取消全选", on_click=deselect_all),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=10),
                    ft.Text("设置送货人", weight=ft.FontWeight.BOLD),
                    ft.Row([deliver1_dd, deliver2_dd], spacing=10, wrap=True),
                    ft.Row(
                        [
                            ft.Button("确认派单", icon=ft.Icons.CHECK, on_click=do_confirm, expand=True),
                            ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
                        ],
                        spacing=5,
                    ),
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                width=min(get_window_width(page) - 40, 500),
                height=min(get_window_width(page) * 0.8, 700),
            )

            dlg = ft.AlertDialog(
                title=ft.Text("🚚 同地址批量派单"),
                content=assign_content,
                modal=True,
                actions=[],
                on_dismiss=lambda e: None,
            )
            page.show_dialog(dlg)

        def load_trans():
            trans_list.controls.clear()
            try:
                conn = get_db_conn()
                if not conn:
                    trans_list.controls.append(ft.Text("数据库连接失败", color=ft.Colors.RED))
                    page.update()
                    return
                status = status_dropdown.value
                s_date = start_date.value.strip()
                e_date = end_date.value.strip()
                order_no = order_no_input.value.strip()
                cust_name = cust_name_input.value.strip()

                if status in ["已送货入户", "已自提"]:
                    date_field = "trans_date"
                else:
                    date_field = "order_date"

                sql = f"""
                    SELECT id, order_date, order_no, out_order_no, cust_name, phone, full_addr,
                           factory, category, model, t_qty, trans_remark,
                           status, send_date, trans_date,
                           COALESCE(delivery01_name,''), COALESCE(delivery02_name,''),
                           sn_code, sn_photo, home_photo
                    FROM transport
                    WHERE 1=1
                """
                params = []
                if status and status != "全部":
                    sql += " AND status = %s"
                    params.append(status)
                if s_date and e_date:
                    sql += f" AND {date_field} BETWEEN %s AND %s"
                    params.extend([s_date, e_date])
                if order_no:
                    sql += " AND order_no LIKE %s"
                    params.append(f"%{order_no}%")
                if cust_name:
                    sql += " AND cust_name LIKE %s"
                    params.append(f"%{cust_name}%")
                sql += f" ORDER BY {date_field} DESC"

                cur = conn.cursor()
                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()

                if not rows:
                    trans_list.controls.append(ft.Text("暂无符合条件的运输任务", size=16))
                    page.update()
                    return

                for row in rows:
                    trans_id, order_date, order_no, out_order_no, cust_name, phone, full_addr, factory, category, model, t_qty, trans_remark, status_val, send_date_val, trans_date_val, delivery01_name, delivery02_name, sn_code, sn_photo, home_photo = row
                    tag = "normal"
                    today = date.today()
                    try:
                        if send_date_val and isinstance(send_date_val, str):
                            send_dt = datetime.strptime(send_date_val, "%Y-%m-%d").date()
                        else:
                            send_dt = send_date_val
                        if isinstance(send_dt, date) and send_dt < today:
                            if status_val == "待派单":
                                tag = "overdue"
                            elif status_val == "待出库":
                                tag = "orange"
                        if status_val in ["已出库", "待自提", "已自提", "已送货入户"]:
                            tag = "overtrans"
                    except:
                        pass

                    border_side = None
                    if tag == "overdue":
                        border_side = ft.Border(left=ft.BorderSide(4, ft.Colors.RED))
                    elif tag == "orange":
                        border_side = ft.Border(left=ft.BorderSide(4, ft.Colors.ORANGE))
                    elif tag == "overtrans":
                        border_side = ft.Border(left=ft.BorderSide(4, ft.Colors.GREEN))

                    card = ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(f"订单: {order_no}", weight=ft.FontWeight.BOLD),
                                            ft.Text(f"客户: {cust_name}", weight=ft.FontWeight.BOLD),
                                            ft.Text(f"状态: {status_val}"),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    ft.Text(
                                        f"型号: {model}  数量: {t_qty}  计划日: {send_date_val}  实际日: {trans_date_val}"),
                                    ft.Text(f"地址: {full_addr}"),
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                ft.Icons.EDIT,
                                                tooltip="修改状态",
                                                on_click=lambda e, r=row: change_status(r),
                                            ),
                                            ft.IconButton(
                                                ft.Icons.LOCAL_SHIPPING,  # 货车图标
                                                tooltip="派单",
                                                on_click=lambda e, r=row: open_assign_dialog(r),
                                            ),
                                        ],
                                        spacing=5,
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                ],
                                spacing=5,
                            ),
                            padding=10,
                            on_click=lambda e, r=row: open_operation_dialog(r),
                            bgcolor=ft.Colors.WHITE,
                            border=border_side if border_side else None,
                        ),
                        elevation=2,
                    )
                    trans_list.controls.append(card)
                page.update()
            except Exception as err:
                trans_list.controls.append(ft.Text(f"加载运输列表异常：{str(err)}", color=ft.Colors.RED, size=14))
                page.update()

        def do_query(e):
            load_trans()

        def do_reset(e):
            status_dropdown.value = "全部"
            start_date.value = ""
            end_date.value = ""
            order_no_input.value = ""
            cust_name_input.value = ""
            load_trans()

        query_btn.on_click = do_query
        reset_btn.on_click = do_reset

        main_content.controls.append(
            ft.Column(
                [
                    ft.Text("运输任务", size=20, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            status_dropdown,
                            start_date,
                            end_date,
                            order_no_input,
                            cust_name_input,
                            query_btn,
                            reset_btn,
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                    ft.Divider(height=10),
                    trans_list,
                ],
                spacing=10,
            )
        )
        load_trans()
        page.update()

    # ---------------------------- 安装管理 ----------------------------

    def show_install():
        main_content.controls.clear()
        w1 = get_field_width(page, ratio=2, subtract=60)
        w2 = get_field_width(page, ratio=3, subtract=80)

        status_dropdown = ft.Dropdown(
            label="安装状态",
            width=w1,
            options=[
                ft.dropdown.Option("全部"),
                ft.dropdown.Option("待安装"),
                ft.dropdown.Option("已报装"),
                ft.dropdown.Option("已安装"),
            ],
            value="待安装",
        )
        start_date_field = ft.TextField(
            label="起始日期",
            width=w1,
            value=(date.today() - timedelta(days=30)).strftime("%Y-%m-%d"),
            read_only=True,
        )
        end_date_field = ft.TextField(
            label="结束日期",
            width=w1,
            value=date.today().strftime("%Y-%m-%d"),
            read_only=True,
        )

        # 标准日期选择弹窗
        def pick_date(target_field: ft.TextField):
            def on_date_selected(e):
                if e.control.value:
                    # 补上东八区8小时时差，解决选中日期少一天
                    local_fix_dt = e.control.value + timedelta(hours=8)
                    target_field.value = local_fix_dt.strftime("%Y-%m-%d")
                    page.update()
                page.pop_dialog()

            picker = ft.DatePicker(on_change=on_date_selected)
            page.show_dialog(picker)

        start_cal_btn = ft.TextButton("📅", on_click=lambda e: pick_date(start_date_field))
        end_cal_btn = ft.TextButton("📅", on_click=lambda e: pick_date(end_date_field))

        order_input = ft.TextField(label="订单号", width=w2, hint_text="模糊搜索")
        cust_input = ft.TextField(label="客户名称", width=w2, hint_text="模糊搜索")
        install_list = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO)

        def load_install():
            install_list.controls.clear()
            conn = get_db_conn()
            if not conn:
                install_list.controls.append(ft.Text("数据库连接失败", size=14, color="#ef4444"))
                page.update()
                return
            sql = """
                SELECT 
                    MAX(id) AS id,
                    MAX(order_date) AS order_date,
                    order_no,
                    MAX(cust_name) AS cust_name,
                    MAX(phone) AS phone,
                    MAX(factory) AS factory,
                    model,
                    SUM(i_qty) AS i_qty,
                    MAX(status) AS status,
                    MAX(CASE WHEN is_report=1 THEN '是' ELSE '否' END) AS is_report,
                    MAX(install_team) AS install_team,
                    MAX(install_tel) AS install_tel,
                    MAX(installer01) AS installer01,
                    MAX(installer02) AS installer02,
                    MAX(install_fee) AS install_fee,
                    MAX(fee_remark) AS fee_remark,
                    MAX(install_date) AS install_date,
                    MAX(install_time) AS install_time
                FROM install 
                WHERE 1=1
            """
            params = []
            status = status_dropdown.value
            if status and status != "全部":
                sql += " AND status = %s"
                params.append(status)
            start = start_date_field.value
            end = end_date_field.value
            if status in ["已安装", "已报装"]:
                if start:
                    sql += " AND install_date >= %s"
                    params.append(start)
                if end:
                    sql += " AND install_date <= %s"
                    params.append(end)
            else:
                if start:
                    sql += " AND order_date >= %s"
                    params.append(start)
                if end:
                    sql += " AND order_date <= %s"
                    params.append(end)
            order_no = order_input.value.strip()
            if order_no:
                sql += " AND order_no LIKE %s"
                params.append(f"%{order_no}%")
            cust_name = cust_input.value.strip()
            if cust_name:
                sql += " AND cust_name LIKE %s"
                params.append(f"%{cust_name}%")
            sql += " GROUP BY order_no, model ORDER BY MAX(install_date) DESC, MAX(install_time) DESC, order_no DESC"

            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()

            if not rows:
                install_list.controls.append(ft.Text("没有符合条件的安装记录", size=14, color="#94a3b8"))
                page.update()
                return

            for row in rows:
                install_id = row[0]
                order_no = row[2]
                cust_name = row[3]
                model = row[6]
                qty = row[7]
                status = row[8]
                r12 = str(row[12]).strip() if row[12] else ""
                r13 = str(row[13]).strip() if row[13] else ""
                team = row[10] if (not r12 and not r13) else (f"{r12}、{r13}" if (r12 and r13) else r12 or r13)
                install_time = str(row[17])[:5] if row[17] else "--:--"

                if status == "待安装":
                    color = "#f59e0b"
                elif status == "已报装":
                    color = "#3b82f6"
                else:
                    color = "#10b981"

                card = ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(f"📦 {order_no}", weight=ft.FontWeight.BOLD, size=14),
                                        ft.Text(f"安装方: {team}", color=color, size=12),
                                        ft.Text(f"状态: {status}", color=color, size=12),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Text(f"客户: {cust_name}  |  型号: {model}  |  数量: {qty}", size=12),
                                ft.Text(f"安装&报装日期: {row[16] or '--'}  {install_time}", size=12),
                                ft.Row(
                                    [
                                        ft.Button(
                                            "📞 报装",
                                            on_click=lambda e, st=status, order=order_no, mdl=model,
                                                            cust=cust_name, q=qty:
                                            report_install(st, order, mdl, cust, q),
                                        ),
                                        ft.Button(
                                            "✅ 安装",
                                            on_click=lambda e, st=status, order=order_no, mdl=model,
                                                            cust=cust_name, q=qty:
                                            confirm_install(st, order, mdl, cust, q),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.END,
                                    spacing=10,
                                ),
                            ],
                            spacing=5,
                        ),
                        padding=10,
                    )
                )
                install_list.controls.append(card)
            page.update()

        def report_install(status, order_no, model, cust_name, qty):
            if status != "待安装":
                show_alert(page, "提示", "只能报装待安装订单")
                return

            team_tel_dict = {
                "海信售后": "400-6111-111",
                "格力售后": "400-836-5315",
                "海尔售后": "4006-999-999",
                "美的售后": "400-889-9315",
                "小天鹅售后": "400-822-8228",
                "老板":"95105855"
            }

            tel_field = ft.TextField(
                label="联系电话",
                width=200,
                read_only=True
            )
            fee_field = ft.TextField(label="安装费用", width=200, value="0")
            remark_field = ft.TextField(label="费用备注", width=200)

            # 下拉框选中回调，对标你示例的 dropdown_changed
            def dropdown_selected(e):
                selected_team = e.control.value
                print("当前选中安装单位：", selected_team)
                tel_field.value = team_tel_dict.get(selected_team, "")
                page.update()

            team_dropdown = ft.Dropdown(
                label="安装单位",
                width=200,
                hint_text="请选择安装售后",
                options=[ft.DropdownOption(key=name, text=name) for name in team_tel_dict.keys()],
                on_select=dropdown_selected  # 和你的示例保持一致，用 on_select
            )

            def do_report(e):
                team = team_dropdown.value.strip() if team_dropdown.value else ""
                tel = tel_field.value.strip()

                # 兜底防护，防止极端情况界面没赋值成功
                if team in team_tel_dict and not tel:
                    tel = team_tel_dict[team]
                    tel_field.value = tel
                    page.update()

                fee = float(fee_field.value or 0) if fee_field.value else 0
                remark = remark_field.value.strip()

                if not team or not tel:
                    show_alert(page, "提示", "请选择安装单位")
                    return
                d = date.today()
                t = datetime.now()
                date_str = d.strftime("%Y-%m-%d")
                time_str = t.strftime("%H:%M:%S").lstrip("0").replace("0:", ":")
                # 下面原有数据库提交逻辑完全不动
                conn = get_db_conn()
                if not conn:
                    show_alert(page, "提示", "数据库连接失败")
                    return
                cur = conn.cursor()
                try:
                    sql = "UPDATE install SET status='已报装',is_report='1', install_team=%s, install_tel=%s, install_fee=%s, fee_remark=%s, install_date=%s,install_time=%s WHERE order_no = %s AND model = %s"
                    params = (team, tel, fee, remark, date_str,time_str,order_no,model)
                    cur.execute(sql, params)
                    rows_affected = cur.rowcount
                    conn.commit()
                    if rows_affected == 0:
                        show_alert(page, "提示", f"未找到 订单号={order_no} 的记录，更新失败")
                        conn.close()
                        return
                except Exception as ex:
                    conn.rollback()
                    show_alert(page, "提示", f"数据库错误：{ex}")
                    conn.close()
                    return
                conn.close()

                full_addr = "无地址"
                receiver_phone = "无电话"
                conn2 = get_db_conn()
                if conn2:
                    cur2 = conn2.cursor()
                    cur2.execute("SELECT full_addr, phone FROM sale_main WHERE order_no=%s", (order_no,))
                    addr_row = cur2.fetchone()
                    conn2.close()
                    if addr_row:
                        full_addr = addr_row[0] if addr_row[0] else "无地址"
                        receiver_phone = addr_row[1] if addr_row[1] else "无电话"

                clipboard_text = (
                    f"安装联系人：{receiver_phone}\n"
                    f"客户：{cust_name}\n"
                    f"{model} 共 {qty} 套安装\n"
                    f"地址：{full_addr}\n"
                    f"费用备注：{remark}"
                )
                page.pop_dialog()
                load_install()

                copy_ok = False
                try:
                    page.set_clipboard(clipboard_text)
                    copy_ok = True
                except Exception:
                    copy_ok = False

                if copy_ok:
                    show_alert(page, "成功", "报装成功，信息已复制到剪贴板")
                else:
                    text_dlg = ft.AlertDialog(
                        title=ft.Text("报装成功（请手动复制信息）"),
                        modal=True,
                        content=ft.TextField(
                            value=clipboard_text,
                            multiline=True,
                            read_only=True,
                            width=300,
                            min_lines=6,
                            max_lines=10
                        ),
                        actions=[ft.TextButton("关闭", on_click=lambda _: page.pop_dialog())],
                    )
                    page.show_dialog(text_dlg)

            dialog_content = ft.Column(
                [team_dropdown, tel_field, fee_field, remark_field],
                tight=True,
                spacing=10,
            )

            dialog = ft.AlertDialog(
                title=ft.Text("报装信息"),
                modal=True,
                content=dialog_content,
                actions=[
                    ft.TextButton("确认", on_click=do_report),
                    ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
                ]
            )
            page.show_dialog(dialog)

        def confirm_install(status, order_no, model, cust_name, qty):
            if status not in ["待安装", "已报装"]:
                show_alert(page, "提示", "只能确认待安装或已报装的订单")
                return

            installer_field = ft.TextField(label="安装人", width=200, value="徐连配")
            co_installer_field = ft.TextField(label="共同安装人", width=200, value="麻跃进")
            fee_field = ft.TextField(label="安装费用", width=200, value="0")
            remark_field = ft.TextField(label="费用备注", width=200)

            def do_confirm(e):
                installer = installer_field.value.strip()
                co_installer = co_installer_field.value.strip()
                fee = float(fee_field.value or 0) if fee_field.value else 0
                remark = remark_field.value.strip()
                if not installer:
                    show_snack(page, "请填写安装人", ft.Colors.RED)
                    return
                d = date.today()
                t = datetime.now()
                date_str = d.strftime("%Y-%m-%d")
                time_str = t.strftime("%H:%M:%S").lstrip("0").replace("0:", ":")
                conn = get_db_conn()
                if not conn:
                    show_snack(page, "数据库连接失败", ft.Colors.RED)
                    return
                cur = conn.cursor()
                try:
                    sql = "UPDATE install SET status='已安装',is_report='0', installer01=%s, installer02=%s, install_fee=%s, fee_remark=%s, install_date=%s, install_time=%s WHERE order_no = %s AND model = %s"
                    params = (installer, co_installer, fee, remark, date_str, time_str, order_no, model)
                    cur.execute(sql, params)
                    rows_affected = cur.rowcount
                    conn.commit()
                    if rows_affected == 0:
                        show_alert(page, "提示", f"⚠️ 订单号={order_no} 的记录，更新失败")
                        conn.close()
                        return
                    show_alert(page, "提示", "✅ 确认安装成功，状态已更新为'已安装'")
                except Exception as ex:
                    conn.rollback()
                    show_alert(page, "提示", f"❌ 数据库错误：{ex}")
                    conn.close()
                    return
                conn.close()
                load_install()

            dialog = ft.AlertDialog(
                title=ft.Text("安装确认"),
                modal=True,
                content=ft.Column(
                    [installer_field, co_installer_field, fee_field, remark_field],
                    tight=True,
                    spacing=10,
                ),
                actions=[
                    ft.TextButton("确认", on_click=do_confirm),
                    ft.TextButton("取消", on_click=lambda e: page.pop_dialog()),
                ],
            )
            page.show_dialog(dialog)

        def on_search(e):
            load_install()

        def on_reset(e):
            status_dropdown.value = "待安装"
            start_date_field.value = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
            end_date_field.value = date.today().strftime("%Y-%m-%d")
            order_input.value = ""
            cust_input.value = ""
            page.update()
            load_install()

        query_row = ft.Row(
            [
                status_dropdown,
                ft.Row([start_date_field, start_cal_btn]),
                ft.Row([end_date_field, end_cal_btn]),
                order_input,
                cust_input,
                ft.Button("🔍 查询", on_click=on_search),
                ft.Button("🔄 重置", on_click=on_reset),
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=8,
            wrap=True,
        )
        title_row = ft.Row(
            [
                ft.Text("🔧 安装任务", size=20, weight=ft.FontWeight.BOLD),
                ft.TextButton("🔄", on_click=lambda e: load_install(), tooltip="刷新"),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        main_content.controls.append(
            ft.Column(
                [
                    title_row,
                    query_row,
                    install_list,
                ],
                spacing=10,
            )
        )
        load_install()

    # ---------------------------- 库存管理 ----------------------------

    def show_stock_detail(model):
        conn = get_db_conn()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("SELECT factory, spec, qty FROM stock_now WHERE model=%s", (model,))
        row = cur.fetchone()
        conn.close()
        if not row:
            show_alert(page, "提示", "未找到该型号库存信息")
            return
        factory, spec, qty = row
        qty = qty or 0

        start_date_field = ft.TextField(
            label="起始日期",
            width=None,
            expand=True,
            value=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
            text_size=13,
            dense=True
        )
        end_date_field = ft.TextField(
            label="结束日期",
            width=None,
            expand=True,
            value=datetime.now().strftime("%Y-%m-%d"),
            text_size=13,
            dense=True
        )

        # 修复日期选择器日期偏移一天问题
        def pick_date(field):
            def on_date_selected(e):
                if e.control.value:
                    real_local_date = e.control.value + timedelta(days=1)
                    field.value = real_local_date.strftime("%Y-%m-%d")
                    page.update()

            picker = ft.DatePicker(on_change=on_date_selected)
            page.overlay.append(picker)
            picker.open = True
            page.update()

        start_icon = ft.TextButton("📅", on_click=lambda e: pick_date(start_date_field),
                                   style=ft.ButtonStyle(padding=ft.Padding(2, 2, 2, 2)))
        end_icon = ft.TextButton("📅", on_click=lambda e: pick_date(end_date_field),
                                 style=ft.ButtonStyle(padding=ft.Padding(2, 2, 2, 2)))

        # 入库表格：入库日期、数量、库位
        in_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("入库日期", size=13)),
                ft.DataColumn(ft.Text("数量", size=13)),
                ft.DataColumn(ft.Text("库位", size=13)),
            ],
            rows=[],
            expand=True,
            data_row_min_height=32,
            heading_row_height=36,
            column_spacing=8
        )

        # 销售表格极致紧凑优化
        sale_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("状态", size=12)),
                ft.DataColumn(ft.Text("订单号", size=12)),
                ft.DataColumn(ft.Text("日期", size=12)),
                ft.DataColumn(ft.Text("客户", size=12)),
                ft.DataColumn(ft.Text("数量", size=12)),
            ],
            rows=[],
            expand=True,
            data_row_min_height=28,
            heading_row_height=34,
            column_spacing=4
        )

        stat_label = ft.Text(
            "",
            size=13,
            weight=ft.FontWeight.BOLD,
            color="#d946ef",
            text_align=ft.TextAlign.CENTER
        )

        def load_detail_data(model, start, end):
            in_table.rows.clear()
            sale_table.rows.clear()
            conn = get_db_conn()
            if not conn:
                return
            cur = conn.cursor()

            # 入库数据读取
            cur.execute("""
                SELECT in_date, qty, location
                FROM stock_in
                WHERE model=%s AND in_date BETWEEN %s AND %s
                ORDER BY in_date DESC
            """, (model, start, end))
            in_total_qty = 0
            for r in cur.fetchall():
                in_date, qty, location = r
                in_total_qty += qty
                display_date = ""
                if in_date:
                    if isinstance(in_date, str):
                        display_date = datetime.strptime(in_date, "%Y-%m-%d").strftime("%m-%d")
                    else:
                        display_date = in_date.strftime("%m-%d")

                in_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(display_date, size=12)),
                        ft.DataCell(ft.Text(str(qty), size=12)),
                        ft.DataCell(ft.Text(location or "", size=12)),
                    ])
                )

            # 销售数据读取
            cur.execute("""
                SELECT DISTINCT
                    IFNULL(t.status, '未配送'),
                    si.order_no,
                    m.order_date,
                    m.cust_name,
                    si.qty
                FROM sale_items si
                LEFT JOIN sale_main m ON si.order_no = m.order_no
                LEFT JOIN transport t ON si.order_no = t.order_no AND si.model = t.model
                WHERE si.model=%s AND m.order_date BETWEEN %s AND %s
                ORDER BY m.order_date DESC
            """, (model, start, end))
            sale_total_qty = 0
            for r in cur.fetchall():
                status, order_no, order_date, cust_name, qty = r
                sale_total_qty += qty
                display_sale_date = ""
                if order_date:
                    if isinstance(order_date, str):
                        display_sale_date = datetime.strptime(order_date, "%Y-%m-%d").strftime("%m-%d")
                    else:
                        display_sale_date = order_date.strftime("%m-%d")

                sale_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(status or "", size=11)),
                        ft.DataCell(ft.Text(order_no or "", size=11)),
                        ft.DataCell(ft.Text(display_sale_date, size=11)),
                        ft.DataCell(ft.Text(cust_name or "", size=11)),
                        ft.DataCell(ft.Text(str(qty), size=11)),
                    ])
                )
            conn.close()

            stat_label.value = f"入库合计：{in_total_qty} 件 | 销售合计：{sale_total_qty} 件"
            page.update()

        load_detail_data(model, start_date_field.value, end_date_field.value)

        # 查询条件竖向排布
        filter_area = ft.Column(
            [
                ft.Row([start_date_field, start_icon], spacing=3),
                ft.Row([end_date_field, end_icon], spacing=3),
                ft.Row(
                    [ft.Button("查询", expand=True)],
                    alignment=ft.MainAxisAlignment.CENTER
                )
            ],
            spacing=6
        )

        # 入库区域
        in_block = ft.Column(
            [
                ft.Text("入库记录", weight=ft.FontWeight.BOLD, size=14),
                ft.Divider(height=1),
                ft.Column(
                    [in_table],
                    height=240,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True
                )
            ],
            spacing=4
        )

        # 销售记录整体极致紧凑
        sale_block = ft.Column(
            [
                ft.Text("销售记录", weight=ft.FontWeight.BOLD, size=14),
                ft.Divider(height=1),
                ft.Column(
                    [sale_table],
                    height=240,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True
                )
            ],
            spacing=3
        )

        # 整体竖向布局
        main_content = ft.Column(
            [
                ft.Text(f"型号：{model}  理论库存：{qty}", size=15, weight=ft.FontWeight.BOLD, color="red"),
                ft.Divider(height=1),
                filter_area,
                ft.Divider(height=1),
                in_block,
                ft.Divider(height=1),
                sale_block,
                ft.Divider(height=1),
                stat_label
            ],
            spacing=8,
            expand=True,
            scroll=ft.ScrollMode.AUTO
        )

        dlg = ft.AlertDialog(
            title=ft.Text("库存进销详情", size=16),
            content=main_content,
            inset_padding=ft.Padding(8, 8, 8, 8),
            actions=[
                ft.Button("关闭", expand=True,
                          on_click=lambda e: (setattr(dlg, 'open', False), safe_remove_dialog(page, dlg)))
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def show_stock():
        main_content.controls.clear()
        w1 = get_field_width(page, ratio=2, subtract=60)
        brand_dropdown = ft.Dropdown(
            label="品牌",
            width=w1,
            options=[ft.dropdown.Option("")],
            value="",
        )
        model_textfield = ft.TextField(
            label="型号",
            width=w1,
            hint_text="模糊搜索",
        )
        gap_checkbox = ft.Checkbox(label="仅显示缺口", value=False)

        def load_brands():
            conn = get_db_conn()
            if not conn:
                return
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT factory FROM base_product ORDER BY factory")
            brands = [row[0] for row in cur.fetchall()]
            conn.close()
            brand_dropdown.options = [ft.dropdown.Option("")] + [ft.dropdown.Option(b) for b in brands]
            page.update()
        load_brands()

        stock_list = ft.Column(spacing=5)

        def load_stock():
            stock_list.controls.clear()
            conn = get_db_conn()
            if not conn:
                return
            brand = brand_dropdown.value.strip() if brand_dropdown.value else ""
            model = model_textfield.value.strip()
            only_gap = gap_checkbox.value
            cur = conn.cursor()
            cur.execute("""
                SELECT model, IFNULL(SUM(t_qty), 0)
                FROM transport
                WHERE status IN ('待派单', '待出库')
                GROUP BY model
            """)
            wait_out_dict = {row[0]: row[1] for row in cur.fetchall()}
            cur.execute("""
                SELECT model, COUNT(*)
                FROM booth
                WHERE is_real = 1 AND status = '上样中'
                GROUP BY model
            """)
            booth_dict = {row[0]: row[1] for row in cur.fetchall()}
            sql = "SELECT IFNULL(factory, ''), IFNULL(model, ''), IFNULL(spec, ''), IFNULL(qty, 0) FROM stock_now WHERE 1=1"
            params = []
            if brand:
                sql += " AND factory = %s"
                params.append(brand)
            if model:
                sql += " AND model LIKE %s"
                params.append(f"%{model}%")
            sql += " ORDER BY factory, model"
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()
            has_data = False
            for row in rows:
                factory, model_name, spec, qty = row
                if not model_name:
                    model_name = "未知型号"
                qty = qty if qty is not None else 0
                wait_out = wait_out_dict.get(model_name, 0)
                booth_use = booth_dict.get(model_name, 0)
                s_qty = qty + wait_out - booth_use
                if only_gap and qty >= 0:
                    continue
                has_data = True
                q_qty_display = abs(int(qty)) if qty < 0 else ""
                if qty < 0:
                    status = "⚠️ 存在缺口"
                    color = "#ff0000"
                elif s_qty == 0:
                    status = "❌ 无库存"
                    color = "#94a3b8"
                elif s_qty < 5:
                    status = "⚠️ 库存不足"
                    color = "#ef4444"
                elif s_qty < 20:
                    status = "🟢 正常"
                    color = "#22c55e"
                else:
                    status = "✅ 充足"
                    color = "#22c55e"
                if model_name in booth_dict:
                    status += " 有样机"
                card = ft.Card(
                    content=ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(model_name, weight=ft.FontWeight.BOLD, size=16),
                                        ft.Text(f"品牌: {factory} | 规格: {spec}", size=12, color="#64748b"),
                                        ft.Text(f"理论: {qty} | 实际: {s_qty} | 缺口: {q_qty_display}", size=12),
                                        ft.Text(status, size=12, color=color),
                                    ],
                                    spacing=2,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=10,
                        on_click=lambda e, m=model_name: show_stock_detail(m),
                    )
                )
                stock_list.controls.append(card)
            if not has_data:
                stock_list.controls.append(ft.Text("没有符合条件的库存", size=14, color="#94a3b8"))
            page.update()

        def on_search(e):
            load_stock()
        def on_refresh(e):
            load_brands()
            load_stock()

        query_row = ft.Row(
            [
                brand_dropdown,
                model_textfield,
                gap_checkbox,
                ft.Button("查询", on_click=on_search),
                ft.TextButton("🔄", on_click=on_refresh, tooltip="刷新"),
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=10,
            wrap=True,
        )
        main_content.controls.append(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("实时库存", size=20, weight=ft.FontWeight.BOLD),
                            ft.TextButton("🔄", on_click=lambda e: load_stock()),
                        ]
                    ),
                    query_row,
                    stock_list,
                ],
                spacing=10,
            )
        )
        load_stock()

    def show_more_menu():
        main_content.controls.clear()
        menu_items = ft.Column([
            ft.ListTile(title=ft.Text("产品档案"), leading=ft.Icon(ft.Icons.CATEGORY), on_click=lambda e: show_products()),
            ft.ListTile(title=ft.Text("客户档案"), leading=ft.Icon(ft.Icons.PEOPLE), on_click=lambda e: show_customers()),
            ft.ListTile(title=ft.Text("发票管理"), leading=ft.Icon(ft.Icons.RECEIPT), on_click=lambda e: show_invoice()),
            ft.ListTile(title=ft.Text("补贴申报"), leading=ft.Icon(ft.Icons.MONEY), on_click=lambda e: show_subsidy()),
            ft.ListTile(title=ft.Text("财务管理"), leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE), on_click=lambda e: show_finance()),
            ft.ListTile(title=ft.Text("入库记录查询"), leading=ft.Icon(ft.Icons.HISTORY), on_click=lambda e: show_inbound_records()),
            ft.ListTile(title=ft.Text("销售订单查询"), leading=ft.Icon(ft.Icons.SEARCH), on_click=lambda e: show_sale_orders()),
            ft.ListTile(title=ft.Text("展台样机"), leading=ft.Icon(ft.Icons.DISPLAY_SETTINGS), on_click=lambda e: show_booth()),
            ft.ListTile(title=ft.Text("用户管理"), leading=ft.Icon(ft.Icons.SUPERVISOR_ACCOUNT), on_click=lambda e: show_user_manager()) if current_user and current_user["role"] == "超级管理员" else ft.Container()
        ])
        main_content.controls.append(menu_items)
        page.update()

    # ---------------------------- 产品档案 ----------------------------
    def show_products():
        def load_products():
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT model, factory, spec, price FROM base_product ORDER BY model")
            rows = cur.fetchall()
            conn.close()
            products_list.controls.clear()
            for row in rows:
                products_list.controls.append(
                    ft.Card(content=ft.Container(
                        content=ft.Column([
                            ft.Text(row[0], weight=ft.FontWeight.BOLD),
                            ft.Text(f"品牌: {row[1]} | 规格: {row[2]} | 价格: {row[3]}", size=12)
                        ], spacing=2), padding=10)))
            page.update()
        products_list = ft.Column(spacing=5)
        main_content.controls.clear()
        main_content.controls.append(ft.Column([
            ft.Row([ft.Text("产品档案", size=20, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_products())]),
            products_list], scroll=ft.ScrollMode.AUTO))
        load_products()

    # ---------------------------- 客户档案 ----------------------------
    def show_customers():
        def load_customers():
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT name, phone, full_addr, total_amount FROM base_customer ORDER BY total_amount DESC")
            rows = cur.fetchall()
            conn.close()
            customers_list.controls.clear()
            for row in rows:
                customers_list.controls.append(
                    ft.Card(content=ft.Container(
                        content=ft.Column([
                            ft.Text(row[0], weight=ft.FontWeight.BOLD),
                            ft.Text(f"电话: {row[1]}", size=12),
                            ft.Text(f"地址: {row[2]}", size=12),
                            ft.Text(f"累计消费: {row[3]} 元", size=12, color=ft.Colors.GREEN)
                        ], spacing=2), padding=10)))
            page.update()
        customers_list = ft.Column(spacing=5)
        main_content.controls.clear()
        main_content.controls.append(ft.Column([
            ft.Row([ft.Text("客户档案", size=20, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_customers())]),
            customers_list], scroll=ft.ScrollMode.AUTO))
        load_customers()

    # ---------------------------- 发票管理 ----------------------------
    def show_invoice():
        main_content.controls.clear()
        invoice_list = ft.Column(spacing=5)
        def load_invoice():
            invoice_list.controls.clear()
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT invoice_no, order_no, cust_name, invoice_amount, invoice_date, status FROM invoice ORDER BY invoice_date DESC")
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                invoice_list.controls.append(
                    ft.Card(content=ft.Container(
                        content=ft.Column([
                            ft.Text(f"发票号: {row[0]}", weight=ft.FontWeight.BOLD),
                            ft.Text(f"订单: {row[1]}  客户: {row[2]}"),
                            ft.Text(f"金额: {row[3]}  日期: {row[4]}  状态: {row[5]}", size=12)
                        ], spacing=2), padding=10)))
            page.update()

        def new_invoice():
            def select_order(e):
                order_no = order_dropdown.value
                if not order_no: return
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("SELECT SUM(total) FROM sale_items WHERE order_no=%s", (order_no,))
                total = cur.fetchone()[0] or 0
                conn.close()
                invoice_no = gen_invoice_no()
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("""INSERT INTO invoice (invoice_no, order_no, cust_name, invoice_amount, invoice_date, status, invoice_type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                            (invoice_no, order_no, "客户名", total, date.today(), "已开票", "电子发票"))
                conn.commit()
                conn.close()
                dialog.open = False
                safe_remove_dialog(page, dialog)
                show_alert(page, "提示", f"发票 {invoice_no} 开具成功")
                load_invoice()
                page.update()

            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT order_no FROM sale_main WHERE order_no NOT IN (SELECT order_no FROM invoice)")
            orders = [row[0] for row in cur.fetchall()]
            conn.close()
            order_dropdown = ft.Dropdown(label="选择订单", options=[ft.dropdown.Option(o) for o in orders], width=300)
            dialog = ft.AlertDialog(
                title=ft.Text("开具新发票"),
                content=order_dropdown,
                actions=[ft.TextButton("确认", on_click=select_order), ft.TextButton("取消", on_click=lambda e: (setattr(dialog, 'open', False), safe_remove_dialog(page, dialog)))]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        main_content.controls.append(
            ft.Column([
                ft.Row([ft.Text("发票管理", size=20, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.ADD, on_click=lambda e: new_invoice()), ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_invoice())]),
                invoice_list], scroll=ft.ScrollMode.AUTO))
        load_invoice()

    # ---------------------------- 补贴申报 ----------------------------
    def show_subsidy():
        main_content.controls.clear()
        subsidy_list = ft.Column(spacing=5)
        def load_subsidy():
            subsidy_list.controls.clear()
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT claim_no, order_no, cust_name, claim_amount, status FROM subsidy_claim ORDER BY claim_date DESC")
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                subsidy_list.controls.append(
                    ft.Card(content=ft.Container(
                        content=ft.Column([
                            ft.Text(f"申报单: {row[0]}", weight=ft.FontWeight.BOLD),
                            ft.Text(f"订单: {row[1]}  客户: {row[2]}"),
                            ft.Text(f"金额: {row[3]}  状态: {row[4]}", size=12)
                        ], spacing=2), padding=10)))
            page.update()

        def new_subsidy():
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT order_no FROM sale_main WHERE order_no NOT IN (SELECT order_no FROM subsidy_claim)")
            orders = [row[0] for row in cur.fetchall()]
            conn.close()
            if not orders:
                show_alert(page, "提示", "没有可申报的订单")
                return
            order_dropdown = ft.Dropdown(label="选择订单", options=[ft.dropdown.Option(o) for o in orders], width=300)
            def do_create(e):
                order_no = order_dropdown.value
                if not order_no: return
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("SELECT cust_name, card_no, SUM(total) FROM sale_items JOIN sale_main USING(order_no) WHERE order_no=%s", (order_no,))
                cust_name, card_no, total = cur.fetchone()
                claim_no = f"CLM{date.today().strftime('%Y%m%d')}{int(datetime.now().timestamp()) % 10000:04d}"
                cur.execute("""INSERT INTO subsidy_claim (claim_no, order_no, cust_name, card_no, claim_amount, claim_date, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                            (claim_no, order_no, cust_name, card_no, total, date.today(), "待申报"))
                conn.commit()
                conn.close()
                dialog.open = False
                safe_remove_dialog(page, dialog)
                show_alert(page, "提示", f"申报单 {claim_no} 创建成功")
                load_subsidy()
                page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("新建补贴申报"),
                content=order_dropdown,
                actions=[ft.TextButton("确认", on_click=do_create), ft.TextButton("取消", on_click=lambda e: (setattr(dialog, 'open', False), safe_remove_dialog(page, dialog)))]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        main_content.controls.append(
            ft.Column([
                ft.Row([ft.Text("补贴申报", size=20, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.ADD, on_click=lambda e: new_subsidy()), ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_subsidy())]),
                subsidy_list], scroll=ft.ScrollMode.AUTO))
        load_subsidy()

    # ---------------------------- 财务管理 ----------------------------
    def show_finance():
        main_content.controls.clear()
        year_dd = ft.Dropdown(label="年份", options=[ft.dropdown.Option(str(y)) for y in range(2023, 2035)], value=str(date.today().year))
        month_dd = ft.Dropdown(label="月份", options=[ft.dropdown.Option(f"{m:02d}") for m in range(1,13)], value=f"{date.today().month:02d}")
        result_text = ft.Text("", selectable=True)

        def calc_finance(e):
            year = year_dd.value
            month = month_dd.value
            prefix = f"{year}-{month}"
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT IFNULL(SUM(total),0) FROM sale_items JOIN sale_main USING(order_no) WHERE DATE_FORMAT(order_date,'%Y-%m')=%s", (prefix,))
            sale_total = cur.fetchone()[0] or 0
            cur.execute("SELECT IFNULL(SUM(qty*in_price),0) FROM stock_in WHERE DATE_FORMAT(in_date,'%Y-%m')=%s", (prefix,))
            in_cost = cur.fetchone()[0] or 0
            cur.execute("SELECT IFNULL(SUM(amount),0) FROM operate_cost WHERE DATE_FORMAT(cost_date,'%Y-%m')=%s", (prefix,))
            op_cost = cur.fetchone()[0] or 0
            cur.execute("SELECT IFNULL(SUM(install_fee),0) FROM install WHERE DATE_FORMAT(install_date,'%Y-%m')=%s AND status='已安装'", (prefix,))
            inst_fee = cur.fetchone()[0] or 0
            profit = sale_total - in_cost - op_cost - inst_fee
            result_text.value = f"""📅 {year}年{int(month)}月财务统计
销售额: {sale_total:.2f}
进货成本: {in_cost:.2f}
运营成本: {op_cost:.2f}
安装费用: {inst_fee:.2f}
净利润: {profit:.2f}"""
            page.update()
            conn.close()

        main_content.controls.append(
            ft.Column([
                ft.Text("财务报表", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([year_dd, month_dd]),
                ft.Button("计算", icon=ft.Icons.CALCULATE, on_click=calc_finance),
                ft.Card(content=ft.Container(content=result_text, padding=15))
            ], spacing=15))
        page.update()

    # ---------------------------- 入库记录查询 ----------------------------

    def show_inbound_records():
        main_content.controls.clear()
        w1 = get_field_width(page, ratio=2, subtract=60)

        # 默认显示一个月内
        default_start = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        default_end = date.today().strftime("%Y-%m-%d")

        start_date_field = ft.TextField(
            label="起始日期",
            width=w1,
            value=default_start,
            read_only=True,
        )
        end_date_field = ft.TextField(
            label="结束日期",
            width=w1,
            value=default_end,
            read_only=True,
        )

        brand = ft.TextField(label="品牌", width=w1)
        model = ft.TextField(label="型号", width=w1)
        price_switch = ft.Switch(label="价格维护模式（仅显示空/0价格）", value=False)

        query_btn = ft.Button("查询", icon=ft.Icons.SEARCH)
        results_list = ft.Column(spacing=5)
        total_label = ft.Text("", size=14)

        # 标准日期选择弹窗
        def pick_date(target_field: ft.TextField):
            def on_date_selected(e):
                if e.control.value:
                    # 补上东八区8小时时差，解决选中日期少一天
                    local_fix_dt = e.control.value + timedelta(hours=8)
                    target_field.value = local_fix_dt.strftime("%Y-%m-%d")
                    page.update()
                page.pop_dialog()

            picker = ft.DatePicker(on_change=on_date_selected)
            page.show_dialog(picker)

        start_cal_btn = ft.TextButton("📅", on_click=lambda e: pick_date(start_date_field))
        end_cal_btn = ft.TextButton("📅", on_click=lambda e: pick_date(end_date_field))

        def open_edit_dialog(row):
            # ========== 优化开始 ==========
            # 1. 移除 ID 字段（不再显示）
            # 2. 品牌和品类一行，型号单独一行，入库日期单独一行，数量和价格一行
            # 3. 控制弹窗宽度（约260）和高度（约260），高度减半
            factory_field = ft.TextField(
                label="品牌",
                value=row[1],
                read_only=True,
                width=85,
                bgcolor=ft.Colors.GREY_200,
            )
            category_field = ft.TextField(
                label="品类",
                value=row[2],
                read_only=True,
                width=85,
                bgcolor=ft.Colors.GREY_200,
            )
            model_field = ft.TextField(
                label="型号",
                value=row[3],
                read_only=True,
                width=180,
                bgcolor=ft.Colors.GREY_200,
            )
            in_date_field = ft.TextField(
                label="入库日期",
                value=str(row[6]),  # row[6] 为 in_date
                read_only=True,
                width=180,
                bgcolor=ft.Colors.GREY_200,
            )

            # 可编辑字段（默认白色背景）
            qty_field = ft.TextField(label="数量", value=str(row[4]), width=85)
            price_field = ft.TextField(
                label="入库价格",
                value="" if row[5] is None else str(row[5]),
                width=85,
            )

            edit_dialog = ft.AlertDialog(
                title=ft.Text("修改入库记录"),
                content=ft.Container(
                    width=260,  # 固定宽度，与单列字段宽度基本一致
                    height=240,  # 固定高度，约为原来的一半
                    content=ft.Column(
                        [
                            ft.Row([factory_field, category_field], spacing=10),
                            model_field,
                            in_date_field,
                            ft.Row([qty_field, price_field], spacing=10),
                        ],
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO,  # 防止内容溢出时无法操作
                    ),
                ),
                actions=[],
            )

            # ========== 优化结束 ==========

            def close_edit(e=None):
                edit_dialog.open = False
                safe_remove_dialog(page, edit_dialog)
                page.update()

            def save(e):
                qty_text = qty_field.value.strip()
                price_text = price_field.value.strip()

                if not qty_text:
                    show_snack(page,"数量不能为空",ft.Colors.RED)
                    return

                try:
                    qty_val = int(qty_text)
                    price_val = float(price_text) if price_text else 0.0
                except ValueError:
                    show_snack(page,"请输入有效数字",ft.Colors.RED)
                    return

                conn = get_db_conn()
                if not conn:
                    return
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE stock_in SET qty=%s, in_price=%s WHERE id=%s",
                        (qty_val, price_val, row[0]),
                    )
                    conn.commit()
                finally:
                    conn.close()

                close_edit()
                show_snack(page,"修改已保存",ft.Colors.RED)
                do_query(None)

            def delete(e):
                def do_delete(e):
                    conn = get_db_conn()
                    if not conn:
                        return
                    try:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM stock_in WHERE id=%s", (row[0],))
                        conn.commit()
                    finally:
                        conn.close()

                    confirm_dialog.open = False
                    safe_remove_dialog(page, confirm_dialog)
                    close_edit()
                    show_snack(page,"记录已删除",ft.Colors.RED)
                    do_query(None)

                confirm_dialog = ft.AlertDialog(
                    title=ft.Text("确认删除"),
                    content=ft.Text(f"确定要删除记录 ID:{row[0]} 吗？此操作不可恢复。"),
                    actions=[
                        ft.TextButton(
                            "取消",
                            on_click=lambda e: (
                                setattr(confirm_dialog, "open", False),
                                safe_remove_dialog(page, confirm_dialog),
                                page.update(),
                            ),
                        ),
                        ft.TextButton("删除", on_click=do_delete),
                    ],
                )
                page.overlay.append(confirm_dialog)
                confirm_dialog.open = True
                page.update()

            edit_dialog.actions = [
                ft.Row(
                    controls=[
                        ft.TextButton("保存", on_click=save),
                        ft.TextButton("删除", on_click=delete),
                        ft.TextButton("取消", on_click=close_edit),
                    ],
                    alignment=ft.MainAxisAlignment.END,  # 靠右显示
                    spacing=8,
                )
            ]

            page.overlay.append(edit_dialog)
            edit_dialog.open = True
            page.update()

        def show_detail(row):
            detail_text = f"""入库详情
    ID: {row[0]}
    品牌: {row[1]}
    品类: {row[2]}
    型号: {row[3]}
    数量: {row[4]}
    单价: {row[5] if row[5] is not None else '未维护'}
    日期: {row[6]}"""

            detail_dialog = ft.AlertDialog(
                title=ft.Text("入库明细"),
                content=ft.Text(detail_text),
                actions=[],
            )

            def close_detail(e=None):
                detail_dialog.open = False
                safe_remove_dialog(page, detail_dialog)
                page.update()

            def go_edit(e):
                close_detail()
                open_edit_dialog(row)

            detail_dialog.actions = [
                ft.TextButton("修改", on_click=go_edit),
                ft.TextButton("关闭", on_click=close_detail),
            ]

            page.overlay.append(detail_dialog)
            detail_dialog.open = True
            page.update()

        def do_query(e):
            results_list.controls.clear()

            conn = get_db_conn()
            if not conn:
                return
            cur = conn.cursor()

            sql = "SELECT id, factory, category, model, qty, in_price, in_date FROM stock_in WHERE 1=1"
            params = []

            if price_switch.value:
                # 价格维护模式：忽略日期，查询所有空价格或 0 价格记录
                sql += " AND (in_price IS NULL OR in_price = 0)"
            else:
                if start_date_field.value:
                    sql += " AND in_date >= %s"
                    params.append(start_date_field.value)
                if end_date_field.value:
                    sql += " AND in_date <= %s"
                    params.append(end_date_field.value)

            if brand.value:
                sql += " AND factory LIKE %s"
                params.append(f"%{brand.value}%")
            if model.value:
                sql += " AND model LIKE %s"
                params.append(f"%{model.value}%")

            sql += " ORDER BY in_date DESC"
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()

            total_qty = 0
            total_amt = 0.0
            for row in rows:
                qty = int(row[4])
                price = float(row[5]) if row[5] is not None else 0.0
                total_qty += qty
                total_amt += qty * price

                price_display = row[5] if row[5] is not None else "未维护"
                results_list.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        f"{row[2]} | {row[1]}  {row[3]}",
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        f"数量: {row[4]}  单价: {price_display}  日期: {row[6]}"
                                    ),
                                ],
                                spacing=2,
                            ),
                            padding=8,
                            # 关键修改：价格维护模式下直接打开编辑弹窗
                            on_click=lambda e, r=row: (
                                open_edit_dialog(r) if price_switch.value else show_detail(r)
                            ),
                        )
                    )
                )

            mode_tip = "（价格维护模式）" if price_switch.value else ""
            total_label.value = f"总数量: {total_qty}  总金额: {total_amt:.2f} {mode_tip}"
            page.update()

        query_btn.on_click = do_query

        main_content.controls.append(
            ft.Column(
                [
                    ft.Text("入库记录查询", size=20, weight=ft.FontWeight.BOLD),
                    ft.Row([start_date_field, start_cal_btn], alignment=ft.MainAxisAlignment.START),
                    ft.Row([end_date_field, end_cal_btn], alignment=ft.MainAxisAlignment.START),
                    ft.Row([brand, model], alignment=ft.MainAxisAlignment.START),
                    ft.Row([price_switch], alignment=ft.MainAxisAlignment.START),
                    query_btn,
                    total_label,
                    results_list,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            )
        )
        page.update()

        # 自动执行一次默认查询
        do_query(None)

    # ---------------------------- 销售订单查询（简版） ----------------------------
    # ========== 电话操作弹窗 ==========
    def show_phone_dialog(phone_number: str):
        """弹出拨号/短信选择对话框"""
        clean_number = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

        async def make_call(e):
            dialog.open = False
            page.update()
            await ft.UrlLauncher().launch_url(f"tel:{clean_number}")

        async def send_sms(e):
            dialog.open = False
            page.update()
            await ft.UrlLauncher().launch_url(f"sms:{clean_number}")

        def close_dialog(e):
            dialog.open = False
            page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("选择操作"),
            content=ft.Text(f"电话号码：{phone_number}"),
            actions=[
                ft.TextButton("拨打电话", icon=ft.Icons.CALL, on_click=make_call),
                ft.TextButton("发送短信", icon=ft.Icons.SMS, on_click=send_sms),
                ft.TextButton("取消", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # ========== 订单明细展示 ==========
    def show_order_detail(order_no):
        conn = get_db_conn()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("""
            SELECT m.order_no, m.order_date, m.cust_name, m.phone, m.full_addr, i.model, i.qty, i.total 
            FROM sale_main m JOIN sale_items i ON m.order_no=i.order_no 
            WHERE m.order_no=%s
        """, (order_no,))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            show_alert(page, "提示", "未找到明细")
            page.update()
            return

        order_info = rows[0]
        phone = order_info[3]

        # 构建详情内容列，支持滚动
        content_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

        content_column.controls.append(ft.Text(f"订单号: {order_info[0]}", weight=ft.FontWeight.BOLD))
        content_column.controls.append(ft.Text(f"日期: {order_info[1]}"))
        content_column.controls.append(ft.Text(f"客户: {order_info[2]}"))

        # 可点击的电话号码
        phone_button = ft.TextButton(
            content=ft.Text(
                f"电话: {phone}" if phone else "电话: 无",
                color=ft.Colors.BLUE,
                weight=ft.FontWeight.BOLD,
            ),
            on_click=lambda e: show_phone_dialog(phone) if phone else None,
        )
        content_column.controls.append(phone_button)

        content_column.controls.append(ft.Text(f"地址: {order_info[4]}"))
        content_column.controls.append(ft.Text("商品明细:", weight=ft.FontWeight.BOLD))

        for r in rows:
            content_column.controls.append(
                ft.Text(f"型号: {r[5]}  数量: {r[6]}  金额: {r[7]:.2f}")
            )

        # 固定高度容器，实现滚动
        scrollable_content = ft.Container(
            content=content_column,
            height=400,
            width=450,
            padding=10,
        )

        def close_detail(e=None):
            dialog.open = False
            safe_remove_dialog(page, dialog)
            page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("订单明细"),
            content=scrollable_content,
            actions=[
                ft.TextButton("关闭", on_click=close_detail),
            ],
        )

        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    # ========== 销售订单查询主界面 ==========
    def show_sale_orders():
        main_content.controls.clear()
        w1 = get_field_width(page, ratio=2, subtract=60)
        start_date = ft.TextField(label="起始日期", width=w1)
        end_date = ft.TextField(label="结束日期", width=w1)
        order_no = ft.TextField(label="订单号", width=w1)
        cust_name = ft.TextField(label="客户", width=w1)
        model = ft.TextField(label="型号", width=w1)
        query_btn = ft.Button("查询", icon=ft.Icons.SEARCH)
        orders_list = ft.Column(spacing=5)

        def do_query(e):
            orders_list.controls.clear()
            conn = get_db_conn()
            if not conn:
                return
            cur = conn.cursor()
            sql = """SELECT m.order_no, m.order_date, m.cust_name, m.phone, SUM(i.total) as total
                     FROM sale_main m JOIN sale_items i ON m.order_no=i.order_no WHERE 1=1"""
            params = []
            if start_date.value:
                sql += " AND m.order_date >= %s"
                params.append(start_date.value)
            if end_date.value:
                sql += " AND m.order_date <= %s"
                params.append(end_date.value)
            if order_no.value:
                sql += " AND m.order_no LIKE %s"
                params.append(f"%{order_no.value}%")
            if cust_name.value:
                sql += " AND m.cust_name LIKE %s"
                params.append(f"%{cust_name.value}%")
            if model.value:
                sql += " AND i.model LIKE %s"
                params.append(f"%{model.value}%")
            sql += " GROUP BY m.order_no ORDER BY m.order_date DESC"
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                orders_list.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(f"订单号: {row[0]}  日期: {row[1]}", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"客户: {row[2]}  电话: {row[3]}  金额: {row[4]:.2f}")
                                ],
                                spacing=2,
                            ),
                            padding=8,
                            on_click=lambda e, order=row[0]: show_order_detail(order)
                        )
                    )
                )
            page.update()

        query_btn.on_click = do_query

        main_content.controls.append(
            ft.Column(
                [
                    ft.Text("销售订单查询", size=20, weight=ft.FontWeight.BOLD),
                    ft.Row([start_date, end_date], alignment=ft.MainAxisAlignment.START),
                    ft.Row([order_no, cust_name], alignment=ft.MainAxisAlignment.START),
                    ft.Row([model], alignment=ft.MainAxisAlignment.START),
                    query_btn,
                    orders_list
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            )
        )
        page.update()

    # ---------------------------- 展台样机 ----------------------------
    def show_booth():
        main_content.controls.clear()
        booth_grid = ft.GridView(expand=1, runs_count=2, max_extent=200, child_aspect_ratio=0.8, spacing=10)

        def load_booth():
            booth_grid.controls.clear()
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, factory, category, model, price, is_real, feature, after_sales, p_website, on_price, on_date FROM booth WHERE status='上样中'")
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                booth_grid.controls.append(
                    ft.Card(content=ft.Container(
                        content=ft.Column([
                            ft.Text(row[3], weight=ft.FontWeight.BOLD, size=14),
                            ft.Text(f"{row[1]} | {row[2]}", size=11),
                            ft.Text(f"备案价: {row[4]}", size=11),
                            ft.Text(f"实机: {'是' if row[5] else '否'}", size=11),
                            ft.Row([
                                ft.IconButton(ft.Icons.EDIT, on_click=lambda e, rid=row[0]: edit_booth(rid)),
                                ft.IconButton(ft.Icons.DELETE, on_click=lambda e, rid=row[0]: remove_booth(rid))
                            ])
                        ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=8)))
            page.update()

        def edit_booth(booth_id):
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT factory, category, model, price, is_real, feature, after_sales, p_website, on_price, on_date FROM booth WHERE id=%s", (booth_id,))
            row = cur.fetchone()
            conn.close()
            if not row: return
            factory, category, model, price, is_real, feature, after_sales, p_website, on_price, on_date = row
            factory_in = ft.TextField(label="品牌", value=factory, width=200)
            category_in = ft.TextField(label="品类", value=category, width=200)
            model_in = ft.TextField(label="型号", value=model, width=200, read_only=True)
            price_in = ft.TextField(label="备案价", value=str(price), width=200)
            is_real_in = ft.Dropdown(label="实机与否", options=[ft.dropdown.Option("是"), ft.dropdown.Option("否")], value="是" if is_real else "否", width=200)
            feature_in = ft.TextField(label="特点", value=feature or "", width=200)
            after_in = ft.TextField(label="售后", value=after_sales or "", width=200)
            web_in = ft.TextField(label="官网", value=p_website or "", width=200)
            online_price_in = ft.TextField(label="线上价", value=str(on_price or 0), width=200)
            on_date_in = ft.TextField(label="上样日期", value=str(on_date), width=200)

            def save_edit(e):
                new_factory = factory_in.value.strip()
                new_category = category_in.value.strip()
                new_price = float(price_in.value or 0)
                new_is_real = 1 if is_real_in.value == "是" else 0
                new_feature = feature_in.value
                new_after = after_in.value
                new_web = web_in.value
                new_online = float(online_price_in.value or 0)
                new_date = on_date_in.value
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("""UPDATE booth SET factory=%s, category=%s, price=%s, is_real=%s, feature=%s,
                                after_sales=%s, p_website=%s, on_price=%s, on_date=%s, update_time=NOW()
                                WHERE id=%s""",
                            (new_factory, new_category, new_price, new_is_real, new_feature, new_after, new_web, new_online, new_date, booth_id))
                conn.commit()
                conn.close()
                dialog.open = False
                safe_remove_dialog(page, dialog)
                show_alert(page, "提示", "样机信息已更新")
                load_booth()
                page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("编辑样机"),
                content=ft.Column([factory_in, category_in, model_in, price_in, is_real_in, feature_in, after_in, web_in, online_price_in, on_date_in],
                                  tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
                actions=[ft.TextButton("保存", on_click=save_edit), ft.TextButton("取消", on_click=lambda e: (setattr(dialog, 'open', False), safe_remove_dialog(page, dialog)))]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        def remove_booth(booth_id):
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("UPDATE booth SET status='已下样' WHERE id=%s", (booth_id,))
            conn.commit()
            conn.close()
            load_booth()
            show_alert(page, "提示", "已下样")
            page.update()

        def add_booth(e):
            model_input = ft.TextField(label="型号", width=200)
            scan_btn = ft.IconButton(ft.Icons.CAMERA_ALT, on_click=lambda ev: unified_barcode_scan(page, on_scan, title="扫码识别商品"))
            factory_input = ft.TextField(label="品牌", width=200)
            category_input = ft.TextField(label="品类", width=200)
            price_input = ft.TextField(label="备案价", value="0", width=200)
            is_real_input = ft.Dropdown(label="实机与否", options=[ft.dropdown.Option("是"), ft.dropdown.Option("否")], value="否", width=200)
            feature_input = ft.TextField(label="特点", width=200)
            after_input = ft.TextField(label="售后", width=200)
            web_input = ft.TextField(label="官网", width=200)
            online_price_input = ft.TextField(label="线上价", value="0", width=200)
            on_date_input = ft.TextField(label="上样日期", value=date.today().isoformat(), width=200)

            def on_scan(code, prod=None):
                if prod:
                    model_input.value = prod["model"]
                    factory_input.value = prod["factory"]
                    price_input.value = str(prod["price"])
                    page.update()
                else:
                    prod = query_product_by_code(code)
                    if prod:
                        model_input.value = prod["model"]
                        factory_input.value = prod["factory"]
                        price_input.value = str(prod["price"])
                        page.update()
                    else:
                        def after_add(m):
                            model_input.value = m
                            page.update()
                        add_product_from_scan(page, code, after_add)

            def save_new(e):
                model = model_input.value.strip()
                if not model:
                    show_alert(page, "提示", "型号不能为空")
                    return
                factory = factory_input.value.strip()
                category = category_input.value.strip()
                price = float(price_input.value or 0)
                is_real = 1 if is_real_input.value == "是" else 0
                feature = feature_input.value
                after = after_input.value
                web = web_input.value
                online = float(online_price_input.value or 0)
                on_date = on_date_input.value
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("""INSERT INTO booth (factory, category, model, price, is_real, feature, after_sales, p_website, on_price, on_date, update_time, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), '上样中')""",
                            (factory, category, model, price, is_real, feature, after, web, online, on_date))
                conn.commit()
                conn.close()
                dialog.open = False
                safe_remove_dialog(page, dialog)
                show_alert(page, "提示", "样机上样成功")
                load_booth()
                page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("新增样机"),
                content=ft.Column([
                    ft.Row([model_input, scan_btn], alignment=ft.MainAxisAlignment.START),
                    factory_input, category_input, price_input, is_real_input, feature_input,
                    after_input, web_input, online_price_input, on_date_input
                ], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
                actions=[ft.TextButton("保存", on_click=save_new), ft.TextButton("取消", on_click=lambda e: (setattr(dialog, 'open', False), safe_remove_dialog(page, dialog)))]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        main_content.controls.append(
            ft.Column([
                ft.Row([ft.Text("展台样机", size=20, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.ADD, on_click=add_booth), ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_booth())]),
                booth_grid
            ], scroll=ft.ScrollMode.AUTO))
        load_booth()

    # ---------------------------- 用户管理 ----------------------------
    def show_user_manager():
        if current_user and current_user.get("role") != "超级管理员":
            show_alert(page,"提示", "仅超级管理员可访问")
            return
        main_content.controls.clear()
        user_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("用户名")),
                ft.DataColumn(ft.Text("姓名")),
                ft.DataColumn(ft.Text("角色")),
                ft.DataColumn(ft.Text("有效期")),
                ft.DataColumn(ft.Text("权限")),
            ],
            rows=[],
            width=get_window_width(page) - 20,
        )

        def load_users():
            user_table.rows.clear()
            conn = get_db_conn()
            if not conn:
                show_alert(page,"错误", "数据库连接失败")
                return
            cur = conn.cursor()
            cur.execute("SELECT id, username, real_name, role, expire_date, permissions FROM users ORDER BY id")
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                user_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(row[0]))),
                            ft.DataCell(ft.Text(row[1])),
                            ft.DataCell(ft.Text(row[2] or "")),
                            ft.DataCell(ft.Text(row[3] or "")),
                            ft.DataCell(ft.Text(str(row[4]) if row[4] else "永久")),
                            ft.DataCell(ft.Text(row[5] or "")),
                        ],
                        on_select_change=lambda e, r=row: None
                    )
                )
            page.update()

        def add_user_dialog():
            username_field = ft.TextField(label="用户名", width=250)
            realname_field = ft.TextField(label="真实姓名", width=250)
            password_field = ft.TextField(label="密码", password=True, can_reveal_password=True, width=250)
            role_dropdown = ft.Dropdown(
                label="角色",
                options=[
                    ft.dropdown.Option("普通用户"),
                    ft.dropdown.Option("管理员"),
                    ft.dropdown.Option("销售员"),
                    ft.dropdown.Option("配送员"),
                    ft.dropdown.Option("安装员"),
                ],
                value="普通用户",
                width=250,
            )
            day_field = ft.TextField(label="有效天数(留空永久)", width=250, hint_text="数字")
            perm_checkboxes = {}
            perm_col = ft.Column(spacing=5)
            for p in PERMISSIONS:
                cb = ft.Checkbox(label=p, value=True)
                perm_checkboxes[p] = cb
                perm_col.controls.append(cb)

            def save_user(e):
                uname = username_field.value.strip()
                real = realname_field.value.strip()
                pwd = password_field.value.strip()
                role = role_dropdown.value
                day_str = day_field.value.strip()
                if not uname or not pwd:
                    show_alert(page,"提示", "用户名和密码不能为空")
                    return
                expire_date = None
                if day_str.isdigit() and int(day_str) > 0:
                    expire_date = (date.today() + timedelta(days=int(day_str))).strftime("%Y-%m-%d")
                elif day_str == "" or day_str == "0":
                    expire_date = None
                else:
                    show_alert(page,"错误", "有效期请输入数字（0或留空为永久）")
                    return
                selected = [p for p, cb in perm_checkboxes.items() if cb.value]
                perm_str = ",".join(selected)
                conn = get_db_conn()
                if not conn:
                    show_alert(page,"错误", "数据库连接失败")
                    return
                cur = conn.cursor()
                try:
                    cur.execute(
                        "INSERT INTO users (username, password, real_name, role, permissions, expire_date) VALUES (%s, %s, %s, %s, %s, %s)",
                        (uname, md5_pwd(pwd), real, role, perm_str, expire_date)
                    )
                    conn.commit()
                    show_alert(page,"成功", f"用户 {uname} 添加成功")
                    add_dlg.open = False
                    safe_remove_dialog(page, add_dlg)
                    load_users()
                except Exception as ex:
                    conn.rollback()
                    show_alert(page,"错误", f"添加失败: {str(ex)}")
                finally:
                    conn.close()

            add_dlg = ft.AlertDialog(
                title=ft.Text("新增用户"),
                content=ft.Column(
                    [
                        username_field,
                        realname_field,
                        password_field,
                        role_dropdown,
                        day_field,
                        ft.Divider(height=5),
                        ft.Text("功能权限", weight=ft.FontWeight.BOLD),
                        perm_col,
                    ],
                    spacing=8,
                    width=300,
                ),
                actions=[
                    ft.TextButton("保存", on_click=save_user),
                    ft.TextButton("取消", on_click=lambda e: (setattr(add_dlg, 'open', False), safe_remove_dialog(page, add_dlg))),
                ],
            )
            page.overlay.append(add_dlg)
            add_dlg.open = True
            page.update()

        def edit_user_dialog():
            if not user_table.rows:
                show_alert(page,"提示", "没有用户可编辑")
                return
            def do_edit(e):
                uid_str = id_field.value.strip()
                if not uid_str.isdigit():
                    show_alert(page,"错误", "请输入有效ID")
                    return
                uid = int(uid_str)
                conn = get_db_conn()
                if not conn:
                    show_alert(page,"错误", "数据库连接失败")
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT id, username, real_name, role, permissions, expire_date FROM users WHERE id=%s", (uid,))
                user = cur.fetchone()
                conn.close()
                if not user:
                    show_alert(page,"错误", f"未找到ID {uid}")
                    return
                if user["role"] == "超级管理员":
                    show_alert(page,"提示", "超级管理员不可编辑")
                    return
                real_field = ft.TextField(label="真实姓名", value=user["real_name"] or "", width=250)
                role_drop = ft.Dropdown(
                    label="角色",
                    options=[
                        ft.dropdown.Option("普通用户"),
                        ft.dropdown.Option("管理员"),
                        ft.dropdown.Option("销售员"),
                        ft.dropdown.Option("配送员"),
                        ft.dropdown.Option("安装员"),
                    ],
                    value=user["role"] or "普通用户",
                    width=250,
                )
                pwd_field = ft.TextField(label="新密码(留空不修改)", password=True, can_reveal_password=True, width=250)
                day_field = ft.TextField(label="有效天数(重新计算，留空保持原日期)", width=250, hint_text="数字或留空")
                perm_checkboxes = {}
                perm_col = ft.Column(spacing=5)
                user_perms = set(user["permissions"].split(",")) if user["permissions"] else set()
                for p in PERMISSIONS:
                    cb = ft.Checkbox(label=p, value=(p in user_perms))
                    perm_checkboxes[p] = cb
                    perm_col.controls.append(cb)

                def save_edit(e):
                    new_real = real_field.value.strip()
                    new_role = role_drop.value
                    new_pwd = pwd_field.value.strip()
                    day_str = day_field.value.strip()
                    new_expire = user["expire_date"]
                    if day_str.isdigit() and int(day_str) > 0:
                        new_expire = (date.today() + timedelta(days=int(day_str))).strftime("%Y-%m-%d")
                    elif day_str == "" or day_str == "0":
                        new_expire = None
                    elif day_str:
                        show_alert(page,"错误", "有效期请输入数字（0或留空为永久）")
                        return
                    selected = [p for p, cb in perm_checkboxes.items() if cb.value]
                    perm_str = ",".join(selected)
                    conn = get_db_conn()
                    if not conn:
                        show_alert(page,"错误", "数据库连接失败")
                        return
                    cur = conn.cursor()
                    try:
                        if new_pwd:
                            cur.execute(
                                "UPDATE users SET real_name=%s, role=%s, password=%s, permissions=%s, expire_date=%s WHERE id=%s",
                                (new_real, new_role, md5_pwd(new_pwd), perm_str, new_expire, uid)
                            )
                        else:
                            cur.execute(
                                "UPDATE users SET real_name=%s, role=%s, permissions=%s, expire_date=%s WHERE id=%s",
                                (new_real, new_role, perm_str, new_expire, uid)
                            )
                        conn.commit()
                        show_alert(page,"成功", "用户信息已更新")
                        edit_dlg.open = False
                        safe_remove_dialog(page, edit_dlg)
                        load_users()
                    except Exception as ex:
                        conn.rollback()
                        show_alert(page,"错误", f"更新失败: {str(ex)}")
                    finally:
                        conn.close()

                edit_dlg = ft.AlertDialog(
                    title=ft.Text(f"编辑用户 {user['username']}"),
                    content=ft.Column(
                        [
                            real_field,
                            role_drop,
                            pwd_field,
                            day_field,
                            ft.Divider(height=5),
                            ft.Text("功能权限", weight=ft.FontWeight.BOLD),
                            perm_col,
                        ],
                        spacing=8,
                        scroll=ft.ScrollMode.AUTO,
                        width=300,
                    ),
                    actions=[
                        ft.TextButton("保存", on_click=save_edit),
                        ft.TextButton("取消", on_click=lambda e: (setattr(edit_dlg, 'open', False), safe_remove_dialog(page, edit_dlg))),
                    ],
                )
                page.overlay.append(edit_dlg)
                edit_dlg.open = True
                page.update()

            id_field = ft.TextField(label="要编辑的用户ID", width=200)
            select_dlg = ft.AlertDialog(
                title=ft.Text("请输入用户ID"),
                content=id_field,
                actions=[
                    ft.TextButton("确定", on_click=do_edit),
                    ft.TextButton("取消", on_click=lambda e: (setattr(select_dlg, 'open', False), safe_remove_dialog(page, select_dlg))),
                ],
            )
            page.overlay.append(select_dlg)
            select_dlg.open = True
            page.update()

        def delete_user():
            if not user_table.rows:
                show_alert(page,"提示", "没有用户可删除")
                return
            def do_delete(e):
                uid_str = id_field.value.strip()
                if not uid_str.isdigit():
                    show_alert(page,"错误", "请输入有效ID")
                    return
                uid = int(uid_str)
                conn = get_db_conn()
                if not conn:
                    show_alert(page,"错误", "数据库连接失败")
                    return
                cur = conn.cursor()
                cur.execute("SELECT role FROM users WHERE id=%s", (uid,))
                row = cur.fetchone()
                if not row:
                    show_alert(page,"错误", "用户不存在")
                    conn.close()
                    return
                if row[0] == "超级管理员":
                    show_alert(page,"提示", "无法删除超级管理员")
                    conn.close()
                    return

                def confirm(e):
                    try:
                        cur.execute("DELETE FROM users WHERE id=%s", (uid,))
                        conn.commit()
                        show_alert(page,"成功", "用户已删除")
                        confirm_dlg.open = False
                        safe_remove_dialog(page, confirm_dlg)
                        dlg.open = False
                        safe_remove_dialog(page, dlg)
                        load_users()
                    except Exception as ex:
                        conn.rollback()
                        show_alert(page,"错误", f"删除失败: {str(ex)}")
                    finally:
                        conn.close()

                confirm_dlg = ft.AlertDialog(
                    title=ft.Text("确认删除"),
                    content=ft.Text(f"确定要删除ID {uid} 吗？此操作不可恢复！"),
                    actions=[
                        ft.TextButton("确定", on_click=confirm),
                        ft.TextButton("取消", on_click=lambda e: (setattr(confirm_dlg, 'open', False), safe_remove_dialog(page, confirm_dlg))),
                    ],
                )
                page.overlay.append(confirm_dlg)
                confirm_dlg.open = True
                page.update()

            id_field = ft.TextField(label="要删除的用户ID", width=200)
            dlg = ft.AlertDialog(
                title=ft.Text("请输入用户ID"),
                content=id_field,
                actions=[
                    ft.TextButton("确定", on_click=do_delete),
                    ft.TextButton("取消", on_click=lambda e: (setattr(dlg, 'open', False), safe_remove_dialog(page, dlg))),
                ],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        btn_row = ft.Row(
            [
                ft.Button("新增用户", on_click=lambda e: add_user_dialog(), bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE),
                ft.Button("编辑用户", on_click=lambda e: edit_user_dialog(), bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE),
                ft.Button("删除用户", on_click=lambda e: delete_user(), bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
                ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_users(), tooltip="刷新"),
            ],
            spacing=10,
            wrap=True,
        )
        main_content.controls.append(
            ft.Column(
                [
                    ft.Text("用户管理（超级管理员）", size=20, weight=ft.FontWeight.BOLD),
                    btn_row,
                    ft.Container(
                        content=ft.Column([user_table], scroll=ft.ScrollMode.AUTO),
                        expand=True,
                    ),
                ],
                spacing=10,
            )
        )
        load_users()
        page.update()

    # ---------- 退出登录 ----------
    def logout_handler(e):
        nonlocal current_user
        current_user = None
        page.controls.clear()
        # 重新添加包含 login_container 和 config_overlay 的 Stack，确保齿轮按钮可用
        page.add(ft.Stack([login_container, config_overlay], expand=True))
        page.update()

    # ---------------------------- 个人中心 ----------------------------
    def show_profile():
        main_content.controls.clear()
        main_content.controls.append(
            ft.Column([
                ft.Card(content=ft.Container(
                    content=ft.Column([
                        ft.Text(f"用户名: {current_user['username']}", size=16),
                        ft.Text(f"姓名: {current_user['real_name']}", size=16),
                        ft.Text(f"角色: {current_user['role']}", size=16)
                    ], spacing=10), padding=20)),
                ft.Button("退出登录", icon=ft.Icons.LOGOUT, on_click=logout_handler)
            ], spacing=20))
        page.update()

    page.update()

ft.run(main)
