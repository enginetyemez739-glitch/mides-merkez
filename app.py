import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
import requests
import qrcode
from io import BytesIO

st.set_page_config(page_title="MİDES - Merkezi Sistem", page_icon="🏢", layout="wide")

# --- GİZLİ KASA AYARLARI VE TELEGRAM ---
try:
    google_json_str = st.secrets["google_json"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except Exception as e:
    st.error(f"Gizli kasa (Secrets) ayarları eksik! Hata: {e}")
    st.stop()

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}
    try:
        requests.post(url, data=payload)
    except:
        pass

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(google_json_str)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

try:
    merkez_tablosu = client.open("MİDES - Merkez Kontrol").get_worksheet(0)
    df_kullanicilar = pd.DataFrame(merkez_tablosu.get_all_records())
except:
    st.error("Google Drive'da 'MİDES - Merkez Kontrol' tablosu bulunamadı.")
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
                kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adı'] == kadi_input) & (df_kullanicilar['Şifre'] == str(sifre_input))]
                
                if not kullanici.empty:
                    if str(kullanici['Lisans Durumu'].values[0]).strip().lower() != "aktif":
                        st.error("❌ Kurumunuzun lisans süresi dolmuş veya askıya alınmıştır.")
                    else:
                        st.session_state['giris_yapildi'] = True
                        st.session_state['kullanici'] = kadi_input
                        st.session_state['birlik'] = kullanici['Birlik Adı'].values[0]
                        st.session_state['yetki'] = kullanici['Yetki Türü'].values[0]
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
            
            # --- SEKMELER OLUŞTURMA ---
            tab1, tab2, tab3, tab4 = st.tabs(["📦 Stok Durumu", "➕ Yeni Ürün Ekle", "🔄 Stok Güncelle / Düş", "🔲 QR Kod Üret"])
            
            with tab1:
                st.subheader("Mevcut Depo Durumu")
                st.dataframe(df_depo, use_container_width=True)
                
            with tab2:
                st.subheader("Depoya Yeni Ürün Ekle")
                with st.form("urun_ekle_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        yeni_stok_no = st.text_input("Stok No")
                        yeni_urun_adi = st.text_input("Ürün Adı")
                        yeni_miktar = st.number_input("Miktar", min_value=0)
                    with col2:
                        yeni_birim = st.selectbox("Birim", ["Kg", "Litre", "Adet", "Kutu", "Paket"])
                        yeni_uretim = st.date_input("Üretim Tarihi")
                        yeni_skt = st.date_input("Son Kullanma Tarihi (SKT)")
                    
                    if st.form_submit_button("Ürünü Kaydet", use_container_width=True):
                        if yeni_urun_adi != "":
                            yeni_id = 1 if df_depo.empty else int(df_depo['ID'].max()) + 1
                            yeni_satir = [yeni_id, yeni_stok_no, yeni_urun_adi, yeni_miktar, yeni_birim, datetime.now().strftime("%Y-%m-%d"), str(yeni_skt), str(yeni_uretim)]
                            aktif_tablo.append_row(yeni_satir)
                            st.success(f"✅ {yeni_urun_adi} başarıyla eklendi!")
                            st.rerun()
                            
            with tab3:
                st.subheader("Stok Güncelle")
                if not df_depo.empty:
                    with st.form("stok_guncelle_form"):
                        secilen_urun = st.selectbox("İşlem Yapılacak Ürünü Seçin", df_depo['Ürün Adı'].tolist())
                        islem_turu = st.radio("İşlem Türü", ["Stok Düş (Çıkış)", "Stok Ekle (Giriş)"], horizontal=True)
                        islem_miktari = st.number_input("Miktar", min_value=1)
                        
                        if st.form_submit_button("Güncelle", use_container_width=True):
                            satir_index = df_depo[df_depo['Ürün Adı'] == secilen_urun].index[0]
                            mevcut_miktar = int(df_depo.loc[satir_index, 'Miktar'])
                            yeni_stok = mevcut_miktar - islem_miktari if islem_turu == "Stok Düş (Çıkış)" else mevcut_miktar + islem_miktari
                                
                            if yeni_stok < 0:
                                st.error("❌ Stok 0'ın altına düşemez!")
                            else:
                                aktif_tablo.update_cell(int(satir_index) + 2, 4, yeni_stok)
                                st.success(f"✅ Stok güncellendi. Yeni miktar: {yeni_stok}")
                                
                                # Telegram Kritik Stok Uyarısı (20 birim altı)
                                if yeni_stok < 20:
                                    uyari = f"⚠️ KRİTİK STOK UYARISI\n🏢 Kurum: {birlik_adi}\n📦 Modül: {yetki_turu}\n🏷️ Ürün: {secilen_urun}\n📉 Kalan Stok: {yeni_stok}"
                                    telegram_mesaj_gonder(uyari)
                                    st.warning("Kritik stok seviyesine düşüldü, Telegram üzerinden yöneticiye bilgi verildi!")
                                st.rerun()

            with tab4:
                st.subheader("QR Kod Oluştur")
                if not df_depo.empty:
                    secilen_qr_urun = st.selectbox("QR Kod Üretilecek Ürün", df_depo['Ürün Adı'].tolist())
                    if st.button("QR Kod Üret"):
                        urun_bilgisi = df_depo[df_depo['Ürün Adı'] == secilen_qr_urun].iloc[0]
                        qr_metni = f"Kurum: {birlik_adi}\nModül: {yetki_turu}\nÜrün: {urun_bilgisi['Ürün Adı']}\nStok No: {urun_bilgisi['Stok No']}\nMiktar: {urun_bilgisi['Miktar']} {urun_bilgisi['Birim']}\nSKT: {urun_bilgisi['SKT']}"
                        
                        qr = qrcode.QRCode(version=1, box_size=10, border=5)
                        qr.add_data(qr_metni)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        
                        buf = BytesIO()
                        img.save(buf, format="PNG")
                        st.image(buf.getvalue(), caption=f"{secilen_qr_urun} QR Kodu", width=300)
                        
        except Exception as e:
            st.error(f"❌ Veritabanı bağlantı hatası. Lütfen tablo adını ve yetkileri kontrol edin.")
    elif yetki_turu == "Yonetici":
        st.info("📊 Yönetici paneli tüm alt depoları okuyacak şekilde yapılandırılacak.")
