import streamlit as st
import os
import time
import json
import re
import tempfile
import io
import pandas as pd
from google import genai
from google.genai import types
import unicodedata


# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(
    page_title="AI Đối Soát & Thẩm Định MBA Phân Phối",
    page_icon="⚡",
    layout="wide"
)

KNOWLEDGE_FILE = "knowledge_mba_history.json"

# --- HÀM TIỆN ÍCH LỊCH SỬ HỌC TẬP ---
def load_knowledge_base():
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_to_knowledge_base(record_info):
    try:
        history = load_knowledge_base()
        history.append(record_info)
        with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
            json.dump(history[-20:], f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.warning(f"Không thể ghi nhận tri thức học lịch sử: {e}")

# --- QUẢN LÝ TẢI FILE LÊN GEMINI ---

def clean_api_key(key: str) -> str:
    if not key:
        return ""
    # Chuẩn hóa về dạng NFKD để tách các ký tự đồng dạng (homoglyph)
    normalized = unicodedata.normalize('NFKD', key.strip())
    # Loại bỏ triệt để mọi ký tự nằm ngoài bảng mã ASCII tiêu chuẩn
    return normalized.encode('ascii', 'ignore').decode('ascii')

def sanitize_api_key(key: str) -> str:
    if not key:
        return ""
    # Chuyển đổi các ký tự trông giống chữ A, B Cyrillic về ASCII hoặc lọc bỏ ký tự lạ
    key = key.strip().replace('\u0410', 'A').replace('\u0430', 'a')
    return key.encode('ascii', 'ignore').decode('ascii')

def make_pdf_part(uploaded_file):
    return types.Part.from_bytes(
        data=uploaded_file.getvalue(),
        mime_type="application/pdf"
    )

def extract_json(text):
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except Exception:
        return None

# --- KHỞI TẠO BIẾN TRẠNG THÁI (SESSION STATE) ---
if "file_a_status" not in st.session_state:
    st.session_state.file_a_status = {"valid": False, "msg": "", "info": None, "last_name": ""}
if "file_b_status" not in st.session_state:
    st.session_state.file_b_status = {"valid": False, "msg": "", "info": None, "last_name": ""}

# --- GIAO DIỆN CHÍNH ---
st.title("⚡ AI Đối Soát & Thẩm Định Chuyên Sâu Máy Biến Áp (MBA)")
st.caption("Hệ thống thẩm định hồ sơ kỹ thuật & đối soát biên bản thí nghiệm MBA theo TCVN 6306 / IEC 60076 & Tiêu chuẩn EVN (TCCS 01, TCCS 10).")

# Cấu hình API Key và Model
env_api_key = os.environ.get("GEMINI_API_KEY", "")
if not env_api_key and "GEMINI_API_KEY" in st.secrets:
    env_api_key = st.secrets["GEMINI_API_KEY"]

with st.sidebar:
    st.header("⚙️ Cấu hình Hệ thống")
    api_key_input = st.text_input(
        "Gemini API Key:", 
        value=env_api_key, 
        type="password",
        placeholder="Dán API Key vào đây (AIza... hoặc AQ...)",
        help="Khóa API được xử lý an toàn trong phiên làm việc hiện tại."
    )
    
    model_name = st.selectbox(
        "Mô hình AI:", 
        ["gemini-2.5-flash", "gemini-3.6-flash"], 
        index=0
    )
    
    st.divider()
    st.subheader("📚 Bộ nhớ đối soát lịch sử")
    hist = load_knowledge_base()
    st.write(f"Số phiên ghi nhớ: **{len(hist)}**")
    if st.button("Xóa bộ nhớ học tập"):
        if os.path.exists(KNOWLEDGE_FILE):
            os.remove(KNOWLEDGE_FILE)
            st.success("Đã làm sạch bộ nhớ!")
            st.rerun()

# --- HÀM THẨM ĐỊNH FILE TỨC THÌ KHI TẢI LÊN ---
def verify_file_a(uploaded_file, client):
    with st.spinner("🔍 Đang thẩm định tính pháp lý & kỹ thuật của File Gốc..."):
        try:
            pdf_part = make_pdf_part(uploaded_file)
            prompt = """
            Bạn là Kỹ sư Trưởng thẩm định hồ sơ kỹ thuật lưới điện và thiết bị phân phối EVN.
            Hãy kiểm tra tài liệu PDF này có thuộc một trong các loại tài liệu chuẩn sau không:
            1. Tiêu chuẩn kỹ thuật máy biến áp phân phối: TCCS 01, TCCS 10 (EVN SPC, EVN CPC, EVN NPC, EVNHCMC, EVNHANOI) hoặc quy cách kỹ thuật máy biến áp tương đương.
            2. Biên bản thử nghiệm/thí nghiệm xuất xưởng chuẩn (Routine Test Report) của nhà sản xuất máy biến áp (MBA/máy biến thế).

            YÊU CẦU TRẢ VỀ DUY NHẤT ĐỊNH DẠNG JSON:
            {
                "is_valid": true/false,
                "doc_type": "TCCS_01" hoặc "TCCS_10" hoặc "BBTN_CHUAN" hoặc "OTHER",
                "reason": "Giải thích chi tiết căn cứ xác định (Tên tiêu chuẩn, Số quyết định ban hành, Mã hiệu MBA, Tên đơn vị lập...)"
            }
            """
            res = client.models.generate_content(
                model=model_name,
                contents=[pdf_part, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return extract_json(res.text)
        except Exception as e:
            return {"is_valid": False, "reason": f"Lỗi thẩm định: {str(e)}"}

def verify_file_b(uploaded_file, client):
    with st.spinner("🔍 Đang kiểm tra tính hợp lệ của Biên bản kiểm định..."):
        try:
            pdf_part = make_pdf_part(uploaded_file)
            prompt = """
            Bạn là Chuyên viên Thử nghiệm Cao cấp của Trung tâm Thí nghiệm điện (ETC).
            Hãy kiểm tra tài liệu PDF này có phải là Biên bản kiểm định / Biên bản thử nghiệm / Thí nghiệm kỹ thuật của MÁY BIẾN ÁP (máy biến thế) hay không?
            (Không chấp nhận biên bản của máy cắt, TU, TI, chống sét van hoặc thiết bị khác).

            YÊU CẦU TRẢ VỀ DUY NHẤT ĐỊNH DẠNG JSON:
            {
                "is_bbtn_mba": true/false,
                "reason": "Giải thích chi tiết (Tên trạm/nhà máy, số chế tạo MBA, đơn vị thí nghiệm, các hạng mục đo lường được nhận dạng...)"
            }
            """
            res = client.models.generate_content(
                model=model_name,
                contents=[pdf_part, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return extract_json(res.text)
        except Exception as e:
            return {"is_bbtn_mba": False, "reason": f"Lỗi thẩm định: {str(e)}"}
            

# --- BỐ TRÍ 2 KHUNG CHỌN TỆP ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. File Gốc (A)")
    file_a = st.file_uploader("Chọn Tiêu chuẩn kỹ thuật (TCCS 01 / TCCS 10) hoặc Biên bản MBA chuẩn", type=["pdf"], key="uploader_a")
    
    if file_a:
        if file_a.name != st.session_state.file_a_status["last_name"]:
            if not api_key_input.strip():
                st.error("⚠️ Vui lòng nhập Gemini API Key ở cột trái trước khi tải tài liệu!")
            else:
                client_temp = genai.Client(api_key=api_key_input.strip())
                res_check = verify_file_a(file_a, client_temp)
                if res_check and res_check.get("is_valid"):
                    st.session_state.file_a_status = {
                        "valid": True, 
                        "msg": f"✅ HỢP LỆ: {res_check.get('doc_type')} - {res_check.get('reason')}", 
                        "info": res_check, 
                        "last_name": file_a.name
                    }
                else:
                    reason = res_check.get("reason") if res_check else "Không nhận diện được định dạng TCCS/MBA"
                    st.session_state.file_a_status = {
                        "valid": False, 
                        "msg": f"❌ KHÔNG HỢP LỆ: Tệp vừa chọn không phải là TCCS 01, TCCS 10 hoặc Biên bản MBA chuẩn!\n\nLý do: {reason}\n👉 Vui lòng chọn lại đúng tệp tiêu chuẩn hoặc biên bản thử nghiệm MBA.", 
                        "info": None, 
                        "last_name": file_a.name
                    }
        
        # Hiển thị kết quả thẩm định File A
        if st.session_state.file_a_status["valid"]:
            st.success(st.session_state.file_a_status["msg"])
        else:
            st.error(st.session_state.file_a_status["msg"])
    else:
        st.session_state.file_a_status = {"valid": False, "msg": "", "info": None, "last_name": ""}

with col2:
    st.subheader("2. File Đối Chiếu (B)")
    file_b = st.file_uploader("Chọn Biên bản kiểm định / thử nghiệm máy biến áp", type=["pdf"], key="uploader_b")
    
    if file_b:
        if file_b.name != st.session_state.file_b_status["last_name"]:
            if not api_key_input.strip():
                st.error("⚠️ Vui lòng nhập Gemini API Key ở cột trái trước khi tải tài liệu!")
            else:
                client_temp = genai.Client(api_key=api_key_input.strip())
                res_check = verify_file_b(file_b, client_temp)
                if res_check and res_check.get("is_bbtn_mba"):
                    st.session_state.file_b_status = {
                        "valid": True, 
                        "msg": f"✅ HỢP LỆ: Biên bản thử nghiệm MBA - {res_check.get('reason')}", 
                        "info": res_check, 
                        "last_name": file_b.name
                    }
                else:
                    reason = res_check.get("reason") if res_check else "Không nhận diện được biên bản kiểm định MBA"
                    st.session_state.file_b_status = {
                        "valid": False, 
                        "msg": f"❌ KHÔNG HỢP LỆ: Tệp vừa chọn KHÔNG PHẢI là Biên bản kiểm định/thí nghiệm máy biến áp!\n\nLý do: {reason}\n👉 Vui lòng chọn lại đúng tệp biên bản kiểm định MBA.", 
                        "info": None, 
                        "last_name": file_b.name
                    }
        
        # Hiển thị kết quả thẩm định File B
        if st.session_state.file_b_status["valid"]:
            st.success(st.session_state.file_b_status["msg"])
        else:
            st.error(st.session_state.file_b_status["msg"])
    else:
        st.session_state.file_b_status = {"valid": False, "msg": "", "info": None, "last_name": ""}

st.write("---")

# Kiểm tra điều kiện mở khóa nút chạy
can_proceed = st.session_state.file_a_status["valid"] and st.session_state.file_b_status["valid"]

if not can_proceed:
    st.info("💡 **Trạng thái:** Nút phân tích sẽ tự động kích hoạt sau khi cả 2 tệp đầu vào được AI thẩm định hợp lệ.")

# --- NÚT BẮT ĐẦU ĐỐI SOÁT ---
if st.button("📊 BẮT ĐẦU ĐỐI SOÁT CHUYÊN SÂU & XUẤT EXCEL", type="primary", disabled=not can_proceed, use_container_width=True):
    try:
        sanitized_key = clean_api_key(api_key_input)
        client = genai.Client(api_key=sanitized_key)
        
        with st.status("🚀 Đang tiến hành đối soát và phân tích chuyên gia...", expanded=True) as status:
            st.write("⏳ Đang đồng bộ tài liệu lên AI Analysis Engine...")
            pdf_1 = make_pdf_part(file_a)
            pdf_2 = make_pdf_part(file_b)
          
            st.write("🧠 AI Chuyên gia Thí nghiệm điện đang thẩm định toàn diện các hạng mục kỹ thuật...")
            
            hist_items = load_knowledge_base()
            history_context = ""
            if hist_items:
                history_context = f"\n[LỊCH SỬ ĐỐI SOÁT TRƯỚC ĐÓ ĐỂ ĐẢM BẢO TÍNH NHẤT QUÁN VỀ TIÊU CHÍ ĐÁNH GIÁ VÀ DUNG SAI]:\n{json.dumps(hist_items[-3:], ensure_ascii=False)}"

            # Prompt Chuyên gia Thử nghiệm MBA Phân phối bậc cao
            system_instruction = """
            Bạn là Kỹ sư Trưởng Thí nghiệm & Thẩm định Máy Biến Áp Phân Phối (cấp điện áp đến 35kV theo tiêu chuẩn EVN và TCVN 6306 / IEC 60076).
            Nhiệm vụ của bạn: Đối soát toàn diện, chi tiết từng tham số đo đạc giữa Hồ sơ kỹ thuật / Tiêu chuẩn cơ sở chuẩn (File 1) với Biên bản kiểm định / Thử nghiệm hiện trường thực tế (File 2).

            QUY TẮC ĐÁNH GIÁ CHUYÊN MÔN:
            1. TỶ SỐ BIẾN ĐỔI (K) & TỔ ĐẤU DÂY:
               - Kiểm tra tỷ số biến ở TẤT CẢ các nấc phân áp (Nấc 1, 2, 3, 4, 5...). Dung sai cho phép theo IEC 60076 không vượt quá ±0.5% so với tỷ số danh định.
               - Đối soát đúng tổ đấu dây quy định (Dyn11, Yyn0...).
            2. ĐIỆN TRỞ MỘT CHIỀU (DC RESISTANCE):
               - Kiểm tra cuộn Cao áp và Hạ áp.
               - Độ lệch điện trở một chiều giữa các pha: Không vượt quá 2%. Đánh giá độ đồng đều giữa các nấc.
            3. THỬ NGHIỆM KHÔNG TẢI (NO-LOAD TEST):
               - Tổn hao không tải (Po) ở tần số và điện áp danh định (Un): So sánh với ngưỡng TCCS 01 / TCCS 10 (dung sai Po tối đa +15%).
               - Dòng điện không tải (Io%): Dung sai tối đa +30% giá trị cam kết.
            4. THỬ NGHIỆM NGẮN MẠCH (LOAD LOSS / SHORT-CIRCUIT TEST):
               - Tổn hao ngắn mạch (Pk) đã quy đổi về nhiệt độ chuẩn 75°C: So sánh với TCCS (dung sai +15%).
               - Điện áp ngắn mạch (Uk%): Dung sai thông thường ±10% giá trị danh định.
            5. TỔNG TỔN HAO CÔNG SUẤT (TOTAL LOSSES - BẮT BUỘC ĐỐI SOÁT):
               - Xác định Tổng tổn hao thực tế: P_tong = Po + Pk (Pk tính ở 75°C).
               - Xác định Tổng tổn hao chuẩn/danh định theo TCCS: P_tong_chuan = Po_chuan + Pk_chuan.
               - Đánh giá dung sai kép theo IEC 60076 / Quy định EVN:
                 + Từng tổn hao riêng lẻ (Po hoặc Pk) được phép lệch tối đa +15%.
                 + TUY NHIÊN TỔNG TỔN HAO (Po + Pk) TUYỆT ĐỐI KHÔNG ĐƯỢC VƯỢT QUÁ +10% so với Tổng tổn hao chuẩn.
                 + Nếu tổng tổn hao vượt +10%, lập tức đánh giá "KHÔNG ĐẠT" và đưa vào Discrepancy_Alert.
            6. ĐIỆN TRỞ CÁCH ĐIỆN & HỆ SỐ HẤP THỤ (INSULATION RESISTANCE):
               - R60s và Hệ số hấp thụ KHA = R60s / R15s (Yêu cầu KHA ≥ 1.3 đối với MBA ngâm dầu).
            7. THỬ NGHIỆM ĐẶC TÍNH DẦU CÁCH ĐIỆN:
               - Điện áp đánh thủng dầu (kV/2.5mm) ≥ 40kV (hoặc ≥ 35kV tùy cấp điện áp).
            8. ĐỘ BỀN CÁCH ĐIỆN:
               - Điện áp tăng cao tần số công nghiệp (AC withstand voltage) cuộn CA và HA trong 1 phút.
            """

            prompt_main = f"""
            Dựa trên File 1 (Chuẩn / TCCS) và File 2 (Biên bản kiểm định đối chiếu), hãy thực hiện đối soát chi tiết và phát hiện mọi điểm bất thường, sai khác hoặc vượt ngưỡng dung sai cho phép.
            ĐẶC BIỆT chú ý tính toán và so sánh chi tiết TỔNG TỔN HAO (Po + Pk ở 75°C) xem có vượt ngưỡng dung sai +10% hay không.
            {history_context}

            YÊU CẦU TRẢ VỀ ĐỊNH DẠNG JSON NGUYÊN KHỐI DUY NHẤT theo đúng schema:
            {{
              "Summary": [
                {{
                  "Thong_tin": "Trạm / Vị trí / Mã trạm / Mã MBA / Số chế tạo / Công suất danh định (kVA) / Cấp điện áp (kV) / Tổ đấu dây",
                  "File_chuan_A": "Thông số danh định tại File 1",
                  "File_doi_chieu_B": "Thông số đo đạc thực tế tại File 2",
                  "Ket_luan_so_bo": "Khớp / Sai lệch / Cần lưu ý"
                }}
              ],
              "Comparison": [
                {{
                  "Hang_muc": "Tên hạng mục thí nghiệm (Gồm: Tỷ số biến, Điện trở DC Cao áp, Điện trở DC Hạ áp, Tổn hao Po, Dòng không tải Io, Tổn hao ngắn mạch Pk 75°C, TỔNG TỔN HAO (Po + Pk), Điện áp ngắn mạch Uk%, Điện trở cách điện R60, Hệ số KHA, Độ cách điện của dầu...)",
                  "Parameter": "Tham số cụ thể (Ví dụ: 'Tổng Po + Pk ở 75°C', Nấc phân áp, Pha A-B...)",
                  "Unit": "Đơn vị (W, kW, V, A, %, Ohm...)",
                  "Gia_tri_goc": "Số liệu chuẩn từ TCCS hoặc File 1",
                  "Gia_tri_doi_chieu": "Số liệu đo đạc thực tế trong File 2",
                  "Do_lech_phan_tram": "Độ lệch tính bằng % hoặc Ghi chú chênh lệch",
                  "Nguong_cho_phep": "Ngưỡng quy định theo TCCS / TCVN / IEC (Ví dụ: Tổng tổn hao không quá +10%)",
                  "Result": "ĐẠT / KHÔNG ĐẠT / KHÁC BIỆT / CẢNH BÁO"
                }}
              ],
              "Discrepancy_Alert": [
                {{
                  "Warning": "Tên thông số/hạng mục sai lệch hoặc bất thường (đặc biệt nếu Tổng tổn hao vượt +10%)",
                  "Detail": "Đánh giá chi tiết rủi ro tổn thất kỹ thuật, quá nhiệt gây suy giảm tuổi thọ máy và khuyến nghị vận hành"
                }}
              ]
            }}
            Lưu ý: Bóc tách đầy đủ tất cả các trang, không bỏ sót bất kỳ hạng mục đo lường nào có trong biên bản.
            """

            chat = client.chats.create(
                model=model_name,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            
            res_main = client.models.generate_content(
                model=model_name,
                contents=[pdf_1, pdf_2, prompt_main],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            data_result = extract_json(res_main.text)
                   
            status.update(label="Hoàn tất phân tích chuyên gia!", state="complete")

        if data_result:
            # Lưu học tập vào bộ nhớ
            save_to_knowledge_base({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "file_a": file_a.name,
                "file_b": file_b.name,
                "alerts_summary": data_result.get("Discrepancy_Alert", [])[:3]
            })

            # Hiển thị cảnh báo sai lệch
            st.subheader("⚠️ Cảnh Báo Kỹ Thuật & Khuyến Nghị Vận Hành")
            alerts = data_result.get("Discrepancy_Alert", [])
            if alerts:
                for alert in alerts:
                    st.error(f"**{alert.get('Warning')}**: {alert.get('Detail')}")
            else:
                st.success("✅ Toàn bộ thông số đo đạc trong biên bản đều nằm trong giới hạn dung sai cho phép của tiêu chuẩn.")

            # Tab chi tiết
            tab1, tab2 = st.tabs(["📊 Bảng Đối Soát Chi Tiết", "📄 Thông Tin Thiết Bị MBA"])
            
            with tab1:
                df_comp = pd.DataFrame(data_result.get("Comparison", []))
                if not df_comp.empty:
                    # Đổi màu hiển thị kết quả nếu muốn
                    st.dataframe(df_comp, use_container_width=True)
                else:
                    st.info("Không có dữ liệu đối chiếu thông số.")

            with tab2:
                df_sum = pd.DataFrame(data_result.get("Summary", []))
                if not df_sum.empty:
                    st.dataframe(df_sum, use_container_width=True)
                else:
                    st.info("Không có dữ liệu tổng quan.")

            # Xuất tệp Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                for sheet_name, content in data_result.items():
                    display_name = sheet_name.replace("_", " ")[:31]
                    df_sheet = pd.DataFrame(content)
                    df_sheet.to_excel(writer, sheet_name=display_name, index=False)
                    worksheet = writer.sheets[display_name]
                    for col in worksheet.columns:
                        worksheet.column_dimensions[col[0].column_letter].width = 28

            st.download_button(
                label="📥 TẢI VỀ BÁO CÁO ĐỐI SOÁT EXCEL",
                data=excel_buffer.getvalue(),
                file_name=f"Bao_Cao_Doi_Soat_MBA_{int(time.time())}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        else:
            st.error("Không thể giải mã dữ liệu JSON phản hồi từ AI.")
            st.text_area("Phản hồi thô:", res_main.text, height=200)

    except Exception as e:
        st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {str(e)}")
