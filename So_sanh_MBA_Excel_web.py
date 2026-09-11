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

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(
    page_title="AI Đối Soát Máy Biến Áp",
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
def upload_file_bytes_to_gemini(client, uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    try:
        file = client.files.upload(file=tmp_path)
        while file.state.name == "PROCESSING":
            time.sleep(1.5)
            file = client.files.get(name=file.name)
        return file
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def extract_json(text):
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except Exception:
        return None

# --- GIAO DIỆN CHÍNH ---
st.title("⚡ AI Đối Soát & So Sánh Thông Số Máy Biến Áp (MBA)")
st.caption("Hệ thống thẩm định và đối soát hồ sơ thí nghiệm / tiêu chuẩn TCCS theo chuẩn EVN.")

# Lấy key từ biến môi trường hệ thống hoặc secrets (nếu có cấu hình trước)
env_api_key = os.environ.get("GEMINI_API_KEY", "")
if not env_api_key and "GEMINI_API_KEY" in st.secrets:
    env_api_key = st.secrets["GEMINI_API_KEY"]

# Sidebar cấu hình
with st.sidebar:
    st.header("⚙️ Cấu hình Hệ thống")
    
    # Cho phép người dùng tự nhập Key, mặc định là chuỗi rỗng để không bị lộ
    api_key_input = st.text_input(
        "Nhập Gemini API Key của bạn:", 
        value=env_api_key, 
        type="password",
        placeholder="Dán mã API Key vào đây (AIza... hoặc AQ...)",
        help="Khóa API được xử lý an toàn trong phiên làm việc hiện tại và không lưu cố định vào mã nguồn."
    )
    
    if not api_key_input:
        st.info("💡 Bạn cần cung cấp API Key để ứng dụng có thể kết nối với mô hình Gemini.")
        
    model_name = st.selectbox("Mô hình AI:", ["gemini-2.5-flash", "gemini-2.5-pro"], index=0)
    
    st.divider()
    st.subheader("📚 Lịch sử bộ nhớ")
    hist = load_knowledge_base()
    st.write(f"Số phiên đã ghi nhận: **{len(hist)}**")
    if st.button("Xóa bộ nhớ học tập"):
        if os.path.exists(KNOWLEDGE_FILE):
            os.remove(KNOWLEDGE_FILE)
            st.success("Đã làm sạch bộ nhớ!")
            st.rerun()

# 2 Cột tải tài liệu
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. File Gốc (A)")
    file_a = st.file_uploader("TCCS 01 / TCCS 10 / Biên bản chuẩn", type=["pdf"], key="file_a")

with col2:
    st.subheader("2. File Đối Chiếu (B)")
    file_b = st.file_uploader("Biên bản kiểm định / thử nghiệm", type=["pdf"], key="file_b")

# Nút Thẩm định và Xử lý
if st.button("📊 BẮT ĐẦU ĐỐI SOÁT & XUẤT BÁO CÁO", type="primary", use_container_width=True):
    # Kiểm tra API Key chặt chẽ trước khi xử lý
    if not api_key_input or not api_key_input.strip():
        st.error("❌ Vui lòng nhập Gemini API Key ở bảng điều khiển bên trái trước khi bắt đầu!")
    elif not file_a or not file_b:
        st.error("❌ Vui lòng tải lên đầy đủ cả File Gốc (A) và File Đối Chiếu (B)!")
    else:
        try:
            # Khởi tạo client bằng key do người dùng nhập vào
            client = genai.Client(api_key=api_key_input.strip())
            
            with st.status("Đang tiến hành xử lý...", expanded=True) as status:
                # Bước 1: Nạp File
                st.write("⏳ Đang nạp tệp lên AI Cloud...")
                pdf_1 = upload_file_bytes_to_gemini(client, file_a)
                pdf_2 = upload_file_bytes_to_gemini(client, file_b)
                
                # Bước 2: Thẩm định sơ bộ File A
                st.write("🔍 Đang thẩm định tính hợp lệ của File Gốc...")
                prompt_a = """
                Hãy phân tích tài liệu PDF này và cho biết:
                Tài liệu này có phải là Tiêu chuẩn cơ sở MBA (TCCS 01, TCCS 10...) hoặc Biên bản kiểm định/thí nghiệm MBA không?
                YÊU CẦU TRẢ VỀ DUY NHẤT ĐỊNH DẠNG JSON:
                {"is_valid": true/false, "doc_type": "TCCS_01/TCCS_10/BBTN_MBA/OTHER", "reason": "giải thích ngắn"}
                """
                res_a = client.chats.create(
                    model=model_name,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                ).send_message(message=[pdf_1, prompt_a])
                data_a = extract_json(res_a.text)
                
                if not (data_a and data_a.get("is_valid")):
                    status.update(label="File A không hợp lệ!", state="error")
                    st.error(f"❌ Lỗi File Gốc: {data_a.get('reason') if data_a else 'Sai định dạng'}")
                    st.stop()
                st.success(f"✅ File Gốc hợp lệ: {data_a.get('doc_type')} ({data_a.get('reason')})")

                # Bước 3: Thẩm định sơ bộ File B
                st.write("🔍 Đang thẩm định tính hợp lệ của File Đối Chiếu...")
                prompt_b = """
                Hãy kiểm tra xem đây có phải là Biên bản kiểm định/thử nghiệm máy biến áp hay không?
                YÊU CẦU TRẢ VỀ DUY NHẤT ĐỊNH DẠNG JSON:
                {"is_bbtn_mba": true/false, "reason": "giải thích ngắn"}
                """
                res_b = client.chats.create(
                    model=model_name,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                ).send_message(message=[pdf_2, prompt_b])
                data_b = extract_json(res_b.text)
                
                if not (data_b and data_b.get("is_bbtn_mba")):
                    status.update(label="File B không hợp lệ!", state="error")
                    st.error(f"❌ Lỗi File Đối Chiếu: {data_b.get('reason') if data_b else 'Sai định dạng'}")
                    st.stop()
                st.success(f"✅ File Đối Chiếu hợp lệ: {data_b.get('reason')}")

                # Bước 4: Chạy đối soát chi tiết
                st.write("🧠 AI Chuyên gia đang thực hiện đối soát chi tiết & đánh giá dung sai...")
                
                hist_items = load_knowledge_base()
                history_context = ""
                if hist_items:
                    history_context = f"\n[LỊCH SỬ ĐỐI SOÁT TRƯỚC ĐÓ]:\n{json.dumps(hist_items[-3:], ensure_ascii=False)}"

                system_instruction = """
                Bạn là Chuyên gia Cao cấp về Thí nghiệm & Kiểm định Máy Biến Áp Phân Phối (EVN/TCCS).
                Nhiệm vụ của bạn: Đối soát toàn diện các hạng mục đo lường giữa File 1 (Chuẩn/TCCS) với File 2 (Biên bản kiểm định).
                Tiêu chuẩn kiểm tra:
                1. Tỷ số biến đổi điện áp (K) và Tổ đấu dây.
                2. Điện trở một chiều (DC) các cuộn dây Cao áp và Hạ áp, độ lệch pha (%).
                3. Thử nghiệm không tải: Tổn hao (Po), Dòng điện không tải (Io%).
                4. Thử nghiệm ngắn mạch: Tổn hao (Pk ở 75°C), Điện áp ngắn mạch (Uk%).
                5. Điện trở cách điện cuộn dây (R60s, R15s, KHA = R60/R15).
                6. Thử nghiệm đặc tính cách điện của dầu: Điện áp đánh thủng (kV), tạp chất.
                """

                prompt_main = f"""
                Dựa trên File 1 và File 2, hãy thực hiện đối soát chi tiết và phát hiện mọi điểm bất thường, sai khác hoặc vượt ngưỡng dung sai cho phép.
                {history_context}

                YÊU CẦU TRẢ VỀ ĐỊNH DẠNG JSON NGUYÊN KHỐI DUY NHẤT theo đúng schema:
                {{
                  "Summary": [
                    {{"Thong_tin": "...", "File_chuan_A": "...", "File_doi_chieu_B": "...", "Ket_luan_so_bo": "..."}}
                  ],
                  "Comparison": [
                    {{"Hang_muc": "...", "Parameter": "...", "Unit": "...", "Gia_tri_goc": "...", "Gia_tri_doi_chieu": "...", "Do_lech_phan_tram": "...", "Nguong_cho_phep": "...", "Result": "ĐẠT / KHÔNG ĐẠT / KHÁC BIỆT"}}
                  ],
                  "Discrepancy_Alert": [
                    {{"Warning": "...", "Detail": "..."}}
                  ]
                }}
                """

                chat = client.chats.create(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json"
                    )
                )
                res_main = chat.send_message(message=[pdf_1, pdf_2, prompt_main])
                data_result = extract_json(res_main.text)
                
                status.update(label="Đối soát hoàn tất!", state="complete")

            # Bước 5: Hiển thị kết quả ra Web
            if data_result:
                save_to_knowledge_base({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "file_a": file_a.name,
                    "file_b": file_b.name,
                    "alerts_summary": data_result.get("Discrepancy_Alert", [])[:3]
                })

                st.subheader("📋 Cảnh báo & Sai lệch chính (Discrepancy Alert)")
                alerts = data_result.get("Discrepancy_Alert", [])
                if alerts:
                    for alert in alerts:
                        st.warning(f"**{alert.get('Warning')}**: {alert.get('Detail')}")
                else:
                    st.success("Không phát hiện sai lệch bất thường vượt ngưỡng cho phép.")

                # Tab hiển thị chi tiết
                tab1, tab2 = st.tabs(["📊 Bảng So Sánh Chi Tiết", "📄 Thông Tin Chung"])
                
                with tab1:
                    df_comp = pd.DataFrame(data_result.get("Comparison", []))
                    if not df_comp.empty:
                        st.dataframe(df_comp, use_container_width=True)
                    else:
                        st.info("Không có dữ liệu đối chiếu tham số.")

                with tab2:
                    df_sum = pd.DataFrame(data_result.get("Summary", []))
                    if not df_sum.empty:
                        st.dataframe(df_sum, use_container_width=True)
                    else:
                        st.info("Không có dữ liệu tóm tắt.")

                # Bước 6: Tạo nút tải Excel trực tiếp
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
                    label="📥 TẢI VỀ BÁO CÁO EXCEL",
                    data=excel_buffer.getvalue(),
                    file_name=f"Bao_Cao_Doi_Soat_MBA_{int(time.time())}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )

            else:
                st.error("Không thể phân tích dữ liệu JSON trả về từ mô hình.")
                st.text_area("Dữ liệu phản hồi gốc:", res_main.text, height=200)

        except Exception as e:
            st.error(f"Đã xảy ra lỗi kết nối hoặc xử lý: {str(e)}")