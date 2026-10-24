import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="MİDES - Merkezi Sistem", page_icon="🏢", layout="wide")

# --- GİZLİ KASA AYARLARI ---
try:
    google_json_str = st.secrets["google_json"]
except:
    st.error("Gizli kasa (Secrets) ayarları bulunamadı! Lütfen ayarlardan google_json değerini ekleyin.")
    st.stop()

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(google_json_str)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

try:
    merkez_tablosu = client.open("MİDES - Merkez Kontrol").get_worksheet(0)
    df_kullanicilar = pd.DataFrame(merkez_tablosu.get_all_records())
except:
    st.error("Google Drive'da 'MİDES - Merkez Kontrol' tablosu bulunamadı veya erişim yetkisi verilmemiş.")
    st.stop()

# --- OTURUM YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'birlik': "", 'yetki': ""})

if not st.session_state['giris_yapildi']:
    st.markdown("<h1 style='text-align: center;'>🏢 MİDES - Merkezi Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Kurumsal Kullanıcı Girişi</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi_input = st.text_input("Kullanıcı Adı")
            sifre_input = st.text_input("Şifre", type="password")
            
            if st.form_submit_button("Sisteme Giriş Yap", use_container_width=True):
                # 1. Kullanıcıyı veri tabanında ara
                kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adı'] == kadi_input) & (df_kullanicilar['Şifre'] == str(sifre_input))]
                
                if not kullanici.empty:
                    lisans_durumu = kullanici['Lisans Durumu'].values[0]
                    
                    # 2. Lisans Kontrolü (Ticari Kilit)
                    if str(lisans_durumu).strip().lower() != "aktif":
                        st.error("❌ Kurumunuzun lisans süresi dolmuş veya askıya alınmıştır. Lütfen sistem yöneticisiyle iletişime geçin.")
                    else:
                        st.session_state['giris_yapildi'] = True
                        st.session_state['kullanici'] = kadi_input
                        st.session_state['birlik'] = kullanici['Birlik Adı'].values[0]
                        st.session_state['yetki'] = kullanici['Yetki Türü'].values[0]
                        st.success("Giriş başarılı, yönlendiriliyorsunuz...")
                        st.rerun()
                else:
                    st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    birlik_adi = st.session_state['birlik']
    yetki_turu = st.session_state['yetki']

    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: 
        st.title(f"🏢 {birlik_adi}")
        st.subheader(f"Yetkili Modül: {yetki_turu} Deposu")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']}")
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()
            
    st.divider()
    
    tablo_adi = f"{birlik_adi} - {yetki_turu} Deposu"
    
    if yetki_turu in ["Gida", "Temizlik", "Esya", "Kiyafet"]:
        try:
            aktif_tablo = client.open(tablo_adi).get_worksheet(0)
            df_depo = pd.DataFrame(aktif_tablo.get_all_records())
            st.success(f"✅ {tablo_adi} veri tabanına bağlandı.")
            st.dataframe(df_depo, use_container_width=True)
        except Exception as e:
            st.error(f"❌ '{tablo_adi}' bulunamadı veya servis hesabına yetki verilmedi.")
    elif yetki_turu == "Yonetici":
        st.info("📊 Yönetici paneli tüm alt depoları okuyacak şekilde yapılandırılacak.")
