import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
import requests
import qrcode
from io import BytesIO

st.set_page_config(page_title="MİDES", page_icon="📦", layout="wide")

try:
    google_json_str = st.secrets["google_json"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.error("Gizli kasa ayarları eksik!")
    st.stop()

def telegram_mesaj_gonder(mesaj):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj})
    except:
        pass

scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
client = gspread.authorize(Credentials.from_service_account_info(json.loads(google_json_str), scopes=scope))

if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'birlik': "", 'yetki': ""})

if not st.session_state['giris_yapildi']:
    st.markdown("<h1 style='text-align: center;'>🏢 MİDES - Merkezi Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login"):
            kadi = st.text_input("Kullanıcı Adı")
            sifre = st.text_input("Şifre", type="password")
            if st.form_submit_button("Sisteme Giriş Yap", use_container_width=True):
                df_kul = pd.DataFrame(client.open("MİDES - Merkez Kontrol").get_worksheet(0).get_all_records())
                kullanici = df_kul[(df_kul['Kullanıcı Adı'] == kadi) & (df_kul['Şifre'] == str(sifre))]
                if not kullanici.empty and str(kullanici['Lisans Durumu'].values[0]).strip().lower() == "aktif":
                    st.session_state.update({'giris_yapildi': True, 'kullanici': kadi, 'birlik': kullanici['Birlik Adı'].values[0], 'yetki': kullanici['Yetki Türü'].values[0]})
                    st.rerun()
                else:
                    st.error("Hatalı giriş veya lisans süresi dolmuş!")
else:
    birlik = st.session_state['birlik']
    yetki = st.session_state['yetki']
    
    col_baslik, col_kullanici = st.columns([4, 1])
    with col_baslik:
        st.markdown(f"<h1>📦 MİDES - Merkezi İkmal ve Depo Sistemi</h1>", unsafe_allow_html=True)
        st.caption(f"{birlik} - {yetki} Deposu")
    with col_kullanici:
        st.write(f"👤 *{st.session_state['kullanici']}*")
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()
    
    if yetki in ["Gida", "Temizlik", "Esya", "Kiyafet"]:
        tablo_adi = f"{birlik} - {yetki} Deposu"
        aktif_tablo = client.open(tablo_adi).get_worksheet(0)
        df = pd.DataFrame(aktif_tablo.get_all_records())
        
        if 'Kritik Seviye' not in df.columns: df['Kritik Seviye'] = 20
        df['Miktar'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)

        t_ozet, t_ekle, t_guncelle, t_hizli, t_kart, t_gecmis = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "📇 Ürün Kartı", "📄 Geçmiş"])

        with t_ozet:
            st.markdown("### 📋 Depo Uyarıları")
            bugun = datetime.now()
            uyari_yok = True
            
            rapor_metni = f"📊 {birlik} - {yetki} Deposu Günlük Rapor\n\n"
            
            for _, row in df.iterrows():
                try:
                    skt_tarihi = datetime.strptime(str(row['SKT']), "%Y-%m-%d")
                    fark_gun = (skt_tarihi - bugun).days
                    
                    if fark_gun < 0:
                        mesaj = f"❌ {row['Ürün Adı']} (Stok No: {row['Stok No']} | {row['Miktar']} {row['Birim']}) - TARİHİ GEÇTİ! ({row['SKT']})"
                        st.error(mesaj)
                        rapor_metni += mesaj + "\n"
                        uyari_yok = False
                    elif fark_gun <= 30:
                        mesaj = f"⚠️ {row['Ürün Adı']} (Stok No: {row['Stok No']} | {row['Miktar']} {row['Birim']}) - SKT'ye {fark_gun} gün kaldı! ({row['SKT']})"
                        st.warning(mesaj)
                        rapor_metni += mesaj + "\n"
                        uyari_yok = False
                except: pass

                if row['Miktar'] <= row['Kritik Seviye']:
                    mesaj = f"📉 STOK ALARMI: {row['Ürün Adı']} (Stok No: {row['Stok No']}) bitmek üzere! (Kalan: {row['Miktar']} {row['Birim']})"
                    st.info(mesaj) # Görseldeki mavi/gri kutu tasarımı için
                    rapor_metni += mesaj + "\n"
                    uyari_yok = False
            
            if uyari_yok:
                st.success("Depoda kritik uyarı bulunmamaktadır.")
                rapor_metni += "Tüm stoklar ve tarihler uygun seviyededir."
            
            if st.button("📲 Telegram'a Rapor Gönder"):
                telegram_mesaj_gonder(rapor_metni)
                st.success("Rapor başarıyla gönderildi!")
            
            st.markdown("---")
            st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
            if not df.empty:
                ozet_df = df.groupby(['Stok No', 'Ürün Adı', 'Birim'])['Miktar'].sum().reset_index()
                ozet_df = ozet_df.rename(columns={'Miktar': 'Toplam Miktar'})
                st.dataframe(ozet_df, use_container_width=True, hide_index=True)
            
            st.markdown("### 🔍 Detaylı Parti Listesi")
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # --- Otomatik Sabah Raporu Kontrolü ---
            su_an = datetime.now()
            if su_an.hour == 8 and 'sabah_raporu_gonderildi' not in st.session_state:
                telegram_mesaj_gonder(rapor_metni)
                st.session_state['sabah_raporu_gonderildi'] = True
            elif su_an.hour != 8 and 'sabah_raporu_gonderildi' in st.session_state:
                del st.session_state['sabah_raporu_gonderildi']

        with t_ekle:
            with st.form("ekle"):
                c1, c2 = st.columns(2)
                with c1:
                    s_no = st.text_input("Stok No")
                    u_ad = st.text_input("Ürün Adı")
                    mik = st.number_input("Miktar", min_value=0)
                    birim = st.selectbox("Birim", ["Kg", "Litre", "Adet", "Paket"])
                with c2:
                    k_sev = st.number_input("Kritik Seviye", value=20)
                    u_tar = st.date_input("Üretim Tarihi")
                    skt = st.date_input("SKT")
                if st.form_submit_button("Kaydet") and u_ad:
                    aktif_tablo.append_row([len(df)+1 if not df.empty else 1, s_no, u_ad, mik, birim, bugun.strftime("%Y-%m-%d"), str(skt), str(u_tar), k_sev])
                    st.rerun()

        with t_guncelle:
            if not df.empty:
                with st.form("guncelle"):
                    secilen = st.selectbox("Ürün Seçin", df['Ürün Adı'].tolist())
                    islem = st.radio("İşlem", ["Stok Ekle", "Stok Düş"], horizontal=True)
                    deger = st.number_input("Miktar", min_value=1)
                    if st.form_submit_button("Güncelle"):
                        idx = df[df['Ürün Adı'] == secilen].index[0]
                        yeni = df.loc[idx, 'Miktar'] + deger if islem == "Stok Ekle" else df.loc[idx, 'Miktar'] - deger
                        if yeni >= 0:
                            aktif_tablo.update_cell(int(idx)+2, 4, yeni)
                            st.rerun()

        with t_hizli:
            st.info("Barkod okuyucu ile hızlı işlem menüsü.")
            with st.form("qr_islem"):
                qr_no = st.text_input("Barkod / Stok No")
                islem_t = st.radio("Tipi", ["Giriş", "Çıkış"], horizontal=True)
                val = st.number_input("Miktar", min_value=1)
                if st.form_submit_button("Uygula") and qr_no:
                    eslesme = df[df['Stok No'].astype(str) == str(qr_no)]
                    if not eslesme.empty:
                        idx = eslesme.index[0]
                        yeni = df.loc[idx, 'Miktar'] + val if islem_t == "Giriş" else df.loc[idx, 'Miktar'] - val
                        if yeni >= 0:
                            aktif_tablo.update_cell(int(idx)+2, 4, yeni)
                            st.rerun()

        with t_kart:
            if not df.empty:
                qr_urun = st.selectbox("QR Üretilecek Ürün", df['Ürün Adı'].tolist())
                if st.button("QR Oluştur"):
                    stok_kodu = str(df[df['Ürün Adı'] == qr_urun].iloc[0]['Stok No'])
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(stok_kodu)
                    qr.make(fit=True)
                    buf = BytesIO()
                    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
                    st.image(buf.getvalue(), width=250)

        with t_gecmis:
            st.info("Geçmiş işlem kayıtları yakında eklenecektir.")
