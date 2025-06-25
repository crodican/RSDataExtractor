import sys
import os
import threading
import requests
import pandas as pd
import time
import io
from bs4 import BeautifulSoup

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QTextEdit, QFileDialog, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QFontDatabase

COUNTY_URL = "https://resourcespage.pages.dev/pa_cities_counties.csv"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

FONT_PATHS = {
    "AvenirLTPro-Book": "avenir.ttf",
    "AvenirLTPro-Heavy": "avenir-heavy.ttf",
    "AvenirLTPro-Black": "avenir-black.ttf"
}

# --- Scraping Functions ---
def get_city_county_df(output_lines):
    try:
        resp = requests.get(COUNTY_URL, headers=HEADERS)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df['City'] = df['City'].str.strip().str.lower()
        output_lines.append("City-County CSV loaded.")
        return df
    except Exception as e:
        output_lines.append(f"❌ Failed to load city-county data: {e}")
        return pd.DataFrame()

def get_total_pages(base_url, output_lines):
    output_lines.append("📄 Determining total number of pages...")
    try:
        response = requests.get(base_url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        output_lines.append(f"❌ Error: {e}")
        return 98
    soup = BeautifulSoup(response.content, 'html.parser')
    last_page_link = soup.find('a', title='Go to last page')
    if last_page_link and 'href' in last_page_link.attrs:
        try:
            return int(last_page_link['href'].split('page=')[-1]) + 1
        except:
            return 98
    return 98

def scrape_website(base_url, total_pages, output_lines, progress_callback=None):
    all_data = []
    scrape_index = 0

    for page in range(total_pages):
        url = f"{base_url}&page={page}"
        msg = f"🔍 Scraping page {page + 1} of {total_pages}"
        output_lines.append(msg)
        if progress_callback:
            progress_callback(page+1, total_pages, msg)
        try:
            response = requests.get(url)
            response.raise_for_status()
        except:
            output_lines.append(f"⚠️ Failed to load {url}")
            continue

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='table table-hover table-striped views-table views-view-table cols-3')
        if not table:
            continue

        rows = table.select('tbody > tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 3:
                continue

            name = cols[0].get_text(strip=True)
            city_raw = cols[1].get_text(strip=True).replace(", PA", "").strip().lower()

            cert_table = cols[2].find('table')
            if cert_table:
                cert_rows = cert_table.select('tbody > tr')
                for cert_row in cert_rows:
                    cert_cols = cert_row.find_all('td')
                    if len(cert_cols) == 5:
                        credential = cert_cols[0].get_text(strip=True)
                        number = cert_cols[1].get_text(strip=True)
                        issue = cert_cols[2].get_text(strip=True)
                        expire = cert_cols[3].get_text(strip=True)
                        status = cert_cols[4].get_text(strip=True)

                        all_data.append({
                            'SCRAPE ORDER': scrape_index,
                            'NAME': name,
                            'CITY': city_raw,
                            'CREDENTIAL': credential,
                            'NUMBER': number,
                            'ISSUE DATE': issue,
                            'EXP DATE': expire,
                            'STATUS': status
                        })
                        scrape_index += 1

        time.sleep(1)
    return pd.DataFrame(all_data)

# --- PyQt Signal Helper ---
class Communicate(QObject):
    progress = pyqtSignal(int, int, str)
    line = pyqtSignal(str)
    done = pyqtSignal(tuple)

# --- Main App ---
class RecoverySpecialistApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RS Data Collector Tool")
        self.setFixedSize(350, 700)
        self.setObjectName("MainWindow")

        # ---- Load Fonts ----
        self.font_ids = {}
        for name, path in FONT_PATHS.items():
            font_id = QFontDatabase.addApplicationFont(os.path.join(os.path.dirname(__file__), path))
            if font_id != -1:
                self.font_ids[name] = font_id

        self.fontFamilies = {
            "book": QFontDatabase.applicationFontFamilies(self.font_ids["AvenirLTPro-Book"])[0],
            "heavy": QFontDatabase.applicationFontFamilies(self.font_ids["AvenirLTPro-Heavy"])[0],
            "black": QFontDatabase.applicationFontFamilies(self.font_ids["AvenirLTPro-Black"])[0],
        }

        # ---- Outer Layout ----
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Header Bar ----
        self.header = QWidget(self)
        self.header.setObjectName("HeaderBar")
        self.header.setFixedHeight(60)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(0)
        self.title_label = QLabel("RS DATA COLLECTOR TOOL", self.header)
        self.title_label.setObjectName("AppTitle")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_layout.addWidget(self.title_label)
        outer.addWidget(self.header)

        # ---- Main Body ----
        self.body = QWidget(self)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(0)

        body_layout.addSpacing(50)  # 50px below header

        self.subtitle = QLabel("Select Data to Extract:", self.body)
        self.subtitle.setObjectName("Subtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)
        body_layout.addWidget(self.subtitle)

        body_layout.addSpacing(30)

        # ---- Data Buttons ----
        self.data_btns = []
        btn_labels = [("CRS", "CRS Data"), ("CFRS", "CFRS Data"), ("CRSS", "CRSS Data")]
        for i, (cred, label) in enumerate(btn_labels):
            btn = QPushButton(label, self.body)
            btn.setObjectName(f"DataBtn{i}")
            btn.setFixedSize(260, 65)
            btn.clicked.connect(lambda _, c=cred: self.start_scrape(c))
            self.data_btns.append(btn)
            body_layout.addWidget(btn, alignment=Qt.AlignHCenter)
            if i < 2:
                body_layout.addSpacing(25)

        # Download Button (hidden until done)
        body_layout.addSpacing(25)
        self.download_btn = QPushButton("Download Data", self.body)
        self.download_btn.setObjectName("DownloadBtn")
        self.download_btn.setFixedSize(260, 50)
        self.download_btn.setVisible(False)
        self.download_btn.clicked.connect(self.download_data)
        body_layout.addWidget(self.download_btn, alignment=Qt.AlignHCenter)

        body_layout.addStretch(1)
        outer.addWidget(self.body)

        # ---- Status Bar & Output ----
        self.status_container = QWidget(self)
        self.status_container.setObjectName("StatusContainer")
        self.status_container.setFixedHeight(60)
        self.status_container.setVisible(False)
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setContentsMargins(20, 0, 20, 0)
        status_layout.setSpacing(2)

        # Status bar + show/hide output button
        bar_row = QHBoxLayout()
        bar_row.setSpacing(0)
        self.progress = QProgressBar(self.status_container)
        self.progress.setObjectName("StatusBar")
        self.progress.setFixedHeight(30)
        self.progress.setTextVisible(False)
        bar_row.addWidget(self.progress, stretch=4)

        bar_row.addSpacing(10)

        self.show_output_btn = QPushButton("Show Output", self.status_container)
        self.show_output_btn.setObjectName("ShowOutputBtn")
        self.show_output_btn.setFixedHeight(30)
        self.show_output_btn.setFixedWidth(120)
        self.show_output_btn.clicked.connect(self.toggle_log)
        bar_row.addWidget(self.show_output_btn, stretch=0)
        status_layout.addLayout(bar_row)

        # Last log line
        self.status_line = QLabel("", self.status_container)
        self.status_line.setObjectName("StatusLine")
        self.status_line.setFixedHeight(16)
        status_layout.addWidget(self.status_line)
        outer.addWidget(self.status_container, alignment=Qt.AlignBottom)

        # Output log (hidden by default)
        self.log_box = QTextEdit(self)
        self.log_box.setObjectName("LogBox")
        self.log_box.setReadOnly(True)
        self.log_box.setVisible(False)
        self.log_box.setFixedHeight(180)
        outer.addWidget(self.log_box, alignment=Qt.AlignBottom)

        # ---- State ----
        self.full_output_lines = []
        self.data_files = None
        self.log_expanded = False

        # ---- Threaded scraping signals ----
        self.c = Communicate()
        self.c.progress.connect(self.set_progress)
        self.c.line.connect(self.append_log)
        self.c.done.connect(self.scrape_done)

        # ---- Style and Fonts ----
        self.setStyleSheet(self.build_stylesheet())
        self.update_fonts()

    def build_stylesheet(self):
        return f"""
        QWidget#MainWindow {{
            background: #fff;
            border: 3px solid rgba(18,178,232,1);
            border-radius: 0px;
        }}
        QWidget#HeaderBar {{
            background: rgb(234, 94, 100);
            min-height: 60px;
            max-height: 60px;
        }}
        QLabel#AppTitle {{
            color: white;
            font-size: 18px;
            font-family: '{self.fontFamilies["black"]}';
            font-weight: 900;
            letter-spacing: 1.2px;
            text-transform: uppercase;
        }}
        QLabel#Subtitle {{
            color: #000;
            font-size: 14px;
            font-family: '{self.fontFamilies["book"]}';
            font-weight: normal;
            margin-bottom: 30px;
        }}
        QPushButton[id^="DataBtn"] {{
            background: rgb(234, 94, 100);
            color: white;
            font-size: 16px;
            font-family: '{self.fontFamilies["heavy"]}';
            font-weight: 800;
            border: none;
            border-radius: 7px;
            text-transform: uppercase;
        }}

        QPushButton#DownloadBtn {{
            background: rgba(18,178,232,1);
            color: white;
            font-size: 16px;
            font-family: '{self.fontFamilies["heavy"]}';
            font-weight: 800;
            border: none;
            border-radius: 7px;
            text-transform: uppercase;
        }}
        QWidget#StatusContainer {{
            background: transparent;
        }}
        QProgressBar#StatusBar {{
            border-radius: 4px;
            background: rgb(240, 244, 249);
            height: 30px;
        }}
        QProgressBar#StatusBar::chunk {{
            border-radius: 4px;
            background: rgba(18,178,232,1);
        }}
        QPushButton#ShowOutputBtn {{
            background: rgb(234, 94, 100);
            color: white;
            font-size: 13px;
            font-family: '{self.fontFamilies["heavy"]}';
            font-weight: 800;
            border: none;
            border-radius: 7px;
            text-transform: uppercase;
        }}
        QLabel#StatusLine {{
            color: #000;
            font-size: 11px;
            font-family: '{self.fontFamilies["book"]}';
        }}
        QTextEdit#LogBox {{
            background: #111;
            color: #fff;
            font-size: 11px;
            font-family: '{self.fontFamilies["book"]}';
            border-radius: 0px;
            border: none;
            padding: 10px;
        }}
        """

    def update_fonts(self):
        self.title_label.setFont(QFont(self.fontFamilies["black"], 18))
        self.subtitle.setFont(QFont(self.fontFamilies["book"], 14))
        for btn in self.data_btns:
            btn.setFont(QFont(self.fontFamilies["heavy"], 16))
        self.download_btn.setFont(QFont(self.fontFamilies["heavy"], 16))
        self.show_output_btn.setFont(QFont(self.fontFamilies["heavy"], 13))
        self.status_line.setFont(QFont(self.fontFamilies["book"], 11))
        self.log_box.setFont(QFont(self.fontFamilies["book"], 11))

    def start_scrape(self, cred):
        # Reset UI
        self.full_output_lines = []
        self.log_box.clear()
        self.log_box.setVisible(False)
        self.download_btn.setVisible(False)
        self.progress.setValue(0)
        self.status_line.setText("")
        self.show_output_btn.setText("Show Output")
        self.log_expanded = False
        for btn in self.data_btns:
            btn.setDisabled(True)
        self.data_files = None
        self.status_container.setVisible(True)
        # Start thread
        threading.Thread(target=self.scrape_worker, args=(cred,), daemon=True).start()

    def scrape_worker(self, credential_choice):
        try:
            # Progress helper
            def progress_callback(current, total, msg):
                self.c.progress.emit(current, total, msg)
                self.c.line.emit(msg)
            target_credential = credential_choice
            base_url = f"https://www.pacertboard.org/credential-search?type={target_credential.lower()}"
            city_county_df = get_city_county_df(self.full_output_lines)
            if city_county_df.empty:
                self.c.line.emit("❌ City-county data is required. Exiting.")
                self.c.done.emit((None, None, None))
                return
            total_pages = get_total_pages(base_url, self.full_output_lines)
            df = scrape_website(base_url, total_pages, self.full_output_lines, progress_callback=progress_callback)
            df['CITY'] = df['CITY'].str.strip().str.lower()
            df = df.merge(city_county_df, how='left', left_on='CITY', right_on='City')
            if 'City' in df.columns:
                df.drop(columns=['City'], inplace=True)
            df = df[df['CREDENTIAL'].str.contains(target_credential, na=False)]
            df.sort_values(by='SCRAPE ORDER', inplace=True)
            # CSV output
            all_csv = f"{target_credential}_all_PA.csv"
            df.to_csv(all_csv, index=False)
            # Filtered by county
            target_counties = [
                'Philadelphia', 'Berks', 'Bucks', 'Chester',
                'Delaware', 'Lancaster', 'Montgomery', 'Schuylkill'
            ]
            county_df = df[df['County'].isin(target_counties)]
            filtered_csv = f"{target_credential}_filtered_by_county.csv"
            county_df.to_csv(filtered_csv, index=False)
            # Excel file with two sheets
            excel_file = f"{target_credential}_output.xlsx"
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='All PA', index=False)
                county_df.to_excel(writer, sheet_name='Selected Counties', index=False)
            self.c.line.emit("✅ Done! All files generated and ready to download.")
            self.c.done.emit((excel_file, all_csv, filtered_csv))
        except Exception as e:
            self.c.line.emit(f"❌ Error: {e}")
            self.c.done.emit((None, None, None))

    def set_progress(self, current, total, msg):
        percent = int((current/total)*100) if total else 0
        self.progress.setMaximum(100)
        self.progress.setValue(percent)
        if not self.log_expanded:
            self.status_line.setText(msg)

    def append_log(self, line):
        self.full_output_lines.append(line)
        if self.log_expanded:
            self.log_box.append(line)
        else:
            self.status_line.setText(line)

    def toggle_log(self):
        self.log_expanded = not self.log_expanded
        self.log_box.setVisible(self.log_expanded)
        self.show_output_btn.setText("Hide Output" if self.log_expanded else "Show Output")
        if self.log_expanded:
            self.log_box.setPlainText('\n'.join(self.full_output_lines))
            self.log_box.moveCursor(self.log_box.textCursor().End)
        else:
            if self.full_output_lines:
                self.status_line.setText(self.full_output_lines[-1])

    def scrape_done(self, file_tuple):
        for btn in self.data_btns:
            btn.setDisabled(False)
        self.data_files = file_tuple
        if all(file_tuple):
            self.download_btn.setVisible(True)
        else:
            self.download_btn.setVisible(False)

    def download_data(self):
        if not self.data_files or not all(self.data_files):
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose folder to save data files")
        if not folder:
            return
        for f in self.data_files:
            try:
                dest = os.path.join(folder, os.path.basename(f))
                with open(f, "rb") as src, open(dest, "wb") as dst:
                    dst.write(src.read())
            except Exception as e:
                msg = f"Failed to save {f}: {e}"
                self.append_log(msg)
        msg = "Files saved to: " + folder
        self.append_log(msg)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RecoverySpecialistApp()
    window.show()
    sys.exit(app.exec_())