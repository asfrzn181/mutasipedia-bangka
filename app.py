import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload
import fitz  # Library PyMuPDF
import toml # Library untuk membaca file config.toml

# --- FUNGSI-FUNGSI ---
# (Semua fungsi Anda di sini tidak berubah, jadi saya singkat)
@st.cache_data(ttl=1800)
def load_config(file_path="config.toml"):
    # ... (kode fungsi ini sama seperti sebelumnya)
    try:
        return toml.load(file_path)
    except FileNotFoundError:
        st.error(f"File konfigurasi '{file_path}' tidak ditemukan.")
        return None

@st.cache_data(ttl=1800)
def bangun_basis_pengetahuan(_creds, folder_id):
    # ... (kode fungsi ini sama seperti sebelumnya)
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
            # ... (logika pembacaan file sama seperti sebelumnya)
            file_id, file_name, mime_type = item['id'], item['name'], item['mimeType']
            teks_dari_file = ""
            if mime_type == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=file_id, mimeType='text/plain')
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done: status, done = downloader.next_chunk()
                teks_dari_file = fh.getvalue().decode('utf-8')
            elif mime_type == 'application/pdf':
                request = service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done: status, done = downloader.next_chunk()
                fh.seek(0)
                with fitz.open(stream=fh, filetype="pdf") as doc:
                    for page in doc: teks_dari_file += page.get_text()
            teks_gabungan += f"\n\n--- Mulai Dokumen: {file_name} ---\n{teks_dari_file}\n--- Selesai Dokumen: {file_name} ---\n"
        return teks_gabungan
    except Exception as e:
        st.error(f"Terjadi kesalahan saat mengakses Google Drive atau memproses file: {e}")
        return None

# --- APLIKASI UTAMA STREAMLIT ---

config = load_config()
if not config:
    st.stop()

st.set_page_config(
    page_title=config["app"]["title"],
    page_icon=config["app"]["icon"]
)

st.title(f'{config["app"]["icon"]} {config["app"]["title"]}')
st.caption(config["app"]["caption"])

try:
    with open(config["app"].get("prompt_template_file", "prompt_template.txt"), 'r', encoding='utf-8') as f:
        prompt_template = f.read()
except FileNotFoundError:
    st.error(config["error_messages"]["template_not_found"].format(file_name=config["app"].get("prompt_template_file", "prompt_template.txt")))
    st.stop()

if 'type' in st.secrets and 'project_id' in st.secrets and 'gemini_api_key' in st.secrets:
    try:
        FOLDER_ID = st.secrets.get("folder_id", "")
        if not FOLDER_ID:
            st.error("ID Folder Google Drive belum diatur di Streamlit Secrets.")
            st.stop()

        creds = service_account.Credentials.from_service_account_info(st.secrets, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        basis_pengetahuan = bangun_basis_pengetahuan(creds, FOLDER_ID)

        if basis_pengetahuan:
            genai.configure(api_key=st.secrets["gemini_api_key"])
            model = genai.GenerativeModel('gemini-2.5-pro')

            # Inisialisasi riwayat chat
            if "messages" not in st.session_state:
                st.session_state.messages = []
                # Menambahkan sapaan pembuka hanya saat inisialisasi
                welcome_message = config["app"].get("welcome_message", "Selamat datang! Ada yang bisa saya bantu?")
                st.session_state.messages.append({"role": "assistant", "content": welcome_message})

            # >>> PERUBAHAN UTAMA: BAGIAN TAMPILAN DAN LOGIKA DIPISAH <<<

            # 1. BLOK UNTUK MENAMPILKAN SELURUH RIWAYAT CHAT
            # Blok ini akan selalu menggambar ulang semua pesan dari awal setiap kali ada interaksi
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # 2. BLOK UNTUK MENANGANI INPUT BARU DARI PENGGUNA
            # Blok ini hanya bertugas menambah pesan baru ke riwayat, lalu memicu gambar ulang
            if prompt_input := st.chat_input(config["app"]["chat_input_placeholder"]):
                # Tambahkan pesan pengguna ke riwayat
                st.session_state.messages.append({"role": "user", "content": prompt_input})

                # Siapkan prompt untuk AI
                prompt_lengkap = prompt_template.format(
                    basis_pengetahuan=basis_pengetahuan,
                    prompt=prompt_input
                )

                # Dapatkan respons dari AI
                with st.spinner("Sedang berpikir..."):
                    response = model.generate_content(prompt_lengkap)
                
                # Tambahkan respons AI ke riwayat
                st.session_state.messages.append({"role": "assistant", "content": response.text})

                # Memicu gambar ulang seluruh halaman
                st.rerun()

    except Exception as e:
        st.error(f"Terjadi kesalahan pada aplikasi: {e}")
else:
    st.error(config["error_messages"]["secrets_not_found"])