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
    st.error("Gizli kasa (Secrets) ayarları eksik!")
    st.stop()

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj})
    except:
        pass

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(json.loads(google_json_str), scopes=scope)
client = gspread.authorize(creds)

try:
    df_kullanicilar = pd.DataFrame(client.open("MİDES - Merkez Kontrol").get_worksheet(0).get_all_records())
except:
    st.error("Google Drive bağlantı hatası.")
    st.stop()

if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'birlik': "", 'yetki': ""})

# --- GİRİŞ EKRANI ---
if not st.session_state['giris_yapildi']:
    st.markdown("<h1 style='text-align: center;'>🏢 MİDES - Merkezi Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi = st.text_input("Kullanıcı Adı")
            sifre = st.text_input("Şifre", type="password")
            if st.form_submit_button("Sisteme Giriş Yap", use_container_width=True):
                kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adı'] == kadi) & (df_kullanicilar['Şifre'] == str(sifre))]
                if not kullanici.empty:
                    if str(kullanici['Lisans Durumu'].values[0]).strip().lower() != "aktif":
                        st.error("❌ Kurumunuzun lisans süresi dolmuş.")
                    else:
                        st.session_state.update({'giris_yapildi': True, 'kullanici': kadi, 'birlik': kullanici['Birlik Adı'].values[0], 'yetki': kullanici['Yetki Türü'].values[0]})
                        st.rerun()
                else:
                    st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    # --- ANA PANEL ---
    birlik_adi = st.session_state['birlik']
    yetki_turu = st.session_state['yetki']
    tablo_adi = f"{birlik_adi} - {yetki_turu} Deposu"

    c1, c2 = st.columns([4, 1])
    with c1: 
        st.title(f"🏢 {birlik_adi} - {yetki_turu} Deposu")
    with c2:
        st.write(f"👤 {st.session_state['kullanici']}")
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()
    st.divider()
    
    if yetki_turu in ["Gida", "Temizlik", "Esya", "Kiyafet"]:
        try:
            aktif_tablo = client.open(tablo_adi).get_worksheet(0)
            df_depo = pd.DataFrame(aktif_tablo.get_all_records())
            
            # Kritik Seviye Sütunu Kontrolü (Yoksa varsayılan 20 ekler)
            if 'Kritik Seviye' not in df_depo.columns:
                df_depo['Kritik Seviye'] = 20

            t1, t2, t3, t4 = st.tabs(["📦 Durum & Rapor", "➕ Yeni Kayıt", "🔄 Hızlı İşlem (QR/Barkod)", "🔲 QR Üretici"])
            
            # --- 1. DURUM VE RAPOR ---
            with t1:
                if not df_depo.empty:
                    c_uyari, c_rapor = st.columns([3, 1])
                    with c_uyari:
                        uyari_mesajlari = []
                        df_depo['Miktar'] = pd.to_numeric(df_depo['Miktar'], errors='coerce').fillna(0)
                        df_depo['Kritik Seviye'] = pd.to_numeric(df_depo['Kritik Seviye'], errors='coerce').fillna(20)
                        
                        kritik_stoklar = df_depo[df_depo['Miktar'] <= df_depo['Kritik Seviye']]
                        if not kritik_stoklar.empty:
                            uyari_mesajlari.append(f"📉 *Kritik Stoklar:* {', '.join(kritik_stoklar['Ürün Adı'].astype(str).tolist())}")
                        
                        skt_gecenler, skt_yaklasanlar = [], []
                        bugun = datetime.now()
                        for _, row in df_depo.iterrows():
                            try:
                                fark = (datetime.strptime(str(row['SKT']), "%Y-%m-%d") - bugun).days
                                if fark < 0: skt_gecenler.append(row['Ürün Adı'])
                                elif fark <= 30: skt_yaklasanlar.append(row['Ürün Adı'])
                            except: pass
                        
                        if skt_gecenler: uyari_mesajlari.append(f"❌ *SKT Geçmiş:* {', '.join(skt_gecenler)}")
                        if skt_yaklasanlar: uyari_mesajlari.append(f"⏳ *SKT Yaklaşanlar:* {', '.join(skt_yaklasanlar)}")
                        
                        if uyari_mesajlari:
                            for msg in uyari_mesajlari: st.error(msg)
                        else:
                            st.success("✅ Tüm stoklar ve SKT durumları ideal seviyede.")
                            
                    with c_rapor:
                        if st.button("📱 Telegram'a Rapor Gönder", use_container_width=True):
                            rapor = f"📊 {birlik_adi} {yetki_turu} Özet Raporu\n\nToplam Ürün Kalemi: {len(df_depo)}\nKritik Ürün Sayısı: {len(kritik_stoklar)}\nSKT Riski: {len(skt_gecenler) + len(skt_yaklasanlar)} ürün"
                            telegram_mesaj_gonder(rapor)
                            st.success("Rapor gönderildi!")
                    
                    st.dataframe(df_depo, use_container_width=True)
            
            # --- 2. YENİ ÜRÜN EKLE ---
            with t2:
                with st.form("yeni_urun_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        stok_no = st.text_input("Barkod / Stok No (Zorunlu)")
                        urun_adi = st.text_input("Ürün Adı")
                        miktar = st.number_input("İlk Miktar", min_value=0)
                        birim = st.selectbox("Birim", ["Kg", "Litre", "Adet", "Paket"])
                    with col2:
                        k_seviye = st.number_input("Kritik Uyarı Seviyesi", min_value=1, value=20)
                        uretim_t = st.date_input("Üretim Tarihi")
                        skt_t = st.date_input("Son Kullanma Tarihi (SKT)")
                    
                    if st.form_submit_button("Ürünü Veritabanına Kaydet", use_container_width=True):
                        if urun_adi and stok_no:
                            yeni_id = 1 if df_depo.empty else int(df_depo['ID'].max()) + 1
                            # Kritik seviye 9. sütun olarak ekleniyor
                            aktif_tablo.append_row([yeni_id, stok_no, urun_adi, miktar, birim, datetime.now().strftime("%Y-%m-%d"), str(skt_t), str(uretim_t), k_seviye])
                            st.success("Ürün eklendi!")
                            st.rerun()
                        else:
                            st.error("Stok No ve Ürün Adı zorunludur.")

            # --- 3. QR / BARKOD İLE GÜNCELLEME ---
            with t3:
                st.info("💡 Barkod okuyucu veya QR cihazınızla Stok No alanına okutma yaparak doğrudan işlem yapabilirsiniz.")
                if not df_depo.empty:
                    with st.form("qr_islem_form"):
                        islem_stok_no = st.text_input("Barkod / Stok No Okutun")
                        islem_tipi = st.radio("İşlem Tipi", ["Giriş (Stok Ekle)", "Çıkış (Stok Düş)", "SKT Güncelle"], horizontal=True)
                        islem_degeri = st.number_input("Miktar (Giriş/Çıkış için)", min_value=1)
                        yeni_skt = st.date_input("Yeni SKT (Sadece SKT Güncellemesi İçin)")
                        
                        if st.form_submit_button("İşlemi Uygula"):
                            if islem_stok_no:
                                eslesenler = df_depo[df_depo['Stok No'].astype(str) == str(islem_stok_no)]
                                if not eslesenler.empty:
                                    satir_idx = eslesenler.index[0]
                                    mevcut_miktar = int(eslesenler['Miktar'].values[0])
                                    tablo_satir = int(satir_idx) + 2
                                    
                                    if islem_tipi == "SKT Güncelle":
                                        aktif_tablo.update_cell(tablo_satir, 7, str(yeni_skt))
                                        st.success("SKT Başarıyla güncellendi.")
                                    else:
                                        yeni_stok = mevcut_miktar + islem_degeri if "Giriş" in islem_tipi else mevcut_miktar - islem_degeri
                                        if yeni_stok < 0:
                                            st.error("Stok sıfırın altına düşemez.")
                                        else:
                                            aktif_tablo.update_cell(tablo_satir, 4, yeni_stok)
                                            st.success(f"Stok güncellendi. Yeni miktar: {yeni_stok}")
                                            k_sinir = int(eslesenler['Kritik Seviye'].values[0])
                                            if yeni_stok <= k_sinir:
                                                telegram_mesaj_gonder(f"⚠️ DÜŞÜK STOK: {eslesenler['Ürün Adı'].values[0]} ({yeni_stok} kaldı)")
                                    st.rerun()
                                else:
                                    st.error("Bu Stok Numarasına ait ürün bulunamadı!")
                            else:
                                st.warning("Lütfen bir Stok No okutun veya yazın.")

            # --- 4. QR KOD ÜRETİCİ ---
            with t4:
                if not df_depo.empty:
                    secilen_qr = st.selectbox("QR Kod Üretilecek Ürün", df_depo['Ürün Adı'].tolist())
                    if st.button("QR Oluştur"):
                        urun = df_depo[df_depo['Ürün Adı'] == secilen_qr].iloc[0]
                        qr_metni = f"{urun['Stok No']}"  # Sadece Stok No barkodu okutur gibi çalışması için
                        
                        qr = qrcode.QRCode(version=1, box_size=10, border=5)
                        qr.add_data(qr_metni)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        
                        buf = BytesIO()
                        img.save(buf, format="PNG")
                        st.image(buf.getvalue(), caption=f"{urun['Ürün Adı']} (QR İçeriği: {qr_metni})", width=250)
                        st.info("Bu QR kodu okuttuğunuzda 'Hızlı İşlem' sekmesindeki Stok No alanına otomatik olarak yazılacaktır.")

        except Exception as e:
            st.error(f"Veritabanı erişim hatası: {e}")
