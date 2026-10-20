"""Các hàm nền xử lý PDF dùng chung cho mọi engine chuyển đổi của QT PDF Pro.

- `splice_overlapping_stamped_text`: ghép số hiệu / ngày tháng do phần mềm ký số đóng dấu đè
  lên khoảng trắng của dòng mẫu (`Số:      /QĐ-UBND`) vào đúng vị trí trong dòng chủ.
- `extract_widget_overlays`: trích ảnh con dấu đỏ, chữ ký số, chữ ký nháy (PNG RGBA trong suốt)
  từ PDF Signature Widgets kèm toạ độ trang chính xác.
"""

from __future__ import annotations

import fitz  # PyMuPDF


def splice_overlapping_stamped_text(text_blocks: list[dict]) -> list[dict]:
    """Ghép các dòng văn bản đóng dấu đè lên khoảng trắng (như Số văn bản '3865', Ngày '14'
    trong văn bản hành chính ký số VGCA/iOffice) trực tiếp vào khoảng trắng của dòng chủ.

    Nhờ đó `pdf2docx` không loại bỏ nhầm dòng đóng dấu khi chạy `_remove_overlapped_lines`.
    """
    line_refs: list[tuple[dict, dict, str, tuple[float, float, float, float]]] = []
    for blk in text_blocks:
        if blk.get("type", 0) != 0:
            continue
        for ln in blk.get("lines", []):
            txt = "".join(
                c.get("c", "") for sp in ln.get("spans", []) for c in sp.get("chars", [])
            )
            bbox = tuple(ln.get("bbox", (0.0, 0.0, 0.0, 0.0)))
            line_refs.append((blk, ln, txt, bbox))

    lines_to_remove: set[int] = set()

    for s_blk, s_ln, s_txt, s_bbox in line_refs:
        s_clean = s_txt.strip()
        if not s_clean or len(s_clean) > 30:
            continue
        sx0, sy0, sx1, sy1 = s_bbox
        sw = sx1 - sx0
        sh = sy1 - sy0
        if sw <= 0 or sh <= 0:
            continue

        # Tìm dòng chủ (host line) rộng hơn và chứa dòng đóng dấu này
        for h_blk, h_ln, h_txt, h_bbox in line_refs:
            if h_ln is s_ln or id(h_ln) in lines_to_remove:
                continue
            hx0, hy0, hx1, hy1 = h_bbox
            hw = hx1 - hx0
            hh = hy1 - hy0
            if hw <= sw * 1.25 or hh <= 0:
                continue

            # Kiểm tra giao nhau theo chiều dọc và nằm gọn theo chiều ngang
            y_ov = min(sy1, hy1) - max(sy0, hy0)
            if y_ov < 0.35 * min(sh, hh):
                continue
            if sx0 < hx0 - 4.0 or sx1 > hx1 + 4.0:
                continue

            # Tìm span trong dòng chủ có giao vùng ngang lớn nhất với [sx0, sx1]
            best_span = None
            best_x_ov = 0.0
            for sp in h_ln.get("spans", []):
                spx0, _, spx1, _ = sp.get("bbox", (0.0, 0.0, 0.0, 0.0))
                x_ov = min(sx1, spx1) - max(sx0, spx0)
                if x_ov > best_x_ov:
                    best_x_ov = x_ov
                    best_span = sp

            if best_span is None:
                continue

            h_chars = best_span.get("chars", [])
            if not h_chars:
                continue

            overlapped_indices = [
                idx
                for idx, ch in enumerate(h_chars)
                if (sx0 - 1.5)
                <= 0.5 * (ch["bbox"][0] + ch["bbox"][2])
                <= (sx1 + 1.5)
            ]
            if not overlapped_indices:
                continue

            # Chỉ ghép nếu vùng bị đè trong dòng chủ là khoảng trắng
            if not all(h_chars[i].get("c", "").strip() == "" for i in overlapped_indices):
                continue

            # Mở rộng ra toàn bộ dải khoảng trắng liên tiếp chứa vùng đóng dấu
            ws_start = overlapped_indices[0]
            while ws_start > 0 and h_chars[ws_start - 1].get("c", "").strip() == "":
                ws_start -= 1
            ws_end = overlapped_indices[-1]
            while (
                ws_end + 1 < len(h_chars)
                and h_chars[ws_end + 1].get("c", "").strip() == ""
            ):
                ws_end += 1

            # Lấy danh sách ký tự thực của dòng đóng dấu
            s_chars = [
                dict(c)
                for sp in s_ln.get("spans", [])
                for c in sp.get("chars", [])
            ]
            while s_chars and s_chars[0].get("c", "").strip() == "":
                s_chars.pop(0)
            while s_chars and s_chars[-1].get("c", "").strip() == "":
                s_chars.pop()
            if not s_chars:
                continue

            replacement: list[dict] = []
            if ws_start > 0:
                prev_ch = h_chars[ws_start - 1].get("c", "")
                if prev_ch not in (" ", "/", "(", "["):
                    sp_before = dict(h_chars[ws_start])
                    sp_before["c"] = " "
                    replacement.append(sp_before)

            replacement.extend(s_chars)

            if ws_end + 1 < len(h_chars):
                next_ch = h_chars[ws_end + 1].get("c", "")
                next_x0 = h_chars[ws_end + 1]["bbox"][0]
                last_sx1 = s_chars[-1]["bbox"][2]
                if next_ch == "/" and (next_x0 - last_sx1) >= 1.5:
                    sp_after = dict(h_chars[ws_end])
                    sp_after["c"] = " "
                    replacement.append(sp_after)
                elif next_ch not in (" ", "/", ",", ".", ";", ":", ")", "]"):
                    sp_after = dict(h_chars[ws_end])
                    sp_after["c"] = " "
                    replacement.append(sp_after)

            h_chars[ws_start : ws_end + 1] = replacement
            lines_to_remove.add(id(s_ln))
            break

    if not lines_to_remove:
        return text_blocks

    cleaned_blocks: list[dict] = []
    for blk in text_blocks:
        if blk.get("type", 0) != 0:
            cleaned_blocks.append(blk)
            continue
        kept_lines = [ln for ln in blk.get("lines", []) if id(ln) not in lines_to_remove]
        if kept_lines:
            blk = dict(blk)
            blk["lines"] = kept_lines
            cleaned_blocks.append(blk)
    return cleaned_blocks


def extract_widget_overlays(
    page: fitz.Page,
) -> list[tuple[bytes, float, float, float, bool]]:
    """Trích xuất hình ảnh con dấu đỏ, chữ ký số và chữ ký nháy từ PDF Signature Widgets (`page.widgets()`).

    Khôi phục kênh trong suốt Alpha (`/SMask`) gốc của XObject và tính chính xác toạ độ trang
    từ ma trận biến đổi `cm` bên trong Form XObject `/AP /N`.
    """
    import re

    doc = page.parent
    if doc is None:
        return []

    overlays: list[tuple[bytes, float, float, float, bool]] = []
    for w in page.widgets() or []:
        if not w.xref:
            continue
        try:
            w_obj = doc.xref_object(w.xref)
        except Exception:
            continue

        ap_match = re.search(r"/AP\s*<<[^>]*?/N\s+(\d+)\s+0\s+R", w_obj, re.S)
        if not ap_match:
            continue

        ap_xref = int(ap_match.group(1))
        visited: set[int] = set()
        queue: list[int] = [ap_xref]
        found_in_widget = False

        while queue and not found_in_widget:
            cur_xref = queue.pop(0)
            if cur_xref in visited:
                continue
            visited.add(cur_xref)
            try:
                obj_str = doc.xref_object(cur_xref)
            except Exception:
                continue

            if "/Type /Page" in obj_str:
                continue

            # Kiểm tra nếu Form XObject hiện tại chứa lệnh vẽ ảnh `/img... Do`
            if "/Subtype /Form" in obj_str and "/XObject" in obj_str:
                try:
                    stream_bytes = doc.xref_stream(cur_xref) or b""
                    stream_txt = stream_bytes.decode("latin1", errors="ignore")
                except Exception:
                    stream_txt = ""

                # Tìm tất cả XObject con được khai báo trong Form này
                xobj_map: dict[str, int] = {}
                for xm in re.finditer(r"/([A-Za-z0-9_.-]+)\s+(\d+)\s+0\s+R", obj_str):
                    name, ref_id = xm.group(1), int(xm.group(2))
                    try:
                        if "/Subtype /Image" in doc.xref_object(ref_id):
                            xobj_map[name] = ref_id
                    except Exception:
                        pass

                if xobj_map:
                    # Chọn ảnh chính (không phải SMask của ảnh khác trong cùng Form)
                    smask_refs: set[int] = set()
                    for img_ref in xobj_map.values():
                        try:
                            im_obj = doc.xref_object(img_ref)
                            sm_m = re.search(r"/SMask\s+(\d+)\s+0\s+R", im_obj)
                            if sm_m:
                                smask_refs.add(int(sm_m.group(1)))
                        except Exception:
                            pass

                    for img_name, img_xref in xobj_map.items():
                        if img_xref in smask_refs and len(xobj_map) > 1:
                            continue
                        try:
                            im_obj = doc.xref_object(img_xref)
                            sm_m = re.search(r"/SMask\s+(\d+)\s+0\s+R", im_obj)
                            smask_xref = int(sm_m.group(1)) if sm_m else None

                            base_pix = fitz.Pixmap(doc, img_xref)
                            if base_pix.colorspace is None or base_pix.colorspace.n != 3:
                                base_pix = fitz.Pixmap(fitz.csRGB, base_pix)
                            if smask_xref:
                                mask_pix = fitz.Pixmap(doc, smask_xref)
                                rgba_pix = fitz.Pixmap(base_pix, mask_pix)
                            else:
                                rgba_pix = base_pix
                            png_bytes = rgba_pix.tobytes("png")
                        except Exception:
                            continue

                        # Tính toạ độ hiển thị chính xác từ BBox và ma trận cm trong stream
                        wx0, wy0, wx1, wy1 = w.rect
                        w_width = max(1.0, wx1 - wx0)
                        w_height = max(1.0, wy1 - wy0)

                        bbox_m = re.search(
                            r"/BBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]",
                            obj_str,
                        )
                        form_w = (
                            max(1.0, float(bbox_m.group(3)) - float(bbox_m.group(1)))
                            if bbox_m
                            else w_width
                        )
                        form_h = (
                            max(1.0, float(bbox_m.group(4)) - float(bbox_m.group(2)))
                            if bbox_m
                            else w_height
                        )
                        scale_x = w_width / form_w
                        scale_y = w_height / form_h

                        cm_m = re.search(
                            rf"([-\d.]+)\s+[-\d.]+\s+[-\d.]+\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+cm\s+/{re.escape(img_name)}\s+Do",
                            stream_txt,
                        )
                        if cm_m:
                            a = abs(float(cm_m.group(1)))
                            d = abs(float(cm_m.group(2)))
                            e = float(cm_m.group(3))
                            f = float(cm_m.group(4))
                            disp_w = a * scale_x
                            disp_h = d * scale_y
                            pos_x = wx0 + e * scale_x
                            pos_y = wy1 - (f + d) * scale_y
                        else:
                            aspect = rgba_pix.width / max(1, rgba_pix.height)
                            disp_w = min(w_width, w_height * aspect)
                            disp_h = disp_w / max(0.05, aspect)
                            pos_x = wx0 + (w_width - disp_w) * 0.5
                            pos_y = wy0 + (w_height - disp_h) * 0.5

                        overlays.append((png_bytes, disp_w, pos_x, pos_y, False))
                        found_in_widget = True
                        break

            for ref_m in re.finditer(r"(\d+)\s+0\s+R", obj_str):
                ref_id = int(ref_m.group(1))
                if ref_id not in visited:
                    queue.append(ref_id)

    return overlays
