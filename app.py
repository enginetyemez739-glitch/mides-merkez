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
                if not kullanici.empty:
            yetki = kullanici['Yetki'].values[0]
            
            if yetki == "Gida" or yetki == "Yonetici":
                st.session_state['kullanici'] = kadi_input
                st.session_state['rol'] = "admin" if yetki == "Yonetici" else "personel"
                
                # Yeni sütunları (Telegram ve İlk Giriş) sisteme alma
                ilk_giris = str(kullanici['İlk Giriş'].values[0]).strip().lower()
                st.session_state['telegram_token'] = str(kullanici['Telegram Token'].values[0])
                st.session_state['telegram_chat_id'] = str(kullanici['Chat ID'].values[0])
                
                # İlk giriş kontrolü ve 90 günlük şifre döngüsü
                if ilk_giris == "evet":
                    st.session_state['sifre_degistirme_modu'] = True
                    st.warning("⚠️ Sisteme ilk girişiniz! Lütfen devam etmek için şifrenizi belirleyin.")
                else:
                    son_guncelleme = pd.to_datetime(kullanici['Son Güncelleme'].values[0], errors='coerce')
                    gecen_gun = (datetime.today() - son_guncelleme).days
                    kalan_gun = 90 - gecen_gun
                    
                    if gecen_gun >= 90:
                        st.session_state['sifre_degistirme_modu'] = True
                    else:
                        st.session_state['sifre_degistirme_modu'] = False
                        st.session_state['giris_yapildi'] = True
                        
                        if kalan_gun <= 5:
                            st.warning(f"⚠️ Dikkat: Şifrenizin geçerlilik süresinin dolmasına {kalan_gun} gün kalmıştır.")
                        
                        st.rerun()
            else:
                st.error("❌ Bu depoya giriş yetkiniz bulunmamaktadır!")
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
        krt_sayisi = 0
        telegram_raporu = "⚠️ MİDES KRİTİK UYARI RAPORU ⚠️\n\n"
        
        for index, row in df.iterrows():
            urun_adi = str(row.get('Ürün Adı', 'Bilinmeyen Ürün')).strip()
            stok_no = str(row.get('Stok No', '-'))
            miktar_metni = str(row.get('Miktar', '0')).strip()
            birim = str(row.get('Birim', '')).strip()
            
            try:
                skt_metni = str(row.get('SKT', '')).strip()
                if skt_metni and skt_metni != "-" and skt_metni.lower() != "nan":
                    skt = datetime.strptime(skt_metni, '%Y-%m-%d').date()
                    kalan = (skt - bugun).days
                    uyari_baslik = f"{urun_adi} (Stok No: {stok_no} | {miktar_metni} {birim})"
                    
                    if kalan < 0:
                        st.error(f"❌ {uyari_baslik} - TARİHİ GEÇTİ! ({skt_metni})")
                        telegram_raporu += f"❌ {uyari_baslik} - TARİHİ GEÇTİ!\n"
                        krt_sayisi += 1
                    elif 0 <= kalan <= 30:
                        st.warning(f"⚠️ {uyari_baslik} - SKT'ye {kalan} gün kaldı! ({skt_metni})")
                        telegram_raporu += f"⚠️ {uyari_baslik} - {kalan} gün kaldı!\n"
                        krt_sayisi += 1
            except: pass
            
            try:
                kritik_metni = str(row.get('Kritik Stok', '10')).strip()
                if not miktar_metni or miktar_metni.lower() == "nan": miktar_metni = "0"
                if not kritik_metni or kritik_metni.lower() == "nan": kritik_metni = "10"
                
                miktar_val = float(miktar_metni)
                kritik_val = float(kritik_metni)
                
                if miktar_val <= kritik_val:
                    st.error(f"📉 STOK ALARMI: {urun_adi} (Stok No: {stok_no}) bitmek üzere! (Kalan: {int(miktar_val)} {birim})")
                    telegram_raporu += f"📉 ALARM: {urun_adi} (Stok No: {stok_no}) (Kalan: {int(miktar_val)} {birim})\n"
                    krt_sayisi += 1
            except: pass

        if krt_sayisi == 0:
            st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")
            telegram_raporu += "✅ Kritik ürün bulunmamaktadır. Depo güvende!"

        if st.button("📲 Telegram'a Rapor Gönder", type="primary"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Gönderildi!")
            
        st.divider()
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        try:
            df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
            toplam_stok_df = df.groupby('Stok No').agg({'Ürün Adı': 'first', 'Miktar_Sayi': 'sum', 'Birim': 'first'}).reset_index()
            toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
            toplam_stok_df = toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']]
            st.dataframe(toplam_stok_df, use_container_width=True, hide_index=True)
        except: st.info("Toplamlar hesaplanırken hata oluştu.")

        st.markdown("### 🔍 Detaylı Parti Listesi")
        gosterilecek_df = df.drop(columns=['Resim Yolu', 'Miktar_Sayi'], errors='ignore')
        st.dataframe(gosterilecek_df, use_container_width=True, hide_index=True)

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
