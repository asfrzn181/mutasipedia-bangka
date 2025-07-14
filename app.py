import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload
import fitz  # Library PyMuPDF
import toml # Library untuk membaca file config.toml

# --- FUNGSI-FUNGSI ---

@st.cache_data(ttl=600)
def load_config(file_path="config.toml"):
    """Memuat konfigurasi dari file TOML."""
    try:
        return toml.load(file_path)
    except FileNotFoundError:
        st.error(f"File konfigurasi '{file_path}' tidak ditemukan.")
        return None
    except Exception as e:
        st.error(f"Gagal memuat konfigurasi: {e}")
        return None

@st.cache_data(ttl=600)
def bangun_basis_pengetahuan(_creds, folder_id):
    """Menghubungi Google Drive, membaca semua file dari folder, dan menggabungkannya."""
    try:
        service = build('drive', 'v3', credentials=_creds)
        teks_gabungan = ""
        query = f"'{folder_id}' in parents and (mimeType='application/vnd.google-apps.document' or mimeType='application/pdf')"
        results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        if not items:
            st.error("Tidak ada file Google Docs atau PDF yang ditemukan di folder. Pastikan ID folder benar dan file sudah dibagikan dengan benar.")
            return None
        for item in items:
            file_id = item['id']
            file_name = item['name']
            mime_type = item['mimeType']
            teks_dari_file = ""
            if mime_type == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=file_id, mimeType='text/plain')
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                teks_dari_file = fh.getvalue().decode('utf-8')
            elif mime_type == 'application/pdf':
                request = service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.seek(0)
                with fitz.open(stream=fh, filetype="pdf") as doc:
                    for page in doc:
                        teks_dari_file += page.get_text()
            teks_gabungan += f"\n\n--- Mulai Dokumen: {file_name} ---\n{teks_dari_file}\n--- Selesai Dokumen: {file_name} ---\n"
        return teks_gabungan
    except Exception as e:
        st.error(f"Terjadi kesalahan saat mengakses Google Drive atau memproses file: {e}")
        st.info("Pastikan kredensial di Streamlit Secrets sudah benar dan folder sudah dibagikan ke email service account.")
        return None

# --- APLIKASI UTAMA STREAMLIT ---

# Memuat konfigurasi terlebih dahulu
config = load_config()
if not config:
    st.stop()

# Mengatur konfigurasi halaman dari file config.toml
st.set_page_config(
    page_title=config["app"]["title"],
    page_icon=config["app"]["icon"]
)

st.title(f'{config["app"]["icon"]} {config["app"]["title"]}')
st.caption(config["app"]["caption"])

# Membaca template prompt dari file eksternal
try:
    with open(config["app"].get("prompt_template_file", "prompt_template.txt"), 'r', encoding='utf-8') as f:
        prompt_template = f.read()
except FileNotFoundError:
    st.error(config["error_messages"]["template_not_found"].format(file_name=config["app"].get("prompt_template_file", "prompt_template.txt")))
    st.stop()

# Memeriksa apakah semua secrets sudah diatur
if 'type' in st.secrets and 'project_id' in st.secrets and 'gemini_api_key' in st.secrets:
    try:
        FOLDER_ID = st.secrets.get("folder_id", "") # Mengambil ID Folder dari secrets
        if not FOLDER_ID:
            st.error("ID Folder Google Drive belum diatur di Streamlit Secrets.")
            st.stop()

        creds = service_account.Credentials.from_service_account_info(st.secrets, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        basis_pengetahuan = bangun_basis_pengetahuan(creds, FOLDER_ID)

        if basis_pengetahuan:
            genai.configure(api_key=st.secrets["gemini_api_key"])
            model = genai.GenerativeModel('gemini-1.5-flash')

            if "messages" not in st.session_state:
                st.session_state.messages = []

            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            if prompt_input := st.chat_input(config["app"]["chat_input_placeholder"]):
                st.session_state.messages.append({"role": "user", "content": prompt_input})
                with st.chat_message("user"):
                    st.markdown(prompt_input)

                prompt_lengkap = prompt_template.format(
                    basis_pengetahuan=basis_pengetahuan,
                    prompt=prompt_input
                )
                
                with st.chat_message("assistant"):
                    with st.spinner("Sedang berpikir..."):
                        response = model.generate_content(prompt_lengkap)
                        st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
    except Exception as e:
        st.error(f"Terjadi kesalahan pada aplikasi: {e}")

else:
    st.error(config["error_messages"]["secrets_not_found"])