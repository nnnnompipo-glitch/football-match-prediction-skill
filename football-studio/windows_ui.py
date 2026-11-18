"""Small native Windows control window for the local research server."""
import ctypes as ct
from ctypes import wintypes as wt
from pathlib import Path
import webbrowser


def show_manager(url, icon, auto_open):
    user = ct.windll.user32
    gdi = ct.windll.gdi32
    proc_type = ct.WINFUNCTYPE(ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WindowClass(ct.Structure):
        _fields_ = [("style", wt.UINT), ("proc", proc_type), ("class_bytes", ct.c_int),
                    ("window_bytes", ct.c_int), ("instance", wt.HINSTANCE), ("icon", wt.HICON),
                    ("cursor", wt.HANDLE), ("background", wt.HBRUSH), ("menu", wt.LPCWSTR),
                    ("name", wt.LPCWSTR)]

    def bind(dll, name, result, *args):
        f = getattr(dll, name)
        f.restype = result
        f.argtypes = args
        return f

    instance = bind(ct.windll.kernel32, "GetModuleHandleW", wt.HINSTANCE, wt.LPCWSTR)(None)
    default_proc = bind(user, "DefWindowProcW", ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    destroy = bind(user, "DestroyWindow", wt.BOOL, wt.HWND)
    create = bind(user, "CreateWindowExW", wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                  ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
    send = bind(user, "SendMessageW", ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    background = bind(user, "GetSysColorBrush", wt.HBRUSH, ct.c_int)(5)
    transparent = bind(gdi, "SetBkMode", ct.c_int, wt.HDC, ct.c_int)

    @proc_type
    def window_proc(hwnd, message, wparam, lparam):
        if message == 0x0111:  # WM_COMMAND
            button_id = wparam & 0xffff
            if button_id == 101:
                webbrowser.open(url)
            elif button_id == 102:
                destroy(hwnd)
            return 0
        if message == 0x0138:  # WM_CTLCOLORSTATIC
            transparent(wparam, 1)
            return background
        if message == 0x0002:  # WM_DESTROY
            user.PostQuitMessage(0)
            return 0
        return default_proc(hwnd, message, wparam, lparam)

    user.SetProcessDPIAware()
    scale = user.GetDpiForSystem() / 96 if hasattr(user, "GetDpiForSystem") else 1
    px = lambda n: round(n * scale)
    cursor = bind(user, "LoadCursorW", wt.HANDLE, wt.HINSTANCE, ct.c_void_p)(None, 32512)
    image = bind(user, "LoadImageW", wt.HANDLE, wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ct.c_int, ct.c_int,
                 wt.UINT)(None, str(Path(icon)), 1, 0, 0, 0x0050)
    class_name = "TouchlineLabDesktopControl"
    cls = WindowClass(0, window_proc, 0, 0, instance, image, cursor, background, None, class_name)
    if not bind(user, "RegisterClassW", wt.ATOM, ct.POINTER(WindowClass))(ct.byref(cls)):
        raise ct.WinError()
    style = 0x00CA0000  # WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX
    rect = wt.RECT(0, 0, px(415), px(187))
    user.AdjustWindowRect(ct.byref(rect), style, False)
    hwnd = create(0, class_name, "Touchline Lab · 足球赛前研究室", style, -2147483648, -2147483648,
                  rect.right - rect.left, rect.bottom - rect.top, None, None, instance, None)
    if not hwnd:
        raise ct.WinError()
    make_font = bind(gdi, "CreateFontW", wt.HFONT, *([ct.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]))
    fonts = [make_font(-px(size), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, "Microsoft YaHei UI")
             for size, weight in ((24, 650), (15, 400))]

    def control(kind, label, x, y, width, height, font, button_id=0):
        child_style = 0x50000000 | (0x00010000 if button_id else 0)  # child, visible, optional tab stop
        handle = create(0, kind, label, child_style, px(x), px(y), px(width), px(height),
                        hwnd, button_id or None, instance, None)
        send(handle, 0x0030, font, 1)  # WM_SETFONT

    control("STATIC", "足球赛前研究室", 24, 19, 375, 35, fonts[0])
    control("STATIC", f"本机服务已启动  ·  {url}", 25, 64, 374, 23, fonts[1])
    control("STATIC", "关闭此窗口将停止本机服务。", 25, 92, 374, 24, fonts[1])
    control("BUTTON", "打开研究室", 24, 133, 110, 34, fonts[1], 101)
    control("BUTTON", "退出", 145, 133, 75, 34, fonts[1], 102)
    bind(user, "ShowWindow", wt.BOOL, wt.HWND, ct.c_int)(hwnd, 1)
    bind(user, "UpdateWindow", wt.BOOL, wt.HWND)(hwnd)
    if auto_open:
        webbrowser.open(url)
    msg = wt.MSG()
    dialog_message = bind(user, "IsDialogMessageW", wt.BOOL, wt.HWND, ct.POINTER(wt.MSG))
    dispatch = bind(user, "DispatchMessageW", ct.c_ssize_t, ct.POINTER(wt.MSG))
    while user.GetMessageW(ct.byref(msg), None, 0, 0) > 0:
        if not dialog_message(hwnd, ct.byref(msg)):
            user.TranslateMessage(ct.byref(msg))
            dispatch(ct.byref(msg))
    for font in fonts:
        bind(gdi, "DeleteObject", wt.BOOL, wt.HANDLE)(font)
