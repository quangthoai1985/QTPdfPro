"""Điều khiển mọi máy scan trên Windows qua WIA (Windows Image Acquisition).

Hỗ trợ tất cả máy scan hỗ trợ chuẩn WIA 1.0 / WIA 2.0 (USB, mạng WSD/eSCL, máy in đa năng
Epson, Canon, HP, Brother, Fujitsu, Ricoh, Xerox...), cả Mặt kính (Flatbed) lẫn Khay nạp giấy
tự động (ADF).

Ưu tiên truyền ảnh thẳng vào bộ nhớ bằng `IWiaDataTransfer::idtGetBandedData` (`TYMED_CALLBACK`)
để tránh lỗi ghi tệp tạm vào `%TEMP%` (0x80070005 / 0x80030070 do quyền thư mục hoặc phần mềm diệt
virus); tự động lùi về `item.Transfer` trong bộ nhớ với các driver WIA 2.0 / WSD không hỗ trợ
`TYMED_CALLBACK`, và có hàm `scan_via_common_dialog()` dùng hộp thoại hệ thống Windows cho máy đặc thù.
"""

from __future__ import annotations

import ctypes
import gc
import struct
from contextlib import contextmanager
from ctypes import HRESULT, POINTER, Structure, c_int, c_long, c_ubyte, c_ulong, c_void_p
from typing import Callable, List, Optional, Tuple

import comtypes
import comtypes.client
import cv2
import numpy as np
from comtypes import COMMETHOD, GUID, COMObject, IUnknown

SCANNER_DEVICE_TYPE = 1
WIA_FORMAT_MEMORYBMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"
WIA_FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
TYMED_FILE = 128
TYMED_CALLBACK = 128

# Mã thuộc tính WIA
WIA_DIP_DEV_DESC = 4
WIA_DIP_DEV_NAME = 7
BED_WIDTH = 3074  # đơn vị 1/1000 inch
BED_HEIGHT = 3075
SHEET_FEED_WIDTH = 3076
SHEET_FEED_HEIGHT = 3077
DOCUMENT_HANDLING_CAPS = 3086  # 1=Feeder, 2=Flatbed, 4=Duplex
DOCUMENT_HANDLING_SELECT = 3088  # 1=Feeder, 2=Flatbed, 4=Duplex
PAGES = 3096
DATA_TYPE = 4103
FORMAT = 4106
TYMED = 4108
MIN_BUFFER_SIZE = 4118
ITEM_CATEGORY = 4125
X_RES, Y_RES = 6147, 6148
X_POS, Y_POS = 6149, 6150
X_EXTENT, Y_EXTENT = 6151, 6152
BRIGHTNESS, CONTRAST = 6154, 6155
MAX_HORIZONTAL_SIZE = 6165  # WIA 2.0 (1/1000 inch)
MAX_VERTICAL_SIZE = 6166

WIA_CATEGORY_FLATBED = "{FB607B1F-43F3-488B-855B-FB703EC342A6}"
WIA_CATEGORY_FEEDER = "{FE131934-F84C-42AD-8DA4-6129CDDD7288}"
WIA_CATEGORY_FEEDER_FRONT = "{4823175C-3B28-487B-A75D-EFB1681862B7}"
WIA_CATEGORY_FEEDER_BACK = "{61CA74D4-39DB-42AA-89B1-8C19C9CD4C23}"

DATA_TYPES = {"bw": 0, "gray": 2, "color": 3}

IT_MSG_DATA_HEADER = 1
IT_MSG_DATA = 2
IT_MSG_STATUS = 3
S_OK, S_FALSE = 0, 1

WIA_ERROR_PAPER_EMPTY = 0x80210003
WIA_ERRORS = {
    0x80210001: "Lỗi chung từ trình điều khiển máy scan.",
    0x80210002: "Giấy bị kẹt trong máy scan.",
    0x80210003: "Khay nạp giấy (ADF) đang trống — hãy nạp thêm giấy.",
    0x80210004: "Khay nạp giấy (ADF) bị kẹt hoặc có vấn đề.",
    0x80210005: "Máy scan đang tắt hoặc mất kết nối.",
    0x80210006: "Máy scan đang bận — hãy đóng phần mềm scan khác (VueScan/Epson Scan/Canon Scan...) rồi thử lại.",
    0x80210007: "Máy scan đang khởi động đèn, đợi vài giây rồi thử lại.",
    0x80210008: "Máy scan chưa sẵn sàng.",
    0x80210009: "Lệnh điều khiển không hợp lệ với máy scan này.",
    0x8021000A: "Lỗi giao tiếp với máy scan (kiểm tra cáp USB hoặc kết nối mạng).",
    0x8021000C: "Nắp máy scan đang mở.",
    0x8021000D: "Đầu quét đang bị khoá (kiểm tra lẫy khoá vận chuyển dưới máy).",
    0x80210064: "Đã huỷ scan.",
}

# Các mã lỗi COM cho biết driver không hỗ trợ truyền dải callback → lùi sang Tier 2
_CALLBACK_UNSUPPORTED_HRESULTS = frozenset({
    0x80004001,  # E_NOTIMPL
    0x80004002,  # E_NOINTERFACE
    0x80070057,  # E_INVALIDARG
    0x8021000F,  # WIA_ERROR_INVALID_COMMAND / property unsupported
})
_HARDWARE_STOP_HRESULTS = frozenset(WIA_ERRORS.keys())


class WIA_DATA_TRANSFER_INFO(Structure):
    _fields_ = [
        ("ulSize", c_ulong),
        ("ulSection", c_ulong),
        ("ulBufferSize", c_ulong),
        ("bDoubleBuffer", c_int),
        ("ulReserved1", c_ulong),
        ("ulReserved2", c_ulong),
        ("ulReserved3", c_ulong),
    ]


class WIA_DATA_CALLBACK_HEADER(Structure):
    _fields_ = [
        ("lSize", c_long),
        ("guidFormatID", GUID),
        ("lBufferSize", c_long),
        ("lPageCount", c_long),
    ]


class IWiaDataCallback(IUnknown):
    _iid_ = GUID("{A558A866-A5B0-11D2-A08F-00C04F72DC3C}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "BandedDataCallback",
            (["in"], c_long, "lMessage"),
            (["in"], c_long, "lStatus"),
            (["in"], c_long, "lPercentComplete"),
            (["in"], c_long, "lOffset"),
            (["in"], c_long, "lLength"),
            (["in"], c_long, "lReserved"),
            (["in"], c_long, "lResLength"),
            (["in"], POINTER(c_ubyte), "pbBuffer"),
        ),
    ]


class IWiaDataTransfer(IUnknown):
    _iid_ = GUID("{A6CEF998-A5B0-11D2-A08F-00C04F72DC3C}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "idtGetData",
            (["in"], c_void_p, "pMedium"),
            (["in"], POINTER(IWiaDataCallback), "pCallback"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "idtGetBandedData",
            (["in"], POINTER(WIA_DATA_TRANSFER_INFO), "pInfo"),
            (["in"], POINTER(IWiaDataCallback), "pCallback"),
        ),
        COMMETHOD([], HRESULT, "idtQueryGetData", (["in"], c_void_p, "pfe")),
        COMMETHOD([], HRESULT, "idtEnumWIA_FORMAT_INFO", (["in"], c_void_p, "ppEnum")),
        COMMETHOD([], HRESULT, "idtGetExtendedTransferInfo", (["in"], c_void_p, "pInfo")),
    ]


class _Receiver(COMObject):
    """Nhận từng dải dữ liệu ảnh vào bộ nhớ."""

    _com_interfaces_ = [IWiaDataCallback]

    def __init__(self, progress: Optional[Callable[[int], object]] = None) -> None:
        super().__init__()
        self.data = bytearray()
        self.progress = progress
        self.cancelled = False

    def BandedDataCallback(self, this, msg, status, percent, offset, length, reserved, res_len, buf):  # noqa: N802
        if msg == IT_MSG_DATA_HEADER:
            header = ctypes.cast(buf, POINTER(WIA_DATA_CALLBACK_HEADER)).contents
            if header.lBufferSize > 0:
                self.data = bytearray(header.lBufferSize)
        elif msg == IT_MSG_DATA:
            end = offset + length
            if end > len(self.data):
                self.data.extend(bytes(end - len(self.data)))
            self.data[offset:end] = ctypes.string_at(buf, length)
        if msg in (IT_MSG_DATA, IT_MSG_STATUS) and self.progress:
            if self.progress(int(percent)) is False:
                self.cancelled = True
        return S_FALSE if self.cancelled else S_OK


class ScanError(Exception):
    pass


@contextmanager
def com_apartment():
    """Khởi tạo COM STA cho luồng phụ. Mọi đối tượng WIA phải tạo & huỷ trong cùng luồng này."""
    comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
    try:
        yield
    finally:
        gc.collect()
        comtypes.CoUninitialize()


def _hresult_u32(err: BaseException) -> int:
    return (getattr(err, "hresult", 0) or 0) & 0xFFFFFFFF


def _explain(err: BaseException) -> str:
    code = _hresult_u32(err)
    msg = WIA_ERRORS.get(code)
    return f"{msg} (mã 0x{code:08X})" if msg else f"Lỗi WIA 0x{code:08X}: {err}"


def _find_prop_opt(props, pid: int):
    try:
        for p in props:
            if getattr(p, "PropertyID", None) == pid:
                return p
    except Exception:
        pass
    return None


def _find_prop_by_name(props, name: str):
    try:
        return props.Item(name)
    except Exception:
        return None


def _find_prop(props, pid: int):
    p = _find_prop_opt(props, pid)
    if p is None:
        raise ScanError(f"Máy scan không hỗ trợ thuộc tính WIA {pid}.")
    return p


def _coerce_prop_value(p, value):
    """Ép giá trị về đúng miền SubType của thuộc tính WIA (Range step hoặc List gần nhất)."""
    try:
        sub_type = int(getattr(p, "SubType", 0))
    except Exception:
        return value
    if sub_type == 1:  # Range
        try:
            mn = int(p.SubTypeMin)
            mx = int(p.SubTypeMax)
            step = max(1, int(getattr(p, "SubTypeStep", 1) or 1))
            clamped = max(mn, min(mx, int(round(value))))
            snapped = mn + round((clamped - mn) / step) * step
            if snapped > mx:
                snapped -= step
            return max(mn, min(mx, snapped))
        except Exception:
            return value
    if sub_type == 2:  # List
        try:
            vals = list(p.SubTypeValues)
            if vals:
                if value in vals:
                    return value
                if all(isinstance(v, (int, float)) for v in vals) and isinstance(value, (int, float)):
                    return min(vals, key=lambda v: abs(v - value))
        except Exception:
            pass
    return value


def _set_safe(props, pid: int, value, *, required: bool = False):
    """Đặt thuộc tính WIA an toàn: tự làm tròn theo step/list, bỏ qua nếu thiếu hoặc ReadOnly (trừ `required`)."""
    p = _find_prop_opt(props, pid)
    if p is None:
        if required:
            raise ScanError(f"Máy scan không hỗ trợ thuộc tính WIA {pid}.")
        return None
    try:
        if getattr(p, "IsReadOnly", False):
            return p.Value
    except Exception:
        pass
    coerced = _coerce_prop_value(p, value)
    try:
        p.Value = coerced
        return p.Value
    except comtypes.COMError as e:
        if required:
            raise ScanError(_explain(e)) from e
        try:
            return p.Value
        except Exception:
            return coerced


def _set(props, pid: int, value):
    return _set_safe(props, pid, value, required=True)


def _clamp(props, pid: int, value: float) -> int:
    p = _find_prop_opt(props, pid)
    if p is None:
        return int(round(value))
    return int(_coerce_prop_value(p, value))


def _decode_dib(buf) -> np.ndarray:
    """Giải mã DIB / BMP (1/4/8/16/24/32 bit, BI_RGB hoặc BI_BITFIELDS) hoặc PNG/JPEG/TIFF thành ảnh numpy."""
    b = bytes(buf)
    if not b:
        raise ScanError("Dữ liệu ảnh từ máy scan bị rỗng.")

    # Một số driver WIA 2.0 / WSD trả trực tiếp PNG, JPEG hoặc TIFF
    if b.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*")):
        img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ScanError("Không giải mã được định dạng ảnh nén từ máy scan.")
        if img.dtype == np.uint16:
            img = (img >> 8).astype(np.uint8)
        if img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return np.ascontiguousarray(img)

    if b[:2] == b"BM":  # có BITMAPFILEHEADER 14 byte
        b = b[14:]

    if len(b) < 16:
        raise ScanError("Dữ liệu ảnh DIB từ máy scan quá ngắn hoặc hỏng.")

    bi_size = struct.unpack_from("<I", b, 0)[0]
    if bi_size == 12:  # BITMAPCOREHEADER
        _, width, height, _, bpp = struct.unpack_from("<IHHHH", b)
        compression, clr_used = 0, 0
        pal_entry_size = 3
    else:
        bi_size, width, height, _, bpp, compression, _, _, _, clr_used, _ = struct.unpack_from("<IiiHHIIiiII", b)
        pal_entry_size = 4

    if compression not in (0, 3):  # BI_RGB=0, BI_BITFIELDS=3
        raise ScanError(f"Định dạng ảnh DIB nén chưa hỗ trợ (compression={compression}).")

    mask_bytes = 12 if (compression == 3 and bi_size == 40) else 0
    n_colors = clr_used or (1 << bpp if bpp <= 8 else 0)
    offset = bi_size + mask_bytes + n_colors * pal_entry_size
    stride = (width * bpp + 31) // 32 * 4
    if stride <= 0 or width <= 0:
        raise ScanError(f"Kích thước ảnh DIB không hợp lệ ({width}x{height}).")
    avail_rows = max(0, (len(b) - offset) // stride)
    rows = min(abs(height), avail_rows) if height else avail_rows
    if rows <= 0:
        raise ScanError("Dữ liệu điểm ảnh DIB không đủ dòng.")

    raw = np.frombuffer(b, np.uint8, count=rows * stride, offset=offset).reshape(rows, stride)

    if bpp == 24:
        img = raw[:, : width * 3].reshape(rows, width, 3)
    elif bpp == 32:
        img = raw[:, : width * 4].reshape(rows, width, 4)[..., :3]
    elif bpp == 16:
        px16 = np.frombuffer(raw[:, : width * 2].tobytes(), dtype="<u2").reshape(rows, width)
        # Mặc định RGB555 hoặc RGB565
        if compression == 3 and len(b) >= bi_size + 12:
            r_mask, g_mask, b_mask = struct.unpack_from("<III", b, bi_size)
        else:
            r_mask, g_mask, b_mask = 0x7C00, 0x03E0, 0x001F
        if g_mask == 0x07E0:  # RGB565
            r = ((px16 >> 11) & 0x1F) * 255 // 31
            g = ((px16 >> 5) & 0x3F) * 255 // 63
            bl = (px16 & 0x1F) * 255 // 31
        else:  # RGB555
            r = ((px16 >> 10) & 0x1F) * 255 // 31
            g = ((px16 >> 5) & 0x1F) * 255 // 31
            bl = (px16 & 0x1F) * 255 // 31
        img = np.stack([bl, g, r], axis=2).astype(np.uint8)
    elif bpp in (1, 4, 8):
        if bpp == 1:
            idx = np.unpackbits(raw, axis=1)[:, :width]
        elif bpp == 4:
            hi = (raw >> 4) & 0x0F
            lo = raw & 0x0F
            nibbles = np.empty((rows, stride * 2), dtype=np.uint8)
            nibbles[:, 0::2] = hi
            nibbles[:, 1::2] = lo
            idx = nibbles[:, :width]
        else:
            idx = raw[:, :width]
        palette = np.frombuffer(b, np.uint8, count=n_colors * pal_entry_size, offset=bi_size + mask_bytes).reshape(
            -1, pal_entry_size
        )
        if np.array_equal(palette[:, 0], palette[:, 1]) and np.array_equal(palette[:, 1], palette[:, 2]):
            img = palette[:, 0][idx]
        else:
            img = palette[:, :3][idx]
    else:
        raise ScanError(f"Độ sâu màu {bpp} bit chưa hỗ trợ.")

    if height > 0:  # DIB mặc định lưu từ dưới lên
        img = img[::-1]
    return np.ascontiguousarray(img)


def _safe_device_name(info) -> str:
    props = getattr(info, "Properties", None)
    if props is not None:
        for accessor in (
            lambda: _find_prop_by_name(props, "Name"),
            lambda: _find_prop_opt(props, WIA_DIP_DEV_NAME),
            lambda: _find_prop_by_name(props, "Description"),
            lambda: _find_prop_opt(props, WIA_DIP_DEV_DESC),
        ):
            p = accessor()
            if p is not None:
                val = str(getattr(p, "Value", "") or "").strip()
                if val:
                    return val
    return str(getattr(info, "DeviceID", "Máy scan WIA"))


def _iter_scan_items(container) -> list:
    """Duyệt mọi WIA Item có khả năng scan (có X_RES hoặc DATA_TYPE), hỗ trợ cả cây WIA 2.0."""
    found = []
    try:
        items = container.Items
        count = int(items.Count)
    except Exception:
        return found
    for i in range(1, count + 1):
        try:
            it = items.Item(i)
        except Exception:
            continue
        props = getattr(it, "Properties", None)
        has_scan_props = props is not None and (
            _find_prop_opt(props, X_RES) is not None
            or _find_prop_opt(props, DATA_TYPE) is not None
            or _find_prop_opt(props, X_EXTENT) is not None
        )
        if has_scan_props:
            found.append(it)
        try:
            sub = _iter_scan_items(it)
            for s in sub:
                if s not in found:
                    found.append(s)
        except Exception:
            pass
    return found


def _looks_like_scanner(info) -> bool:
    """Nhận cả thiết bị Type==1 lẫn máy đa năng Type==0 có thuộc tính/item scan."""
    t = getattr(info, "Type", None)
    if t == SCANNER_DEVICE_TYPE:
        return True
    if t not in (0, None):
        return False
    try:
        dev = info.Connect()
        return bool(_iter_scan_items(dev))
    except Exception:
        return False


def _connect(device_id: Optional[str] = None):
    dm = comtypes.client.CreateObject("WIA.DeviceManager")
    fallback_dev = None
    for i in range(1, int(dm.DeviceInfos.Count) + 1):
        try:
            info = dm.DeviceInfos.Item(i)
        except Exception:
            continue
        if device_id is not None:
            if getattr(info, "DeviceID", None) == device_id:
                return info.Connect()
        else:
            if getattr(info, "Type", None) == SCANNER_DEVICE_TYPE:
                return info.Connect()
            if getattr(info, "Type", None) == 0 and fallback_dev is None and _looks_like_scanner(info):
                fallback_dev = info
    if fallback_dev is not None:
        return fallback_dev.Connect()
    raise ScanError("Không tìm thấy máy scan. Kiểm tra máy đã bật nguồn và kết nối USB / mạng chưa.")


def list_scanners() -> List[Tuple[str, str]]:
    """Trả về danh sách `(device_id, tên)` các máy scan WIA đang kết nối (WIA 1.0, WIA 2.0, USB, WSD/MFP)."""
    dm = comtypes.client.CreateObject("WIA.DeviceManager")
    found: List[Tuple[str, str]] = []
    seen_ids: set[str] = set()
    for i in range(1, int(dm.DeviceInfos.Count) + 1):
        try:
            info = dm.DeviceInfos.Item(i)
            dev_id = str(getattr(info, "DeviceID", "") or "")
            if not dev_id or dev_id in seen_ids:
                continue
            if _looks_like_scanner(info):
                seen_ids.add(dev_id)
                found.append((dev_id, _safe_device_name(info)))
        except Exception:
            continue
    return found


def _item_category_str(item) -> str:
    props = getattr(item, "Properties", None)
    if props is None:
        return ""
    p = _find_prop_opt(props, ITEM_CATEGORY)
    if p is not None:
        return str(getattr(p, "Value", "") or "").upper()
    return ""


def _item_name_str(item) -> str:
    props = getattr(item, "Properties", None)
    if props is None:
        return ""
    for name in ("Item Name", "Full Item Name"):
        p = _find_prop_by_name(props, name)
        if p is not None:
            return str(getattr(p, "Value", "") or "").lower()
    return ""


def _select_scan_item(dev, source: str = "auto"):
    """Chọn WIA Item và cấu hình nguồn quét (`auto` | `flatbed` | `adf`)."""
    items = _iter_scan_items(dev)
    if not items:
        try:
            items = [dev.Items.Item(1)]
        except Exception as e:
            raise ScanError("Máy scan không có mục quét khả dụng.") from e

    # Thử đặt DOCUMENT_HANDLING_SELECT trên dev.Properties (WIA 1.0 như Epson 4490)
    if source == "adf":
        _set_safe(dev.Properties, DOCUMENT_HANDLING_SELECT, 1)
    elif source == "flatbed":
        _set_safe(dev.Properties, DOCUMENT_HANDLING_SELECT, 2)

    chosen = items[0]
    if source == "adf":
        for it in items:
            cat = _item_category_str(it)
            name = _item_name_str(it)
            if cat in (WIA_CATEGORY_FEEDER, WIA_CATEGORY_FEEDER_FRONT) or "feeder" in name or "adf" in name:
                chosen = it
                break
        _set_safe(chosen.Properties, DOCUMENT_HANDLING_SELECT, 1)
        _set_safe(dev.Properties, PAGES, 1)
        _set_safe(chosen.Properties, PAGES, 1)
    elif source == "flatbed":
        for it in items:
            cat = _item_category_str(it)
            name = _item_name_str(it)
            if cat == WIA_CATEGORY_FLATBED or "flatbed" in name or "platen" in name:
                chosen = it
                break
        _set_safe(chosen.Properties, DOCUMENT_HANDLING_SELECT, 2)
    else:
        for it in items:
            cat = _item_category_str(it)
            name = _item_name_str(it)
            if cat == WIA_CATEGORY_FLATBED or "flatbed" in name:
                chosen = it
                break
    return chosen


def _get_bed_size_in(dev, item, dpi: int) -> Tuple[float, float]:
    """Đọc kích thước mặt kính / khay giấy tối đa (inch) với nhiều tầng dự phòng cho mọi hãng máy scan."""
    d_props = getattr(dev, "Properties", None)
    i_props = getattr(item, "Properties", None)
    candidates = [
        (i_props, MAX_HORIZONTAL_SIZE, MAX_VERTICAL_SIZE, 1000.0),
        (d_props, BED_WIDTH, BED_HEIGHT, 1000.0),
        (d_props, SHEET_FEED_WIDTH, SHEET_FEED_HEIGHT, 1000.0),
    ]
    for props, pid_w, pid_h, div in candidates:
        if props is None:
            continue
        pw = _find_prop_opt(props, pid_w)
        ph = _find_prop_opt(props, pid_h)
        if pw is not None and ph is not None:
            try:
                w_in = float(pw.Value) / div
                h_in = float(ph.Value) / div
                if w_in > 0.5 and h_in > 0.5:
                    return w_in, h_in
            except Exception:
                pass
    if i_props is not None and dpi > 0:
        px = _find_prop_opt(i_props, X_EXTENT)
        py = _find_prop_opt(i_props, Y_EXTENT)
        if px is not None and py is not None:
            try:
                mx_x = float(getattr(px, "SubTypeMax", 0) or 0)
                mx_y = float(getattr(py, "SubTypeMax", 0) or 0)
                if mx_x > dpi and mx_y > dpi:
                    return mx_x / dpi, mx_y / dpi
            except Exception:
                pass
    return 8.5, 11.7


def _set_data_type_with_fallback(props, mode: str) -> None:
    desired = DATA_TYPES[mode]
    order = [desired] + [v for v in (2, 3, 0) if v != desired]
    p = _find_prop_opt(props, DATA_TYPE)
    if p is None:
        return
    try:
        if getattr(p, "IsReadOnly", False):
            return
    except Exception:
        pass
    for candidate in order:
        try:
            if int(getattr(p, "SubType", 0)) == 2:
                vals = list(p.SubTypeValues)
                if vals and candidate not in vals:
                    continue
            p.Value = candidate
            return
        except comtypes.COMError:
            continue


def _transfer_banded(item, props, progress) -> Optional[bytearray]:
    """Tầng 1: Nhận ảnh qua IWiaDataTransfer::idtGetBandedData thẳng vào RAM (không tạo file tạm)."""
    tymed_res = _set_safe(props, TYMED, TYMED_CALLBACK, required=False)
    if tymed_res is not None and int(tymed_res) != TYMED_CALLBACK:
        return None
    fmt = _find_prop_opt(props, FORMAT)
    if fmt is not None and str(getattr(fmt, "Value", "")).upper() != WIA_FORMAT_MEMORYBMP:
        try:
            fmt.Value = WIA_FORMAT_MEMORYBMP
        except comtypes.COMError:
            pass

    p_buf = _find_prop_opt(props, MIN_BUFFER_SIZE)
    min_buffer = int(getattr(p_buf, "Value", 0) or 0) if p_buf is not None else 65536
    min_buffer = max(65536, min_buffer)

    transfer = item.WiaItem.QueryInterface(IWiaDataTransfer)
    info = WIA_DATA_TRANSFER_INFO(
        ulSize=ctypes.sizeof(WIA_DATA_TRANSFER_INFO),
        ulBufferSize=2 * min_buffer,
        bDoubleBuffer=True,
    )
    receiver = _Receiver(progress)
    transfer.idtGetBandedData(ctypes.byref(info), receiver.QueryInterface(IWiaDataCallback))
    if receiver.cancelled:
        raise ScanError("Đã huỷ scan.")
    return receiver.data


def _transfer_item_memory(item, progress) -> bytes:
    """Tầng 2: Dự phòng cho driver WIA 2.0 / WSD không hỗ trợ `TYMED_CALLBACK` — dùng `item.Transfer` vào RAM."""
    if progress:
        progress(10)
    img_file = None
    for fmt in (WIA_FORMAT_BMP, WIA_FORMAT_PNG, None):
        try:
            img_file = item.Transfer(fmt) if fmt is not None else item.Transfer()
            if img_file is not None:
                break
        except comtypes.COMError as e:
            code = _hresult_u32(e)
            if code in _HARDWARE_STOP_HRESULTS:
                raise ScanError(_explain(e)) from e
            continue
    if img_file is None:
        raise ScanError("Không truyền được dữ liệu ảnh từ máy scan.")
    if progress:
        progress(90)
    raw_data = img_file.FileData.BinaryData
    data = bytes(raw_data)
    if progress:
        progress(100)
    return data


def scan_with_info(
    dpi: int = 300,
    mode: str = "gray",
    area: Optional[Tuple[float, float, float, float]] = None,
    brightness: int = 0,
    contrast: int = 0,
    device_id: Optional[str] = None,
    source: str = "auto",
    progress: Optional[Callable[[int], object]] = None,
) -> Tuple[np.ndarray, int]:
    """Scan một trang từ máy scan WIA. Trả về `(ảnh numpy, dpi thực tế)`.

    - `mode`: `"gray" | "color" | "bw"`.
    - `area`: `(x, y, w, h)` tính bằng inch từ góc trên-trái; `None` = toàn bộ mặt kính/khay giấy.
    - `source`: `"auto" | "flatbed" | "adf"`.
    """
    actual_dpi = int(dpi)
    try:
        dev = _connect(device_id)
        item = _select_scan_item(dev, source=source)
        props = item.Properties

        _set_data_type_with_fallback(props, mode)
        res_x = _set_safe(props, X_RES, dpi)
        _set_safe(props, Y_RES, res_x or dpi)
        if res_x:
            actual_dpi = int(res_x)

        bed_w, bed_h = _get_bed_size_in(dev, item, actual_dpi)
        x, y, w, h = area or (0.0, 0.0, bed_w, bed_h)

        # Đưa vị trí về 0 trước để dải giá trị của vùng quét mở rộng tối đa
        _set_safe(props, X_POS, 0)
        _set_safe(props, Y_POS, 0)
        x_pos_val = _clamp(props, X_POS, round(x * actual_dpi))
        y_pos_val = _clamp(props, Y_POS, round(y * actual_dpi))

        p_xext = _find_prop_opt(props, X_EXTENT)
        p_yext = _find_prop_opt(props, Y_EXTENT)
        max_x_ext = int(getattr(p_xext, "SubTypeMax", round(bed_w * actual_dpi))) if p_xext is not None else round(w * actual_dpi)
        max_y_ext = int(getattr(p_yext, "SubTypeMax", round(bed_h * actual_dpi))) if p_yext is not None else round(h * actual_dpi)

        req_w = min(round(w * actual_dpi), max(1, max_x_ext - x_pos_val))
        req_h = min(round(h * actual_dpi), max(1, max_y_ext - y_pos_val))
        _set_safe(props, X_EXTENT, _clamp(props, X_EXTENT, req_w))
        _set_safe(props, Y_EXTENT, _clamp(props, Y_EXTENT, req_h))
        _set_safe(props, X_POS, x_pos_val)
        _set_safe(props, Y_POS, y_pos_val)

        if brightness:
            _set_safe(props, BRIGHTNESS, brightness)
        if contrast:
            _set_safe(props, CONTRAST, contrast)

        raw_bytes: Optional[bytes] = None
        try:
            banded = _transfer_banded(item, props, progress)
            if banded is not None:
                raw_bytes = bytes(banded)
        except comtypes.COMError as e:
            code = _hresult_u32(e)
            if code in _HARDWARE_STOP_HRESULTS:
                raise ScanError(_explain(e)) from e
            if code not in _CALLBACK_UNSUPPORTED_HRESULTS:
                raise ScanError(_explain(e)) from e

        if not raw_bytes:
            raw_bytes = _transfer_item_memory(item, progress)

    except ScanError:
        raise
    except comtypes.COMError as e:
        raise ScanError(_explain(e)) from e

    if not raw_bytes:
        raise ScanError("Máy scan không trả về dữ liệu ảnh.")
    return _decode_dib(raw_bytes), actual_dpi


def scan(
    dpi: int = 300,
    mode: str = "gray",
    area: Optional[Tuple[float, float, float, float]] = None,
    brightness: int = 0,
    contrast: int = 0,
    device_id: Optional[str] = None,
    source: str = "auto",
    progress: Optional[Callable[[int], object]] = None,
) -> np.ndarray:
    """Scan một trang từ máy scan và trả về ảnh numpy (giữ chữ ký tương thích với PDFScanner)."""
    img, _actual_dpi = scan_with_info(
        dpi=dpi,
        mode=mode,
        area=area,
        brightness=brightness,
        contrast=contrast,
        device_id=device_id,
        source=source,
        progress=progress,
    )
    return img


def scan_via_common_dialog() -> Optional[Tuple[np.ndarray, int]]:
    """Tầng 3: Mở hộp thoại scan chuẩn của Windows / hãng máy scan (WIA.CommonDialog) cho máy đặc thù."""
    try:
        dlg = comtypes.client.CreateObject("WIA.CommonDialog")
        img_file = dlg.ShowAcquireImage(
            DeviceType=SCANNER_DEVICE_TYPE,
            Intent=0,
            Bias=0,
            FormatID=WIA_FORMAT_BMP,
            AlwaysSelectDevice=False,
            UseCommonUI=True,
            CancelError=False,
        )
    except comtypes.COMError as e:
        code = _hresult_u32(e)
        if code == 0x80210064:
            return None
        raise ScanError(_explain(e)) from e
    if img_file is None:
        return None
    data = bytes(img_file.FileData.BinaryData)
    if not data:
        return None
    dpi = 300
    try:
        dpi = max(72, int(round(float(getattr(img_file, "HorizontalResolution", 300) or 300))))
    except Exception:
        pass
    return _decode_dib(data), dpi


def scan_adf_pages(
    dpi: int = 300,
    mode: str = "gray",
    area: Optional[Tuple[float, float, float, float]] = None,
    brightness: int = 0,
    contrast: int = 0,
    device_id: Optional[str] = None,
    progress: Optional[Callable[[int], object]] = None,
    on_page: Optional[Callable[[np.ndarray, int, int], object]] = None,
    max_pages: int = 200,
) -> List[Tuple[np.ndarray, int]]:
    """Scan nhiều trang liên tiếp từ khay nạp giấy tự động (ADF) tới khi hết giấy hoặc bị huỷ.

    `on_page(img, actual_dpi, page_num_1based)` nếu trả về `False` sẽ dừng quét các trang tiếp theo.
    """
    results: List[Tuple[np.ndarray, int]] = []
    for page_num in range(1, max_pages + 1):
        try:
            img, actual_dpi = scan_with_info(
                dpi=dpi,
                mode=mode,
                area=area,
                brightness=brightness,
                contrast=contrast,
                device_id=device_id,
                source="adf",
                progress=progress,
            )
        except ScanError as exc:
            err_txt = str(exc)
            # Hết giấy sau ít nhất 1 trang → kết thúc bình thường
            if results and (f"0x{WIA_ERROR_PAPER_EMPTY:08X}" in err_txt or "hết giấy" in err_txt.lower() or "đang trống" in err_txt.lower()):
                break
            raise
        results.append((img, actual_dpi))
        if on_page is not None and on_page(img, actual_dpi, page_num) is False:
            break
    return results
