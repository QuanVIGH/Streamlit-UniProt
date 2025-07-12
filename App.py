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
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import io
import os
import sys
from datetime import datetime
import logging
import subprocess

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cấu hình trang
st.set_page_config(
    page_title="UniProt 3D Structure Extractor",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def install_chromium():
    """Cài đặt chromium nếu chưa có"""
    try:
        # Kiểm tra xem chromium đã được cài đặt chưa
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"Chromium đã được cài đặt tại: {result.stdout.strip()}")
            return result.stdout.strip()
        
        # Thử các đường dẫn khác
        possible_paths = [
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Tìm thấy browser tại: {path}")
                return path
        
        logger.warning("Không tìm thấy chromium")
        return None
        
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra chromium: {e}")
        return None

def create_driver():
    """Tạo Chrome driver với cấu hình tối ưu"""
    # Tìm chromium
    chromium_path = install_chromium()
    
    chrome_options = Options()
    
    # Cấu hình cơ bản
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--no-zygote")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-features=TranslateUI,VizDisplayCompositor")
    chrome_options.add_argument("--disable-ipc-flooding-protection")
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    
    # User agent
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Tắt automation detection
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Đặt binary location nếu tìm thấy
    if chromium_path:
        chrome_options.binary_location = chromium_path
    
    try:
        # Thử tạo driver
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("Tạo driver thành công")
        return driver
        
    except Exception as e:
        logger.error(f"Lỗi tạo driver: {e}")
        
        # Thử với webdriver-manager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("Tạo driver thành công với webdriver-manager")
            return driver
        except Exception as e2:
            logger.error(f"Lỗi với webdriver-manager: {e2}")
            return None

def test_driver():
    """Test driver functionality"""
    try:
        driver = create_driver()
        if driver:
            driver.get("https://www.google.com")
            title = driver.title
            driver.quit()
            logger.info(f"Driver test thành công: {title}")
            return True, f"Thành công: {title}"
        return False, "Không thể tạo driver"
    except Exception as e:
        logger.error(f"Driver test thất bại: {e}")
        return False, f"Lỗi: {str(e)}"

def get_entry_from_uniprot_selenium(gene_id, entry_name):
    """Lấy Entry ID từ UniProt"""
    url = f"https://www.uniprot.org/uniprotkb?query={gene_id}"
    
    driver = create_driver()
    if not driver:
        logger.error("Không thể tạo driver")
        return None
    
    try:
        logger.info(f"Đang truy cập: {url}")
        driver.get(url)
        
        # Chờ trang tải
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "data-table"))
            )
        except TimeoutException:
            logger.warning(f"Timeout chờ bảng tải cho {gene_id}")
            return None
        
        # Chấp nhận cookie
        try:
            cookie_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I agree, dismiss this banner')]"))
            )
            cookie_button.click()
            time.sleep(2)
        except TimeoutException:
            logger.info("Không có cookie banner")
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm bảng
        table = soup.find('table', class_='data-table')
        if not table:
            table = soup.find('table')
        
        if not table:
            logger.warning(f"Không tìm thấy bảng cho {gene_id}")
            return None
        
        tbody = table.find('tbody')
        if not tbody:
            logger.warning(f"Không tìm thấy tbody cho {gene_id}")
            return None
        
        rows = tbody.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) > 3:
                current_entry_name = cols[3].text.strip()
                if current_entry_name == entry_name:
                    entry = cols[1].text.strip()
                    logger.info(f"Tìm thấy entry {entry} cho {gene_id}")
                    return entry
        
        logger.warning(f"Không tìm thấy entry name '{entry_name}' cho {gene_id}")
        return None
        
    except Exception as e:
        logger.error(f"Lỗi khi xử lý {gene_id}: {e}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

def extract_3d_structure_table(final_url, query, entry_name):
    """Lấy thông tin từ bảng 3D structure"""
    driver = create_driver()
    if not driver:
        logger.error("Không thể tạo driver cho 3D structure")
        return None
    
    try:
        logger.info(f"Đang truy cập 3D structure: {final_url}")
        driver.get(final_url)
        time.sleep(8)
        
        # Chấp nhận cookie
        try:
            cookie_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I agree, dismiss this banner')]"))
            )
            cookie_button.click()
            time.sleep(3)
        except TimeoutException:
            logger.info("Không có cookie banner")
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm bảng 3D structure
        table = None
        tables = soup.find_all('table')
        
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
            
            matching_keywords = sum(1 for keyword in structure_keywords if keyword in ' '.join(headers))
            if matching_keywords >= 3:
                table = t
                break
        
        if not table:
            for t in tables:
                table_text = t.get_text().upper()
                if ('ALPHAFOLD' in table_text or 'PDB' in table_text or 'AF-' in table_text) and len(t.find_all('tr')) > 1:
                    table = t
                    break
        
        if not table:
            logger.warning(f"Không tìm thấy bảng 3D structure cho {query}")
            return None
        
        # Lấy headers
        headers = []
        thead = table.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    header_text = th.get_text(strip=True)
                    if header_text:
                        headers.append(header_text)
        
        if not headers:
            first_row = table.find('tr')
            if first_row:
                header_cells = first_row.find_all(['th', 'td'])
                for cell in header_cells:
                    header_text = cell.get_text(strip=True)
                    if header_text:
                        headers.append(header_text)
        
        # Lấy dữ liệu
        data = []
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            all_rows = table.find_all('tr')
            if all_rows and headers:
                rows = all_rows[1:]
            else:
                rows = all_rows
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = []
            
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                
                links = cell.find_all('a')
                if links:
                    link_urls = []
                    for link in links:
                        href = link.get('href', '')
                        if href:
                            if href.startswith('/'):
                                href = 'https://www.uniprot.org' + href
                            elif not href.startswith('http'):
                                href = 'https://www.uniprot.org/' + href
                            link_urls.append(href)
                    
                    if link_urls:
                        cell_text = f"{cell_text} | Links: {'; '.join(link_urls)}"
                
                row_data.append(cell_text)
            
            if row_data and any(cell.strip() for cell in row_data):
                while len(row_data) < len(headers):
                    row_data.append("")
                
                full_row = [query, entry_name] + row_data[:len(headers)]
                data.append(full_row)
        
        if data:
            full_headers = ['Query', 'Entry Name'] + headers
            logger.info(f"Lấy được {len(data)} dòng dữ liệu cho {query}")
            return data, full_headers
        else:
            logger.warning(f"Không có dữ liệu cho {query}")
            return None
            
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu 3D structure cho {query}: {e}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

def calculate_time_estimate(total_items, current_item, start_time):
    """Tính toán thời gian ước tính"""
    if current_item == 0:
        return "Đang tính toán..."
    
    elapsed_time = time.time() - start_time
    avg_time_per_item = elapsed_time / current_item
    remaining_items = total_items - current_item
    estimated_remaining = remaining_items * avg_time_per_item
    
    minutes = int(estimated_remaining // 60)
    seconds = int(estimated_remaining % 60)
    
    if minutes > 0:
        return f"Còn khoảng {minutes} phút {seconds} giây"
    else:
        return f"Còn khoảng {seconds} giây"

def process_complete_workflow(df_input):
    """Xử lý toàn bộ workflow"""
    progress_container = st.container()
    
    with progress_container:
        st.markdown("### 🔄 Đang xử lý dữ liệu...")
        
        overall_progress = st.progress(0)
        current_step = st.empty()
        step_progress = st.progress(0)
        status_text = st.empty()
        time_estimate = st.empty()
        
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
            
            current_progress = (index + 1) / total_rows
            step_progress.progress(current_progress)
            overall_progress.progress(current_progress * 0.4)
            
            status_text.text(f"Đang xử lý {index + 1}/{total_rows}: {query}")
            
            if index > 0:
                time_est = calculate_time_estimate(total_rows, index + 1, start_time)
                time_estimate.text(f"⏱️ {time_est}")
            
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
            
            time.sleep(3)
        
        step_progress.progress(1.0)
        overall_progress.progress(0.4)
        
        df_entry_results = pd.DataFrame(results)
        
        # Bước 2: Lấy 3D Structure data
        current_step.markdown("**🧬 Bước 2/2: Lấy dữ liệu 3D Structure**")
        
        valid_results = df_entry_results[df_entry_results['Entry ID'] != ""]
        
        if len(valid_results) == 0:
            st.error("❌ Không có Entry ID nào hợp lệ")
            return df_entry_results, None
        
        all_structure_data = []
        all_headers = None
        structure_count = 0
        
        step2_start_time = time.time()
        
        for idx, (index, row) in enumerate(valid_results.iterrows()):
            query = row['Query']
            entry_name = row['Entry Name']
            final_url = row['Final URL']
            
            current_progress = (idx + 1) / len(valid_results)
            step_progress.progress(current_progress)
            overall_progress.progress(0.4 + (current_progress * 0.6))
            
            status_text.text(f"Đang lấy 3D structure {idx + 1}/{len(valid_results)}: {query}")
            
            if idx > 0:
                time_est = calculate_time_estimate(len(valid_results), idx + 1, step2_start_time)
                time_estimate.text(f"⏱️ {time_est}")
            
            result = extract_3d_structure_table(final_url, query, entry_name)
            
            if result:
                data, headers = result
                if all_headers is None:
                    all_headers = headers
                all_structure_data.extend(data)
                structure_count += len(data)
            
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
            
            time.sleep(4)
        
        overall_progress.progress(1.0)
        step_progress.progress(1.0)
        status_text.text("✅ Hoàn thành tất cả!")
        
        total_time = time.time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        time_estimate.text(f"🎉 Hoàn thành trong {minutes} phút {seconds} giây!")
        
        if all_structure_data:
            df_final_results = pd.DataFrame(all_structure_data, columns=all_headers)
            return df_entry_results, df_final_results
        else:
            return df_entry_results, None

def main():
    """Hàm chính"""
    st.markdown("# 🧬 UniProt 3D Structure Extractor")
    st.markdown("Trích xuất thông tin cấu trúc 3D từ UniProt Database")
    
    # Test driver
    with st.expander("🔧 Kiểm tra hệ thống", expanded=False):
        if st.button("🧪 Test Browser Driver"):
            with st.spinner("Đang test driver..."):
                success, message = test_driver()
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    # Upload section
    st.markdown("### 📁 Upload File Excel")
    st.markdown("File Excel cần có **2 cột**: `Query` và `Entry Name`")
    
    uploaded_file = st.file_uploader(
        "Chọn file Excel",
        type=['xlsx', 'xls'],
        help="File Excel với 2 cột: Query và Entry Name"
    )
    
    if uploaded_file is not None:
        try:
            df_input = pd.read_excel(uploaded_file)
            
            required_columns = ['Query', 'Entry Name']
            missing_columns = [col for col in required_columns if col not in df_input.columns]
            
            if missing_columns:
                st.error(f"❌ File thiếu cột: {missing_columns}")
                st.error(f"Các cột hiện tại: {list(df_input.columns)}")
                return
            
            st.success(f"✅ File hợp lệ - {len(df_input)} dòng dữ liệu")
            
            estimated_time = len(df_input) * 12
            est_minutes = estimated_time // 60
            est_seconds = estimated_time % 60
            
            st.info(f"⏱️ Ước tính thời gian xử lý: {est_minutes} phút {est_seconds} giây")
            
            with st.expander("👀 Xem trước dữ liệu", expanded=True):
                st.dataframe(df_input.head(10), use_container_width=True)
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🚀 Bắt đầu xử lý", type="primary", use_container_width=True):
                    
                    df_entry_results, df_final_results = process_complete_workflow(df_input)
                    
                    if df_entry_results is not None:
                        st.markdown("### 📊 Kết quả Entry IDs")
                        
                        success_count = len(df_entry_results[df_entry_results['Entry ID'] != ""])
                        total_count = len(df_entry_results)
                        fail_count = total_count - success_count
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Tổng số", total_count)
                        with col2:
                            st.metric("Thành công", success_count)
                        with col3:
                            st.metric("Thất bại", fail_count)
                        with col4:
                            st.metric("Tỷ lệ thành công", f"{success_count/total_count*100:.1f}%")
                        
                        with st.expander("📋 Chi tiết Entry IDs", expanded=False):
                            st.dataframe(df_entry_results, use_container_width=True)
                        
                        if df_final_results is not None:
                            st.markdown("### 🧬 Kết quả 3D Structure")
                            
                            unique_proteins = df_final_results['Query'].nunique()
                            total_structures = len(df_final_results)
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Tổng dòng dữ liệu", total_structures)
                            with col2:
                                st.metric("Số proteins", unique_proteins)
                            with col3:
                                st.metric("Trung bình/protein", f"{total_structures/unique_proteins:.1f}")
                            
                            with st.expander("🔬 Chi tiết 3D Structure", expanded=True):
                                st.dataframe(df_final_results, use_container_width=True)
                            
                            st.markdown("### 💾 Tải xuống kết quả")
                            
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df_final_results.to_excel(writer, sheet_name='3D_Structures', index=False)
                                df_entry_results.to_excel(writer, sheet_name='Entry_IDs', index=False)
                            
                            output.seek(0)
                            
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"UniProt_3D_Structures_{timestamp}.xlsx"
                            
                            st.download_button(
                                label="📥 Tải xuống kết quả Excel",
                                data=output.getvalue(),
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                            
                        else:
                            st.warning("⚠️ Không lấy được dữ liệu 3D structure nào")
                    else:
                        st.error("❌ Không thể xử lý dữ liệu")
        
        except Exception as e:
            st.error(f"❌ Lỗi khi đọc file: {str(e)}")
    
    st.markdown("---")
    st.markdown("**🔬 UniProt 3D Structure Extractor** - Văn Quân Bùi")

if __name__ == "__main__":
    main()
