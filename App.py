import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import io
import os
from datetime import datetime
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cấu hình trang
st.set_page_config(
    page_title="UniProt 3D Structure Extractor",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS tùy chỉnh
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 1rem;
        font-weight: bold;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
 
    .progress-detail {
        background: #e3f2fd;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 3px solid #2196f3;
    }
    .success-metric {
        background: #d4edda;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        margin: 0.5rem;
        border: 1px solid #c3e6cb;
    }
    .error-metric {
        background: #f8d7da;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        margin: 0.5rem;
        border: 1px solid #f5c6cb;
    }
   
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 25px;
        font-weight: bold;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    .time-estimate {
        background: #fff3cd;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #ffc107;
    }
</style>
""", unsafe_allow_html=True)

def create_driver():
    """Tạo Chrome driver với cấu hình tối ưu"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        try:
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e2:
            logger.error(f"Không thể tạo driver: {str(e2)}")
            return None

def get_entry_from_uniprot_selenium(gene_id, entry_name):
    """Lấy Entry ID từ UniProt - giống hệt source code Colab"""
    url = f"https://www.uniprot.org/uniprotkb?query={gene_id}"
    
    driver = create_driver()
    if not driver:
        return None
    
    try:
        driver.get(url)
        
        # Chờ bảng tải - giống Colab
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "data-table"))
        )
        
        # Chấp nhận cookie - giống Colab
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I agree, dismiss this banner')]"))
            )
            cookie_button.click()
        except:
            pass
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm bảng chính xác như Colab
        table = soup.find('table', class_='hotjar-margin Anr5j data-table')
        if not table:
            return None
        
        tbody = table.find('tbody', translate='no')
        if not tbody:
            return None
        
        rows = tbody.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) > 3:
                current_entry_name = cols[3].text.strip()
                if current_entry_name == entry_name:
                    entry = cols[1].text.strip()
                    return entry
        return None
        
    except Exception as e:
        logger.error(f"Lỗi khi xử lý {gene_id}: {str(e)}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

def extract_3d_structure_table(final_url, query, entry_name):
    """Lấy thông tin từ bảng 3D structure - cải thiện để trả về đầy đủ dữ liệu như Colab"""
    driver = create_driver()
    if not driver:
        return None
    
    try:
        driver.get(final_url)
        time.sleep(5)
        
        # Chấp nhận cookie
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I agree, dismiss this banner')]"))
            )
            cookie_button.click()
        except:
            pass
        
        time.sleep(3)
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm bảng 3D structure - cải thiện logic tìm kiếm
        table = None
        tables = soup.find_all('table')
        
        # Tìm bảng có header chứa các từ khóa 3D structure
        structure_keywords = ['SOURCE', 'IDENTIFIER', 'METHOD', 'RESOLUTION', 'CHAIN', 'POSITIONS', 'LINKS']
        
        for t in tables:
            headers = []
            thead = t.find('thead')
            if thead:
                header_cells = thead.find_all(['th', 'td'])
                headers = [cell.get_text(strip=True).upper() for cell in header_cells]
            else:
                first_row = t.find('tr')
                if first_row:
                    header_cells = first_row.find_all(['th', 'td'])
                    headers = [cell.get_text(strip=True).upper() for cell in header_cells]
            
            # Kiểm tra nếu có ít nhất 3 keywords trong headers
            matching_keywords = sum(1 for keyword in structure_keywords if keyword in ' '.join(headers))
            if matching_keywords >= 3:
                table = t
                break
        
        # Nếu không tìm thấy bảng theo keywords, tìm bảng chứa AlphaFold hoặc PDB
        if not table:
            for t in tables:
                table_text = t.get_text().upper()
                if ('ALPHAFOLD' in table_text or 'PDB' in table_text or 'AF-' in table_text) and len(t.find_all('tr')) > 1:
                    table = t
                    break
        
        if not table:
            logger.warning(f"Không tìm thấy bảng 3D structure cho {query}")
            return None
        
        # Lấy headers chính xác
        headers = []
        thead = table.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    header_text = th.get_text(strip=True)
                    if header_text:  # Chỉ lấy header không rỗng
                        headers.append(header_text)
        
        # Nếu không có thead, lấy từ row đầu tiên
        if not headers:
            first_row = table.find('tr')
            if first_row:
                header_cells = first_row.find_all(['th', 'td'])
                for cell in header_cells:
                    header_text = cell.get_text(strip=True)
                    if header_text:
                        headers.append(header_text)
        
        # Lấy dữ liệu từ tbody
        data = []
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            all_rows = table.find_all('tr')
            # Bỏ qua header row nếu có
            if all_rows and headers:
                rows = all_rows[1:]
            else:
                rows = all_rows
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = []
            
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                
                # Lấy tất cả links trong cell
                links = cell.find_all('a')
                if links:
                    link_urls = []
                    for link in links:
                        href = link.get('href', '')
                        if href:
                            # Xử lý URL đầy đủ
                            if href.startswith('/'):
                                href = 'https://www.uniprot.org' + href
                            elif not href.startswith('http'):
                                href = 'https://www.uniprot.org/' + href
                            link_urls.append(href)
                    
                    if link_urls:
                        # Thêm links vào cuối cell text
                        cell_text = f"{cell_text} | Links: {'; '.join(link_urls)}"
                
                row_data.append(cell_text)
            
            # Chỉ thêm row có dữ liệu
            if row_data and any(cell.strip() for cell in row_data):
                # Đảm bảo số cột khớp với headers
                while len(row_data) < len(headers):
                    row_data.append("")
                
                # Thêm Query và Entry Name vào đầu
                full_row = [query, entry_name] + row_data[:len(headers)]
                data.append(full_row)
        
        if data:
            # Thêm Query và Entry Name vào headers
            full_headers = ['Query', 'Entry Name'] + headers
            logger.info(f"Lấy được {len(data)} dòng dữ liệu cho {query}")
            return data, full_headers
        else:
            logger.warning(f"Không có dữ liệu cho {query}")
            return None
            
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu 3D structure cho {query}: {str(e)}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

def calculate_time_estimate(total_items, current_item, start_time):
    """Tính toán thời gian ước tính hoàn thành"""
    if current_item == 0:
        return "Đang tính toán..."
    
    elapsed_time = time.time() - start_time
    avg_time_per_item = elapsed_time / current_item
    remaining_items = total_items - current_item
    estimated_remaining = remaining_items * avg_time_per_item
    
    # Chuyển đổi thành phút và giây
    minutes = int(estimated_remaining // 60)
    seconds = int(estimated_remaining % 60)
    
    if minutes > 0:
        return f"Còn khoảng {minutes} phút {seconds} giây"
    else:
        return f"Còn khoảng {seconds} giây"

def process_complete_workflow(df_input):
    """Xử lý toàn bộ workflow với progress tracking chi tiết"""
    
    # Container cho progress
    progress_container = st.container()
    
    with progress_container:
        st.markdown('<div class="progress-container">', unsafe_allow_html=True)
        st.markdown("### 🔄 Đang xử lý dữ liệu...")
        
        # Progress tracking
        overall_progress = st.progress(0)
        current_step = st.empty()
        step_progress = st.progress(0)
        status_text = st.empty()
        time_estimate = st.empty()
        
        # Thống kê real-time
        stats_container = st.container()
        
        start_time = time.time()
        
        # Bước 1: Lấy Entry IDs
        current_step.markdown("**🔍 Bước 1/2: Lấy Entry IDs từ UniProt**")
        
        results = []
        total_rows = len(df_input)
        success_count = 0
        
        for index, row in df_input.iterrows():
            query = str(row['Query']).strip()
            entry_name = str(row['Entry Name']).strip()
            
            # Cập nhật progress
            current_progress = (index + 1) / total_rows
            step_progress.progress(current_progress)
            overall_progress.progress(current_progress * 0.4)  # 40% cho bước 1
            
            # Cập nhật status và time estimate
            status_text.text(f"Đang xử lý {index + 1}/{total_rows}: {query}")
            
            # Tính toán thời gian ước tính
            if index > 0:
                time_est = calculate_time_estimate(total_rows, index + 1, start_time)
                time_estimate.markdown(f'<div class="time-estimate">⏱️ {time_est}</div>', unsafe_allow_html=True)
            
            # Lấy Entry ID
            entry_id = get_entry_from_uniprot_selenium(query, entry_name)
            
            if entry_id:
                final_url = f"https://www.uniprot.org/uniprotkb/{entry_id}/entry#structure"
                status = "✅ Thành công"
                success_count += 1
            else:
                final_url = ""
                status = "❌ Không tìm thấy"
            
            results.append({
                'Query': query,
                'Entry Name': entry_name,
                'Entry ID': entry_id if entry_id else "",
                'Final URL': final_url,
                'Status': status
            })
            
            # Hiển thị thống kê real-time
            with stats_container:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Đã xử lý", f"{index + 1}/{total_rows}")
                with col2:
                    st.metric("Thành công", success_count)
                with col3:
                    st.metric("Thất bại", (index + 1) - success_count)
                with col4:
                    success_rate = (success_count / (index + 1)) * 100
                    st.metric("Tỷ lệ thành công", f"{success_rate:.1f}%")
            
            # Nghỉ giữa các request
            time.sleep(2)
        
        # Hoàn thành bước 1
        step_progress.progress(1.0)
        overall_progress.progress(0.4)
        
        # Tạo DataFrame Entry IDs
        df_entry_results = pd.DataFrame(results)
        
        # Bước 2: Lấy 3D Structure data
        current_step.markdown("**🧬 Bước 2/2: Lấy dữ liệu 3D Structure**")
        
        # Lọc những dòng có Entry ID
        valid_results = df_entry_results[df_entry_results['Entry ID'] != ""]
        
        if len(valid_results) == 0:
            st.error("❌ Không có Entry ID nào hợp lệ để lấy dữ liệu 3D structure")
            return df_entry_results, None
        
        all_structure_data = []
        all_headers = None
        structure_count = 0
        
        # Reset time tracking cho bước 2
        step2_start_time = time.time()
        
        for idx, (index, row) in enumerate(valid_results.iterrows()):
            query = row['Query']
            entry_name = row['Entry Name']
            final_url = row['Final URL']
            
            # Cập nhật progress
            current_progress = (idx + 1) / len(valid_results)
            step_progress.progress(current_progress)
            overall_progress.progress(0.4 + (current_progress * 0.6))  # 60% cho bước 2
            
            # Cập nhật status
            status_text.text(f"Đang lấy 3D structure {idx + 1}/{len(valid_results)}: {query}")
            
            # Tính toán thời gian ước tính cho bước 2
            if idx > 0:
                time_est = calculate_time_estimate(len(valid_results), idx + 1, step2_start_time)
                time_estimate.markdown(f'<div class="time-estimate">⏱️ {time_est}</div>', unsafe_allow_html=True)
            
            result = extract_3d_structure_table(final_url, query, entry_name)
            
            if result:
                data, headers = result
                if all_headers is None:
                    all_headers = headers
                all_structure_data.extend(data)
                structure_count += len(data)
            
            # Hiển thị thống kê real-time cho bước 2
            with stats_container:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Proteins đã xử lý", f"{idx + 1}/{len(valid_results)}")
                with col2:
                    st.metric("Structures tìm thấy", structure_count)
                with col3:
                    st.metric("Trung bình/protein", f"{structure_count/(idx+1):.1f}" if idx >= 0 else "0")
                with col4:
                    completion_rate = ((idx + 1) / len(valid_results)) * 100
                    st.metric("Hoàn thành", f"{completion_rate:.1f}%")
            
            # Nghỉ giữa các request
            time.sleep(3)
        
        # Hoàn thành
        overall_progress.progress(1.0)
        step_progress.progress(1.0)
        status_text.text("✅ Hoàn thành tất cả!")
        
        # Tính tổng thời gian
        total_time = time.time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        time_estimate.markdown(f'<div class="time-estimate">🎉 Hoàn thành trong {minutes} phút {seconds} giây!</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        if all_structure_data:
            df_final_results = pd.DataFrame(all_structure_data, columns=all_headers)
            return df_entry_results, df_final_results
        else:
            return df_entry_results, None

def main():
    """Hàm chính"""
    
    # Header
    st.markdown('<h1 class="main-header">🧬 UniProt Extractor</h1>', unsafe_allow_html=True)
   
    
    # Upload section
    st.markdown('<div class="upload-section">', unsafe_allow_html=True)
    st.markdown("### 📁 Upload File Excel")
    st.markdown("File Excel cần có **2 cột**: `Query` và `Entry Name`")
    
    uploaded_file = st.file_uploader(
        "Chọn file Excel",
        type=['xlsx', 'xls'],
        help="File Excel với 2 cột: Query và Entry Name"
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    if uploaded_file is not None:
        try:
            # Đọc file
            df_input = pd.read_excel(uploaded_file)
            
            # Kiểm tra cột
            required_columns = ['Query', 'Entry Name']
            missing_columns = [col for col in required_columns if col not in df_input.columns]
            
            if missing_columns:
                st.error(f"❌ File thiếu cột: {missing_columns}")
                st.error(f"Các cột hiện tại: {list(df_input.columns)}")
                return
            
            # Hiển thị thông tin file
            st.success(f"✅ File hợp lệ - {len(df_input)} dòng dữ liệu")
            
            # Ước tính thời gian
            estimated_time = len(df_input) * 7  # ~7 giây/item trung bình
            est_minutes = estimated_time // 60
            est_seconds = estimated_time % 60
            
            st.info(f"⏱️ Ước tính thời gian xử lý: {est_minutes} phút {est_seconds} giây")
            
            # Preview dữ liệu
            with st.expander("👀 Xem trước dữ liệu", expanded=True):
                st.dataframe(df_input.head(10), use_container_width=True)
            
            # Nút xử lý
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🚀 Bắt đầu xử lý hoàn chỉnh", type="primary", use_container_width=True):
                    
                    # Xử lý workflow
                    df_entry_results, df_final_results = process_complete_workflow(df_input)
                    
                    if df_entry_results is not None:
                        # Hiển thị kết quả Entry IDs
                        st.markdown("### 📊 Kết quả Entry IDs")
                        
                        # Metrics
                        success_count = len(df_entry_results[df_entry_results['Entry ID'] != ""])
                        total_count = len(df_entry_results)
                        fail_count = total_count - success_count
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown(f'<div class="success-metric"><h3>{total_count}</h3><p>Tổng số</p></div>', unsafe_allow_html=True)
                        with col2:
                            st.markdown(f'<div class="success-metric"><h3>{success_count}</h3><p>Thành công</p></div>', unsafe_allow_html=True)
                        with col3:
                            st.markdown(f'<div class="error-metric"><h3>{fail_count}</h3><p>Thất bại</p></div>', unsafe_allow_html=True)
                        with col4:
                            st.markdown(f'<div class="success-metric"><h3>{success_count/total_count*100:.1f}%</h3><p>Tỷ lệ thành công</p></div>', unsafe_allow_html=True)
                        
                        # Bảng Entry IDs
                        with st.expander("📋 Chi tiết Entry IDs", expanded=False):
                            st.dataframe(df_entry_results, use_container_width=True)
                        
                        # Kết quả 3D Structure
                        if df_final_results is not None:
                            st.markdown("### 🧬 Kết quả 3D Structure")
                            
                            # Metrics cho 3D Structure
                            unique_proteins = df_final_results['Query'].nunique()
                            total_structures = len(df_final_results)
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.markdown(f'<div class="success-metric"><h3>{total_structures}</h3><p>Tổng dòng dữ liệu</p></div>', unsafe_allow_html=True)
                            with col2:
                                st.markdown(f'<div class="success-metric"><h3>{unique_proteins}</h3><p>Số proteins</p></div>', unsafe_allow_html=True)
                            with col3:
                                st.markdown(f'<div class="success-metric"><h3>{total_structures/unique_proteins:.1f}</h3><p>Trung bình/protein</p></div>', unsafe_allow_html=True)
                            
                            # Bảng 3D Structure
                            with st.expander("🔬 Chi tiết 3D Structure", expanded=True):
                                st.dataframe(df_final_results, use_container_width=True)
                            
                            # Download section
                            st.markdown('<div class="download-section">', unsafe_allow_html=True)
                            st.markdown("### 💾 Tải xuống kết quả")
                            st.markdown("File Excel chứa 2 sheets: **3D_Structures** và **Entry_IDs**")
                            
                            # Tạo file Excel
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df_final_results.to_excel(writer, sheet_name='3D_Structures', index=False)
                                df_entry_results.to_excel(writer, sheet_name='Entry_IDs', index=False)
                            
                            output.seek(0)
                            
                            # Tên file với timestamp
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"UniProt_3D_Structures_{timestamp}.xlsx"
                            
                            st.download_button(
                                label="📥 Tải xuống kết quả Excel",
                                data=output.getvalue(),
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                            
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                        else:
                            st.warning("⚠️ Không lấy được dữ liệu 3D structure nào")
                    
                    else:
                        st.error("❌ Không thể xử lý dữ liệu")
        
        except Exception as e:
            st.error(f"❌ Lỗi khi đọc file: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("**🔬 UniProt lấy mã Alpha fold hoặc PDB** - Văn Quân Bùi")

if __name__ == "__main__":
    main()
